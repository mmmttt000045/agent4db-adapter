#!/usr/bin/env python3
"""Plot the development pilot, including missing solutions and setup cost."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/figures'))
import mplstyle
import style
from matplotlib import pyplot as plt, colors
from matplotlib.patches import Patch

OUT=ROOT/'output/mechanism-pilot-20261029'
d=json.loads((OUT/'pilot-analysis.json').read_text(encoding='utf-8'))
assert d['complete'], 'A pilot plot must include all eight completed cells'
mplstyle.setup('en')
arms=['none','program','definition','full']
labels=['None','Program','Definition','Both']
palette={a:style.PAPER_COLORS[c] for a,c in zip(arms,['mNoShare','mTraj','mCondCur','mCond'])}
fig=mplstyle.figure(178,132)
axs=fig.subplots(2,2)
fig.subplots_adjust(left=.095,right=.98,top=.85,bottom=.22,hspace=.55,wspace=.27)
for col,(target,title) in enumerate([('cross-task','Cross-task: user-engagement k1'),('same-task-later','Later cutoff: user-badge k2')]):
    rs=[next(r for r in d['rows'] if r['target']['name']==target and r['arm']==a) for a in arms]
    ax=axs[0,col]
    for i,r in enumerate(rs):
        if r['valid']:
            ax.plot(i,r['validation_auc'],marker=['^','s','D','o'][i],color=palette[r['arm']],mfc='white',mew=.8,ms=4)
            ax.text(i,r['validation_auc']+.017,f"{r['validation_auc']:.3f}",ha='center',fontsize=6.5)
        else:
            ax.text(i,.59,'No valid\nsolution',ha='center',fontsize=6.5)
    base=rs[0]
    if base['valid']:ax.axhline(base['validation_auc']-.01,color='black',lw=.6,ls='--')
    ax.set(title=f"({'ab'[col]}) {title}",ylabel='Validation AUC',xticks=range(4),xticklabels=labels,
           xlim=(-.5,3.5),ylim=(.55,1))
    ax.grid(axis='y')
    ax=axs[1,col]
    for i,r in enumerate(rs):
        rgb=colors.to_rgb(palette[r['arm']]);fill=tuple(.35*x+.65 for x in rgb)
        online=r['agent_tokens']/1000;source=r['historical_source_allocated_tokens']/1000;extract=r['new_extraction_allocated_tokens']/1000
        ax.bar(i,online,.6,color=fill,edgecolor='black',linewidth=.4)
        ax.bar(i,source,.6,bottom=online,color='white',hatch='//',edgecolor='black',linewidth=.4)
        ax.bar(i,extract,.6,bottom=online+source,color='#D4D4D4',hatch='xx',edgecolor='black',linewidth=.4)
        ax.text(i,online+source+extract+5,f'{online+source+extract:.0f}',ha='center',fontsize=6.5)
    ax.set(title=f"({'cd'[col]}) Cost including source setup",ylabel='Tokens (thousands)',xticks=range(4),xticklabels=labels,
           xlim=(-.5,3.5),ylim=(0,max(r['amortized_tokens']/1000 for r in d['rows'])*1.18))
    ax.grid(axis='y')
fig.suptitle('Figure A: Program access × definition access (development pilot)',fontsize=9,y=.985)
fig.legend(handles=[Patch(facecolor='#C0C0C0',edgecolor='black',linewidth=.4,label='Target session'),
                    Patch(facecolor='white',edgecolor='black',linewidth=.4,hatch='//',label='Source exploration / 2'),
                    Patch(facecolor='#D4D4D4',edgecolor='black',linewidth=.4,hatch='xx',label='Definition extraction / 2')],
           loc='upper center',bbox_to_anchor=(.53,.925),ncol=3,fontsize=7)
fig.text(.095,.065,'One run per cell; development validation only. No test-label scoring or confidence intervals.\n'
         'The dashed line is the paired no-memory AUC minus 0.01, when that control has a valid solution.\n'
         'Interrupted interface attempts remain in the study cost ledger and are reported separately.',fontsize=6.5)
fig.savefig(OUT/'figure-a-pilot.png',dpi=250,facecolor='white')
fig.savefig(OUT/'figure-a-pilot.pdf',facecolor='white')
fig.savefig(OUT/'figure-a-pilot.svg',facecolor='white')
plt.close(fig)
print(OUT/'figure-a-pilot.png')
