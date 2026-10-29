#!/usr/bin/env python3
"""Audit complete matched cells and export data for three non-redundant plots.

No selection by performance: every planned cell is listed, every session of an
included cell is retained, and reference fallbacks keep their incurred costs.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time

HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE/'protocol.json').read_text())
ARMS=CONFIG['evaluation']['arms']
DATASETS=CONFIG['evaluation']['datasets']


def read_json(path):
    # The live harness writes snapshots in place. A reader may hit that narrow
    # window; retry a short time instead of treating it as a completed record.
    for attempt in range(3):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            if attempt == 2: raise
            time.sleep(.1)


def read_cell(root,arm,ds):
    path=root/f'{arm}-{ds}-r1'
    result={'arm':arm,'dataset':ds,'status':'not_started','issues':[],'sessions':[]}
    if not path.exists(): return result
    if not (path/'run.json').exists():
        result['status']='running_or_failed_before_first_cutoff'
        return result
    run=read_json(path/'run.json')
    result['status']='complete' if run.get('finished') and not run.get('error') else 'incomplete'
    if run.get('error'): result['issues'].append(run['error'])
    refs={(t,c['k']):v for c in run['cutoffs'] if isinstance(c,dict) for t,v in c.get('reference',{}).items()}
    for p in sorted((path/'sessions').glob('*.json')):
        if p.name.endswith('.partial.json'): continue
        r=read_json(p)
        ev=r.get('eval') or {}
        audit=(r.get('audit') or {}).get('result')
        valid=bool(r.get('final_sql') and audit=='clean' and ev.get('test') is not None)
        fallback_reason=(None if valid else 'no_query' if not r.get('final_sql')
                         else 'audit_not_clean' if audit!='clean'
                         else 'evaluation_error' if ev.get('error')
                         else 'evaluation_pending' if ev.get('pending') else 'missing_test_score')
        ref=refs.get((r['task'],r['k']),{})
        test=ev.get('test') if valid else ref.get('test')
        if test is None: result['issues'].append(f'{p.name}: no final or reference test score')
        if r.get('error'): result['issues'].append(f"{p.name}: {r['error']}")
        lr=r.get('learning') or {}
        if lr.get('error'): result['issues'].append(f"{p.name}: memory operation: {lr['error']}")
        counts=r['totals'].get('tool_calls_by_category',{})
        events=lr.get('events') or []
        names=[x.get('name') for x in r.get('tools',[])]
        tokens=r['totals']['tokens_with_learning']
        assert tokens==r['totals']['tokens']+r['totals']['learn_tokens'],p
        result['sessions'].append({
            'task':r['task'],'k':r['k'],'metric':r['metric'],'higher_is_better':r['higher_is_better'],
            'test':test,'quality_source':'final_sql' if valid else 'entity_reference',
            'fallback_reason':fallback_reason,'evaluation_error':ev.get('error'),
            'valid':valid,'audit':audit,'stop':r.get('stop'),'tokens':tokens,
            'agent_tokens':r['totals']['tokens'],'learn_tokens':r['totals']['learn_tokens'],
            'llm_calls':r['totals']['llm_calls'],'tool_calls':r['totals']['tool_calls'],
            'schema':counts.get('schema',0),'probe':counts.get('probe',0),
            'validate':counts.get('validate',0),'memory':counts.get('memory',0),'submit':counts.get('submit',0),
            'memory_tools':{name:names.count(name) for name in ('find_program','find_features','compose_features')},
            'drafts':len(events),'definitions_promoted':sum(e.get('event')=='promoted' for e in events),
            'definitions_corroborated':sum(e.get('event')=='corroborated' for e in events),
            'rejected_gates':{gate:sum(e.get('failed_gate')==gate for e in events) for gate in ('F1','F2','F3','F4')},
            'program_saved':bool(lr.get('program')),'learning_skipped':lr.get('skipped'),
            'agent_seconds':r.get('agent_seconds',0),'learn_seconds':r['totals'].get('learn_seconds',0),
            'source':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    support={(r['task'],r['k']) for r in result['sessions']}
    expected_k=set(CONFIG['evaluation']['cutoffs'])
    tasks={r['task'] for r in result['sessions']}
    expected={(t,k) for t in tasks for k in expected_k}
    if support != expected or len(tasks)!=3 or len(result['sessions'])!=len(expected):
        result['issues'].append('The expected three tasks at every planned cutoff are not all present exactly once.')
    if result['status']=='complete' and result['issues']:
        result['status']='complete_with_issues'
    result['settings']=run.get('settings') or {}
    return result


def task_quality(rows):
    return {task:{'metric':xs[0]['metric'],'higher_is_better':xs[0]['higher_is_better'],
                  'mean':statistics.mean(r['test'] for r in xs),
                  'per_cutoff':[{'k':r['k'],'score':r['test'],'source':r['quality_source']}
                                for r in sorted(xs,key=lambda x:x['k'])]}
            for task in sorted({r['task'] for r in rows})
            for xs in [[r for r in rows if r['task']==task]]}


def summarize(rows):
    reuse=[r for r in rows if r['k']>1]
    return {'n':len(rows),'valid':sum(r['valid'] for r in rows),
            'fallback_counts':dict(Counter(r['fallback_reason'] for r in rows if r['fallback_reason'])),
            'tokens':sum(r['tokens'] for r in rows),'reuse_tokens':sum(r['tokens'] for r in reuse),
            'learn_tokens':sum(r['learn_tokens'] for r in rows),
            'agent_seconds':sum(r['agent_seconds'] for r in rows),
            'learn_seconds':sum(r['learn_seconds'] for r in rows),
            'mechanism':{'memory_tools':{name:sum(r['memory_tools'][name] for r in rows)
                                        for name in ('find_program','find_features','compose_features')},
                         'drafts':sum(r['drafts'] for r in rows),
                         'definitions_promoted':sum(r['definitions_promoted'] for r in rows),
                         'definitions_corroborated':sum(r['definitions_corroborated'] for r in rows),
                         'programs_saved':sum(r['program_saved'] for r in rows),
                         'rejected_gates':{gate:sum(r['rejected_gates'][gate] for r in rows) for gate in ('F1','F2','F3','F4')}},
            'reuse_mean_calls':{k:statistics.mean(r[k] for r in reuse) for k in ('schema','probe','validate','memory','submit','llm_calls')},
            'quality':task_quality(rows),'reuse_quality':task_quality(reuse),
            'reuse_n':len(reuse),'reuse_valid':sum(r['valid'] for r in reuse)}


def analyze(root):
    cells=[read_cell(root,a,d) for d in DATASETS for a in ARMS]
    out={'generated_utc':datetime.now(timezone.utc).isoformat(),'protocol':CONFIG,'cells':cells,'comparisons':{}}
    for name in ('status','budget-state','selection','build-provenance','timeout-audit'):
        if (root/(name+'.json')).exists(): out[name]=read_json(root/(name+'.json'))
    for ds in DATASETS:
        complete={c['arm']:c for c in cells if c['dataset']==ds and c['status']=='complete'}
        # Keep a complete control comparison available for diagnostics. It is
        # not a published-method result unless that flag is also true.
        if not {'mavra','none'}<=complete.keys(): continue
        support={(r['task'],r['k']) for r in complete['none']['sessions']}
        assert all({(r['task'],r['k']) for r in c['sessions']}==support for c in complete.values())
        sums={a:summarize(c['sessions']) for a,c in complete.items()}
        baseline=sums['none']
        for a,s in sums.items():
            s['token_saving_vs_none_pct']=100*(1-s['tokens']/baseline['tokens'])
            s['reuse_token_saving_vs_none_pct']=100*(1-s['reuse_tokens']/baseline['reuse_tokens'])
            for phase in ('quality','reuse_quality'):
                for task,q in s[phase].items():
                    ref=baseline[phase][task]['mean']
                    q['within_margin_vs_none']=q['mean']>=ref-.01 if q['higher_is_better'] else q['mean']<=ref*1.02
        out['comparisons'][ds]={'complete_method_set':set(complete)==set(ARMS),
                                'has_published_baseline':bool(set(complete)&{'ace','awm','gmemory'}),
                                'arms':sums}
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('results/official-20261028'))
    p.add_argument('--out',type=Path,default=HERE)
    a=p.parse_args()
    report=analyze(a.root)
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'analysis.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    lines=['# Official API experiment status and results','',
           'All scheduled cells are shown. Only complete matched cells enter comparisons. A single sequence does not establish statistical significance.','',
           '| Dataset | Method | Status | Sessions | Issues |','|---|---|---|---:|---:|']
    budget=report.get('budget-state',{})
    if budget:
        lines[4:4]=[f"Queue stage: {report.get('status',{}).get('status','unknown')}. API calls: {budget.get('calls')}. "
                    f"Conservative spending bound: CNY {budget.get('ceiling_cny',0):.3f}; "
                    f"last observed account decrease: CNY {budget.get('observed_account_decrease_cny',0):.2f}; "
                    f"authorized cap: CNY {CONFIG['budget_cny']:.2f}.",'']
    for c in report['cells']:
        lines.append(f"| {c['dataset']} | {c['arm']} | {c['status']} | {len(c['sessions'])}/9 | {len(c['issues'])} |")
    for ds,comp in report['comparisons'].items():
        lines += ['',f'## {ds}', '',f"Complete five-method set: {comp['complete_method_set']}. Published comparison available: {comp['has_published_baseline']}.", '',
                  '| Method | All tokens (M) | Reuse tokens (M) | Valid | Quality within stated margins |',
                  '|---|---:|---:|---:|---:|']
        for arm,s in comp['arms'].items():
            good=sum(q['within_margin_vs_none'] for q in s['quality'].values())
            lines.append(f"| {arm} | {s['tokens']/1e6:.3f} | {s['reuse_tokens']/1e6:.3f} | {s['valid']}/{s['n']} | {good}/3 |")
        lines += ['', 'Quality by task and phase (the all-cutoff result is retained; reuse is the predeclared cutoffs 2-3):','',
                  '| Method | Task | Metric | All cutoffs | Reuse cutoffs | All within margin | Reuse within margin |',
                  '|---|---|---|---:|---:|---|---|']
        for arm,s in comp['arms'].items():
            for task,q in s['quality'].items():
                reuse=s['reuse_quality'][task]
                lines.append(f"| {arm} | {task} | {q['metric']} | {q['mean']:.6f} | {reuse['mean']:.6f} | {q['within_margin_vs_none']} | {reuse['within_margin_vs_none']} |")
        mechanism=comp['arms']['mavra']['mechanism']
        lines += ['', 'MAVRA mechanism audit (whole-program reuse and structured-feature reuse must not be conflated):',
                  '', '```json',json.dumps(mechanism,indent=2),'```']
    (a.out/'analysis.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'cells':{c['dataset']+'/'+c['arm']:c['status'] for c in report['cells']},
                      'comparison_datasets':list(report['comparisons'])},indent=2))


if __name__=='__main__': main()
