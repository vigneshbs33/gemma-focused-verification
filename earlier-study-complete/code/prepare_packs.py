"""Freeze issue/source chunks and first rounds. Final prompt is a deterministic subset."""
from pathlib import Path
import argparse,json,hashlib,sys,time,resource
P=Path(__file__).parent;M=Path('/downloads/gemma-genuine-feasibility');sys.path.insert(0,str(M/'runtime'));import litert_lm
import method
from method import packing
sha=lambda b:hashlib.sha256(b).hexdigest();a=argparse.ArgumentParser();a.add_argument('--assignment',required=True);a.add_argument('--count',type=int,default=1);args=a.parse_args();out=P/'private-packs';out.mkdir(exist_ok=True)
engine=litert_lm.Engine(model_path=str(M/'gemma-4-E2B-it.litertlm'),backend=litert_lm.Backend.CPU(thread_count=2),max_num_tokens=1536,cache_dir=str(M/'cache'))
nt=lambda s:len(engine.tokenize(s))
def clip(s,n):
 tok=engine.tokenize(s)
 return s if len(tok)<=n else engine.detokenize(tok[:n])+' [truncated]'
PREFIX='Choose the ONE candidate most likely to need editing for the bug. Reply only its number 1-5, or 0 if none. Do not explain.\nBUG REPORT (possibly truncated):\n'
MID='\nCANDIDATES (source excerpts possibly truncated):\n';SUFFIX='\nAnswer:'
def assemble(issue,chunks,symbols):return PREFIX+issue+MID+'\n'.join(str(i)+'. '+chunks[s] for i,s in enumerate(symbols,1))+SUFFIX
done=0
for f in sorted((P/'rankings').glob('*.json')):
 rank=json.loads(f.read_text());iid=rank['instance_id'];dest=out/(iid+'.json')
 if rank['assignment']!=args.assignment or dest.exists():continue
 prep=json.loads((P/'private-prepared'/(iid+'.json')).read_text());q=prep['query'];records=prep['records'];ranks=rank['ranks'];groups={arm:[symbols[g::4] for g in range(4)] for arm,symbols in ranks.items() if arm!='D_fielded_single'};groups['D_fielded_single']=[ranks['D_fielded_single']];wanted=set(sum(ranks.values(),[]));issue_cap=256;source_cap=128
 while True:
  issue=clip(q,issue_cap);chunks={};details={}
  for s in sorted(wanted):
   r=records[s];r['doclines']=set(r['doclines']);lo,hi=packing.window(r,q,12);raw=packing.render_lines(r,lo,hi);excerpt=clip(raw,source_cap)
   chunks[s]=f"{s}\nSIGNATURE: {clip(r['header'],24)}\nCODE:\n{excerpt}"
   details[s]={'path':r['path'],'start':r['start'],'end':r['end'],'same_qualified_count':r['same_qualified_count'],'window_lo_index':lo,'window_hi_index':hi,'source_tokens':nt(excerpt),'source_truncated':excerpt!=raw,'excerpt_sha256':sha(excerpt.encode()),'complete_source_lines_shown':[r['start']+j for j,line in enumerate(r['lines']) if f"{r['start']+j}: {line}" in excerpt.splitlines()]}
  prompts={arm:[assemble(issue,chunks,syms) for syms in gs] for arm,gs in groups.items()};largest=max(nt(s) for ps in prompts.values() for s in ps)
  # Conservative final-round cap: any four winners, with32-token boundary margin.
  final_bound=nt(PREFIX+issue+MID+SUFFIX)+sum(sorted((nt('1. '+s) for s in chunks.values()),reverse=True)[:4])+32
  if largest<=960 and final_bound<=960:break
  source_cap-=8
  if source_cap<16:
   issue_cap-=32
   if issue_cap<64:raise RuntimeError(('cannot_pack',iid,largest,final_bound))
   source_cap=128
 result={'instance_id':iid,'assignment':args.assignment,'plan_sha256':sha((P/'PLAN.md').read_bytes()),'ranking_sha256':sha(f.read_bytes()),'pack_code_sha256':sha(Path(__file__).read_bytes()),'query_sha256':prep['query_sha256'],'issue':issue,'issue_token_ceiling':issue_cap,'issue_original_tokens':nt(q),'issue_shown_tokens':nt(issue),'source_token_ceiling':source_cap,'chunks':chunks,'candidate_sources':details,'groups':groups,'first_rounds':{},'prompt_template':{'prefix':PREFIX,'middle':MID,'suffix':SUFFIX},'final_conservative_token_bound':final_bound}
 for arm,gs in groups.items():
  result['first_rounds'][arm]=[{'candidates':symbols,'prompt':prompt,'prompt_sha256':sha(prompt.encode()),'prompt_tokens':nt(prompt),'stage':i} for i,(symbols,prompt) in enumerate(zip(gs,prompts[arm]))]
 dest.write_text(json.dumps(result,indent=2)+'\n');print('PACKED',iid,'first_max',largest,'final_bound',final_bound,'source_cap',source_cap,'rss',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,flush=True);done+=1
 if done>=args.count:break
