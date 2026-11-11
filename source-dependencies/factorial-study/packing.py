"""Deterministic source-text windows. No gold imports and no repository execution."""
import ast,collections,keyword,pathlib,re
TOK=re.compile(r'[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+')
STOP=set(keyword.kwlist)|set('the a an is are was were be been it its this that these those of to for from and or with without in on at by as not should would could can does do have has when then than use using return self none true false'.split())
def words(s):return {t.lower() for t in TOK.findall(s) if len(t)>=3 and t.lower() not in STOP}
def extract(root,wanted):
 out={};multiplicity=collections.Counter()
 for fp in sorted(root.rglob('*.py')):
  rel=str(fp.relative_to(root));module=(rel[4:] if rel.startswith('src/') else rel)[:-3].replace('/','.');src=fp.read_text(errors='replace');lines=src.splitlines()
  if module in wanted:out.setdefault(module,{'symbol':module,'path':rel,'start':1,'end':len(lines),'lines':lines,'header':'[module]','body_start':0,'doclines':set()})
  try:tree=ast.parse(src)
  except SyntaxError:continue
  def walk(n,prefix=''):
   for c in ast.iter_child_nodes(n):
    if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
     q=prefix+'.'+c.name if prefix else c.name;s=module+'.'+q
     if s in wanted:
      multiplicity[s]+=1;firstbody=c.body[0].lineno if c.body else c.lineno+1;doclines=set()
      if c.body and isinstance(c.body[0],ast.Expr) and isinstance(c.body[0].value,ast.Constant) and isinstance(c.body[0].value.value,str):doclines=set(range(c.body[0].lineno,c.body[0].end_lineno+1))
      out.setdefault(s,{'symbol':s,'path':rel,'start':c.lineno,'end':c.end_lineno,'lines':lines[c.lineno-1:c.end_lineno],'header':'\n'.join(lines[c.lineno-1:firstbody-1]),'body_start':firstbody-c.lineno,'doclines':doclines})
     walk(c,q)
    else:walk(c,prefix)
  walk(tree)
 for s in wanted:
  if s not in out:out[s]={'symbol':s,'path':None,'start':0,'end':0,'lines':[],'header':'[source unavailable]','body_start':0,'doclines':set()}
  out[s]['same_qualified_count']=multiplicity[s]
 return out

def window(candidate,query,max_lines=12):
 lines=candidate['lines'];base=candidate['start'];start=candidate['body_start'];q=words(query);scores=[]
 for i in range(start,len(lines)):
  n=base+i
  if n in candidate['doclines'] or not lines[i].strip() or lines[i].lstrip().startswith('#'):continue
  tokenhits=words(lines[i])&q
  scores.append((len(tokenhits),-i,i))
 center=max(scores)[2] if scores else min(start,max(len(lines)-1,0))
 # Anchor the window up to three lines before the strongest body line.
 lo=max(start,center-min(3,max_lines-1));hi=min(len(lines),lo+max_lines)
 if hi-lo<max_lines:lo=max(start,hi-max_lines)
 return lo,hi

def render_lines(candidate,lo,hi):
 return '\n'.join(f"{candidate['start']+i}: {candidate['lines'][i]}" for i in range(lo,hi))

def synthetic():
 c={'lines':['def f(x):','    """A long boring docstring."""','    a = x + 1','    for k in range(20):','        a += k','    return target_bug(a)'],'start':10,'body_start':1,'doclines':{11}}
 lo,hi=window(c,'target_bug causes failure',3);assert lo<=5<hi;assert render_lines(c,lo,hi).splitlines()[-1].startswith('15:')
 assert window(c,'unrelated',3)[0]>=1
 assert words('The fooBar and self target_bug')=={'foo','bar','target','bug'}
 return True
if __name__=='__main__':assert synthetic();print('synthetic window tests pass')
