"""Draft figure 3: how MAVRA learns a definition and keeps it valid, by example.

One definition, store return amount, through its life. Top row: the built-in
analysis optimizer, an LLM agent, answers a learning question whose meaning is
stated; the extractor and the admission checks turn its answer provenance into
m_1^1, with derived conditions and evidence; a benign write (late returns) makes
m_1^1 pending and the rechecks pass, so the revision stays. Bottom row: a
breaking write (an application-state row per return) fails the grain condition
and invalidates m_1^1; bounded repair finds exactly one filter that restores one
row per key without losing keys, the regression test compares it with the
agent's learning SQL as of learning time, and m_1^2 is published. The red box
is the other outcome: when two filters (or none) pass, as after a full backup
copy, the definition is invalidated and stays unavailable until a new judged
task is learned.

Values are those of the fixture and the end-to-end study: learning task M2-L1
(April, 3,133,115.63), held-out task M2-P1 (May, 3,294,349.93; the
unmaintained SQL returns 6,588,699.86 under status-change rows), the repair
filter sr_status = '完成' (completed), and the backup copy's sr_source filters.
Labels use words, not the paper's symbols (m_1^1, c_1, R, m').
Coordinates are millimetres from the top-left at printed size (178 mm).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from parts import (LEARN, NOTE, THIN, TITLE, USE, WAIT, baseline, legend, llm_badge,  # noqa: E402
                   mark, step)
from style import ACC, ACC_DK, AMBER, AMBER_PALE, FIELD, INK, MUTED, RED, WHITE  # noqa: E402
from vecfig import measure  # noqa: E402

NAME = 'lifecycle'
W, H = style.TEXTWIDTH, 57.0

LABELS = {
    'en': {
        'title': 'MAVRA learning and maintenance', 'paths': ('learning path', 'maintenance on use'),
        'otherwise': 'other outcome',
        'learn': ('Learn', 'built-in analysis optimizer, an LLM agent'),
        'l_rows': ('“Return amount in April?” + stated meaning',
                   '`SELECT SUM(sr_return_amt) … d_moy = 4`',
                   'answer 3,133,115.63, judged correct', 'admission checks pass'),
        'publish1': ('Publish revision 1', 'what the definition records'),
        'm1': ('`SUM(sr_return_amt)` by return date', 'relies on: one row per return,',
               'one date per date key, no lost dates', "evidence: the agent's SQL"),
        'benign': ('Benign write', 'late returns appended'),
        'b_rows': ('rechecked: still holds', '`date_dim` same: result reused',
                   'stays revision 1'),
        'later': 'a later write',
        'breaking': ('Breaking write', 'an application-state row per return'),
        'k_rows': ('one row per return: fails', 'revision 1 invalidated',
                   'unmaintained: 6,588,699.86 (2×)'),
        'search': ('Search filters', 'one filter per column value'),
        's_rows': ("`sr_status='completed'`", "`sr_status='applied'` loses returns",
                   'exactly one keeps one row per return'),
        'regress': ('Regression test', 'on the data as of learning'),
        'r_rows': ("agent's SQL", 'with the filter', 'same answer: fix accepted'),
        'publish2': ('Publish revision 2', 'same definition, new revision'),
        'p_rows': ('revision 1 + filter', "`sr_status='completed'`", 'SQL citing revision 1: rejected',
                   'waiting lookups get revision 2'),
        'nofix': ('No unique fix', 'e.g. a full backup copy appended'),
        'n_rows': ("`sr_source='primary'`", "`sr_source='backup'`", 'both work: invalidate',
                   'relearn from a new judged task'),
        'two': 'two fixes, or none', 'relearn': 'relearn',
    },
    'zh': {
        'title': 'MAVRA 学习与维护', 'paths': ('学习路径', '使用时维护'),
        'otherwise': '另一种结果',
        'learn': ('学习', '内置分析优化器（大模型智能体）'),
        'l_rows': ('“4 月的门店退货金额？”+ 给定口径',
                   '`SELECT SUM(sr_return_amt) … d_moy = 4`',
                   '答案 3,133,115.63，判题正确', '通过准入检查'),
        'publish1': ('发布修订 1', '定义记录的内容'),
        'm1': ('`SUM(sr_return_amt)` 按退货日期', '依赖：每笔退货一行、',
               '每个日期键一个日期、日期不丢失', '证据：智能体的 SQL'),
        'benign': ('正常写入', '追加迟到的退货'),
        'b_rows': ('变化的表：重查，成立', '`date_dim` 未变：复用结果', '仍是修订 1'),
        'later': '之后的一次写入',
        'breaking': ('破坏性写入', '每笔退货追加申请状态行'),
        'k_rows': ('每笔退货一行：不成立', '修订 1 失效', '不维护：6,588,699.86（2 倍）'),
        'search': ('搜索过滤', '每列每个取值试一个过滤'),
        's_rows': ("`sr_status='完成'`", "`sr_status='申请'` 丢掉退货", '恰好一个能恢复每笔退货一行'),
        'regress': ('回归测试', '在学习时刻的数据上'),
        'r_rows': ('智能体的 SQL', '加上过滤', '答案相同：接受修复'),
        'publish2': ('发布修订 2', '同一定义的新修订'),
        'p_rows': ('修订 1 + 过滤', "`sr_status='完成'`", '引用修订 1 的 SQL：拒绝', '等待的查找得到修订 2'),
        'nofix': ('没有唯一修复', '例：追加整份备份副本'),
        'n_rows': ("`sr_source='primary'`", "`sr_source='backup'`", '两个都可以：失效',
                   '由新的判题任务重新学习'),
        'two': '两个修复，或没有', 'relearn': '重新学习',
    },
}

ROUTE_Y = 7.0                            # the relearn route runs above the top row
R1, R2, RH = 9.0, 35.5, 20.5             # tops of the two rows, their height
LEARN_B = (1.5, R1, 47.0, RH)
PUB1 = (52.5, R1, 41.0, RH)
BENIGN = (97.5, R1, 33.5, RH)
NOFIX = (135.0, R1, 41.5, RH)
BREAK = (1.5, R2, 40.0, RH)
SEARCH = (45.5, R2, 44.0, RH)
REGRESS = (93.5, R2, 41.0, RH)
PUB2 = (138.5, R2, 38.0, RH)
PANEL = 8.6                              # example area starts this far below a box's top
ROW = 2.85                               # pitch of example rows


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def stage(b, n, color, title_note, edge='#9DBBE2', dash=None):
        """A step: badge, bold title, a muted note, then the example rows."""
        x, y, w, h = b
        rect(*b, WHITE, edge, .18, r=.8, dash=dash)
        if n is None:                        # the other outcome: a red badge with a cross
            s.circle(x + 2.5, y + 2.6, 1.45, RED)
            s.line(x + 2.0, y + 2.1, x + 3.0, y + 3.1, WHITE, .26)
            s.line(x + 2.0, y + 3.1, x + 3.0, y + 2.1, WHITE, .26)
        else:
            step(s, x + 2.5, y + 2.6, n, color)
        title, note = title_note
        text(x + 4.6, baseline(y + 2.6, TITLE), title, TITLE, INK, 'bold', width=w - 5.4)
        text(x + 1.4, y + 6.6, note, NOTE, MUTED, width=w - 2.4)
        rect(x + .9, y + PANEL - .4, w - 1.8, h - PANEL - .5, '#F7F6F3', None, r=.5)
        return x + 1.8, y + PANEL + 2.3, w - 3.6     # first example baseline and its room

    def version(ex, yy, ew, old, new):
        rect(ex - .6, yy - 2.0, ew + 1.2, 2.75, AMBER_PALE, AMBER, .12, r=.4)
        text(ex, yy, '`store_returns`', NOTE, INK)
        text(ex + ew, yy, f'${old}\\to{new}$', NOTE, WAIT, align='right')

    def rows(ex, ey, ew, lines, first=0, colors=None, marks=None):
        for k, line in enumerate(lines):
            yy = ey + ROW * (k + first)
            color = (colors or {}).get(k, INK)
            text(ex, yy, line, NOTE, color, width=ew - (2.4 if marks and k in marks else 0))
            if marks and k in marks:
                mark(s, ex + ew - 1.0, yy - .75, marks[k])

    rect(0, 0, W, H, FIELD, None, r=1.4)
    rect(1.5, 1.4, .55, 2.6, ACC)
    text(2.9, 3.6, L['title'], TITLE - .4, ACC_DK, 'bold')
    x = 92.0
    for label, color, steps in zip(L['paths'], (LEARN, USE), ('1–2', '3–7')):
        legend(s, x, 2.6, [(label, color, steps)])
        x += 6.6 + 1.2 + measure(label, NOTE) + 4.0
    rect(x, 1.2, 6.6, 2.8, WHITE, RED, .18, r=1.4, dash=(.8, .5))
    text(x + 7.8, baseline(2.6, NOTE), L['otherwise'], NOTE, INK)

    # 1 Learn: the optimizer answers a question whose meaning is stated -------
    ex, ey, ew = stage(LEARN_B, 1, LEARN, L['learn'])
    llm_badge(s, LEARN_B[0] + LEARN_B[2] - 3.0, LEARN_B[1] + 2.9, 1.6)
    rows(ex, ey, ew, L['l_rows'], marks={2: 'ok', 3: 'ok'})

    # 2 Publish m_1^1 with its conditions and evidence --------------------------
    ex, ey, ew = stage(PUB1, 2, LEARN, L['publish1'])
    rows(ex, ey, ew, L['m1'])

    # 3 A benign write: the rechecks pass, the revision stays --------------------
    ex, ey, ew = stage(BENIGN, 3, USE, L['benign'])
    version(ex, ey, ew, 12, 13)
    rows(ex, ey, ew, L['b_rows'], first=1, colors={2: ACC_DK}, marks={0: 'ok', 1: 'ok'})

    # 4 A breaking write invalidates m_1^1 -----------------------------------------
    ex, ey, ew = stage(BREAK, 4, USE, L['breaking'])
    version(ex, ey, ew, 13, 14)
    rows(ex, ey, ew, L['k_rows'], first=1, colors={0: RED, 1: RED, 2: MUTED}, marks={0: 'fail'})

    # 5 Bounded repair: search for exactly one filter ---------------------------
    ex, ey, ew = stage(SEARCH, 5, USE, L['search'])
    rows(ex, ey, ew, L['s_rows'], colors={2: ACC_DK}, marks={0: 'ok', 1: 'fail', 2: 'ok'})

    # 6 Regression test as of learning time ---------------------------------------
    ex, ey, ew = stage(REGRESS, 6, USE, L['regress'])
    for k, label in enumerate(L['r_rows'][:2]):
        yy = ey + ROW * k
        text(ex, yy, label, NOTE, INK)
        text(ex + ew - 2.4, yy, '3,133,115.63', NOTE, INK, align='right')
    rows(ex, ey, ew, L['r_rows'][2:], first=2, colors={0: ACC_DK}, marks={0: 'ok'})

    # 7 Publish the replacement -----------------------------------------------------
    ex, ey, ew = stage(PUB2, 7, USE, L['publish2'])
    rows(ex, ey, ew, L['p_rows'], colors={0: ACC_DK, 1: ACC_DK})

    # The other outcome: no unique fix, so invalidate and relearn ------------------
    ex, ey, ew = stage(NOFIX, None, RED, L['nofix'], edge=RED, dash=(.8, .5))
    rows(ex, ey, ew, L['n_rows'], colors={2: RED, 3: LEARN}, marks={0: 'ok', 1: 'ok'})

    # Arrows ---------------------------------------------------------------------
    for (l, r), color in (((LEARN_B, PUB1), LEARN), ((PUB1, BENIGN), USE), ((BREAK, SEARCH), USE),
                          ((SEARCH, REGRESS), USE), ((REGRESS, PUB2), USE)):
        yy = l[1] + 2.6
        route([(l[0] + l[2], yy), (r[0], yy)], color, THIN, length=1.0)
    # From the benign write to the breaking one: a later write.
    xb, yc = BENIGN[0] + BENIGN[2] / 2, R1 + RH + 2.2
    xk = BREAK[0] + BREAK[2] / 2
    route([(xb, R1 + RH), (xb, yc), (xk, yc), (xk, R2)], USE, THIN, radius=.9)
    text(xk + 1.6, yc + 2.6, L['later'], NOTE, USE)
    # From the filter search to the other outcome when the fix is not unique.
    xs, yn, xn = SEARCH[0] + SEARCH[2] - 8.0, R2 - 1.6, NOFIX[0] + NOFIX[2] / 2
    route([(xs, R2), (xs, yn), (xn, yn), (xn, R1 + RH)], RED, THIN, radius=.9)
    text(xb + 2.0, yn - .7, L['two'], NOTE, RED)
    # From the other outcome back to learning.
    xl = LEARN_B[0] + LEARN_B[2] / 2 + 8.0
    route([(xn, R1), (xn, ROUTE_Y), (xl, ROUTE_Y), (xl, R1)], LEARN, THIN, radius=.9, dash=(.9, .6))
    text(xl + 2.0, ROUTE_Y - .7, L['relearn'], NOTE, LEARN)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
