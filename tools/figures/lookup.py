"""Deck figure 2 (query and execution): how the query service answers a user agent.

Top lane: the agent asks for "return amount"; the service matches names and
aliases, compares the data versions recorded at the last validation with the
current ones, looks each validation rule up in the cache (reusing hits,
validating and caching misses), and returns the valid definition v2. Middle:
the validation cache, keyed by (rule, data version) and shared by every
definition and agent, with who wrote each entry and which step reused it.
Bottom lane: the agent's SQL names v2; the service checks the version, validates
the rules on the query's own snapshot (a write has meanwhile moved store_returns
to version 16), and runs the SQL on that snapshot. Values come from the
end-to-end study (task M2-P1: 3,294,349.93). Drawn at slide size for the
report deck, with everyday terms rather than the paper's notation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import (EXEC, HEAD, NOTE, PANEL_EDGE, THIN, TITLE, USE, WAIT, legend_pill, mark,  # noqa: E402
                   node, person, stage, step)
from style import ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, FIELD, INK, MUTED, RED, RULE, WHITE  # noqa: E402

NAME = 'lookup'
W, H = 300.0, 149.0

LABELS = {
    'zh': {
        'agent': '用户智能体', 'mavra': 'MAVRA 查询服务', 'paths': ('查询指标定义', '执行 SQL'),
        'text_req': '文本请求', 'question': ('5 月门店', '退货金额？'), 'ask': '查“退货金额”',
        's1': ('匹配名称', '名称或别名包含它'),
        'names': (('门店退货金额', True), ('门店退货率', False), ('门店营业额', False)),
        's2': ('看数据版本', '上次校验时 → 现在'), 'then_now': ('上次', '现在'),
        'changed': '变了：要重新校验',
        's3': ('校验（先查缓存）', '每条规则：查缓存，没有才执行校验'),
        'rules': ('每笔退货一行', '日期键唯一', '退货都有日期'),
        'lookup_out': ('缓存命中：复用', '缓存命中：复用', '未命中：校验后缓存'),
        's4': ('返回', '有效时返回定义'), 'valid': '退货金额 v2，有效',
        'fields': ('`store_returns`', '`SUM(sr_return_amt)`', "`sr_status='完成'`"),
        'then': ('然后', '写 SQL'),
        'cache_title': '校验结果缓存',
        'cache_note': ('按（校验规则，数据版本）缓存校验结果。', '同一规则、同一数据版本：所有指标定义、',
                       '所有智能体共用一份，不重复校验。', '数据版本变了，才需要重新校验。'),
        'cache_head': ('规则', '数据版本', '写入者', '使用者'),
        'cache_rows': (('每笔退货一行', '`store_returns` 15', '退货率', (3,)),
                       ('日期键唯一', '`date_dim` 3', '之前的校验', (3, 6)),
                       ('退货都有日期', '`store_returns` 15', 3, ()),
                       ('每笔退货一行', '`store_returns` 16', 6, ()),
                       ('退货都有日期', '`store_returns` 16', 6, ())),
        'lookup_cache': '查 / 写缓存',
        'sql_req': 'SQL 请求',
        'sql': ('SELECT SUM(sr_return_amt)', 'FROM store_returns', 'JOIN date_dim ON …',
                "WHERE sr_status = '完成'", 'AND d_moy = 5 AND …'),
        'declares': '注明：退货金额 v2',
        's5': ('检查版本', '注明的 v2 能用吗？'),
        'version_rows': ('v2 存在、未停用', 'v2 是最新版本', 'SQL 含状态过滤', '若注明 v1：已过期，拒绝'),
        's6': ('快照内校验', '在本次查询的快照上，规则都成立？'),
        'snap': '快照里 `store_returns` 已是 16',
        'snap_out': ('未命中：快照内校验', '命中：复用', '未命中：快照内校验'),
        's7': ('执行', '同一快照上执行'), 'run': '执行 SQL', 'result': '结果', 'value': '329.4 万',
        'fail': ('校验失败则', '拒绝执行'),
    },
    'en': {
        'agent': 'User agent', 'mavra': 'MAVRA query service', 'paths': ('find definition', 'run SQL'),
        'text_req': 'Text request', 'question': ('Return amount', 'in May?'), 'ask': 'ask “amount”',
        's1': ('Match name', 'name or alias'),
        'names': (('return amount', True), ('return rate', False), ('revenue', False)),
        's2': ('Data versions', 'last check → now'), 'then_now': ('then', 'now'),
        'changed': 'changed: recheck',
        's3': ('Validate (cache first)', 'look up each rule; validate misses'),
        'rules': ('one row/return', 'date key unique', 'dates complete'),
        'lookup_out': ('cache hit: reuse', 'cache hit: reuse', 'miss: check, cache'),
        's4': ('Return', 'only if valid'), 'valid': 'amount v2, valid',
        'fields': ('`store_returns`', '`SUM(sr_return_amt)`', "`sr_status='done'`"),
        'then': ('then', 'writes SQL'),
        'cache_title': 'Validation cache',
        'cache_note': ('Results are cached per (rule, data version).',
                       'Same rule, same data version: every definition',
                       'and every agent shares one result. Only a new',
                       'data version needs a new check.'),
        'cache_head': ('rule', 'data version', 'written by', 'used in'),
        'cache_rows': (('one row/return', '`store_returns` 15', 'return rate', (3,)),
                       ('date key unique', '`date_dim` 3', 'earlier', (3, 6)),
                       ('dates complete', '`store_returns` 15', 3, ()),
                       ('one row/return', '`store_returns` 16', 6, ()),
                       ('dates complete', '`store_returns` 16', 6, ())),
        'lookup_cache': 'read / write',
        'sql_req': 'SQL request',
        'sql': ('SELECT SUM(sr_return_amt)', 'FROM store_returns', 'JOIN date_dim ON …',
                "WHERE sr_status = 'done'", 'AND d_moy = 5 AND …'),
        'declares': 'declares amount v2',
        's5': ('Check version', 'is the named v2 usable?'),
        'version_rows': ('v2 exists, not retired', 'v2 is the latest', 'SQL keeps the filter',
                         'naming v1: rejected'),
        's6': ('Snapshot check', 'do the rules hold on this snapshot?'),
        'snap': 'snapshot sees `store_returns` 16',
        'snap_out': ('miss: check here', 'hit: reuse', 'miss: check here'),
        's7': ('Run', 'on the same snapshot'), 'run': 'run the SQL', 'result': 'result',
        'value': '3,294,349.93', 'fail': ('a failed rule', 'rejects the SQL'),
    },
}

A_Y, B_Y, LANE = 13.0, 107.0, 40.0
REQ_A = (2.0, A_Y, 44.0, LANE)
S1 = (52.0, A_Y, 45.0, LANE)
S2 = (101.0, A_Y, 52.0, LANE)
S3 = (157.0, A_Y, 86.0, LANE)
S4 = (247.0, A_Y, 51.0, LANE)
CACHE = (157.0, 59.0, 141.0, 40.0)
REQ_B = (2.0, B_Y, 62.0, LANE)
S5 = (69.0, B_Y, 84.0, LANE)
S6 = (157.0, B_Y, 86.0, LANE)
S7 = (247.0, B_Y, 51.0, LANE)
FIELD_BOX = (49.0, 1.0, 250.0, H - 1.5)
PITCH = 5.6


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    # Header -------------------------------------------------------------------------
    rect(*FIELD_BOX, FIELD, None, r=2.8)
    text(2.0, 8.0, L['agent'], TITLE, INK, 'bold')
    rect(52.0, 3.6, 1.1, 5.4, ACC)
    text(55.2, 8.4, L['mavra'], TITLE, ACC_DK, 'bold')
    x = 190.0
    for label, color, steps in zip(L['paths'], (USE, EXEC), ('1–4', '5–7')):
        x += legend_pill(s, x, 6.6, label, color, steps) + 6.0

    # Text request -------------------------------------------------------------------
    x, y, w, h = REQ_A
    node(s, REQ_A)
    text(x + 3.0, y + 7.0, L['text_req'], TITLE, INK, 'bold', width=w - 5)
    person(s, x + 3.0, y + 12.0)
    bx, by, bw, bh = x + 10.5, y + 10.5, w - 13.5, 13.0
    rect(bx, by, bw, bh, ACC_PALE, ACC, .25, r=1.8)
    for k, line in enumerate(L['question']):
        text(bx + bw / 2, by + 5.4 + 5.2 * k, line, NOTE, ACC_DK, align='center', width=bw - 1.6)
    rect(x + 3.0, y + 28.5, w - 6.0, 6.5, WHITE, USE, .3, r=1.2)
    text(x + w / 2, y + 33.0, L['ask'], NOTE, USE, align='center', width=w - 7.0)

    # 1 Match the name ------------------------------------------------------------------
    ex, ey, ew = stage(s, S1, 1, USE, *L['s1'])
    for k, (name, hit) in enumerate(L['names']):
        yy = ey + PITCH * k
        if hit:
            rect(ex - 1.2, yy - 4.3, ew + 2.4, 5.8, ACC_PALE, None, r=.8)
            mark(s, ex + ew - 1.6, yy - 1.5, 'ok')
        else:
            s.line(ex + ew - 2.7, yy - 1.5, ex + ew - .5, yy - 1.5, MUTED, .5)
        text(ex, yy, name, NOTE, INK if hit else MUTED, width=ew - 5.0)

    # 2 Compare data versions ----------------------------------------------------------------
    ex, ey, ew = stage(s, S2, 2, USE, *L['s2'])
    c1, c2 = ex + ew - 11.0, ex + ew - 1.0
    for cx_, head in zip((c1, c2), L['then_now']):
        text(cx_, ey, head, NOTE, MUTED, align='right')
    for k, (table, then, now) in enumerate((('`store_returns`', 14, 15), ('`date_dim`', 3, 3))):
        yy = ey + PITCH * (k + 1)
        if then != now:
            rect(ex - 1.2, yy - 4.3, ew + 2.4, 5.8, AMBER_PALE, AMBER, .25, r=.8)
        text(ex, yy, table, NOTE, INK)
        text(c1, yy, str(then), NOTE, INK, align='right')
        text(c2, yy, str(now), NOTE, WAIT if then != now else INK, align='right')
    text(ex, ey + PITCH * 3, L['changed'], NOTE, WAIT, 'bold', width=ew)

    # 3 Validate, cache first ------------------------------------------------------------------
    ex, ey, ew = stage(s, S3, 3, USE, *L['s3'])
    for k, (rule, out) in enumerate(zip(L['rules'], L['lookup_out'])):
        yy = ey + PITCH * k
        text(ex, yy, rule, NOTE, INK, width=28.0)
        text(ex + 29.0, yy, out, NOTE, MUTED if k < 2 else WAIT, width=ew - 33.6)
        mark(s, ex + ew - 1.6, yy - 1.5, 'ok')

    # 4 Return the valid definition ----------------------------------------------------------
    ex, ey, ew = stage(s, S4, 4, USE, *L['s4'])
    text(ex, ey, L['valid'], NOTE, ACC_DK, 'bold', width=ew)
    for k, field in enumerate(L['fields']):
        text(ex, ey + PITCH * (k + 1), field, NOTE, INK, width=ew + 1.0)

    # The agent then writes the SQL of the second lane --------------------------------------
    xa = REQ_A[0] + 12.0
    route([(xa, A_Y + LANE), (xa, B_Y - 3.4)], INK, THIN, length=HEAD)
    for k, line in enumerate(L['then']):
        text(xa + 3.0, 77.0 + 5.4 * k, line, NOTE, MUTED)

    # The validation cache: note on the left, table on the right ------------------------------
    nx = 55.2
    text(nx, CACHE[1] + 6.5, L['cache_title'], TITLE, ACC_DK, 'bold')
    for k, line in enumerate(L['cache_note']):
        text(nx, CACHE[1] + 13.5 + 5.6 * k, line, NOTE, INK, width=CACHE[0] - nx - 3.0)
    x, y, w, h = CACHE
    rect(*CACHE, WHITE, PANEL_EDGE, .4, r=1.6)
    cols = (x + 3.5, x + 33.0, x + 71.5, x + 78.0, x + 113.0)   # rule, version, mark, writer, users
    hy = y + 6.0
    for cx_, head in zip((cols[0], cols[1], cols[3], cols[4]), L['cache_head']):
        text(cx_, hy, head, NOTE, MUTED)
    s.line(x + 2.0, hy + 2.0, x + w - 2.0, hy + 2.0, RULE, .3)
    for k, (rule, version, writer, users) in enumerate(L['cache_rows']):
        yy = hy + 7.4 + 5.6 * k
        new = not isinstance(writer, str)
        if new:
            rect(x + 1.8, yy - 4.3, w - 3.6, 5.6, '#FBF6EA', None, r=.8)
        text(cols[0], yy, rule, NOTE, INK, width=cols[1] - cols[0] - 1.0)
        text(cols[1], yy, version, NOTE, INK, width=cols[2] - cols[1] - 1.0)
        mark(s, cols[2] + 1.0, yy - 1.5, 'ok')
        if new:
            step(s, cols[3] + 3.0, yy - 1.5, writer, USE if writer == 3 else EXEC, r=2.6)
        else:
            text(cols[3], yy, writer, NOTE, MUTED, width=cols[4] - cols[3] - 1.0)
        for j, n in enumerate(users):
            step(s, cols[4] + 3.0 + 6.8 * j, yy - 1.5, n, USE if n == 3 else EXEC, r=2.6)
    xc = S3[0] + 40.0
    route([(xc, A_Y + LANE), (xc, y)], USE, THIN, heads='both', length=HEAD)
    text(xc + 2.4, (A_Y + LANE + y) / 2 + 2.0, L['lookup_cache'], NOTE, USE)
    route([(xc, y + h), (xc, B_Y)], EXEC, THIN, heads='both', length=HEAD)
    text(xc + 2.4, (y + h + B_Y) / 2 + 2.0, L['lookup_cache'], NOTE, EXEC)

    # SQL request --------------------------------------------------------------------------
    x, y, w, h = REQ_B
    node(s, REQ_B)
    text(x + 3.0, y + 7.0, L['sql_req'], TITLE, INK, 'bold', width=w - 5)
    for k, line in enumerate(L['sql']):
        text(x + 3.0, y + 12.6 + 4.9 * k, line, NOTE, INK, 'code', width=w - 5.0)
    rect(x + 3.0, y + h - 6.6, w - 6.0, 5.6, WHITE, EXEC, .3, r=1.2)
    text(x + w / 2, y + h - 2.5, L['declares'], NOTE, EXEC, align='center', width=w - 7.0)

    # 5 Check the named version ---------------------------------------------------------------
    ex, ey, ew = stage(s, S5, 5, EXEC, *L['s5'])
    for k, line in enumerate(L['version_rows']):
        yy = ey + PITCH * k
        mark(s, ex + 1.4, yy - 1.5, 'ok' if k < 3 else 'fail')
        text(ex + 4.4, yy, line, NOTE, INK if k < 3 else RED, width=ew - 4.4)

    # 6 Validate on the query's snapshot ------------------------------------------------------
    ex, ey, ew = stage(s, S6, 6, EXEC, *L['s6'])
    rect(ex - 1.2, ey - 4.3, ew + 2.4, 5.8, AMBER_PALE, AMBER, .25, r=.8)
    text(ex, ey, L['snap'], NOTE, WAIT, width=ew)
    for k, (rule, out) in enumerate(zip(L['rules'], L['snap_out'])):
        yy = ey + PITCH * (k + 1)
        text(ex, yy, rule, NOTE, INK, width=28.0)
        text(ex + 29.0, yy, out, NOTE, MUTED if k == 1 else WAIT, width=ew - 33.6)
        mark(s, ex + ew - 1.6, yy - 1.5, 'ok')

    # 7 Run on the same snapshot --------------------------------------------------------------
    ex, ey, ew = stage(s, S7, 7, EXEC, *L['s7'])
    text(ex, ey, L['run'], NOTE, INK)
    text(ex, ey + PITCH, L['result'], NOTE, MUTED)
    text(ex + ew, ey + PITCH, L['value'], NOTE + 1, EXEC, 'bold', align='right')
    for k, line in enumerate(L['fail']):
        text(ex, ey + PITCH * (k + 2), line, NOTE, MUTED, width=ew)

    # Arrows from one step to the next ----------------------------------------------------------
    for (l, r), color in (((REQ_A, S1), USE), ((S1, S2), USE), ((S2, S3), USE), ((S3, S4), USE),
                          ((REQ_B, S5), EXEC), ((S5, S6), EXEC), ((S6, S7), EXEC)):
        yy = l[1] + 5.6
        x0 = l[0] + l[2] + (3.0 if l in (REQ_A, REQ_B) else 0)
        route([(x0, yy), (r[0], yy)], color, THIN, length=HEAD)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
