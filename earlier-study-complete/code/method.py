"""Pre-patch AST graph and bounded candidate proposal. No gold or patch imports.
Conceptual lineage: LocAgent/RepoGraph, CoRNStack/CodeRankEmbed, SweRank.
All retrieval/fusion constants fixed before new cohort outcomes.
"""
from pathlib import Path
import ast,re,collections,json,hashlib,sys,math
P=Path(__file__).parent
sys.path.insert(0,'/downloads/gemma-standalone')
import scorer_v3 as scorer
sys.path.insert(0,'/downloads/gemma-factorial-20261110')
import packing
MODULE=scorer.mod_of
STOP_PATH=scorer.TESTPAT

def build(root):
 nodes={};imports={};filemods={};duplicates=[];parse_errors=[]
 def local_calls(x):
  for c in ast.iter_child_nodes(x):
   if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):continue
   if isinstance(c,ast.Call):yield ast.unparse(c.func)
   yield from local_calls(c)
 for f in sorted(Path(root).rglob('*.py')):
  rel=str(f.relative_to(root));mod=MODULE(rel);src=f.read_text(errors='replace');lines=src.splitlines();filemods[rel]=mod
  nodes.setdefault(mod,dict(symbol=mod,path=rel,start=1,end=len(lines),kind='module',lines=lines,header='[module]',body_start=0,doclines=set(),text=src))
  try:t=ast.parse(src)
  except SyntaxError as e:parse_errors.append({'path':rel,'line':e.lineno});continue
  aliases={}
  for x in t.body:
   if isinstance(x,ast.Import):
    for a in x.names:aliases[a.asname or a.name.split('.')[0]]=a.name if a.asname else a.name.split('.')[0]
   elif isinstance(x,ast.ImportFrom):
    parts=mod.split('.')[:-1];base='.'.join(parts[:len(parts)-x.level+1]) if x.level else '';base='.'.join(filter(None,[base,x.module]))
    for a in x.names:
     if a.name!='*':aliases[a.asname or a.name]='.'.join(filter(None,[base,a.name]))
  imports[mod]=aliases
  def walk(n,prefix=''):
   for c in ast.iter_child_nodes(n):
    if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
     q=prefix+'.'+c.name if prefix else c.name;s=mod+'.'+q;first=c.body[0].lineno if c.body else c.lineno+1
     doc=ast.get_docstring(c) or '';dl=set()
     if c.body and isinstance(c.body[0],ast.Expr) and isinstance(c.body[0].value,ast.Constant) and isinstance(c.body[0].value.value,str):dl=set(range(c.body[0].lineno,c.body[0].end_lineno+1))
     seg='\n'.join(lines[c.lineno-1:c.end_lineno]);entry=dict(symbol=s,path=rel,start=c.lineno,end=c.end_lineno,kind='class' if isinstance(c,ast.ClassDef) else 'function',lines=lines[c.lineno-1:c.end_lineno],header='\n'.join(lines[c.lineno-1:first-1]),body_start=first-c.lineno,doclines=dl,text=c.name+'\n'+doc+'\n'+seg,calls_raw=list(local_calls(c)),bases_raw=[ast.unparse(b) for b in c.bases] if isinstance(c,ast.ClassDef) else [],module=mod,qualified=q)
     if s in nodes:duplicates.append({'symbol':s,'first_line':nodes[s]['start'],'additional_line':c.lineno})
     else:nodes[s]=entry
     walk(c,q)
    else:walk(c,prefix)
  walk(t)
 suffix=collections.defaultdict(set)
 for s in nodes:
  ps=s.split('.')
  for k in range(1,len(ps)+1):suffix['.'.join(ps[-k:])].add(s)
 edges=set();adj=collections.defaultdict(set);unresolved=0
 def edge(a,b,typ):
  if a in nodes and b in nodes and a!=b:edges.add((a,b,typ));adj[a].add(b);adj[b].add(a)
 def resolve(raw,mod,owner):
  if not raw:return None
  if raw.startswith(('self.','cls.')):
   parent=owner.rsplit('.',1)[0];r=parent+'.'+raw.split('.',1)[1]
   if r in nodes:return r
  first,*tail=raw.split('.');a=imports[mod].get(first)
  if a:
   r='.'.join([a]+tail)
   if r in nodes:return r
  r=mod+'.'+raw
  if r in nodes:return r
  matches=suffix.get(raw,set())
  return next(iter(matches)) if len(matches)==1 else None
 for s,n in nodes.items():
  if n['kind']=='module':
   for a in imports.get(s,{}).values():
    target=resolve(a,s,s)
    if target:edge(s,target,'imports')
   continue
  mod=n['module'];parent=s.rsplit('.',1)[0]
  if parent not in nodes:parent=mod
  edge(parent,s,'contains')
  if n['kind']=='class':
   for raw in n['bases_raw']:
    target=resolve(raw,mod,s)
    if target:edge(s,target,'inherits')
  # Avoid attributing nested functions' calls to their enclosing function/class.
  def calls(x):
   for c in ast.iter_child_nodes(x):
    if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):continue
    if isinstance(c,ast.Call):yield c
    yield from calls(c)
  for raw in n['calls_raw']:
   target=resolve(raw,mod,s)
   if target:edge(s,target,'calls')
   else:unresolved+=1
 for n in nodes.values():n.pop('ast',None)
 return {'nodes':nodes,'suffix':suffix,'edges':edges,'adj':adj,'parse_errors':parse_errors,'duplicates':duplicates,'unresolved_calls':unresolved,'filemods':filemods}

def query_only_bm25_scores(texts,query):
 # Exact BM25 sufficient statistics: non-query terms affect length only.
 # Preserve token/query order and arithmetic of scorer_v3.BM25.scores.
 q=scorer.tokenize(query);wanted=set(q);lengths=[];tfs=[];df=collections.Counter()
 for text in texts:
  tokens=scorer.tokenize(text);lengths.append(len(tokens));counts=collections.Counter(t for t in tokens if t in wanted);tfs.append(counts);df.update(counts.keys())
 avg=sum(lengths)/max(1,len(lengths));N=len(lengths);out=[]
 for dl,tf in zip(lengths,tfs):
  score=0.0
  for t in q:
   frequency=tf.get(t)
   if not frequency:continue
   idf=math.log(1+(N-df[t]+0.5)/(df[t]+0.5));denom=frequency+1.5*(1-0.75+0.75*dl/avg);score+=idf*frequency*(1.5+1)/denom
  out.append(score)
 return out

def lexical(index,query):
 nodes=index['nodes'];names=list(nodes)
 body=query_only_bm25_scores((nodes[s]['text'] for s in names),query)
 name=query_only_bm25_scores((s.split('.')[-1]+' '+(s.split('.')[-2] if '.' in s else '') for s in names),query)
 path=query_only_bm25_scores((scorer.sym_path(s) for s in names),query)
 scores={}
 for i,s in enumerate(names):
  weight=2*name[i]+2*path[i]+body[i]
  if STOP_PATH.search('/'.join(s.split('.')[:-1]) or ''):weight*=.5
  scores[s]=weight
 ordinary=sorted(range(len(names)),key=lambda i:(-body[i],i));fielded=sorted(names,key=lambda s:-scores[s])
 return {'C2':[names[i] for i in ordinary],'C2F':fielded}

def structural(index,query,lexical_ranks):
 nodes=index['nodes'];suffix=index['suffix'];seeds={};evidence=[]
 # Exact qualified names and unique single identifiers. Ambiguous suffixes are not guessed.
 identifiers=re.findall(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*',query)
 for raw in identifiers:
  if len(raw)<4:continue
  match=suffix.get(raw,set())
  if len(match)==1:
   s=next(iter(match));weight=3 if '.' in raw else 1
   seeds[s]=max(seeds.get(s,0),weight);evidence.append({'seed':s,'via':'exact_unique_name','mention':raw})
 # Explicit Python file and traceback line: source-only innermost definition.
 for match in re.finditer(r'(?:File\s+[\"\']?)?([A-Za-z_0-9./-]+\.py)[\"\']?[, :]*(?:line\s*)?(\d+)?',query):
  path,line=match.groups();paths=[p for p in index['filemods'] if p==path or p.endswith('/'+path)]
  if len(paths)!=1:continue
  rel=paths[0];mod=index['filemods'][rel];s=mod
  if line:
   span=[(n['end']-n['start'],a) for a,n in nodes.items() if n['path']==rel and n['start']<=int(line)<=n['end']]
   if span:s=min(span)[1]
  seeds[s]=max(seeds.get(s,0),4);evidence.append({'seed':s,'via':'unique_path_line' if line else 'unique_path'})
 order=sorted(seeds,key=lambda s:(-seeds[s],s));scores=collections.defaultdict(float)
 for s in order:
  scores[s]+=seeds[s]
  for v in sorted(index['adj'].get(s,set())):scores[v]+=seeds[s]/2
 # Shallow expansion of eight independent lexical anchors; no iterative generated query.
 for i,s in enumerate(lexical_ranks[:8]):
  for v in sorted(index['adj'].get(s,set())):scores[v]+=1/(i+2)
 ranking=sorted(scores,key=lambda s:(-scores[s],s))
 return {'ranking':ranking,'seeds':order,'evidence':evidence,'scores':dict(scores),'depth':1}

def propose(index,query):
 lex=lexical(index,query);graph=structural(index,query,lex['C2F']);base=lex['C2F'][:320]
 rescue=[s for s in graph['ranking'] if s not in set(lex['C2F'][:256])][:64]
 structural_pool=list(dict.fromkeys(lex['C2F'][:256]+rescue))
 for s in base:
  if len(structural_pool)>=320:break
  if s not in structural_pool:structural_pool.append(s)
 return {'lexical':lex,'graph':graph,'pools':{'semantic':base,'structural':structural_pool},'max_embedding_candidates_per_arm':320,'deduplicated_symbols':len(index['nodes']),'parse_errors':index['parse_errors'],'duplicates':index['duplicates'],'graph_edges':len(index['edges']),'unresolved_calls':index['unresolved_calls']}

def fuse(lexical_order,dense_order,graph_order=None):
 scores=collections.defaultdict(float);orders=[lexical_order,dense_order]+([graph_order] if graph_order is not None else [])
 for rank in orders:
  for i,s in enumerate(rank):scores[s]+=1/(60+i+1)
 return sorted(scores,key=lambda s:(-scores[s],s))[:20]

def tests():
 import tempfile
 with tempfile.TemporaryDirectory() as d:
  p=Path(d);(p/'pkg').mkdir();(p/'pkg'/'core.py').write_text('def leaf(x):\n    return x + 1\n\ndef wrapper(x):\n    return leaf(x)\n\nclass Base:\n    pass\n\nclass Child(Base):\n    def run(self,x):\n        return wrapper(x)\n')
  g=build(p);assert ('pkg.core.wrapper','pkg.core.leaf','calls') in g['edges'];assert ('pkg.core.Child','pkg.core.Base','inherits') in g['edges'];assert ('pkg.core.Child','pkg.core.Child.run','contains') in g['edges']
  st=structural(g,'wrapper fails with negative data',[]);assert 'pkg.core.wrapper' in st['seeds'] and 'pkg.core.leaf' in st['ranking']
  st2=structural(g,'File pkg/core.py, line 5 failed',[]);assert 'pkg.core.wrapper' in st2['seeds']
  proposal=propose(g,'leaf fails');assert len(proposal['pools']['semantic'])<=320
  assert fuse(['a','b'],['b','a'])[0]=='a'
 return {'synthetic_tests':'passed','gold_access':False,'repository_execution':False}
if __name__=='__main__':print(json.dumps(tests()))
