"""Pre-evaluation, label-free audit. Independently reconstruct completed numeric decisions."""
from pathlib import Path
import json,hashlib,re,ast,datetime
P=Path(__file__).parent
sha=lambda b:hashlib.sha256(b).hexdigest()
freeze=json.loads((P/'PRE-RESOURCE-CODE-FREEZE.json').read_text())
for name,h in freeze['code_hashes'].items():assert sha((P/name).read_bytes())==h,(name,'method changed')
module=ast.parse((P/'run_study.py').read_text());node=next(x for x in module.body if isinstance(x,ast.FunctionDef) and x.name=='parse');env={'re':re};exec(compile(ast.Module(body=[node],type_ignores=[]),'<parser-under-test>','exec'),env)
for text,cs,selected,valid in [('0',['a'],None,True),('1',['a'],'a',True),('2',['a'],None,False),('5',['a','b','c','d','e'],'e',True),(' 3\n',['a','b','c'],'c',True),('1.',['a'],None,False),('Answer: 1',['a'],None,False),('',[],None,False),('6',['a']*5,None,False)]:
 r=env['parse'](text,cs);assert (r['selected'],r['valid'])==(selected,valid)
def pick(text,cs):
 m=re.fullmatch(r'\s*([0-5])\s*',text)
 return cs[int(m[1])-1] if m and 1<=int(m[1])<=len(cs) else None
checks=[]
for f in sorted((P/'task-receipts').glob('development-*.json')):
 r=json.loads(f.read_text());packpath=P/'private-packs'/(r['instance_id']+'.json');pack=json.loads(packpath.read_text());assert r['pack_sha256']==sha(packpath.read_bytes());order=[s['candidates'][0] for s in pack['verifier_rounds']];assert len(order)==len(set(order))==20
 for rotation in range(4):
  arm='T'+str(rotation);rot=order[rotation:]+order[:rotation];assert pack['groups'][arm]==[rot[i::4] for i in range(4)];winners=[]
  for stage in pack['first_rounds'][arm]:
   d=json.loads((P/'outputs'/f"development-{r['instance_id']}-{arm}-s{stage['stage']}.json").read_text());selected=pick(d['response'],stage['candidates'])
   if selected:winners.append(selected)
  if winners:
   d=json.loads((P/'outputs'/f"development-{r['instance_id']}-{arm}-final.json").read_text());assert d['candidates']==winners;selected=pick(d['response'],winners)
  else:selected=None
  assert r['arms'][arm]['selected']==selected
 scores=[]
 for st in pack['verifier_rounds']:
  d=json.loads((P/'outputs'/f"development-{r['instance_id']}-V20-s{st['stage']}.json").read_text());m=re.fullmatch(r'\s*([0-3])\s*',d['response']);scores.append(int(m[1]) if m else -1)
 best=max(range(20),key=lambda i:(scores[i],-i));assert r['arms']['V20']['selected']==(order[best] if scores[best]>0 else None)
 votes=[sum(r['arms']['T'+str(i)]['selected']==s for i in range(4)) for s in order];best=max(range(20),key=lambda i:(votes[i],-i));assert r['arms']['T20']['selected']==(order[best] if votes[best] else None);assert r['arms']['T5']['selected']==r['arms']['T0']['selected'];checks.append(r['instance_id'])
statuses=[json.loads(f.read_text()) for f in (P/'logs').glob('call-development-*-status.json')];assert all(x['returncode']==0 and not x['stop_reason'] and x['peak_rss_kib']<=1500*1024 and x['elapsed_seconds']<=90.5 for x in statuses)
report={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'label_free':True,'scientific_code_unchanged_since_resource_freeze':True,'parser_unit_cases':9,'completed_development_tasks_reconstructed':checks,'governed_calls_checked':len(statuses),'peak_governed_rss_kib':max((x['peak_rss_kib'] for x in statuses),default=0),'no_gold_access':True,'status':'PASS'};(P/'DEVELOPMENT-LOGIC-AUDIT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
