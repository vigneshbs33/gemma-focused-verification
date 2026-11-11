from pathlib import Path
import argparse,json,hashlib,tarfile,tempfile,time,resource
import method
P=Path(__file__).parent;sha=lambda b:hashlib.sha256(b).hexdigest()
a=argparse.ArgumentParser();a.add_argument('--assignment',choices=['development','evaluation'],required=True);a.add_argument('--count',type=int,default=1);args=a.parse_args()
rows={r['instance_id']:r for r in map(json.loads,(P/'inference-only.jsonl').read_text().splitlines())};tasks=json.loads((P/'COHORT-QUALIFICATION.json').read_text())['selected'];outdir=P/'private-prepared';outdir.mkdir(exist_ok=True);done=0
for t in sorted(tasks,key=lambda t:t['instance_id']):
 if t['assignment']!=args.assignment:continue
 iid=t['instance_id'];dest=outdir/(iid+'.json')
 if dest.exists():continue
 start=time.monotonic();qa=json.loads((P/'qa'/(iid+'.json')).read_text());assert not qa.get('error') and qa['patch_check_rc']==0 and qa['old_targets_present'];arc=P/'source-archives'/(iid+'.tar.gz');assert sha(arc.read_bytes())==qa['private_python_archive_sha256']
 q=rows[iid]['problem_statement'];assert sha(q.encode())==t['query_sha256']
 with tempfile.TemporaryDirectory(prefix='stronger-index-') as td:
  with tarfile.open(arc) as tf:
   for m in tf:
    if not m.isfile() or '..' in Path(m.name).parts or Path(m.name).is_absolute():continue
    f=Path(td)/m.name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(tf.extractfile(m).read())
  pins={str(f.relative_to(td)):sha(f.read_bytes()) for f in sorted(Path(td).rglob('*.py'))};assert pins==qa['source_file_pins'];index=method.build(td);proposal=method.propose(index,q)
  needed=set(proposal['pools']['semantic'])|set(proposal['pools']['structural'])|set(proposal['lexical']['C2'][:20])|set(proposal['lexical']['C2F'][:5]);records={}
  for s in sorted(needed):
   n=index['nodes'][s];r={k:n[k] for k in ['symbol','path','start','end','kind','lines','header','body_start']};r['doclines']=sorted(n['doclines']);r['same_qualified_count']=1+sum(x['symbol']==s for x in index['duplicates']);r['embedding_text']=r['path']+'\n'+s+'\n'+'\n'.join(r['lines']);records[s]=r
  # Compact scientific graph evidence, all full node code stays private.
  graph=proposal['graph'];proposal['graph']={k:graph[k] for k in ['seeds','evidence','depth'] }|{'ranking':graph['ranking'][:320]}
  out={'instance_id':iid,'assignment':t['assignment'],'query':q,'query_sha256':t['query_sha256'],'source_content_sha256':qa['source_content_sha256'],'plan_sha256':sha((P/'PLAN.md').read_bytes()),'method_sha256':sha((P/'method.py').read_bytes()),'records':records,'proposal':proposal,'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
  tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(out)+'\n');tmp.replace(dest)
  print('PREPARED',iid,'nodes',len(index['nodes']),'edges',len(index['edges']),'union_records',len(records),'seconds',round(out['elapsed_seconds'],2),'rss',out['peak_rss_kib'],flush=True)
  del index,proposal,records,out
 done+=1
 if done>=args.count:break
