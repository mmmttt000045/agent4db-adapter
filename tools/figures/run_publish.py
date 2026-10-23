"""Deck run figure 1 (publish): how one learning task became a shared definition, on the recorded run.

Left: the built-in agent A answers a learning question that states the business
meaning (3 月门店营业额, net paid), with the tool calls the middleware recorded
(list_tables, find_metric finds nothing, describe_table x2, join_path, run_sql,
final_answer; judged correct). Middle: the extractor turns A's SQL into
structured fields (the period becomes a parameter; the grain comes from the table
comment), then seven admission checks run. Right: what is published, v1 with its
canonical SQL, three preconditions and the evidence MAVRA keeps.
Values from the trace run (noctis results/scen-20261008-trace/metric-1791449167012862,
copy in exp/2026-10-08-optimize/trace): M1-L1 5 turns / 7 tool calls, answer
13,570,368.70, join 989,695 of 1,000,000 rows (1.03% unmatched), extraction 12.7 s,
gates G1-G7 passed with 5 queries in 5.6 s. Steps 1-9 give the reading order.
Colours from deckpal.py; drawn at slide size (300 mm, 10-15 pt), Chinese only, no years.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import HEAD, NOTE, THICK, THIN, TITLE, baseline, llm_badge, step  # noqa: E402
from style import INK, MUTED, WHITE  # noqa: E402
from deckparts import (SMALL, TINY, check, code_panel, ex, headed, panel, pill, pill_width, section,  # noqa: E402
                       window)
import deckpal as P  # noqa: E402

NAME = 'run-publish'
LANGS = ('zh',)
W, H = 300.0, 134.0
G = P.PUBLISH

Q = (4.0, 12.0, 94.0, 38.0)                       # the learning question
T = (4.0, 56.0, 94.0, 74.0)                       # A's tool calls
E = (110.0, 12.0, 94.0, 62.0)                     # extraction
A = (110.0, 80.0, 94.0, 50.0)                     # admission checks
M = (216.0, 12.0, 80.0, 118.0)                    # the published definition


def draw(s, lang):
    text, route = s.text, s.route
    section(s, 4.0, 6.4, '发布：一道学习题，变成一条共享的指标定义', '真实运行记录 · 门店营业额',
            color=G, text_color=P.PUBLISH_TEXT)

    # The learning question ----------------------------------------------------------------------
    x, y, w, h = Q
    panel(s, Q, G, '#F6FBFA')
    llm_badge(s, x + 7.0, y + 7.0, 3.6, color=G)
    text(x + 13.4, baseline(y + 7.0, TITLE), '内置 agent A', TITLE, INK, 'bold')
    pill(s, x + w - 3.0 - pill_width('学习题'), y + 7.0, '学习题', G)
    s.rect(x + 3.0, y + 13.6, w - 6.0, 21.4, WHITE, P.PANEL, .35, r=1.2)
    text(x + 5.6, y + 20.0, '3 月的门店营业额是多少？', NOTE + 1, INK, 'bold')
    text(x + 5.6, y + 26.0, '口径：门店销售行的净支付额', NOTE, INK, width=w - 11.0)
    text(x + 5.6, y + 31.6, '（`ss_net_paid`）之和，按销售日期归属期间', NOTE, INK, width=w - 11.0)
    route([(x + w / 2, y + h), (x + w / 2, T[1])], G, THIN, length=HEAD)

    # A's tool calls, as MAVRA recorded them --------------------------------------------------------
    x, y, w, h = T
    window(s, T, 'A 的工具调用', 'MAVRA 逐次记录 · 5 轮 7 次')
    calls = (
        ('list_tables()', ('5 张表及注释', MUTED)),
        ('find_metric("门店营业额")', ('还没有已验证的定义，需要自己学', MUTED)),
        ('describe_table ×2', ('store_sales 一行 = 小票中的一种商品', MUTED)),
        ('join_path', ('98.97% 的销售能关联到 date_dim', MUTED)),
        ('run_sql', ('ex', '13,570,368.70（编号 r1）')),
        ('final_answer', ('ok', '判题：正确')),
    )
    for k, (call, (res, kind)) in enumerate(calls):
        y0 = y + 13.6 + 10.2 * k
        step(s, x + 5.6, y0 - 1.4, k + 1, G, r=2.6)
        text(x + 10.6, y0, call, NOTE, INK, 'code', width=w - 13.0)
        if res == 'ex':
            ex(s, x + 10.6, y0 + 5.0, kind, width=w - 13.0, size=SMALL)
        elif res == 'ok':
            check(s, x + 10.6, y0 + 5.0, kind, size=SMALL, color=P.PUBLISH_TEXT, style='bold')
        else:
            text(x + 10.6, y0 + 5.0, res, SMALL, kind, width=w - 13.0)
        if k < len(calls) - 1:
            s.line(x + 3.0, y0 + 7.4, x + w - 3.0, y0 + 7.4, '#ECEEF2', .25)

    # Extraction: SQL to fields ------------------------------------------------------------------------
    x, y, w, h = E
    headed(s, E, '提取定义', n=7, color=G)
    pw = pill_width('大模型 · 12.7 秒', SMALL, 'sans')
    pill(s, x + w - 3.0 - pw, y + 6.4, '大模型 · 12.7 秒', '#EEF0F4', INK, SMALL, 'sans')
    text(x + 3.0, y + 15.4, 'A 的 SQL 拆成结构化字段，提取器看不到数据行', SMALL, MUTED, width=w - 6.0)
    rows = (('`SUM(ss.ss_net_paid)`', '度量'), ('`FROM store_sales`', '事实表'),
            ('`JOIN date_dim ON …`', '销售日期'), ('`d_year = … AND d_moy = 3`', '期间参数'),
            ('表注释：一行 = 一种商品', '粒度'))
    for k, (src, field) in enumerate(rows):
        yb = y + 23.2 + 7.0 * k
        ex(s, x + 3.0, yb, src, width=57.0, size=SMALL)
        route([(x + 60.0, yb - 1.5), (x + 65.0, yb - 1.5)], G, THIN, length=HEAD)
        param = field == '期间参数'
        text(x + 67.0, yb, field, NOTE, P.PENDING_TEXT if param else P.USE_TEXT, 'bold', width=w - 69.0)
    text(x + 3.0, y + h - 3.0, '期间不进定义；粒度 = (日期键, 小票号, 商品键)', TINY + .5, MUTED, width=w - 6.0)
    route([(x + w / 2, y + h), (x + w / 2, A[1])], G, THICK, length=HEAD)

    # Admission checks ----------------------------------------------------------------------------------
    x, y, w, h = A
    headed(s, A, '发布前校验', n=8, color=G)
    pw = pill_width('7 项', SMALL)
    pill(s, x + w - 3.0 - pw, y + 6.4, '7 项', G)
    left = ('业务依据', '答案正确、可复现', '静态检查', '当前数据主键唯一')
    right = ('SQL 审查', '示例 SQL 重放', '规范 SQL 重放')
    for k, label in enumerate(left):
        check(s, x + 3.0, y + 16.4 + 6.0 * k, label, size=SMALL, width=46.0)
    for k, label in enumerate(right):
        check(s, x + 50.0, y + 16.4 + 6.0 * k, label, size=SMALL, width=w - 52.0)
    ex(s, x + 50.0, y + 16.4 + 6.0 * 3, '5 条查询，5.6 秒', width=w - 52.0, size=SMALL)
    text(x + 3.0, y + h - 9.0, '每一项都是 MAVRA 执行的查询或规则，不靠大模型判断', TINY, MUTED, width=w - 6.0)
    text(x + 3.0, y + h - 3.2, '任一项不通过：拒绝，不进共享记忆', SMALL, P.FAIL_TEXT, width=w - 6.0)
    route([(T[0] + T[2], T[1] + 13.6 + 10.2 * 5 - 1.4), (104.0, T[1] + 13.6 + 10.2 * 5 - 1.4), (104.0, E[1] + 30.0),
           (E[0], E[1] + 30.0)], G, THIN, length=HEAD, radius=1.6)
    route([(x + w, y + 25.0), (M[0], y + 25.0)], G, THICK, length=HEAD)

    # The published definition ------------------------------------------------------------------------
    x, y, w, h = M
    panel(s, M, P.USE, '#FBFCFE', .55)
    step(s, x + 5.8, y + 6.4, 9, G, r=3.0)
    text(x + 11.2, baseline(y + 6.4, TITLE), '写入共享记忆', TITLE, INK, 'bold')
    c = (x + 3.0, y + 12.4, w - 6.0, 13.0)
    s.rect(*c, P.PUBLISH_PALE, None, r=1.2)
    text(c[0] + 2.6, c[1] + 5.8, '门店营业额', NOTE + 1, INK, 'bold')
    pill(s, c[0] + c[2] - 2.4 - pill_width('v1', NOTE), c[1] + 4.6, 'v1', G, size=NOTE)
    text(c[0] + 2.6, c[1] + 10.8, '已发布的版本不再原地修改', TINY, MUTED)

    def label(yb, t):
        text(x + 3.0, yb, t, SMALL, P.USE_TEXT, 'bold')

    label(y + 32.0, '口径')
    text(x + 3.0, y + 37.4, '门店销售行的净支付额之和，', SMALL, INK, width=w - 6.0)
    text(x + 3.0, y + 42.4, '按销售日期归属期间', SMALL, INK)
    label(y + 50.2, '规范 SQL（由字段编译）')
    code_panel(s, (x + 3.0, y + 52.4, w - 6.0, 16.6), [
        'select sum(ss_net_paid)',
        'from store_sales join date_dim …',
        [('where ', INK), ('d_year = :年 and d_moy = :月', P.PENDING_TEXT)],
    ], size=TINY, pitch=4.5, first=5.0)
    label(y + 76.4, '前提条件')
    conds = (('主键唯一', '行数 = 不同键数'), ('维表主键唯一', '`d_date_sk` 不重复'), ('参照完整性', '关联不上 ≤ 1.13%'))
    for k, (name, gloss) in enumerate(conds):
        yc = y + 81.6 + 6.6 * k
        pw = pill(s, x + 3.0, yc, name, P.USE_PALE, P.USE_TEXT, SMALL)
        text(x + 3.0 + 31.0, baseline(yc, TINY), gloss, TINY, MUTED, width=w - 36.0)
    label(y + 106.6, '证据（MAVRA 保管）')
    text(x + 3.0, y + 111.8, '学习题、A 的 SQL 与答案、', TINY + .5, MUTED, width=w - 6.0)
    text(x + 3.0, y + 116.2, '学习时的表版本', TINY + .5, MUTED, width=w - 6.0)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
