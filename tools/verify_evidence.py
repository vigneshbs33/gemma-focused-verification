"""New evidence verifier, 11 November 2026.
No inference, network access, model loading or benchmark/source execution.
Checks preserved records, not missing final outputs or gold-label validity.
"""
from pathlib import Path
import hashlib,json,re,collections,sys
P=Path(__file__).resolve().parent
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def need(ok,msg):
    if not ok:raise ValueError(msg)
def choice(text,candidates):
    m=re.fullmatch(r'\s*([0-5])\s*',text)
    if not m:return None,False
    n=int(m[1]);valid=n<=len(candidates)
    return (candidates[n-1] if valid and n else None),valid

def check_outputs(root):
    totals=collections.Counter()
    for f in sorted((root/'outputs').glob('*.json')):
        o=load(f);totals[o['assignment']]+=1
        need(o['prompt_tokens']<=960,f'{f.name}: prompt cap')
        need(o['peak_rss_kib']<=1536000,f'{f.name}: output RSS cap')
        st=root/'call-status'/('call-'+f.stem+'-status.json')
        need(st.exists(),f'{f.name}: missing status')
        s=load(st)
        need(s['returncode']==0 and not s['stop_reason'],f'{f.name}: governor failed')
        need(s['peak_rss_kib']<=1536000 and s['elapsed_seconds']<=90.5,f'{f.name}: governor cap')
    return dict(totals)

def check_receipts(root,current):
    count=collections.Counter()
    for f in sorted((root/'task-receipts').glob('*.json')):
        r=load(f);count[r['assignment']]+=1
        for arm,a in r['arms'].items():
            for stage in a.get('stages',[])+([a['final']] if a.get('final') else [])+a.get('scores',[]):
                cid=stage.get('call_id')
                if not cid:continue
                path=root/'outputs'/(cid+'.json');need(path.exists(),f'{cid}: no output')
                need(H(path)==stage['output_sha256'],f'{cid}: receipt hash mismatch')
                out=load(path)
                if 'score' in stage:
                    m=re.fullmatch(r'\s*([0-3])\s*',out['response']);score=int(m[1]) if m else -1
                    need(score==stage['score'],f'{cid}: score mismatch')
                    need(out['candidates']==[stage['symbol']],f'{cid}: candidate mismatch')
                else:
                    selected,valid=choice(out['response'],out['candidates'])
                    need(selected==stage['selected'] and valid==stage['valid'],f'{cid}: decision mismatch')
        if current:
            scores=r['arms']['V20']['scores'];order=[s['symbol'] for s in scores];priority={s:i for i,s in enumerate(order)}
            ranked=sorted(scores,key=lambda s:(-s['score'],priority[s['symbol']],s['symbol']))
            predicted=ranked[0]['symbol'] if ranked and ranked[0]['score']>0 else None
            need(predicted==r['arms']['V20']['selected'],f'{f.name}: V20 ranking mismatch')
            votes={s:sum(r['arms'][k]['selected']==s for k in ['T0','T1','T2','T3']) for s in order}
            best=sorted(order,key=lambda s:(-votes[s],priority[s],s))
            predicted=best[0] if votes[best[0]]>0 else None
            need(predicted==r['arms']['T20']['selected'],f'{f.name}: T20 vote mismatch')
            need(r['arms']['T5']['selected']==r['arms']['T0']['selected'],f'{f.name}: T5 reuse mismatch')
            for k in ['T0','T1','T2','T3']:
                arm=r['arms'][k]
                need(arm['selected']==arm.get('final',{}).get('selected'),f'{f.name}: tournament final mismatch')
    return dict(count)

def old_scores(root):
    results=load(root/'RESULTS.json');totals=collections.Counter()
    for row in results['per_task']:
        iid=row['instance_id'];rec=load(root/'task-receipts'/('evaluation-'+iid+'.json'));gold=load(root/'gold-bindings'/(iid+'.json'))
        for arm,stats in row['arms'].items():
            selected=rec['arms'][arm]['selected']
            correct=int(selected in set(gold['gold']))
            need(selected==stats['selected'] and correct==stats['correct'],f'{iid}: old score mismatch')
            totals[arm]+=correct
    need(dict(totals)==results['evaluation']['correct'],'earlier aggregate mismatch')
    return dict(totals)

def main():
    manifest=load(P/'MANIFEST.json')
    for name,digest in manifest.items():need(H(P/name)==digest,f'{name}: package hash mismatch')
    c=P/'current-study-captured';o=P/'earlier-study-complete'
    current_counts=check_outputs(c);current_receipts=check_receipts(c,True)
    old_counts=check_outputs(o);old_receipts=check_receipts(o,False);old_correct=old_scores(o)
    need(current_counts=={'development':480,'evaluation':786},'unexpected current snapshot output counts')
    need(current_receipts=={'development':12,'evaluation':19},'unexpected current snapshot receipt counts')
    need(old_counts=={'development':192,'evaluation':960},'unexpected earlier output counts')
    need(old_receipts=={'development':12,'evaluation':60},'unexpected earlier receipt counts')
    print(json.dumps({'pass':True,'package_files_hashed':len(manifest),'current_study_captured_outputs':current_counts,'current_study_completed_receipts_replayed':current_receipts,'earlier_study_outputs':old_counts,'earlier_study_receipts_checked':old_receipts,'earlier_study_exact_scores_recomputed':old_correct,'verification_scope':['Captured-record integrity and decision replay; no inference rerun.','Earlier-study scores recomputed from captured labels, not source/patch rebinding.','This check does not reproduce the complete current-study paper result.']},indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:print('FAIL:',str(e),file=sys.stderr);sys.exit(1)
