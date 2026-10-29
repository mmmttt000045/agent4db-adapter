#!/usr/bin/env python3
"""Paired three-block system summaries; raw ranges are not confidence intervals."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import statistics as st
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE=ROOT/'results/mechanism-systems-20261029'
OUT=ROOT/'output/mechanism-pilot-20261029'
sys.path.insert(0,str(ROOT/'tools/figures'))
import mplstyle
import style
from matplotlib import pyplot as plt

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def interval(xs):return {'n':len(xs),'median':st.median(xs),'min':min(xs),'max':max(xs),'raw':xs}

data={'kind':'new controlled supplements; separate from archival previews','B':{},'C':{},'sources':{}}
reports={}
for kind in ['B','C']:
    for p in sorted(BASE.glob(kind+'-*/report.json')):
        r=read(p)
        data['sources'][str(p.relative_to(ROOT))]={'sha256':sha(p),'cleaned_up':r.get('cleaned_up')}
        if r.get('report',{}).get('error'):
            data[kind].setdefault('failed_attempts',[]).append(r['report'])
        else:
            assert kind not in reports, 'Multiple successful reports need an explicit inclusion rule'
            reports[kind]=r['report']

if 'C' in reports:
    rows=reports['C']['rows']
    groups=[]
    for case in ['benign_after_check','violation_after_check','violation_before_call']:
        for mode in ['tx-precheck','tx-bound']:
            rs=[r for r in rows if r['case']==case and r['mode']==mode]
            groups.append({'case':case,'mode':mode,'n':len(rs),
                **{k:sum(r['outcome']==k for r in rs) for k in ['served','violation','rejected','error']}})
    gate=(len(rows)==30 and all(g['n']==5 and not g['error'] for g in groups)
          and all(not g['violation'] for g in groups if g['mode']=='tx-bound')
          and all(g['rejected']==5 for g in groups if g['case']=='violation_before_call')
          and all(g['served']==5 for g in groups if g['case']=='benign_after_check')
          and all(g['violation']==5 for g in groups if g['mode']=='tx-precheck' and g['case']=='violation_after_check'))
    data['C'].update(complete=len(rows)==30,groups=groups,gate_passed=gate,
        limits=['controlled interleavings; no natural violation-rate estimate',
                'artificial barrier time excluded from performance claims','same transactional version source in both modes'])

if 'B' in reports:
    cells=reports['B']['cells']
    assert len({(c['repeat'],c['reuse_factor'],c['policy'],c['arrival']) for c in cells})==len(cells)
    expected={(r,k,p,a) for r in range(3) for k in [1,2,4,8]
              for p in ['definition','definition-cache','condition'] for a in ['staggered','burst']}
    observed={(c['repeat'],c['reuse_factor'],c['policy'],c['arrival']) for c in cells}
    assert observed <= expected, 'Unexpected experiment cell'
    assert all(c['definitions']==16 and c['agents']==8 and c['rows_per_fact']==100000
               and len(c['uses'])==128 for c in cells), 'Protocol or request count mismatch'
    extra_refresh=[]
    for c in cells:
        events=[e for e in c['events'] if e['event']=='maintenance']
        counts=Counter(e['key'] for e in events)
        if counts and max(counts.values())>1:
            extra_refresh.append({**{k:c[k] for k in ['repeat','reuse_factor','policy','arrival']},
                'maintenance_events':len(events),'refreshes_per_key':dict(counts),
                'interpretation':'Observed a second refresh for the same definitions; retained without exclusion. '
                    'The version counter sequence was not recorded, so the cause is not established.'})
    groups=[]
    for arrival in ['staggered','burst']:
        for reuse in [1,2,4,8]:
            for policy in ['definition','definition-cache','condition']:
                rs=sorted([r for r in cells if r['arrival']==arrival and r['reuse_factor']==reuse and r['policy']==policy],key=lambda r:r['repeat'])
                if not rs:continue
                bases=[next(b for b in cells if b['arrival']==arrival and b['reuse_factor']==reuse and b['repeat']==r['repeat'] and b['policy']=='definition') for r in rs]
                counts=lambda r:sum(r['db']['by_kind'][k][0] for k in ['check','guard','metric'])
                groups.append({'arrival':arrival,'reuse_factor':reuse,'policy':policy,
                    'db_ms':interval([r['db']['db_ms'] for r in rs]),
                    'paired_db_ratio':interval([r['db']['db_ms']/b['db']['db_ms'] for r,b in zip(rs,bases)]),
                    'validation_queries':interval([counts(r) for r in rs]),
                    'wall_seconds':interval([r['wall_seconds'] for r in rs]),
                    'unavailable':sum(r['unavailable'] for r in rs),
                    'requests':sum(len(r['uses']) for r in rs)})
    data['B'].update(complete=observed==expected,groups=groups,extra_refresh_cells=extra_refresh,
        unavailable=sum(r['unavailable'] for r in cells),requests=sum(len(r['uses']) for r in cells),
        limits=['three randomized run blocks; error bars show min-max, not confidence intervals',
                'exact shared checks; no claim of semantic subsumption','active table working set shrinks with reuse',
                'both fact and date versions change; no unchanged-dimension skip benefit',
                'one zero-overlap SQL-cache cell refreshed all definitions twice; retained in the range',
                'legacy versions include asynchronous DML counters; the cause of the second refresh is unresolved'])

OUT.mkdir(parents=True,exist_ok=True)
for p in [OUT/'system-analysis.json',HERE/'system-summary.json']:
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

if data['B'].get('complete'):
    mplstyle.setup('en')
    fig=mplstyle.figure(178,133);axes=fig.subplots(2,2,sharey='row')
    fig.subplots_adjust(left=.10,right=.98,top=.82,bottom=.19,hspace=.52,wspace=.30)
    marks={'definition':'s','definition-cache':'^','condition':'o'}
    lines={'definition':':','definition-cache':'--','condition':'-'}
    names={'definition':'Full recheck','definition-cache':'SQL/version cache','condition':'MAVRA'}
    for col,arrival in enumerate(['staggered','burst']):
        for policy in marks:
            pts=[next(r for r in data['B']['groups'] if r['arrival']==arrival and r['policy']==policy and r['reuse_factor']==k) for k in [1,2,4,8]]
            for row,metric,mult in [(0,'paired_db_ratio',100),(1,'validation_queries',1)]:
                vals=[r[metric]['median']*mult for r in pts]
                errs=[[r[metric]['median']*mult-r[metric]['min']*mult for r in pts],
                      [r[metric]['max']*mult-r[metric]['median']*mult for r in pts]]
                axes[row,col].errorbar([1,2,4,8],vals,yerr=errs,color=mplstyle.color(policy),
                    marker=marks[policy],ls=lines[policy],mfc='white',mew=.6,capsize=2,elinewidth=.6,label=names[policy])
        for row in [0,1]:
            ax=axes[row,col]
            ax.set(title=f"({'abcd'[row*2+col]}) "+('Staggered arrivals' if col==0 else 'Simultaneous arrivals'),
                   xlabel='Definitions per shared table pair',xticks=[1,2,4,8],ylim=(0,None))
            ax.set_ylabel('DB time / paired full recheck (%)' if row==0 else 'Validation SQL queries')
            ax.tick_params(axis='y',labelleft=True)
            ax.grid(axis='y')
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.925),ncol=3,handlelength=2.7)
    fig.suptitle('Figure B supplement: Fixed 16 definitions, varying exact check sharing',fontsize=9,y=.985)
    fig.text(.10,.05,'100K rows per fact table; 8 agents; 128 requests per cell. Both fact and date tables are invalidated.\n'
             'Three randomized run blocks. Points: medians; error bars: full observed ranges, not confidence intervals.\n'
             'The active table set shrinks with sharing. One zero-overlap SQL-cache run refreshed twice; it is retained.',fontsize=6.5)
    fig.savefig(OUT/'figure-b-controlled.png',dpi=250,facecolor='white')
    fig.savefig(OUT/'figure-b-controlled.pdf',facecolor='white')
    fig.savefig(OUT/'figure-b-controlled.svg',facecolor='white');plt.close(fig)

if data['C'].get('complete'):
    mplstyle.setup('en')
    fig=mplstyle.figure(178,73);ax=fig.add_subplot()
    fig.subplots_adjust(left=.09,right=.98,top=.73,bottom=.30)
    cases=['benign_after_check','violation_after_check','violation_before_call']
    for i,case in enumerate(cases):
        for j,mode in enumerate(['tx-precheck','tx-bound']):
            g=next(r for r in data['C']['groups'] if r['case']==case and r['mode']==mode)
            bottom=0
            for key,color,hatch,label in [('served',style.OUT_CORRECT,'','Condition-valid'),('violation',style.WRONG,'xx','Condition-violating'),('rejected',style.OUT_UNNEEDED,'//','Refused'),('error','#FFFFFF','++','Error')]:
                if key=='error' and not any(x['error'] for x in data['C']['groups']):continue
                ax.bar(i*2.6+j*.9,g[key],bottom=bottom,width=.70,color=color,hatch=hatch,edgecolor='black',lw=.4,label=label if i==j==0 else None)
                bottom+=g[key]
    ax.set(xticks=[i*2.6+j*.9 for i in range(3) for j in range(2)],xticklabels=['Pre','Bound']*3,
           yticks=range(6),ylim=(0,5.8),ylabel='Controlled calls (n = 5)')
    ax.grid(axis='y')
    for i,label in enumerate(['Benign commit\nafter validation','Violating commit\nafter validation','Violating commit\nbefore invocation']):
        ax.text(i*2.6+.45,-1.0,label,ha='center',va='top',fontsize=7)
    fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.88),ncol=4)
    fig.suptitle('Figure C supplement: Same transactional versions, different snapshot lifetime',fontsize=9,y=.985)
    fig.text(.09,.025,'Deterministic two-way barriers establish ordering. These counts are not natural workload violation rates or performance measurements.',fontsize=6.5)
    fig.savefig(OUT/'figure-c-controlled.png',dpi=250,facecolor='white');plt.close(fig)

print(json.dumps({k:{x:v for x,v in data[k].items() if x in ['complete','gate_passed','unavailable','requests','failed_attempts']} for k in ['B','C']}))
