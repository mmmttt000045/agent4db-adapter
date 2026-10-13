"""Paper figure 2 (architecture): one agent explores, MAVRA shares, every agent reuses.

Drawn with the deck kit at 300 mm and scaled to the text width by LaTeX (12 pt
prints at 7.1 pt, 11 pt at 6.5 pt), like figure 1. Few words, more picture:
- top: agent windows. Agent A explores (table, value, join and SQL tools) and its
  answer is verified; agents B-D ask other questions about the same metric and each
  holds the same shared definition card, answering with one SQL;
- middle, MAVRA: publication checks, the shared memory (definition cards with
  version and state, and the check results shared by all definitions), maintenance
  (repair and optimization, once for all agents), and execution on one snapshot;
- bottom: the SQL database and the updates that change its tables.
Paths and colours follow figure 1: publish violet (1-2), use amber (3-5),
maintain and optimize blue (6-8). Thick arrows write the shared memory, dashed
ones read database state.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import (DASH, EXEC, HEAD, LEARN, NOTE, SOFT, STEP, THICK, THIN, TITLE, USE, WAIT, baseline,  # noqa: E402
                   legend_pill, mark, node, person, slab, sparkle, step, table_card)
from style import ACC_DK, AMBER, AMBER_PALE, INK, MUTED, RED, WHITE  # noqa: E402
import deckpal as P  # noqa: E402

SMALL = NOTE - 1                                             # 11 pt, prints at 6.5 pt


def pill(s, x, yc, label, fill, color=WHITE, size=SMALL, h=5.8):
    """A rounded label; (x, yc) its left edge and vertical centre. Returns its width."""
    w = measure(label, size, 'bold') + 4.4
    s.rect(x, yc - h / 2, w, h, fill, None, r=h / 2)
    s.text(x + 2.2, baseline(yc, size), label, size, color, 'bold')
    return w


def pill_width(label, size=SMALL):
    return measure(label, size, 'bold') + 4.4


def panel(s, b, edge=P.PANEL, fill=WHITE, sw=.45):
    s.rect(*b, fill, edge, sw, r=1.6)


def bubble(s, b, fill, edge):
    """A speech bubble with a small tail on the left of its top edge."""
    x, y, w, h = b
    s.rect(*b, fill, edge, .35, r=1.6)
    tx = x + 6.0
    s.poly([(tx - 2.0, y + .2), (tx, y - 2.2), (tx + 2.0, y + .2)], fill, None)
    s.line(tx - 2.0, y, tx, y - 2.2, edge, .35)
    s.line(tx, y - 2.2, tx + 2.0, y, edge, .35)


def window(s, b, title, fill=WHITE, edge='#C9CED6', bar='#EEF0F4'):
    """An app window: a title bar with three dots."""
    x, y, w, h = b
    s.rect(*b, fill, edge, .4, r=1.6)
    s.rect(x + .2, y + .2, w - .4, 7.0, bar, None, r=1.4)
    s.rect(x + .2, y + 4.0, w - .4, 3.2, bar, None)
    for k, c in enumerate(('#E8796B', '#E9B949', '#6CBF7A')):
        s.circle(x + 4.0 + 3.6 * k, y + 3.7, 1.05, c)
    s.text(x + 16.6, baseline(y + 3.7, SMALL), title, SMALL, INK, 'bold')

NAME = 'architecture'
W, H = 300.0, 138.0
OK = P.OK
LEARN_PALE, USE_PALE, EXEC_PALE = '#EFECF7', '#E8F0FB', '#FBF1E6'

A = (4.0, 12.0, 74.0, 40.0)                                   # agent A, who explores
AGENTS = [(146.0 + 47.0 * k, 12.0, 44.0, 40.0) for k in range(3)]   # agents B, C, D, who reuse
FIELD = (4.0, 64.0, 292.0, 44.0)                             # MAVRA
PUB = (9.0, 70.0, 50.0, 32.0)
MEM = (70.0, 70.0, 122.0, 32.0)
MAINT = (202.0, 70.0, 42.0, 32.0)
RUN = (250.0, 70.0, 41.0, 32.0)
DB = (42.0, 116.0, 254.0, 18.0)
ETL = (6.0, 116.0, 26.0, 18.0)

LABELS = {
    'en': {
        'legend': (('1–2', 'publish', LEARN), ('3–5', 'use', EXEC), ('6–8', 'maintain and optimize', USE)),
        'agent': 'Agent', 'explores': 'explores once', 'reuses': 'every other agent reuses',
        'qa': 'Store revenue in March?', 'given': 'definition given', 'verified': 'verified',
        'qs': ('September?', 'Best month?', 'Q3 vs. Q2?'),
        'chip': 'Store revenue', 'one_sql': 'one SQL',
        'mavra': 'MAVRA', 'pub': 'Publish', 'pub_checks': ('answer matches', 'SQL replays', 'key unique'),
        'mem': 'Shared memory', 'all': 'all agents',
        'defs': (('Store revenue', 'v2', 'valid'), ('Return rate', 'v1', 'valid'), ('Catalog sales', 'v1', 'checking')),
        'checks': 'check results, shared',
        'maint': 'Maintain', 'maint_note': 'repair · optimize', 'once': 'once for all',
        'run': 'Run', 'run_note': 'on one snapshot', 'run_checks': ('version valid', 'conditions hold'),
        'db': 'SQL database', 'etl': 'Updates',
        'a3': 'definition', 'a4': 'SQL + version', 'a5': 'snapshot', 'a7': 'table versions', 'a8': 'new version',
    },
    'zh': {
        'legend': (('1–2', '发布', LEARN), ('3–5', '使用', EXEC), ('6–8', '维护与优化', USE)),
        'agent': '智能体', 'explores': '只探索一次', 'reuses': '其他智能体都复用',
        'qa': '3 月门店营业额？', 'given': '给出口径', 'verified': '核对正确',
        'qs': ('9 月营业额？', '哪个月最高？', '季度环比？'),
        'chip': '门店营业额', 'one_sql': '一条 SQL',
        'mavra': 'MAVRA', 'pub': '发布', 'pub_checks': ('答案一致', 'SQL 重放', '主键唯一'),
        'mem': '共享记忆', 'all': '所有智能体',
        'defs': (('门店营业额', 'v2', '有效'), ('退货率', 'v1', '有效'), ('目录营业额', 'v1', '待校验')),
        'checks': '共享的检查结果',
        'maint': '维护', 'maint_note': '修复 · 优化', 'once': '一次服务所有',
        'run': '执行', 'run_note': '在同一快照上', 'run_checks': ('版本有效', '前提成立'),
        'db': 'SQL 数据库', 'etl': '数据更新',
        'a3': '定义', 'a4': 'SQL + 版本', 'a5': '快照', 'a7': '表版本', 'a8': '新版本',
    },
}


# Icons ------------------------------------------------------------------------------------------------------

def icon_table(s, x, y, color=MUTED):
    """A small table: header and two rows; (x, y) top-left of a 6 x 5 mm glyph."""
    s.rect(x, y, 6.0, 5.0, WHITE, color, .3, r=.5)
    s.rect(x + .15, y + .15, 5.7, 1.4, color, None, r=.4)
    s.line(x, y + 3.2, x + 6.0, y + 3.2, color, .25)
    s.line(x + 3.0, y + 1.6, x + 3.0, y + 5.0, color, .25)


def icon_search(s, x, y, color=MUTED):
    s.circle(x + 2.3, y + 2.2, 1.7, None, color, .45)
    s.line(x + 3.5, y + 3.4, x + 5.3, y + 5.2, color, .6)


def icon_join(s, x, y, color=MUTED):
    s.circle(x + 1.4, y + 2.5, 1.3, None, color, .4)
    s.circle(x + 4.6, y + 2.5, 1.3, None, color, .4)
    s.line(x + 2.7, y + 2.5, x + 3.3, y + 2.5, color, .4)


def icon_sql(s, x, y, color=MUTED):
    s.rect(x, y, 7.2, 5.0, WHITE, color, .3, r=.6)
    s.text(x + 3.6, y + 3.6, 'SQL', 7.5, color, 'bold', 'center')


def icon_shield(s, cx, cy, color):
    """Shield with a tick: the publication checks."""
    r = 4.2
    s.poly([(cx, cy - r), (cx + r * .85, cy - r * .62), (cx + r * .78, cy + r * .2), (cx, cy + r),
            (cx - r * .78, cy + r * .2), (cx - r * .85, cy - r * .62)], color, None)
    s.poly([(cx - 1.7, cy), (cx - .4, cy + 1.3), (cx + 1.9, cy - 1.3)], None, WHITE, .7, closed=False)


def icon_cycle(s, cx, cy, color, r=3.4):
    """Two arcs with heads: recheck when the data changes."""
    for a0 in (math.radians(200), math.radians(20)):
        pts = [(cx + r * math.cos(a0 + t * math.radians(130)), cy + r * math.sin(a0 + t * math.radians(130)))
               for t in (0, 1 / 3, 2 / 3, 1)]
        s.curve(*pts, stroke=color, sw=.7)
        a = a0 + math.radians(130)
        s.head(cx + r * math.cos(a), cy + r * math.sin(a), a + math.pi / 2, color, 1.6)


def icon_gauge(s, cx, cy, color, r=3.4):
    """Speed gauge: optimization."""
    pts = [(cx + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a))) for a in range(0, 181, 15)]
    s.poly(pts, None, color, .7, closed=False)
    a = math.radians(40)
    s.line(cx, cy, cx + .85 * r * math.cos(a), cy - .85 * r * math.sin(a), color, .7)
    s.circle(cx, cy, .7, color)


def icon_snapshot(s, cx, cy, color):
    """Camera: one snapshot."""
    s.rect(cx - 4.0, cy - 2.4, 8.0, 5.4, color, None, r=.9)
    s.rect(cx - 1.6, cy - 3.5, 3.2, 1.4, color, None, r=.4)
    s.circle(cx, cy + .3, 1.8, WHITE)
    s.circle(cx, cy + .3, 1.0, color)


def icon_bolt(s, x, y, color):
    s.poly([(x + 2.2, y), (x, y + 3.0), (x + 1.6, y + 3.0), (x + .9, y + 5.4), (x + 3.4, y + 2.0),
            (x + 1.8, y + 2.0), (x + 2.9, y)], color, None)


def icon_updates(s, x, y, color=MUTED):
    """A stack of update batches."""
    for k in (2, 1, 0):
        s.rect(x + 1.4 * k, y + 1.4 * (2 - k), 11.0, 8.0, WHITE, SOFT, .3, r=.8)
    for r_ in range(3):
        s.circle(x + 2.4, y + 4.9 + 1.9 * r_, .45, AMBER)
        s.rect(x + 3.6, y + 4.5 + 1.9 * r_, 5.6, .8, '#D9D5CE', None, r=.3)


# Pieces -----------------------------------------------------------------------------------------------------

def agent_window(s, b, title):
    x, y, w, h = b
    window(s, b, title)


def group(s, x0, x1, y, label, color):
    """A header over a group of agents: a pill and a bracket line under it."""
    pw = pill_width(label)
    s.line(x0, y + 3.4, x1, y + 3.4, color, .45)
    s.line(x0, y + 3.4, x0, y + 5.0, color, .45)
    s.line(x1, y + 3.4, x1, y + 5.0, color, .45)
    s.rect((x0 + x1 - pw) / 2 - 1.0, y - 3.0, pw + 2.0, 6.6, WHITE, None)
    pill(s, (x0 + x1 - pw) / 2, y, label, color)


def def_card(s, x, y, w, name, ver, state):
    """One definition in the shared memory: name, then state dot and version pill."""
    colour = {'valid': OK, '有效': OK}.get(state, P.PENDING)
    s.rect(x, y, w, 12.6, WHITE, '#C9D3E6', .35, r=1.0)
    s.rect(x, y, 1.3, 12.6, colour, None, r=.6)
    s.text(x + 3.2, y + 5.0, name, SMALL, INK, 'bold', width=w - 4.4)
    s.circle(x + 4.4, y + 9.2, 1.0, colour)
    s.text(x + 6.4, y + 10.4, state, SMALL, MUTED)
    pill(s, x + w - 2.0 - pill_width(ver), y + 9.2, ver, USE, h=4.4)


def check_row(s, x, y, label, size=SMALL):
    mark(s, x + 1.4, y - 1.2, 'ok', OK)
    return s.text(x + 4.2, y, label, size, INK)


def module(s, b, title, note, color, pale):
    """A MAVRA module: tinted header with the title and a muted note."""
    x, y, w, h = b
    panel(s, b, color, WHITE, .5)
    s.rect(x + .25, y + .25, w - .5, 9.0, pale, None, r=1.4)
    s.rect(x + .25, y + 5.0, w - .5, 4.25, pale, None)
    s.text(x + 3.0, baseline(y + 4.9, TITLE - 1), title, TITLE - 1, INK, 'bold')
    if note:
        s.text(x + w - 3.0, baseline(y + 4.9, SMALL), note, SMALL, MUTED, align='right')


def arrow_label(s, x, y, label, color, align='left'):
    s.text(x, y, label, SMALL, color, align=align)


def draw(s, lang):
    L = LABELS[lang]
    text, route = s.text, s.route

    # Agents ---------------------------------------------------------------------------------------------
    x, y, w, h = A
    group(s, x, x + w, y - 6.0, L['explores'], LEARN)
    agent_window(s, A, f"{L['agent']} A")
    bubble(s, (x + 3.0, y + 10.0, w - 6.0, 13.0), '#F7F6FB', '#D5CFE8')
    text(x + 5.4, baseline(y + 14.6, NOTE), L['qa'], NOTE, INK, 'bold', width=w - 11.0)
    text(x + 5.4, baseline(y + 19.6, SMALL), L['given'], SMALL, LEARN)
    ix = x + 4.0
    for draw_icon, adv in ((icon_table, 8.4), (icon_search, 7.4), (icon_join, 8.2), (icon_sql, 9.6)):
        draw_icon(s, ix, y + 27.4)
        ix += adv
    route([(ix - .4, y + 29.9), (ix + 3.4, y + 29.9)], MUTED, THIN, length=1.6)
    check_row(s, ix + 4.2, y + 31.4, L['verified'])

    group(s, AGENTS[0][0], AGENTS[-1][0] + AGENTS[-1][2], y - 6.0, L['reuses'], EXEC)
    for k, b in enumerate(AGENTS):
        bx, by, bw, bh = b
        agent_window(s, b, f"{L['agent']} {'BCD'[k]}")
        bubble(s, (bx + 3.0, by + 10.0, bw - 6.0, 8.0), '#FBF7F1', '#EBD9C2')
        text(bx + 5.0, baseline(by + 14.0, SMALL), L['qs'][k], SMALL, INK, 'bold', width=bw - 10.0)
        s.rect(bx + 3.0, by + 21.0, bw - 6.0, 8.6, USE_PALE, '#B9CBEA', .35, r=1.0)
        text(bx + 5.0, baseline(by + 25.3, SMALL), L['chip'], SMALL, ACC_DK, width=bw - 11.0 - pill_width('v2'))
        pill(s, bx + bw - 5.0 - pill_width('v2'), by + 25.3, 'v2', USE, h=4.6)
    # more agents
    for k in range(3):
        s.circle(AGENTS[-1][0] + AGENTS[-1][2] + 1.6 + 1.5 * k, 32.0, .45, MUTED)
    # one SQL each
    for b in AGENTS:
        icon_bolt(s, b[0] + 4.0, b[1] + 32.0, EXEC)
        text(b[0] + 8.4, b[1] + 36.4, L['one_sql'], SMALL, EXEC)
        mark(s, b[0] + b[2] - 6.0, b[1] + 35.2, 'ok', OK)

    # Legend between the agents ------------------------------------------------------------------------
    lx, ly = 88.0, 18.0
    for steps, label, color in L['legend']:
        legend_pill(s, lx, ly, label, color, steps)
        ly += 8.6
    route([(lx, ly + 1.0), (lx + 13.0, ly + 1.0)], INK, THICK, length=HEAD)
    text(lx + 15.4, baseline(ly + 1.0, SMALL), {'en': 'writes shared memory', 'zh': '写入共享记忆'}[lang], SMALL, MUTED)

    # MAVRA field --------------------------------------------------------------------------------------
    fx, fy, fw, fh = FIELD
    s.rect(*FIELD, P.FIELD, '#C9D3E6', .45, r=2.4)
    s.rect(fx + 3.0, fy - 2.6, 1.1, 5.2, ACC_DK)
    text(fx + 5.6, baseline(fy, TITLE), L['mavra'], TITLE, ACC_DK, 'bold')

    # Publish
    module(s, PUB, L['pub'], None, LEARN, LEARN_PALE)
    px, py, pw, ph = PUB
    icon_shield(s, px + pw - 7.5, py + 4.9, LEARN)
    for k, lab in enumerate(L['pub_checks']):
        check_row(s, px + 4.0, py + 16.6 + 6.4 * k, lab)

    # Shared memory
    mx, my, mw, mh = MEM
    node(s, MEM, 2.6)
    s.rect(mx + .25, my + .25, mw - .5, 9.0, USE_PALE, None, r=.8)
    text(mx + 3.0, baseline(my + 4.9, TITLE - 1), L['mem'], TITLE - 1, INK, 'bold')
    pill(s, mx + mw - 3.0 - pill_width(L['all']), my + 4.9, L['all'], USE, h=5.0)
    cw = (mw - 6.0 - 2 * 3.0) / 3
    for k, (name, ver, state) in enumerate(L['defs']):
        def_card(s, mx + 3.0 + k * (cw + 3.0), my + 12.0, cw, name, ver, state)
    # shared check results: one strip of results under the cards
    sy = my + 28.0
    text(mx + 3.0, sy + 1.0, L['checks'], SMALL, MUTED)
    cx0 = mx + 6.0 + measure(L['checks'], SMALL)
    for k, kind in enumerate(('ok', 'ok', 'ok', 'ok', 'wait', 'ok')):
        bx = cx0 + 6.2 * k
        s.rect(bx, sy - 2.6, 5.0, 4.4, AMBER_PALE if kind == 'wait' else WHITE,
               AMBER if kind == 'wait' else '#C9D3E6', .3, r=.7)
        if kind == 'ok':
            mark(s, bx + 2.5, sy - .4, 'ok', OK)
        else:
            text(bx + 2.5, sy + 1.0, '?', SMALL, WAIT, 'bold', 'center')

    # Maintain
    module(s, MAINT, L['maint'], None, USE, USE_PALE)
    ax, ay, aw, ah = MAINT
    icon_cycle(s, ax + 12.0, ay + 16.6, USE)
    icon_gauge(s, ax + 29.0, ay + 18.2, USE)
    text(ax + aw / 2, ay + 25.4, L['maint_note'], SMALL, MUTED, align='center')
    text(ax + aw / 2, ay + 30.4, L['once'], SMALL, USE, 'bold', align='center')

    # Run on one snapshot
    module(s, RUN, L['run'], None, EXEC, EXEC_PALE)
    rx, ry, rw, rh = RUN
    icon_snapshot(s, rx + rw - 8.0, ry + 5.0, EXEC)
    text(rx + 3.0, ry + 15.0, L['run_note'], SMALL, MUTED)
    for k, lab in enumerate(L['run_checks']):
        check_row(s, rx + 3.0, ry + 22.0 + 6.0 * k, lab)

    # Database -----------------------------------------------------------------------------------------
    dx, dy, dw, dh = DB
    slab(s, DB)
    text(dx + 4.0, baseline(dy + dh / 2, TITLE - 1), L['db'], TITLE - 1, INK, 'bold')
    tables = (('`store_sales`', (1, 2)), ('`date_dim`', ()), ('`item`', ()), ('`store`', ()), ('`customer`', ()))
    tx = dx + 52.0
    for label, changed in tables:
        tw = 30.0
        table_card(s, tx, tw, dy + 2.4, dh - 4.8, label, changed, size=SMALL)
        tx += tw + 6.0
    ex_, ey_, ew_, eh_ = ETL
    icon_updates(s, ex_ + 2.0, ey_ + 1.0)
    text(ex_ + ew_ / 2 - 3.0, ey_ + eh_ + .2, L['etl'], SMALL, MUTED, align='center')

    # Arrows -------------------------------------------------------------------------------------------
    wb = A[1] + A[3]                                   # bottom of the agent windows
    bus = wb + 7.0
    # 1 the verified session becomes a candidate; 2 the checks publish it
    ax1 = PUB[0] + 24.0
    route([(ax1, wb), (ax1, PUB[1])], LEARN, THIN, length=HEAD)
    step(s, ax1 + 4.6, (wb + PUB[1]) / 2, 1, LEARN, r=2.6)
    route([(PUB[0] + PUB[2], my + 18.0), (mx, my + 18.0)], LEARN, THICK, length=HEAD)
    step(s, (PUB[0] + PUB[2] + mx) / 2, my + 13.0, 2, LEARN, r=2.6)

    # 3 the definition goes to every agent; 4 their SQL with the declared version; 5 run on a snapshot
    xs = [b[0] + 10.0 for b in AGENTS]
    route([(xs[0], my - 2.6), (xs[0], wb)], EXEC, THIN, length=HEAD)
    route([(xs[0], bus), (xs[-1], bus)], EXEC, THIN, heads=None)
    for xb in xs[1:]:
        route([(xb, bus), (xb, wb)], EXEC, THIN, length=HEAD)
    y3 = (wb + bus) / 2
    step(s, xs[0] - 4.6, y3, 3, EXEC, r=2.6)
    arrow_label(s, xs[0] + 2.0, baseline(y3, SMALL), L['a3'], EXEC)

    x4 = RUN[0] + RUN[2] / 2 + 6.0
    route([(x4, wb), (x4, RUN[1])], EXEC, THIN, length=HEAD)
    step(s, x4 + 4.6, y3, 4, EXEC, r=2.6)
    arrow_label(s, x4 - 2.0, baseline(y3, SMALL), L['a4'], EXEC, align='right')

    x5 = RUN[0] + RUN[2] / 2
    y57 = (RUN[1] + RUN[3] + DB[1] - 2.8) / 2
    route([(x5, RUN[1] + RUN[3]), (x5, DB[1] - 2.8)], EXEC, THIN, dash=DASH, length=HEAD)
    step(s, x5 + 4.6, y57, 5, EXEC, r=2.6)
    arrow_label(s, x5 + 8.4, baseline(y57, SMALL), L['a5'], EXEC)

    # 6 updates change tables; 7 maintenance reads table versions; 8 it writes the new version
    route([(ETL[0] + ETL[2] - 2.0, dy + dh / 2), (dx, dy + dh / 2)], USE, THIN, length=HEAD)
    step(s, (ETL[0] + ETL[2] + dx) / 2 - 1.0, dy + dh / 2 - 4.6, 6, USE, r=2.6)
    x7 = MAINT[0] + MAINT[2] / 2
    route([(x7, DB[1] - 2.8), (x7, MAINT[1] + MAINT[3])], USE, THIN, dash=DASH, length=HEAD)
    step(s, x7 + 4.6, y57, 7, USE, r=2.6)
    arrow_label(s, x7 - 2.0, baseline(y57, SMALL), L['a7'], USE, align='right')
    route([(MAINT[0], my + 18.0), (mx + mw + 2.6, my + 18.0)], USE, THICK, length=HEAD)
    step(s, (MAINT[0] + mx + mw + 2.6) / 2, my + 13.0, 8, USE, r=2.6)

if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
