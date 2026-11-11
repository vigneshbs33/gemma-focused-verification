from pathlib import Path
import argparse,json,hashlib,sys,resource
P=Path(__file__).parent;M=Path('/downloads/gemma-genuine-feasibility');sys.path.insert(0,str(M/'runtime'));import litert_lm
import method
packing=method.packing;sha=lambda b:hashlib.sha256(b).hexdigest();a=argparse.ArgumentParser();a.add_argument('--assignment',required=True);a.add_argument('--count',type=int,default=1);args=a.parse_args();out=P/'private-packs';out.mkdir(exist_ok=True)
engine=litert_lm.Engine(model_path=str(M/'gemma-4-E2B-it.litertlm'),backend=litert_lm.Backend.CPU(thread_count=2),max_num_tokens=1536,cache_dir=str(M/'cache'));nt=lambda s:len(engine.tokenize(s))
def clip(s,n):
 t=engine.tokenize(s);return s if len(t)<=n else engine.detokenize(t[:n])+' [truncated]'
PREFIX='Choose the ONE candidate most likely to need editing for the bug. Reply only its number 1-5, or 0 if none. Do not explain.\nBUG REPORT (possibly truncated):\n';MID='\nCANDIDATES (source excerpts possibly truncated):\n';SUFFIX='\nAnswer:'
VP='Rate this ONE candidate as a likely edit site for the bug. Reply only 0, 1, 2, or 3. Do not explain.\n0: no plausible edit relevance\n1: related concept, weak evidence this definition needs editing\n2: plausible edit site tied to the described behavior\n3: direct evidence this definition implements the failing behavior and likely needs editing\nBUG REPORT (possibly truncated):\n';VM='\nCANDIDATE (source excerpt possibly truncated):\n'
def assemble(issue,chunks,symbols):return PREFIX+issue+MID+'\n'.join(str(i)+'. '+chunks[s] for i,s in enumerate(symbols,1))+SUFFIX
for f in sorted((P/'rankings').glob('*.json')):
 rank=json.loads(f.read_text());iid=rank['instance_id'];dest=out/f.name
 if rank['assignment']!=args.assignment or dest.exists():continue
 prep=json.loads((P/'private-prepared'/f.name).read_text());q=prep['query'];records=prep['records'];symbols=rank['ranks']['semantic20'];assert len(symbols)==20
 rotated={f'T{r}':symbols[r:]+symbols[:r] for r in range(4)};groups={k:[v[g::4] for g in range(4)] for k,v in rotated.items()};issue_cap=256;source_cap=128
 def chunk(s,cap):
  r=records[s];r['doclines']=set(r['doclines']);lo,hi=packing.window(r,q,12);raw=packing.render_lines(r,lo,hi);excerpt=clip(raw,cap);return f"{s}\nSIGNATURE: {clip(r['header'],24)}\nCODE:\n{excerpt}",{'path':r['path'],'start':r['start'],'end':r['end'],'same_qualified_count':r['same_qualified_count'],'window_lo_index':lo,'window_hi_index':hi,'source_tokens':nt(excerpt),'source_truncated':excerpt!=raw,'excerpt_sha256':sha(excerpt.encode())}
 while True:
  issue=clip(q,issue_cap);pairs={s:chunk(s,source_cap) for s in symbols};chunks={s:v[0] for s,v in pairs.items()};prompts={k:[assemble(issue,chunks,ss) for ss in gs] for k,gs in groups.items()};largest=max(nt(s) for ps in prompts.values() for s in ps);bound=nt(PREFIX+issue+MID+SUFFIX)+sum(sorted((nt('1. '+s) for s in chunks.values()),reverse=True)[:4])+32
  if largest<=960 and bound<=960:break
  source_cap-=8
  if source_cap<16:
   issue_cap-=32;source_cap=128
   if issue_cap<64:raise RuntimeError(('packingfailed',iid))
 verifier=[]
 for s in symbols:
  cap=640
  while True:
   text,details=chunk(s,cap);prompt=VP+issue+VM+text+SUFFIX
   if nt(prompt)<=960:break
   cap-=8
   if cap<16:raise RuntimeError(('verifierpackingfailed',iid,s))
  verifier.append({'candidates':[s],'prompt':prompt,'prompt_sha256':sha(prompt.encode()),'prompt_tokens':nt(prompt),'source_token_ceiling':cap,'source':details,'stage':len(verifier)})
 result={'instance_id':iid,'assignment':args.assignment,'plan_sha256':sha((P/'PLAN.md').read_bytes()),'ranking_sha256':sha(f.read_bytes()),'pack_code_sha256':sha(Path(__file__).read_bytes()),'query_sha256':prep['query_sha256'],'issue':issue,'issue_token_ceiling':issue_cap,'issue_original_tokens':nt(q),'issue_shown_tokens':nt(issue),'source_token_ceiling':source_cap,'chunks':chunks,'candidate_sources':{s:v[1] for s,v in pairs.items()},'groups':groups,'first_rounds':{},'verifier_rounds':verifier,'prompt_template':{'prefix':PREFIX,'middle':MID,'suffix':SUFFIX},'final_conservative_token_bound':bound}
 for arm,gs in groups.items():result['first_rounds'][arm]=[{'candidates':ss,'prompt':prompt,'prompt_sha256':sha(prompt.encode()),'prompt_tokens':nt(prompt),'stage':i} for i,(ss,prompt) in enumerate(zip(gs,prompts[arm]))]
 dest.write_text(json.dumps(result,indent=2)+'\n');print('PACKED',iid,'sourcecap',source_cap,'controlmax',largest,'verifiermax',max(x['prompt_tokens'] for x in verifier),'rss',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,flush=True);args.count-=1
 if args.count<=0:break
