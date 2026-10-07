"""Draft figure 1 (system overview): a user agent's requests through MAVRA.

A user agent sends two kinds of request. A text request names a metric
("return amount"); request handling looks it up in the shared store, which
hands a definition whose dependency versions changed to maintenance first, and
the agent receives a valid revision. An SQL request declares that revision;
same-snapshot validation checks its conditions on the query's snapshot and runs
the query there. Learning and maintenance is the third module: MAVRA's built-in
analysis optimizer, an LLM agent, learns definitions that admission publishes,
and maintenance rechecks, repairs, or invalidates them. Draft figure 2 opens
request handling (lookup.py), draft figure 3 learning and maintenance
(lifecycle.py). These are drafts for a later paper figure; neither the paper nor
the deck uses them yet.

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
                   baseline, box, legend, llm_badge, mark, node, person, slab, step, table_card,
                   titled)
from vecfig import measure  # noqa: E402
from style import (ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FACE, FIELD, INK, MUTED,  # noqa: E402
                   RULE, SLATE, WHITE)

NAME = 'overview'
W, H = style.TEXTWIDTH, 66.0

LABELS = {
    'en': {
        'agents': 'User agents', 'question': ('Return amount', 'in May?'),
        'sql': 'SQL', 'declares': 'declares revision 2',
        'middleware': 'MAVRA middleware',
        'handling': 'Request handling', 'store': 'Shared store',
        'lookup': 'Lookup', 'lookup_note': 'match name, compare versions',
        'exec': 'Same-snapshot validation', 'exec_note': 'check on the query’s snapshot',
        'defs': 'Definitions', 'results': 'Check results',
        'shared': 'per condition and table version, shared by all definitions and agents',
        'def_rows': (('return amount', 'pending'), ('return rate', 'valid'), ('store revenue', 'valid')),
        'cr_rows': (('one row per return', '`store_returns` 15', 'ok'),
                    ('one date per date key', '`date_dim` 3', 'ok'),
                    ('no lost dates', '`store_returns` 15', 'wait')),
        'opt': 'Analysis optimizer', 'opt_note': 'LLM agent: learns definitions; admission checks them',
        'maint': 'Maintenance', 'maint_note': 'run missing checks · repair or invalidate',
        'req_text': '“return amount”', 'resp_text': 'valid definition',
        'req_sql': 'SQL query', 'resp_sql': 'query result',
        'read_def': 'read definition', 'reuse': ('reuse', 'check results'),
        'missing': 'missing result: run check', 'store_result': 'store result', 'publish': 'publish',
        'run': 'run the query on the snapshot', 'qc': 'check queries, table versions',
        'db': 'SQL database', 'snapshot': 'snapshot',
        'etl': 'ETL and writers', 'updates': 'updates',
        'paths': ('use', 'execution', 'learning'),
        'lines': ('call / response', 'shared-store write', 'database read'),
    },
    'zh': {
        'agents': '用户端智能体', 'question': ('5 月的门店', '退货金额？'),
        'sql': 'SQL', 'declares': '声明修订 2',
        'middleware': 'MAVRA 中间件',
        'handling': '请求处理', 'store': '共享知识库',
        'lookup': '查找', 'lookup_note': '匹配名称，比较表版本',
        'exec': '同快照验证', 'exec_note': '在查询的快照上核对并执行',
        'defs': '定义', 'results': '检查结果',
        'shared': '按“条件 + 表版本”保存，所有定义与智能体共用',
        'def_rows': (('退货金额', '待验证'), ('退货率', '有效'), ('门店营业额', '有效')),
        'cr_rows': (('每笔退货一行', '`store_returns` 15', 'ok'),
                    ('每个日期键一个日期', '`date_dim` 3', 'ok'),
                    ('日期不丢失', '`store_returns` 15', 'wait')),
        'opt': '分析优化器', 'opt_note': '大模型智能体：学习定义，经准入检查后发布',
        'maint': '维护', 'maint_note': '执行缺失的检查 · 修复或失效',
        'req_text': '“退货金额”', 'resp_text': '有效定义',
        'req_sql': 'SQL 查询', 'resp_sql': '查询结果',
        'read_def': '读取定义', 'reuse': ('复用', '检查结果'),
        'missing': '缺结果：执行检查', 'store_result': '存入结果', 'publish': '发布',
        'run': '在快照上执行查询', 'qc': '检查查询、表版本',
        'db': 'SQL 数据库', 'snapshot': '快照',
        'etl': 'ETL 与写入方', 'updates': '更新',
        'paths': ('使用', '执行', '学习'),
        'lines': ('调用／返回', '写入共享库', '读取数据库'),
    },
}

FIELD_BOX = (27.5, .5, 149.5, 53.0)
AGENT = (2.2, 14.2, 21.0, 24.0)
PA = (44.5, 14.0, 37.0, 24.5)            # request handling
LOOKUP = (46.0, 19.2, 34.0, 7.8)
EXECB = (46.0, 29.4, 34.0, 7.8)
OPT = (108.0, 2.4, 68.5, 8.4)            # the built-in analysis optimizer, above the store
PB = (97.0, 14.0, 79.5, 25.8)            # shared store
DEFS = (98.5, 19.2, 76.5, 7.8)
CRB = (98.5, 28.2, 76.5, 10.2)
MAINT = (120.0, 44.2, 56.5, 7.8)         # maintenance, below the store
DB = (27.5, 57.0, 149.0, 8.4)
SNAP = (45.5, 35.0)                      # (x, w) of the snapshot region, under request handling
VERS = (98.5, 30.0)                      # versions, under the store
TABLES = (138.0, 37.0)                   # tables, under maintenance
Y_TEXT, Y_SQL = 21.4, 31.6               # request arrows; responses run 2.6 mm below
CHIP = 23.5                              # width of a check-result entry


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    # MAVRA's area, its title and the legend ---------------------------------
    rect(*FIELD_BOX, FIELD, None, r=1.4)
    rect(29.2, 1.7, .55, 2.6, ACC)
    text(30.6, 3.9, L['middleware'], TITLE - .4, ACC_DK, 'bold')
    x = 30.6
    for label, color, steps in zip(L['paths'], (USE, EXEC, LEARN), ('1–5', '6–8', '')):
        legend(s, x, 7.5, [(label, color, steps)])
        x += 6.6 + 1.2 + measure(label, NOTE) + 3.5
    x = 30.6
    for label, sw, color, dash in zip(L['lines'], (THIN, THICK, THIN), (INK, INK, SLATE),
                                      (None, None, DASH)):
        route([(x, 11.1), (x + 6.5, 11.1)], color, sw, dash=dash, length=1.1)
        text(x + 8.0, baseline(11.1, NOTE), label, NOTE, MUTED)
        x += 8.0 + measure(label, NOTE) + 3.5

    # User agent: a person asking in text, and the SQL it then writes --------
    ax, ay, aw, ah = AGENT
    node(s, AGENT)
    text(ax, 11.4, L['agents'], TITLE, INK, 'bold')
    person(s, ax + 1.3, ay + 1.6)
    bx, by, bw, bh = ax + 4.6, ay + 1.2, aw - 5.8, 7.0
    rect(bx, by, bw, bh, ACC_PALE, ACC, .12, r=.9)
    q1, q2 = L['question']
    text(bx + bw / 2, by + 2.9, q1, NOTE, ACC_DK, align='center', width=bw - .8)
    text(bx + bw / 2, by + 5.5, q2, NOTE, ACC_DK, align='center', width=bw - .8)
    cx, cy, cw, ch = ax + 1.3, ay + 11.8, aw - 2.6, 10.6
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
    for (y_req, y_resp), color, (n_req, n_resp), (req, resp), target in (
            ((Y_TEXT, Y_TEXT + 2.6), USE, (1, 5), (L['req_text'], L['resp_text']), LOOKUP),
            ((Y_SQL, Y_SQL + 2.6), EXEC, (6, 8), (L['req_sql'], L['resp_sql']), EXECB)):
        route([(x0, y_req), (target[0], y_req)], color, THIN)
        route([(target[0], y_resp), (x0, y_resp)], color, THIN)
        text(lab, y_req - 1.0, req, NOTE, color, width=x1 - lab - .6)
        text(lab, y_resp + 2.6, resp, NOTE, color, width=x1 - lab - .6)
        step(s, x0 + 1.9, y_req - 1.9, n_req, color)
        step(s, x0 + 1.9, y_resp + 1.9, n_resp, color)

    # Request handling ---------------------------------------------------------
    panel(s, PA, L['handling'])
    titled(s, LOOKUP, L['lookup'], L['lookup_note'])
    titled(s, EXECB, L['exec'], L['exec_note'])

    # Built-in analysis optimizer -----------------------------------------------
    ox, oy, ow, oh = OPT
    box(s, OPT, fill='#F7FAFE', stroke=ACC)
    llm_badge(s, ox + 3.0, oy + oh / 2, 1.7)
    text(ox + 5.8, oy + 3.4, L['opt'], TITLE, INK, 'bold', width=ow - 6.4)
    text(ox + 5.8, oy + 6.7, L['opt_note'], NOTE, ACC_DK, width=ow - 6.4)

    # Shared store: definitions above, check results below ----------------------
    panel(s, PB, L['store'])
    x, y, w, h = DEFS
    box(s, DEFS)
    text(x + 1.2, y + h / 2 + 1.0, L['defs'], NOTE, INK, 'bold')
    cw2 = 18.5
    for k, ((metric, state), col, pale) in enumerate(zip(
            L['def_rows'], (AMBER, ACC_DK, ACC_DK), (AMBER_PALE, ACC_PALE, ACC_PALE))):
        xx = x + w - 1.0 - (3 - k) * cw2 - (2 - k) * 1.0
        rect(xx, y + 1.0, cw2, h - 2.0, pale, None, r=.5)
        rect(xx + .6, y + 1.6, .5, h - 3.2, col)
        text(xx + 1.7, y + 3.4, metric, NOTE, INK, width=cw2 - 2.2)
        text(xx + 1.7, y + 6.0, state, NOTE, WAIT if col == AMBER else col, width=cw2 - 2.2)
    x, y, w, h = CRB
    box(s, CRB)
    tw = text(x + 1.2, y + 3.0, L['results'], NOTE, INK, 'bold')
    text(x + 2.6 + tw, y + 3.0, L['shared'], NOTE, MUTED, width=w - 3.8 - tw)
    for k, (cond, version, kind) in enumerate(L['cr_rows']):
        xx = x + 1.0 + k * (CHIP + 1.0)
        missing = kind == 'wait'
        rect(xx, y + 4.2, CHIP, 5.3, AMBER_PALE if missing else FACE, AMBER if missing else EDGE,
             .14 if missing else .1, r=.5)
        text(xx + .8, y + 6.4, cond, NOTE, INK, width=CHIP - 1.2)
        text(xx + .8, y + 8.9, version, NOTE, WAIT if missing else MUTED, width=CHIP - 3.4)
        mark(s, xx + CHIP - 1.3, y + 8.2, kind)

    # Maintenance ---------------------------------------------------------------
    titled(s, MAINT, L['maint'], L['maint_note'])

    # Inside MAVRA: read the definition, reuse check results, fill a missing one
    ga, gb = PA[0] + PA[2], PB[0]                       # gap between request handling and store
    yr = DEFS[1] + DEFS[3] / 2 + 1.0
    route([(DEFS[0], yr), (LOOKUP[0] + LOOKUP[2], yr)], USE, THIN)
    text((ga + gb) / 2 + .8, yr - 1.0, L['read_def'], NOTE, USE, align='center', width=gb - ga + 3.0)
    step(s, (ga + gb) / 2 + .8, yr + 2.2, 2, USE)
    ye = CRB[1] + 6.4
    route([(EXECB[0] + EXECB[2], ye), (CRB[0], ye)], EXEC, THIN, heads='both', length=1.0)
    r1, r2 = L['reuse']
    text((ga + gb) / 2 + .8, ye - 3.6, r1, NOTE, EXEC, align='center')
    text((ga + gb) / 2 + .8, ye - 1.0, r2, NOTE, EXEC, align='center', width=gb - ga + 3.0)
    step(s, (ga + gb) / 2 + .8, ye + 2.2, 7, EXEC)
    # The missing entry (third) sends maintenance to run its check; the result is stored back.
    xm0 = CRB[0] + 1.0 + 2 * (CHIP + 1.0)
    xd, xu = xm0 + 4.0, xm0 + 11.5
    yb, yt = CRB[1] + CRB[3], MAINT[1]
    route([(xd, yb), (xd, yt)], USE, THIN, length=1.0)
    route([(xu, yt), (xu, yb + .2)], USE, THICK, length=1.0)
    ym = (yb + yt) / 2 + .2
    text(xd - 1.4, baseline(ym, NOTE), L['missing'], NOTE, USE, align='right')
    step(s, xd - 1.4 - measure(L['missing'], NOTE) - 2.0, ym, 3, USE)
    step(s, xu - 2.6, ym, 4, USE)
    text(xu + 1.4, baseline(ym, NOTE), L['store_result'], NOTE, USE, width=W - xu - 1.6)
    # Learning: the optimizer publishes into the definitions.
    xp = OPT[0] + OPT[2] - 12.0
    route([(xp, OPT[1] + OPT[3]), (xp, DEFS[1])], LEARN, THICK, length=1.0)
    text(xp - 1.4, PB[1] + 2.4, L['publish'], NOTE, LEARN, align='right')

    # Database ---------------------------------------------------------------
    px, py, pw, ph = DB
    slab(s, DB)
    text(px + 1.8, py + 5.0, L['db'], TITLE, INK, 'bold', width=SNAP[0] - px - 2.6)
    top, inner = py + 1.0, ph - 2.0
    nx, nw = SNAP
    rect(nx + 1.0, top - .6, nw - 1.0, inner, '#EFEDE8', None, r=.35)
    rect(nx, top, nw - 1.0, inner, WHITE, EXEC, .18, r=.35, dash=(.8, .5))
    text(nx + 1.2, top + 4.2, L['snapshot'], NOTE, EXEC, width=13)
    for k in range(3):
        table_card(s, nx + 14.0 + k * 6.6, 6.0, top + .6, inner - 1.2, '')
    vx, vw = VERS
    rect(vx, top, vw, inner, WHITE, EDGE, .14, r=.35)
    for k, (table, old, new) in enumerate((('`store_returns`', 14, 15), ('`date_dim`', 3, None))):
        yy = top + 1.8 + 2.9 * k
        if new:
            rect(vx + .5, yy - 1.2, vw - 1.0, 2.5, AMBER_PALE, AMBER, .14, r=.45)
        text(vx + 1.3, yy + .8, table, NOTE, INK)
        value = f'${old}\\to{new}$' if new else f'${old}$'
        text(vx + vw - 1.3, yy + .8, value, NOTE, WAIT if new else INK, align='right')
    tx, tw = TABLES
    cw = (tw - 1.0) / 2
    for k, (label, changed) in enumerate((('`store_returns`', (1, 2)), ('`date_dim`', ()))):
        table_card(s, tx + k * (cw + 1.0), cw, top, inner, label, changed,
                   outline=AMBER if changed else EDGE)

    # Reads and writes of the database ---------------------------------------
    xq = EXECB[0] + EXECB[2] / 2
    route([(xq, EXECB[1] + EXECB[3]), (xq, py - 1.2)], EXEC, THIN)
    text(xq + 1.4, 47.0, L['run'], NOTE, EXEC)
    xm = MAINT[0] + 8.0
    route([(xm, py - 1.2), (xm, MAINT[1] + MAINT[3])], SLATE, THIN, dash=DASH, length=1.0)
    text(xm + 1.4, baseline((MAINT[1] + MAINT[3] + py - 1.2) / 2, NOTE), L['qc'], NOTE, SLATE)

    # Writers ----------------------------------------------------------------
    wx, wy = 2.6, 59.0
    for off in (1.4, .7, 0):
        rect(wx + off, wy - off, 10.5, 6.0, WHITE, EDGE, .13, r=.4)
    for k in range(3):
        s.circle(wx + 1.7, wy + 1.4 + 1.6 * k, .38, AMBER)
        s.line(wx + 2.8, wy + 1.4 + 1.6 * k, wx + 8.8, wy + 1.4 + 1.6 * k, RULE, .3)
    text(wx - .4, 55.4, L['etl'], TITLE - .4, INK, 'bold')
    yy = wy + 3.0
    route([(wx + 13.0, yy), (px, yy)], INK, THIN)
    text((wx + 13.0 + px) / 2, yy - 1.1, L['updates'], NOTE, MUTED, align='center',
         width=px - wx - 13.6)


def panel(s, b, title):
    """A module: a white panel with a bold title."""
    x, y, w, h = b
    s.rect(x, y, w, h, '#FBFCFE', '#9DBBE2', .18, r=.8)
    s.text(x + 1.5, y + 3.6, title, TITLE, ACC_DK, 'bold', width=w - 3)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
