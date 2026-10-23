"""Deck run figure 3 (maintain): a data correction breaks v2; the next use finds it and publishes v3.

Top: the write (更正保留旧行: the old amount is kept as a non-current row, the
current row is cut to 90%), the table version it changes, and the next use (B asks
again; find_metric sees the version change and maintains first). Middle: only the
preconditions whose tables changed are re-checked (the two date_dim ones are
skipped; referential integrity passes; primary-key uniqueness fails), the repair
search tries each value of the low-cardinality columns and keeps the only filter
that leaves one row per key without losing keys, and the regression test recomputes
the learning question on learning-time data. Bottom: v3 is published; B's answer
next to that of the stale shared SQL; and the other outcome, a duplicate load,
where no filter restores the grain and the definition is invalidated.
Values: trace run (noctis results/scen-20261008-trace/metric-1791449167012862):
65,915 rows written, store_sales DML count 1,000,000 -> 1,131,830, the revision
phase's maintenance event (coverage executed 0.2 s, 0.97% <= 1.03% + 0.1; grain
executed 6.0 s, 1,055,610 rows / 989,695 keys), repair candidate ss_is_current =
'1', gates G3 G4 G5 G8, 31.6 s, B's answer 12,932,888.04; the stale answer
14,300,525.64 from results/scen-20261010 (example retrieval and invalidate-on-schema-
change, 5 of 5 runs); duplicate load from the opt run (results/scen-20261008-opt/
metric-1791439498065570): 1,110,165 rows / 1,000,000 keys, no filter, B explored
alone for 158 s and answered correctly. Candidate columns: ss_is_current (2 values)
and ss_quantity (9 values) are the store_sales columns with at most 20 distinct values.
Steps 1-8 give the reading order. Colours from deckpal.py; slide size (300 mm,
10-15 pt), Chinese only, no years.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import HEAD, NOTE, THICK, THIN, TITLE, baseline, mark, step  # noqa: E402
from style import INK, MUTED, WHITE  # noqa: E402
from deckparts import SMALL, TINY, check, ex, headed, panel, pill, pill_width, section  # noqa: E402
import deckpal as P  # noqa: E402

NAME = 'run-maintain'
LANGS = ('zh',)
W, H = 300.0, 134.0
M = P.MAINT

W1 = (4.0, 12.0, 116.0, 36.0)                     # the write
W2 = (128.0, 12.0, 80.0, 36.0)                    # the table version
W3 = (216.0, 12.0, 80.0, 36.0)                    # the next use
C4 = (4.0, 56.0, 120.0, 48.0)                     # re-check the affected preconditions
C5 = (132.0, 56.0, 96.0, 48.0)                    # repair search
C6 = (236.0, 56.0, 60.0, 48.0)                    # regression test
BR = (4.0, 110.0, 120.0, 21.0)                    # the other outcome: invalidation
RS = (132.0, 110.0, 96.0, 21.0)                   # B's answer next to the stale one
V3 = (236.0, 110.0, 60.0, 21.0)                   # v3 published


def draw(s, lang):
    text, route = s.text, s.route
    section(s, 4.0, 6.4, '维护：数据更正之后，下一次使用时发现并修复', '真实运行记录 · 门店营业额 v2 → v3',
            color=M, text_color=P.MAINT_TEXT)

    # 1 The write --------------------------------------------------------------------------------------
    x, y, w, h = W1
    headed(s, W1, '数据更正（更正保留旧行）', n=1, color=P.PENDING, edge=P.PENDING, fill='#FFFBF9', size=NOTE + 2)
    for k, line in enumerate(('小票号尾数为 7 的销售：', '旧金额另存一行，标为非当前；', '当前行金额改为九折')):
        text(x + 3.0, y + 16.0 + 5.4 * k, line, SMALL, INK, width=64.0)
    ex(s, x + 3.0, y + 32.4, '写入 65,915 行', width=64.0, size=SMALL)
    t = (x + 70.0, y + 12.6, 43.0, 21.0)          # one corrected sale (illustration)
    s.rect(*t, WHITE, P.PANEL, .3, r=1.0)
    text(t[0] + 2.0, t[1] + 4.4, '一笔销售（示意）', TINY - 1, MUTED, 'bold')
    cols = (t[0] + 2.0, t[0] + 22.0)
    for cx, head in zip(cols, ('is_current', 'net_paid')):
        text(cx, t[1] + 9.2, head, TINY - 1, INK, 'code')
    for k, (a, b, color, tag) in enumerate((('0', '100.00', MUTED, '旧'), ('1', ' 90.00', INK, '当前'))):
        yb = t[1] + 14.0 + 4.8 * k
        if k == 0:
            s.rect(t[0] + .6, yb - 3.4, t[2] - 1.2, 4.4, P.PENDING_PALE, None, r=.6)
        text(cols[0] + 6.0, yb, a, TINY, color, 'code')
        text(cols[1], yb, b, TINY, color, 'code')
        text(t[0] + t[2] - 1.6, yb, tag, TINY - 1.5, color, align='right')

    # 2 The table version ------------------------------------------------------------------------------
    x, y, w, h = W2
    headed(s, W2, '表版本变了', n=2, color=P.PENDING, edge=P.PENDING, fill='#FFFBF9', size=NOTE + 2)
    text(x + 3.0, y + 16.0, 'store_sales', SMALL, INK, 'code')
    ex(s, x + 3.0, y + 21.6, 'DML 1,000,000 → 1,131,830', width=w - 6.0, size=SMALL)
    text(x + 3.0, y + 27.4, 'date_dim', SMALL, INK, 'code')
    text(x + 3.0 + measure('date_dim', SMALL, 'code') + 2.4, y + 27.4, '没变', SMALL, MUTED)
    text(x + 3.0, y + 33.2, '写入时 MAVRA 什么都不做', TINY, MUTED, width=w - 6.0)

    # 3 The next use ------------------------------------------------------------------------------------
    x, y, w, h = W3
    headed(s, W3, 'B 再次提问', n=3, color=P.USE, edge=P.USE, fill='#F7F9FC', size=NOTE + 2)
    text(x + 3.0, y + 16.0, '“9 月的门店营业额是多少？”', SMALL, INK, width=w - 6.0)
    text(x + 3.0, y + 22.2, '`find_metric` 发现依赖表的', SMALL, INK, width=w - 6.0)
    text(x + 3.0, y + 27.6, '版本和记录的不同', SMALL, INK, width=w - 6.0)
    text(x + 3.0, y + 33.2, '先维护，再把结果返回给 B', SMALL, P.USE_TEXT, 'bold', width=w - 6.0)

    # 4 Re-check only the affected preconditions --------------------------------------------------------
    x, y, w, h = C4
    headed(s, C4, '只重查受影响的前提', n=4, color=M, size=NOTE + 2)
    hx = (x + 3.0, x + 35.0, x + 58.0)
    for cx, head in zip(hx, ('v2 的前提', '处理', '结果')):
        text(cx, y + 15.0, head, TINY, MUTED, 'bold')
    rows = (('维表主键唯一', '跳过', None, 'date_dim 没写入'), ('日期键连续', '跳过', None, 'date_dim 没写入'),
            ('参照完整性', '执行 0.2 秒', 'ok', '关联不上 0.97% ≤ 1.13%'),
            ('主键唯一', '执行 6.0 秒', 'fail', '1,055,610 行，989,695 个键'))
    for k, (name, act, kind, res) in enumerate(rows):
        yb = y + 21.4 + 6.0 * k
        if kind == 'fail':
            s.rect(x + 1.6, yb - 4.4, w - 3.2, 6.0, '#FCE9E6', None, r=.8)
        text(hx[0], yb, name, SMALL, INK, 'bold')
        text(hx[1], yb, act, SMALL, M if kind else MUTED, 'bold' if kind else 'sans')
        if kind:
            mark(s, hx[2] + 1.4, yb - 1.4, kind, P.OK, P.FAIL)
            text(hx[2] + 4.6, yb, res, SMALL, P.FAIL_TEXT if kind == 'fail' else P.EXAMPLE, width=x + w - hx[2] - 7.6)
        else:
            text(hx[2] + 4.6, yb, res, SMALL, MUTED, width=x + w - hx[2] - 7.6)
    text(x + 3.0, y + h - 2.8, '主键唯一不成立 → v2 失效，记录原因', SMALL, P.FAIL_TEXT, 'bold', width=w - 6.0)

    # 5 Repair: the one filter that restores the grain --------------------------------------------------
    x, y, w, h = C5
    headed(s, C5, '自动修复：找唯一的过滤', n=5, color=M, size=NOTE + 2)
    text(x + 3.0, y + 15.0, '取值 ≤ 20 个的列，逐个取值试：每键一行、不丢键？', TINY, MUTED, width=w - 6.0)
    cands = (("ss_is_current = '1'", '每键一行，不丢键', 'ok'), ("ss_is_current = '0'", '只有被更正的销售', 'fail'),
             ('ss_quantity = 1 … 9', '每个取值只有一部分', 'fail'))
    for k, (f, why, kind) in enumerate(cands):
        yb = y + 21.4 + 6.0 * k
        if kind == 'ok':
            s.rect(x + 1.6, yb - 4.4, w - 3.2, 6.0, P.MAINT_PALE, None, r=.8)
        mark(s, x + 4.4, yb - 1.4, kind, P.OK, P.FAIL)
        text(x + 7.6, yb, f, SMALL, INK if kind == 'ok' else MUTED, 'code')
        text(x + 50.0, yb, why, SMALL, P.EXAMPLE if kind == 'ok' else MUTED, width=w - 52.0)
    text(x + 3.0, y + h - 2.8, '恰好 1 个才采用；0 个或多个：不修复', SMALL, P.MAINT_TEXT, 'bold', width=w - 6.0)

    # 6 Regression on learning-time data -----------------------------------------------------------------
    x, y, w, h = C6
    headed(s, C6, '回归测试', n=6, color=M, size=NOTE + 2)
    text(x + 3.0, y + 16.0, '在学习时的数据上', SMALL, INK)
    text(x + 3.0, y + 21.4, '重算学习题 3 月', SMALL, INK)
    ex(s, x + 3.0, y + 28.0, '13,570,368.70', width=w - 6.0, size=SMALL)
    check(s, x + 3.0, y + 34.6, '= 学习时判对的答案', size=SMALL, color=P.PUBLISH_TEXT, width=w - 6.0)
    text(x + 3.0, y + h - 2.8, 'as-of 学习时刻', TINY, MUTED)

    # 7 v3 published ----------------------------------------------------------------------------------
    x, y, w, h = V3
    s.rect(*V3, M, None, r=1.6)
    s.circle(x + 5.6, y + 5.8, 3.0, WHITE)
    text(x + 5.6, baseline(y + 5.8, SMALL), '7', SMALL, P.MAINT_TEXT, 'bold', 'center')
    text(x + 10.8, baseline(y + 5.8, NOTE + 2), '发布 v3', NOTE + 2, WHITE, 'bold')
    text(x + 3.0, y + 13.0, "v2 + `ss_is_current = '1'`", TINY + .5, WHITE, width=w - 6.0)
    text(x + 3.0, y + 18.2, '31.6 秒，只做一次', TINY + .5, WHITE)

    # 8 B's answer, next to the stale shared SQL --------------------------------------------------------
    x, y, w, h = RS
    half = w / 2
    s.rect(x, y, half, h, P.USE, None, r=1.6)
    s.rect(x + half - 2.0, y, 2.0, h, P.USE, None)
    s.rect(x + half, y, half, h, '#FCE9E6', None, r=1.6)
    s.rect(x + half, y, 2.0, h, '#FCE9E6', None)
    s.rect(*RS, None, P.PANEL, .35, r=1.6)
    s.circle(x + 5.0, y + 5.4, 2.6, WHITE)
    text(x + 5.0, baseline(y + 5.4, TINY), '8', TINY, P.USE_TEXT, 'bold', 'center')
    text(x + 9.6, baseline(y + 5.4, TINY), 'B 用 v3 的答案', TINY, WHITE, 'bold')
    text(x + 3.0, y + 15.4, '1293.3 万', TITLE + 1, WHITE, 'bold')
    mark(s, x + half - 5.0, y + 13.6, 'ok', WHITE, WHITE)
    text(x + 3.0, y + 19.6, '判题正确', TINY - .5, WHITE)
    text(x + half + 3.0, baseline(y + 5.4, TINY), '不维护的共享 SQL', TINY, P.FAIL_TEXT, 'bold')
    text(x + half + 3.0, y + 15.4, '1430.1 万', TITLE + 1, P.FAIL_TEXT, 'bold')
    mark(s, x + w - 5.0, y + 13.6, 'fail', P.OK, P.FAIL)
    text(x + half + 3.0, y + 19.6, '旧金额也算进去，+10.6%', TINY - .5, INK, width=half - 4.0)

    # The other outcome: no filter, invalidation ------------------------------------------------------------
    x, y, w, h = BR
    s.rect(*BR, '#FFF8F7', P.FAIL, .45, r=1.6, dash=(1.6, 1.0))
    s.circle(x + 5.4, y + 5.6, 2.8, P.FAIL)
    s.line(x + 4.4, y + 4.6, x + 6.4, y + 6.6, WHITE, .5)
    s.line(x + 4.4, y + 6.6, x + 6.4, y + 4.6, WHITE, .5)
    text(x + 10.6, baseline(y + 5.6, NOTE + 1), '修不好时：指标失效', NOTE + 1, P.FAIL_TEXT, 'bold')
    text(x + 3.0, y + 13.4, '重复加载：完全相同的行再装一遍，没有过滤能恢复每键一行', TINY, INK, width=w - 6.0)
    ex(s, x + 3.0, y + 18.6, '1,110,165 行，1,000,000 个键；通知 B，B 自己探索 158 秒答对', width=w - 6.0, size=TINY)

    # Arrows -------------------------------------------------------------------------------------------------
    ya = W1[1] + 21.0
    route([(W1[0] + W1[2], ya), (W2[0], ya)], P.PENDING, THIN, length=HEAD)
    route([(W2[0] + W2[2], ya), (W3[0], ya)], P.USE, THIN, length=HEAD)
    xb = W3[0] + W3[2] / 2
    route([(xb, W3[1] + W3[3]), (xb, 52.0), (C4[0] + 60.0, 52.0), (C4[0] + 60.0, C4[1])], M, THIN, length=HEAD,
          radius=1.6)
    yc = C4[1] + 27.0
    route([(C4[0] + C4[2], yc), (C5[0], yc)], P.FAIL, THIN, length=HEAD)
    route([(C5[0] + C5[2], yc), (C6[0], yc)], M, THIN, length=HEAD)
    xv = C6[0] + C6[2] / 2
    route([(xv, C6[1] + C6[3]), (xv, V3[1])], M, THICK, length=HEAD)
    yv = V3[1] + V3[3] / 2
    route([(V3[0], yv), (RS[0] + RS[2], yv)], P.USE, THIN, length=HEAD)
    xr = C5[0] + 16.0
    route([(xr, C5[1] + C5[3]), (xr, 107.0), (BR[0] + 60.0, 107.0), (BR[0] + 60.0, BR[1])], P.FAIL, THIN,
          dash=(1.4, .9), length=HEAD, radius=1.4)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
