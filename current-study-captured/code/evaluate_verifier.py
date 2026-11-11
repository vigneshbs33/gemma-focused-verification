"""Frozen evaluation of focused verifier. Run only after all evaluation outputs freeze."""
from pathlib import Path
import json,hashlib,random,statistics,datetime,sqlite3
P=Path(__file__).parent;H=lambda f:hashlib.sha256(f.read_bytes()).hexdigest();ARMS=['T5','T20','V20','Dense1']
def paired(rows,a,b,metric='correct'):
 d=[r['arms'][a][metric]-r['arms'][b][metric] for r in rows];n=len(d);rng=random.Random(42);bs=sorted(sum(rng.choices(d,k=n))/n for _ in range(10000));repos=sorted({r['repo'] for r in rows});by={repo:[r['arms'][a][metric]-r['arms'][b][metric] for r in rows if r['repo']==repo] for repo in repos};rng=random.Random(43);cs=[]
 for _ in range(10000):
  vals=[v for repo in rng.choices(repos,k=len(repos)) for v in by[repo]];cs.append(sum(vals)/len(vals))
 cs.sort();return {'delta':sum(d)/n,'wins':d.count(1),'losses':d.count(-1),'ties':d.count(0),'task_ci95':[bs[250],bs[9750]],'repository_cluster_ci95':[cs[250],cs[9750]],'n_clusters':len(repos),'denominator':n}
def main():
 freeze=json.loads((P/'EVALUATION-OUTPUT-FREEZE.json').read_text());inp=json.loads((P/'EVALUATION-FREEZE.json').read_text());assert len(freeze['receipt_hashes'])==60
 for n,h in freeze['output_hashes'].items():assert H(P/'outputs'/n)==h
 for n,h in freeze['receipt_hashes'].items():assert H(P/'task-receipts'/n)==h
 rows=[]
 for n in sorted(freeze['receipt_hashes']):
  rec=json.loads((P/'task-receipts'/n).read_text());iid=rec['instance_id'];gold=json.loads((P/'gold-bindings'/(iid+'.json')).read_text());rank=json.loads((P/'rankings'/(iid+'.json')).read_text());prep=json.loads((P/'private-prepared'/(iid+'.json')).read_text());assert H(P/'rankings'/(iid+'.json'))==inp['ranking_hashes'][iid+'.json'];g=set(gold['gold']);fg=set(gold['function_gold']);gm=set(gold['coarse_modules']);item={'instance_id':iid,'repo':gold['repo'],'has_gold':bool(g),'has_function_gold':bool(fg),'ambiguous':bool(gold['ambiguous_symbols']),'unresolved_hunks':gold['coverage'].get('unresolved_hunks',0),'arms':{},'shortlist_has_gold':int(bool(set(rank['ranks']['semantic20'])&g)),'pool_has_gold':int(bool(set(rank['pools']['semantic'])&g))}
  for arm in ARMS:
   if arm=='Dense1':selected=rank['dense_orders']['semantic'][0];stages=[]
   elif arm=='V20':selected=rec['arms'][arm]['selected'];stages=rec['arms'][arm]['scores']
   else:
    selected=rec['arms'][arm]['selected'];stages=[]
    for control in (['T0'] if arm=='T5' else ['T0','T1','T2','T3']):
     a=rec['arms'][control];stages+=a['stages']+([a['final']] if a.get('final') else [])
   outputs=[json.loads((P/'outputs'/(s['call_id']+'.json')).read_text()) for s in stages if s.get('call_id')];statuses=[json.loads((P/'logs'/('call-'+s['call_id']+'-status.json')).read_text()) for s in stages if s.get('call_id')]
   item['arms'][arm]={'selected':selected,'correct':int(selected in g),'function_only_correct':int(selected in fg),'coarse_module_correct':int(bool(selected) and prep['records'][selected]['path'][:-3].replace('/','.').removesuffix('.__init__') in gm),'calls':len(outputs),'invalid_calls':sum(not s.get('valid',True) for s in stages),'final_abstention':selected is None,'prompt_tokens':sum(o['prompt_tokens'] for o in outputs),'generation_seconds':sum(o['elapsed_seconds'] for o in outputs),'process_seconds':sum(s['elapsed_seconds'] for s in statuses),'max_rss_kib':max([o['peak_rss_kib'] for o in outputs]+[s['peak_rss_kib'] for s in statuses]+[0]),'returned_text_characters':sum(len(o['response']) for o in outputs)}
  rows.append(item)
 def summary(rs):
  return {'n':len(rs),'has_gold':sum(r['has_gold'] for r in rs),'has_function_gold':sum(r['has_function_gold'] for r in rs),'ambiguous_tasks':sum(r['ambiguous'] for r in rs),'unresolved_hunks':sum(r['unresolved_hunks'] for r in rs),'correct':{a:sum(r['arms'][a]['correct'] for r in rs) for a in ARMS},'function_only_correct':{a:sum(r['arms'][a]['function_only_correct'] for r in rs) for a in ARMS},'coarse_module_correct':{a:sum(r['arms'][a]['coarse_module_correct'] for r in rs) for a in ARMS},'shortlist_has_gold':sum(r['shortlist_has_gold'] for r in rs),'pool_has_gold':sum(r['pool_has_gold'] for r in rs),'resources':{a:{k:sum(r['arms'][a][k] for r in rs) for k in ['calls','prompt_tokens','generation_seconds','process_seconds','invalid_calls','final_abstention','returned_text_characters']}|{'max_rss_kib':max([r['arms'][a]['max_rss_kib'] for r in rs]+[0])} for a in ARMS}}
 pairs=[('V20','T20'),('V20','T5'),('T20','T5'),('V20','Dense1')]
 with sqlite3.connect(P/'private-embedding-cache.sqlite') as db:embedding=db.execute('select count(*),sum(tokens),sum(seconds) from vectors').fetchone()
 result={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'study':'focused_candidate_verification','output_freeze_sha256':H(P/'EVALUATION-OUTPUT-FREEZE.json'),'binder_sha256':H(P/'gold_bind.py'),'evaluation':summary(rows),'paired':{a+'-minus-'+b:paired(rows,a,b) for a,b in pairs},'function_only_primary':paired(rows,'V20','T20','function_only_correct'),'unambiguous_sensitivity':summary([r for r in rows if not r['ambiguous']]),'per_repository':{repo:summary([r for r in rows if r['repo']==repo]) for repo in sorted({r['repo'] for r in rows})},'embedding_physical_cache_including19344_seed':{'vectors':embedding[0],'tokens':embedding[1],'generation_seconds':embedding[2]},'resource_note':'T5 reuses T20 rotation0; do not sum their cost. Equal maximal20calls does not mean equal tokens/compute. Returned text characters are not tokenizer counts.','per_task':rows}
 (P/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['evaluation','paired','function_only_primary']},indent=2))
if __name__=='__main__':main()
