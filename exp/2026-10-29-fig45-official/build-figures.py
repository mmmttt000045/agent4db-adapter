"""Fig.4 quality and the morning Fig.5 design from all audited official runs.

No experiment or API calls. Failed sessions retain the preregistered fallback.
Cutoffs form one dependent sequence; they are not treated as replicates.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/figures'))
import mplstyle
import style
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

METHODS = [('none', 'No memory', '无记忆', 'mNoShare', '^'),
           ('ace', 'ACE', 'ACE', 'mACE', 'v'),
           ('awm', 'AWM', 'AWM', 'mAWM', 's'),
           ('gmemory', 'G-Memory', 'G-Memory', 'mGMem', 'D'),
           ('mavra', 'MAVRA', 'MAVRA', 'mCond', 'o')]
TASKS = [('rel-stack', ['post-votes', 'user-badge', 'user-engagement']),
         ('rel-trial', ['site-success', 'study-adverse', 'study-outcome'])]
KINDS = [('schema', 'Schema', '结构检查', '#B8CDE5', ''),
         ('probe', 'SQL probes', 'SQL 探查', '#E1B78D', '//'),
         ('validate', 'Validation', '验证', '#8FBCA0', '..'),
         ('memory', 'Memory tools', '记忆工具', '#B3A7C9', 'xx'),
         ('submit', 'Submission', '提交', '#D4D4D4', '\\\\')]
OUT = ROOT / 'overleaf/figures'
PREVIEW = ROOT / 'tmp/pdfs/fig45-official'
PREVIEW.mkdir(parents=True, exist_ok=True)
paths = [ROOT / 'results/official-20261028' / n
         for n in ('analysis.json', 'evidence-audit.json')]
data, audit = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
assert audit['complete'] and audit['counts']['saved_formal_sessions'] == 90
assert len(data['cells']) == 10 and all(c['status'] == 'complete' for c in data['cells'])
expected = {m[0] for m in METHODS}
for ds, tasks in TASKS:
    comp = data['comparisons'][ds]
    assert comp['complete_method_set'] and set(comp['arms']) == expected
    for arm in comp['arms'].values():
        assert arm['n'] == 9 and arm['reuse_n'] == 6
        assert set(arm['quality']) == set(tasks)
        for q in arm['quality'].values():
            assert [r['k'] for r in q['per_cutoff']] == [1, 2, 3]
            assert abs(sum(r['score'] for r in q['per_cutoff']) / 3 - q['mean']) < 1e-12


def values(ds, task):
    arms = data['comparisons'][ds]['arms']
    base = arms['none']['quality'][task]
    higher = base['higher_is_better']
    threshold = -1.0 if higher else -2.0
    rows = []
    for key, en, zh, color, marker in METHODS:
        q = arms[key]['quality'][task]
        delta = 100 * (q['mean'] - base['mean']) if higher else 100 * (base['mean'] - q['mean']) / base['mean']
        valid = sum(p['source'] == 'final_sql' for p in q['per_cutoff'])
        raw = [r for c in data['cells'] if c['dataset'] == ds and c['arm'] == key
               for r in c['sessions'] if r['task'] == task]
        assert len(raw) == 3 and valid == sum(r['valid'] for r in raw)
        assert (delta >= threshold - 1e-10) == q['within_margin_vs_none']
        rows.append(dict(method=key, mean=q['mean'], delta=delta, valid=valid, n=3,
                         within_margin=q['within_margin_vs_none']))
    return dict(dataset=ds, task=task, metric=base['metric'],
                unit='AUC percentage points' if higher else 'relative MAE reduction (%)',
                threshold=threshold, rows=rows)


quality_data = [values(ds, task) for ds, tasks in TASKS for task in tasks]


def save(fig, name, lang):
    stem = name + ('-zh' if lang == 'zh' else '')
    path = OUT / (stem + '.pdf')
    mplstyle.save(fig, path)
    subprocess.run(['pdftoppm', '-r', '180', '-png', '-singlefile',
                    str(path), str(PREVIEW / stem)], check=True)


def quality(lang):
    mplstyle.setup(lang)
    fig = mplstyle.figure(178, 100)
    axes = fig.subplots(2, 3, gridspec_kw=dict(left=.10, right=.945, bottom=.12,
                                             top=.88, hspace=.78, wspace=.70))
    for i, (ax, item) in enumerate(zip(axes.flat, quality_data)):
        rows = item['rows']
        threshold = item['threshold']
        xs = [r['delta'] for r in rows]
        lo, hi = min(xs + [threshold]), max(xs + [0.0])
        span = max(hi - lo, 1.5)
        lo -= .10 * span
        hi += .15 * span
        ax.axvspan(threshold, hi, color='#EFF4F2', lw=0, zorder=0)
        ax.axvline(0, color='#777777', lw=.65, zorder=1)
        ax.axvline(threshold, color='#9E3F3F', ls=(0, (3, 2)), lw=.7, zorder=2)
        for y, (row, method) in enumerate(zip(rows, METHODS)):
            key, en, zh, color, marker = method
            ax.plot(row['delta'], y, marker=marker, ms=4.5, color=style.PAPER_COLORS[color],
                    mec=style.PAPER_COLORS[color], mfc='white', mew=1.0, zorder=3)
            ax.text(1.045, y, f"{row['valid']}/3", transform=ax.get_yaxis_transform(),
                    ha='left', va='center', fontsize=7, color='#222222', clip_on=False)
        ax.set_xlim(lo, hi)
        ax.set_ylim(4.65, -.65)
        ax.set_yticks(range(5), [m[1] if lang == 'en' else m[2] for m in METHODS])
        ax.tick_params(axis='y', length=0, pad=4)
        ax.spines[['top', 'right', 'left']].set_visible(False)
        ax.spines['bottom'].set_color('#777777')
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
        ax.grid(axis='x', zorder=0)
        unit = ('AUC change (pp)' if lang == 'en' else 'AUC 变化（百分点）') if item['metric'] == 'roc_auc' else ('MAE reduction (%)' if lang == 'en' else 'MAE 降低（%）')
        ax.set_xlabel(unit, labelpad=3, fontsize=7)
        ax.set_title(f"({chr(97+i)}) {item['task']}", fontsize=8, pad=14)
        ax.text(1.045, 1.01, 'Valid' if lang == 'en' else '有效', transform=ax.transAxes,
                ha='left', va='bottom', fontsize=6.5, clip_on=False)
    fig.text(.015, .925, 'rel-stack', fontsize=8, fontweight='bold')
    fig.text(.015, .478, 'rel-trial', fontsize=8, fontweight='bold')
    fig.legend(handles=[Patch(facecolor='#EFF4F2', edgecolor='none', label='Within predeclared margin' if lang=='en' else '满足预设质量门槛'),
                        Line2D([0], [0], color='#9E3F3F', ls=(0,(3,2)), lw=.7, label='Margin: -1 pp AUC / -2% MAE' if lang=='en' else '门槛：AUC -1百分点 / MAE -2%')],
               loc='upper center', bbox_to_anchor=(.54,.995), ncol=2, fontsize=7)
    fig.text(.5,.015, 'Relative to no memory; positive is better. All three cutoffs, including fallback scores.' if lang=='en' else '相对无记忆，正值更好。包含全部三个截点及失败回退分数。',
             ha='center', fontsize=7)
    save(fig, 'official-quality', lang)


def work(lang):
    """Keep the morning chart's layout, marks, categories, denominators and data."""
    mplstyle.setup(lang)
    fig = mplstyle.figure(86, 110)
    axes = fig.subplots(2, 1, gridspec_kw=dict(left=.16, right=.98, bottom=.17, top=.85, hspace=.85))
    for ax, (ds, _) in zip(axes, TASKS):
        means = data['comparisons'][ds]['arms']
        bottom = [0.] * len(METHODS)
        for key, en, zh, color, hatch in KINDS:
            ys = [means[m[0]]['reuse_mean_calls'][key] for m in METHODS]
            ax.bar(range(5), ys, bottom=bottom, color=color, edgecolor='black', hatch=hatch, linewidth=.4, width=.64)
            bottom = [a+b for a,b in zip(bottom,ys)]
        ax.set_xticks(range(5), [m[1] if lang=='en' else m[2] for m in METHODS], rotation=25, ha='right')
        ax.set_ylim(0,max(bottom)*1.12)
        ax.set_title(ds,pad=4)
        ax.yaxis.grid(True)
        for i,v in enumerate(bottom): ax.text(i,v+.15,f'{v:.1f}',ha='center',va='bottom',fontsize=7)
    fig.text(.025,.51,'Agent tool calls / reuse session' if lang=='en' else '复用会话的智能体工具调用数', rotation=90,ha='center',va='center',fontsize=7.5)
    fig.legend(handles=[Patch(facecolor=c,edgecolor='black',hatch=h,linewidth=.4,label=en if lang=='en' else zh) for _,en,zh,c,h in KINDS],
               loc='upper center',ncol=3,bbox_to_anchor=(.52,.995),fontsize=7)
    fig.text(.5,.018,'Cutoffs 2-3; agent-issued tool calls only.\nInternal memory-model work is included in total tokens.' if lang=='en'
             else '截点 2-3；仅计智能体发起的工具调用。\n记忆模块内部的模型工作计入总 token。',ha='center',fontsize=6.5)
    save(fig,'reuse-work',lang)


for lang in ('en', 'zh'):
    quality(lang)
    work(lang)
manifest = dict(sources_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                session_count=90, independent_runs_per_method=1, quality=quality_data,
                work={ds:{m[0]:data['comparisons'][ds]['arms'][m[0]]['reuse_mean_calls'] for m in METHODS} for ds,_ in TASKS},
                quality_scope='All 90 scheduled sessions, no completed failures excluded.',
                work_scope='Six reuse sessions per method/database, including failures; internal model calls are not agent tool calls.')
(HERE/'figure-data.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Generated four bilingual figure assets from 90 audited sessions.')
