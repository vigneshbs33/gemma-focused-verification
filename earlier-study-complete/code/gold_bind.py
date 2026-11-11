"""Post-output-freeze strict source/patch binder. Never executes repository code."""
from pathlib import Path
import ast,re,json,hashlib,tarfile,collections,datetime
import pyarrow.parquet as pq
P=Path(__file__).parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def module(path):
 p=path[:-3].replace('/','.')
 return p[:-9] if p.endswith('.__init__') else p

def definitions(text):
 tree=ast.parse(text);out=[]
 def walk(n,prefix=''):
  for c in ast.iter_child_nodes(n):
   if isinstance(c,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
    q=prefix+'.'+c.name if prefix else c.name;out.append((c.lineno,c.end_lineno,q,'class' if isinstance(c,ast.ClassDef) else 'function'));walk(c,q)
   else:walk(c,prefix)
 walk(tree);return out

def parse(patch):
 files=[];f=None;h=None
 for line in patch.splitlines():
  if line.startswith('diff --git '):
   f={'path':None,'new_path':None,'hunks':[]};files.append(f);h=None
  elif line.startswith('--- '):f['path']=None if line[4:]=='/dev/null' else line[6:]
  elif line.startswith('+++ '):f['new_path']=None if line[4:]=='/dev/null' else line[6:]
  elif line.startswith('@@ '):
   m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',line);assert m,line
   h={'old_start':int(m[1]),'old_count':int(m[2] or 1),'new_start':int(m[3]),'new_count':int(m[4] or 1),'lines':[]};f['hunks'].append(h)
  elif h is not None and line[:1] in [' ','+','-']:h['lines'].append(line)
  elif line.startswith('\\ No newline'):pass
 return files

def bind_task(row,qa,archive):
 gold=set();function_gold=set();ambiguous=set();modules=set();targets=[];bindings=[];coverage=collections.Counter()
 with tarfile.open(archive) as tf:
  members={m.name:m for m in tf if m.isfile()}
  for f in parse(row['patch']):
   path=f['path']
   if not path or not path.endswith('.py') or path not in members:
    coverage['unmapped_file_hunks']+=len(f['hunks']);continue
   raw=tf.extractfile(members[path]).read();assert sha(raw)==qa['source_file_pins'][path];text=raw.decode(errors='replace');lines=text.splitlines();modules.add(module(path))
   try:defs=definitions(text)
   except SyntaxError:coverage['parse_failure_hunks']+=len(f['hunks']);continue
   counts=collections.Counter(d[2] for d in defs)
   def enclosing(ln):
    ds=[d for d in defs if d[0]<=ln<=d[1]]
    return min(ds,key=lambda d:(d[1]-d[0],-d[0])) if ds else None
   def add(ln,kind):
    d=enclosing(ln)
    if not d:coverage['outside_definition_lines']+=1;return
    s=module(path)+'.'+d[2]
    if counts[d[2]]!=1:ambiguous.add(s);coverage['ambiguous_definition_lines']+=1;return
    gold.add(s)
    if d[3]=='function':function_gold.add(s)
    targets.append({'symbol':s,'path':path,'line':ln,'kind':d[3],'mapping':kind})
   for h in f['hunks']:
    old=[x[1:] for x in h['lines'] if x[0] in ' -'];assert len(old)==h['old_count'],(row['instance_id'],path,'bad_hunk_count')
    matches=[i for i in range(len(lines)-len(old)+1) if lines[i:i+len(old)]==old] if old else []
    if len(matches)!=1:
     bindings.append({'path':path,'header_start':h['old_start'],'actual_start':None,'matches':len(matches)});coverage['unresolved_hunks']+=1;continue
    start=matches[0];bindings.append({'path':path,'header_start':h['old_start'],'actual_start':start+1,'offset':start+1-h['old_start'],'matches':1});pos=start+1;i=0
    while i<len(h['lines']):
     x=h['lines'][i]
     if x[0]==' ':pos+=1;i+=1;continue
     block=[];boundary=pos
     while i<len(h['lines']) and h['lines'][i][0]!=' ':block.append(h['lines'][i]);i+=1
     removed=[x for x in block if x[0]=='-']
     if removed:
      for x in removed:assert lines[pos-1]==x[1:];add(pos,'removed_line');pos+=1
     else:
      left=enclosing(boundary-1);right=enclosing(boundary)
      if left and left==right:add(boundary-1,'insertion_neighbor');add(boundary,'insertion_neighbor')
      else:coverage['unresolved_insertion_blocks']+=1
 return {'gold':sorted(gold),'function_gold':sorted(function_gold),'ambiguous_symbols':sorted(ambiguous),'coarse_modules':sorted(modules),'targets':targets,'bindings':bindings,'coverage':dict(coverage)}

def main():
 freeze=json.loads((P/'EVALUATION-OUTPUT-FREEZE.json').read_text());assert freeze['evaluation_tasks']==60
 for n,h in freeze['output_hashes'].items():assert sha((P/'outputs'/n).read_bytes())==h
 rows={r['instance_id']:r for r in pq.read_table(P/'recovered-inputs/full-test-private.parquet',columns=['instance_id','repo','base_commit','problem_statement','patch']).to_pylist()};tasks=[t for t in json.loads((P/'COHORT-QUALIFICATION.json').read_text())['selected'] if t['assignment']=='evaluation'];out=P/'gold-bindings';out.mkdir(exist_ok=True)
 for t in sorted(tasks,key=lambda t:t['instance_id']):
  iid=t['instance_id'];f=out/(iid+'.json')
  if f.exists():continue
  row=rows[iid];qa=json.loads((P/'qa'/(iid+'.json')).read_text());assert row['base_commit']==t['base_commit'];assert sha(row['patch'].encode())==qa['patch_sha256'];assert sha(row['problem_statement'].encode())==t['query_sha256'];arc=P/'source-archives'/(iid+'.tar.gz');assert sha(arc.read_bytes())==qa['private_python_archive_sha256'];r=bind_task(row,qa,arc);r.update(instance_id=iid,repo=t['repo'],output_freeze_sha256=sha((P/'EVALUATION-OUTPUT-FREEZE.json').read_bytes()),binder_sha256=sha(Path(__file__).read_bytes()));f.write_text(json.dumps(r,indent=2)+'\n')
 print('GOLD_BINDINGS_COMPLETE',len(list(out.glob('*.json'))))
if __name__=='__main__':main()
