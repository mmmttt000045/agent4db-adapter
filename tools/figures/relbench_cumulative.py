"""Cumulative RelBench tokens, with one full-column panel per database.

Panels are stacked to keep six method curves readable at print size. The
initial learning cutoff is shaded; subsequent cutoffs permit memory reuse.
Data and arrival order are unchanged from paper-sessions.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import INK, MUTED  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

NAME = 'relbench-cumulative'
W, H = 88.9, 82.0
DATA = style.ROOT / 'exp/2026-10-20-relbench/paper-sessions.json'
ARMS = [('none', 'No memory', '无记忆', 'mNoShare', '^'), ('ace', 'ACE', 'ACE', 'mACE', 'v'),
        ('gmemory', 'G-Memory', 'G-Memory', 'mGMem', 'P'), ('awm', 'AWM', 'AWM', 'mAWM', 'X'),
        ('deepprep', 'DeepPrep', 'DeepPrep', 'mDeepPrep', 's'), ('mavra', 'MAVRA (ours)', 'MAVRA（本文）', 'mCond', 'o')]
TEXT = {'en': {'y': 'Cumulative tokens (M)', 'x': 'Session (arrival order)',
               'first': 'C1: learn', 'later': 'C2–5: reuse'},
        'zh': {'y': '累计 token（百万）', 'x': '会话（按到来顺序）',
               'first': '截点 1：学习', 'later': '截点 2–5：复用'}}


def draw(lang, data_path=DATA, out_dir=None):
    data = json.loads(Path(data_path).read_text(encoding='utf-8'))
    mplstyle.setup(lang)
    fig = mplstyle.figure(W, H)
    dbs = [db for db in ('rel-stack', 'rel-trial') if db in data]
    axes = fig.subplots(len(dbs), 1, sharex=True, squeeze=False)[:, 0]
    for panel, (ax, db) in enumerate(zip(axes, dbs)):
        sequence = [row['k'] for row in data[db]['mavra']]
        boundaries = [i + .5 for i in range(1, len(sequence)) if sequence[i] != sequence[i - 1]]
        assert len(boundaries) == 4, (db, sequence)
        first_end = boundaries[0]
        ax.axvspan(.5, first_end, color='#ECECEC', zorder=0)
        for boundary in boundaries:
            ax.axvline(boundary, color=style.GRID, lw=.45, zorder=1)
        for arm, en, zh, color, marker in ARMS:
            rows = data[db].get(arm)
            if not rows:
                continue
            assert [row['k'] for row in rows] == sequence, (db, arm)
            total, ys = 0.0, []
            for row in rows:
                total += row['tokens'] / 1e6
                ys.append(total)
            ax.plot(range(1, len(ys) + 1), ys, color=style.PAPER_COLORS[color],
                    lw=1.5 if arm == 'mavra' else .95, marker=marker, ms=2.8, mew=0,
                    label=en if lang == 'en' else zh, zorder=3 if arm == 'mavra' else 2)
        ax.set_title(f"({'ab'[panel]}) {db}", loc='left', fontsize=8, color=INK, pad=3)
        ax.set_xlim(.5, len(sequence) + .5)
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
        ax.set_xticks([1, 3, 6, 9, 12, 15])
        ax.tick_params(labelsize=6.5)
        transform = ax.get_xaxis_transform()
        for x, label in (((.5 + first_end) / 2, TEXT[lang]['first']),
                         ((first_end + len(sequence) + .5) / 2, TEXT[lang]['later'])):
            ax.text(x, .98, label, transform=transform, ha='center', va='top',
                    fontsize=6.5, color=MUTED)
    axes[-1].set_xlabel(TEXT[lang]['x'], color=MUTED, fontsize=7)
    fig.text(.015, .45, TEXT[lang]['y'], rotation=90, va='center', fontsize=7, color=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    legend = fig.legend(handles, labels, loc='upper center', ncol=3, bbox_to_anchor=(.53, .99),
                        fontsize=7, handlelength=1.8, columnspacing=.8, labelspacing=.35)
    for label in legend.get_texts():
        if label.get_text().startswith('MAVRA'):
            label.set_weight('bold')
    fig.subplots_adjust(left=.15, right=.99, bottom=.13, top=.80, hspace=.65)
    out = Path(out_dir or style.OUT) / (f'{NAME}.pdf' if lang == 'en' else f'{NAME}-zh.pdf')
    mplstyle.save(fig, out)
    print(out)


if __name__ == '__main__':
    for lang in ('en', 'zh'):
        draw(lang, *(sys.argv[1:3]))
