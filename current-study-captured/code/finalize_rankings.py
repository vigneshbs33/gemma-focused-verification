from pathlib import Path
import json,sqlite3,hashlib,argparse,sys
import numpy as np
import method
P=Path(__file__).parent;sha=lambda b:hashlib.sha256(b).hexdigest();a=argparse.ArgumentParser();a.add_argument('--assignment',required=True);args=a.parse_args();cache=sqlite3.connect(P/'private-embedding-cache.sqlite');out=P/'rankings';out.mkdir(exist_ok=True);ready=0;waiting=0
for f in sorted((P/'private-semantic').glob('*.json')):
 m=json.loads(f.read_text());iid=m['instance_id']
 if m['assignment']!=args.assignment:continue
 dest=out/(iid+'.json')
 if dest.exists():ready+=1;continue
 keys=set(m['candidate_keys'].values())|{m['query_key']};vectors={}
 for key in keys:
  row=cache.execute('SELECT vector FROM vectors WHERE key=?',(key,)).fetchone()
  if row:vectors[key]=np.frombuffer(row[0],dtype='<f4')
 if len(vectors)!=len(keys):waiting+=1;continue
 pfile=P/'private-prepared'/(iid+'.json');assert sha(pfile.read_bytes())==m['prepared_sha256'];data=json.loads(pfile.read_text());proposal=data['proposal'];q=vectors[m['query_key']];scores={s:float(np.dot(q,vectors[k])) for s,k in m['candidate_keys'].items()};dense={arm:sorted(pool,key=lambda s:(-scores[s],s)) for arm,pool in proposal['pools'].items()}
 lex=proposal['lexical'];sp=set(proposal['pools']['semantic']);gp=set(proposal['pools']['structural']);ranks={'semantic20':method.fuse([s for s in lex['C2F'] if s in sp],dense['semantic'])}
 result={'instance_id':iid,'assignment':args.assignment,'plan_sha256':data['plan_sha256'],'method_sha256':data['method_sha256'],'prepared_sha256':m['prepared_sha256'],'semantic_manifest_sha256':sha(f.read_bytes()),'source_content_sha256':data['source_content_sha256'],'query_sha256':data['query_sha256'],'ranks':ranks,'pools':proposal['pools'],'dense_orders':dense,'dense_scores':scores,'graph':proposal['graph'],'graph_edges':proposal['graph_edges'],'unresolved_calls':proposal['unresolved_calls'],'deduplicated_symbols':proposal['deduplicated_symbols'],'duplicates':proposal['duplicates'],'parse_errors':proposal['parse_errors'],'embedding_tokens':{s:int(cache.execute('SELECT tokens FROM vectors WHERE key=?',(k,)).fetchone()[0]) for s,k in m['candidate_keys'].items()},'query_embedding_tokens':cache.execute('SELECT tokens FROM vectors WHERE key=?',(m['query_key'],)).fetchone()[0]}
 tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=2)+'\n');tmp.replace(dest);ready+=1;print('RANKS_READY',iid,{k:len(v) for k,v in ranks.items()},flush=True)
print('READY',ready,'WAITING',waiting,flush=True)
