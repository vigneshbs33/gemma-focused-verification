"""Independent read-only source, label, tournament and metric audit.
Does not import binder/evaluator or rerun inference.
"""
from pathlib import Path
import ast,collections,json,re,hashlib,tarfile,random,sqlite3
import pyarrow.parquet as pq
P=Path(__file__).parent;H=lambda b:hashlib.sha256(b).hexdigest();arms=['A_plain_tournament','B_semantic_tournament','C_structural_tournament','D_fielded_single']
def module(path):return path[:-3].replace('/','.').removesuffix('.__init__')
def ast_nodes(text):
 class Visitor(ast.NodeVisitor):
  def __init__(self):self.stack=[];self.nodes=[]
  def visit_def(self,node):
   self.stack.append(node.name);self.nodes.append((node.lineno,node.end_lineno,'.'.join(self.stack),'class' if isinstance(node,ast.ClassDef) else 'function'));self.generic_visit(node);self.stack.pop()
  visit_ClassDef=visit_def;visit_FunctionDef=visit_def;visit_AsyncFunctionDef=visit_def
 v=Visitor();v.visit(ast.parse(text));return v.nodes

def independent_gold(patch,archive):
 gold=set();func=set();mods=set();amb=set();unresolved=0
 with tarfile.open(archive) as tf:
  data={m.name:tf.extractfile(m).read() for m in tf if m.isfile()}
  for section in re.split(r'(?m)^diff --git ',patch)[1:]:
   pm=re.search(r'(?m)^--- (.+)$',section)
   if not pm or not pm[1].startswith('a/'):continue
   path=pm[1][2:]
   if not path.endswith('.py') or path not in data:continue
   mods.add(module(path));text=data[path].decode(errors='replace');source=text.splitlines()
   try:nodes=ast_nodes(text)
   except SyntaxError:continue
   count=collections.Counter(n[2] for n in nodes)
   def at(line):
    options=sorted([n for n in nodes if n[0]<=line<=n[1]],key=lambda n:(n[1]-n[0],-n[0]))
    return options[0] if options else None
   def record(node):
    if not node:return
    symbol=module(path)+'.'+node[2]
    if count[node[2]]>1:amb.add(symbol);return
    gold.add(symbol)
    if node[3]=='function':func.add(symbol)
   for hunk in re.split(r'(?m)^@@ ',section)[1:]:
    header,_,body=hunk.partition('\n');items=[s for s in body.splitlines() if s[:1] in [' ','+','-']];old=[s[1:] for s in items if s[0]!='+'];places=[]
    if old:
     for k in range(len(source)-len(old)+1):
      if source[k:k+len(old)]==old:places.append(k)
    if len(places)!=1:unresolved+=1;continue
    cursor=places[0]+1;block=[]
    def handle(block,cursor):
     removed=sum(s[0]=='-' for s in block)
     if removed:
      for ln in range(cursor,cursor+removed):record(at(ln))
     elif block and at(cursor-1) and at(cursor-1)==at(cursor):record(at(cursor))
     return cursor+removed
    for s in items+[' ']:
     if s[0]==' ':cursor=handle(block,cursor);block=[];cursor+=1
     else:block.append(s)
 return gold,func,mods,amb,unresolved

def decision(text,cands):
 stripped=text.strip()
 if len(stripped)!=1 or stripped not in '012345':return None,False,stripped=='0'
 n=int(stripped)
 return (cands[n-1] if 1<=n<=len(cands) else None),n<=len(cands),n==0

def main():
 frozen=json.loads((P/'EVALUATION-FREEZE.json').read_text());outfreeze=json.loads((P/'EVALUATION-OUTPUT-FREEZE.json').read_text());results=json.loads((P/'RESULTS.json').read_text());rows={r['instance_id']:r for r in pq.read_table(P/'recovered-inputs/full-test-private.parquet',columns=['instance_id','patch']).to_pylist()};scores=[];checked=0;source_files=0;max_tokens=0
 for n,h in frozen['code_hashes'].items():assert H((P/n).read_bytes())==h
 for n,h in outfreeze['output_hashes'].items():assert H((P/'outputs'/n).read_bytes())==h
 for expected in results['per_task']:
  iid=expected['instance_id'];qa=json.loads((P/'qa'/(iid+'.json')).read_text());arc=P/'source-archives'/(iid+'.tar.gz')
  with tarfile.open(arc) as tf:
   pins={m.name:H(tf.extractfile(m).read()) for m in tf if m.isfile() and m.name.endswith('.py')};assert pins==qa['source_file_pins'];source_files+=len(pins)
  gold,func,mods,amb,unresolved=independent_gold(rows[iid]['patch'],arc);bound=json.loads((P/'gold-bindings'/(iid+'.json')).read_text());assert gold==set(bound['gold']),(iid,'gold disagreement');assert func==set(bound['function_gold']);assert mods==set(bound['coarse_modules']);assert amb==set(bound['ambiguous_symbols']);assert unresolved==bound['coverage'].get('unresolved_hunks',0)
  pack=json.loads((P/'private-packs'/(iid+'.json')).read_text());rank=json.loads((P/'rankings'/(iid+'.json')).read_text());assert H((P/'private-packs'/(iid+'.json')).read_bytes())==frozen['pack_hashes'][iid+'.json'];receipt=json.loads((P/'task-receipts'/('evaluation-'+iid+'.json')).read_text());score={'repo':expected['repo'],'arms':{}}
  for arm in arms:
   order=rank['ranks'][arm];groups=[order] if arm==arms[-1] else [order[k::4] for k in range(4)];assert groups==pack['groups'][arm];winners=[];callids=[]
   for k,cands in enumerate(groups):
    if not cands:continue
    cid=f'evaluation-{iid}-{arm}-s{k}';callids.append(cid);call=json.loads((P/'private-calls'/(cid+'.json')).read_text());out=json.loads((P/'outputs'/(cid+'.json')).read_text());assert call['candidates']==cands==out['candidates'];assert H(call['prompt'].encode())==out['prompt_sha256'];chosen,valid,zero=decision(out['response'],cands);saved=receipt['arms'][arm]['stages'][k];assert chosen==saved['selected'] and valid==saved['valid'];checked+=1;max_tokens=max(max_tokens,out['prompt_tokens']);assert out['prompt_tokens']<=960
    if chosen:winners.append(chosen)
   if arm!=arms[-1] and winners:
    cid=f'evaluation-{iid}-{arm}-final';callids.append(cid);call=json.loads((P/'private-calls'/(cid+'.json')).read_text());out=json.loads((P/'outputs'/(cid+'.json')).read_text());assert call['candidates']==winners==out['candidates'];chosen,valid,zero=decision(out['response'],winners);assert chosen==receipt['arms'][arm]['final']['selected'];checked+=1;max_tokens=max(max_tokens,out['prompt_tokens']);assert out['prompt_tokens']<=960
   elif arm!=arms[-1]:chosen=None
   assert chosen==receipt['arms'][arm]['selected'];assert int(chosen in gold)==expected['arms'][arm]['correct'];assert int(chosen in func)==expected['arms'][arm]['function_only_correct'];score['arms'][arm]=int(chosen in gold)
   for cid in callids:
    st=json.loads((P/'logs'/('call-'+cid+'-status.json')).read_text());assert st['returncode']==0 and not st['stop_reason'] and st['peak_rss_kib']<=1536000
  scores.append(score)
 assert checked==960
 for a,b in [(arms[2],arms[1]),(arms[2],arms[0]),(arms[2],arms[3]),(arms[1],arms[0])]:
  ds=[r['arms'][a]-r['arms'][b] for r in scores];rng=random.Random(42);boot=sorted(sum(ds[i] for i in rng.choices(range(60),k=60))/60 for _ in range(10000));repos=sorted({r['repo'] for r in scores});rng=random.Random(43);cluster=[]
  for _ in range(10000):
   sample=[r['arms'][a]-r['arms'][b] for repo in rng.choices(repos,k=len(repos)) for r in scores if r['repo']==repo];cluster.append(sum(sample)/len(sample))
  cluster.sort();e=results['paired'][a+'-minus-'+b];assert e['task_ci95']==[boot[250],boot[9750]] and e['repository_cluster_ci95']==[cluster[250],cluster[9750]];assert e['wins']==ds.count(1) and e['losses']==ds.count(-1)
 audit={'pass':True,'tasks':len(scores),'independently_parsed_calls':checked,'source_file_hashes_checked':source_files,'independent_gold_all60_agrees':True,'strict_parse_tournament_paths_agree':True,'primary_and_secondary_bootstrap_ci_agree':True,'max_prompt_tokens':max_tokens,'results_sha256':H((P/'RESULTS.json').read_bytes()),'audit_code_sha256':H(Path(__file__).read_bytes()),'limitations':'Both audits use the same public patch and pre-patch source as evidence. Uniquely bound old hunk context is required; ambiguous/new-file/outside-definition changes do not create exact-definition targets. No repair outcome or global unseen/contamination-free claim.'};(P/'INDEPENDENT-AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
