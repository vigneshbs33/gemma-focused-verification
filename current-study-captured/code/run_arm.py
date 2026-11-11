#!/usr/bin/env python3
import sys,pathlib,json,time,resource,hashlib
P=pathlib.Path(__file__).parent;M=pathlib.Path('/downloads/gemma-genuine-feasibility');sys.path.insert(0,str(M/'runtime'));import litert_lm
armid=sys.argv[1];q=json.loads((P/'private-calls'/(armid+'.json')).read_text());protocol=json.loads((P/'MODEL-PROTOCOL.json').read_text());start=time.monotonic()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(q['prompt'].encode())==q['prompt_sha256']
engine=litert_lm.Engine(model_path=str(M/'gemma-4-E2B-it.litertlm'),backend=litert_lm.Backend.CPU(thread_count=2),max_num_tokens=1536,cache_dir=str(M/'cache'))
tokens=len(engine.tokenize(q['prompt']));assert tokens==q['prompt_tokens'] and tokens<=960
c=engine.create_conversation(thinking_config=litert_lm.ThinkingConfig(enable_thinking=False,thinking_token_budget=0),sampler_config=litert_lm.SamplerConfig(top_k=1,top_p=1.0,temperature=0.0,seed=42),max_output_tokens=12)
r=c.send_message(q['prompt']);out={k:v for k,v in q.items() if k!='prompt'};out.update(response=str(r),raw_response=dict(r),channels=r.channels,elapsed_seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,protocol_sha256=sha((P/'MODEL-PROTOCOL.json').read_bytes()));dest=P/'outputs'/(armid+'.json');dest.parent.mkdir(exist_ok=True);tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(out,indent=2)+'\n');tmp.replace(dest);print('ARM_DONE',armid,str(r),flush=True)
