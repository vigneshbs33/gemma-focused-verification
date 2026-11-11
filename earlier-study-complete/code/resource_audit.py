from pathlib import Path
import json,sqlite3,collections,sys,hashlib
import numpy as np
P=Path(__file__).parent;db=sqlite3.connect(P/'private-embedding-cache.sqlite');cache={r[0]:(np.frombuffer(r[1],dtype='<f4'),r[2],r[3]) for r in db.execute('select key,vector,tokens,seconds from vectors')};db.close();logical=collections.defaultdict(lambda:collections.Counter());rescue=[]
for f in sorted((P/'rankings').glob('*.json')):
 r=json.loads(f.read_text())
 if r['assignment']!='evaluation':continue
 m=json.loads((P/'private-semantic'/f.name).read_text());prep=json.loads((P/'private-prepared'/f.name).read_text());q=cache[m['query_key']][0];score={s:float(np.dot(q,cache[k][0])) for s,k in m['candidate_keys'].items()};assert score==r['dense_scores']
 for arm in ['semantic','structural']:
  pool=r['pools'][arm];dense=sorted(pool,key=lambda s:(-score[s],s));assert dense==r['dense_orders'][arm];lex=[s for s in prep['proposal']['lexical']['C2F'] if s in set(pool)];orders=[lex,dense]
  if arm=='structural':orders.append([s for s in r['graph']['ranking'] if s in set(pool)])
  fused=collections.defaultdict(float)
  for order in orders:
   for i,s in enumerate(order):fused[s]+=1/(60+i+1)
  ranking=sorted(fused,key=lambda s:(-fused[s],s))[:20];name='B_semantic_tournament' if arm=='semantic' else 'C_structural_tournament';assert ranking==r['ranks'][name]
  keys=[m['query_key']]+[m['candidate_keys'][s] for s in pool];logical[arm]['documents_including_queries']+=len(keys);logical[arm]['token_sum']+=sum(cache[k][1] for k in keys);logical[arm]['cached_single_vector_generation_seconds_sum']+=sum(cache[k][2] for k in keys)
 rescue.append(len(set(r['pools']['structural'])-set(r['pools']['semantic'])))
sys.path.insert(0,'/downloads/gemma-genuine-feasibility/runtime');import litert_lm
engine=litert_lm.Engine(model_path='/downloads/gemma-genuine-feasibility/gemma-4-E2B-it.litertlm',backend=litert_lm.Backend.CPU(thread_count=2),max_num_tokens=1536,cache_dir='/downloads/gemma-genuine-feasibility/cache');output_tokens=collections.Counter()
for f in (P/'outputs').glob('evaluation-*.json'):
 r=json.loads(f.read_text());output_tokens[r['method']]+=len(engine.tokenize(r['response']))
statuses=[json.loads(f.read_text()) for f in (P/'logs').glob('call-evaluation-*-status.json')];embed=[json.loads(f.read_text()) for f in (P/'logs').glob('embed-*-status.json')];result={'independent_dense_scores_and_rrf_rankings_all60':'pass','physical_cache_all72':{'vectors':len(cache),'tokens':sum(v[1] for v in cache.values()),'generation_seconds':sum(v[2] for v in cache.values())},'logical_evaluation_pools':{k:dict(v) for k,v in logical.items()},'logical_cost_note':'Logical per-arm sums count every query/candidate, including reused cached vectors. Cached single-vector generation times are descriptive, not independent end-to-end arm timing. Physical cache totals cover all72 tasks and both pools. Startup/tokenization/AST acquisition are additional. No full-repository dense index was built.','structural_candidates_outside_semantic320':{'total':sum(rescue),'tasks_with_any':sum(x>0 for x in rescue),'max':max(rescue)},'evaluation_output_text_tokens_by_gemma_tokenizer':dict(output_tokens),'evaluation_governor_process_seconds_sum':sum(r['elapsed_seconds'] for r in statuses),'max_governor_rss_kib':max(r['peak_rss_kib'] for r in statuses),'evaluation_failed_calls':sum(r['returncode']!=0 or bool(r['stop_reason']) for r in statuses),'resource_limits':{'cpu_threads':2,'max_prompt_tokens':960,'context_tokens':1536,'max_generated_tokens':12,'rss_kib':1536000,'process_seconds':90},'output_token_note':'Token counts re-tokenize returned text and omit hidden runtime control tokens; generated-token cap was12.'};(P/'RESOURCE-AUDIT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
