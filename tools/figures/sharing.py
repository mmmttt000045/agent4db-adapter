"""Figure 1: definitions share conditions.

Definition families of the controlled workload on the left (one tile per
definition), their seven distinct conditions on the right, and what an update
of store_returns costs: definition-level revalidation reruns every condition
of the eight pending definitions (19 checks), MAVRA runs the three conditions
that read the table. The counts are computed from the structure below and
must equal the ones the caption states.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import measure  # noqa: E402
import style  # noqa: E402
from style import (ACC, ACC_DK, ACC_PALE, EDGE, FACE, INK, MUTED, ORANGE,  # noqa: E402
                   ORANGE_PALE, RULE, WHITE)

NAME = 'sharing'
W, H = style.COLUMN, 46.0

# Conditions, top to bottom: (kind, text, reads store_returns).
CONDITIONS = [
    ('grain', '`store_returns`(ticket, item)', True),
    ('time', '`store_returns`$\\to$`date_dim`', True),
    ('join', '`store_sales`$\\to$`store_returns`', True),
    ('grain', '`store_sales`(ticket, item)', False),
    ('time', '`store_sales`$\\to$`date_dim`', False),
    ('grain', '`catalog_sales`(order, item)', False),
    ('time', '`catalog_sales`$\\to$`date_dim`', False),
]
GROUPS = [(0, 1, 2), (3, 4), (5, 6)]
# Families: (key, definitions, condition indices).
FAMILIES = [('returns', 5, (0, 1)), ('ratios', 3, (2, 3, 4)), ('sales', 6, (3, 4)),
            ('catalog', 5, (5, 6))]

TEXT = {
    'en': {'defs': 'Definitions', 'conds': 'Conditions', 'update': 'update `store_returns`',
           'kinds': {'grain': 'Grain', 'time': 'Time', 'join': 'Join'},
           'families': {'returns': ('Store returns', 'amount, tax, fee, …'),
                        'ratios': ('Return ratios', 'return rate, …'),
                        'sales': ('Store sales', 'revenue, profit, …'),
                        'catalog': ('Catalog sales', 'revenue, shipping, …')},
           'def_level': 'Definition-level reruns', 'mavra': 'MAVRA runs',
           'checks': '{} checks'},
    'zh': {'defs': '定义', 'conds': '条件', 'update': '更新 `store_returns`',
           'kinds': {'grain': '粒度', 'time': '时间', 'join': '连接'},
           'families': {'returns': ('门店退货', '金额、税额、手续费等'),
                        'ratios': ('退货比率', '退货率等'),
                        'sales': ('门店销售', '营业额、利润等'),
                        'catalog': ('目录销售', '营业额、运费等')},
           'def_level': '定义级重跑', 'mavra': 'MAVRA 只查',
           'checks': '{} 次检查'},
}
NAMEPT, BODY, NOTE = 7.0, 6.4, 6.0     # font sizes, pt (acmart \footnotesize, \scriptsize)


def counts():
    """The numbers the caption states, derived from the structure."""
    pending = [f for f in FAMILIES if any(CONDITIONS[c][2] for c in f[2])]
    out = {'definitions': sum(n for _, n, _ in FAMILIES),
           'instances': sum(n * len(cs) for _, n, cs in FAMILIES),
           'conditions': len(CONDITIONS),
           'pending': sum(n for _, n, _ in pending),
           'definition_level_checks': sum(n * len(cs) for _, n, cs in pending),
           'mavra_checks': sum(1 for c in CONDITIONS if c[2])}
    expected = {'definitions': 19, 'instances': 41, 'conditions': 7, 'pending': 8,
                'definition_level_checks': 19, 'mavra_checks': 3}
    for key, value in expected.items():
        style.agree(f'Figure 1 {key}', out[key], value)
    return out, pending


def draw(s, lang):
    T, text = TEXT[lang], s.text
    n, pending = counts()
    pending_keys = {f[0] for f in pending}

    cx0, cx1, ch = 36.0, 79.6, 3.2           # condition chips
    fx1, fh = 26.0, 6.4                      # family cards
    top = 6.4

    # Condition chips, grouped by fact table.
    ys, y = {}, top
    for g, members in enumerate(GROUPS):
        for c in members:
            ys[c] = y
            y += ch + .7
        y += 1.0
    text(0, 3.0, T['defs'], NAMEPT, INK, 'bold')
    text(cx0, 3.0, T['conds'], NAMEPT, INK, 'bold')

    # Family cards spread over the same height.
    span_top, span_bottom = top, ys[6] + ch
    step = (span_bottom - span_top - fh) / (len(FAMILIES) - 1)
    fy = {f[0]: span_top + k * step for k, f in enumerate(FAMILIES)}

    # Edges first: grey for families left alone, orange for the pending ones.
    for hot in (False, True):
        for key, count, conds in FAMILIES:
            if (key in pending_keys) != hot:
                continue
            for i, c in enumerate(conds):
                y0 = fy[key] + fh / 2 + (i - (len(conds) - 1) / 2) * 1.0
                y1 = ys[c] + ch / 2
                s.curve((fx1, y0), (fx1 + 4.5, y0), (cx0 - 4.5, y1), (cx0, y1),
                        ORANGE if hot else RULE, .34 if hot else .26)

    for key, count, conds in FAMILIES:
        hot = key in pending_keys
        y = fy[key]
        s.rect(0, y, fx1, fh, ORANGE_PALE if hot else WHITE, ORANGE if hot else EDGE,
               .2 if hot else .15, r=.6)
        name, examples = T['families'][key]
        text(1.2, y + 2.75, name, BODY, INK, 'bold')
        for t in range(count):
            tx = fx1 - 1.2 - (count - t) * 1.7 + .35
            s.rect(tx, y + 1.0, 1.35, 1.35, ORANGE if hot else FACE, None if hot else EDGE, .1,
                   r=.2)
        text(1.2, y + 5.35, examples, NOTE, MUTED, width=fx1 - 2.4)

    tag = 1.1 + max(measure(k, NOTE, 'bold') for k in T['kinds'].values()) + 1.2
    for c, (kind, label, reads) in enumerate(CONDITIONS):
        y = ys[c]
        s.rect(cx0, y, cx1 - cx0, ch, ACC_PALE if reads else WHITE, ACC if reads else EDGE,
               .2 if reads else .15, r=.5)
        text(cx0 + 1.1, y + 2.25, T['kinds'][kind], NOTE, ACC_DK if reads else MUTED, 'bold')
        text(cx0 + tag, y + 2.25, label, NOTE, INK, width=cx1 - cx0 - tag - .8)

    # The update: a bracket over the three conditions that read store_returns.
    hot = [c for c, cond in enumerate(CONDITIONS) if cond[2]]
    b0, b1, bx = ys[hot[0]] + .4, ys[hot[-1]] + ch - .4, cx1 + 1.2
    s.poly([(cx1 + .4, b0), (bx, b0), (bx, b1), (cx1 + .4, b1)], None, ACC, .24, closed=False)
    mid = (b0 + b1) / 2
    text(W, 3.0, T['update'], NOTE, ACC_DK, align='right')
    s.route([(W - 1.0, 4.0), (W - 1.0, mid), (bx + .15, mid)], ACC, .24, length=1.0, radius=.8)

    # What the update costs.
    rows = [(T['def_level'], ORANGE, [2] * 5 + [3] * 3, n['definition_level_checks']),
            (T['mavra'], ACC, [3], n['mavra_checks'])]
    tile, pitch, group_gap = 1.3, 1.6, .7
    y = span_bottom + 3.6
    centers = []
    for label, color, groups, total in rows:
        text(cx0 - 1.6, y + 1.2, label, BODY, INK, align='right', width=cx0 - 2)
        x, centers = cx0, []
        for size in groups:
            start = x
            for _ in range(size):
                s.rect(x, y, tile, tile, color, None, r=.2)
                x += pitch
            centers.append((start + x - pitch + tile) / 2)
            x += group_gap
        text(x + .6, y + 1.2, T['checks'].format(total), BODY, color, 'bold', width=W - x - .6)
        if total == n['definition_level_checks']:
            # 5 x 2 + 3 x 3 under the definition-level tiles.
            ty = y + 3.6
            text(sum(centers[:5]) / 5, ty, '$5\\times2$', NOTE, MUTED, align='center')
            text(sum(centers[5:]) / 3, ty, '$3\\times3$', NOTE, MUTED, align='center')
        y += 4.8


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
