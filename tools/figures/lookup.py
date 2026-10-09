"""Deck figure 2 (rely): one use of store revenue, steps 1-8 of deck figure 1 in detail.

The state is the incremental load of the end-to-end study: store_sales has had a
write (table version v14 -> v15; date_dim unchanged at v7; version numbers are
illustrative). User agent B asks for September store revenue.
Top lane: find_metric("门店营业额") matches two definitions that read store_sales
(门店营业额 and 电子品类门店营业额, both at revision v2); their recorded table
versions differ from the current ones, so maintenance runs the two conditions on
store_sales once (5.3 s and 0.15 s) and both definitions share the results; the
two date_dim conditions are skipped because date_dim did not change; v2 is
returned as valid. Middle: the validation cache keyed by (condition, table
version), with where each result came from and who used it. Bottom lane: B's
run_sql declares revision 1 (= v2); the pre-execution check confirms v2 is the
current revision and finds every condition already decided at the snapshot's
table versions, so nothing is re-run; the SQL runs on the same snapshot and
returns 26,139,303.60, the reference answer.
Values: record M1-P1 of the append phase in noctis
results/scen-20261008-opt/metric-1791439498065570 (metric-global-opt; events
`maintenance` for 电子品类门店营业额 with the executed checks and their times,
门店营业额 refreshed with both store_sales conditions reused and 0 queries; the
record's declared revision and answer). Drawn at slide size (300 mm, 12-15 pt),
Chinese only, with standard database terms rather than the paper's notation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import (EXEC, HEAD, NOTE, PANEL_EDGE, THIN, TITLE, USE, WAIT, baseline, legend_pill,  # noqa: E402
                   mark, node, person, stage, step)
from style import ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, FIELD, INK, MUTED, RED, RULE, WHITE  # noqa: E402

NAME = 'lookup'
LANGS = ('zh',)                                  # the report deck is Chinese
W, H = 300.0, 134.0

LABELS = {
    'zh': {
        'agent': '用户 agent B', 'mavra': 'MAVRA：一次使用的第 1–8 步',
        'paths': ('查询指标定义', '执行 SQL'),
        'question': ('9 月门店', '营业额？'), 'call': ('`find_metric(`', '`"门店营业额")`'),
        's2': ('读定义，比较表版本', '名称匹配到两条定义'),
        'names': ('门店营业额 v2', '电子品类门店营业额 v2'),
        'tables': (('`store_sales`', 'v14 → v15'), ('`date_dim`', 'v7（未变）')),
        's3': ('维护：补齐缺少的验证结果', '两条定义共用，每项只执行一次'),
        'conds': (('粒度键唯一', '`store_sales` v15', '执行', 'run'),
                  ('日期键完整性', '`store_sales` v15', '执行', 'run'),
                  ('日期键唯一', '`date_dim` v7', '表未变', 'same'),
                  ('日期键按月连续', '`date_dim` v7', '表未变', 'same')),
        's5': ('返回有效修订', '附口径、示例 SQL 与注意事项'),
        'valid': '门店营业额 v2，有效',
        'fields': ('度量 `SUM(ss_net_paid)`', '期间：按日期键范围筛选', '不连接 `date_dim`'),
        'then': ('拿到 v2 后', '照示例写 SQL'),
        'cache_title': '验证结果缓存',
        'cache_note': ('键为（条件，表版本）：', '同一表版本上只验证一次，', '所有定义、所有 agent 共享；',
                       '表有写入，旧结果不再命中'),
        'cache_head': ('条件', '表版本', '结果', '来源', '本次用于'),
        'cache_rows': (('粒度键唯一', '`store_sales` v14', '此前', '不再命中：表已写入', 'old'),
                       ('粒度键唯一', '`store_sales` v15', '执行，5.3 秒', '两条定义、', 'new'),
                       ('日期键完整性', '`store_sales` v15', '执行，0.15 秒', '两条定义、', 'new'),
                       ('日期键唯一', '`date_dim` v7', '此前', '两条定义、', 'kept'),
                       ('日期键按月连续', '`date_dim` v7', '此前', '两条定义、', 'kept')),
        'write': '写入', 'reuse': '复用',
        'run_sql': '`run_sql(`',
        'sql': ('`SELECT SUM(ss_net_paid)`', '`FROM store_sales WHERE`', '`ss_sold_date_sk BETWEEN …`'),
        'declares': ('`metrics: [门店营业额,`', '`revision: 1])`'), 'gloss': '即 v2',
        's7': '执行前验证',
        'declared_head': '核对声明',
        'declared': (('v2 是当前修订：通过', 'ok', INK), ('已失效的修订：拒绝', 'fail', RED),
                     ('未声明：照常执行，无此保证', None, MUTED)),
        'snap_head': '在本查询的快照上验证',
        'snap': (('快照：`store_sales` v15、`date_dim` v7', None, INK),
                 ('4 个条件都已有结果：复用', 'ok', INK),
                 ('快照已是新版本：当场验证', None, MUTED)),
        's8': '同一快照上执行',
        'run': ('执行 SQL', '29 ms'), 'result': ('结果', '2613.9 万'),
        'answer': '与参考答案一致', 'trace': '答案 ← 查询 #1 ← v2',
    },
}

A_Y, LA = 11.5, 39.0                             # top lane: find_metric
M_Y, MH = 56.0, 35.0                             # validation cache
B_Y, LB = 97.0, 36.0                             # bottom lane: run_sql
REQ_A = (2.0, A_Y, 41.0, LA)
S2 = (51.0, A_Y, 60.0, LA)
S3 = (115.0, A_Y, 92.0, LA)
S5 = (211.0, A_Y, 87.0, LA)
CACHE = (115.0, M_Y, 183.0, MH)
REQ_B = (2.0, B_Y, 62.0, LB)
S7 = (72.0, B_Y, 140.0, LB)
S8 = (216.0, B_Y, 82.0, LB)
FIELD_BOX = (48.5, 1.0, 250.5, H - 1.5)
PITCH = 5.2


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    # Header -------------------------------------------------------------------------
    rect(*FIELD_BOX, FIELD, None, r=2.8)
    text(2.0, 6.2, L['agent'], TITLE, INK, 'bold')
    rect(51.5, 3.0, 1.1, 5.4, ACC)
    text(54.6, 7.8, L['mavra'], TITLE, ACC_DK, 'bold')
    x = 205.0
    for label, color, steps in zip(L['paths'], (USE, EXEC), ('1–5', '6–8')):
        x += legend_pill(s, x, 5.8, label, color, steps) + 6.0

    # 1 The question and the call ---------------------------------------------------------
    x, y, w, h = REQ_A
    node(s, REQ_A)
    person(s, x + 3.0, y + 3.5)
    bx, by, bw = x + 10.5, y + 2.5, w - 13.0
    rect(bx, by, bw, 12.5, ACC_PALE, ACC, .25, r=1.8)
    for k, line in enumerate(L['question']):
        text(bx + bw / 2, by + 5.2 + 5.0 * k, line, NOTE, ACC_DK, align='center', width=bw - 1.6)
    cx, cy, cw = x + 2.5, y + 18.5, w - 5.0
    rect(cx, cy, cw, 17.5, WHITE, USE, .3, r=1.2)
    step(s, cx + 4.0, cy + 4.4, 1, USE)
    a, b = L['call']
    text(cx + 8.4, baseline(cy + 4.4, NOTE - 1), a, NOTE - 1, USE, width=cw - 9.0)
    text(cx + 2.4, cy + 13.2, b, NOTE - 1, USE, width=cw - 3.0)

    # 2 Read the definitions, compare table versions -----------------------------------------
    ex, ey, ew = stage(s, S2, 2, USE, *L['s2'])
    for k, name in enumerate(L['names']):
        yy = ey + PITCH * k
        rect(ex - 1.2, yy - 4.1, ew + 2.4, 5.4, ACC_PALE, None, r=.8)
        text(ex, yy, name, NOTE, INK, width=ew - 4.4)
        mark(s, ex + ew - 1.6, yy - 1.5, 'ok')
    for k, (table, versions) in enumerate(L['tables']):
        yy = ey + PITCH * (k + 2)
        changed = k == 0
        if changed:
            rect(ex - 1.2, yy - 4.1, ew + 2.4, 5.4, AMBER_PALE, AMBER, .25, r=.8)
        text(ex, yy, table, NOTE, INK)
        text(ex + ew, yy, versions, NOTE, WAIT if changed else MUTED, align='right')

    # 3 Maintenance fills the missing results ------------------------------------------------
    ex, ey, ew = stage(s, S3, 3, USE, *L['s3'])
    for k, (cond, version, action, kind) in enumerate(L['conds']):
        yy = ey + PITCH * k
        text(ex, yy, cond, NOTE, INK, width=30.5)
        text(ex + 31.5, yy, version, NOTE, INK, width=32.5)
        text(ex + 65.0, yy, action, NOTE, WAIT if kind == 'run' else MUTED, width=ew - 69.6)
        mark(s, ex + ew - 1.6, yy - 1.5, 'ok')

    # 5 Return the valid revision -------------------------------------------------------------
    ex, ey, ew = stage(s, S5, 5, USE, *L['s5'])
    text(ex, ey, L['valid'], NOTE, ACC_DK, 'bold', width=ew)
    for k, field in enumerate(L['fields']):
        text(ex, ey + PITCH * (k + 1), field, NOTE, INK, width=ew)

    # The agent then writes its SQL from the example ------------------------------------------
    xa = REQ_A[0] + 12.0
    route([(xa, A_Y + LA), (xa, B_Y - 3.4)], INK, THIN, length=HEAD)
    for k, line in enumerate(L['then']):
        text(xa + 3.0, 70.0 + 5.4 * k, line, NOTE, MUTED, width=FIELD_BOX[0] - xa - 4.0)

    # The validation cache: a note on the left, the entries on the right ----------------------
    nx = 52.0
    text(nx, M_Y + 6.0, L['cache_title'], TITLE, ACC_DK, 'bold')
    for k, line in enumerate(L['cache_note']):
        text(nx, M_Y + 12.6 + 5.4 * k, line, NOTE, INK, width=CACHE[0] - nx - 2.0)
    x, y, w, h = CACHE
    rect(*CACHE, WHITE, PANEL_EDGE, .4, r=1.6)
    cols = (x + 3.5, x + 35.0, x + 69.0, x + 84.0, x + 121.0)   # condition, version, result, source, used by
    hy = y + 5.4
    for cx_, head in zip(cols, L['cache_head']):
        text(cx_, hy, head, NOTE, MUTED)
    s.line(x + 2.0, hy + 1.8, x + w - 2.0, hy + 1.8, RULE, .3)
    for k, (cond, version, source, used, kind) in enumerate(L['cache_rows']):
        yy = hy + 7.0 + PITCH * k
        ink = MUTED if kind == 'old' else INK
        if kind == 'new':
            rect(x + 1.8, yy - 4.0, w - 3.6, 5.2, '#FBF6EA', None, r=.8)
        text(cols[0], yy, cond, NOTE, ink, width=cols[1] - cols[0] - 1.0)
        text(cols[1], yy, version, NOTE, ink, width=cols[2] - cols[1] - 1.0)
        mark(s, cols[2] + 3.4, yy - 1.5, 'ok')
        if kind == 'new':
            step(s, cols[3] + 2.6, yy - 1.5, 3, USE, r=2.4)
            text(cols[3] + 6.6, yy, source, NOTE, WAIT, width=cols[4] - cols[3] - 7.6)
        else:
            text(cols[3], yy, source, NOTE, MUTED, width=cols[4] - cols[3] - 1.0)
        tw = text(cols[4], yy, used, NOTE, ink, width=x + w - cols[4] - 8.0)
        if kind != 'old':
            step(s, cols[4] + tw + 2.6, yy - 1.5, 7, EXEC, r=2.4)
    # 4: maintenance writes into the cache; 7: the pre-execution check reuses it.
    xc = 168.0
    route([(xc, A_Y + LA), (xc, M_Y)], USE, THIN, length=HEAD)
    step(s, xc + 4.6, (A_Y + LA + M_Y) / 2, 4, USE, r=2.6)
    text(xc + 8.6, baseline((A_Y + LA + M_Y) / 2, NOTE), L['write'], NOTE, USE)
    route([(xc, M_Y + MH), (xc, B_Y)], EXEC, THIN, heads='both', length=HEAD)
    step(s, xc + 4.6, (M_Y + MH + B_Y) / 2, 7, EXEC, r=2.6)
    text(xc + 8.6, baseline((M_Y + MH + B_Y) / 2, NOTE), L['reuse'], NOTE, EXEC)

    # 6 The SQL request with its declaration ---------------------------------------------------
    x, y, w, h = REQ_B
    node(s, REQ_B)
    step(s, x + 5.0, y + 4.8, 6, EXEC)
    text(x + 9.4, baseline(y + 4.8, NOTE - 1), L['run_sql'], NOTE - 1, EXEC, width=w - 11.0)
    for k, line in enumerate(L['sql']):
        text(x + 3.0, y + 11.6 + 4.5 * k, line, NOTE - 1, INK, width=w - 4.5)
    dy = y + h - 12.4
    rect(x + 2.0, dy, w - 4.0, 11.0, WHITE, EXEC, .3, r=1.2)
    a, b = L['declares']
    text(x + 3.6, dy + 4.6, a, NOTE - 1, EXEC, width=w - 7.0)
    tb = text(x + 3.6, dy + 9.2, b, NOTE - 1, EXEC)
    text(x + 5.6 + tb, dy + 9.2, L['gloss'], NOTE - 1, ACC_DK, 'bold', width=w - 9.2 - tb)

    # 7 Check the declaration and the conditions on the query's snapshot -----------------------
    ex, ey, ew = stage(s, S7, 7, EXEC, L['s7'], None)
    left = 58.5                                   # declaration check | conditions on the snapshot
    for x0, room, head, lines in ((ex, left, L['declared_head'], L['declared']),
                                  (ex + left + 4.0, ew - left - 4.0, L['snap_head'], L['snap'])):
        text(x0, ey, head, NOTE, EXEC, 'bold', width=room)
        for k, (line, kind, ink) in enumerate(lines):
            yy = ey + PITCH * (k + 1)
            text(x0, yy, line, NOTE, ink, width=room - (4.6 if kind else 0))
            if kind:
                mark(s, x0 + room - 1.6, yy - 1.5, kind)
    s.line(ex + left + 2.0, ey - 3.6, ex + left + 2.0, ey + PITCH * 3 + 1.0, RULE, .3)

    # 8 Run on the same snapshot ------------------------------------------------------------------
    ex, ey, ew = stage(s, S8, 8, EXEC, L['s8'], None)
    for k, (label, value) in enumerate((L['run'], L['result'])):
        yy = ey + PITCH * k
        text(ex, yy, label, NOTE, INK)
        bold = k == 1
        text(ex + ew - (4.6 if bold else 0), yy, value, NOTE + (1 if bold else 0), EXEC if bold else MUTED,
             'bold' if bold else 'sans', align='right')
        if bold:
            mark(s, ex + ew - 1.6, yy - 1.5, 'ok')
    text(ex, ey + PITCH * 2, L['answer'], NOTE, ACC_DK, width=ew)
    text(ex, ey + PITCH * 3, L['trace'], NOTE, MUTED, width=ew)

    # Arrows from one step to the next ----------------------------------------------------------
    for (l, r), color in (((REQ_A, S2), USE), ((S2, S3), USE), ((S3, S5), USE),
                          ((REQ_B, S7), EXEC), ((S7, S8), EXEC)):
        yy = l[1] + 5.6
        x0 = l[0] + l[2] + (3.0 if l in (REQ_A, REQ_B) else 0)
        route([(x0, yy), (r[0], yy)], color, THIN, length=HEAD)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
