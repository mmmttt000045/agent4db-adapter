#!/usr/bin/env python3
"""Build figures only from audited complete method sets, never synthetic numbers."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/figures'))
import mplstyle
import style
from matplotlib import pyplot as plt
from matplotlib.patches import Patch

METHODS=[('none','No memory','无记忆','mNoShare','^'),('ace','ACE','ACE','mACE','v'),
         ('awm','AWM','AWM','mAWM','s'),('gmemory','G-Memory','G-Memory','mGMem','D'),
         ('mavra','MAVRA','MAVRA','mCond','o')]
KINDS=[('schema','Schema','结构检查','#B8CDE5'),('probe','SQL probes','SQL 探查','#E1B78D'),
       ('validate','Validation','验证','#8FBCA0'),('memory','Memory tools','记忆工具','#B3A7C9'),
       ('submit','Submission','提交','#D4D4D4')]
HATCHES={'schema':'','probe':'//','validate':'..','memory':'xx','submit':'\\\\'}


def usable(data,preview=False):
    expected=set(data['protocol']['evaluation']['datasets'])
    if set(data['comparisons'])!=expected or (not preview and any(not c['complete_method_set'] for c in data['comparisons'].values())):
        raise SystemExit('No paper figures: the complete matched five-method comparison is not ready. See analysis.json for all statuses.')
    return list(data['protocol']['evaluation']['datasets'])


def build(data,out,lang,preview=False):
    datasets=usable(data,preview)
    mplstyle.setup(lang)
    labels=[m[1] if lang=='en' else m[2] for m in METHODS]
    # Mechanism: tool calls the agent issues, not unobserved internal memory calls.
    # The manuscript uses single-column figure floats. Keep the 7-point text at
    # its intended physical size instead of shrinking a two-column canvas.
    fig=mplstyle.figure(86,110)
    axes=fig.subplots(2,1,gridspec_kw={'left':.16,'right':.98,'bottom':.17,'top':.85,'hspace':.85})
    for ax,ds in zip(axes,datasets):
        means=data['comparisons'][ds]['arms']
        bottom=[0.]*len(METHODS)
        for key,en,zh,color in KINDS:
            values=[means[m[0]]['reuse_mean_calls'][key] if m[0] in means else 0. for m in METHODS]
            present=[i for i,m in enumerate(METHODS) if m[0] in means]
            ax.bar(present,[values[i] for i in present],bottom=[bottom[i] for i in present],color=color,edgecolor='black',
                   hatch=HATCHES[key],linewidth=.4,width=.64)
            bottom=[a+b for a,b in zip(bottom,values)]
        ax.set_xticks(range(len(METHODS)),labels,rotation=25,ha='right')
        ax.set_ylim(0,max(bottom)*1.12)
        ax.set_title(ds,pad=4)
        ax.yaxis.grid(True)
        for i,v in enumerate(bottom):
            if METHODS[i][0] in means: ax.text(i,v+.15,f'{v:.1f}',ha='center',va='bottom',fontsize=7)
            else: ax.text(i,max(bottom)*.04,'pending' if lang=='en' else '待完成',rotation=90,
                          ha='center',va='bottom',fontsize=6.5,color='#555555')
    fig.text(.025,.51,'Agent tool calls / reuse session' if lang=='en' else '复用会话的智能体工具调用数',
             rotation=90,ha='center',va='center',fontsize=7.5)
    fig.legend(handles=[Patch(facecolor=c,edgecolor='black',hatch=HATCHES[key],linewidth=.4,label=en if lang=='en' else zh)
                        for key,en,zh,c in KINDS],loc='upper center',ncol=3,bbox_to_anchor=(.52,.995),fontsize=7)
    prefix=('PREVIEW: comparison incomplete.\n' if lang=='en' else '排版预览：五方法对照尚未完成。\n') if preview else ''
    fig.text(.5,.018,prefix+('Cutoffs 2-3; agent-issued tool calls only.\nInternal memory-model work is charged in the table.' if lang=='en'
             else '截点 2-3；仅计智能体发起的工具调用。\n记忆模块内部的模型工作计入表中的记忆开销。'),ha='center',fontsize=6.5)
    save(fig,out,'reuse-work',lang,preview)
    # Amortization: same entire sequences, with memory construction charged.
    fig=mplstyle.figure(86,98)
    axes=fig.subplots(2,1,gridspec_kw={'left':.17,'right':.98,'bottom':.20,'top':.85,'hspace':.65})
    for ax,ds in zip(axes,datasets):
        cells={c['arm']:c for c in data['cells'] if c['dataset']==ds}
        for arm,en,zh,color,marker in METHODS:
            if cells[arm]['status']!='complete':continue
            rows=cells[arm]['sessions']
            ks=sorted({r['k'] for r in rows})
            ys=[sum(r['tokens'] for r in rows if r['k']<=k)/1e6 for k in ks]
            ax.plot(ks,ys,label=en if lang=='en' else zh,color=style.PAPER_COLORS[color],
                    marker=marker,mfc='white',linewidth=.9,ms=3.5)
        ax.set_title(ds,pad=4)
        ax.set_xticks(ks)
        ax.set_ylim(bottom=0)
        ax.set_xlabel('Retraining cutoff' if lang=='en' else '重训截点')
        ax.yaxis.grid(True)
        pending=[en if lang=='en' else zh for arm,en,zh,_,_ in METHODS if cells[arm]['status']!='complete']
        if preview and pending:
            ax.text(.02,.04,', '.join(pending)+(' pending' if lang=='en' else '待完成'),
                    transform=ax.transAxes,ha='left',va='bottom',fontsize=6.5,color='#555555')
    fig.text(.025,.51,'Cumulative tokens incl. memory (M)' if lang=='en' else '累计 token，含记忆操作（百万）',
             rotation=90,ha='center',va='center',fontsize=7.5)
    handles,legend=axes[0].get_legend_handles_labels()
    fig.legend(handles,legend,loc='upper center',ncol=3,bbox_to_anchor=(.52,.995),fontsize=7)
    fig.text(.5,.018,prefix+('One sequence per method;\ncutoffs are not independent repetitions.' if lang=='en'
             else '每种方法一条顺序运行；\n截点不是独立重复。'),ha='center',fontsize=6.5)
    save(fig,out,'official-cumulative',lang,preview)


def save(fig,out,name,lang,preview=False):
    stem=name+('-zh' if lang=='zh' else '')+('-preview' if preview else '')
    mplstyle.save(fig,out/(stem+'.pdf'))
    # Render the actual vector deliverable. Agg's font fallback can omit CJK
    # annotations even when the embedded PDF glyphs are correct.
    subprocess.run(['pdftoppm','-r','300','-png','-singlefile',
                    str(out/(stem+'.pdf')),str(out/stem)],check=True)


def tables(data,out,preview=False):
    usable(data,preview)
    lines=[r'% Generated by exp/2026-10-28-official/build-figures.py; complete matched cells only.',
           r'\begin{table*}[t]',r'\centering\footnotesize\setlength{\tabcolsep}{3pt}',
           r'\caption{\bt{Official-API comparison: one sequence of three tasks at three cutoffs per method and database. Total tokens include memory retrieval and updates; reuse covers cutoffs 2--3. Test quality averages all three cutoffs. Valid counts queries passing the leakage audit and final evaluation; other sessions receive the entity-reference score and retain all incurred cost. Bold denotes the best mean; $\dagger$ marks AUC more than 0.01 below, or MAE more than 2\% above, no memory.}{官方API对照：每种方法在每个数据库上运行一条序列，含三个任务和三个截点。总token包含记忆检索与更新，复用代价覆盖截点2--3；测试质量为全部三个截点的均值。有效方案指通过泄漏审计和最终评估的查询，其余会话使用实体表参照分数并保留全部成本。粗体为最佳均值；$\dagger$表示AUC比无记忆低超过0.01，或MAE高超过2\%。}}',
           r'\label{tab:official-results}',r'\begin{tabular}{lrrrrccc}',r'\toprule']
    for ds,comp in data['comparisons'].items():
        arms=comp['arms']; tasks=sorted(arms['none']['quality'])
        lines.append(r'\multicolumn{8}{l}{\textbf{'+ds+r'}}\\')
        task_headers=[]
        best={}
        for task in tasks:
            q=arms['none']['quality'][task]
            metric='AUC' if q['metric']=='roc_auc' else 'MAE'
            arrow=r'$\uparrow$' if q['higher_is_better'] else r'$\downarrow$'
            task_headers.append(r'\shortstack{'+task+r'\\'+metric+' '+arrow+'}')
            best[task]=(max if q['higher_is_better'] else min)(s['quality'][task]['mean'] for s in arms.values())
        lines.append(r'\bh{Method}{方法} & \bh{Total (M)}{总量(M)} & \bh{Reuse (M)}{复用(M)} & \bh{Memory (k)}{记忆(k)} & \bh{Valid}{有效} & '+' & '.join(task_headers)+r'\\')
        lines.append(r'\midrule')
        for arm,en,_,_,_ in METHODS:
            if arm not in arms:
                lines.append(en+r' & \multicolumn{7}{c}{\emph{\bt{Pending: full sequence or scoring incomplete}{待完成：完整序列或评分尚未结束}}}\\')
                continue
            s=arms[arm];values=[]
            for task in tasks:
                q=s['quality'][task];precision=5 if q['metric']=='mae' and abs(q['mean'])<.1 else 4
                v=f"{q['mean']:.{precision}f}"
                if abs(q['mean']-best[task])<1e-12: v=r'\textbf{'+v+'}'
                if not q['within_margin_vs_none']:v+=r'$^{\dagger}$'
                values.append(v)
            label=r'\bhl{No memory}{无记忆}' if arm=='none' else en
            lines.append(f"{label} & {s['tokens']/1e6:.3f} & {s['reuse_tokens']/1e6:.3f} & {s['learn_tokens']/1e3:.1f} & {s['valid']}/{s['n']} & "+' & '.join(values)+r'\\')
        lines.append(r'\addlinespace')
    lines += [r'\bottomrule',r'\end{tabular}',r'\end{table*}']
    if preview:
        lines[3]=lines[3].replace(r'\caption{',r'\caption{\textbf{\bt{LAYOUT PREVIEW: incomplete comparison.}{排版预览：对照尚未完成。}} ',1)
    (out/('official-results-preview.tex' if preview else 'official-results.tex')).write_text('\n'.join(lines)+'\n',encoding='utf-8')


def numbers(data,out):
    """Control-pair prose numbers may be staged once both full pairs finish."""
    if set(data['comparisons']) != set(data['protocol']['evaluation']['datasets']):
        raise SystemExit('Both complete control pairs are required for manuscript numbers')
    values={}
    full_quality=reuse_quality=0
    for ds,prefix in [('rel-stack','Stack'),('rel-trial','Trial')]:
        arms=data['comparisons'][ds]['arms']
        m,n=arms['mavra'],arms['none']
        assert m['n']==n['n']==9 and m['reuse_n']==n['reuse_n']==6
        values.update({f'Of{prefix}SaveAll':f"{m['token_saving_vs_none_pct']:.1f}",
                       f'Of{prefix}SaveReuse':f"{m['reuse_token_saving_vs_none_pct']:.1f}",
                       f'Of{prefix}Explore':f"{m['reuse_mean_calls']['schema']+m['reuse_mean_calls']['probe']:.1f}",
                       f'Of{prefix}NoneExplore':f"{n['reuse_mean_calls']['schema']+n['reuse_mean_calls']['probe']:.1f}",
                       f'Of{prefix}Validate':f"{m['reuse_mean_calls']['validate']:.1f}"})
        full_quality+=sum(q['within_margin_vs_none'] for q in m['quality'].values())
        reuse_quality+=sum(q['within_margin_vs_none'] for q in m['reuse_quality'].values())
    trial=data['comparisons']['rel-trial']['arms']
    ratio=trial['mavra']['quality']['study-adverse']['mean']/trial['none']['quality']['study-adverse']['mean']
    values.update(OfFullQualityCount=str(full_quality),OfReuseQualityCount=str(reuse_quality),
                  OfAdverseRegression=f'{100*(ratio-1):.1f}')
    lines=['% Official-API control-pair results; all 9 sessions of each cell retained.',
           '% Analysis generated UTC: '+data['generated_utc']]
    lines += ['\\newcommand{\\'+name+'}{'+value+'}' for name,value in values.items()]
    (out/'official-numbers.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path(__file__).with_name('analysis.json'))
    p.add_argument('--out',type=Path,default=ROOT/'overleaf/build/official-rebuild')
    p.add_argument('--preview',action='store_true',help='Layout preview with all unfinished methods explicitly pending; uses distinct filenames')
    a=p.parse_args();data=json.loads(a.data.read_text(encoding='utf-8'));usable(data,a.preview)
    a.out.mkdir(parents=True,exist_ok=True)
    for lang in ('en','zh'): build(data,a.out,lang,a.preview)
    tables(data,a.out,a.preview)
    numbers(data,a.out)
    print(a.out)
