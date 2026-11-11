from pathlib import Path
import sys,json,time,resource,hashlib
P=Path(__file__).parent;M=Path('/downloads/gemma-genuine-feasibility');sys.path.insert(0,str(M/'runtime'));import litert_lm
start=time.monotonic();engine=litert_lm.Engine(model_path=str(M/'gemma-4-E2B-it.litertlm'),backend=litert_lm.Backend.CPU(thread_count=2),max_num_tokens=1536,cache_dir=str(M/'cache'))
text='Choose the function that adds one. Reply only 1 or 2.\n1. def add_one(x):\n    return x + 1\n2. def read_file(path):\n    return open(path).read()\n'
padding='\n# unrelated context: value = calculate(123)'
while len(engine.tokenize(text+padding))<=950:text+=padding
text+='\nAnswer:';nt=len(engine.tokenize(text));assert 900<=nt<=960
c=engine.create_conversation(thinking_config=litert_lm.ThinkingConfig(enable_thinking=False,thinking_token_budget=0),sampler_config=litert_lm.SamplerConfig(top_k=1,top_p=1.0,temperature=0.0,seed=42),max_output_tokens=12);r=c.send_message(text)
out={'gate':'replacement synthetic Gemma smoke, not benchmark accuracy','prompt_tokens':nt,'response':str(r),'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'model_sha256':'181938105e0eefd105961417e8da75903eacda102c4fce9ce90f50b97139a63c','runtime_wheel_sha256':'93db43085401b208815a636150ae87576bb7e82adbada9f083ec16114dff8898','gold_analysis':False};(P/'GEMMA-REPLACEMENT-SMOKE.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
