"""Optional offline record check. Packaging tool, not experimental method.
Python 3.10+, standard library. No inference, model loading or network.
"""
from pathlib import Path
import json, tempfile, subprocess, sys, hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
    files={}
    for bundle in sorted((ROOT/'records').glob('captured-records-*.json')):
        for name,text in json.loads(bundle.read_text(encoding='utf-8'))['files'].items():
            if name in files: raise ValueError('Duplicate member')
            files[name]=text.encode('utf-8')
    for directory in ['current-study-captured','earlier-study-complete','source-dependencies']:
        for p in (ROOT/directory).rglob('*.py'):
            files[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    files['verify_evidence.py']=(ROOT/'tools/verify_evidence.py').read_bytes()
    manifest=json.loads(files['MANIFEST.json'])
    for name,digest in manifest.items():
        if hashlib.sha256(files[name]).hexdigest()!=digest: raise ValueError('Hash mismatch: '+name)
    with tempfile.TemporaryDirectory(prefix='focused-verification-records-') as td:
        d=Path(td)
        for name,b in files.items():
            p=Path(name)
            if p.is_absolute() or '..' in p.parts: raise ValueError('Unsafe member')
            out=d/p;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b)
        return subprocess.run([sys.executable,str(d/'verify_evidence.py')]).returncode
if __name__=='__main__': sys.exit(main())
