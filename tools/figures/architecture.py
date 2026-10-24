"""MAVRA architecture based on the final 2026-10-07 layout (6fb1325).

Preserve the central definition/check-result store, maintenance write-backs,
compact agent UIs, version table, and snapshot view. Add feature definitions
and their temporal execution boundary without replacing that architecture
with large agent cards. Learning may come from any successful agent session.
The visual focus is knowledge sharing: one learned revision serves different
questions, and one matching check result serves several definitions. The
explore-versus-hit comparison sits on the reuse lane that feeds the consumer
cards: it shows avoided exploration on a reuse hit, not measured timings or a
count of LLM calls. The database label is exactly Database in both languages.
Literal revision and table-version values always carry a v prefix; object,
table, and condition indices do not.

Coordinates are millimetres at paper size. Thin arrows are calls/responses,
thick arrows write shared state, and dashed arrows read database state.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import PT  # noqa: E402
import style  # noqa: E402
from style import (ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FACE, FIELD, INK, MUTED,  # noqa: E402
                   RED, RULE, SIDE, SLATE, TOP, WHITE)

NAME = 'architecture'
W, H = style.TEXTWIDTH, 76.4
LOW = 7.8                                # gap between the field and the database slab

# IEEEtran conference \scriptsize is 7pt; the committed PDF is 178 mm wide and
# is scaled to the 181.9 mm IEEEtran text width (x1.022), so TITLE, BODY and
# NOTE land at or above 7pt on paper. STEP and the chip labels sit just under
# it; they are bold white-on-colour or high-contrast indices.
TITLE, BODY, NOTE, STEP = 7.4, 7.0, 6.9, 6.6
LEARN, USE, EXEC_C = '#7A68B0', ACC, '#C97A1E'  # path colours: learning, use, execution
THIN, THICK = .22, .5                            # call or response; write to the shared store
SHARED_CHECK, SHARED_PALE = '#2F7A70', '#E6F2ED'

LABELS = {
    'en': {
        'opt': ('Successful', 'session'), 'opt_kind': 'learn once', 'ext': ('LLM', 'extractor'),
        'agents': 'Reuse across agents', 'agents_note': 'different questions',
        'questions': ('Sep?', 'Oct?', 'Predict'),
        'explore': 'No memory', 'hit': 'On a hit',
        'explore_steps': ('schema', 'probe', 'join', 'SQL'), 'find': 'lookup',
        'skipped': 'skipped',
        'names': ('Revenue', 'Past spend'),
        'middleware': 'MAVRA',
        'admission': 'Publish', 'candidate': 'candidate',
        'defs': 'Definitions', 'defs_note': 'metric / feature', 'valid': 'valid', 'pending': 'pending', 'revoked': 'invalid',
        'results': 'Check results',
        'check_share': 'one result, reused', 'qc_result': '$Q_c$ result',
        'valid_mr': 'valid revision', 'q_decl': 'query / seed',
        'available': 'valid · SQL review', 'prov': 'provenance',
        'shared': 'Shared knowledge',
        'maint': 'Maintain', 'maint_note': 'recheck only changes',
        'repair': 'Metric repair', 'repair_note': 'unique filter', 'checks': 'checks', 'regression': 'regression',
        'lookup': 'Lookup', 'lookup_note': 'compare versions $V(T)$',
        'tracker': 'Version tracker', 'tracker_note': 'per-table versions',
        'exec': ('Compile and run', None), 'declares': 'Metric query · $m^r$',
        'run': 'run $q$ on $D_s$', 'db': 'Database', 'feature': 'Feature',
        'db_note': 'tables $T$ · versions $V(T)$ · snapshots $D_s$',

        'db_snapshot': 'snapshot',
        'etl': 'ETL and writers', 'updates': 'updates', 'publish': 'publish',
        'reuse': 'reuse', 'to_maint': 'pending', 'failed': 'failed $c$',
        'versions': '$V(T)$',
        'tracker_read': '$V(T)$', 'snapshot': 'snapshot $s$',
    },
    'zh': {
        'opt': ('成功', '会话'), 'opt_kind': '一次探索', 'ext': ('大模型', '提取器'),
        'agents': '跨智能体复用', 'agents_note': '回答不同问题',
        'questions': ('9 月？', '10 月？', '预测'),
        'explore': '无记忆', 'hit': '命中后',
        'explore_steps': ('模式', '探查', '连接', 'SQL'), 'find': '查找',
        'skipped': '跳过',
        'names': ('营业额', '历史消费'),
        'middleware': 'MAVRA',
        'admission': '发布', 'candidate': '候选',
        'defs': '定义', 'defs_note': '指标 / 特征', 'valid': '有效', 'pending': '待验证', 'revoked': '已失效',
        'results': '检查结果',
        'check_share': '一个结果，多定义复用', 'qc_result': '$Q_c$ 结果',
        'valid_mr': '有效版本', 'q_decl': '查询 / 种子表',
        'available': '有效版本 · SQL 审查', 'prov': '答案溯源',
        'shared': '共享知识',
        'maint': '维护', 'maint_note': '复用检查，仅重查变更',
        'repair': '指标修复', 'repair_note': '唯一过滤', 'checks': '检查', 'regression': '回归测试',
        'lookup': '查找', 'lookup_note': '比较版本 $V(T)$',
        'tracker': '版本跟踪', 'tracker_note': '每张表的版本',
        'exec': ('编译与执行', None), 'declares': '指标查询 · $m^r$',
        'run': '在 $D_s$ 上执行 $q$', 'db': 'Database', 'feature': '特征',
        'db_note': '表 $T$ · 版本 $V(T)$ · 快照 $D_s$',

        'db_snapshot': '快照',
        'etl': 'ETL 与写入方', 'updates': '更新', 'publish': '发布',
        'reuse': '复用', 'to_maint': '待验证', 'failed': '条件失败',
        'versions': '$V(T)$',
        'tracker_read': '$V(T)$', 'snapshot': '快照 $s$',
    },
}

# Boxes (x, y, w, h).
ADM = (4, 24, 21, 30.4)
STORE = (33, 24, 68, 21)
SPLIT = 72                               # definitions | check results inside the store
REPAIR = (33, 48.2, 25.5, 8)
MAINT = (71.4, 48.2, 29.6, 8)
LOOKUP = (109, 24, 27, 9.5)
TRACK = (109, 46.4, 27, 8)
EXEC = (144, 24, 31, 30.4)
FIELD_BOX = (1.5, 20, 175.5, 37.4)
NODE_Y, NODE_H = 6, 10.4                 # compact consumer UIs, matching the learning agent's height
OPT = (2.6, 6.0, 18.2, 10.4)             # a successful session, outside MAVRA
PG = (31, 64.8, 144, 11.0)               # the database slab
DB_TABLES, DB_STATS, DB_SNAP = (76, 32), (110.5, 27), (143.5, 30)   # (x, w) of its three regions
# One worked example, kept consistent across the figure: each condition reads one
# table; only T2 is written, so c3 has no check result at the current version
# and m_2 at v1, which needs c3, is pending. (condition, table, result)
CONDS = ((1, 1, 'ok'), (2, 3, 'ok'), (3, 2, 'wait'), (4, 4, 'fail'))


def mid(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


def baseline(y_center, size):
    """Baseline that centres capitals and digits on y_center."""
    return y_center + .34 * size * PT


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def node(x, w, y=NODE_Y, d=1.5, own=False):
        """Front face with a top and a right face behind it; MAVRA's own parts are blue."""
        h = NODE_H
        top, side, edge, face = ('#E6EFFA', '#D3E2F4', '#9DBBE2', '#F7FAFE') if own else \
            ('#F2F0EC', '#E7E4DF', '#BDB9B2', WHITE)
        s.poly([(x, y), (x + d, y - d), (x + w + d, y - d), (x + w, y)], top, edge, .12)
        s.poly([(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)],
               side, edge, .12)
        rect(x, y, w, h, face, edge, .16, r=.35)

    def learner(b):
        """Any successful agent session, outside MAVRA, drawn like the consumer
        agents (person icon): the session is the source, not a system component."""
        x, y, w, h = b
        d = 1.2
        s.poly([(x, y), (x + d, y - d), (x + w + d, y - d), (x + w, y)], '#F2F0EC', '#BDB9B2', .12)
        s.poly([(x + w, y), (x + w + d, y - d), (x + w + d, y + h - d), (x + w, y + h)],
               '#E7E4DF', '#BDB9B2', .12)
        rect(x, y, w, h, WHITE, '#BDB9B2', .2, r=.5)
        s.circle(x + 2.45, y + 2.7, .95, '#8E8B85')
        rect(x + 1.2, y + 3.9, 2.6, 1.7, '#8E8B85', None, r=.85)
        tx, room = x + 4.9, w - 4.9 - .8
        first, second = L['opt']
        text(tx, y + 3.5, first, TITLE, INK, 'bold', width=room)
        text(tx, y + 6.3, second, TITLE, INK, 'bold', width=room)
        text(tx, y + 9.0, L['opt_kind'], NOTE, ACC_DK, 'bold', width=room)

    def agent(x, definition, question, w=15.):
        """A compact request UI holding a retrieved metric or feature revision."""
        node(x, w)
        y = NODE_Y
        s.circle(x + 2.25, y + 2.1, .85, '#8E8B85')
        rect(x + 1.0, y + 3.15, 2.5, 1.5, '#8E8B85', None, r=.75)
        bx, bw = x + 4.3, w - 5.6
        rect(bx, y + 1.0, bw, 3.4, ACC_PALE, ACC, .12, r=.7)
        text(bx + bw / 2, baseline(y + 2.7, NOTE), question, NOTE, ACC_DK,
             align='center', width=bw - .8)
        shared_def(x + 1.2, y + 6.5, w - 2.4, definition)

    def shared_def(x, y, w, definition):
        """A retrieved definition revision, matching a valid row in the store."""
        rect(x, y, w, 2.5, ACC_PALE, ACC, .16, r=.5)
        text(x + w / 2, y + 1.85, definition, 6.4, ACC_DK, align='center', width=w - 1.2)

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
            text(x, y + .8, '?', 7.2, '#9A6500', 'bold', 'center')

    def chip(x, y, cond, kind):
        rect(x, y, 4.2, 2.3, SHARED_PALE if cond == 2 else FACE,
             SHARED_CHECK if cond == 2 else EDGE, .15 if cond == 2 else .1, r=.45)
        text(x + .45, y + 1.7, f'$c_{cond}$', 6.2, INK)
        mark(x + 3.2, y + 1.15, kind)

    def step(x, y, n, color):
        s.circle(x, y, 1.55, color)
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

    # Field: the blue band is MAVRA; the session card above it stays outside.
    rect(*FIELD_BOX, FIELD, None, r=1.4)
    rect(21.9, 20.9, .55, 2.6, ACC)
    text(23.6, 22.9, L['middleware'], TITLE - .4, ACC_DK, 'bold')

    # The successful session feeds the publication pipeline; user agents sit
    # outside MAVRA on the right ---------
    learner(OPT)

    b4, b8 = mid(LOOKUP)[0], mid(EXEC)[0]
    b_xs = (111., 132., 153.)
    revisions = (r'$m_1^{\mathrm{v}3}$', r'$m_1^{\mathrm{v}3}$', r'$f_1^{\mathrm{v}1}$')
    for x, definition, question in zip(b_xs, revisions, L['questions']):
        agent(x, definition, question)
    for k in range(3):
        s.circle(b_xs[-1] + 19.2 + 1.6 * k, NODE_Y + NODE_H / 2, .32, EDGE)
    w = text(b_xs[0], 3.2, L['agents'], TITLE, INK, 'bold')
    text(b_xs[0] + w + 1.6, 3.2, L['agents_note'], NOTE, MUTED, width=W - b_xs[0] - w - 2.5)

    # The same question, two workflows, column-aligned: without memory the
    # agent inspects the schema, probes values and tests joins before writing
    # SQL; on a memory hit one lookup replaces the first three stages (grey =
    # not executed). Operations, not fabricated token counts or latency bars;
    # the measured savings are the evaluation's figures.
    def operation(x, yc, w, label, color, fill):
        rect(x, yc - 1.5, w, 3., fill, None, r=.5)
        text(x + w / 2, baseline(yc, NOTE), label, NOTE, color, align='center', width=w - .8)

    text(62.3, baseline(7.2, NOTE), L['explore'], NOTE, MUTED, align='right')
    exs = (63.5, 73.3, 83.1, 92.9)
    for (xx, label) in zip(exs, L['explore_steps']):
        operation(xx, 7.2, 8.4, label, MUTED, '#ECEEF1')
    for xa, xb in zip(exs[:-1], exs[1:]):
        route([(xa + 8.4, 7.2), (xb, 7.2)], MUTED, .18, length=.7)
    text(62.3, baseline(12.6, NOTE), L['hit'], NOTE, ACC_DK, 'bold', align='right')
    operation(63.5, 12.6, 8.4, L['find'], ACC_DK, ACC_PALE)
    route([(71.9, 12.6), (92.9, 12.6)], USE, .32, length=1.1)
    operation(92.9, 12.6, 8.4, 'SQL', ACC_DK, ACC_PALE)
    gap_label(71.9, 92.9, 16.2, L['skipped'])

    # Learning path: a successful session feeds MAVRA's publication pipeline,
    # which extracts a candidate and publishes it after the checks -----------
    ax, ay, aw, ah = ADM
    box(ADM)
    text(ax + aw - 1.8, ay + 3.4, L['admission'], TITLE, INK, 'bold', 'right')
    a1 = 7.5                                   # the session's provenance enters the extractor
    route([(a1, OPT[1] + OPT[3]), (a1, ay + 5)], LEARN, THIN)
    step(a1 - 2.8, 21.8, 1, LEARN)
    text(a1 + 1.8, 19.8, L['prov'], NOTE, MUTED)
    # First stage: model-based extraction proposes a structured candidate.
    ex, ey, ew, eh = ax + 1.8, ay + 5, aw - 3.6, 12
    box((ex, ey, ew, eh))
    nc_x, nc_y = ex + ew / 2, ey + 3.3
    cols = [(nc_x - 4.5, (-1.6, 1.6)), (nc_x, (-2.2, 0, 2.2)), (nc_x + 4.5, (-1.4, 1.4))]
    for (xa, ya), (xb, yb) in zip(cols, cols[1:]):
        for y1 in ya:
            for y2 in yb:
                s.line(xa, nc_y + y1, xb, nc_y + y2, RULE, .14)
    for xc, ys in cols:
        for yc in ys:
            s.circle(xc, nc_y + yc, .58, WHITE, ACC, .2)
    text(nc_x, ey + 8.3, L['ext'][0], TITLE, INK, 'bold', 'center', width=ew - 1.6)
    text(nc_x, ey + 10.9, L['ext'][1], TITLE, INK, 'bold', 'center', width=ew - 1.6)
    # The candidate passes the deterministic checks (the gate) and is published.
    cx, cy = ax + 1.8, ey + eh + 1.5           # candidate stack below the extractor
    rect(cx + .7, cy - .7, 6.6, 7, FACE, EDGE, .12, r=.4)
    rect(cx, cy, 6.6, 7, WHITE, EDGE, .15, r=.4)
    s.line(cx + 1.6, cy + 1.7, cx + 1.6, cy + 5.2, LEARN, .2)
    for k in range(3):
        yy = cy + 1.7 + 1.75 * k
        s.circle(cx + 1.6, yy, .45, LEARN)
        s.line(cx + 2.8, yy, cx + 5.5, yy, RULE, .3)
    gx, gy = ax + aw - 4.6, 43.5
    route([(cx + 7.4, gy), (gx - 2.0, gy)], LEARN, .18, length=1.0)
    step(15.1, gy + 3.5, 2, LEARN)
    gate(gx, gy)
    text(gx, gy + 4.6, L['checks'], NOTE, ACC_DK, 'sans', 'center', width=8.5)
    text(cx + 3.8, cy + 10.4, L['candidate'], NOTE, MUTED, 'sans', 'center')
    sx = STORE[0]
    route([(gx + 2.0, gy), (sx, gy)], LEARN, THICK)
    gap_label(ax + aw, sx, gy - 1.2, L['publish'])
    step((ax + aw + sx) / 2, gy + 2.9, 3, LEARN)

    # Shared store: definitions | check results ---------------------------
    x, y, w, h = STORE
    rect(x + 1, y + 1, w, h, SIDE, EDGE, .12, r=.6)
    box(STORE)
    rect(x, y, w, 4.4, ACC_PALE, None, r=.6)
    rect(x, y + 2.2, w, 2.2, ACC_PALE, None)
    s.line(x, y + 4.4, x + w, y + 4.4, RULE, .14)
    s.line(SPLIT, y, SPLIT, y + h, RULE, .14)
    rect(x, 20.5, w, 3., ACC, None, r=.6)
    text(x + w / 2, baseline(22., TITLE), L['shared'], TITLE, WHITE, 'bold', 'center')
    tw = text(x + 1.8, y + 3.2, L['defs'], TITLE, INK, 'bold')
    text(SPLIT - 1.6, y + 3.2, L['defs_note'], BODY, INK, align='right',
         width=SPLIT - x - 5 - tw)
    rows = [(r'$m_1^{\mathrm{v}3}$', L['names'][0], ACC_DK, ((1, 'ok'), (2, 'ok'))),
            (r'$m_2^{\mathrm{v}1}$', L['pending'], AMBER, ((2, 'ok'), (3, 'wait'))),
            (r'$m_3^{\mathrm{v}2}$', L['revoked'], RED, ((4, 'fail'),)),
            (r'$f_1^{\mathrm{v}1}$', L['names'][1], ACC_DK, ((2, 'ok'),))]
    for k, (name, label, col, conds) in enumerate(rows):
        yy = y + 5.6 + 3.7 * k
        if k in (0, 3):                 # valid revisions held by the user agents
            rect(x + .9, yy - .25, SPLIT - x - 1.8, 2.6, ACC_PALE, None, r=.4)
        elif k == 1:                     # pending because c3 has no result at V(T2)
            rect(x + .9, yy - .25, SPLIT - x - 1.8, 2.6, AMBER_PALE, None, r=.4)
        rect(x + 1.8, yy + .1, .6, 2.1, col)
        text(x + 3.2, yy + 1.75, name, BODY, INK, width=4.6)
        # A valid row shows what the definition computes; a stuck row shows why.
        text(x + 8.2, yy + 1.75, label, NOTE, ACC_DK if k in (0, 3) else col,
             'bold' if k in (0, 3) else 'sans')
        for j, (cond, kind) in enumerate(conds):
            chip(SPLIT - 1.6 - 4.2 * (len(conds) - j) - .5 * (len(conds) - 1 - j), yy, cond, kind)
    text(SPLIT + 1.6, y + 3.2, L['results'], TITLE, INK, 'bold', width=x + w - SPLIT - 3.2)
    cw_ = (x + w - SPLIT - 3.2 - 1.0) / 2
    for j, (cond, table, kind) in enumerate(CONDS):
        cx_, cy_ = SPLIT + 1.6 + (j % 2) * (cw_ + 1.0), y + 7.6 + (j // 2) * 3.6
        missing = kind == 'wait'
        shared = cond == 2
        rect(cx_, cy_, cw_, 2.6, AMBER_PALE if missing else SHARED_PALE if shared else FACE,
             AMBER if missing else SHARED_CHECK if shared else EDGE,
             .14 if missing or shared else .1, r=.45)
        text(cx_ + .6, cy_ + 1.8, f'$c_{cond}$', NOTE, INK)
        text(cx_ + 3.8, cy_ + 1.8, f'$T_{table}$', NOTE, MUTED)
        mark(cx_ + cw_ - 1.4, cy_ + 1.3, kind)
    text(SPLIT + 1.6, y + h - 1.2, L['check_share'], NOTE, SHARED_CHECK,
         width=x + w - SPLIT - 3.2)

    # Use path: lookup, maintenance, repair --------------------------------
    titled(MAINT, L['maint'], L['maint_note'])
    titled(REPAIR, L['repair'], L['repair_note'], reserve=6)
    rx, ry, rw, rh = REPAIR
    gate(rx + rw - 3.6, ry + 3.0, 1.6)
    text(rx + rw - .8, ry + 6.8, L['regression'], NOTE, ACC_DK, 'sans', 'right', width=11.5)

    lx_, ly, lw, lh = LOOKUP
    box(LOOKUP)
    text(lx_ + 1.8, ly + 3.9, L['lookup'], TITLE, INK, 'bold')
    text(lx_ + 1.8, ly + 7.3, L['lookup_note'], NOTE, MUTED, width=lw - 3.6)
    titled(TRACK, L['tracker'], L['tracker_note'])

    # The same valid revision visibly fans out to different questions/agents.
    bus_y = 18.
    centers = [bx + 7.5 for bx in b_xs]
    # The hit's SQL flows down the reuse lane from the contrast above to every
    # waiting agent; lookup's response joins the same lane.
    route([(101.3, 12.6), (104.0, 12.6), (104.0, bus_y), (max(b8, centers[-1]), bus_y)],
          USE, .3, heads=None, radius=.8)
    for xc in centers:
        route([(xc, bus_y), (xc, NODE_Y + NODE_H)], USE, .3, length=.9)
    route([(b4 - .9, bus_y), (b4 - .9, ly)], USE, THIN, length=1.0)        # call
    route([(b4 + .9, ly), (b4 + .9, bus_y)], USE, THIN, length=1.0)        # response
    text(b4 + 2.3, 21.6, L['valid_mr'], NOTE, USE)
    step(b4 - 3.7, 21.6, 4, USE)

    store_right = STORE[0] + STORE[2]
    route([(store_right, ly + 3.5), (lx_, ly + 3.5)], USE, THIN)
    gap_label(store_right, lx_, ly + 2.4, '$m^r,f^r$')
    mx, my, mw, mh = MAINT
    lane = 105
    route([(lx_, ly + 7.5), (lane, ly + 7.5), (lane, my + 4.0), (mx + mw, my + 4.0)], USE, THIN,
          radius=.8)
    step(store_right + 1.85, (STORE[1] + STORE[3] + my) / 2, 5, USE)
    text(lane + 1.3, 37.0, L['to_maint'], NOTE, MUTED)

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
    step(b8 + 2.8, 21.6, 8, EXEC_C)
    text(b8 - 1.4, 21.6, L['q_decl'], NOTE, EXEC_C, align='right', width=b8 - 1.4 - b4 - 16)
    first, second = L['exec']
    text(ex + 1.8, ey + 3.9, first, TITLE, INK, 'bold', width=ew - 3.6)
    top = ey + 3.9
    if second:
        top += 3.0
        text(ex + 1.8, top, second, TITLE, INK, 'bold', width=ew - 3.6)
    text(ex + 1.8, top + 3.3, L['declares'], BODY, INK, width=ew - 3.6)
    mark(ex + 3.2, top + 5.75, 'ok')
    text(ex + 4.6, top + 6.3, L['available'], NOTE, INK, width=ew - 6.4)
    fx, fy, fw, fh = ex + 1.8, top + 8.6, ew - 3.6, 7.0
    rect(fx, fy, fw, fh, None, EXEC_C, .18, r=.6, dash=(.8, .5))
    dw = 4.4
    rect(fx + fw - dw - 1.2, fy - 1.1, dw, 2.2, WHITE, None)
    text(fx + fw - 1.2 - dw / 2, fy + .8, '$D_s$', BODY, EXEC_C, align='center')
    for k, label in enumerate((r'$\forall c \in C(m^r){:}\ c(D_s)$', L['run'])):
        yy = fy + 2.9 + 2.7 * k
        mark(fx + 1.4, yy - .55, 'ok')
        text(fx + 2.8, yy, label, NOTE, INK, width=fw - 3.4)
    # Feature compilation excludes events at/after each seed's cutoff.
    text(ex + 1.8, ey + 23.0, L['feature'], NOTE, INK, 'bold')
    text(ex + ew - 1.8, ey + 23.0, '$t < t_i$', NOTE, EXEC_C, align='right')
    axis_y, cutoff = ey + 27.5, ex + 20.0
    rect(ex + 2.0, axis_y - 1.0, cutoff - ex - 2.0, 2.0, AMBER_PALE, None, r=.3)
    s.line(ex + 2.0, axis_y, ex + ew - 1.8, axis_y, RULE, .18)
    s.line(cutoff, axis_y - 1.8, cutoff, axis_y + 1.2, EXEC_C, .25)
    for dx in (5., 10., 16.):
        s.circle(ex + dx, axis_y, .42, EXEC_C)
    for dx in (23., 27.):
        s.line(ex + dx - .35, axis_y - .35, ex + dx + .35, axis_y + .35, MUTED, .18)
        s.line(ex + dx - .35, axis_y + .35, ex + dx + .35, axis_y - .35, MUTED, .18)
    text(cutoff, axis_y - 2.2, '$t_i$', NOTE, EXEC_C, align='center')
    px, py, pw, ph = PG
    route([(b8, ey + eh), (b8, py - 1.3)], EXEC_C, THIN)
    step(b8 - 2.8, 52.2 + LOW, 9, EXEC_C)
    text(b8 - 4.8, baseline(52.2 + LOW, NOTE), L['snapshot'], NOTE, MUTED, align='right')

    # Database reads -------------------------------------------------------
    t_cw = (DB_TABLES[1] - 3 * .9) / 4
    qx = DB_TABLES[0] + (t_cw + .9) + t_cw / 2       # over T2, the table c3 reads
    route([(qx, py - 1.3), (qx, my + mh)], SLATE, THIN, dash=(.9, .6), length=1.0)
    text(qx + 1.3, 53.6 + LOW, L['qc_result'], NOTE, SLATE)
    vr = tx + 5
    route([(vr, py - 1.3), (vr, ty + th)], SLATE, THIN, dash=(.9, .6), length=1.0)
    text(vr + 1.3, 53.6 + LOW, L['tracker_read'], NOTE, SLATE, width=b8 - 4.8 - 18 - vr)

    # Database: one storage slab. Its three regions sit under the arrows that
    # reach them: check queries read tables, the tracker reads statistics and
    # versions, same-snapshot validation runs on a snapshot.
    d = 1.4
    soft = '#BDB9B2'
    s.poly([(px, py), (px + d, py - d), (px + pw + d, py - d), (px + pw, py)], '#F2F0EC', soft, .12)
    s.poly([(px + pw, py), (px + pw + d, py - d), (px + pw + d, py + ph - d), (px + pw, py + ph)],
           '#E7E4DF', soft, .12)
    rect(px, py, pw, ph, FACE, soft, .16, r=.5)
    room = DB_TABLES[0] - px - 4.0
    text(px + 2.4, py + 4.4, L['db'], TITLE, INK, 'bold', width=room)
    text(px + 2.4, py + 7.8, L['db_note'], NOTE, MUTED, width=room)
    top, inner = py + 1.2, ph - 2.4
    row_fill = '#E4E1DB'

    def table_card(x0, w, y0, h, label, changed=(), outline=EDGE, dash=None):
        rect(x0, y0, w, h, WHITE, outline, .14, r=.35, dash=dash)
        rect(x0 + .15, y0 + .15, w - .3, 2.0, TOP, None, r=.25)
        text(x0 + w / 2, y0 + 1.75, label, NOTE, INK, align='center', width=w - .6)
        rows = int((h - 2.9) // 1.35)
        for r_ in range(rows):
            yy = y0 + 2.75 + 1.35 * r_
            hot = r_ in changed
            rect(x0 + .8, yy, w - 1.6, .78, AMBER_PALE if hot else row_fill,
                 AMBER if hot else None, .1, r=.2)

    # Tables: rows changed by the writers are amber.
    tx, tw_all = DB_TABLES
    cw = (tw_all - 3 * .9) / 4
    for k, changed in enumerate(((), (1, 2), (), ())):
        table_card(tx + k * (cw + .9), cw, top, inner, f'$T_{k + 1}$', changed,
                   outline=AMBER if changed else EDGE)

    # Version of each table.
    sx_, sw_ = DB_STATS
    rect(sx_, top, sw_, inner, WHITE, EDGE, .14, r=.35)
    # The write to T2 (amber rows) moves its version; T1 and T3 keep theirs.
    for k, (old, new) in enumerate(((7, None), (13, 14), (4, None))):
        yy = top + 1.9 + 2.35 * k
        if new:
            rect(sx_ + .6, yy - 1.0, sw_ - 1.2, 2.3, AMBER_PALE, AMBER, .14, r=.45)
        text(sx_ + 1.4, yy + .75, f'$V(T_{k + 1})$', NOTE, INK)
        value = rf'$\mathrm{{v}}{old}\to\mathrm{{v}}{new}$' if new else rf'$\mathrm{{v}}{old}$'
        text(sx_ + sw_ - 1.4, yy + .75, value, NOTE, '#9A6500' if new else INK, align='right')

    # Snapshot D_s: a frozen copy of the tables, framed like D_s above.
    nx, nw = DB_SNAP
    rect(nx + 1.0, top - .6, nw - 1.0, inner, '#EFEDE8', None, r=.35)
    rect(nx, top, nw - 1.0, inner, WHITE, EXEC_C, .18, r=.35, dash=(.8, .5))
    lw_ = text(nx + 1.2, top + 3.4, L['db_snapshot'], NOTE, MUTED, 'bold')
    text(nx + 1.2, top + 6.6, '$D_s$', BODY, EXEC_C)
    m0 = nx + 1.2 + lw_ + 1.2
    mini = (nx + nw - 1.0 - 1.0 - m0 - 2 * .6) / 3
    for k in range(3):
        table_card(m0 + k * (mini + .6), mini, top + .8, inner - 1.6, f'$T_{k + 1}$')

    # Writers --------------------------------------------------------------
    dx0, dy0 = 4, 60.0 + LOW
    for off in (1.6, .8, 0):
        rect(dx0 + off, dy0 - off, 11.5, 7.0, WHITE, EDGE, .13, r=.4)
    for k in range(3):
        s.circle(dx0 + 1.8, dy0 + 1.7 + 1.8 * k, .4, AMBER)
        s.line(dx0 + 3.0, dy0 + 1.7 + 1.8 * k, dx0 + 9.6, dy0 + 1.7 + 1.8 * k, RULE, .3)
    text(dx0, 55.6 + LOW, L['etl'], TITLE - .4, INK, 'bold')
    yy = dy0 + 3.2
    route([(dx0 + 13.6, yy), (px, yy)], INK, THIN)
    gap_label(dx0 + 13.6, px, yy - 1.1, L['updates'])


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
