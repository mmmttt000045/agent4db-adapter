"""Deck run figure 2 (use): a user agent that knows only the metric's name, on the recorded run.

User agent B asks for September store revenue without the business meaning.
find_metric matches the name, compares the dependency versions (unchanged, so no
checks) and returns the valid revision v2: its meaning, structure, caveats and
example SQL, which is what B reads (right). B writes the key-range SQL and
declares v2 in run_sql; MAVRA checks the call (read-only query, the declared
revision exists and is valid, the SQL review) and executes it; the result goes
back to B. The bottom-left card sets the answer next to that of agents without
shared memory in the five-run study.
Values: trace run (noctis results/scen-20261008-trace/metric-1791449167012862,
copy in exp/2026-10-08-optimize/trace), holdout M1-P1: 4 turns / 6 tool calls /
7.4 s, find_metric 4 ms, run_sql 24 ms, 13,069,651.80 judged correct; without
shared memory: results/scen-20261010 (method `middle`), M1-P1 holdout, 5 of 5 runs
used ss_ext_sales_price, 14,137,928.00, 24.4 s on average.
Steps 1-7 give the reading order. Colours from deckpal.py; slide size (300 mm,
10-15 pt), Chinese only, no years.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import HEAD, NOTE, THICK, THIN, TITLE, baseline, person, slab, step, table_card  # noqa: E402
from style import INK, MUTED, WHITE  # noqa: E402
from deckparts import (SMALL, TINY, check, code_panel, ex, headed, panel, pill, pill_width, section)  # noqa: E402
import deckpal as P  # noqa: E402

NAME = 'run-use'
LANGS = ('zh',)
W, H = 300.0, 134.0
U = P.USE

B = (4.0, 12.0, 86.0, 32.0)                       # user agent B and the question
SQL = (4.0, 50.0, 86.0, 48.0)                     # B's SQL with the declared revision
RES = (4.0, 104.0, 86.0, 26.0)                    # the answer, next to no shared memory
FIELD = (98.0, 12.0, 102.0, 118.0)                # MAVRA
F = (103.0, 24.0, 92.0, 42.0)                     # find_metric
R = (103.0, 72.0, 92.0, 54.0)                     # run_sql
D = (208.0, 12.0, 88.0, 88.0)                     # the definition B reads
DB = (208.0, 108.0, 88.0, 22.0)


def draw(s, lang):
    text, route = s.text, s.route
    section(s, 4.0, 6.4, '使用：用户 agent B 只知道指标名', '真实运行记录 · 4 轮、6 次工具调用、7.4 秒')

    # B and its question --------------------------------------------------------------------------
    x, y, w, h = B
    panel(s, B, U, '#F7F9FC')
    person(s, x + 3.6, y + 3.0, U)
    text(x + 11.6, baseline(y + 6.4, TITLE), '用户 agent B', TITLE, INK, 'bold')
    pill(s, x + w - 3.0 - pill_width('新问题'), y + 6.4, '新问题', U)
    s.rect(x + 3.0, y + 13.0, w - 6.0, 16.0, WHITE, P.PANEL, .35, r=1.2)
    text(x + 5.6, y + 19.6, '9 月的门店营业额是多少？', NOTE + 1, INK, 'bold')
    text(x + 5.6, y + 25.6, '只给指标名，不给口径', SMALL, MUTED)
    route([(x + w / 2, y + h), (x + w / 2, SQL[1])], U, THIN, length=HEAD)

    # B's SQL ------------------------------------------------------------------------------------------
    x, y, w, h = SQL
    headed(s, SQL, '照着示例写 SQL，声明版本', n=3, color=U)
    code_panel(s, (x + 3.0, y + 12.0, w - 6.0, 32.0), [
        'select round(sum(ss_net_paid), 2)',
        'from store_sales',
        'where ss_sold_date_sk between',
        '  (select min(d_date_sk) … 9 月)',
        '  and (select max(d_date_sk) … 9 月)',
        [('metrics = [门店营业额 v2]', U)],
    ], size=TINY + .5, pitch=4.5, first=5.0)
    mw = measure('metrics = [门店营业额 v2]', TINY + .5, 'code') + 2.4
    s.rect(x + 4.2, y + 12.0 + 5.0 + 4.5 * 5 - 3.5, mw, 4.8, None, U, .4, r=.8)

    # The answer, and agents without shared memory -------------------------------------------------------
    x, y, w, h = RES
    half = 43.0
    s.rect(x, y, half, h, U, None, r=1.6)
    s.rect(x + half - 2.0, y, 2.0, h, U, None)
    text(x + 3.0, y + 6.4, 'MAVRA', SMALL, WHITE, 'bold')
    text(x + 3.0, y + 15.4, '1307.0 万', TITLE + 2, WHITE, 'bold')
    text(x + 3.0, y + 22.0, '判题正确 · 7.4 秒', TINY, WHITE)
    s.rect(x + half, y, w - half, h, '#FCE9E6', None, r=1.6)
    s.rect(x + half, y, 2.0, h, '#FCE9E6', None)
    text(x + half + 3.0, y + 6.4, '没有共享记忆', SMALL, P.FAIL_TEXT, 'bold')
    text(x + half + 3.0, y + 15.4, '1413.8 万', TITLE + 2, P.FAIL_TEXT, 'bold')
    text(x + half + 3.0, y + 22.0, '5 次都选错列 · 24.4 秒', TINY, INK, width=w - half - 4.0)
    s.rect(*RES, None, P.PANEL, .35, r=1.6)

    # MAVRA ------------------------------------------------------------------------------------------------
    x, y, w, h = FIELD
    s.rect(*FIELD, P.FIELD, None, r=2.8)
    s.rect(x + 4.0, y + 2.2, 1.1, 5.4, U)
    text(x + 7.2, y + 7.0, 'MAVRA 共享记忆层', TITLE - 1, P.USE_TEXT, 'bold')

    def tool_box(b, n, name, cost):
        x, y, w, h = b
        panel(s, b, P.PANEL)
        step(s, x + 5.8, y + 6.4, n, U, r=3.0)
        tw = pill(s, x + 11.2, y + 6.4, '使用', U)
        text(x + 13.8 + tw, baseline(y + 6.4, NOTE + 1), name, NOTE + 1, INK, 'code')
        pw = pill_width(cost, SMALL, 'sans')
        pill(s, x + w - 3.0 - pw, y + 6.4, cost, '#EEF0F4', INK, SMALL, 'sans')

    x, y, w, h = F
    tool_box(F, 1, 'find_metric', '4 毫秒')
    rows = (('按名称、别名匹配', '门店营业额'), ('比较依赖表的版本', '没变，不用重新校验'), ('返回当前有效版本', 'v2'))
    text(x + 3.0, y + h - 3.0, '没有匹配时：返回“没有已验证的定义”，agent 自己探索', TINY, MUTED, width=w - 6.0)
    for k, (what, val) in enumerate(rows):
        yb = y + 16.8 + 6.8 * k
        s.circle(x + 4.4, yb - 1.4, .9, U)
        text(x + 7.4, yb, what, SMALL, INK)
        ex(s, x + 44.0, yb, val, width=w - 46.0, size=SMALL)

    x, y, w, h = R
    tool_box(R, 5, 'run_sql', '24 毫秒')
    checks = ('单条只读查询（SELECT）', '声明的 v2 存在、仍然有效', 'SQL 审查：不缺必需的过滤', '在快照上执行 SQL')
    for k, label in enumerate(checks):
        check(s, x + 3.0, y + 17.6 + 6.6 * k, label, size=SMALL, width=w - 6.0)
    s.line(x + 3.0, y + 42.4, x + w - 3.0, y + 42.4, '#E6E8EC', .3)
    text(x + 3.0, y + 47.6, '版本已失效、缺少过滤：拒绝执行，', SMALL, P.FAIL_TEXT, width=w - 6.0)
    text(x + 3.0, y + 52.4 - .4, '并把原因告诉 B', SMALL, P.FAIL_TEXT, width=w - 6.0)

    # What B reads -------------------------------------------------------------------------------------------
    x, y, w, h = D
    panel(s, D, U, WHITE, .55)
    step(s, x + 5.8, y + 6.4, 2, U, r=3.0)
    text(x + 11.2, baseline(y + 6.4, TITLE), 'B 拿到的定义', TITLE, INK, 'bold')
    pill(s, x + w - 3.0 - pill_width('v2', NOTE), y + 6.4, 'v2', P.MAINT, size=NOTE)
    text(x + 3.0, y + 17.6, '门店营业额', NOTE + 1, INK, 'bold')
    fields = (('口径', '净支付额之和，按销售日期归属期间', 'sans'), ('度量', '`sum(store_sales.ss_net_paid)`', 'sans'),
              ('粒度', '(日期键, 小票号, 商品键)', 'sans'), ('日期', '按日期键范围过滤（v2 的写法）', 'sans'))
    for k, (head, body, _) in enumerate(fields):
        yb = y + 24.4 + 5.6 * k
        text(x + 3.0, yb, head, SMALL, P.USE_TEXT, 'bold')
        text(x + 13.0, yb, body, SMALL if '`' not in body else TINY, INK, width=w - 15.0)
    text(x + 3.0, y + 48.8, '注意事项', SMALL, P.USE_TEXT, 'bold')
    for k, line in enumerate(('用净支付额 `ss_net_paid`，不含税', '约 1.03% 无日期的销售被排除', '前提：日期键按月连续，MAVRA 维护')):
        yb = y + 54.0 + 4.9 * k
        s.circle(x + 4.2, yb - 1.3, .7, MUTED)
        text(x + 6.4, yb, line, TINY, INK, width=w - 9.0)
    code_panel(s, (x + 3.0, y + 64.6, w - 6.0, 15.0), [
        'select sum(ss_net_paid) from store_sales',
        'where ss_sold_date_sk between',
        '  (select min(d_date_sk) …) and (…)',
    ], size=TINY - .5, pitch=4.1, first=4.6)
    text(x + 3.0, y + h - 3.0, 'B 看不到前提条件和校验结果（MAVRA 保管）', TINY, MUTED, width=w - 6.0)

    # The database ----------------------------------------------------------------------------------------------
    x, y, w, h = DB
    slab(s, DB)
    text(x + 3.6, baseline(y + h / 2, NOTE + 1), '数据库', NOTE + 1, INK, 'bold')
    for k, label in enumerate(('`store_sales`', '`date_dim`')):
        table_card(s, x + 22.0 + 32.0 * k, 30.0, y + 2.6, h - 5.2, label, size=TINY)

    # Arrows, numbered in reading order -------------------------------------------------------------------------
    def badge_on(x0, x1, yy, n):
        step(s, (x0 + x1) / 2, yy - 5.0, n, U, r=2.6)

    yy = B[1] + 19.0
    route([(B[0] + B[2], yy), (F[0], yy)], U, THIN, length=HEAD)
    route([(F[0] + F[2], yy), (D[0], yy)], U, THICK, length=HEAD)
    badge_on(F[0] + F[2], D[0], yy, 2)
    yy = R[1] + 12.0
    route([(SQL[0] + SQL[2], yy), (R[0], yy)], U, THIN, length=HEAD)
    badge_on(SQL[0] + SQL[2], R[0], yy, 4)
    yy = DB[1] + DB[3] / 2
    route([(R[0] + R[2], yy), (DB[0], yy)], U, THIN, length=HEAD)
    badge_on(R[0] + R[2], DB[0], yy, 6)
    yr = RES[1] + 13.0
    route([(R[0], yr), (RES[0] + RES[2], yr)], U, THICK, length=HEAD)
    badge_on(RES[0] + RES[2], R[0], yr, 7)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
