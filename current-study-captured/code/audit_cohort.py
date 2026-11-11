"""Read-only label-free overlap audit using independent pairwise checks."""
from pathlib import Path
import hashlib,json,re,collections,itertools
import pyarrow.parquet as pq
P=Path(__file__).parent;H=lambda b:hashlib.sha256(b).hexdigest();cols=['instance_id','repo','base_commit','problem_statement'];full=pq.read_table(P/'full-test-private.parquet',columns=cols).to_pylist();byid={r['instance_id']:r for r in full};cohort=json.loads((P/'COHORT-QUALIFICATION.json').read_text());chosen=[byid[t['instance_id']] for t in cohort['selected']];oldids={r['instance_id'] for r in json.loads(Path('/downloads/gemma-stronger-recovered-20261110/COHORT-QUALIFICATION.json').read_text())['selected']};prior=[]
for n in ['lite-test.parquet','lite-dev.parquet','full-dev-private.parquet']:prior+=pq.read_table(P/'recovered-inputs'/n,columns=cols).to_pylist()
prior += [byid[i] for i in oldids]
words=lambda q:set(re.findall(r'[a-z0-9]+',q.lower()))
def close(a,b):return len(a&b)/max(1,len(a|b))>=.8
pp=[words(r['problem_statement']) for r in prior];pairs=0
for r,t in zip(chosen,cohort['selected']):
 assert r['repo']!='psf/requests';assert t['query_sha256']==H(r['problem_statement'].encode());q=words(r['problem_statement'])
 for prev,qt in zip(prior,pp):
  assert r['instance_id']!=prev['instance_id'];assert (r['repo'],r['base_commit'])!=(prev['repo'],prev['base_commit']);assert r['problem_statement']!=prev['problem_statement'];assert not close(q,qt),(r['instance_id'],prev['instance_id']);pairs+=1
for a,b in itertools.combinations(chosen,2):assert (a['repo'],a['base_commit'])!=(b['repo'],b['base_commit']) and not close(words(a['problem_statement']),words(b['problem_statement']))
assert collections.Counter(t['assignment'] for t in cohort['selected'])=={'development':12,'evaluation':60}
r={'pass':True,'selected_tasks':72,'prior_rows':len(prior),'prior_pairs_checked':pairs,'within_selected_pairs_checked':2556,'excluded_entire_requests':True,'no_source_availability_or_gold_consulted':True,'qualification_code_sha256':H((P/'qualify_new.py').read_bytes()),'cohort_sha256':H((P/'COHORT-QUALIFICATION.json').read_bytes()),'limitations':'Original withdrawn129 cross-repository exact/near queries not rechecked; no globally unseen or repository-disjoint claim.'};(P/'COHORT-INDEPENDENT-AUDIT.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
