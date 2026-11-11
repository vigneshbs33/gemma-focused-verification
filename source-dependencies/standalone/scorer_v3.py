#!/usr/bin/env python3
"""Original v3 scorer extracted without task-card or published-row loading.
Algorithm bodies copied unchanged. Standard library only. No gold data loaded.
"""
import json,os,re,sys,math,hashlib,ast,pickle
from collections import defaultdict
EXP=os.path.dirname(os.path.abspath(__file__))
TOK=re.compile(r'[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+')
TESTPAT=re.compile(r'(^|/)(tests?|testing|conftest)|(^|/)test_[^/]*\.py$|_test\.py$')
_BM_CACHE={}
CACHE=None
def mod_of(f):
    if not f.endswith('.py'): return None
    p = f[:-3]
    if p.startswith('src/'): p = p[4:]
    return p.replace('/', '.')

def tokenize(text):
    return [t.lower() for t in TOK.findall(text)]

class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.df = defaultdict(int)
        self.dl = [len(d) for d in docs]
        self.tfs = []
        for d in docs:
            tf = defaultdict(int)
            for t in d: tf[t] += 1
            self.tfs.append(tf)
            for t in tf: self.df[t] += 1
        self.avgdl = sum(self.dl) / max(1, len(self.dl))
        self.N = len(docs)
    def scores(self, query):
        q = tokenize(query)
        sc = []
        for i, tf in enumerate(self.tfs):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f: continue
                idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                denom = f + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl)
                s += idf * f * (self.k1 + 1) / denom
            sc.append(s)
        return sc

def load_task_source(task):
    root = os.environ.get('GEMMA_SRC_DIR', f'{EXP}/src') + f'/x-{task}'
    files = {}
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith('.py'):
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, root)
                try: files[rel] = open(p, encoding='utf-8', errors='replace').read()
                except OSError: pass
    return files

def symbols_of(rel, src):
    m = mod_of(rel)
    if not m: return []
    out = [(m, src)]
    try: tree = ast.parse(src)
    except SyntaxError: return out
    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f'{prefix}.{ch.name}' if prefix else ch.name
                body = ast.get_docstring(ch) or ''
                seg = ast.get_source_segment(src, ch) or ch.name
                out.append((f'{m}.{qual}', ch.name + '\n' + body + '\n' + seg))
                visit(ch, qual)
            else:
                visit(ch, prefix)
    visit(tree, '')
    return out

def build_indexes(task, issue):
    cp = f'{CACHE}/{task}.pkl'
    if os.path.exists(cp):
        return pickle.load(open(cp, 'rb'))
    files = load_task_source(task)
    # C1: file-level
    fmods, fdocs = [], []
    for rel, src in sorted(files.items()):
        m = mod_of(rel)
        if m:
            fmods.append(m)
            fdocs.append(tokenize(rel.replace('/', ' ') + ' ' + src))
    # C2/C3: symbol-level
    syms, sdocs2, sdocs3 = [], [], []
    for rel, src in sorted(files.items()):
        m = mod_of(rel)
        if not m: continue
        for qual, text in symbols_of(rel, src):
            syms.append(qual)
            sdocs2.append(tokenize(text))
            sdocs3.append(tokenize(rel.replace('/', ' ') + ' ' + text))
    res = ((fmods, fdocs), (syms, sdocs2, sdocs3))
    pickle.dump(res, open(cp, 'wb'))
    return res

def rank(bm, docs, names, query):
    sc = bm.scores(query)
    order = sorted(range(len(sc)), key=lambda i: -sc[i])
    return [names[i] for i in order]

def path_of(sym):
    m = sym.split('.')
    for i in range(len(m), 0, -1):
        p = '/'.join(m[:i])
        return p.replace('.', '/')

def sym_path(sym):
    # symbol 'pkg.mod.Outer.fn' -> module path tokens from the leading module part is unknown;
    # use all dot-parts as path-ish tokens except the final name: approximates the file path field.
    return sym.replace('.', ' ')

def c2f_rank(task, idx, query):
    (fmods, fdocs), (syms, sdocs2, sdocs3) = idx
    name_docs = [tokenize(s.split('.')[-1] + ' ' + (s.split('.')[-2] if '.' in s else '')) for s in syms]
    path_docs = [tokenize(sym_path(s)) for s in syms]
    bm_n = _BM_CACHE.setdefault((task,'Fn'), BM25(name_docs))
    bm_p = _BM_CACHE.setdefault((task,'Fp'), BM25(path_docs))
    bm_b = _BM_CACHE.setdefault((task,'Fb'), BM25(sdocs2))
    sn, sp, sb = bm_n.scores(query), bm_p.scores(query), bm_b.scores(query)
    out = []
    for i, s in enumerate(syms):
        w = 2*sn[i] + 2*sp[i] + sb[i]
        if TESTPAT.search('/'.join(s.split('.')[:-1]) or ''): w *= 0.5
        out.append((w, s))
    out.sort(key=lambda x: -x[0])
    return [s for _, s in out]

def run_config(task, cfg, idx, query):
    if cfg == 'C2F':
        return c2f_rank(task, idx, query)
    (fmods, fdocs), (syms, sdocs2, sdocs3) = idx
    def get_bm(key, docs):
        k = (task, key)
        if k not in _BM_CACHE: _BM_CACHE[k] = BM25(docs)
        return _BM_CACHE[k]
    if cfg == 'C1':
        return rank(get_bm('C1', fdocs), fdocs, fmods, query)
    if cfg == 'C2':
        return rank(get_bm('C2', sdocs2), sdocs2, syms, query)
    if cfg == 'C3':
        return rank(get_bm('C3', sdocs3), sdocs3, syms, query)
    if cfg == 'C4':
        r1 = rank(get_bm('C1', fdocs), fdocs, fmods, query)
        r2 = rank(get_bm('C2', sdocs2), sdocs2, syms, query)
        rrf = defaultdict(float)
        for ranks in (r1, r2):
            for i, s in enumerate(ranks[:60]):
                rrf[s] += 1.0 / (60 + i + 1)
        return sorted(rrf, key=lambda s: -rrf[s])
    raise ValueError(cfg)
