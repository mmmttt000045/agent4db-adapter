"""Deck figure 3 (the process): what happens to a definition as the data changes.

The third of three views of the method, as a state diagram whose boxes carry
step numbers 1-10 in reading order (main row, the improvement loop above valid,
then the repair path right to left and invalidation). A definition is
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
three writes' maintenance events and the September answers. Colours from deckpal.py. Drawn at slide size
(300 mm, 12-15 pt), Chinese only, standard database terms.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import HEAD, NOTE, THICK, THIN, baseline, example, state  # noqa: E402
from style import INK, MUTED, WHITE  # noqa: E402
import deckpal as P  # noqa: E402

NAME = 'process'
LANGS = ('zh',)                                  # the report deck is Chinese
W, H = 300.0, 142.0
LEARN, USE, MAINT, RED = P.PUBLISH, P.USE, P.MAINT, P.FAIL   # publish, use, maintain and optimize, invalidation

LABELS = {
    'zh': {
        'legend': (('发布', LEARN, '学习、发布前校验'), ('使用', USE, '执行前校验'),
                   ('维护与优化', MAINT, '修复、回归测试、优化'), ('指标失效', RED, '通知使用方')),
        'learn': ('学习', ('内置 agent 完成学习', '任务，提取指标定义'), ('3 月 1357.0 万 ✓',)),
        'admit': ('发布前校验', ('结果正确且可复现；', '保存前提条件与证据'), ('v1，3 个前提',)),
        'valid': ('有效', ('使用方声明指标', '版本后直接使用'), ('门店营业额 v2',)),
        'pending': ('待校验', ('依赖的表发生写入；', '下次使用时再校验'), ()),
        'check': ('执行前校验', ('在本次查询的快照上', '校验，结果按表版本', '缓存、跨指标复用'), ()),
        'improve': ('优化：结果等价且更快的 SQL', ('各期间结果一致且执行更快才发布，', '新 SQL 依赖的假设加入前提条件'),
                    ('改为日期键范围过滤，快 19.8% → v2，新增前提“日期键连续”',)),
        'candidate': '候选 SQL', 'adopt': '发布新版本',
        'holds': '校验通过：继续使用', 'holds_ex': '增量加载：9 月 2613.9 万 ✓',
        'fails': '校验不通过', 'fails_ex': '数据更正：主键重复',
        'repair': ('自动修复', ('寻找能恢复前提的过滤', '条件，且必须唯一'), ("`ss_is_current='1'`",)),
        'regress': ('回归测试', ('在学习时的数据上重算', '结果一致才发布'), ('3 月 1357.0 万 ✓',)),
        'publish': ('发布新版本', ('写入共享记忆；引用', '旧版本的查询被拒绝'), ('v3：9 月 1293.3 万 ✓',)),
        'effective': '新版本生效',
        'retire': ('指标失效，通知使用方', ('引用它的查询被拒绝，由使用方自行处理；', '等待重新学习'),
                   ('重复加载：没有过滤条件能消除主键重复',)),
        'relearn': '重新学习', 'no_repair': '找不到可行的过滤条件，或可行的不止一个',
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
            text(6.2, baseline(y, NOTE - 1), label, NOTE - 1, P.FAIL_TEXT, 'bold')
        else:
            rect(4.0, y - 2.9, w, 5.8, color, None, r=2.9)
            text(6.2, baseline(y, NOTE - 1), label, NOTE - 1, WHITE, 'bold')
        text(4.0 + w + 2.4, baseline(y, NOTE), desc, NOTE, MUTED, width=I[0] - 8.0 - w)

    # States and steps ----------------------------------------------------------------------------
    # Step numbers give the reading order: along the main row, up to the improvement loop, then the repair path.
    ex = P.EXAMPLE
    state(s, A, *L['learn'], color=P.PUBLISH_TEXT, edge=LEARN, n=1, badge=LEARN, ex_color=ex)
    state(s, B, *L['admit'], color=P.PUBLISH_TEXT, edge=LEARN, n=2, badge=LEARN, ex_color=ex)
    state(s, C, *L['valid'], color=P.USE_TEXT, edge=USE, sw=.7, fill=P.USE_PALE, n=3, badge=USE, ex_color=ex)
    state(s, I, *L['improve'], color=P.MAINT_TEXT, edge=MAINT, n=4, badge=MAINT, ex_color=ex)
    state(s, D, *L['pending'], color=P.PENDING_TEXT, edge=P.PENDING, fill=P.PENDING_PALE, n=5, badge=P.PENDING_TEXT,
          ex_color=ex)
    state(s, E, *L['check'], color=P.USE_TEXT, edge=USE, n=6, badge=USE, ex_color=ex)
    state(s, R, *L['repair'], color=P.MAINT_TEXT, edge=MAINT, ex_size=NOTE - 1, n=7, badge=MAINT, ex_color=ex)
    state(s, G, *L['regress'], color=P.MAINT_TEXT, edge=MAINT, n=8, badge=MAINT, ex_color=ex)
    state(s, N, *L['publish'], color=P.MAINT_TEXT, edge=MAINT, n=9, badge=MAINT, ex_color=ex)
    state(s, X, *L['retire'], color=P.FAIL_TEXT, edge=RED, dash=(1.6, 1.0), n=10, badge=RED, ex_color=ex)

    # Main row: learn -> admit -> valid -> pending -> check ------------------------------------------
    ym = ROW + RH / 2
    for (l, r), color in (((A, B), LEARN), ((B, C), LEARN), ((C, D), USE), ((D, E), USE)):
        route([(l[0] + l[2], ym), (r[0], ym)], color, THICK if (l, r) == (B, C) else THIN, length=HEAD)

    # Improvement: a candidate goes up, a new revision comes back down ------------------------------
    xu, xd = C[0] + 12.0, C[0] + 36.0
    route([(xu, C[1]), (xu, I[1] + I[3])], MAINT, THIN, length=HEAD)
    route([(xd, I[1] + I[3]), (xd, C[1])], MAINT, THICK, length=HEAD)
    text(xu + 2.4, 40.4, L['candidate'], NOTE, MUTED)
    text(xd + 2.4, 40.4, L['adopt'], NOTE, P.MAINT_TEXT)

    # The check holds: back to valid ---------------------------------------------------------------
    xl, xc = E[0] + 8.0, C[0] + C[2] - 8.0
    route([(xl, ROW + RH), (xl, LOOP_Y), (xc, LOOP_Y), (xc, ROW + RH)], USE, THIN, length=HEAD, radius=1.8)
    text(D[0] + 2.0, 78.2, L['holds'], NOTE, P.USE_TEXT)
    example(s, D[0] + 2.0, 86.8, L['holds_ex'], color=P.EXAMPLE)

    # The check fails: repair search, regression test, new revision ----------------------------------
    xf = E[0] + E[2] - 8.0
    route([(xf, ROW + RH), (xf, LOW)], MAINT, THIN, length=HEAD)
    text(xf - 2.4, 78.2, L['fails'], NOTE, P.MAINT_TEXT, align='right')
    ew = measure('例', NOTE - 1, 'bold') + 2.6 + 1.4 + measure(L['fails_ex'], NOTE)
    example(s, xf - 2.4 - ew, 93.4, L['fails_ex'], color=P.EXAMPLE)
    yl = LOW + 14.0
    for l, r in ((R, G), (G, N)):
        route([(l[0], yl), (r[0] + r[2], yl)], MAINT, THIN, length=HEAD)
    xn = N[0] + 28.0
    route([(xn, LOW), (xn, ROW + RH)], MAINT, THICK, length=HEAD)
    text(xn + 2.4, 87.4, L['effective'], NOTE, P.MAINT_TEXT)

    # No unique repair: invalidate, then learn again ---------------------------------------------------
    xr, yb = R[0] + 24.0, LOW + RH + 7.0
    xx = X[0] + X[2] / 2
    route([(xr, LOW + RH), (xr, yb), (xx, yb), (xx, LOW + RH)], RED, THIN, length=HEAD, radius=1.8)
    text((xr + xx) / 2, yb + 5.4, L['no_repair'], NOTE, P.FAIL_TEXT, align='center')
    xa = A[0] + 26.0
    route([(xa, LOW), (xa, ROW + RH)], RED, THIN, length=HEAD)
    text(xa + 2.4, 87.4, L['relearn'], NOTE, P.FAIL_TEXT)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
