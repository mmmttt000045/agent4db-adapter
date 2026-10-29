"""Cumulative RelBench tokens, with one full-column panel per database.

Panels are stacked to keep six method curves readable at print size. The
cutoffs are separated by thin dashed rules; line styles and markers identify
methods at equal visual weight.
Data and arrival order are unchanged from paper-sessions.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplstyle  # noqa: E402
import style  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

NAME = 'relbench-cumulative'
W, H = 88.9, 82.0
DATA = style.ROOT / 'exp/2026-10-20-relbench/paper-sessions.json'
ARMS = [('none', 'No memory', '无记忆', 'mNoShare', '^'), ('ace', 'ACE', 'ACE', 'mACE', 'v'),
        ('gmemory', 'G-Memory', 'G-Memory', 'mGMem', 'P'), ('awm', 'AWM', 'AWM', 'mAWM', 'X'),
        ('deepprep', 'DeepPrep', 'DeepPrep', 'mDeepPrep', 's'), ('mavra', 'MAVRA (ours)', 'MAVRA（本文）', 'mCond', 'o')]
LINESTYLES = {
    'none': '--', 'ace': '-.', 'gmemory': ':',
    'awm': (0, (5, 2, 1, 2)), 'deepprep': (0, (3, 1, 1, 1, 1, 1)), 'mavra': '-',
}
TEXT = {'en': {'y': 'Cumulative tokens (M)', 'x': 'Session (arrival order)'},
        'zh': {'y': '累计 token（百万）', 'x': '会话（按到来顺序）'}}


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
        for boundary in boundaries:
            ax.axvline(boundary, color='#999999', lw=.4, ls='--', zorder=1)
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
                    ls=LINESTYLES[arm], lw=.9, marker=marker, ms=2.8,
                    mfc='white', mew=.55, label=en if lang == 'en' else zh, zorder=2)
        ax.set_title(f"({'ab'[panel]}) {db}", fontsize=mplstyle.TITLE, pad=3)
        ax.set_xlim(.5, len(sequence) + .5)
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
        ax.set_xticks([1, 3, 6, 9, 12, 15])
        ax.tick_params(labelsize=mplstyle.TICK, labelbottom=True)
        ax.yaxis.grid(True)
    axes[-1].set_xlabel(TEXT[lang]['x'])
    fig.text(.015, .45, TEXT[lang]['y'], rotation=90, va='center', fontsize=mplstyle.LABEL)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=3, bbox_to_anchor=(.53, .995),
               fontsize=7, handlelength=2.3, columnspacing=1.0, labelspacing=.4)
    fig.subplots_adjust(left=.15, right=.99, bottom=.13, top=.79, hspace=.60)
    out = Path(out_dir or style.OUT) / (f'{NAME}.pdf' if lang == 'en' else f'{NAME}-zh.pdf')
    mplstyle.save(fig, out)
    print(out)


if __name__ == '__main__':
    for lang in ('en', 'zh'):
        draw(lang, *(sys.argv[1:3]))
