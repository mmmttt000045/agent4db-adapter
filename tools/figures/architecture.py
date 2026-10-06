"""Figure 2: the MAVRA architecture as a vector drawing.

The layout reads left to right: the learning side (agent A, admission) writes
into the shared store in the centre; condition maintenance and bounded repair
sit under the store, so their write-backs go up into it; the use side
(lookup) and the execution side (same-snapshot validation) read from it on
the right, and the revision m^r a lookup returns is the one a query declares.
PostgreSQL is one storage slab at the bottom.

Step numbers and arrows are coloured by path (learning 1-3, use 4-7,
execution 8-9, as in the caption of overleaf/figures/architecture.tex); line
weight says what an arrow does: thin = call or response, thick = write to the
shared store, dashed = read of database state.
Coordinates are millimetres from the top-left at printed size: the figure
spans \\textwidth (178 mm). Every label is checked against the room it has.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import PT  # noqa: E402
import style  # noqa: E402
from style import (ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FACE, FIELD, INK, MUTED,  # noqa: E402
                   RED, RULE, SIDE, SLATE, TOP, WHITE)

NAME = 'architecture'
W, H = style.TEXTWIDTH, 67

TITLE, BODY, NOTE, STEP = 7.0, 6.4, 6.0, 5.6    # font sizes, pt (acmart \scriptsize is 6, \footnotesize 7)
LEARN, USE, EXEC_C = '#7A68B0', ACC, '#C97A1E'  # path colours: learning, use, execution
THIN, THICK = .22, .5                            # call or response; write to the shared store

LABELS = {
    'en': {
        'agent_a': 'Agent A', 'extractor': 'LLM extractor',
        'agents': 'Agents B, C, …', 'agents_note': 'questions with metric names only',
        'middleware': 'MAVRA middleware',
        'admission': 'Admission', 'candidate': 'candidate',
        'defs': 'Definitions', 'valid': 'valid', 'pending': 'pending', 'revoked': 'invalid',
        'results': 'Check results', 'results_key': 'one per',
        'maint': 'Condition maintenance', 'maint_note': 'reuse · coalesce · wait',
        'repair': 'Bounded repair', 'repair_note': 'unique filter',
        'lookup': 'Lookup', 'lookup_note': 'version check',
        'tracker': 'Version tracker', 'tracker_note': 'statistics, triggers',
        'exec': ('Same-snapshot', 'validation'), 'check': 'check $C(m^r)$',
        'run': 'run SQL', 'pg': 'PostgreSQL',
        'pg_note': 'tables · DML statistics · version triggers',
        'etl': 'ETL and writers', 'updates': 'updates', 'publish': 'publish',
        'reuse': 'reuse', 'to_maint': 'pending', 'failed': 'failed $c$',
        'chain': 'provenance / candidate', 'versions': 'versions',
        'tracker_read': 'DML stats, tx versions', 'snapshot': 'one snapshot',
        'paths': ('learning path', 'use path', 'execution path'),
        'lines': ('call / response', 'shared-store write', 'read of database state'),
    },
    'zh': {
        'agent_a': '智能体 A', 'extractor': '大模型提取器',
        'agents': '智能体 B、C 等', 'agents_note': '只给指标名的问题',
        'middleware': 'MAVRA 中间件',
        'admission': '准入', 'candidate': '候选',
        'defs': '定义', 'valid': '有效', 'pending': '待验证', 'revoked': '已失效',
        'results': '检查结果', 'results_key': '每个键一条',
        'maint': '条件维护', 'maint_note': '复用 · 合并 · 等待',
        'repair': '有界修复', 'repair_note': '唯一过滤',
        'lookup': '查找', 'lookup_note': '版本比较',
        'tracker': '版本跟踪', 'tracker_note': '统计、触发器',
        'exec': ('同快照验证', None), 'check': '核对 $C(m^r)$',
        'run': '执行 SQL', 'pg': 'PostgreSQL',
        'pg_note': '表 · DML 统计 · 版本触发器',
        'etl': 'ETL 与写入方', 'updates': '更新', 'publish': '发布',
        'reuse': '复用', 'to_maint': '待验证', 'failed': '条件失败',
        'chain': '答案溯源／候选', 'versions': '版本',
        'tracker_read': 'DML 统计、事务版本', 'snapshot': '同一快照',
        'paths': ('学习路径', '使用路径', '执行路径'),
        'lines': ('调用／返回', '写入共享库', '读取数据库状态'),
    },
}

# Boxes (x, y, w, h).
ADM = (4, 24, 21, 24.5)
STORE = (33, 24, 68, 13.3)
SPLIT = 71                               # definitions | check results inside the store
REPAIR = (33, 40.5, 28, 8)
MAINT = (70.4, 40.5, 30.6, 8)
LOOKUP = (109, 24, 27, 9.5)
TRACK = (109, 40.5, 27, 8)
EXEC = (144, 24, 31, 24.5)
FIELD_BOX = (1.5, 20, 175.5, 31.5)
NODE_Y, NODE_H = 6, 8.4                  # agent front faces
PG = (31, 57.0, 144, 9.4)


def mid(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


def baseline(y_center, size):
    """Baseline that centres capitals and digits on y_center."""
    return y_center + .34 * size * PT


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def node(x, w, d=1.5):
        """Front face with a top and a right face behind it."""
        y, h = NODE_Y, NODE_H
        s.poly([(x, y), (x + d, y - d), (x + w + d, y - d), (x + w, y)], TOP, EDGE, .12)
        s.poly([(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)],
               SIDE, EDGE, .12)
        rect(x, y, w, h, WHITE, EDGE, .16, r=.35)

    def agent(x, letter, w=9.5):
        node(x, w)
        y = NODE_Y
        text(x + 1.5, y + 4.9, letter, TITLE + .6, INK, 'bold')
        bx, bw = x + 4.3, w - 5.6               # speech bubble with two lines
        rect(bx, y + 1.4, bw, 4.0, ACC_PALE, ACC, .12, r=.7)
        for k, length in enumerate((bw - 1.4, bw - 2.3)):
            s.line(bx + .7, y + 2.75 + 1.3 * k, bx + .7 + length, y + 2.75 + 1.3 * k, ACC, .22)
        s.circle(x + 2.3, y + 6.9, .45, ACC)
        s.line(x + 3.6, y + 6.9, x + w - 1.4, y + 6.9, RULE, .3)

    def gate(cx, cy, r=2.0):
        """Admission check: candidates pass only between its two bars."""
        s.poly([(cx - r, cy), (cx, cy - r), (cx + r, cy), (cx, cy + r)], WHITE, ACC, .2)
        for dx in (-.42 * r, .42 * r):
            s.line(cx + dx, cy - .55 * r, cx + dx, cy + .55 * r, ACC, .24)

    def mark(x, y, kind):
        """Check-result mark centred on (x, y): holds, fails, or not yet known."""
        if kind == 'ok':
            s.poly([(x - .62, y), (x - .15, y + .5), (x + .65, y - .55)], None, ACC, .24,
                   closed=False)
        elif kind == 'fail':
            s.line(x - .5, y - .5, x + .5, y + .5, RED, .24)
            s.line(x - .5, y + .5, x + .5, y - .5, RED, .24)
        else:
            s.circle(x, y, .42, AMBER)

    def chip(x, y, cond, kind):
        rect(x, y, 4.4, 2.3, FACE, EDGE, .1, r=.45)
        text(x + .5, y + 1.7, f'$c_{cond}$', 5.4, INK)
        mark(x + 3.35, y + 1.15, kind)

    def step(x, y, n, color):
        s.circle(x, y, 1.45, color)
        text(x, baseline(y, STEP), str(n), STEP, WHITE, 'bold', 'center')

    def box(b, fill=WHITE):
        rect(*b, fill, EDGE, .16, r=.6)

    def titled(b, title, note, pad=1.8, reserve=0):
        """Box with a bold title and a note; reserve keeps room on the right."""
        x, y, w, h = b
        box(b)
        text(x + pad, y + 3.6, title, TITLE, INK, 'bold', width=w - 2 * pad - reserve)
        if note:
            text(x + pad, y + 6.8, note, NOTE, MUTED, width=w - 2 * pad)

    def gap_label(x0, x1, y, label, color=MUTED):
        """Label centred over an arrow that crosses the gap from x0 to x1."""
        text((x0 + x1) / 2, y, label, NOTE, color, 'sans', 'center', width=x1 - x0 - .6)

    # Field ----------------------------------------------------------------
    rect(*FIELD_BOX, FIELD, None, r=1.4)
    rect(STORE[0], 20.9, .55, 2.6, ACC)
    text(STORE[0] + 1.5, 23.0, L['middleware'], TITLE - .4, ACC_DK, 'bold')

    # Agents and extractor -------------------------------------------------
    a_x, x_x, x_w = 4, 17, 14
    agent(a_x, 'A')
    text(a_x + 4.75, 3.2, L['agent_a'], TITLE, INK, 'bold', 'center')
    node(x_x, x_w)
    text(x_x + x_w / 2, 3.2, L['extractor'], TITLE, INK, 'bold', 'center')
    cols = [(x_x + 2.6, (8.2, 12.2)), (x_x + 7, (7.6, 10.2, 12.8)), (x_x + 11.4, (8.9, 11.5))]
    for (xa, ya), (xb, yb) in zip(cols, cols[1:]):
        for y1 in ya:
            for y2 in yb:
                s.line(xa, y1, xb, y2, RULE, .14)
    for xc, ys in cols:
        for yc in ys:
            s.circle(xc, yc, .62, WHITE, ACC, .2)

    b4, b8 = mid(LOOKUP)[0], mid(EXEC)[0]
    b_xs = (b4 - 4.75, b4 + 9.25, b4 + 23.25)
    for x, letter in zip(b_xs, 'BCD'):
        agent(x, letter)
    for k in range(3):
        s.circle(b_xs[-1] + 13.2 + 1.6 * k, NODE_Y + NODE_H / 2, .32, EDGE)
    w = text(b_xs[0], 3.2, L['agents'], TITLE, INK, 'bold')
    text(b_xs[0] + w + 1.6, 3.2, L['agents_note'], NOTE, MUTED, width=W - b_xs[0] - w - 2.5)

    # Legend: step colours by path, line kinds -----------------------------
    lx = 50
    for k, (label, color, steps) in enumerate(zip(L['paths'], (LEARN, USE, EXEC_C),
                                                  ('1–3', '4–7', '8–9'))):
        y = 4.6 + 3.8 * k
        rect(lx, y - 1.4, 6.6, 2.8, color, None, r=1.4)
        text(lx + 3.3, baseline(y, STEP), steps, STEP, WHITE, 'bold', 'center')
        text(lx + 7.8, baseline(y, NOTE), label, NOTE, INK)
    kx = 77
    for k, (label, sw, color, dash) in enumerate(zip(L['lines'], (THIN, THICK, THIN),
                                                     (INK, INK, SLATE), (None, None, (.9, .6)))):
        y = 4.6 + 3.8 * k
        route([(kx, y), (kx + 6.5, y)], color, sw, dash=dash, length=1.1)
        text(kx + 8.0, baseline(y, NOTE), label, NOTE, MUTED, width=b_xs[0] - kx - 10)

    # Learning path: agent A -> admission -> store -------------------------
    ax, ay, aw, ah = ADM
    box(ADM)
    a1, a2 = a_x + 4.75, x_x + x_w / 2
    route([(a1, NODE_Y + NODE_H), (a1, ay)], LEARN, THIN)
    step(a1 - 2.8, 21.8, 1, LEARN)
    route([(a2, ay), (a2, NODE_Y + NODE_H)], LEARN, THIN, heads='both')
    text(a2 + 2, 18.7, L['chain'], NOTE, MUTED)
    step(a2 + 2.8, 21.8, 2, LEARN)
    # Candidate (answer provenance: queries and arithmetic) through the checks.
    cx, cy = ax + 2.0, ay + 2.2
    rect(cx + .9, cy - .9, 8.6, 9.2, FACE, EDGE, .12, r=.4)
    rect(cx, cy, 8.6, 9.2, WHITE, EDGE, .15, r=.4)
    s.line(cx + 2, cy + 2.2, cx + 2, cy + 6.8, LEARN, .2)
    for k in range(3):
        yy = cy + 2.2 + 2.3 * k
        s.circle(cx + 2, yy, .55, LEARN)
        s.line(cx + 3.6, yy, cx + 7.2 - .9 * (k == 2), yy, RULE, .32)
    text(cx + 4.3, cy + 12.6, L['candidate'], NOTE, MUTED, 'sans', 'center')
    gx, gy = ax + aw - 4.6, cy + 4.6
    route([(cx + 8.6, gy), (gx - 2.0, gy)], LEARN, .18, length=1.0)
    gate(gx, gy)
    text(gx, cy + 12.6, 'G1–G7', NOTE, ACC_DK, 'sans', 'center')
    text(ax + aw / 2, ay + ah - 2.4, L['admission'], TITLE, INK, 'bold', 'center', width=aw - 2)
    sx = STORE[0]
    route([(gx + 2.0, gy), (sx, gy)], LEARN, THICK)
    gap_label(ax + aw, sx, gy - 1.2, L['publish'])
    step((ax + aw + sx) / 2, gy + 2.7, 3, LEARN)

    # Shared store: definitions | check results ---------------------------
    x, y, w, h = STORE
    rect(x + 1, y + 1, w, h, SIDE, EDGE, .12, r=.6)
    box(STORE)
    rect(x, y, w, 4.4, ACC_PALE, None, r=.6)
    rect(x, y + 2.2, w, 2.2, ACC_PALE, None)
    s.line(x, y + 4.4, x + w, y + 4.4, RULE, .14)
    s.line(SPLIT, y, SPLIT, y + h, RULE, .14)
    tw = text(x + 1.8, y + 3.2, L['defs'], TITLE, INK, 'bold')
    text(SPLIT - 1.6, y + 3.2, '$m^r=(B,I,C,E,r)$', BODY, INK, align='right',
         width=SPLIT - x - 5 - tw)
    rows = [('$m_1^{3}$', L['valid'], ACC_DK, ((1, 'ok'), (2, 'ok'))),
            ('$m_2^{1}$', L['pending'], AMBER, ((2, 'ok'), (3, 'wait'))),
            ('$m_3^{2}$', L['revoked'], RED, ((4, 'fail'),))]
    for k, (name, state, col, conds) in enumerate(rows):
        yy = y + 5.0 + 2.65 * k
        rect(x + 1.8, yy + .1, .6, 2.1, col)
        text(x + 3.2, yy + 1.75, name, BODY, INK)
        text(x + 9.0, yy + 1.75, state, NOTE, col)
        for j, (cond, kind) in enumerate(conds):
            chip(SPLIT - 1.6 - 4.4 * (len(conds) - j) - .6 * (len(conds) - 1 - j), yy, cond, kind)
    text(SPLIT + 1.6, y + 3.2, L['results'], TITLE, INK, 'bold', width=x + w - SPLIT - 3.2)
    for j, (cond, kind) in enumerate(((1, 'ok'), (2, 'ok'), (3, 'wait'), (4, 'fail'))):
        chip(SPLIT + 1.6 + 5.0 * j, y + 5.2, cond, kind)
    kw = text(SPLIT + 1.6, y + h - 1.6, L['results_key'], NOTE, MUTED)
    text(x + w - 1.6, y + h - 1.6, r'$(\mathrm{id}(c),\,V(\mathrm{dep}(c)))$', NOTE, INK,
         align='right', width=x + w - SPLIT - 4.4 - kw)

    # Use path: lookup, maintenance, repair --------------------------------
    titled(MAINT, L['maint'], L['maint_note'])
    titled(REPAIR, L['repair'], L['repair_note'], reserve=6)
    rx, ry, rw, rh = REPAIR
    gate(rx + rw - 3.6, ry + 3.0, 1.6)
    text(rx + rw - 3.6, ry + 6.8, 'G8', NOTE, ACC_DK, 'sans', 'center')

    lx_, ly, lw, lh = LOOKUP
    box(LOOKUP)
    tw = text(lx_ + 1.8, ly + 3.9, L['lookup'], TITLE, INK, 'bold')
    text(lx_ + 3.0 + tw, ly + 3.9, '`find_metric`', BODY, INK, width=lw - 4.8 - tw)
    text(lx_ + 1.8, ly + 7.3, L['lookup_note'], NOTE, MUTED, width=lw - 3.6)
    titled(TRACK, L['tracker'], L['tracker_note'])

    # Agents: one bus to both entry points.
    bus_y = 17.2
    for xc in (bx + 4.75 for bx in b_xs):
        route([(xc, NODE_Y + NODE_H), (xc, bus_y)], INK, .2, heads=None)
    route([(b4, bus_y), (b8, bus_y)], INK, .2, heads=None)
    route([(b4, bus_y), (b4, ly)], USE, THIN)
    step(b4 - 2.8, 21.6, 4, USE)

    store_right = STORE[0] + STORE[2]
    route([(store_right, ly + 3.5), (lx_, ly + 3.5)], USE, THIN)
    gap_label(store_right, lx_, ly + 2.4, '$m^r$')
    mx, my, mw, mh = MAINT
    lane = 105
    route([(lx_, ly + 7.5), (lane, ly + 7.5), (lane, my + 4.0), (mx + mw, my + 4.0)], USE, THIN,
          radius=.8)
    step(store_right + 1.85, (STORE[1] + STORE[3] + my) / 2, 5, USE)
    text(lane + 1.3, (STORE[1] + STORE[3] + my) / 2 + .9, L['to_maint'], NOTE, MUTED)

    vx = SPLIT + 15
    route([(vx, my), (vx, STORE[1] + STORE[3])], USE, THICK, heads='both', length=1.0)
    step(vx - 2.9, (STORE[1] + STORE[3] + my) / 2, 6, USE)
    text(vx + 1.4, (STORE[1] + STORE[3] + my) / 2 + .9, L['reuse'], NOTE, MUTED)
    route([(mx, my + 4.0), (rx + rw, my + 4.0)], USE, THIN, length=1.0)
    gap_label(rx + rw, mx, my + 2.9, L['failed'], RED)
    step((rx + rw + mx) / 2, my + 6.6, 7, USE)
    fx = rx + 14
    route([(fx, ry), (fx, STORE[1] + STORE[3])], USE, THICK, length=1.0)
    text(fx + 1.4, (STORE[1] + STORE[3] + ry) / 2 + .9, '$m^{r+1}$', NOTE, MUTED)

    tx, ty, tw_, th = TRACK
    vt = tx + 18
    route([(vt, ty), (vt, ly + lh)], SLATE, THIN, dash=(.9, .6), length=1.0)
    text(vt + 1.3, (ly + lh + ty) / 2 + .9, L['versions'], NOTE, SLATE)

    # Execution path: same-snapshot validation -----------------------------
    ex, ey, ew, eh = EXEC
    box(EXEC)
    route([(b8, bus_y), (b8, ey)], EXEC_C, THIN)
    step(b8 - 2.8, 21.6, 8, EXEC_C)
    route([(lx_ + lw, ly + 3.5), (ex, ly + 3.5)], EXEC_C, THIN)
    gap_label(lx_ + lw, ex, ly + 2.4, '$m^r$')
    first, second = L['exec']
    text(ex + 1.8, ey + 3.9, first, TITLE, INK, 'bold', width=ew - 3.6)
    top = ey + 3.9
    if second:
        top += 3.0
        text(ex + 1.8, top, second, TITLE, INK, 'bold', width=ew - 3.6)
    text(ex + 1.8, top + 3.3, '`run_sql`', BODY, INK)
    fx, fy, fw, fh = ex + 1.8, ey + 12.4, ew - 3.6, 7.0
    rect(fx, fy, fw, fh, None, EXEC_C, .18, r=.6, dash=(.8, .5))
    dw = 4.4
    rect(fx + fw - dw - 1.2, fy - 1.1, dw, 2.2, WHITE, None)
    text(fx + fw - 1.2 - dw / 2, fy + .8, '$D_s$', BODY, EXEC_C, align='center')
    for k, label in enumerate((L['check'], L['run'])):
        yy = fy + 2.9 + 2.7 * k
        mark(fx + 1.4, yy - .55, 'ok')
        text(fx + 2.8, yy, label, NOTE, INK, width=fw - 3.4)
    px, py, pw, ph = PG
    route([(b8, ey + eh), (b8, py - 1.3)], EXEC_C, THIN)
    step(b8 - 2.8, 52.2, 9, EXEC_C)
    text(b8 - 4.8, baseline(52.2, NOTE), L['snapshot'], NOTE, MUTED, align='right')

    # Database reads -------------------------------------------------------
    qx = mx + mw - 7
    route([(qx, py - 1.3), (qx, my + mh)], SLATE, THIN, dash=(.9, .6), length=1.0)
    text(qx + 1.3, 53.6, '$Q_c$', BODY, SLATE)
    vr = tx + 5
    route([(vr, py - 1.3), (vr, ty + th)], SLATE, THIN, dash=(.9, .6), length=1.0)
    text(vr + 1.3, 53.6, L['tracker_read'], NOTE, SLATE, width=b8 - 4.8 - 18 - vr)

    # PostgreSQL: one storage slab with table pages ------------------------
    d = 1.4
    s.poly([(px, py), (px + d, py - d), (px + pw + d, py - d), (px + pw, py)], TOP, EDGE, .14)
    s.poly([(px + pw, py), (px + pw + d, py - d), (px + pw + d, py + ph - d), (px + pw, py + ph)],
           SIDE, EDGE, .14)
    rect(px, py, pw, ph, FACE, EDGE, .18, r=.5)
    text(px + 2.4, py + 3.9, L['pg'], TITLE, INK, 'bold')
    text(px + 2.4, py + 7.3, L['pg_note'], NOTE, MUTED, width=44)
    changed = {(0, 4), (3, 1), (3, 5), (5, 2)}
    for k in range(6):
        x0 = px + 48 + 14.4 * k
        rect(x0 + .7, py + 1.0, 12.4, 7.2, SIDE, None, r=.35)
        rect(x0, py + 1.6, 12.4, 7.2, WHITE, EDGE, .12, r=.35)
        for c in range(6):
            cxx, cyy = x0 + 1.0 + (c % 3) * 3.6, py + 2.7 + (c // 3) * 2.9
            rect(cxx, cyy, 3.0, 2.2, AMBER_PALE if (k, c) in changed else FACE,
                 AMBER if (k, c) in changed else None, .1, r=.3)
    for k in range(3):
        s.circle(px + pw - 2.2 - 1.5 * k, py + ph - 1.2, .38, ACC)

    # Writers --------------------------------------------------------------
    dx0, dy0 = 4, 59.2
    for off in (1.6, .8, 0):
        rect(dx0 + off, dy0 - off, 11.5, 7.0, WHITE, EDGE, .13, r=.4)
    for k in range(3):
        s.circle(dx0 + 1.8, dy0 + 1.7 + 1.8 * k, .4, AMBER)
        s.line(dx0 + 3.0, dy0 + 1.7 + 1.8 * k, dx0 + 9.6, dy0 + 1.7 + 1.8 * k, RULE, .3)
    text(dx0, 55.6, L['etl'], TITLE - .4, INK, 'bold')
    yy = dy0 + 3.2
    route([(dx0 + 13.6, yy), (px, yy)], INK, THIN)
    gap_label(dx0 + 13.6, px, yy - 1.1, L['updates'])


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
