"""Figure 2: the MAVRA architecture as a vector drawing.

Agents sit on top, the MAVRA middleware in the middle, PostgreSQL as one
storage slab at the bottom. The numbered steps match the caption in
overleaf/figures/architecture.tex: learning path 1-3, use path 4-7,
execution path 8-9; dashed arrows are reads of database state.
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

LABELS = {
    'en': {
        'agent_a': 'Agent A', 'extractor': 'LLM extractor',
        'agents': 'Agents B, C, …', 'agents_note': 'questions with metric names only',
        'middleware': 'MAVRA middleware',
        'admission': 'Admission', 'candidate': 'candidate',
        'defs': 'Definitions', 'valid': 'valid', 'pending': 'pending',
        'revoked': 'revoked', 'verdicts': 'one verdict per',
        'maint': 'Condition maintenance', 'maint_note': 'reuse · merge · wait',
        'repair': 'Bounded repair', 'repair_note': 'unique filter',
        'lookup': 'Lookup', 'lookup_note': 'version check',
        'tracker': 'Version tracker', 'tracker_note': 'statistics, triggers',
        'exec': ('Snapshot-bound', 'execution'), 'check': 'check $C(m^r)$',
        'run': 'run SQL', 'pg': 'PostgreSQL',
        'pg_note': 'tables · DML statistics · version triggers',
        'etl': 'ETL and writers', 'updates': 'updates', 'publish': 'publish',
        'reuse': 'reuse', 'to_maint': 'pending', 'failed': 'failed $c$',
        'chain': 'chain / candidate', 'versions': 'versions',
        'snapshot': 'one snapshot',
        'legend': ('call / write', 'shared-store update', 'read of database state'),
    },
    'zh': {
        'agent_a': '智能体 A', 'extractor': '大模型提炼器',
        'agents': '智能体 B、C 等', 'agents_note': '只给指标名的问题',
        'middleware': 'MAVRA 中间层',
        'admission': '准入', 'candidate': '候选',
        'defs': '定义', 'valid': '有效', 'pending': '待验证',
        'revoked': '已撤销', 'verdicts': '每个键一条结论',
        'maint': '条件维护', 'maint_note': '复用 · 合并 · 等待',
        'repair': '有界修复', 'repair_note': '唯一过滤',
        'lookup': '查找', 'lookup_note': '版本比较',
        'tracker': '版本跟踪', 'tracker_note': '统计、触发器',
        'exec': ('绑定快照执行', None), 'check': '核对 $C(m^r)$',
        'run': '执行 SQL', 'pg': 'PostgreSQL',
        'pg_note': '表 · DML 统计 · 版本触发器',
        'etl': 'ETL 与写入方', 'updates': '更新', 'publish': '发布',
        'reuse': '复用', 'to_maint': '待验证', 'failed': '条件失败',
        'chain': '计算链／候选', 'versions': '版本',
        'snapshot': '同一快照',
        'legend': ('调用／写入', '共享库更新', '读取数据库状态'),
    },
}

# Boxes (x, y, w, h). Row A holds lookup-side work, row B what follows it.
ADM = (4, 26, 23, 21)
STORE = (36, 26, 34, 21)
MAINT = (79, 26, 31, 9.5)
REPAIR = (79, 38.5, 28, 8.5)
LOOKUP = (120, 26, 26.5, 9.5)
TRACK = (120, 38.5, 26.5, 8.5)
EXEC = (150.5, 26, 24.5, 21)
FIELD_BOX = (1.5, 20, 175.5, 30)
NODE_Y, NODE_H = 6, 8.4                  # agent front faces
PG = (31, 56.6, 144, 9.4)


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
        """Admission gate: candidates pass only between its two bars."""
        s.poly([(cx - r, cy), (cx, cy - r), (cx + r, cy), (cx, cy + r)], WHITE, ACC, .2)
        for dx in (-.42 * r, .42 * r):
            s.line(cx + dx, cy - .55 * r, cx + dx, cy + .55 * r, ACC, .24)

    def mark(x, y, kind):
        """Verdict mark centred on (x, y): holds, fails, or not yet known."""
        if kind == 'ok':
            s.poly([(x - .62, y), (x - .15, y + .5), (x + .65, y - .55)], None, ACC, .24,
                   closed=False)
        elif kind == 'fail':
            s.line(x - .5, y - .5, x + .5, y + .5, RED, .24)
            s.line(x - .5, y + .5, x + .5, y - .5, RED, .24)
        else:
            s.circle(x, y, .42, AMBER)

    def chip(x, y, cond, kind):
        rect(x, y, 4.7, 2.5, FACE, EDGE, .1, r=.45)
        text(x + .55, y + 1.8, f'$c_{cond}$', 5.4, INK)
        mark(x + 3.55, y + 1.25, kind)

    def step(x, y, n):
        s.circle(x, y, 1.45, ACC)
        text(x, baseline(y, STEP), str(n), STEP, WHITE, 'bold', 'center')

    def box(b, fill=WHITE):
        rect(*b, fill, EDGE, .16, r=.6)

    def titled(b, title, note, pad=1.8, note_style='sans', reserve=0):
        """Box with a bold title and a note; reserve keeps room on the right."""
        x, y, w, h = b
        box(b)
        text(x + pad, y + 3.9, title, TITLE, INK, 'bold', width=w - 2 * pad - reserve)
        if note:
            text(x + pad, y + 7.3, note, NOTE, MUTED, note_style, width=w - 2 * pad)

    # Fields -------------------------------------------------------------
    rect(*FIELD_BOX, FIELD, None, r=1.4)
    rect(STORE[0], 21.6, .55, 3.0, ACC)
    text(STORE[0] + 1.5, 24.2, L['middleware'], TITLE - .2, ACC_DK, 'bold')

    # Agents, extractor, legend -------------------------------------------
    a_x, x_x, x_w = 4, 17, 14
    agent(a_x, 'A')
    text(a_x + 4.75, 3.2, L['agent_a'], TITLE, INK, 'bold', 'center')
    node(x_x, x_w)
    text(x_x + x_w / 2, 3.2, L['extractor'], TITLE, INK, 'bold', 'center')
    # A small network inside the extractor.
    cols = [(x_x + 2.6, (8.2, 12.2)), (x_x + 7, (7.6, 10.2, 12.8)), (x_x + 11.4, (8.9, 11.5))]
    for (xa, ya), (xb, yb) in zip(cols, cols[1:]):
        for y1 in ya:
            for y2 in yb:
                s.line(xa, y1, xb, y2, RULE, .14)
    for xc, ys in cols:
        for yc in ys:
            s.circle(xc, yc, .62, WHITE, ACC, .2)

    b_xs = (121, 135, 149)
    for x, letter in zip(b_xs, 'BCD'):
        agent(x, letter)
    for k in range(3):
        s.circle(163.6 + 1.6 * k, NODE_Y + NODE_H / 2, .32, EDGE)
    w = text(b_xs[0], 3.2, L['agents'], TITLE, INK, 'bold')
    text(b_xs[0] + w + 1.6, 3.2, L['agents_note'], NOTE, MUTED, width=W - b_xs[0] - w - 2.5)

    lx = 50
    for k, (label, col, dash) in enumerate(zip(L['legend'], (INK, ACC, SLATE),
                                               (None, None, (.9, .6)))):
        y = 6.2 + 3.7 * k
        route([(lx, y - .7), (lx + 7, y - .7)], col, .22, dash=dash)
        text(lx + 8.5, y, label, NOTE, MUTED)

    # Learning path ------------------------------------------------------
    ax, ay, aw, ah = ADM
    box(ADM)
    a1, a2 = a_x + 4.75, x_x + x_w / 2       # arrows 1 and 2
    text((a1 + a2) / 2, ay + 3.9, L['admission'], TITLE, INK, 'bold', 'center',
         width=a2 - a1 - 2)
    route([(a1, NODE_Y + NODE_H), (a1, ay)], INK)
    step(a1 - 2.8, 23.2, 1)
    route([(a2, ay), (a2, NODE_Y + NODE_H)], INK, heads='both')
    text(a2 + 2, 18.7, L['chain'], NOTE, MUTED)
    step(a2 + 2.8, 23.2, 2)
    # Candidate: a calculation chain of queries and arithmetic.
    cx, cy = ax + 2.2, ay + 7.4
    rect(cx + .9, cy - .9, 8.6, 9.2, FACE, EDGE, .12, r=.4)
    rect(cx, cy, 8.6, 9.2, WHITE, EDGE, .15, r=.4)
    s.line(cx + 2, cy + 2.2, cx + 2, cy + 6.8, ACC, .2)
    for k in range(3):
        yy = cy + 2.2 + 2.3 * k
        s.circle(cx + 2, yy, .55, ACC)
        s.line(cx + 3.6, yy, cx + 7.2 - .9 * (k == 2), yy, RULE, .32)
    text(cx + 4.3, cy + 12.4, L['candidate'], NOTE, MUTED, 'sans', 'center')
    gx, gy = ax + aw - 5.4, cy + 4.6
    route([(cx + 8.6, gy), (gx - 2.0, gy)], INK, .18, length=1.0)
    gate(gx, gy)
    text(gx, cy + 12.4, 'G1–G7', NOTE, ACC_DK, 'sans', 'center')
    sx = STORE[0]
    route([(gx + 2.0, gy), (sx, gy)], ACC)
    text((ax + aw + sx) / 2, gy - 1.1, L['publish'], NOTE, MUTED, 'sans', 'center',
         width=sx - ax - aw - .6)
    step((ax + aw + sx) / 2, gy + 2.6, 3)

    # Shared store: a versioned card --------------------------------------
    x, y, w, h = STORE
    rect(x + 1, y + 1, w, h, SIDE, EDGE, .12, r=.6)
    box(STORE)
    rect(x, y, w, 5.2, ACC_PALE, None, r=.6)
    rect(x, y + 2.6, w, 2.6, ACC_PALE, None)
    s.line(x, y + 5.2, x + w, y + 5.2, RULE, .14)
    tw = text(x + 1.8, y + 3.6, L['defs'], TITLE, INK, 'bold')
    text(x + w - 1.8, y + 3.6, '$m^r=(B,I,C,E,r)$', BODY, INK, align='right',
         width=w - 5.4 - tw)
    rows = [('$m_1^{3}$', L['valid'], ACC_DK, ((1, 'ok'), (2, 'ok'))),
            ('$m_2^{1}$', L['pending'], AMBER, ((2, 'ok'), (3, 'wait'))),
            ('$m_3^{2}$', L['revoked'], RED, ((4, 'fail'),))]
    for k, (name, state, col, conds) in enumerate(rows):
        yy = y + 6.6 + 3.2 * k
        rect(x + 1.8, yy + .1, .6, 2.4, col)
        text(x + 3.2, yy + 1.95, name, BODY, INK)
        text(x + 9.0, yy + 1.95, state, NOTE, col)
        for j, (cond, kind) in enumerate(conds):
            chip(x + w - 1.8 - 4.7 * (len(conds) - j) - .8 * (len(conds) - 1 - j), yy,
                 cond, kind)
    s.line(x + 1.8, y + 16.6, x + w - 1.8, y + 16.6, RULE, .14)
    vw = text(x + 1.8, y + 19.4, L['verdicts'], NOTE, MUTED)
    text(x + w - 1.8, y + 19.4, r'$(\mathrm{id}(c),\,V(\mathrm{dep}(c)))$', NOTE, INK,
         align='right', width=w - 4.4 - vw)

    # Use path -----------------------------------------------------------
    titled(MAINT, L['maint'], L['maint_note'])
    titled(REPAIR, L['repair'], L['repair_note'], reserve=6)
    rx, ry, rw, rh = REPAIR
    gate(rx + rw - 3.6, ry + 3.2, 1.7)
    text(rx + rw - 3.6, ry + 7.3, 'G8', NOTE, ACC_DK, 'sans', 'center')

    lx, ly, lw, lh = LOOKUP
    box(LOOKUP)
    tw = text(lx + 1.8, ly + 3.9, L['lookup'], TITLE, INK, 'bold')
    text(lx + 3.0 + tw, ly + 3.9, '`find_metric`', BODY, INK, width=lw - 4.8 - tw)
    text(lx + 1.8, ly + 7.3, L['lookup_note'], NOTE, MUTED, width=lw - 3.6)
    titled(TRACK, L['tracker'], L['tracker_note'])

    bus_y, b4, b8 = 17.2, mid(LOOKUP)[0], mid(EXEC)[0]
    centers = [x + 4.75 for x in b_xs]
    route([(centers[0], NODE_Y + NODE_H), (centers[0], bus_y), (b8, bus_y), (b8, ly)], INK,
          heads='end')
    for xc in centers[1:]:
        route([(xc, NODE_Y + NODE_H), (xc, bus_y)], INK, heads=None)
    route([(b4, bus_y), (b4, ly)], INK)
    step(b4 - 2.8, 22.6, 4)
    step(b8 - 2.8, 22.6, 8)

    mx, my, mw, mh = MAINT
    yy = my + 4.2
    route([(lx, yy), (mx + mw, yy)], INK)
    gap = (mx + mw + lx) / 2
    text(gap, yy - 1.1, L['to_maint'], NOTE, MUTED, 'sans', 'center', width=lx - mx - mw - .6)
    step(gap, yy + 2.6, 5)
    sx2 = STORE[0] + STORE[2]
    route([(mx, yy), (sx2, yy)], ACC, heads='both')
    text((mx + sx2) / 2, yy - 1.1, L['reuse'], NOTE, MUTED, 'sans', 'center',
         width=mx - sx2 - .6)
    step((mx + sx2) / 2, yy + 2.6, 6)
    fx = rx + 13
    route([(fx, my + mh), (fx, ry)], INK, length=1.0)
    text(fx + 1.4, ry - .8, L['failed'], NOTE, RED)
    step(fx - 2.8, (my + mh + ry) / 2, 7)
    yy = ry + rh / 2
    route([(rx, yy), (sx2, yy)], ACC)
    text((rx + sx2) / 2, yy - 1.1, '$m^{r+1}$', NOTE, MUTED, 'sans', 'center',
         width=rx - sx2 - .6)

    tx, ty, tw_, th = TRACK
    vx = tx + 12
    route([(vx, ty), (vx, ly + lh)], SLATE, dash=(.9, .6), length=1.0)
    text(vx + 1.4, ty - .8, L['versions'], NOTE, SLATE)

    # Execution path -----------------------------------------------------
    ex, ey, ew, eh = EXEC
    box(EXEC)
    first, second = L['exec']
    text(ex + 1.8, ey + 3.9, first, TITLE, INK, 'bold', width=ew - 3.6)
    top = ey + 3.9
    if second:
        top += 3.0
        text(ex + 1.8, top, second, TITLE, INK, 'bold')
    text(ex + 1.8, top + 3.3, '`run_sql`', BODY, INK)
    fx, fy, fw, fh = ex + 1.8, ey + 12.4, ew - 3.6, 7.0
    rect(fx, fy, fw, fh, None, ACC, .18, r=.6, dash=(.8, .5))
    dw = 4.4
    rect(fx + fw - dw - 1.2, fy - 1.1, dw, 2.2, WHITE, None)
    text(fx + fw - 1.2 - dw / 2, fy + .8, '$D_s$', BODY, ACC_DK, align='center')
    for k, label in enumerate((L['check'], L['run'])):
        yy = fy + 2.9 + 2.7 * k
        mark(fx + 1.4, yy - .55, 'ok')
        text(fx + 2.8, yy, label, NOTE, INK, width=fw - 3.4)
    px, py, pw, ph = PG
    route([(b8, ey + eh), (b8, py - 1.3)], INK)
    step(b8 - 2.8, 51.6, 9)
    text(b8 - 4.8, baseline(51.6, NOTE), L['snapshot'], NOTE, MUTED, align='right')

    # Database reads -----------------------------------------------------
    qx = rx + rw + 1.5
    route([(qx, py - 1.3), (qx, my + mh)], SLATE, dash=(.9, .6), length=1.0)
    text(qx + 1.3, 52.6, '$Q_c$', BODY, SLATE)
    route([(vx, py - 1.3), (vx, ty + th)], SLATE, dash=(.9, .6), length=1.0)

    # PostgreSQL: one storage slab with table pages ----------------------
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
    dx0, dy0 = 4, 58.8
    for off in (1.6, .8, 0):
        rect(dx0 + off, dy0 - off, 11.5, 7.0, WHITE, EDGE, .13, r=.4)
    for k in range(3):
        s.circle(dx0 + 1.8, dy0 + 1.7 + 1.8 * k, .4, AMBER)
        s.line(dx0 + 3.0, dy0 + 1.7 + 1.8 * k, dx0 + 9.6, dy0 + 1.7 + 1.8 * k, RULE, .3)
    text(dx0, 55.2, L['etl'], TITLE - .4, INK, 'bold')
    yy = dy0 + 3.2
    route([(dx0 + 13.6, yy), (px, yy)], INK)
    text((dx0 + 13.6 + px) / 2, yy - 1.1, L['updates'], NOTE, MUTED, align='center',
         width=px - dx0 - 14)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
