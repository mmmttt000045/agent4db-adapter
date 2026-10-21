"""Figure: cumulative tokens of the RelBench sessions, by method.

One panel per database. The x axis is the session in arrival order (cutoff by cutoff, the tasks of a cutoff in the
run's order), thin vertical rules separate the cutoffs, and each method's line is the running total of its sessions'
tokens, memory operations included. Data: exp/2026-10-20-relbench/paper-sessions.json (written by
tools/relbench/paper-stats.py --sessions-json).

  python3 tools/figures/relbench_cumulative.py   # writes overleaf/figures/relbench-cumulative{,-zh}.pdf
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import INK, MUTED  # noqa: E402

NAME = 'relbench-cumulative'
W, H = 88.9, 46.0  # IEEE column width (3.5 in)
DATA = style.ROOT / 'exp/2026-10-20-relbench/paper-sessions.json'
# arm -> (English, Chinese, colour name in the preamble, marker)
ARMS = [('none', 'No memory', '无记忆', 'mNoShare', '^'), ('ace', 'ACE', 'ACE', 'mACE', 'v'),
        ('gmemory', 'G-Memory', 'G-Memory', 'mGMem', 'P'), ('awm', 'AWM', 'AWM', 'mAWM', 'X'),
        ('deepprep', 'DeepPrep', 'DeepPrep', 'mDeepPrep', 's'), ('mavra', 'MAVRA (ours)', 'MAVRA（本文）', 'mCond', 'o')]
TEXT = {'en': {'y': 'Cumulative tokens (M)', 'x': 'Session (in arrival order)', 'k': 'cutoff {k}'},
        'zh': {'y': '累计 token（百万）', 'x': '会话（按到来顺序）', 'k': '截点 {k}'}}


def draw(lang, data_path=DATA, out_dir=None):
    data = json.loads(Path(data_path).read_text(encoding='utf-8'))
    mplstyle.setup(lang)
    fig = mplstyle.figure(W, H)
    dbs = [db for db in ('rel-stack', 'rel-trial') if db in data]
    axes = fig.subplots(1, len(dbs), squeeze=False)[0]
    for ax, db in zip(axes, dbs):
        n_max = 0
        for arm, en, zh, color, marker in ARMS:
            rows = data[db].get(arm)
            if not rows:
                continue
            total, ys = 0.0, []
            for r in rows:
                total += r['tokens'] / 1e6
                ys.append(total)
            xs = list(range(1, len(ys) + 1))
            n_max = max(n_max, len(xs))
            lw = 1.4 if arm == 'mavra' else .9
            ax.plot(xs, ys, color=style.PAPER_COLORS[color], lw=lw, marker=marker, ms=2.4, mew=0, label=en if lang == 'en' else zh,
                    zorder=3 if arm == 'mavra' else 2)
        per = n_max // 5 if n_max >= 5 else 1
        for b in range(per, n_max, per):
            ax.axvline(b + .5, color=style.GRID, lw=.4, zorder=1)
        ax.set_title(db, fontsize=mplstyle.LABEL, color=INK)
        ax.set_xlim(.5, n_max + .5)
        ax.set_ylim(bottom=0)
        ax.set_xticks([b for b in range(per, n_max + 1, per)])
        ax.set_xlabel(TEXT[lang]['x'], color=MUTED)
    axes[0].set_ylabel(TEXT[lang]['y'])
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=3, bbox_to_anchor=(.5, 1.02), fontsize=mplstyle.TICK)
    fig.subplots_adjust(left=.1, right=.99, bottom=.2, top=.72, wspace=.28)
    out = Path(out_dir or style.OUT) / (f'{NAME}.pdf' if lang == 'en' else f'{NAME}-zh.pdf')
    mplstyle.save(fig, out)
    print(out)


if __name__ == '__main__':
    # optional: the sessions JSON and the output folder (default: the archived JSON and overleaf/figures)
    for lang in ('en', 'zh'):
        draw(lang, *(sys.argv[1:3]))
