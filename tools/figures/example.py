"""Paper figure 1 (running example): one shared definition through its lifecycle.

Store revenue on the synthetic retail data (one million sales rows). Top row:
the analysis optimizer, an LLM agent, answers a learning question whose
meaning is given (March, 13,570,368.70) and admission publishes revision 0
with the conditions derived from its structure; an optimization rewrites the
period predicate as a date-key range, equal on 14 periods and 19.8% faster
(29.1 -> 23.3 ms), published as revision 1 with date-key contiguity as a new
condition; user agents that know only the metric name rely on revision 1.
Bottom row: a restatement keeps old sales as non-current rows, key uniqueness
fails and revision 1 is invalid (run unmaintained it returns 14,300,525.64
for September); bounded repair finds exactly one filter, ss_is_current = '1', the
regression test as of learning time reproduces the March answer, and revision
2 serves the correct September value, 12,932,888.04. The dashed box is the
other outcome (duplicate load: no filter restores the grain, the definition is
invalidated). Values: learning, held-out and restatement answers from the
trace run exp/2026-10-08-optimize/trace (revisions 0, 1, 2 of
metric:门店营业额), the optimization timing from the one-million-row
optimization run (exp/2026-10-08-optimize/README.md), the unmaintained answer
from the end-to-end runs of invalidation on schema change
(results/scen-20261002 on noctis). Drawn with the deck kit at 300 mm and
scaled to the text width by LaTeX (12 pt notes print at 7.1 pt).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import (EXEC, HEAD, LEARN, NOTE, THIN, USE, WAIT, legend_pill, llm_badge,  # noqa: E402
                   rows, stage)
from style import ACC_DK, AMBER, AMBER_PALE, INK, MUTED, RED  # noqa: E402

NAME = 'running-example'
W, H = 300.0, 112.0

LABELS = {
    'en': {
        'legend': (('1–2', 'publish', LEARN), ('4', 'rely', EXEC), ('3, 5–7', 'maintain and improve', USE)),
        'other': 'no unique repair', 'table': '`store_sales`', 'write': 'a later write',
        'learn': ('Learn', 'analysis optimizer, an LLM agent'),
        'l_rows': ('question: March store revenue', '`SUM(ss_net_paid) … d_moy = 3`',
                   '13,570,368.70, judged correct', 'answer provenance extracted'),
        'pub': ('Publish revision 0', 'after the admission checks'),
        'p_rows': ('key uniqueness: one row per sale', 'date role: `d_date_sk` unique',
                   'join completeness: loss ≤ 1.0%', 'evidence: learning SQL, snapshot'),
        'opt': ('Optimize: revision 1', 'period as a date-key range'),
        'o_rows': ('equal on 14 periods', '29.1 → 23.3 ms, −19.8%', 'adds date-key contiguity',
                   'revision 0 stays usable'),
        'use': ('User agents rely on it', 'given only the metric name'),
        'u_rows': ('September store revenue?', 'lookup: revision 1, valid', 'declared, run on one snapshot',
                   '13,069,651.80, correct'),
        'break': ('Restatement', 'old sales kept as non-current rows'),
        'k_rows': ('key uniqueness fails', 'revision 1 invalid', 'September: 14,300,525.64'),
        'repair': ('Bounded repair', 'filters on low-cardinality columns'),
        'r_rows': ("`ss_is_current='1'`", "`ss_is_current='0'`", 'exactly one restores the grain'),
        'regress': ('Publish revision 2', 'regression test as of learning time'),
        'g_rows': ('March, learning SQL', 'March, repaired SQL', 'equal: repair accepted',
                   'September: 12,932,888.04'),
        'value': '13,570,368.70',
        'nofix': ('No unique repair', 'e.g., a duplicate load'),
        'n_rows': ('no filter restores the grain', 'or several filters disagree', 'definition invalidated',
                   'relearned from new tasks'),
        'several': 'none or several',
    },
    'zh': {
        'legend': (('1–2', '发布', LEARN), ('4', '依赖', EXEC), ('3, 5–7', '维护与改进', USE)),
        'other': '无唯一修复', 'table': '`store_sales`', 'write': '之后的一次写入',
        'learn': ('学习', '内置分析优化器（大模型）'),
        'l_rows': ('3 月门店营业额（给定口径）', '`SUM(ss_net_paid) … d_moy = 3`',
                   '13,570,368.70，判定正确', '提取答案来源'),
        'pub': ('发布修订 0', '通过准入检查之后'),
        'p_rows': ('键唯一：每笔销售一行', '日期角色：`d_date_sk` 唯一', '连接完整性：损失 ≤ 1.0%',
                   '证据：学习时的 SQL 与快照'),
        'opt': ('优化：修订 1', '期间谓词改为日期键范围'),
        'o_rows': ('14 个期间结果相等', '29.1 → 23.3 ms，−19.8%', '新条件：日期键连续', '修订 0 仍可使用'),
        'use': ('用户端智能体依赖它', '只给出指标名'),
        'u_rows': ('9 月门店营业额？', '查找：修订 1，有效', '声明后在同一快照上执行', '13,069,651.80，正确'),
        'break': ('多版本更正', '旧销售保留为非当前行'),
        'k_rows': ('键唯一：不成立', '修订 1 失效', '9 月：14,300,525.64'),
        'repair': ('有界修复', '在低基数列上枚举过滤'),
        'r_rows': ("`ss_is_current='1'`", "`ss_is_current='0'`", '恰好一个过滤能恢复粒度'),
        'regress': ('发布修订 2', '按学习时刻做回归测试'),
        'g_rows': ('3 月，学习时 SQL', '3 月，修复后 SQL', '相等：接受修复', '9 月：12,932,888.04'),
        'value': '13,570,368.70',
        'nofix': ('无唯一修复', '例：重复加载'),
        'n_rows': ('没有过滤能恢复粒度', '或多个过滤结果不一', '定义失效', '由新任务重新学习'),
        'several': '无或多个',
    },
}

R1, R2, RH = 11.0, 62.0, 40.0             # tops of the two rows, their height
LEARN_B = (2.0, R1, 70.0, RH)
PUB = (78.0, R1, 72.0, RH)
OPT = (156.0, R1, 68.0, RH)
USE_B = (230.0, R1, 68.0, RH)
BREAK = (2.0, R2, 70.0, RH)
REPAIR = (78.0, R2, 72.0, RH)
REGRESS = (156.0, R2, 68.0, RH)
NOFIX = (230.0, R2, 68.0, RH)
PITCH = 5.6


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    x = 2.0
    for steps, label, color in L['legend']:
        x += legend_pill(s, x, 4.6, label, color, steps) + 7.0
    legend_pill(s, x, 4.6, L['other'], RED, dashed=True)

    # 1 Learn: the analysis optimizer answers a question whose meaning is given.
    ex, ey, ew = stage(s, LEARN_B, 1, LEARN, *L['learn'])
    llm_badge(s, LEARN_B[0] + LEARN_B[2] - 6.0, LEARN_B[1] + 5.8, 3.2)
    rows(s, ex, ey, ew, L['l_rows'], PITCH, marks={2: 'ok'})

    # 2 Admission publishes revision 0 with the conditions derived from its structure.
    ex, ey, ew = stage(s, PUB, 2, LEARN, *L['pub'])
    rows(s, ex, ey, ew, L['p_rows'], PITCH, colors={3: MUTED})

    # 3 Optimization: an equivalent, cheaper rewrite becomes revision 1.
    ex, ey, ew = stage(s, OPT, 3, USE, *L['opt'])
    rows(s, ex, ey, ew, L['o_rows'], PITCH, colors={2: ACC_DK, 3: MUTED}, marks={0: 'ok', 1: 'ok'})

    # 4 User agents rely on the valid revision.
    ex, ey, ew = stage(s, USE_B, 4, EXEC, *L['use'])
    rows(s, ex, ey, ew, L['u_rows'], PITCH, marks={1: 'ok', 2: 'ok', 3: 'ok'})

    # 5 A restatement breaks key uniqueness.
    ex, ey, ew = stage(s, BREAK, 5, USE, *L['break'])
    rect(ex - 1.2, ey - 4.3, ew + 2.4, 5.8, AMBER_PALE, AMBER, .25, r=.8)
    text(ex, ey, L['table'], NOTE, INK)
    text(ex + ew, ey, '13 → 14', NOTE, WAIT, align='right')
    rows(s, ex, ey, ew, L['k_rows'], PITCH, first=1, colors={0: RED, 1: RED, 2: MUTED},
         marks={0: 'fail', 2: 'fail'})

    # 6 Bounded repair: exactly one filter restores the grain.
    ex, ey, ew = stage(s, REPAIR, 6, USE, *L['repair'])
    rows(s, ex, ey, ew, L['r_rows'], PITCH, colors={2: ACC_DK}, marks={0: 'ok', 1: 'fail', 2: 'ok'})

    # 7 Regression test as of learning time, then revision 2.
    ex, ey, ew = stage(s, REGRESS, 7, USE, *L['regress'])
    for k, label in enumerate(L['g_rows'][:2]):
        yy = ey + PITCH * k
        text(ex, yy, label, NOTE, INK)
        text(ex + ew, yy, L['value'], NOTE, INK, align='right')
    rows(s, ex, ey, ew, L['g_rows'][2:], PITCH, first=2, colors={0: ACC_DK, 1: ACC_DK},
         marks={0: 'ok', 1: 'ok'})

    # The other outcome: no unique repair.
    ex, ey, ew = stage(s, NOFIX, None, RED, *L['nofix'], edge=RED, dash=(1.6, 1.0))
    rows(s, ex, ey, ew, L['n_rows'], PITCH, colors={0: RED, 2: RED, 3: LEARN}, marks={0: 'fail'})

    # Arrows along each row.
    for (l, r), color in (((LEARN_B, PUB), LEARN), ((PUB, OPT), USE), ((OPT, USE_B), EXEC),
                          ((BREAK, REPAIR), USE), ((REPAIR, REGRESS), USE)):
        yy = l[1] + 5.6
        route([(l[0] + l[2], yy), (r[0], yy)], color, THIN, length=HEAD)
    # A later write: from the use of revision 1 down to the restatement.
    xu, yc = USE_B[0] + USE_B[2] / 2, R1 + RH + 4.5
    xk = BREAK[0] + BREAK[2] / 2
    route([(xu, R1 + RH), (xu, yc), (xk, yc), (xk, R2)], MUTED, THIN, radius=1.8, length=HEAD)
    text(xk + 2.8, yc + 4.2, L['write'], NOTE, MUTED)
    # From the repair search to the other outcome when no unique filter exists.
    xr, yb, xn = REPAIR[0] + REPAIR[2] / 2, R2 + RH + 4.0, NOFIX[0] + NOFIX[2] / 2
    route([(xr, R2 + RH), (xr, yb), (xn, yb), (xn, R2 + RH)], RED, THIN, radius=1.8, length=HEAD)
    text(xr + 3.0, yb + 4.4, L['several'], NOTE, RED)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
