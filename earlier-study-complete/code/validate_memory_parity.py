"""Compare resource-only implementation with retained pre-optimization development rankings."""
from pathlib import Path
import json,tarfile,tempfile,hashlib,argparse,time
import method
P=Path(__file__).parent;sha=lambda b:hashlib.sha256(b).hexdigest();a=argparse.ArgumentParser();a.add_argument('--count',type=int,default=3);args=a.parse_args();report=P/'MEMORY-OPTIMIZATION-PARITY.json';d=json.loads(report.read_text()) if report.exists() else {'checks':{},'synthetic_exact_score_fixtures':100,'accuracy_or_gold_access':False,'reason':'Retained AST objects plus simultaneous token lists/TF stats exceeded1500MiB onSympy. Stream per-file ASTcallstrings and BM25 query sufficientstatistics. No scorer/candidate/ranking change.'};n=0
for f in sorted((P/'private-prepared').glob('*.json')):
 old=json.loads(f.read_text());iid=old['instance_id']
 if old['method_sha256']==sha((P/'method.py').read_bytes()) or iid in d['checks']:continue
 with tempfile.TemporaryDirectory() as td:
  with tarfile.open(P/'source-archives'/(iid+'.tar.gz')) as tf:
   for m in tf:
    if not m.isfile() or '..' in Path(m.name).parts or Path(m.name).is_absolute():continue
    out=Path(td)/m.name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(tf.extractfile(m).read())
  start=time.monotonic();g=method.build(td);p=method.propose(g,old['query']);prior=old['proposal'];assert p['lexical']==prior['lexical'],(iid,'lexical_rank_mismatch');assert p['pools']==prior['pools'];assert p['graph_edges']==prior['graph_edges'];assert p['unresolved_calls']==prior['unresolved_calls'];assert p['duplicates']==prior['duplicates'];assert p['parse_errors']==prior['parse_errors'];assert p['graph']['ranking'][:320]==prior['graph']['ranking'];assert p['graph']['seeds']==prior['graph']['seeds'];assert p['graph']['evidence']==prior['graph']['evidence']
  d['checks'][iid]={'C2_C2F_fullrank_exact':True,'pools_exact':True,'graph_seed_evidence_rank_exact':True,'graph_edges':p['graph_edges'],'node_count':p['deduplicated_symbols'],'old_method_sha256':old['method_sha256'],'seconds':time.monotonic()-start};print('PARITY_PASS',iid,round(time.monotonic()-start,2),flush=True)
  del g,p,old
 d['new_method_sha256']=sha((P/'method.py').read_bytes());report.write_text(json.dumps(d,indent=2)+'\n');n+=1
 if n>=args.count:break
print('PARITY_CHECKED',len(d['checks']),flush=True)
