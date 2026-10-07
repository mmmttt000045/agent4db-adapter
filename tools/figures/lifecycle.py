"""Deck figure 3 (learning and maintenance): one metric definition through its life.

Top row: the built-in agent (an LLM) answers a learning question whose meaning
is given, the answer is verified, and v1 is published after validation; a normal
write (late returns) leaves every rule true, so v1 stays. Bottom row: a breaking
write (an application-state row per return) breaks "one row per return" and v1
is retired; the repair tries filters on low-cardinality columns, exactly one
works, the regression test on the data as of learning gives the same answer,
and v2 is published. The red box is the other outcome: when two filters work
(a full backup copy), the definition stays retired until it is relearned.
Values come from the end-to-end study (tasks M2-L1, M2-P1). Drawn at slide size
for the report deck, with everyday terms rather than the paper's notation.
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
        'learn': ('学习', '内置智能体（大模型）'),
        'l_rows': ('题目：4 月门店退货金额', '`SUM(sr_return_amt) … d_moy = 4`',
                   '答案 313.3 万，核验正确', '发布前校验通过'),
        'pub1': ('发布 v1', '指标定义包含'),
        'p1_rows': ('计算：`SUM(sr_return_amt)`', '规则：每笔退货一行、', '日期键唯一、退货都有日期',
                    '保存：学习时的 SQL'),
        'benign': ('普通写入', '追加迟到的退货'),
        'b_rows': ('重新校验：仍成立', '`date_dim` 未变：复用缓存', '仍为 v1'),
        'later': '之后的一次写入',
        'breaking': ('破坏性写入', '每笔退货追加一行“申请”状态'),
        'k_rows': ('每笔退货一行：不成立', 'v1 停用', '不处理：658.9 万（翻倍）'),
        'search': ('寻找修复', '在取值少的列上逐个试过滤'),
        's_rows': ("`sr_status='完成'`", "`sr_status='申请'` 丢退货", '只有一个可行'),
        'regress': ('回归测试', '用学习时的数据重算'),
        'r_rows': ('原 SQL', '加过滤后', '一致：接受修复'), 'value': '313.3 万',
        'pub2': ('发布 v2', '同一指标的新版本'),
        'p2_rows': ('v2 = v1 + 过滤', "`sr_status='完成'`", '注明 v1 的 SQL 被拒绝', '等待中的请求拿到 v2'),
        'nofix': ('无法唯一修复', '例：追加了一整份备份数据'),
        'n_rows': ("`sr_source='primary'`", "`sr_source='backup'`", '两个都可行：无法判断',
                   '停用，等待重新学习'),
        'two': '两个可行，或一个也没有', 'relearn': '重新学习',
    },
    'en': {
        'title': 'MAVRA learning and maintenance', 'paths': ('learning', 'maintenance'),
        'otherwise': 'other outcome',
        'learn': ('Learn', 'built-in agent (LLM)'),
        'l_rows': ('question: April return amount', '`SUM(sr_return_amt) … d_moy = 4`',
                   'answer 3,133,115.63, verified', 'validated before publishing'),
        'pub1': ('Publish v1', 'the definition holds'),
        'p1_rows': ('`SUM(sr_return_amt)`', 'rules: one row per return,', 'date key unique,',
                    'dates complete; learning SQL'),
        'benign': ('Normal write', 'late returns appended'),
        'b_rows': ('rechecked: still holds', '`date_dim` same: cached', 'stays v1'),
        'later': 'a later write',
        'breaking': ('Breaking write', 'a status row per return'),
        'k_rows': ('one row per return: fails', 'v1 retired', 'unfixed: answer doubles'),
        'search': ('Find a repair', 'try filters on few-value columns'),
        's_rows': ("`sr_status='done'`", "`sr_status='applied'` loses rows", 'exactly one works'),
        'regress': ('Regression test', 'rerun on the learning-time data'),
        'r_rows': ('learning SQL', 'with the filter', 'same: fix accepted'), 'value': '3,133,115.63',
        'pub2': ('Publish v2', 'new version, same metric'),
        'p2_rows': ('v2 = v1 + filter', "`sr_status='done'`", 'SQL naming v1: rejected',
                    'waiting requests get v2'),
        'nofix': ('No unique repair', 'e.g. a full backup copy'),
        'n_rows': ("`sr_source='primary'`", "`sr_source='backup'`", 'both work: cannot tell',
                   'retired until relearned'),
        'two': 'two work, or none', 'relearn': 'relearn',
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
        text(ex, ey, '`store_returns`', NOTE, INK)
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
    rows(s, ex, ey, ew, L['r_rows'][2:], PITCH, first=2, colors={0: ACC_DK}, marks={0: 'ok'})

    # 7 Publish v2 ---------------------------------------------------------------------------
    ex, ey, ew = stage(s, PUB2, 7, USE, *L['pub2'])
    rows(s, ex, ey, ew, L['p2_rows'], PITCH, colors={0: ACC_DK, 1: ACC_DK})

    # The other outcome: no unique repair ---------------------------------------------------
    ex, ey, ew = stage(s, NOFIX, None, RED, *L['nofix'], edge=RED, dash=(1.6, 1.0))
    rows(s, ex, ey, ew, L['n_rows'], PITCH, colors={2: RED, 3: LEARN}, marks={0: 'ok', 1: 'ok'})

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
