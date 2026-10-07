"""Figure: maintenance database time relative to definition-level revalidation.

Two panels (staggered and simultaneous arrivals) share the y axis; series are
labelled on the lines instead of in a legend. Data:
exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json, the archive that
tools/review-results.py turns into the \\Cb* macros; the 4- and 19-definition
points are checked against those macros.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mplstyle  # noqa: E402
import style  # noqa: E402
from style import INK, MUTED, ORANGE, WHITE  # noqa: E402

NAME = 'maintenance-cost'
W, H = style.COLUMN, 44.0
DATA = style.ROOT / 'exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json'

ARRIVALS = [('staggered', 'Stag'), ('burst', 'Burst')]
# policy -> (macro key, line style, marker, filled), in drawing order: the cache comes last with
# hollow triangles, so it stays visible where it coincides with MAVRA.
SERIES = {'condition-scope': ('Scope', (0, (1.0, 1.6)), 's', True),
          'condition': ('Cond', 'solid', 'o', True),
          'definition-cache': ('Cache', (0, (3.0, 1.6)), '^', False)}
SHARES = (1, 2, 4, 6)
TEXT = {
    'en': {'y': 'DB time vs. definition-level', 'x': 'Definitions',
           'panels': ('Staggered', 'Simultaneous')},
    'zh': {'y': '相对定义级的 DB 时间', 'x': '定义数', 'panels': ('错峰', '同时到达')},
}


def load():
    rows = json.loads(DATA.read_text(encoding='utf-8'))['rows']
    printed = style.macros('review')
    series = {}
    for arrival, akey in ARRIVALS:
        for policy, (pkey, *_) in SERIES.items():
            pts = []
            for share in SHARES:
                row = next(r for r in rows if r['share'] == share and r['arrival'] == arrival
                           and r['policy'] == policy)
                pts.append((row['specs'], 100 * row['vs_definition']))
                if share in (1, 6):
                    name = f"Cb{akey}{pkey}{'One' if share == 1 else 'Six'}"
                    style.agree(name, f'{100 * row["vs_definition"]:.1f}', printed[name])
            series[arrival, policy] = pts
    return series


def figure(lang):
    series, T = load(), TEXT[lang]
    fig = mplstyle.figure(W, H)
    axes = fig.subplots(1, 2, sharey=True, gridspec_kw=dict(left=.115, right=.99, top=.80, bottom=.20, wspace=.12))
    for k, (ax, (arrival, _)) in enumerate(zip(axes, ARRIVALS)):
        ax.set_title(T['panels'][k], pad=3)
        ax.axhline(100, color=ORANGE, lw=.9, ls=(0, (1.0, 1.4)), zorder=2)
        for policy, (_, ls, marker, filled) in SERIES.items():
            label, color = style.method(policy, lang)
            xs, ys = zip(*series[arrival, policy])
            ax.plot(xs, ys, ls=ls, color=color, lw=.9, zorder=3)
            if filled:
                ax.plot(xs, ys, ls='', marker=marker, ms=3.4, mfc=color, mec=WHITE, mew=.35, zorder=4)
            else:
                ax.plot(xs, ys, ls='', marker=marker, ms=3.8, mfc='none', mec=color, mew=.6, zorder=4)
        ax.set_xlim(2, 21)
        ax.set_ylim(0, 125)
        ax.set_xticks([4, 8, 15, 19])
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'])
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.spines['left'].set_visible(k == 0)
        ax.tick_params(axis='y', length=0 if k else 1.8)
        scope, scope_color = style.method('condition-scope', lang)
        if k == 0:
            # Labels sit where the staggered lines are far apart.
            ax.text(2.4, 103, style.method('definition', lang)[0], color=ORANGE, fontsize=mplstyle.LABEL,
                    ha='left', va='bottom')
            ax.text(9.2, 89.5, scope, color=scope_color, fontsize=mplstyle.LABEL, ha='left', va='bottom')
            cache, cache_color = style.method('definition-cache', lang)
            ax.text(5.0, 60, cache, color=cache_color, fontsize=mplstyle.LABEL, ha='left', va='bottom')
            mavra, mavra_color = style.method('condition', lang)
            ax.text(19.6, 2.5, mavra, color=mavra_color, fontsize=mplstyle.LABEL, ha='right', va='bottom',
                    fontweight='bold')
        else:
            # Only affected-only revalidation leaves the band of the other series here.
            ax.text(17.8, 117, scope, color=scope_color, fontsize=mplstyle.LABEL, ha='right', va='center')
    fig.text(.01, .965, T['y'], color=MUTED, fontsize=mplstyle.LABEL, ha='left', va='top')
    fig.text((.115 + .99) / 2, .02, T['x'], color=MUTED, fontsize=mplstyle.LABEL, ha='center', va='bottom')
    return fig


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
