"""Deck figure 3 (publish, maintain and improve): one definition, store revenue, through its life.

Top row: the built-in agent (an LLM) answers a learning question whose meaning
is given (March, 13,570,368.70, judged correct, 5 turns and 7 tool calls); the
admission checks pass and v1 is published with its three conditions; an
improvement rewrites the period predicate as a date-key range (equal on 14
periods, 29.1 -> 23.3 ms, -19.8%) and publishes v2 with "date keys contiguous
by month" as a new condition. Bottom: a write to store_sales (table version
v14 -> v15, illustrative); the next use validates v2's conditions, and the three
everyday writes of deck slide 3 end three ways. Incremental load (+27,095 rows,
new tickets): every condition holds, v2 stays valid and September is
26,139,303.60. Correction keeping the old rows as non-current (+65,915 rows):
grain-key uniqueness fails (1,065,915 rows, 1,000,000 keys), v2 is invalidated,
the repair search finds exactly one filter, ss_is_current = '1', the regression
test on the learning-time data gives the March answer again, and v3 serves
September as 12,932,888.04 (v2 left in use: 14,300,525.64). Duplicate load
(+110,165 rows): uniqueness fails (1,110,165 rows, 1,000,000 keys), no filter
restores it, and the definition is invalidated.
Values: learning, admission and optimization from the trace run
(exp/2026-10-08-optimize/trace, README there) and the optimization run
(results/scen-20261008-opt on noctis: the timing, and the three writes'
maintenance events and M1-P1 answers); the unmaintained answer from
results/scen-20261002 (dsv41flash-r1-g3fix--schema). Drawn at slide size
(300 mm, 12-15 pt), Chinese only, with standard database terms rather than the
paper's notation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import (EXEC, HEAD, LEARN, NOTE, PANEL_EDGE, THIN, TITLE, USE, WAIT, legend_pill,  # noqa: E402
                   llm_badge, mark, rows, stage)
from style import ACC, ACC_DK, AMBER, FIELD, INK, MUTED, RED, WHITE  # noqa: E402

NAME = 'lifecycle'
LANGS = ('zh',)                                  # the report deck is Chinese
W, H = 300.0, 134.0

LABELS = {
    'zh': {
        'title': '门店营业额的一生：发布、改进与维护',
        'paths': ('发布', '维护与改进'), 'fails': '失效',
        'learn': ('学习', '内置 agent（大模型），5 轮、7 次工具调用'),
        'l_rows': ('任务：3 月门店营业额（给定口径）', '答案 1357.0 万，判定正确',
                   'SQL：`SUM(ss_net_paid) … d_moy = 3`'),
        'pub1': ('准入检查，发布 v1', '7 项检查通过后写入共享记忆'),
        'p1_rows': ('条件：粒度键唯一、日期键唯一、', '日期键完整性', '证据：学习时的 SQL、答案、表版本'),
        'opt': ('改进：发布 v2', '期间改为日期键范围，不连接 `date_dim`'),
        'o_rows': ('14 个期间结果一致', '29.1 → 23.3 ms，快 19.8%', '新条件：日期键按月连续'),
        'then': '之后 `store_sales` 有一次写入（v14 → v15），下次使用 v2 前先验证它的条件。三种写入，三种结果：',
        'append': ('增量加载', '+27,095 行，新小票号'), 'a_rows': (('4 个条件都成立', 'ok', ACC_DK), ('多出的行都是新键，不是重复', None, MUTED)),
        'keep': ('v2 继续有效', '所有 agent 照常使用（第 7 页）'),
        'k_rows': (('9 月门店营业额 2613.9 万，与参考答案一致', 'ok', INK),
                   ('只重验读 `store_sales` 的两项条件，结果所有定义共享', None, MUTED)),
        'correct': ('数据更正', '+65,915 行，旧行保留'),
        'c_rows': (('粒度键唯一：不成立', 'fail', RED), ('1,065,915 行，1,000,000 个键', None, MUTED),
                   ('v2 失效', None, RED)),
        'search': '修复搜索',
        's_rows': (("`ss_is_current='1'`", 'ok', INK), ("`ss_is_current='0'`：丢键", 'fail', INK),
                   ('只有一个过滤可行', None, ACC_DK)),
        'regress': '回归测试',
        'r_rows': ('按学习时的数据重算 3 月', '学习时的 SQL', '修复后的 v3'), 'value': '1357.0 万',
        'pub3': '发布 v3',
        'v_rows': (("v3 = v2 + `ss_is_current='1'`", None, ACC_DK), ('9 月 1293.3 万', 'ok', INK),
                   ('沿用 v2 会得 1430.1 万', 'fail', MUTED)),
        'dup': ('重复加载', '+110,165 行'),
        'd_rows': (('粒度键唯一：不成立', 'fail', RED), ('1,110,165 行，1,000,000 个键', None, MUTED)),
        'nofix': ('修复搜索', ''), 'n_rows': (('没有过滤能恢复唯一性', 'fail', RED),),
        'retire': ('失效，通知使用方', ''),
        'x_rows': (('声明 v2 的查询被拒绝，等待重新学习', None, INK), ('使用方自己从头探索作答', None, MUTED)),
    },
}

TOP, TH = 12.0, 34.0                      # top row: learn, publish, improve
T1 = (2.0, TOP, 96.0, TH)
T2 = (104.0, TOP, 94.0, TH)
T3 = (204.0, TOP, 94.0, TH)
BUS_Y, BUS_X = 52.5, 5.0                  # the write, and the line down to the three outcomes
LA, LB, LC = (56.0, 20.0), (79.0, 30.0), (112.0, 20.0)   # (top, height) of the three lanes
C1, C2, C3, C4 = (10.0, 70.0), (86.0, 68.0), (158.0, 68.0), (230.0, 68.0)   # (left, width) of the columns
PITCH = 5.2


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def event(b, title, note, lines, edge, color=INK, dash=None):
        """A compact box: bold title and a note on one line, then rows with result marks."""
        x, y, w, h = b
        rect(*b, WHITE, edge, .4, r=1.6, dash=dash)
        tw = text(x + 3.0, y + 6.2, title, NOTE + 1, color, 'bold', width=w - 6.0)
        if note:
            text(x + 5.5 + tw, y + 6.2, note, NOTE, WAIT if edge == AMBER else MUTED, width=w - 8.5 - tw)
        for k, (line, kind, ink) in enumerate(lines):
            yy = y + 12.0 + PITCH * k
            text(x + 3.0, yy, line, NOTE, ink, width=w - 6.0 - (4.6 if kind else 0))
            if kind:
                mark(s, x + w - 4.6, yy - 1.5, kind)

    def marked(ex, ey, ew, lines):
        for k, (line, kind, ink) in enumerate(lines):
            yy = ey + PITCH * k
            text(ex, yy, line, NOTE, ink, width=ew - (4.6 if kind else 0))
            if kind:
                mark(s, ex + ew - 1.6, yy - 1.5, kind)

    # Header ----------------------------------------------------------------------------
    rect(0, 0, W, H, FIELD, None, r=2.8)
    rect(3.0, 3.0, 1.1, 5.4, ACC)
    text(6.2, 7.8, L['title'], TITLE, ACC_DK, 'bold')
    x = 196.0
    for label, color, steps in zip(L['paths'], (LEARN, USE), ('1–2', '3–6')):
        x += legend_pill(s, x, 5.8, label, color, steps) + 6.0
    legend_pill(s, x, 5.8, L['fails'], RED, dashed=True)

    # 1 Learn, 2 publish v1, 3 improve to v2 ------------------------------------------------
    ex, ey, ew = stage(s, T1, 1, LEARN, *L['learn'])
    llm_badge(s, T1[0] + T1[2] - 6.0, T1[1] + 5.8, 3.2)
    rows(s, ex, ey, ew, L['l_rows'], PITCH, marks={1: 'ok'})
    ex, ey, ew = stage(s, T2, 2, LEARN, *L['pub1'])
    rows(s, ex, ey, ew, L['p1_rows'], PITCH)
    ex, ey, ew = stage(s, T3, 3, USE, *L['opt'])
    rows(s, ex, ey, ew, L['o_rows'], PITCH, colors={2: ACC_DK}, marks={0: 'ok', 1: 'ok'})
    for (l, r), color in (((T1, T2), LEARN), ((T2, T3), USE)):
        route([(l[0] + l[2], TOP + 5.6), (r[0], TOP + 5.6)], color, THIN, length=HEAD)

    # The write, then a line down to the three outcomes ---------------------------------------
    xs = T3[0] + T3[2] / 2
    route([(xs, TOP + TH), (xs, BUS_Y), (BUS_X, BUS_Y), (BUS_X, LC[0] + 6.2)], INK, THIN, heads=None,
          radius=1.8)
    text(C1[0], BUS_Y - 1.8, L['then'], NOTE, INK, width=xs - C1[0] - 3.0)
    for top, _ in (LA, LB, LC):
        route([(BUS_X, top + 6.2), (C1[0], top + 6.2)], INK, THIN, length=HEAD)

    def lane_arrow(top, x0, x1, color):
        route([(x0, top + 6.2), (x1, top + 6.2)], color, THIN, length=HEAD)

    # Incremental load: the conditions hold, v2 stays ----------------------------------------
    top, h = LA
    event((C1[0], top, C1[1], h), *L['append'], L['a_rows'], AMBER)
    event((C2[0], top, C4[0] + C4[1] - C2[0], h), *L['keep'], L['k_rows'], EXEC, EXEC)
    lane_arrow(top, C1[0] + C1[1], C2[0], EXEC)

    # Correction: invalidated, repaired, regression-tested, v3 -------------------------------
    top, h = LB
    event((C1[0], top, C1[1], h), *L['correct'], L['c_rows'], AMBER)
    ex, ey, ew = stage(s, (C2[0], top, C2[1], h), 4, USE, L['search'], None)
    marked(ex, ey, ew, L['s_rows'])
    ex, ey, ew = stage(s, (C3[0], top, C3[1], h), 5, USE, L['regress'], None)
    text(ex, ey, L['r_rows'][0], NOTE, INK, width=ew)
    for k, label in enumerate(L['r_rows'][1:]):
        yy = ey + PITCH * (k + 1)
        text(ex, yy, label, NOTE, INK)
        text(ex + ew - 4.6, yy, L['value'], NOTE, INK, align='right')
    mark(s, ex + ew - 1.6, ey + PITCH * 2 - 1.5, 'ok')
    ex, ey, ew = stage(s, (C4[0], top, C4[1], h), 6, USE, L['pub3'], None)
    marked(ex, ey, ew, L['v_rows'])
    for x0, x1 in ((C1[0] + C1[1], C2[0]), (C2[0] + C2[1], C3[0]), (C3[0] + C3[1], C4[0])):
        lane_arrow(top, x0, x1, USE)

    # Duplicate load: no filter restores the grain, the definition is invalidated -------------
    top, h = LC
    event((C1[0], top, C1[1], h), *L['dup'], L['d_rows'], AMBER)
    event((C2[0], top, C2[1], h), *L['nofix'], L['n_rows'], PANEL_EDGE)
    event((C3[0], top, C4[0] + C4[1] - C3[0], h), *L['retire'], L['x_rows'], RED, RED, dash=(1.6, 1.0))
    lane_arrow(top, C1[0] + C1[1], C2[0], USE)
    lane_arrow(top, C2[0] + C2[1], C3[0], RED)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
