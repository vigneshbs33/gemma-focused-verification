"""Orchestration only: shard frozen semantic script into per-task input views.
No rank/score/accuracy changes; atomic vectors and manifests shared.
"""
from pathlib import Path
import json,hashlib,sqlite3,subprocess,sys,datetime
P=Path(__file__).parent;S=P/'embedding-shard';limit=int(sys.argv[1]) if len(sys.argv)>1 else 3;sha=lambda b:hashlib.sha256(b).hexdigest();frozen=json.loads((P/'PRE-EVALUATION-CODE-FREEZE.json').read_text());assert sha((S/'embed_chunk.py').read_bytes())==frozen['code_hashes']['embed_chunk.py'];assert all(sha((P/k).read_bytes())==v for k,v in frozen['code_hashes'].items())
for i in range(limit):
 db=sqlite3.connect(P/'private-embedding-cache.sqlite');keys={r[0] for r in db.execute('select key from vectors')};db.close();pending=None
 for f in sorted((P/'private-prepared').glob('*.json')):
  data=json.loads(f.read_text())
  if data['assignment']!='evaluation':continue
  manifest=P/'private-semantic'/f.name
  if manifest.exists():
   m=json.loads(manifest.read_text());assert m['prepared_sha256']==sha(f.read_bytes());want=set(m['candidate_keys'].values())|{m['query_key']}
   if want<=keys:continue
  pending=f;break
 if pending is None:print('ALL_EVAL_SEMANTICS_COMPLETE',len(keys),flush=True);break
 for f in (S/'private-prepared').glob('*.json'):f.unlink()
 (S/'private-prepared'/pending.name).symlink_to(pending)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S%f');tag='embed-eval-shard-'+stamp
 result=subprocess.run(['python',str(P/'bounded_job.py'),tag,'python',str(S/'embed_chunk.py'),'--assignment','evaluation','--max-docs','64'],capture_output=True,text=True)
 print(pending.stem,result.stdout.splitlines()[0] if result.stdout else '',flush=True)
 if result.returncode:print(result.stdout[-3000:],flush=True);sys.exit(1)
