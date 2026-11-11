"""Bounded cached semantic preprocessing, never uses gold/patches. Exactly pinned local weights."""
from pathlib import Path
import os,sys,json,time,hashlib,sqlite3,resource,argparse,importlib.util
P=Path(__file__).parent;sys.path.insert(0,str(P/'runtime'));os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import torch,numpy as np
from transformers import AutoTokenizer
a=argparse.ArgumentParser();a.add_argument('--assignment',choices=['development','evaluation'],required=True);a.add_argument('--max-docs',type=int,default=64);args=a.parse_args()
torch.set_num_threads(2);torch.set_num_interop_threads(1);M=P/'coderank-model';tokenizer=AutoTokenizer.from_pretrained(str(M),local_files_only=True);sha=lambda b:hashlib.sha256(b).hexdigest();wsha='827529bcd58aef0d9082e66eeff7e7d53a02f62bd005f841a26b3d3e2fb17ebe'
cache=sqlite3.connect(P/'private-embedding-cache.sqlite');cache.execute('CREATE TABLE IF NOT EXISTS vectors(key TEXT PRIMARY KEY, vector BLOB, tokens INTEGER, seconds REAL)');cache.commit();pending={};token_dir=P/'private-token-cache';token_dir.mkdir(exist_ok=True);manifest_dir=P/'private-semantic';manifest_dir.mkdir(exist_ok=True)
for f in sorted((P/'private-prepared').glob('*.json')):
 data=json.loads(f.read_text())
 if data['assignment']!=args.assignment:continue
 # Only semantic pools require embedding; plain C2-only tournament candidates do not.
 symbols=sorted(set(data['proposal']['pools']['semantic'])|set(data['proposal']['pools']['structural']));manifest={'instance_id':data['instance_id'],'assignment':args.assignment,'prepared_sha256':sha(f.read_bytes()),'candidate_keys':{},'query_key':None,'model_weight_sha256':wsha,'document_token_ceiling':256,'query_token_ceiling':512}
 tokenfile=token_dir/(data['instance_id']+'.json');pin=sha(f.read_bytes())
 if tokenfile.exists():
  tokenized=json.loads(tokenfile.read_text());assert tokenized['prepared_sha256']==pin
  entries=tokenized['entries']
 else:
  inputs=[(None,'Represent this query for searching relevant code: '+data['query'],512)]+[(s,data['records'][s]['embedding_text'],256) for s in symbols];entries=[]
  for symbol,text,limit in inputs:
   tok=dict(tokenizer(text,truncation=True,max_length=limit,return_tensors=None));key=sha((wsha+json.dumps(tok,sort_keys=True)).encode());entries.append({'symbol':symbol,'key':key,'tokens':tok})
  tokenfile.write_text(json.dumps({'prepared_sha256':pin,'entries':entries})+'\n')
 for entry in entries:
  symbol,key,tok=entry['symbol'],entry['key'],entry['tokens']
  if symbol is None:manifest['query_key']=key
  else:manifest['candidate_keys'][symbol]=key
  if cache.execute('SELECT 1 FROM vectors WHERE key=?',(key,)).fetchone() is None and len(pending)<args.max_docs:pending.setdefault(key,tok)
 (manifest_dir/(data['instance_id']+'.json')).write_text(json.dumps(manifest,indent=2)+'\n')
 del data,entries
if not pending:print('NO_PENDING',args.assignment,flush=True);sys.exit(0)
spec=importlib.util.spec_from_file_location('coderank_pinned',M/'__init__.py',submodule_search_locations=[str(M)]);pkg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pkg;spec.loader.exec_module(pkg)
from coderank_pinned.configuration_hf_nomic_bert import NomicBertConfig
from coderank_pinned.modeling_hf_nomic_bert import NomicBertModel
from safetensors.torch import load_file
start=time.monotonic();conf=NomicBertConfig.from_json_file(str(M/'config.json'));conf.use_flash_attn=False;conf.fused_bias_fc=False;conf.fused_dropout_add_ln=False;conf.use_cache=False
model=NomicBertModel(conf,add_pooling_layer=False);weights=load_file(str(M/'model.safetensors'));model.load_state_dict(weights,strict=True);del weights;model.eval();n=0
with torch.inference_mode():
 for key,tok in pending.items():
  inputs={k:torch.tensor([v],dtype=torch.long) for k,v in tok.items()};s=time.monotonic();v=torch.nn.functional.normalize(model(**inputs).last_hidden_state[:,0],p=2,dim=1)[0];assert torch.isfinite(v).all() and abs(float(v.norm())-1)<1e-5
  arr=v.numpy().astype('<f4');cache.execute('INSERT OR IGNORE INTO vectors VALUES(?,?,?,?)',(key,arr.tobytes(),len(tok['input_ids']),time.monotonic()-s));cache.commit();n+=1
print('EMBEDDED',n,'in',round(time.monotonic()-start,2),'seconds','PEAK_RSS_KIB',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,flush=True)
