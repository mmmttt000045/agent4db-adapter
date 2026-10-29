#!/usr/bin/env python3
"""Figures B/C: archival measurements only; no interpolation or invented CIs."""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/figures'))
import mplstyle
import style
ARCHIVE = ROOT / 'exp/2026-10-02-cache-baseline-tpcds'
OUT = ROOT / 'output/mechanism-pilot-20261029'
OUT.mkdir(parents=True, exist_ok=True)
mplstyle.setup('en')
COLORS = {key: mplstyle.color(key) for key in ('definition', 'definition-cache', 'condition')}
LABELS = {'definition': 'Full recheck', 'definition-cache': 'SQL/version cache', 'condition': 'MAVRA'}
MARKS = {'definition': 's', 'definition-cache': '^', 'condition': 'o'}
LINES = {'definition': ':', 'definition-cache': '--', 'condition': '-'}
HATCHES = {'definition': '//', 'definition-cache': '..', 'condition': '\\\\'}
evidence = {'purpose': 'Archived-data previews; not new experiments', 'sources': {}, 'figures': {}}


def read(name):
    p = ARCHIVE / name
    evidence['sources'][name] = {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    return json.loads(p.read_text(encoding='utf-8'))


def save(fig, name):
    fig.savefig(OUT / (name + '.pdf'), facecolor='white')
    fig.savefig(OUT / (name + '.png'), dpi=220, facecolor='white')
    plt.close(fig)


def figure_b():
    rows = read('cb-1m-share-stats.json')['rows']
    zero = read('cb-1m-zero-stats.json')['rows']
    eight = read('cb-4m-stats.json')['rows']
    thirtytwo = read('e1b-4m-a32-stats.json')['rows']
    fig = mplstyle.figure(178, 133)
    axes = fig.subplots(2, 2)
    fig.subplots_adjust(top=.83, bottom=.21, left=.085, right=.98, hspace=.62, wspace=.31)
    for ax, arrival, panel in zip(axes[0], ('staggered', 'burst'), ('a', 'b')):
        for policy in COLORS:
            pts = sorted([x for x in rows if x['arrival'] == arrival and x['policy'] == policy], key=lambda x:x['specs'])
            ax.plot([x['specs'] for x in pts], [x['db_s'] for x in pts], marker=MARKS[policy],
                    color=COLORS[policy], label=LABELS[policy], linewidth=.9,
                    ls=LINES[policy], mfc='white', mew=.6)
        ax.set(title=f'({panel}) '+('Staggered arrivals' if arrival == 'staggered' else 'Simultaneous arrivals'),
               xlabel='Definitions (overlap also varies)', ylabel='Maintenance DB time (s)', ylim=(0,None), xticks=[4,8,15,19])
        ax.grid(axis='y')
    ax = axes[1,0]
    for j, policy in enumerate(COLORS):
        vals = [100 * next(x['vs_definition'] for x in zero if x['arrival'] == arrival and x['policy'] == policy)
                for arrival in ('staggered','burst')]
        ax.bar(np.arange(2)+(j-1)*.23, vals, width=.22, **mplstyle.bar_style(policy, HATCHES[policy]))
    ax.axhline(100,color='#555555',ls=':',lw=.8)
    ax.set(title='(c) Zero-overlap control', xticks=[0,1], xticklabels=['Staggered','Simultaneous'],
           ylabel='DB time / full recheck (%)', ylim=(0,120))
    ax.grid(axis='y')
    ax = axes[1,1]
    selected = []
    for policy in ('definition-cache','condition'):
        for arrival, ls in [('staggered','-'),('burst','--')]:
            pts = [next(x for x in dataset if x['policy'] == policy and x['arrival'] == arrival)
                   for dataset in (eight, thirtytwo)]
            ax.plot([8,32],[100*x['vs_definition'] for x in pts], marker=MARKS[policy],color=COLORS[policy],ls=ls,
                    linewidth=.9,mfc='white',mew=.6,label=LABELS[policy]+(' / stag.' if arrival=='staggered' else ' / simult.'))
            selected.extend(pts)
    ax.axhline(100,color='#555555',ls=':',lw=.8)
    ax.set(title='(d) Agents: 4M rows, 19 definitions',xlabel='Agents',ylabel='DB time / full recheck (%)',
           xticks=[8,32],ylim=(0,115))
    ax.text(19,26,'solid: staggered\ndashed: simultaneous',fontsize=6.5)
    ax.grid(axis='y')
    handles, labels = axes[0,0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center',bbox_to_anchor=(.53,.925),ncol=3,frameon=False,handlelength=2.8)
    fig.suptitle('Figure B: Sharing benefit and its limits (archived-data preview)',y=.985,fontsize=9)
    fig.text(.085,.055,'One run per configuration; no confidence intervals. Panels (a-c): 1M rows, 8 agents.\n'
             'Definition count and overlap co-vary. Panel (d) uses separate 4M-row runs.\n'
             'A fixed-definition overlap experiment is still required.',fontsize=6.5,color='black')
    evidence['figures']['B'] = {'sharing': rows,'zero_overlap':zero,'agent_comparison':selected,
        'limitations':['single run per configuration','definition count and overlap co-vary','separate size/agent cohorts']}
    save(fig,'figure-b-archive-preview')


def figure_c(controlled=False):
    stats = read('snapshot-binding-stats.json')
    raw = read('snapshot-binding-report.json')
    shards = read('snapshot-binding-shards-stats.json')
    fig = mplstyle.figure(178, 138)
    grid = fig.add_gridspec(2,2,top=.84,bottom=.22,left=.085,right=.98,hspace=.85,wspace=.32)
    ax = fig.add_subplot(grid[0,:])
    if controlled:
        p=OUT/'system-analysis.json'
        new=json.loads(p.read_text(encoding='utf-8'))['C']
        assert new['complete']
        evidence['sources']['matched-system-analysis']={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        cases=['benign_after_check','violation_after_check','violation_before_call']
        groups=[[{**next(r for r in new['groups'] if r['case']==case and r['mode']==mode),'calls':5}
                 for mode in ['tx-precheck','tx-bound']] for case in cases]
        group_labels=['Benign commit\nafter validation','Violating commit\nafter validation','Violating commit\nbefore invocation']
        top_title='(a) Controlled interleavings with the same transactional version source'
    else:
        combos = [(False,False),(False,True),(True,False),(True,True)]
        groups=[[next(r for r in stats['stress'] if r['notify']==notify and r['distinct']==distinct and r['mode']==mode)
                 for mode in ('precheck','snapshot')] for notify,distinct in combos]
        group_labels=['Unannounced\nsame month','Unannounced\ndifferent months','Announced\nsame month','Announced\ndifferent months']
        top_title='(a) Concurrent outcomes: 20 windows per configuration'
    outcomes = [('served',style.OUT_CORRECT,'','Condition-valid return'),
                ('violation',style.WRONG,'xx','Condition-violating return'),
                ('rejected',style.OUT_UNNEEDED,'//','Refused')]
    plotrows = []
    assert not any(row.get('error',0) for group in groups for row in group), 'Add error category before plotting failed calls'
    for i,group in enumerate(groups):
        for j,row in enumerate(group):
            x = i*2.5+j*.85
            bottom=0
            for key,color,hatch,label in outcomes:
                val = row[key] if controlled else row[key]/row['calls']*100
                ax.bar(x,val,width=.7,bottom=bottom,color=color,label=label if i==j==0 else None,
                       edgecolor='black',linewidth=.4,hatch=hatch)
                bottom += val
            ax.text(x,5.2 if controlled else 104,f"n={row['calls']}",ha='center',fontsize=6.3)
            plotrows.append(row)
    ax.set_xticks([i*2.5+j*.85 for i in range(len(groups)) for j in range(2)])
    ax.set_xticklabels(['Pre','Bound']*len(groups),fontsize=7)
    ax.set(ylabel='Controlled calls' if controlled else 'All requests (%)',
           ylim=(0,5.75) if controlled else (0,115),yticks=range(6) if controlled else [0,25,50,75,100],title=top_title)
    ax.grid(axis='y')
    for i,label in enumerate(group_labels):
        ax.text(i*2.5+.425,-1.1 if controlled else -22,label,ha='center',va='top',fontsize=7)
    fig.legend(*ax.get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.54,.925),ncol=3,frameon=False)
    ax = fig.add_subplot(grid[1,0])
    for j,mode in enumerate(('precheck','snapshot')):
        vals = [stats['reader_p50_ms'][mode][k] for k in ('steady_ms','first_after_write_ms','second_after_write_ms')]
        pos = np.arange(3)+(j-.5)*.3
        policy = ['definition','condition'][j]
        ax.bar(pos,vals,.28,label=['Legacy precheck' if controlled else 'Precheck','Snapshot-bound'][j],
               **mplstyle.bar_style(policy,HATCHES[policy]))
        for x,y in zip(pos,vals):
            ax.text(x,y*1.16,f'{y:g}',ha='center',fontsize=6.3)
    ax.set(title='(b) Legacy reader latency' if controlled else '(b) Single-reader latency',ylabel='Mean of run medians (ms, log)',yscale='log',ylim=(1,5000),
           xticks=[0,1,2],xticklabels=['Steady','First after\nbenign write','Second after\nbenign write'])
    ax.legend(loc='upper right',frameon=False,fontsize=6.3)
    ax.grid(axis='y')
    ax = fig.add_subplot(grid[1,1])
    keys = ['sequential_stmt_per_s','concurrent8_stmt_per_s','concurrent32_stmt_per_s']
    for mode,color,marker,label in [('shards1',COLORS['definition'],'s','One version row'),('shards16',COLORS['condition'],'o','16 version shards')]:
        vals=[shards['writer_median'][mode][k]/shards['writer_median']['no_trigger'][k]*100 for k in keys]
        ax.plot([1,8,32],vals,color=color,marker=marker,label=label,mfc='white',mew=.6,
                ls='--' if mode=='shards1' else '-')
    ax.axhline(100,color='#555555',ls=':',lw=.8)
    ax.set(title='(c) Archived writer throughput' if controlled else '(c) Writer throughput cost',ylabel='Throughput / no version trigger (%)',xlabel='Writer connections',
           xticks=[1,8,32],ylim=(0,115))
    ax.legend(frameon=False,loc='lower left',fontsize=6.3)
    ax.grid(axis='y')
    fig.suptitle('Figure C: Matched snapshot safety and archived overhead' if controlled else
                 'Figure C: Snapshot safety and system overhead (archived-data preview)',y=.985,fontsize=9)
    note=('Panel (a): new controlled schedules, five calls per mode/case, with identical transactional version sources.\n'
          'Panels (b,c): archived reader/writer cohorts; the legacy reader comparison also changes the version source.\n'
          'Reader: mean of two run medians. Writer: median of three runs.\n'
          'Different cohorts: these panels do not estimate a natural-workload safety/throughput tradeoff.' if controlled else
          'Separate cohorts: (a) concurrent stress; (b) two reader runs; (c) three writer runs.\n'
             'Pre = original precheck; Bound = same-snapshot validation. Version sources also differ.\n'
             'Zero observed violations is not universal safety; writer rates are not controlled here.')
    fig.text(.085,.055,note,fontsize=6.5,color='black')
    evidence['figures']['C']={'outcomes':plotrows,'reader_p50_ms':stats['reader_p50_ms'],
        'reader_runs':[{k:r[k] for k in ('mode','steady_ms','first_after_write_ms','second_after_write_ms')} for r in raw['reader_overhead']],
        'writer_medians':shards['writer_median'],
        'limitations':['version-source confound in historical precheck','different reader/writer measurement cohorts',
                      'requests within concurrency windows are dependent','not writer-rate scan']}
    if controlled:
        evidence['figures']['C']['safety_panel']='new matched version-source control'
        evidence['figures']['C']['limitations']=['legacy reader version-source confound in panel (b)',
            'different reader/writer cohorts','controlled safety schedules are not natural violation rates','not writer-rate scan']
        fig.savefig(OUT/'figure-c-combined-preview.png',dpi=250,facecolor='white')
        fig.savefig(OUT/'figure-c-combined-preview.pdf',facecolor='white')
        fig.savefig(OUT/'figure-c-combined-preview.svg',facecolor='white')
        plt.close(fig)
    else:
        save(fig,'figure-c-archive-preview')


if __name__=='__main__':
    if '--controlled-c' in sys.argv:
        figure_c(controlled=True)
        name='combined-c-evidence.json'
    else:
        figure_b()
        figure_c()
        name='archive-preview-evidence.json'
    (OUT/name).write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(str(OUT))
