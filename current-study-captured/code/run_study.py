"""Atomic tournament execution. No dataset, gold or patch access. New-call budget bounds each launch."""
from pathlib import Path
import json,sys,hashlib,re,subprocess,argparse,datetime
P=Path(__file__).parent;sha=lambda b:hashlib.sha256(b).hexdigest();a=argparse.ArgumentParser();a.add_argument('--assignment',choices=['development','evaluation'],required=True);a.add_argument('--max-calls',type=int,default=16);args=a.parse_args();new=0
for d in ['private-calls','outputs','task-receipts']:(P/d).mkdir(exist_ok=True)
if args.assignment=='evaluation':
 freeze=json.loads((P/'EVALUATION-FREEZE.json').read_text())
 for f,h in freeze['code_hashes'].items():assert sha((P/f).read_bytes())==h,(f,'code changed after freeze')

def parse(response,candidates):
 m=re.fullmatch(r'\s*([0-5])\s*',response)
 if not m:return {'choice':None,'selected':None,'valid':False,'abstention':False}
 n=int(m.group(1));valid=0<=n<=len(candidates)
 return {'choice':n,'selected':candidates[n-1] if valid and n else None,'valid':valid,'abstention':n==0}

def output(callid):
 f=P/'outputs'/(callid+'.json')
 if not f.exists():return None
 data=json.loads(f.read_text());q=json.loads((P/'private-calls'/(callid+'.json')).read_text());assert data['prompt_sha256']==q['prompt_sha256'];assert data['candidates']==q['candidates'];assert data['prompt_tokens']<=960;assert data['peak_rss_kib']<=1500*1024
 status=P/'logs'/('call-'+callid+'-status.json')
 if status.exists():
  st=json.loads(status.read_text());assert st['returncode']==0 and not st['stop_reason']
 else:raise RuntimeError(('output_exists_without_governorstatus_do_not_repeat',callid))
 return data

def call(callid):
 global new
 if new>=args.max_calls:return False
 rc=subprocess.run(['python',str(P/'bounded_job.py'),'call-'+callid,'python',str(P/'run_arm.py'),callid],capture_output=True,text=True)
 # Keep model/debug output in governor log; report only resource state, never accuracy.
 print('CALL',callid,'RC',rc.returncode,flush=True)
 if rc.returncode:
  print(rc.stdout[-4000:],flush=True);raise RuntimeError(('call_failed_stop',callid))
 new+=1;return True

for p in sorted((P/'private-packs').glob('*.json')):
 pack=json.loads(p.read_text());iid=pack['instance_id'];assignment=pack['assignment']
 if assignment!=args.assignment:continue
 if args.assignment=='evaluation':assert sha(p.read_bytes())==freeze['pack_hashes'][p.name]
 receipt=P/'task-receipts'/(assignment+'-'+iid+'.json')
 if receipt.exists():continue
 result={'instance_id':iid,'assignment':assignment,'pack_sha256':sha(p.read_bytes()),'arms':{},'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};incomplete=False
 for arm,stages in pack['first_rounds'].items():
  stage_records=[];winners=[]
  for stage in stages:
   n=stage['stage'];candidates=stage['candidates'];callid=f'{assignment}-{iid}-{arm}-s{n}'
   if not candidates:stage_records.append({'stage':n,'call_id':None,'selected':None,'virtual_empty_group':True});continue
   qpath=P/'private-calls'/(callid+'.json');q={'instance_id':iid,'assignment':assignment,'method':arm,'stage':n,'pack_sha256':sha(p.read_bytes()),'query_sha256':pack['query_sha256']}|stage
   if qpath.exists():assert json.loads(qpath.read_text())==q
   else:qpath.write_text(json.dumps(q,indent=2)+'\n')
   data=output(callid)
   if data is None:
    if not call(callid):incomplete=True;break
    data=output(callid)
   decision=parse(data['response'],candidates);stage_records.append({'stage':n,'call_id':callid,'output_sha256':sha((P/'outputs'/(callid+'.json')).read_bytes())}|decision)
   if decision['selected']:winners.append(decision['selected'])
  if incomplete:break
  if False:result['arms'][arm]={'stages':stage_records,'selected':stage_records[0].get('selected'),'final':None,'calls':sum(x['call_id'] is not None for x in stage_records)};continue
  finalid=f'{assignment}-{iid}-{arm}-final'
  if not winners:final={'call_id':None,'selected':None,'virtual_no_survivors':True}
  else:
   qpath=P/'private-calls'/(finalid+'.json')
   if not qpath.exists():
    rc=subprocess.run(['python',str(P/'bounded_job.py'),'build-'+finalid,'python',str(P/'build_final.py'),iid,arm,assignment,json.dumps(winners)],capture_output=True,text=True)
    if rc.returncode:print(rc.stdout[-4000:],flush=True);raise RuntimeError(('final_pack_failed',finalid))
   q=json.loads(qpath.read_text());assert q['candidates']==winners and q['pack_sha256']==sha(p.read_bytes());data=output(finalid)
   if data is None:
    if not call(finalid):incomplete=True;break
    data=output(finalid)
   final={'call_id':finalid,'output_sha256':sha((P/'outputs'/(finalid+'.json')).read_bytes())}|parse(data['response'],winners)
  result['arms'][arm]={'stages':stage_records,'final':final,'selected':final.get('selected'),'calls':sum(x['call_id'] is not None for x in stage_records)+(final['call_id'] is not None)}
 if incomplete:break
 scores=[]
 for stage in pack['verifier_rounds']:
  callid=f'{assignment}-{iid}-V20-s{stage["stage"]}';qpath=P/'private-calls'/(callid+'.json');q={'instance_id':iid,'assignment':assignment,'method':'V20','pack_sha256':sha(p.read_bytes()),'query_sha256':pack['query_sha256']}|stage
  if qpath.exists():assert json.loads(qpath.read_text())==q
  else:qpath.write_text(json.dumps(q,indent=2)+'\n')
  data=output(callid)
  if data is None:
   if not call(callid):incomplete=True;break
   data=output(callid)
  match=re.fullmatch(r'\s*([0-3])\s*',data['response']);scores.append({'call_id':callid,'symbol':stage['candidates'][0],'score':int(match.group(1)) if match else -1,'valid':bool(match),'output_sha256':sha((P/'outputs'/(callid+'.json')).read_bytes())})
 if incomplete:break
 order=[s['candidates'][0] for s in pack['verifier_rounds']];priority={s:i for i,s in enumerate(order)};ranked=sorted(scores,key=lambda r:(-r['score'],priority[r['symbol']],r['symbol']));selected=ranked[0]['symbol'] if ranked and ranked[0]['score']>0 else None
 result['arms']['V20']={'scores':scores,'selected':selected,'calls':len(scores)}
 votes={s:sum(result['arms'][k]['selected']==s for k in ['T0','T1','T2','T3']) for s in order};best=sorted(order,key=lambda s:(-votes[s],priority[s],s));result['arms']['T20']={'votes':votes,'selected':best[0] if votes[best[0]]>0 else None,'calls':sum(result['arms'][k]['calls'] for k in ['T0','T1','T2','T3'])};result['arms']['T5']={'selected':result['arms']['T0']['selected'],'calls':result['arms']['T0']['calls']}
 receipt.write_text(json.dumps(result,indent=2)+'\n');print('TASK_COMPLETE',iid,'CALLS',{arm:d['calls'] for arm,d in result['arms'].items()},flush=True)
print('NEW_CALLS',new,'TASK_RECEIPTS',len(list((P/'task-receipts').glob(args.assignment+'-*.json'))),flush=True)
