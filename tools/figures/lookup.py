"""Figure 2: how request handling serves a user agent's two requests, by example.

Top lane, the text request: the agent asks for "return amount" (its question
is the return amount in May). Lookup matches names and aliases, compares
the dependency versions recorded with the definition against the current ones,
reuses check results keyed by (id(c), V(dep(c))) or runs the missing checks,
and returns only a valid revision. Bottom lane, the SQL request: the agent's
query declares that revision; the middleware checks the declaration and reviews
the SQL, then validates the revision's conditions on the query's own snapshot,
in which a writer has meanwhile raised the version of store_returns, and runs
the query in the same transaction.

The example continues Figure 3's: revision 2 is the repaired return-amount
definition (filter sr_status = 'completed'); the return-rate definition shares
its grain condition, one row per return. Labels use words, not the paper's
symbols (m_1^2, D_s, Q_c, V(T)). The question and its answer, 3,294,349.93,
are a held-out task of the end-to-end study (task M2-P1).
Coordinates are millimetres from the top-left at printed size (178 mm).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import (EXEC, NOTE, THIN, TITLE, USE, WAIT, baseline, legend, mark,  # noqa: E402
                   node, person, step)
from style import (ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FIELD, INK, MUTED, RED,  # noqa: E402
                   WHITE)

NAME = 'lookup'
W, H = style.TEXTWIDTH, 78.0

LABELS = {
    'en': {
        'agent': 'User agent', 'mavra': 'MAVRA request handling',
        'paths': ('use path', 'execution path'),
        'text_req': 'Text request', 'question': ('Return amount', 'in May?'),
        'lookup_of': 'lookup “return amount”',
        'sql_req': 'SQL request', 'declares': 'declares: return amount, revision 2',
        'sql': ('SELECT SUM(sr_return_amt)', 'FROM store_returns', 'JOIN date_dim ON …',
                "WHERE sr_status = 'completed'", 'AND d_moy = 5 AND …'),
        's1': ('Match name', 'name or alias contains it'),
        'names': (('store return amount', True), ('store return rate', False),
                  ('store revenue', False)),
        's2': ('Compare versions', 'did its tables change?'),
        'checked': 'last check', 'now': 'now', 'pending': 'changed: recheck needed',
        's3': ('Reuse or check', 'look up each condition’s result'),
        'conds': ('one row per return', 'one date per date key', 'no lost dates'),
        'reuse_a': ('found at 15: reuse', 'found at 3: reuse', 'none at 15: check, store'),
        's4': ('Return', 'to the agent, if valid'),
        'valid': 'revision 2, valid', 'fields': ('`store_returns`', '`SUM(sr_return_amt)`',
                                                 "`sr_status='completed'`"),
        'then': ('then writes', 'its SQL'),
        'cr_title': 'Reuse of check results',
        'cr_note': ('Each check result is kept under its condition and',
                    'the version of the tables the check read. Every',
                    'definition and agent that needs the same condition',
                    'on the same version reuses it; only a new version',
                    'needs a new check.'),
        'cr_head': ('condition', 'table version', 'stored by', 'reused in'),
        'cr_rows': (('one row per return', '`store_returns` 15', 'return rate', (3,)),
                    ('one date per date key', '`date_dim` 3', 'an earlier check', (3, 6)),
                    ('no lost dates', '`store_returns` 15', 3, ()),
                    ('one row per return', '`store_returns` 16', 6, ()),
                    ('no lost dates', '`store_returns` 16', 6, ())),
        'reuse_store': 'reuse or store',
        's5': ('Check the declaration', 'can revision 2 be used?'),
        'decl': ('exists, not invalidated', 'still the latest revision', 'SQL keeps the status filter'),
        'reject': 'revision 1: outdated, rejected',
        's6': ('Same-snapshot validation', 'conditions hold on the query’s snapshot'),
        'snap': 'a write committed: `store_returns` now at 16',
        'reuse_b': ('none at 16: check, store', 'found at 3: reuse', 'none at 16: check, store'),
        's7': ('Execute', 'on the same snapshot'),
        'run': 'run the query', 'answer': 'answer',
        'if_fail': ('a failed condition', 'rejects the query'),
    },
    'zh': {
        'agent': '用户端智能体', 'mavra': 'MAVRA 请求处理',
        'paths': ('使用路径', '执行路径'),
        'text_req': '文本请求', 'question': ('5 月的门店', '退货金额？'),
        'lookup_of': '查找“退货金额”',
        'sql_req': 'SQL 请求', 'declares': '声明：退货金额，修订 2',
        'sql': ('SELECT SUM(sr_return_amt)', 'FROM store_returns', 'JOIN date_dim ON …',
                "WHERE sr_status = '完成'", 'AND d_moy = 5 AND …'),
        's1': ('匹配名称', '名称或别名包含请求'),
        'names': (('门店退货金额', True), ('门店退货率', False), ('门店营业额', False)),
        's2': ('比较版本', '它读的表变了吗？'),
        'checked': '上次检查', 'now': '当前', 'pending': '有变化：需要重验证',
        's3': ('复用或检查', '查每个条件的检查结果'),
        'conds': ('每笔退货一行', '每个日期键一个日期', '日期不丢失'),
        'reuse_a': ('15 上已有：复用', '3 上已有：复用', '15 上没有：检查并存入'),
        's4': ('返回', '有效时返回给智能体'),
        'valid': '修订 2，有效', 'fields': ('`store_returns`', '`SUM(sr_return_amt)`',
                                          "`sr_status='完成'`"),
        'then': ('然后写出', 'SQL'),
        'cr_title': '检查结果的复用',
        'cr_note': ('每个检查结果按“条件 + 检查所读表的版本”保存。',
                    '任何定义、任何智能体只要需要同一条件、同一',
                    '表版本，就直接复用；只有表版本变了，',
                    '才需要重新检查。'),
        'cr_head': ('条件', '表版本', '存入者', '复用于'),
        'cr_rows': (('每笔退货一行', '`store_returns` 15', '退货率', (3,)),
                    ('每个日期键一个日期', '`date_dim` 3', '更早的检查', (3, 6)),
                    ('日期不丢失', '`store_returns` 15', 3, ()),
                    ('每笔退货一行', '`store_returns` 16', 6, ()),
                    ('日期不丢失', '`store_returns` 16', 6, ())),
        'reuse_store': '复用或存入',
        's5': ('核对声明', '修订 2 能用吗？'),
        'decl': ('存在且未失效', '仍是最新修订', 'SQL 含状态过滤'),
        'reject': '修订 1：已过时，拒绝',
        's6': ('同快照验证', '条件在查询的快照上成立'),
        'snap': '写入已提交：`store_returns` 变为 16',
        'reuse_b': ('16 上没有：检查并存入', '3 上已有：复用', '16 上没有：检查并存入'),
        's7': ('执行', '在同一快照上'),
        'run': '执行查询', 'answer': '答案',
        'if_fail': ('条件失败', '则拒绝查询'),
    },
}

TOP = 6.5                                # lanes start below the header
A_Y, A_H = TOP, 21.5                     # text request lane
CR = (92.0, 32.0, 84.5, 19.6)            # check results, between the lanes
B_Y, B_H = 55.5, 21.5                    # SQL request lane
REQ_A = (1.5, A_Y, 24.3, A_H)
S1 = (30.0, A_Y, 25.0, A_H)
S2 = (59.0, A_Y, 29.0, A_H)
S3 = (92.0, A_Y, 54.5, A_H)
S4 = (150.5, A_Y, 26.0, A_H)
REQ_B = (1.5, B_Y, 36.5, B_H)
S5 = (42.0, B_Y, 46.0, B_H)
S6 = (92.0, B_Y, 54.5, B_H)
S7 = (150.5, B_Y, 26.0, B_H)
FIELD_BOX = (28.0, .5, 149.0, H - 1.0)
PANEL = 8.6                              # example area starts this far below a stage's top
ROW = 3.0                                # pitch of example rows


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def stage(b, n, color, title_note):
        """A step: badge, bold title, the rule in a muted note, then the example."""
        x, y, w, h = b
        rect(*b, WHITE, '#9DBBE2', .18, r=.8)
        step(s, x + 2.5, y + 2.6, n, color)
        title, note = title_note
        text(x + 4.6, baseline(y + 2.6, TITLE), title, TITLE, INK, 'bold', width=w - 5.4)
        text(x + 1.4, y + 6.6, note, NOTE, MUTED, width=w - 2.4)
        rect(x + .9, y + PANEL - .4, w - 1.8, h - PANEL - .5, '#F7F6F3', None, r=.5)
        return x + 1.8, y + PANEL + 2.4, w - 3.6     # first example baseline and its room

    def nomatch(x, y):
        s.line(x - .55, y, x + .55, y, MUTED, .24)

    # Header: who is where, and the path colours ------------------------------
    rect(*FIELD_BOX, FIELD, None, r=1.4)
    text(1.5, 3.6, L['agent'], TITLE, INK, 'bold')
    rect(29.7, 1.4, .55, 2.6, ACC)
    text(31.1, 3.6, L['mavra'], TITLE - .4, ACC_DK, 'bold')
    x = 120
    for label, color, steps in zip(L['paths'], (USE, EXEC), ('1–4', '5–7')):
        legend(s, x, 2.6, [(label, color, steps)])
        x += 6.6 + 1.2 + measure(label, NOTE) + 4.0

    # Text request: a person asking, the lookup it sends ---------------------
    x, y, w, h = REQ_A
    node(s, REQ_A)
    text(x + 1.4, y + 3.6, L['text_req'], TITLE, INK, 'bold', width=w - 2.4)
    person(s, x + 1.4, y + 6.6)
    bx, by, bw, bh = x + 4.8, y + 5.6, w - 6.0, 6.8
    rect(bx, by, bw, bh, ACC_PALE, ACC, .12, r=.9)
    q1, q2 = L['question']
    text(bx + bw / 2, by + 2.8, q1, NOTE, ACC_DK, align='center', width=bw - .6)
    text(bx + bw / 2, by + 5.4, q2, NOTE, ACC_DK, align='center', width=bw - .6)
    rect(x + 1.4, y + 15.4, w - 2.8, 2.6, WHITE, USE, .14, r=.5)
    text(x + w / 2, y + 17.25, L['lookup_of'], NOTE, USE, align='center', width=w - 3.2)

    # 1 Match name -----------------------------------------------------------
    ex, ey, ew = stage(S1, 1, USE, L['s1'])
    for k, (name, hit) in enumerate(L['names']):
        yy = ey + ROW * k
        if hit:
            rect(ex - .6, yy - 2.1, ew + 1.2, 2.9, ACC_PALE, None, r=.4)
        text(ex, yy, name, NOTE, INK if hit else MUTED, width=ew - 2.6)
        if hit:
            mark(s, ex + ew - 1.0, yy - .75, 'ok')
        else:
            nomatch(ex + ew - 1.0, yy - .75)

    # 2 Compare versions -----------------------------------------------------
    ex, ey, ew = stage(S2, 2, USE, L['s2'])
    c1, c2 = ex + ew - 8.0, ex + ew - 1.2           # right edges of the two version columns
    text(c1, ey, L['checked'], NOTE, MUTED, align='right')
    text(c2, ey, L['now'], NOTE, MUTED, align='right')
    for k, (table, then, now) in enumerate((('`store_returns`', 14, 15), ('`date_dim`', 3, 3))):
        yy = ey + ROW * (k + 1)
        if then != now:
            rect(ex - .6, yy - 2.1, ew + 1.2, 2.9, AMBER_PALE, AMBER, .12, r=.4)
        text(ex, yy, table, NOTE, INK)
        text(c1, yy, f'${then}$', NOTE, INK, align='right')
        text(c2, yy, f'${now}$', NOTE, WAIT if then != now else INK, align='right')
    text(ex, ey + ROW * 3 + .2, L['pending'], NOTE, WAIT, 'bold')

    # 3 Reuse a check result or run the check ---------------------------------
    ex, ey, ew = stage(S3, 3, USE, L['s3'])
    for k, (cond, outcome) in enumerate(zip(L['conds'], L['reuse_a'])):
        yy = ey + ROW * k
        text(ex, yy, cond, NOTE, INK, width=21.0)
        text(ex + 21.5, yy, outcome, NOTE, MUTED if k < 2 else WAIT, width=ew - 24.0)
        mark(s, ex + ew - 1.0, yy - .75, 'ok')

    # 4 Return the valid revision ---------------------------------------------
    ex, ey, ew = stage(S4, 4, USE, L['s4'])
    text(ex, ey, L['valid'], NOTE, ACC_DK, 'bold')
    for k, field in enumerate(L['fields']):
        text(ex, ey + 2.7 * (k + 1), field, NOTE, INK, width=ew + .6)
    # The agent then writes the SQL of the second lane from the returned fields.
    xa = REQ_A[0] + 8.0
    route([(xa, A_Y + A_H), (xa, B_Y - 1.6)], INK, THIN, length=1.0)
    for k, line in enumerate(L['then']):
        text(xa + 1.6, (A_Y + A_H + B_Y) / 2 - .4 + 2.6 * k, line, NOTE, MUTED)

    # Check results, between the lanes: who stored each entry, which step reused it
    nx, ny = 31.1, CR[1] + 3.0
    text(nx, ny, L['cr_title'], TITLE, ACC_DK, 'bold')
    for k, line in enumerate(L['cr_note']):
        text(nx, ny + 3.4 + 2.75 * k, line, NOTE, INK, width=CR[0] - nx - 2.0)
    x, y, w, h = CR
    rect(*CR, WHITE, '#9DBBE2', .18, r=.8)
    cols = (x + 1.8, x + 23.5, x + 43.5, x + 47.5, x + 70.0)     # condition, version, mark, by, in
    hy = y + 3.0
    for cx_, head in zip((cols[0], cols[1], cols[3], cols[4]), L['cr_head']):
        text(cx_, hy, head, NOTE, MUTED)
    s.line(x + 1.0, hy + 1.0, x + w - 1.0, hy + 1.0, '#D3D0CA', .14)
    for k, (cond, version, by, used) in enumerate(L['cr_rows']):
        yy = hy + 3.3 + 2.95 * k
        new = not isinstance(by, str)
        if new:
            rect(x + .9, yy - 2.05, w - 1.8, 2.75, '#FBF6EA', None, r=.4)
        text(cols[0], yy, cond, NOTE, INK, width=cols[1] - cols[0] - .6)
        text(cols[1], yy, version, NOTE, INK, width=cols[2] - cols[1] - .4)
        mark(s, cols[2] + .6, yy - .75, 'ok')
        if new:
            step(s, cols[3] + 1.5, yy - .75, by, USE if by == 3 else EXEC)
        else:
            text(cols[3], yy, by, NOTE, MUTED, width=cols[4] - cols[3] - .6)
        for j, n in enumerate(used):
            step(s, cols[4] + 1.5 + 3.4 * j, yy - .75, n, USE if n == 3 else EXEC)
    # The two steps that read and write it.
    xc = S3[0] + 14.0
    route([(xc, A_Y + A_H), (xc, y)], USE, THIN, heads='both', length=1.0)
    text(xc + 1.6, baseline((A_Y + A_H + y) / 2, NOTE), L['reuse_store'], NOTE, USE)
    route([(xc, y + h), (xc, B_Y)], EXEC, THIN, heads='both', length=1.0)
    text(xc + 1.6, baseline((y + h + B_Y) / 2, NOTE), L['reuse_store'], NOTE, EXEC)

    # SQL request: the agent's query declaring m_1^2 ---------------------------
    x, y, w, h = REQ_B
    node(s, REQ_B)
    text(x + 1.4, y + 3.6, L['sql_req'], TITLE, INK, 'bold', width=w - 2.4)
    for k, line in enumerate(L['sql']):
        text(x + 1.4, y + 6.9 + 2.55 * k, line, NOTE, INK, 'code', width=w - 2.2)
    rect(x + 1.4, y + h - 3.3, w - 2.8, 2.6, WHITE, EXEC, .14, r=.5)
    text(x + w / 2, y + h - 1.45, L['declares'], NOTE, EXEC, align='center', width=w - 3.2)

    # 5 Check the declaration ---------------------------------------------------
    ex, ey, ew = stage(S5, 5, EXEC, L['s5'])
    for k, line in enumerate(L['decl']):
        yy = ey + ROW * k
        mark(s, ex + .7, yy - .75, 'ok')
        text(ex + 2.2, yy, line, NOTE, INK, width=ew - 2.2)
    yy = ey + ROW * 3
    mark(s, ex + .7, yy - .75, 'fail')
    text(ex + 2.2, yy, L['reject'], NOTE, RED, width=ew - 2.2)

    # 6 Same-snapshot validation -------------------------------------------------
    ex, ey, ew = stage(S6, 6, EXEC, L['s6'])
    rect(ex - .6, ey - 2.1, ew + 1.2, 2.9, AMBER_PALE, AMBER, .12, r=.4)
    text(ex, ey, L['snap'], NOTE, WAIT, width=ew)
    for k, (cond, outcome) in enumerate(zip(L['conds'], L['reuse_b'])):
        yy = ey + ROW * (k + 1)
        text(ex, yy, cond, NOTE, INK, width=21.0)
        text(ex + 21.5, yy, outcome, NOTE, MUTED if k == 1 else WAIT, width=ew - 24.0)
        mark(s, ex + ew - 1.0, yy - .75, 'ok')

    # 7 Execute on the same snapshot -------------------------------------------
    ex, ey, ew = stage(S7, 7, EXEC, L['s7'])
    text(ex, ey, L['run'], NOTE, INK)
    text(ex, ey + ROW + .2, L['answer'], NOTE, MUTED)
    text(ex + ew, ey + ROW + .5, '3,294,349.93', TITLE, EXEC, align='right')
    f1, f2 = L['if_fail']
    text(ex, ey + ROW * 2 + .6, f1, NOTE, MUTED, width=ew)
    text(ex, ey + ROW * 3 + .6, f2, NOTE, MUTED, width=ew)

    # Arrows from one step to the next -----------------------------------------
    ya, yb_ = A_Y + 2.6, B_Y + 2.6
    for (l, r), color, yy in (((REQ_A, S1), USE, ya), ((S1, S2), USE, ya), ((S2, S3), USE, ya),
                              ((S3, S4), USE, ya), ((REQ_B, S5), EXEC, yb_),
                              ((S5, S6), EXEC, yb_), ((S6, S7), EXEC, yb_)):
        x0 = l[0] + l[2] + (1.5 if l in (REQ_A, REQ_B) else 0)
        route([(x0, yy), (r[0], yy)], color, THIN, length=1.0)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
