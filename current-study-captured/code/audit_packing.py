"""Label-free independent verification of fixed prompt membership and numeric budgets."""
from pathlib import Path
import json,hashlib,sys
P=Path(__file__).parent;H=lambda b:hashlib.sha256(b).hexdigest();sys.path.insert(0,'/downloads/gemma-genuine-feasibility/runtime');import litert_lm
engine=litert_lm.Engine(model_path='/downloads/gemma-genuine-feasibility/gemma-4-E2B-it.litertlm',backend=litert_lm.Backend.CPU(thread_count=2),max_num_tokens=1536,cache_dir='/downloads/gemma-genuine-feasibility/cache');nt=lambda s:len(engine.tokenize(s));counts={'tasks':0,'prompts':0,'max_tokens':0}
for f in sorted((P/'private-packs').glob('*.json')):
 pack=json.loads(f.read_text());rankfile=P/'rankings'/f.name;rank=json.loads(rankfile.read_text());prep=json.loads((P/'private-prepared'/f.name).read_text());assert H(rankfile.read_bytes())==pack['ranking_sha256'];assert pack['query_sha256']==prep['query_sha256'];order=rank['ranks']['semantic20'];assert len(order)==len(set(order))==20;assert [s['candidates'][0] for s in pack['verifier_rounds']]==order
 for rotation in range(4):
  arm='T'+str(rotation);rot=order[rotation:]+order[:rotation];assert pack['groups'][arm]==[rot[k::4] for k in range(4)]
  for k,stage in enumerate(pack['first_rounds'][arm]):
   assert stage['candidates']==pack['groups'][arm][k];template=pack['prompt_template'];text=template['prefix']+pack['issue']+template['middle']+'\n'.join(str(i)+'. '+pack['chunks'][s] for i,s in enumerate(stage['candidates'],1))+template['suffix'];assert text==stage['prompt'];assert H(text.encode())==stage['prompt_sha256'];n=nt(text);assert n==stage['prompt_tokens'] and n<=960;counts['prompts']+=1;counts['max_tokens']=max(n,counts['max_tokens'])
 for stage in pack['verifier_rounds']:
  assert 'BUG REPORT (possibly truncated):\n'+pack['issue']+'\nCANDIDATE (source excerpt possibly truncated):\n' in stage['prompt'];assert H(stage['prompt'].encode())==stage['prompt_sha256'];n=nt(stage['prompt']);assert n==stage['prompt_tokens'] and n<=960;counts['prompts']+=1;counts['max_tokens']=max(n,counts['max_tokens']);assert stage['source_token_ceiling']<=640
 assert pack['final_conservative_token_bound']<=960;assert pack['issue_shown_tokens']==nt(pack['issue']);counts['tasks']+=1
counts.update(pass_audit=True,no_gold_access=True,method_unchanged=True);(P/'PACKING-INDEPENDENT-AUDIT.json').write_text(json.dumps(counts,indent=2)+'\n');print(json.dumps(counts))
