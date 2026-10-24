"""Paper figure 1 (running example): one metric record through its lifecycle.

The record card states the identity shared by every revision: the metric
`store_revenue` = SUM(ss_net_paid) over the grain (ss_ticket_number,
ss_item_sk), with the executable condition c1 that grain keys stay unique.
The four stages then walk one scenario, kept consistent with the intro and
Section 4: agent A learns March revenue with one sale per ticket-item key and
publishes v1 after the check; agent B reuses v1 for September, a new period,
without repeating schema inspection, value probes, or join tests; a
restatement that retains old rows duplicates a grain key, and stage 3 shows
both fates — unmaintained reuse still executes and answers too high (the
over-count range measured in the population study), while MAVRA blocks v1
before reuse — and stage 4 repairs: the candidate filter `ss_is_current = 1`
is published as v2 only if it is the unique repair, preserves the key set,
and reproduces the learning-time answer, otherwise the record is revoked.
The only measured value is the too-high range, read from the
PpTrajChangeOverMin/Max macros of gen/population.tex so that the figure
prints exactly the over-count Section 7 prints; everything else is
schematic. Colors and marks follow the architecture figure: purple is the
learning path, blue reuse and maintenance, amber changed rows.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import PT, measure  # noqa: E402
import style  # noqa: E402
from style import ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FACE, INK, MUTED, RED, RULE, WHITE  # noqa: E402

NAME = 'metric-record'
W, H = style.COLUMN, 92.5

_PP = style.macros('population')
OVER = f"{_PP['PpTrajChangeOverMin']}–{_PP['PpTrajChangeOverMax']}%"

# IEEEtran conference \scriptsize is 7pt; the PDF is 84.6 mm wide and is
# scaled to the 88.9 mm column (x1.05), so TITLE, BODY and NOTE print at or
# above 7pt. SMALL and CHIP sit just under it inside chips and table rows.
TITLE, BODY, NOTE, SMALL, CHIP = 7.4, 7.0, 6.9, 6.4, 6.2
LEARN = '#7A68B0'                                # the learning path, as in the architecture figure
RED_PALE, GREY_ROW, WAIT = '#F9E9E6', '#E4E1DB', '#9A6500'
CODE = 'ss_is_current = 1'

LABELS = {
    'en': {
        'grain': 'Grain',
        's1': ('Learn', 'Agent A · March: one sale per ticket–item key',
               'publication check', 'publishes', 'v1'),
        's2': ('Reuse', 'Agent B · September: same record, new period',
               'holds on the new snapshot', 'schema, value probes, joins: skipped', 'SQL'),
        's3': ('Change', 'A restatement keeps old rows in `store_sales`:',
               ('(1001, 7)', 'current'), ('(1001, 7)', 'old'), ('(1002, 4)', 'current'),
               ('Unmaintained reuse:', ' SQL still runs, answer {} too high'),
               ('MAVRA:', ' a duplicated key violates $c_1$ → v1'), 'blocked'),
        's4': ('Maintain', 'candidate filter ', ('unique repair', 'keys preserved', 'March answer'),
               'all three hold', 'v2', '· otherwise ', 'revoke'),
    },
    'zh': {
        'grain': '粒度',
        's1': ('学习', '智能体 A · 三月：每个票据–商品键一次销售',
               '发布时检查', '发布', 'v1'),
        's2': ('复用', '智能体 B · 九月：同一记录，新的期间',
               '在新快照上仍成立', '模式、探查、连接：跳过', 'SQL'),
        's3': ('变化', '更正在 `store_sales` 中保留旧行：',
               ('(1001, 7)', '当前'), ('(1001, 7)', '旧行'), ('(1002, 4)', '当前'),
               ('不维护的复用：', 'SQL 照常执行，答案偏高 {}'),
               ('MAVRA：', '重复的键违反 $c_1$ → v1'), '已阻止'),
        's4': ('维护', '候选过滤 ', ('唯一修复', '键不变', '三月答案不变'),
               '三条全部成立', 'v2', '· 否则', '撤销'),
    },
}

CARD = (1.2, 1.2, 82.2, 11.8)
X_CIRCLE, X_TEXT, RIGHT = 6.0, 9.6, 83.4
Y1, Y2 = 18.8, 32.6                      # circle centres of stages 1 and 2
Y3, Y4 = 49.0, 74.8


def baseline(y_center, size):
    """Baseline that centres capitals and digits on y_center."""
    return y_center + .34 * size * PT


def draw(s, lang):
    L = LABELS[lang]
    text, rect = s.text, s.rect

    def mark(x, y, kind):
        """Check-result mark centred on (x, y): holds or fails."""
        if kind == 'ok':
            s.poly([(x - .62, y), (x - .15, y + .5), (x + .65, y - .55)], None, ACC, .24,
                   closed=False)
        else:
            s.line(x - .5, y - .5, x + .5, y + .5, RED, .24)
            s.line(x - .5, y + .5, x + .5, y - .5, RED, .24)

    def state_chip(y_c, label, x_right=RIGHT, fill=ACC_PALE, edge=ACC, tcol=ACC_DK):
        w = measure(label, CHIP, 'bold') + 2.8
        rect(x_right - w, y_c - 1.7, w, 3.4, fill, edge, .14, r=.6)
        text(x_right - w + 1.4, baseline(y_c, CHIP), label, CHIP, tcol, 'bold')
        return w

    def cond_chip(y_c, kind, x_right=RIGHT):
        rect(x_right - 4.2, y_c - 1.15, 4.2, 2.3, FACE, EDGE, .1, r=.45)
        text(x_right - 3.75, baseline(y_c, CHIP), '$c_1$', CHIP, INK)
        mark(x_right - 1.0, y_c, kind)

    # The record card: identity and structure shared by every revision ------
    rect(*CARD, WHITE, EDGE, .16, r=.6)
    rect(2.6, 2.7, .8, 6.9, ACC, None, r=.4)
    w = text(4.4, baseline(4.0, TITLE), 'store_revenue', TITLE, INK, 'code')
    text(4.4 + w + 1.0, baseline(4.0, TITLE), '= SUM(ss_net_paid)', TITLE, MUTED, 'code')
    state_chip(4.0, '$m_1$', x_right=82.0)
    w = text(4.4, baseline(9.2, NOTE), L['grain'], NOTE, MUTED)
    text(4.4 + w + 1.4, baseline(9.2, BODY), '(ss_ticket_number, ss_item_sk)', BODY, INK, 'code')
    cond_chip(9.2, 'ok', x_right=82.0)

    # The lifecycle spine with one circle per stage -------------------------
    s.line(X_CIRCLE, Y1, X_CIRCLE, Y4, RULE, .35)

    def stage(y, n, color, title):
        s.circle(X_CIRCLE, y, 1.55, color)
        text(X_CIRCLE, baseline(y, 6.6), str(n), 6.6, WHITE, 'bold', 'center')
        text(X_TEXT, baseline(y, TITLE), title, TITLE, INK, 'bold')

    # 1 Learn: the learned fact, then the publication check that admits v1 --
    y, t, l1, l2, verb, rev = Y1, *L['s1']
    stage(y, 1, LEARN, t)
    text(X_TEXT, baseline(y + 4.6, NOTE), l1, NOTE, INK, width=RIGHT - X_TEXT)
    y_c = y + 8.0
    w = text(X_TEXT, baseline(y_c, NOTE), l2, NOTE, MUTED)
    cond_chip(y_c, 'ok', x_right=X_TEXT + w + 6.0)
    chip_w = state_chip(y_c, rev)
    x_end = RIGHT - chip_w - 2.2
    text(x_end - measure(verb, NOTE), baseline(y_c, NOTE), verb, NOTE, MUTED)

    # 2 Reuse: one lookup replaces the exploration stages -------------------
    y, t, l1, l2, l3, sql = Y2, *L['s2']
    stage(y, 2, ACC, t)
    text(X_TEXT, baseline(y + 4.6, NOTE), l1, NOTE, INK, width=RIGHT - X_TEXT)
    y_c = y + 8.0
    w = text(X_TEXT, baseline(y_c, NOTE), f'$c_1$ {l2}', NOTE, INK, width=RIGHT - 16 - X_TEXT)
    mark(X_TEXT + w + 1.4, y_c, 'ok')
    state_chip(y_c, sql)
    text(X_TEXT, baseline(y + 11.4, SMALL), l3, SMALL, MUTED, width=RIGHT - X_TEXT)

    # 3 Change: the restatement duplicates a grain key; two fates follow ----
    y, t, l1, r1, r2, r3, naive, guarded, blocked = Y3, *L['s3']
    stage(y, 3, AMBER, t)
    text(X_TEXT, baseline(y + 4.6, NOTE), l1, NOTE, INK, width=RIGHT - X_TEXT)
    for k, (key, state) in enumerate((r1, r2, r3)):
        yy = y + 6.4 + 2.5 * k
        hot = k < 2
        rect(X_TEXT, yy, 33.0, 2.1, AMBER_PALE if hot else GREY_ROW,
             AMBER if hot else None, .1, r=.3)
        text(X_TEXT + 1.2, yy + 1.55, key, CHIP, INK, 'code')
        text(X_TEXT + 31.8, yy + 1.55, state, CHIP, WAIT if hot else MUTED, align='right')
    # The two fates of the same question: without maintenance the SQL still
    # runs and silently answers too high; MAVRA blocks and stage 4 repairs.
    y_c = y + 16.6
    w = text(X_TEXT, baseline(y_c, NOTE), naive[0], NOTE, RED, 'bold')
    text(X_TEXT + w, baseline(y_c, NOTE), naive[1].format(OVER), NOTE, INK,
         width=RIGHT - X_TEXT - w)
    y_c = y + 20.0
    w = text(X_TEXT, baseline(y_c, NOTE), guarded[0], NOTE, ACC_DK, 'bold')
    w += text(X_TEXT + w, baseline(y_c, NOTE), guarded[1], NOTE, INK,
              width=RIGHT - X_TEXT - w - 16.0)
    chip_w = state_chip(y_c, blocked, fill=RED_PALE, edge=RED, tcol=RED)
    if X_TEXT + w + 1.2 + chip_w > RIGHT + .01:
        raise SystemExit(f'stage 3: chip collides with text ({X_TEXT + w + 1.2 + chip_w:.1f} > {RIGHT})')

    # 4 Maintain: publish the repair only if the three criteria hold --------
    y, t, l1, crit, hold, rev, else_, revoke = Y4, *L['s4']
    stage(y, 4, ACC, t)
    y_c = y + 4.6
    w = text(X_TEXT, baseline(y_c, NOTE), f'{l1}`{CODE}`', NOTE, INK, width=RIGHT - X_TEXT)
    y_c = y + 8.4
    xx = X_TEXT
    for label in crit:
        w = text(xx, baseline(y_c, SMALL), label, SMALL, INK, width=RIGHT - xx - 3)
        mark(xx + w + 1.5, y_c, 'ok')
        xx += w + 6.0
    y_c = y + 12.2
    w = text(X_TEXT, baseline(y_c, NOTE), hold, NOTE, INK)
    w += text(X_TEXT + w, baseline(y_c, NOTE), ' → ', NOTE, MUTED)
    chip_w = measure(rev, CHIP, 'bold') + 2.8
    state_chip(y_c, rev, x_right=X_TEXT + w + chip_w)
    x_rev_end = RIGHT - measure(revoke, NOTE)
    text(x_rev_end - measure(else_, NOTE) - .4, baseline(y_c, NOTE), else_, NOTE, MUTED)
    text(x_rev_end, baseline(y_c, NOTE), revoke, NOTE, RED, width=RIGHT - x_rev_end)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
