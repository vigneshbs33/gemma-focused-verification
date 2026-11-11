from pathlib import Path
import json,hashlib,collections,re,datetime
import pyarrow.parquet as pq
P=Path(__file__).parent;sha=lambda b:hashlib.sha256(b).hexdigest();cols=['instance_id','repo','base_commit','problem_statement']
rows=pq.read_table(P/'full-test-private.parquet',columns=cols).to_pylist();prior=[]
for f in ['/downloads/external-cohort-research/lite-test.parquet','/downloads/external-cohort-research/lite-dev.parquet','/downloads/gemma-context-next-20261110/full-dev-private.parquet']:prior+=pq.read_table(f,columns=cols).to_pylist()
ids={r['instance_id'] for r in prior};bases={(r['repo'],r['base_commit']) for r in prior};queries={r['problem_statement'] for r in prior};tokens=lambda q:set(re.findall('[a-z0-9]+',q.lower()));qt=[tokens(q) for q in queries]
def near(q,x):
 if min(len(q),len(x))/max(1,max(len(q),len(x)))<.8:return False
 intersection=len(q&x);return intersection/max(1,len(q)+len(x)-intersection)>=.8
allowed=[];excluded=[]
for r in rows:
 why=None;q=tokens(r['problem_statement'])
 if r['repo']=='psf/requests':why='conservative_entire_requests_original129_overlap'
 elif r['instance_id'] in ids:why='prior_public_task'
 elif (r['repo'],r['base_commit']) in bases:why='prior_public_base'
 elif r['problem_statement'] in queries:why='prior_public_exactquery'
 elif any(near(q,x) for x in qt):why='prior_public_nearquery'
 if why:excluded.append({'instance_id':r['instance_id'],'reason':why})
 else:allowed.append(r)
accepted=[];seen_bases=set();accepted_queries=[]
for r in sorted(allowed,key=lambda r:sha(('stronger-v1:'+r['instance_id']).encode())):
 q=tokens(r['problem_statement']);base=(r['repo'],r['base_commit']);why=None
 if base in seen_bases:why='within_pool_base_duplicate'
 elif any(near(q,x) for x in accepted_queries):why='within_pool_nearquery'
 if why:excluded.append({'instance_id':r['instance_id'],'reason':why});continue
 accepted.append(r);accepted_queries.append(q);seen_bases.add(base)
by=collections.defaultdict(list)
for r in accepted:by[r['repo']].append(r)
chosen=[]
while len(chosen)<72:
 any_added=False
 for repo in sorted(by):
  if by[repo] and len(chosen)<72:chosen.append(by[repo].pop(0));any_added=True
 if not any_added:break
assert len(chosen)==72
bychosen=collections.defaultdict(list)
for r in chosen:bychosen[r['repo']].append(r)
for repo in bychosen:bychosen[repo].sort(key=lambda r:sha(('stronger-dev-v1:'+r['instance_id']).encode()))
dev=set()
while len(dev)<12:
 for repo in sorted(bychosen):
  if bychosen[repo] and len(dev)<12:dev.add(bychosen[repo].pop(0)['instance_id'])
selected=[{k:r[k] for k in ['instance_id','repo','base_commit']}|{'query_sha256':sha(r['problem_statement'].encode()),'assignment':'development' if r['instance_id'] in dev else 'evaluation'} for r in chosen]
assert collections.Counter(t['assignment'] for t in selected)=={'development':12,'evaluation':60}
out={'created_utc':'2026-11-10T07:14:26.574870+00:00','plan_sha256':sha((P/'PLAN.md').read_bytes()),'dataset_sha256':sha((P/'full-test-private.parquet').read_bytes()),'n_full_test':len(rows),'prior_public_rows':len(prior),'prior_includes':'Lite323 plus entirefull-dev225(including72/68cohorts)','original129_scope':'Retained ORIGINAL-OVERLAP.json says Requests onlysharedrepo; entireRequests excluded; original129crossrepoquery/nearqueryNOTRECHECKED; withdrawnrawcardsnotaccessed','original_overlap_report_sha256':sha(Path('/downloads/scaled-lite300-20261109/ORIGINAL-OVERLAP.json').read_bytes()),'excluded':excluded,'exclusion_counts':dict(collections.Counter(t['reason'] for t in excluded)),'eligible_unique_snapshots':len(accepted),'eligible_repo':dict(collections.Counter(r['repo'] for r in accepted)),'selected':selected,'selected_repo':dict(collections.Counter(r['repo'] for r in chosen)),'counts':dict(collections.Counter(t['assignment'] for t in selected)),'repo_disjoint':False,'no_gold_or_outcome_selection':True}
(P/'COHORT-QUALIFICATION.json').write_text(json.dumps(out,indent=2)+'\n')
(P/'inference-only.jsonl').write_text(''.join(json.dumps({k:r[k] for k in ['instance_id','repo','base_commit','problem_statement']}|{'hints_text':''})+'\n' for r in chosen))
print(json.dumps({k:v for k,v in out.items() if k not in ['selected','excluded']},indent=2))
