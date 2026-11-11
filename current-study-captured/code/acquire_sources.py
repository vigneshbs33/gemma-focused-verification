"""Qualification only, separate from inference. Compress Python source, no repo code execution."""
from pathlib import Path
import concurrent.futures,hashlib,json,subprocess,tarfile,urllib.request,sys,tempfile,shutil,io
import pyarrow.parquet as pq
P=Path(__file__).parent;sel=json.loads((P/'COHORT-QUALIFICATION.json').read_text())['selected'];mapping={t['instance_id']:t for t in sel};rows=[r for r in pq.read_table(P/'full-test-private.parquet').to_pylist() if r['instance_id'] in mapping];rows.sort(key=lambda r:(mapping[r['instance_id']]['assignment']!='development',r['instance_id']))
sha=lambda b:hashlib.sha256(b).hexdigest()
for d in ['source-archives','qa','patches']:(P/d).mkdir(exist_ok=True)
def acquire(row):
 iid=row['instance_id'];record=P/'qa'/(iid+'.json');arc=P/'source-archives'/(iid+'.tar.gz')
 if record.exists():return json.loads(record.read_text())
 url=f"https://codeload.github.com/{row['repo']}/tar.gz/{row['base_commit']}";out={k:row[k] for k in ['instance_id','repo','base_commit']};out.update(source_url=url,assignment=mapping[iid]['assignment'],query_sha256=sha(row['problem_statement'].encode()),patch_sha256=sha(row['patch'].encode()))
 try:
  with urllib.request.urlopen(url,timeout=60) as response:raw=response.read(120_000_001)
  if len(raw)>120_000_000:raise RuntimeError('archive>120MBcap; no replacement')
  out.update(upstream_archive_bytes=len(raw),upstream_archive_sha256=sha(raw))
  with tempfile.TemporaryDirectory(prefix='stronger-source-') as d:
   root=Path(d)
   with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tf:
    for m in tf:
     parts=Path(m.name).parts[1:]
     if not parts or '..' in parts or not m.isfile():continue
     rel=Path(*parts);lic=rel.name.lower().startswith(('license','licence','copying','notice'))
     if rel.suffix!='.py' and not lic:continue
     if m.size>10_000_000:raise RuntimeError('sourcefile>10MBcap')
     f=root/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(tf.extractfile(m).read())
   del raw
   patch=P/'patches'/(iid+'.patch');patch.write_text(row['patch']);check=subprocess.run(['git','apply','--check',str(patch)],cwd=root,capture_output=True,text=True)
   py=sorted(root.rglob('*.py'));pins={str(f.relative_to(root)):sha(f.read_bytes()) for f in py};old=[s[6:] for s in row['patch'].splitlines() if s.startswith('--- a/')]
   out.update(python_files=len(py),python_bytes=sum(f.stat().st_size for f in py),source_content_sha256=sha(json.dumps(pins,sort_keys=True).encode()),source_file_pins=pins,patch_check_rc=check.returncode,patch_check_message=check.stderr.strip(),old_targets_present=all((root/f).is_file() for f in old if f.endswith('.py')),license_files=[str(f.relative_to(root)) for f in root.rglob('*') if f.is_file() and f.suffix!='.py'])
   with tarfile.open(arc.with_suffix('.tmp'),'w:gz',compresslevel=3) as tf:
    for f in sorted(root.rglob('*')):
     if f.is_file():tf.add(f,arcname=str(f.relative_to(root)),recursive=False)
   arc.with_suffix('.tmp').replace(arc)
   out.update(private_python_archive_bytes=arc.stat().st_size,private_python_archive_sha256=sha(arc.read_bytes()))
 except Exception as e:out['error']=f'{type(e).__name__}: {e}'
 record.write_text(json.dumps(out,indent=2)+'\n');return out
if __name__=='__main__':
 limit=int(sys.argv[1]) if len(sys.argv)>1 else 12;pending=[r for r in rows if not (P/'qa'/(r['instance_id']+'.json')).exists()][:limit]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
  for r in ex.map(acquire,pending):print(r['instance_id'],r.get('patch_check_rc',r.get('error')),r.get('python_files'),r.get('private_python_archive_bytes'),flush=True)
 records=[json.loads(f.read_text()) for f in sorted((P/'qa').glob('*.json'))];(P/'SOURCE-QA.json').write_text(json.dumps({'selected':72,'checked':len(records),'tasks':records},indent=2)+'\n');print('CHECKED',len(records),'/72',flush=True)
