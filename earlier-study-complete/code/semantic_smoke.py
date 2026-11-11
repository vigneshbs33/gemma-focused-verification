from pathlib import Path
import os,sys,json,time,resource,importlib.util,hashlib
P=Path(__file__).parent;sys.path.insert(0,str(P/'runtime'))
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import torch
from transformers import AutoTokenizer
torch.set_num_threads(2);torch.set_num_interop_threads(1)
M=P/'coderank-model'
spec=importlib.util.spec_from_file_location('coderank_pinned',M/'__init__.py',submodule_search_locations=[str(M)]);pkg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pkg;spec.loader.exec_module(pkg)
from coderank_pinned.configuration_hf_nomic_bert import NomicBertConfig
from coderank_pinned.modeling_hf_nomic_bert import NomicBertModel
from safetensors.torch import load_file
start=time.monotonic();conf=NomicBertConfig.from_json_file(str(M/'config.json'));conf.use_flash_attn=False;conf.fused_bias_fc=False;conf.fused_dropout_add_ln=False;conf.use_cache=False
model=NomicBertModel(conf,add_pooling_layer=False);state=load_file(str(M/'model.safetensors'));load=model.load_state_dict(state,strict=True);del state;model.eval()
tokenizer=AutoTokenizer.from_pretrained(str(M),local_files_only=True)
print('LOADED',str(load),resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,flush=True)
texts=['Represent this query for searching relevant code: Fix target function with empty values','def target(values):\n    return sum(values) / len(values)','def unrelated(path):\n    return open(path).read()']
with torch.inference_mode():
 x=tokenizer(texts,padding=True,truncation=True,max_length=512,return_tensors='pt');v=torch.nn.functional.normalize(model(**x).last_hidden_state[:,0],p=2,dim=1)
 v2=torch.nn.functional.normalize(model(**x).last_hidden_state[:,0],p=2,dim=1)
 assert torch.equal(v,v2);assert torch.isfinite(v).all();assert (v.norm(dim=1)-1).abs().max()<1e-5
 times={}
 for length in [128,256,512]:
  synthetic=['def calculate(value):\n    result = value + 1\n    return result\n'*(length//8)]*4
  x=tokenizer(synthetic,padding=True,truncation=True,max_length=length,return_tensors='pt');s=time.monotonic()
  for i in range(4):
   z=model(**{k:a[i:i+1] for k,a in x.items()}).last_hidden_state[:,0]
   assert torch.isfinite(z).all()
  times[length]={'four_documents_seconds':time.monotonic()-s,'tokens':x['input_ids'].shape[1]}
result={'status':'passed','strict_weight_keys':str(load),'query_prefix':'Represent this query for searching relevant code: ','pooling':'normalized raw CLS','device':'cpu','threads':torch.get_num_threads(),'torch':torch.__version__,'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'synthetic_document_timings':times,'no_accuracy_evaluation':True}
(P/'SEMANTIC-RESOURCE-SMOKE.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
