"""Deck figure 3 (learning and maintenance): one metric definition through its life.

Store revenue (门店营业额). Top row: the built-in agent (an LLM) answers a learning
question whose meaning is given (March, 13,570,368.70), the answer is verified,
and v1 is published after validation; appending new sales leaves every rule
true, so v1 stays and the other metrics reuse the results. Bottom row: a
restatement keeps the old rows as non-current (ss_is_current = 0) and breaks
"one row per sale"; v1 is retired; the repair tries filters on low-cardinality
columns, exactly one works, the regression test on the learning-time data gives
the same answer (on current data it would refuse the fix), and v2 is published.
The red box is the other outcome: after a duplicate load no filter works and the
definition stays retired. Values come from the end-to-end study (run r1 of
MAVRA; tasks M1-L1 and M1-P1). Drawn at slide size for the report deck, with
everyday terms rather than the paper's notation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import (DASH, HEAD, LEARN, NOTE, THIN, TITLE, USE, WAIT, legend_pill, llm_badge,  # noqa: E402
                   rows, stage)
from style import ACC, ACC_DK, AMBER, AMBER_PALE, FIELD, INK, MUTED, RED  # noqa: E402

NAME = 'lifecycle'
W, H = 300.0, 110.0

LABELS = {
    'zh': {
        'title': 'MAVRA 学习与维护', 'paths': ('学习', '维护'), 'otherwise': '另一种结果',
        'table': '`store_sales`',
        'learn': ('学习', '内置智能体（大模型）'),
        'l_rows': ('任务：3 月门店营业额（给定口径）', '`SUM(ss_net_paid) … d_moy = 3`',
                   '答案 1357.0 万，判定正确', '准入检查通过'),
        'pub1': ('发布 v1', '定义内容'),
        'p1_rows': ('度量：`SUM(ss_net_paid)`', '条件：粒度键唯一、', '日期键唯一、日期键完整性',
                    '证据：学习时的 SQL'),
        'benign': ('增量加载', '追加新销售记录（新小票号）'),
        'b_rows': ('重新验证：条件成立', '其他定义：复用验证结果', '仍为 v1'),
        'later': '后续更新',
        'breaking': ('数据更正', '旧行标记为非当前，插入当前行'),
        'k_rows': ('粒度键唯一：不成立', 'v1 失效', '不处理：1430.1 万（计入旧行）'),
        'search': ('修复搜索', '在低基数列上枚举等值谓词'),
        's_rows': ("`ss_is_current='1'`", "`ss_is_current='0'` 丢失键", '唯一可行'),
        'regress': ('回归测试', '按学习时刻重算 3 月'),
        'r_rows': ('学习时 SQL', '修复后', '一致：接受修复', '按当前数据比较会误拒'), 'value': '1357.0 万',
        'pub2': ('发布 v2', '同一定义的新修订'),
        'p2_rows': ('v2 = v1 + 谓词', "`ss_is_current='1'`", '声明 v1 的查询被拒绝', '等待中的请求获得 v2'),
        'nofix': ('无法修复', '例：批次重复加载'),
        'n_rows': ('粒度键唯一：不成立', '没有谓词能恢复唯一性', '失效，通知使用方', '等待重新学习'),
        'two': '无候选或多个候选', 'relearn': '重新学习',
    },
    'en': {
        'title': 'MAVRA learning and maintenance', 'paths': ('learning', 'maintenance'),
        'otherwise': 'other outcome', 'table': '`store_sales`',
        'learn': ('Learn', 'built-in agent (LLM)'),
        'l_rows': ('question: March store revenue', '`SUM(ss_net_paid) … d_moy = 3`',
                   'answer 13,570,368.70, verified', 'validated before publishing'),
        'pub1': ('Publish v1', 'the definition holds'),
        'p1_rows': ('`SUM(ss_net_paid)`', 'rules: one row per sale,', 'date key unique,',
                    'loss in bound; learning SQL'),
        'benign': ('New data', 'new sales appended'),
        'b_rows': ('rechecked: still holds', 'other metrics: reuse', 'stays v1'),
        'later': 'a later write',
        'breaking': ('Restatement', 'old rows kept as non-current'),
        'k_rows': ('one row per sale: fails', 'v1 retired', 'unfixed: old rows counted'),
        'search': ('Find a repair', 'try filters on few-value columns'),
        's_rows': ("`ss_is_current='1'`", "`ss_is_current='0'` loses sales", 'exactly one works'),
        'regress': ('Regression test', 'rerun March on learning-time data'),
        'r_rows': ('learning SQL', 'with the filter', 'same: fix accepted', 'current data would refuse it'),
        'value': '13,570,368.70',
        'pub2': ('Publish v2', 'new version, same metric'),
        'p2_rows': ('v2 = v1 + filter', "`ss_is_current='1'`", 'SQL naming v1: rejected',
                    'waiting requests get v2'),
        'nofix': ('No repair', 'e.g. a batch loaded twice'),
        'n_rows': ('one row per sale: fails', 'no filter restores it', 'retired; agents told',
                   'retired until relearned'),
        'two': 'none (or several) work', 'relearn': 'relearn',
    },
}

ROUTE_Y = 12.5                            # the relearn route runs above the top row
R1, R2, RH = 16.0, 68.0, 40.0             # tops of the two rows, their height
LEARN_B = (2.0, R1, 74.0, RH)
PUB1 = (82.0, R1, 70.0, RH)
BENIGN = (158.0, R1, 64.0, RH)
NOFIX = (228.0, R1, 70.0, RH)
BREAK = (2.0, R2, 70.0, RH)
SEARCH = (78.0, R2, 74.0, RH)
REGRESS = (158.0, R2, 66.0, RH)
PUB2 = (230.0, R2, 68.0, RH)
PITCH = 5.6


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def version(ex, ey, ew, old, new):
        rect(ex - 1.2, ey - 4.3, ew + 2.4, 5.8, AMBER_PALE, AMBER, .25, r=.8)
        text(ex, ey, L['table'], NOTE, INK)
        text(ex + ew, ey, f'{old} → {new}', NOTE, WAIT, align='right')

    rect(0, 0, W, H, FIELD, None, r=2.8)
    rect(3.0, 3.4, 1.1, 5.4, ACC)
    text(6.2, 8.2, L['title'], TITLE, ACC_DK, 'bold')
    x = 150.0
    for label, color, steps in zip(L['paths'], (LEARN, USE), ('1–2', '3–7')):
        x += legend_pill(s, x, 6.2, label, color, steps) + 6.0
    legend_pill(s, x, 6.2, L['otherwise'], RED, dashed=True)

    # 1 Learn ---------------------------------------------------------------------------
    ex, ey, ew = stage(s, LEARN_B, 1, LEARN, *L['learn'])
    llm_badge(s, LEARN_B[0] + LEARN_B[2] - 6.0, LEARN_B[1] + 5.8, 3.2)
    rows(s, ex, ey, ew, L['l_rows'], PITCH, marks={2: 'ok', 3: 'ok'})

    # 2 Publish v1 ----------------------------------------------------------------------
    ex, ey, ew = stage(s, PUB1, 2, LEARN, *L['pub1'])
    rows(s, ex, ey, ew, L['p1_rows'], PITCH)

    # 3 A normal write: the rules still hold ----------------------------------------------
    ex, ey, ew = stage(s, BENIGN, 3, USE, *L['benign'])
    version(ex, ey, ew, 12, 13)
    rows(s, ex, ey, ew, L['b_rows'], PITCH, first=1, colors={2: ACC_DK}, marks={0: 'ok', 1: 'ok'})

    # 4 A breaking write retires v1 ----------------------------------------------------------
    ex, ey, ew = stage(s, BREAK, 4, USE, *L['breaking'])
    version(ex, ey, ew, 13, 14)
    rows(s, ex, ey, ew, L['k_rows'], PITCH, first=1, colors={0: RED, 1: RED, 2: MUTED},
         marks={0: 'fail'})

    # 5 Find a repair ----------------------------------------------------------------------
    ex, ey, ew = stage(s, SEARCH, 5, USE, *L['search'])
    rows(s, ex, ey, ew, L['s_rows'], PITCH, colors={2: ACC_DK}, marks={0: 'ok', 1: 'fail', 2: 'ok'})

    # 6 Regression test on the learning-time data ---------------------------------------------
    ex, ey, ew = stage(s, REGRESS, 6, USE, *L['regress'])
    for k, label in enumerate(L['r_rows'][:2]):
        yy = ey + PITCH * k
        text(ex, yy, label, NOTE, INK)
        text(ex + ew - 4.6, yy, L['value'], NOTE, INK, align='right')
    rows(s, ex, ey, ew, L['r_rows'][2:], PITCH, first=2, colors={0: ACC_DK, 1: MUTED}, marks={0: 'ok'})

    # 7 Publish v2 ---------------------------------------------------------------------------
    ex, ey, ew = stage(s, PUB2, 7, USE, *L['pub2'])
    rows(s, ex, ey, ew, L['p2_rows'], PITCH, colors={0: ACC_DK, 1: ACC_DK})

    # The other outcome: no unique repair ---------------------------------------------------
    ex, ey, ew = stage(s, NOFIX, None, RED, *L['nofix'], edge=RED, dash=(1.6, 1.0))
    rows(s, ex, ey, ew, L['n_rows'], PITCH, colors={0: RED, 1: RED, 3: LEARN}, marks={0: 'fail'})

    # Arrows ---------------------------------------------------------------------------------
    for (l, r), color in (((LEARN_B, PUB1), LEARN), ((PUB1, BENIGN), USE), ((BREAK, SEARCH), USE),
                          ((SEARCH, REGRESS), USE), ((REGRESS, PUB2), USE)):
        yy = l[1] + 5.6
        route([(l[0] + l[2], yy), (r[0], yy)], color, THIN, length=HEAD)
    # From the normal write to the breaking one: a later write.
    xb, yc = BENIGN[0] + BENIGN[2] / 2, R1 + RH + 5.0
    xk = BREAK[0] + BREAK[2] / 2
    route([(xb, R1 + RH), (xb, yc), (xk, yc), (xk, R2)], USE, THIN, radius=1.8, length=HEAD)
    text(xk + 2.8, R2 - 1.8, L['later'], NOTE, USE)
    # From the repair search to the other outcome when no unique filter exists.
    xs, yn, xn = SEARCH[0] + SEARCH[2] - 12.0, R2 - 4.5, NOFIX[0] + NOFIX[2] / 2
    route([(xs, R2), (xs, yn), (xn, yn), (xn, R1 + RH)], RED, THIN, radius=1.8, length=HEAD)
    text(xb + 3.0, yn - 2.0, L['two'], NOTE, RED, width=xn - xb - 5.0)
    # From the other outcome back to learning.
    xl = LEARN_B[0] + LEARN_B[2] / 2
    route([(xn, R1), (xn, ROUTE_Y), (xl, ROUTE_Y), (xl, R1)], LEARN, THIN, radius=1.8, dash=DASH,
          length=HEAD)
    text(100.0, ROUTE_Y - 1.6, L['relearn'], NOTE, LEARN)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
