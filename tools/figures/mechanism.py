"""Paper-sized mechanism figures from the frozen 2026-10-29 evidence.

The original, annotated review figures remain unchanged. This renderer removes
their page titles and footnotes, whose content belongs in the LaTeX captions.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt, colors
from matplotlib.patches import Patch

import mplstyle
import style

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / 'exp/2026-10-29-mechanism-pilot'
ARCHIVE = ROOT / 'exp/2026-10-02-cache-baseline-tpcds'
OUT = ROOT / 'overleaf/figures'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


A = read(STUDY / 'pilot-summary.json')
S = read(STUDY / 'system-summary.json')
LEGACY = read(ARCHIVE / 'snapshot-binding-stats.json')
WRITERS = read(ARCHIVE / 'snapshot-binding-shards-stats.json')
assert A['complete'] and len(A['rows']) == 8
assert all(r['test_score'] is None for r in A['rows'])
assert S['B']['complete'] and S['B']['requests'] == 9216 and S['B']['unavailable'] == 0
assert S['C']['complete'] and S['C']['gate_passed']


def bilingual(lang, en, zh):
    return zh if lang == 'zh' else en


def figure_a(lang):
    fig = mplstyle.figure(84.6, 83)
    ax = fig.subplots(2, 2)
    fig.subplots_adjust(left=.15, right=.98, top=.85, bottom=.09, hspace=.52, wspace=.31)
    arms = ['none', 'program', 'definition', 'full']
    palette = {a: style.PAPER_COLORS[c] for a, c in zip(arms, ['mNoShare', 'mTraj', 'mCondCur', 'mCond'])}
    for col, target in enumerate(['cross-task', 'same-task-later']):
        rows = [next(r for r in A['rows'] if r['target']['name'] == target and r['arm'] == a) for a in arms]
        for i, r in enumerate(rows):
            if r['valid']:
                ax[0, col].plot(i, r['validation_auc'], marker=['^', 's', 'D', 'o'][i],
                                color=palette[r['arm']], mfc='white', ms=3.3, mew=.7)
                ax[0, col].text(i, r['validation_auc']+.022, f"{r['validation_auc']:.3f}", ha='center', fontsize=6.5)
            else:
                ax[0, col].text(i, .60, bilingual(lang, 'No\nSQL', '无有效\nSQL'), ha='center', fontsize=6.5)
            online = r['agent_tokens']/1000
            source = r['historical_source_allocated_tokens']/1000
            extract = r['new_extraction_allocated_tokens']/1000
            rgb = colors.to_rgb(palette[r['arm']])
            fill = tuple(.35*c+.65 for c in rgb)
            ax[1, col].bar(i, online, .65, color=fill, edgecolor='black', lw=.4)
            ax[1, col].bar(i, source, .65, bottom=online, color='white', hatch='//', edgecolor='black', lw=.4)
            ax[1, col].bar(i, extract, .65, bottom=online+source, color='#D4D4D4', hatch='xx', edgecolor='black', lw=.4)
            ax[1, col].text(i, online+source+extract+8, f'{online+source+extract:.0f}', ha='center', fontsize=6.5)
        ax[0, col].set(ylim=(.55, .92), yticks=[.6, .7, .8, .9])
        ax[1, col].set(ylim=(0, 370), yticks=[0, 100, 200, 300])
        title = bilingual(lang, 'Cross-task' if col == 0 else 'Later cutoff', '跨任务' if col == 0 else '后续截点')
        for row in range(2):
            p = ax[row, col]
            p.set_title(f"({'abcd'[row*2+col]}) {title}", fontsize=7)
            p.set(xticks=range(4), xticklabels=['N', 'P', 'D', 'B'], xlim=(-.6, 3.6))
            p.tick_params(labelsize=6.5)
            p.grid(axis='y')
    ax[0, 0].set_ylabel(bilingual(lang, 'Validation AUC', '验证 AUC'), fontsize=7)
    ax[1, 0].set_ylabel(bilingual(lang, 'Tokens (k)', 'token（千）'), fontsize=7)
    handles = [Patch(facecolor='#C0C0C0', edgecolor='black', lw=.4, label=bilingual(lang, 'Online', '在线')),
               Patch(facecolor='white', edgecolor='black', lw=.4, hatch='//', label=bilingual(lang, 'Source / 2', '源探索 / 2')),
               Patch(facecolor='#D4D4D4', edgecolor='black', lw=.4, hatch='xx', label=bilingual(lang, 'Extract / 2', '提炼 / 2'))]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.56, .99), ncol=3, fontsize=6.5,
               handlelength=1.3, columnspacing=.7)
    return fig


def figure_b(lang):
    fig = mplstyle.figure(84.6, 89)
    axes = fig.subplots(2, 2, sharey='row')
    fig.subplots_adjust(left=.17, right=.98, top=.84, bottom=.13, hspace=.60, wspace=.35)
    marks = {'definition': 's', 'definition-cache': '^', 'condition': 'o'}
    lines = {'definition': ':', 'definition-cache': '--', 'condition': '-'}
    names = {'definition': bilingual(lang, 'Full recheck', '全量重查'),
             'definition-cache': bilingual(lang, 'SQL/version cache', 'SQL／版本缓存'), 'condition': 'MAVRA'}
    for col, arrival in enumerate(['staggered', 'burst']):
        for policy in marks:
            pts = [next(r for r in S['B']['groups'] if r['arrival'] == arrival and r['policy'] == policy
                        and r['reuse_factor'] == k) for k in [1, 2, 4, 8]]
            for row, metric, mult in [(0, 'paired_db_ratio', 100), (1, 'validation_queries', 1)]:
                vals = [r[metric]['median']*mult for r in pts]
                errs = [[(r[metric]['median']-r[metric]['min'])*mult for r in pts],
                        [(r[metric]['max']-r[metric]['median'])*mult for r in pts]]
                axes[row, col].errorbar([1, 2, 4, 8], vals, yerr=errs, color=mplstyle.color(policy),
                    marker=marks[policy], ls=lines[policy], mfc='white', mew=.6, capsize=1.8,
                    elinewidth=.6, label=names[policy])
        for row in range(2):
            ax = axes[row, col]
            name = bilingual(lang, 'Staggered' if col == 0 else 'Simultaneous', '交错到达' if col == 0 else '同时到达')
            measure = bilingual(lang, 'time' if row == 0 else 'queries', '耗时' if row == 0 else '查询数')
            ax.set_title(f"({'abcd'[row*2+col]}) {name}", fontsize=6.5)
            ax.set(xticks=[1, 2, 4, 8])
            ax.set_ylim(0, 215 if row == 0 else 105)
            ax.set_yticks([0, 100, 200] if row == 0 else [0, 50, 100])
            ax.tick_params(labelleft=True, labelsize=6.5)
            ax.grid(axis='y')
            if row == 1:
                ax.set_xlabel(bilingual(lang, 'Sharing factor', '共享因子'), fontsize=7)
    axes[0, 0].set_ylabel(bilingual(lang, 'DB time / full (%)', 'DB 耗时／全量重查（%）'), fontsize=7)
    axes[1, 0].set_ylabel(bilingual(lang, 'Validation queries', '验证 SQL 次数'), fontsize=7)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc='upper center',
               bbox_to_anchor=(.54, .99), ncol=3, handlelength=1.6, fontsize=6.5, columnspacing=.7)
    return fig


def figure_c(lang):
    fig = mplstyle.figure(178, 55)
    grid = fig.add_gridspec(1, 3, width_ratios=[1.28, 1, 1], left=.055, right=.99,
                            top=.76, bottom=.26, wspace=.37)
    axes = [fig.add_subplot(grid[0, i]) for i in range(3)]
    ax = axes[0]
    cases = ['benign_after_check', 'violation_after_check', 'violation_before_call']
    outcomes = [('served', style.OUT_CORRECT, '', bilingual(lang, 'Condition-valid', '条件成立')),
                ('violation', style.WRONG, 'xx', bilingual(lang, 'Condition-violating', '条件违反')),
                ('rejected', style.OUT_UNNEEDED, '//', bilingual(lang, 'Refused', '拒绝'))]
    for i, case in enumerate(cases):
        for j, mode in enumerate(['tx-precheck', 'tx-bound']):
            g = next(r for r in S['C']['groups'] if r['case'] == case and r['mode'] == mode)
            assert g['n'] == 5 and g['error'] == 0
            bottom = 0
            for key, color, hatch, label in outcomes:
                ax.bar(i*2.6+j*.9, g[key], bottom=bottom, width=.72, color=color, hatch=hatch,
                       edgecolor='black', lw=.4, label=label if i == j == 0 else None)
                bottom += g[key]
    ax.set(xticks=[i*2.6+j*.9 for i in range(3) for j in range(2)],
           xticklabels=['P', 'B']*3, yticks=[0, 1, 2, 3, 4, 5], ylim=(0, 5.5))
    ax.set_title(bilingual(lang, '(a) Matched snapshots', '(a) 同版本源对照'))
    ax.set_ylabel(bilingual(lang, 'Calls (n = 5)', '调用数（n = 5）'))
    labels = bilingual(lang, ['Benign\nafter check', 'Break\nafter check', 'Break\nbefore call'],
                       ['良性写入\n检查后', '破坏性写入\n检查后', '破坏性写入\n调用前'])
    for i, label in enumerate(labels):
        ax.text(i*2.6+.45, -1.15, label, ha='center', va='top', fontsize=6.5)
    fig.legend(*ax.get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.52, .99), ncol=3, fontsize=7)
    ax = axes[1]
    for j, mode in enumerate(['precheck', 'snapshot']):
        vals = [LEGACY['reader_p50_ms'][mode][k] for k in ['steady_ms', 'first_after_write_ms', 'second_after_write_ms']]
        pos = np.arange(3)+(j-.5)*.32
        key = ['definition', 'condition'][j]
        ax.bar(pos, vals, .30, label=bilingual(lang, ['Legacy pre', 'Bound'][j], ['旧预检查', '快照绑定'][j]),
               **mplstyle.bar_style(key, ['//', '\\\\'][j]))
    ax.set(xticks=[0, 1, 2], xticklabels=bilingual(lang, ['Steady', '1st', '2nd'], ['稳态', '第1次', '第2次']),
           yscale='log', ylim=(1, 7000))
    ax.set_title(bilingual(lang, '(b) Archived reader', '(b) 归档读延迟'))
    ax.set_ylabel(bilingual(lang, 'Latency (ms, log)', '延迟（ms，对数）'))
    ax.legend(fontsize=6.5, loc='upper right', bbox_to_anchor=(1, 1.03))
    ax.text(.5, -.39, bilingual(lang, '1st / 2nd read after benign write', '良性写入后的第 1／2 次读取'),
            transform=ax.transAxes, ha='center', fontsize=6.5)
    ax = axes[2]
    keys = ['sequential_stmt_per_s', 'concurrent8_stmt_per_s', 'concurrent32_stmt_per_s']
    for mode, color, marker, line, label in [
        ('shards1', mplstyle.color('definition'), 's', '--', bilingual(lang, 'One row', '单行版本')),
        ('shards16', mplstyle.color('condition'), 'o', '-', bilingual(lang, '16 shards', '16 个分片'))]:
        vals = [WRITERS['writer_median'][mode][k]/WRITERS['writer_median']['no_trigger'][k]*100 for k in keys]
        ax.plot([1, 8, 32], vals, color=color, marker=marker, ls=line, mfc='white', mew=.6, label=label)
    ax.axhline(100, color='#555555', ls=':', lw=.6)
    ax.set(xticks=[1, 8, 32], ylim=(0, 115), yticks=[0, 50, 100])
    ax.set_title(bilingual(lang, '(c) Archived writer', '(c) 归档写吞吐'))
    ax.set_ylabel(bilingual(lang, 'Throughput / no trigger (%)', '吞吐／无触发器（%）'))
    ax.set_xlabel(bilingual(lang, 'Writer connections', '写连接数'))
    ax.legend(fontsize=6.5, loc='lower left')
    for ax in axes:
        ax.grid(axis='y')
        ax.tick_params(labelsize=6.5)
    return fig


def numbers():
    d = {}
    def row(arm):
        return next(r for r in A['rows'] if r['target']['name'] == 'same-task-later' and r['arm'] == arm)
    for arm, name in [('none', 'None'), ('program', 'Program'), ('definition', 'Definition'), ('full', 'Both')]:
        d['MeA'+name+'AUC'] = f"{row(arm)['validation_auc']:.4f}"
    d.update(MeAValid=str(sum(r['valid'] for r in A['rows'])),
             MeASourceK=f"{A['source']['historical_exploration_tokens']/1000:.1f}",
             MeAExtractK=f"{A['source']['new_extraction_tokens']/1000:.1f}",
             MeABothOnlineK=f"{row('full')['agent_tokens']/1000:.1f}",
             MeANoneOnlineK=f"{row('none')['agent_tokens']/1000:.1f}",
             MeABothTotalK=f"{row('full')['amortized_tokens']/1000:.1f}")
    for arrival, a in [('staggered', 'Stag'), ('burst', 'Burst')]:
        for policy, p in [('condition', 'Mavra'), ('definition-cache', 'Cache')]:
            r = next(g for g in S['B']['groups'] if g['arrival'] == arrival and g['reuse_factor'] == 8 and g['policy'] == policy)
            d['MeB'+a+p] = f"{100*r['paired_db_ratio']['median']:.1f}"
    d['MeBRequests'] = f"{S['B']['requests']:,}".replace(',', '{,}')
    return d


if __name__ == '__main__':
    for lang in ['en', 'zh']:
        mplstyle.setup(lang)
        for name, render in [('memory-access-pilot', figure_a), ('fixed-sharing', figure_b), ('snapshot-control', figure_c)]:
            fig = render(lang)
            suffix = '-zh' if lang == 'zh' else ''
            mplstyle.save(fig, OUT/(name+suffix+'.pdf'))
    (ROOT/'overleaf/gen/mechanism.tex').write_text(
        '% Generated from the frozen 2026-10-29 mechanism evidence.\n' +
        ''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k, v in numbers().items()), encoding='utf-8')
    sources = [STUDY/'pilot-summary.json', STUDY/'system-summary.json',
               ARCHIVE/'snapshot-binding-stats.json', ARCHIVE/'snapshot-binding-shards-stats.json',
               Path(__file__), ROOT/'tools/figures/mplstyle.py', ROOT/'tools/figures/style.py', ROOT/'overleaf/latex/preamble.tex']
    evidence = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (STUDY/'paper-integration/figure-sources.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print('Generated six paper figures and mechanism number macros.')
