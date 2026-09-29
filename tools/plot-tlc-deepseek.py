"""Export real-model comparison; run after report-tlc-deepseek.py."""
import json
import os
from pathlib import Path
import statistics as st
import sys

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'target/matplotlib-cache'))
sys.path.insert(0,str(ROOT/'target/plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

r=json.loads((ROOT/'docs/deepseek-real-validation.json').read_text(encoding='utf-8'))
assert r['completed_cells']==48
fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
colors=['#75808A','#1B7A80','#DC9B45','#6951AD']
for i,mode in enumerate('BDML'):
    x=next(v for v in r['check_summary'] if v['mode']==mode and not v['probe'] and v['subset']=='deployment')['saving_pct']
    m=x['mean'];lo,hi=x['ci95']
    axes[0].bar(i,m,color=colors[i])
    axes[0].errorbar(i,m,yerr=[[m-lo],[hi-m]],color='black',capsize=4)
    axes[0].text(i,m+3,f'{m:.1f}%',ha='center',fontsize=10)
axes[0].set(xticks=range(4),xticklabels=['Fixed','Statistics','Mock','DeepSeek'],ylim=(-5,108),
            ylabel='Check execution cost reduction (%)',title='Deployment window: no key probe required')
for offset,study in [(-.18,'cache-on'),(.18,'cache-off')]:
    vals=[st.mean(x['wall_seconds'] for x in r['main'] if x['study']==study and x['mode']==m) for m in 'BDML']
    axes[1].bar([i+offset for i in range(4)],vals,width=.36,label=study,color='#1B7A80' if offset<0 else '#DC9B45')
axes[1].set(xticks=range(4),xticklabels=['Fixed','Statistics','Mock','DeepSeek'],
            ylabel='Mean end-to-end wall time (seconds)',title='Business workload including model proposal wait')
axes[1].legend(frameon=False)
for ax in axes:
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
fig.suptitle('Real DeepSeek Flash / max | NYC TLC 5.97M trips | Four rounds',fontsize=13)
fig.supxlabel('Left: gross check-only savings, excluding observation and model cost. Right: synchronous experiment, not background service.',fontsize=9)
for ext in ['png','svg']: fig.savefig(ROOT/f'docs/figures/deepseek-validation.{ext}',dpi=180)
