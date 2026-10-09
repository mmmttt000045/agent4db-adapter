"""Deck figure 3 (the process): what happens to a definition as the data changes.

The third of three views of the method, as a state diagram. A definition is
learned and published after the admission checks; it is valid and used by
declaring its revision. A write to a table it reads makes it pending; nothing
runs until the next use, which validates the conditions on that query's snapshot
(results kept per table version and shared across definitions). If they hold,
it stays valid. If one fails, the repair search looks for a filter predicate that
restores it and accepts only a unique one; a regression test on the learning-time
data must return the learned answer; then a new revision is published. Without a
unique repair the definition is invalidated, its users are told, and it waits to
be learned again. Independently, an equivalent and faster SQL is published as a
new revision, with its own premise added as a condition.
Teal 例 lines follow store revenue: learned on March (13,570,368.70, 5 turns),
v1 with three conditions, v2 the date-key range (equal on 14 periods, 19.8%
faster, adds "date keys contiguous by month"); after the incremental load the
conditions hold (September 26,139,303.60, the reference answer); after the
correction grain-key uniqueness fails, ss_is_current = '1' is the only repair,
March is again 13,570,368.70 on the learning-time data, v3 answers September
12,932,888.04; after the duplicate load no filter restores the grain.
Values: trace run (exp/2026-10-08-optimize/trace) for learning; optimization run
(noctis results/scen-20261008-opt/metric-1791439498065570) for the rewrite, the
three writes' maintenance events and the September answers. Drawn at slide size
(300 mm, 12-15 pt), Chinese only, standard database terms.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import HEAD, LEARN, NOTE, THICK, THIN, USE, baseline, example, state  # noqa: E402
from style import ACC_PALE, AMBER, AMBER_PALE, INK, MUTED, RED, WHITE  # noqa: E402

NAME = 'process'
LANGS = ('zh',)                                  # the report deck is Chinese
W, H = 300.0, 142.0
MAINT = INK                                      # maintain and improve

LABELS = {
    'zh': {
        'legend': (('发布', LEARN, '学习、准入检查'), ('依赖', USE, '使用时验证'),
                   ('维护与改进', MAINT, '修复、回归测试、改进'), ('定义失效', RED, '通知使用方')),
        'learn': ('学习', ('内置 agent 解题，', '从答案中抽取定义'), ('3 月 1357.0 万 ✓',)),
        'admit': ('准入检查，发布', ('答案正确，重放一致；', '记下条件与证据'), ('v1，3 个条件',)),
        'valid': ('有效', ('使用方声明修订号', '后直接使用'), ('门店营业额 v2',)),
        'pending': ('待验证', ('所读的表有写入；', '下次使用时再验证'), ()),
        'check': ('使用时验证', ('在本次查询的快照上', '验证，结果按表版本', '缓存、跨定义共享'), ()),
        'improve': ('改进：等价且更快的写法', ('每个期间结果一致、计时更快才发布，', '新写法的前提成为新条件'),
                    ('日期键范围，快 19.8% → v2，新增“日期键按月连续”',)),
        'candidate': '候选写法', 'adopt': '发布新修订',
        'holds': '条件成立：继续使用', 'holds_ex': '增量加载：9 月 2613.9 万 ✓',
        'fails': '条件不成立', 'fails_ex': '数据更正：粒度键唯一不成立',
        'repair': ('修复搜索', ('找过滤谓词恢复条件，', '可行的必须唯一'), ("`ss_is_current='1'`",)),
        'regress': ('回归测试', ('在学习时数据上重算', '答案不变才发布'), ('3 月 1357.0 万 ✓',)),
        'publish': ('发布新修订', ('写入共享记忆；声明', '旧修订的查询被拒绝'), ('v3：9 月 1293.3 万 ✓',)),
        'effective': '新修订生效',
        'retire': ('定义失效，通知使用方', ('声明它的查询被拒绝，使用方自行作答；', '等待重新学习'),
                   ('重复加载：没有过滤能恢复唯一性',)),
        'relearn': '重新学习', 'no_repair': '没有可行的过滤，或可行的不止一个',
    },
}

ROW, RH = 44.0, 28.0                              # main row
LOW = 98.0                                        # bottom row
A = (4.0, ROW, 52.0, RH)
B = (64.0, ROW, 56.0, RH)
C = (128.0, ROW, 48.0, RH)
D = (184.0, ROW, 52.0, RH)
E = (244.0, ROW, 52.0, RH)
I = (100.0, 4.0, 140.0, 28.0)
X = (4.0, LOW, 100.0, RH)
N = (112.0, LOW, 60.0, RH)
G = (180.0, LOW, 50.0, RH)
R = (238.0, LOW, 58.0, RH)
LOOP_Y = 80.0                                     # the "conditions hold" path back to valid


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    # Legend: the three responsibilities of figure 1, and invalidation ---------------------------
    for k, (label, color, desc) in enumerate(L['legend']):
        y = 9.0 + 7.4 * k
        w = measure(label, NOTE - 1, 'bold') + 4.4
        if color == RED:
            rect(4.0, y - 2.9, w, 5.8, WHITE, RED, .4, r=2.9, dash=(1.4, .9))
            text(6.2, baseline(y, NOTE - 1), label, NOTE - 1, RED, 'bold')
        else:
            rect(4.0, y - 2.9, w, 5.8, color, None, r=2.9)
            text(6.2, baseline(y, NOTE - 1), label, NOTE - 1, WHITE, 'bold')
        text(4.0 + w + 2.4, baseline(y, NOTE), desc, NOTE, MUTED, width=I[0] - 8.0 - w)

    # States and steps ----------------------------------------------------------------------------
    state(s, A, *L['learn'], color=LEARN, edge=LEARN)
    state(s, B, *L['admit'], color=LEARN, edge=LEARN)
    state(s, C, *L['valid'], color=USE, edge=USE, sw=.7, fill=ACC_PALE)
    state(s, D, *L['pending'], color=AMBER, edge=AMBER, fill=AMBER_PALE)
    state(s, E, *L['check'], color=USE, edge=USE)
    state(s, I, *L['improve'], edge=MAINT)
    state(s, R, *L['repair'], edge=MAINT, ex_size=NOTE - 1)
    state(s, G, *L['regress'], edge=MAINT)
    state(s, N, *L['publish'], edge=MAINT)
    state(s, X, *L['retire'], color=RED, edge=RED, dash=(1.6, 1.0))

    # Main row: learn -> admit -> valid -> pending -> check ------------------------------------------
    ym = ROW + RH / 2
    for (l, r), color in (((A, B), LEARN), ((B, C), LEARN), ((C, D), USE), ((D, E), USE)):
        route([(l[0] + l[2], ym), (r[0], ym)], color, THICK if (l, r) == (B, C) else THIN, length=HEAD)

    # Improvement: a candidate goes up, a new revision comes back down ------------------------------
    xu, xd = C[0] + 12.0, C[0] + 36.0
    route([(xu, C[1]), (xu, I[1] + I[3])], MAINT, THIN, length=HEAD)
    route([(xd, I[1] + I[3]), (xd, C[1])], MAINT, THICK, length=HEAD)
    text(xu + 2.4, 40.4, L['candidate'], NOTE, MUTED)
    text(xd + 2.4, 40.4, L['adopt'], NOTE, INK)

    # The check holds: back to valid ---------------------------------------------------------------
    xl, xc = E[0] + 8.0, C[0] + C[2] - 8.0
    route([(xl, ROW + RH), (xl, LOOP_Y), (xc, LOOP_Y), (xc, ROW + RH)], USE, THIN, length=HEAD, radius=1.8)
    text(D[0] + 2.0, 78.2, L['holds'], NOTE, USE)
    example(s, D[0] + 2.0, 86.8, L['holds_ex'])

    # The check fails: repair search, regression test, new revision ----------------------------------
    xf = E[0] + E[2] - 8.0
    route([(xf, ROW + RH), (xf, LOW)], MAINT, THIN, length=HEAD)
    text(xf - 2.4, 78.2, L['fails'], NOTE, MAINT, align='right')
    ew = measure('例', NOTE - 1, 'bold') + 2.6 + 1.4 + measure(L['fails_ex'], NOTE)
    example(s, xf - 2.4 - ew, 93.4, L['fails_ex'])
    yl = LOW + 14.0
    for l, r in ((R, G), (G, N)):
        route([(l[0], yl), (r[0] + r[2], yl)], MAINT, THIN, length=HEAD)
    xn = N[0] + 28.0
    route([(xn, LOW), (xn, ROW + RH)], MAINT, THICK, length=HEAD)
    text(xn + 2.4, 87.4, L['effective'], NOTE, INK)

    # No unique repair: invalidate, then learn again ---------------------------------------------------
    xr, yb = R[0] + 24.0, LOW + RH + 7.0
    xx = X[0] + X[2] / 2
    route([(xr, LOW + RH), (xr, yb), (xx, yb), (xx, LOW + RH)], RED, THIN, length=HEAD, radius=1.8)
    text((xr + xx) / 2, yb + 5.4, L['no_repair'], NOTE, RED, align='center')
    xa = A[0] + 26.0
    route([(xa, LOW), (xa, ROW + RH)], RED, THIN, length=HEAD)
    text(xa + 2.4, 87.4, L['relearn'], NOTE, RED)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
