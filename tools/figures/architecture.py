"""Figure 1: the life of a user agent's requests through MAVRA's three modules.

A user agent sends two kinds of request. A text request names a metric
("return amount"); request handling looks it up in the shared store, which
hands a definition whose dependency versions changed to maintenance first, and
the agent receives a valid revision. An SQL request declares that revision;
same-snapshot validation checks its conditions on the query's snapshot and runs
the query there. Learning and maintenance is the third module: MAVRA's built-in
analysis optimizer, an LLM agent, learns definitions that admission publishes,
and maintenance rechecks, repairs, or invalidates them. Figure 2 opens request
handling (lookup.py), Figure 3 learning and maintenance (lifecycle.py).

Step numbers and arrows are coloured by path: use 1-5 (blue), execution
6-8 (amber), learning (violet). Line weight says what an arrow does: thin =
call or response, thick = write to the shared store, dashed = read of database
state. Coordinates are millimetres from the top-left at printed size (178 mm).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import (DASH, EXEC, LEARN, NOTE, THICK, THIN, TITLE, USE, WAIT,  # noqa: E402
                   baseline, box, legend, llm_badge, node, person, slab, step, table_card, titled)
from vecfig import measure  # noqa: E402
from style import (ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FIELD, INK, MUTED, RULE,  # noqa: E402
                   SLATE, WHITE)

NAME = 'architecture'
W, H = style.TEXTWIDTH, 50.0

LABELS = {
    'en': {
        'agents': 'User agents', 'question': ('Return amount', 'in May?'),
        'sql': 'SQL', 'declares': 'declares revision 2',
        'middleware': 'MAVRA middleware',
        'handling': 'Request handling', 'store': 'Shared store', 'learning': 'Learning and maintenance',
        'lookup': 'Lookup', 'lookup_note': 'match name, compare versions',
        'exec': 'Same-snapshot validation', 'exec_note': 'check on the query’s snapshot',
        'defs': 'Definitions', 'results': 'Check results', 'key': 'kept per table version',
        'rows': (('return amount', 'pending'), ('store revenue', 'valid')),
        'opt': 'Analysis optimizer', 'opt_note': 'LLM agent · learns',
        'maint': 'Maintenance', 'maint_note': 'recheck · repair or invalidate',
        'req_text': '“return amount”', 'resp_text': 'valid definition',
        'req_sql': 'SQL query', 'resp_sql': 'query result',
        'publish': 'publish',
        'run': 'run the query on the snapshot', 'qc': 'check queries', 'cur_v': 'table versions',
        'db': 'SQL database', 'snapshot': 'snapshot',
        'etl': 'ETL and writers', 'updates': 'updates',
        'paths': ('use path', 'execution path', 'learning path'),
        'lines': ('call / response', 'shared-store write', 'database read'),
    },
    'zh': {
        'agents': '用户端智能体', 'question': ('5 月的门店', '退货金额？'),
        'sql': 'SQL', 'declares': '声明修订 2',
        'middleware': 'MAVRA 中间件',
        'handling': '请求处理', 'store': '共享知识库', 'learning': '学习与维护',
        'lookup': '查找', 'lookup_note': '匹配名称，比较表版本',
        'exec': '同快照验证', 'exec_note': '在查询的快照上核对并执行',
        'defs': '定义', 'results': '检查结果', 'key': '按条件与表版本保存',
        'rows': (('退货金额', '待验证'), ('门店营业额', '有效')),
        'opt': '分析优化器', 'opt_note': '大模型智能体 · 学习',
        'maint': '维护', 'maint_note': '重查 · 修复或失效',
        'req_text': '“退货金额”', 'resp_text': '有效定义',
        'req_sql': 'SQL 查询', 'resp_sql': '查询结果',
        'publish': '发布',
        'run': '在快照上执行查询', 'qc': '检查查询', 'cur_v': '表版本',
        'db': 'SQL 数据库', 'snapshot': '快照',
        'etl': 'ETL 与写入方', 'updates': '更新',
        'paths': ('使用路径', '执行路径', '学习路径'),
        'lines': ('调用／返回', '写入共享库', '读取数据库'),
    },
}

FIELD_BOX = (29.5, .5, 147.5, 35.2)
PA = (51, 10, 37, 24.5)                  # request handling
PB = (97, 10, 35, 24.5)                  # shared store
PC = (141, 10, 34.5, 24.5)               # learning and maintenance
LOOKUP = (PA[0] + 1.5, 15.2, PA[2] - 3, 7.8)
EXECB = (PA[0] + 1.5, 25.2, PA[2] - 3, 7.8)
OPT = (PC[0] + 1.5, 15.2, PC[2] - 3, 7.8)
MAINT = (PC[0] + 1.5, 25.2, PC[2] - 3, 7.8)
AGENT = (2.2, 9.6, 23.0, 24.4)
DB = (33.5, 40.0, 141.5, 9.2)
SNAP = (PA[0] + 1.0, PA[2] - 2.0)        # (x, w) of the snapshot region, under request handling
VERS = (PB[0] + 1.0, PB[2] - 2.0)        # versions, under the store
TABLES = (PC[0] + 1.0, PC[2] - 2.0)      # tables, under maintenance

Y_TEXT, Y_SQL = 18.0, 28.0               # request arrows; responses run 2.6 mm below


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    # MAVRA's area, its title and the legend ---------------------------------
    rect(*FIELD_BOX, FIELD, None, r=1.4)
    rect(31.2, 1.7, .55, 2.6, ACC)
    text(32.6, 3.9, L['middleware'], TITLE - .4, ACC_DK, 'bold')
    lx = 75
    x = lx
    for label, color, steps in zip(L['paths'], (USE, EXEC, LEARN), ('1–5', '6–8', '')):
        legend(s, x, 3.0, [(label, color, steps)])
        x += 6.6 + 1.2 + measure(label, NOTE) + 4.0
    x = lx
    for label, sw, color, dash in zip(L['lines'], (THIN, THICK, THIN), (INK, INK, SLATE),
                                      (None, None, DASH)):
        route([(x, 6.6), (x + 6.5, 6.6)], color, sw, dash=dash, length=1.1)
        text(x + 8.0, baseline(6.6, NOTE), label, NOTE, MUTED)
        x += 8.0 + measure(label, NOTE) + 4.0

    # User agent: a person asking in text, and the SQL it then writes --------
    ax, ay, aw, ah = AGENT
    node(s, AGENT)
    text(ax, 3.9, L['agents'], TITLE, INK, 'bold')
    person(s, ax + 1.3, ay + 1.6)
    bx, by, bw, bh = ax + 4.6, ay + 1.2, aw - 5.8, 7.0
    rect(bx, by, bw, bh, ACC_PALE, ACC, .12, r=.9)
    q1, q2 = L['question']
    text(bx + bw / 2, by + 2.9, q1, NOTE, ACC_DK, align='center', width=bw - .8)
    text(bx + bw / 2, by + 5.5, q2, NOTE, ACC_DK, align='center', width=bw - .8)
    cx, cy, cw, ch = ax + 1.3, ay + 12.2, aw - 2.6, 10.6
    rect(cx, cy, cw, ch, WHITE, EDGE, .14, r=.5)
    text(cx + 1.0, cy + 2.6, L['sql'], NOTE, MUTED, 'bold')
    for k, length in enumerate((cw - 5.5, cw - 3.0, cw - 7.0)):
        yy = cy + 4.4 + 1.25 * k
        s.line(cx + 1.0, yy, cx + 1.0 + length, yy, RULE, .32)
    rect(cx + .8, cy + ch - 2.95, cw - 1.6, 2.4, ACC_PALE, None, r=.5)
    text(cx + cw / 2, cy + ch - 1.1, L['declares'], NOTE, ACC_DK, align='center', width=cw - 2)

    # Requests and responses between the agent and request handling ----------
    x0, x1 = ax + aw + 1.5, PA[0]
    lab = x0 + 4.2                                     # labels start right of the badges
    route([(x0, Y_TEXT), (LOOKUP[0], Y_TEXT)], USE, THIN)
    route([(LOOKUP[0], Y_TEXT + 2.6), (x0, Y_TEXT + 2.6)], USE, THIN)
    text(lab, Y_TEXT - 1.0, L['req_text'], NOTE, USE, width=x1 - lab - .6)
    text(lab, Y_TEXT + 5.2, L['resp_text'], NOTE, USE, width=x1 - lab - .6)
    step(s, x0 + 1.9, Y_TEXT - 1.9, 1, USE)
    step(s, x0 + 1.9, Y_TEXT + 4.5, 5, USE)
    route([(x0, Y_SQL), (EXECB[0], Y_SQL)], EXEC, THIN)
    route([(EXECB[0], Y_SQL + 2.6), (x0, Y_SQL + 2.6)], EXEC, THIN)
    text(lab, Y_SQL - 1.0, L['req_sql'], NOTE, EXEC, width=x1 - lab - .6)
    text(lab, Y_SQL + 5.2, L['resp_sql'], NOTE, EXEC, width=x1 - lab - .6)
    step(s, x0 + 1.9, Y_SQL - 1.9, 6, EXEC)
    step(s, x0 + 1.9, Y_SQL + 4.5, 8, EXEC)

    # Module 1: request handling ---------------------------------------------
    panel(s, PA, L['handling'])
    titled(s, LOOKUP, L['lookup'], L['lookup_note'], fill=WHITE)
    titled(s, EXECB, L['exec'], L['exec_note'], fill=WHITE)

    # Module 2: the shared store ---------------------------------------------
    panel(s, PB, L['store'])
    x, y, w = PB[0] + 1.5, 15.2, PB[2] - 3
    box(s, (x, y, w, 9.6))
    text(x + 1.2, y + 2.9, L['defs'], NOTE, INK, 'bold')
    for k, ((metric, state), col, pale) in enumerate(zip(
            L['rows'], (AMBER, ACC_DK), (AMBER_PALE, ACC_PALE))):
        yy = y + 3.9 + 2.75 * k
        rect(x + .6, yy, w - 1.2, 2.45, pale, None, r=.4)
        rect(x + 1.2, yy + .35, .5, 1.75, col)
        text(x + 2.4, yy + 1.8, metric, NOTE, INK, width=18)
        text(x + w - 1.2, yy + 1.8, state, NOTE, WAIT if col == AMBER else col, align='right')
    y2 = 26.2
    box(s, (x, y2, w, 6.8))
    text(x + 1.2, y2 + 2.9, L['results'], NOTE, INK, 'bold')
    text(x + 1.2, y2 + 5.6, L['key'], NOTE, MUTED, width=w - 2.4)

    # Module 3: learning and maintenance -------------------------------------
    panel(s, PC, L['learning'])
    ox, oy, ow, oh = OPT
    box(s, OPT, fill='#F7FAFE', stroke=ACC)
    llm_badge(s, ox + 2.9, oy + oh / 2, 1.7)
    text(ox + 5.6, oy + 3.6, L['opt'], TITLE, INK, 'bold', width=ow - 6.2)
    text(ox + 5.6, oy + 6.8, L['opt_note'], NOTE, ACC_DK, width=ow - 6.2)
    titled(s, MAINT, L['maint'], L['maint_note'])

    # Lookup path inside MAVRA: read the definition, maintain it if pending --
    ga, gb = PA[0] + PA[2], PB[0]                       # gap between modules 1 and 2
    yr = LOOKUP[1] + 4.0
    route([(gb + 1.5, yr), (LOOKUP[0] + LOOKUP[2], yr)], USE, THIN)
    step(s, (ga + gb) / 2 + .7, yr - 2.6, 2, USE)
    gc, gd = PB[0] + PB[2], PC[0]                       # gap between modules 2 and 3
    yo = OPT[1] + 2.3
    route([(OPT[0], yo), (gc - 1.5, yo)], LEARN, THICK)
    text((gc + gd) / 2, yo - 1.1, L['publish'], NOTE, LEARN, align='center', width=gd - gc + 2.6)
    # The pending definition (first row) goes to maintenance, which writes the results back.
    yp, yw, xe = 15.2 + 3.9 + 1.22, MAINT[1] + 5.4, (gc + gd) / 2 - .6
    route([(gc - 1.5, yp), (xe, yp), (xe, MAINT[1] + 2.4), (MAINT[0], MAINT[1] + 2.4)], USE, THIN,
          radius=.8)
    route([(MAINT[0], yw), (gc - 1.5, yw)], USE, THICK)
    step(s, xe + 2.75, yp + 2.3, 3, USE)
    step(s, (gc + gd) / 2, yw + 2.4, 4, USE)

    # Execution path: check results on the snapshot, run the query there -----
    ye = EXECB[1] + 4.0
    route([(EXECB[0] + EXECB[2], ye), (gb + 1.5, ye)], EXEC, THIN, heads='both', length=1.0)
    step(s, (ga + gb) / 2 + .7, ye - 2.6, 7, EXEC)

    # Database ---------------------------------------------------------------
    px, py, pw, ph = DB
    slab(s, DB)
    text(px + 1.8, py + 4.0, L['db'], TITLE, INK, 'bold', width=SNAP[0] - px - 2.6)
    top, inner = py + 1.1, ph - 2.2
    # Snapshot: a frozen copy of the tables the query and its checks read.
    nx, nw = SNAP
    rect(nx + 1.0, top - .6, nw - 1.0, inner, '#EFEDE8', None, r=.35)
    rect(nx, top, nw - 1.0, inner, WHITE, EXEC, .18, r=.35, dash=(.8, .5))
    text(nx + 1.2, top + 4.4, L['snapshot'], NOTE, EXEC, width=13)
    for k in range(3):
        table_card(s, nx + 15.0 + k * 6.6, 6.0, top + .7, inner - 1.4, '')
    # Versions: the write to store_returns moved its version.
    vx, vw = VERS
    rect(vx, top, vw, inner, WHITE, EDGE, .14, r=.35)
    for k, (table, old, new) in enumerate((('`store_returns`', 14, 15), ('`date_dim`', 3, None))):
        yy = top + 2.0 + 3.0 * k
        if new:
            rect(vx + .5, yy - 1.2, vw - 1.0, 2.5, AMBER_PALE, AMBER, .14, r=.45)
        text(vx + 1.3, yy + .8, table, NOTE, INK, 'code')
        value = f'${old}\\to{new}$' if new else f'${old}$'
        text(vx + vw - 1.3, yy + .8, value, NOTE, WAIT if new else INK, align='right')
    # Tables: rows the writers changed are amber.
    tx, tw = TABLES
    cw = (tw - 1.0) / 2
    for k, (label, changed) in enumerate((('`store_returns`', (1, 2)), ('`date_dim`', ()))):
        table_card(s, tx + k * (cw + 1.0), cw, top, inner, label, changed,
                   outline=AMBER if changed else EDGE)

    # Reads and writes of the database ---------------------------------------
    xq = EXECB[0] + EXECB[2] / 2
    route([(xq, EXECB[1] + EXECB[3]), (xq, py - 1.2)], EXEC, THIN)
    text(xq + 1.4, 38.1, L['run'], NOTE, EXEC)
    xm = MAINT[0] + MAINT[2] / 2
    route([(xm, py - 1.2), (xm, MAINT[1] + MAINT[3])], SLATE, THIN, dash=DASH, length=1.0)
    text(xm + 1.4, 38.1, L['qc'], NOTE, SLATE)
    xv = vx + vw / 2
    route([(xv, py - 1.2), (xv, PB[1] + PB[3])], SLATE, THIN, dash=DASH, length=1.0)
    text(xv + 1.4, 38.1, L['cur_v'], NOTE, SLATE)

    # Writers ----------------------------------------------------------------
    wx, wy = 2.6, 42.0
    for off in (1.4, .7, 0):
        rect(wx + off, wy - off, 10.5, 6.4, WHITE, EDGE, .13, r=.4)
    for k in range(3):
        s.circle(wx + 1.7, wy + 1.5 + 1.7 * k, .38, AMBER)
        s.line(wx + 2.8, wy + 1.5 + 1.7 * k, wx + 8.8, wy + 1.5 + 1.7 * k, RULE, .3)
    text(wx - .4, 38.6, L['etl'], TITLE - .4, INK, 'bold')
    yy = wy + 3.2
    route([(wx + 13.0, yy), (px, yy)], INK, THIN)
    text((wx + 13.0 + px) / 2, yy - 1.1, L['updates'], NOTE, MUTED, align='center',
         width=px - wx - 13.6)


def panel(s, b, title):
    """One of MAVRA's three modules: a white panel with a bold title."""
    x, y, w, h = b
    s.rect(x, y, w, h, '#FBFCFE', '#9DBBE2', .18, r=.8)
    s.text(x + 1.5, y + 3.6, title, TITLE, ACC_DK, 'bold', width=w - 3)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
