"""Static, exportable figure for the real-data report. Requires matplotlib."""
import json
from pathlib import Path
import sys
import os
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'target/matplotlib-cache'))
sys.path.insert(0,str(ROOT/'target/plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

r=json.loads((ROOT/'docs/real-data-validation.json').read_text(encoding='utf-8'))
groups=['A','B','C','oldD','D','M']
fig,axes=plt.subplots(1,2,figsize=(12.5,4.7),layout='constrained')
x=np.arange(len(groups));width=.36
for offset,mode,color,label in [(-width/2,'cache_on','#197D83','Result cache on'),(width/2,'cache_off','#DC9B45','Result cache off')]:
    values=[r[mode]['groups'][g]['db_seconds'] for g in groups]
    axes[0].bar(x+offset,values,width,color=color,label=label)
axes[0].set(xticks=x,xticklabels=groups,ylabel='Mean total database query time (s / round)',title='Real records: shared reuse is the main benefit')
axes[0].legend(frameon=False,fontsize=9)
axes[0].grid(axis='y',alpha=.18);axes[0].set_axisbelow(True)
labels=[];ys=[]
for i,(mode,comparison) in enumerate([('cache_on','D/B'),('cache_on','D/oldD'),('cache_off','D/B'),('cache_off','D/oldD')]):
    c=r[mode]['contrasts'][comparison];m=c['mean_percent'];lo,hi=c['ci95']
    axes[1].errorbar(m,3-i,xerr=[[m-lo],[hi-m]],fmt='o',color='#197D83' if mode=='cache_on' else '#DC9B45',capsize=4)
    labels.append(f'{comparison} / cache {"on" if mode=="cache_on" else "off"}');ys.append(3-i)
axes[1].axvline(0,color='#68747D',ls='--',lw=1)
axes[1].set(yticks=ys,yticklabels=labels,xlabel='Paired cost reduction (%) / descriptive 95% interval',title='No observed reorder: do not attribute timing to feedback')
for ax in axes:
    ax.spines[['top','right']].set_visible(False)
    ax.tick_params(labelsize=9)
fig.suptitle('NYC TLC | 5,972,150 trips | 24 scripted agents | 552,960 task executions',fontsize=13)
out=ROOT/'docs/figures';out.mkdir(exist_ok=True)
fig.savefig(out/'tlc-validation.png',dpi=180)
fig.savefig(out/'tlc-validation.svg')
print(out/'tlc-validation.png')
