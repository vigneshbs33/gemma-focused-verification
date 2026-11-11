"""Independent read-only source, label, tournament and metric audit.
Does not import binder/evaluator or rerun inference.
"""
from pathlib import Path
import ast,collections,json,re,hashlib,tarfile,random,sqlite3
import pyarrow.parquet as pq
P=Path(__file__).parent;H=lambda b:hashlib.sha256(b).hexdigest();arms=['T5','T20','V20','Dense1']
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
 frozen=json.loads((P/'EVALUATION-FREEZE.json').read_text());outfreeze=json.loads((P/'EVALUATION-OUTPUT-FREEZE.json').read_text());results=json.loads((P/'RESULTS.json').read_text());rows={r['instance_id']:r for r in pq.read_table(P/'full-test-private.parquet',columns=['instance_id','patch']).to_pylist()};scores=[];checked=0;source_files=0;max_tokens=0
 for n,h in frozen['code_hashes'].items():assert H((P/n).read_bytes())==h
 for n,h in outfreeze['output_hashes'].items():assert H((P/'outputs'/n).read_bytes())==h
 for expected in results['per_task']:
  iid=expected['instance_id'];qa=json.loads((P/'qa'/(iid+'.json')).read_text());arc=P/'source-archives'/(iid+'.tar.gz')
  with tarfile.open(arc) as tf:
   pins={m.name:H(tf.extractfile(m).read()) for m in tf if m.isfile() and m.name.endswith('.py')};assert pins==qa['source_file_pins'];source_files+=len(pins)
  gold,func,mods,amb,unresolved=independent_gold(rows[iid]['patch'],arc);bound=json.loads((P/'gold-bindings'/(iid+'.json')).read_text());assert gold==set(bound['gold']),(iid,'gold disagreement');assert func==set(bound['function_gold']);assert mods==set(bound['coarse_modules']);assert amb==set(bound['ambiguous_symbols']);assert unresolved==bound['coverage'].get('unresolved_hunks',0)
  pack=json.loads((P/'private-packs'/(iid+'.json')).read_text());rank=json.loads((P/'rankings'/(iid+'.json')).read_text());assert H((P/'private-packs'/(iid+'.json')).read_bytes())==frozen['pack_hashes'][iid+'.json'];receipt=json.loads((P/'task-receipts'/('evaluation-'+iid+'.json')).read_text());score={'repo':expected['repo'],'arms':{}};order=rank['ranks']['semantic20'];winners_by_rotation=[];resources={}
  def load(cid,candidates):
   nonlocal checked,max_tokens
   call=json.loads((P/'private-calls'/(cid+'.json')).read_text());out=json.loads((P/'outputs'/(cid+'.json')).read_text());assert call['candidates']==candidates==out['candidates'];assert H(call['prompt'].encode())==out['prompt_sha256'];st=json.loads((P/'logs'/('call-'+cid+'-status.json')).read_text());assert st['returncode']==0 and not st['stop_reason'] and st['peak_rss_kib']<=1536000 and st['elapsed_seconds']<=90.5;assert out['prompt_tokens']<=960;checked+=1;max_tokens=max(max_tokens,out['prompt_tokens']);return out,st
  for rotation in range(4):
   arm='T'+str(rotation);rot=order[rotation:]+order[:rotation];groups=[rot[k::4] for k in range(4)];assert groups==pack['groups'][arm];winners=[];outs=[];sts=[]
   for k,cands in enumerate(groups):
    cid=f'evaluation-{iid}-{arm}-s{k}';out,st=load(cid,cands);outs.append(out);sts.append(st);chosen,valid,zero=decision(out['response'],cands);saved=receipt['arms'][arm]['stages'][k];assert (chosen,valid)==(saved['selected'],saved['valid'])
    if chosen:winners.append(chosen)
   if winners:
    out,st=load(f'evaluation-{iid}-{arm}-final',winners);outs.append(out);sts.append(st);chosen,valid,zero=decision(out['response'],winners);assert chosen==receipt['arms'][arm]['final']['selected']
   else:chosen=None
   assert chosen==receipt['arms'][arm]['selected'];winners_by_rotation.append(chosen);resources[arm]=(outs,sts)
  votes=[winners_by_rotation.count(s) for s in order];top=max(votes);chosen=order[votes.index(top)] if top else None;pred={'T20':chosen,'T5':winners_by_rotation[0],'Dense1':rank['dense_orders']['semantic'][0]};ordinal=[];outs=[];sts=[]
  for k,symbol in enumerate(order):
   out,st=load(f'evaluation-{iid}-V20-s{k}',[symbol]);outs.append(out);sts.append(st);v=out['response'].strip();n=int(v) if len(v)==1 and v in '0123' else -1;ordinal.append(n);assert receipt['arms']['V20']['scores'][k]['score']==n
  top=max(ordinal);pred['V20']=order[ordinal.index(top)] if top>0 else None;resources['V20']=(outs,sts);resources['T5']=resources['T0'];resources['T20']=([x for k in range(4) for x in resources['T'+str(k)][0]],[x for k in range(4) for x in resources['T'+str(k)][1]]);resources['Dense1']=([],[])
  for arm,chosen in pred.items():
   if arm!='Dense1':assert chosen==receipt['arms'][arm]['selected']
   e=expected['arms'][arm];assert (int(chosen in gold),int(chosen in func))==(e['correct'],e['function_only_correct']);score['arms'][arm]=int(chosen in gold);oo,ss=resources[arm];assert len(oo)==e['calls'] and sum(o['prompt_tokens'] for o in oo)==e['prompt_tokens'];assert abs(sum(o['elapsed_seconds'] for o in oo)-e['generation_seconds'])<1e-7
  scores.append(score)
 assert checked==len(outfreeze['output_hashes'])
 for a,b in [('V20','T20'),('V20','T5'),('T20','T5'),('V20','Dense1')]:
  ds=[r['arms'][a]-r['arms'][b] for r in scores];rng=random.Random(42);boot=sorted(sum(ds[i] for i in rng.choices(range(60),k=60))/60 for _ in range(10000));repos=sorted({r['repo'] for r in scores});rng=random.Random(43);cluster=[]
  for _ in range(10000):
   sample=[r['arms'][a]-r['arms'][b] for repo in rng.choices(repos,k=len(repos)) for r in scores if r['repo']==repo];cluster.append(sum(sample)/len(sample))
  cluster.sort();e=results['paired'][a+'-minus-'+b];assert e['task_ci95']==[boot[250],boot[9750]] and e['repository_cluster_ci95']==[cluster[250],cluster[9750]];assert e['wins']==ds.count(1) and e['losses']==ds.count(-1) and e['ties']==ds.count(0)
 audit={'pass':True,'tasks':len(scores),'independently_parsed_calls':checked,'source_file_hashes_checked':source_files,'independent_gold_all60_agrees':True,'strict_parse_rotations_vote_ordinal_paths_agree':True,'primary_and_secondary_bootstrap_ci_agree':True,'max_prompt_tokens':max_tokens,'results_sha256':H((P/'RESULTS.json').read_bytes()),'audit_code_sha256':H(Path(__file__).read_bytes()),'limitations':'Independent logic uses same source/patch evidence; no repair execution, globally unseen or contamination-free claim.'};(P/'INDEPENDENT-AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
