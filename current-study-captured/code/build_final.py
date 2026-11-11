"""Build a final-round prompt from frozen chunks and already-selected group winners."""
from pathlib import Path
import json,sys,hashlib
P=Path(__file__).parent;iid,arm,assignment=sys.argv[1:4];M=Path('/downloads/gemma-genuine-feasibility');sys.path.insert(0,str(M/'runtime'));import litert_lm
sha=lambda b:hashlib.sha256(b).hexdigest();p=P/'private-packs'/(iid+'.json');pack=json.loads(p.read_text());symbols=json.loads(sys.argv[4]);assert len(symbols)<=4 and all(s in pack['chunks'] for s in symbols);t=pack['prompt_template'];prompt=t['prefix']+pack['issue']+t['middle']+'\n'.join(str(i)+'. '+pack['chunks'][s] for i,s in enumerate(symbols,1))+t['suffix']
engine=litert_lm.Engine(model_path=str(M/'gemma-4-E2B-it.litertlm'),backend=litert_lm.Backend.CPU(thread_count=2),max_num_tokens=1536,cache_dir=str(M/'cache'));tokens=len(engine.tokenize(prompt));assert tokens<=960
callid=f'{assignment}-{iid}-{arm}-final';record={'instance_id':iid,'assignment':assignment,'method':arm,'stage':'final','candidates':symbols,'prompt':prompt,'prompt_sha256':sha(prompt.encode()),'prompt_tokens':tokens,'pack_sha256':sha(p.read_bytes()),'query_sha256':pack['query_sha256']};d=P/'private-calls';d.mkdir(exist_ok=True);dest=d/(callid+'.json');dest.write_text(json.dumps(record,indent=2)+'\n');print('FINAL_PREPARED',callid,tokens,flush=True)
