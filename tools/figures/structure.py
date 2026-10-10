"""Deck figure 1 (structure): where MAVRA sits and the three responsibilities it carries.

The first of three views of the method. This one is static: the built-in agent
(an LLM) learns a definition once; many user agents rely on it; MAVRA sits
between them and the database. Its shared memory holds definitions (SQL, the
conditions it holds under, a revision number) and validation results kept per
(condition, table version). Three responsibilities surround the memory: publish
(admission checks, then the definition goes in with its conditions), rely (a
query declares the revision it uses and runs only when the conditions hold on
its snapshot), maintain and improve (after a write, re-validate; repair into a
new revision or invalidate; publish equivalent faster SQL as a new revision).
Writers change the tables; every write raises the table's version.
The example lines (teal 例) are the running example: 门店营业额 learned on March
(13,570,368.70, judged correct), v2 used in September after the incremental load
(26,139,303.60, the reference answer); see lifecycle and definition figures for
their sources. Drawn at slide size (300 mm, 12-15 pt), Chinese only, standard
database terms rather than the paper's notation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import (DASH, EXEC, HEAD, LEARN, NOTE, PANEL_EDGE, THICK, THIN, TITLE, USE,  # noqa: E402
                   baseline, example, llm_badge, person, slab, table_card, tag)
from style import ACC, ACC_DK, ACC_PALE, EDGE, FIELD, INK, MUTED, SLATE, WHITE  # noqa: E402

NAME = 'structure'
LANGS = ('zh',)                                  # the report deck is Chinese
W, H = 300.0, 134.0

LABELS = {
    'zh': {
        'learner': ('内置 agent（大模型）', '完成学习任务，提取指标定义'), 'once': '一次学习',
        'users': ('用户 agent A、B、C …', '提问、编写 SQL、复用指标定义'), 'many': '多次复用',
        'mavra': 'MAVRA 共享记忆层',
        'candidate': '候选定义',
        'publish': ('发布', '发布前校验', ('结果经确认正确；', '按定义重新生成的 SQL 能在', '学习时的数据上复现相同结果；', '通过后连同前提条件一起入库')),
        'publish_ex': '门店营业额 v1：3 月 1357.0 万 ✓',
        'memory': '共享记忆',
        'defs': '指标定义：口径 + SQL + 前提条件 + 版本号',
        'chips': (('门店营业额', 'v2 · 4 个前提'), ('电子品类门店营业额', 'v2'), ('…', '')),
        'results': '校验结果：按（前提，表版本）缓存，',
        'results2': '跨指标、跨 agent 复用',
        'rely': ('使用', '执行前校验', ('查询声明所用的指标版本；', '在本次查询的快照上校验前提，', '通过后在同一快照上执行')),
        'rely_ex': '声明 v2，9 月 2613.9 万 ✓',
        'ask': '取指标定义；SQL + 指标版本', 'answer': '有效版本；查询结果',
        'maint': ('维护与优化',
                  '表发生写入后重新校验前提：通过则继续使用；不通过则自动修复并发布新版本，无法修复则置为失效',
                  '发现结果等价且更快的 SQL，校验后发布为新版本'),
        'maint_ex': '修复得到 v3；日期键范围过滤的 v2 快 19.8%',
        'revise': '新版本或失效', 'checks': '校验查询', 'run': ('在快照上', '校验并执行'),
        'db': '数据库', 'versions': ('表版本', '每次写入递增'), 'snapshot': '快照',
        'etl': ('ETL / 写入方', '增量加载、', '数据更正、', '重复加载 …'),
    },
}

TOP = (6.0, 3.0, 110.0, 21.0)                    # built-in agent
USERS = (172.0, 3.0, 124.0, 21.0)                # user agents
FIELD_BOX = (2.0, 30.0, 296.0, 79.0)             # MAVRA's area
PUB = (6.0, 43.0, 88.0, 42.0)
MEM = (104.0, 43.0, 92.0, 42.0)
RELY = (206.0, 43.0, 88.0, 42.0)
MAINT = (6.0, 91.0, 236.0, 15.0)
DB = (44.0, 116.0, 252.0, 16.0)


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def pill(x, y, label, color):
        w = measure(label, NOTE - 1, 'bold') + 4.4
        rect(x, y - 2.9, w, 5.8, color, None, r=2.9)
        text(x + 2.2, baseline(y, NOTE - 1), label, NOTE - 1, WHITE, 'bold')
        return w

    # Agents: one learner, many users ------------------------------------------------------
    x, y, w, h = TOP
    rect(*TOP, '#F7FAFE', ACC, .4, r=1.6)
    llm_badge(s, x + 7.0, y + h / 2, 3.6)
    title, note = L['learner']
    text(x + 13.5, y + 8.6, title, TITLE, INK, 'bold')
    text(x + 13.5, y + 15.6, note, NOTE, MUTED, width=w - 17)
    pill(x + w - 3.0 - measure(L['once'], NOTE - 1, 'bold') - 4.4, y + 8.6 - 1.9, L['once'], LEARN)
    x, y, w, h = USERS
    rect(*USERS, WHITE, EDGE, .3, r=1.6)
    for k in range(3):
        person(s, x + 3.5 + 6.6 * k, y + 6.8)
    title, note = L['users']
    text(x + 26.0, y + 8.6, title, TITLE, INK, 'bold')
    text(x + 26.0, y + 15.6, note, NOTE, MUTED, width=w - 29)
    pill(x + w - 3.0 - measure(L['many'], NOTE - 1, 'bold') - 4.4, y + 8.6 - 1.9, L['many'], USE)

    # MAVRA's area ----------------------------------------------------------------------------
    rect(*FIELD_BOX, FIELD, None, r=2.8)
    rect(FIELD_BOX[0] + 4.0, 34.2, 1.1, 5.4, ACC)
    text(FIELD_BOX[0] + 7.2, 39.0, L['mavra'], TITLE, ACC_DK, 'bold')

    def duty(b, label, title, lines, ex):
        x, y, w, h = b
        rect(*b, WHITE, PANEL_EDGE, .45, r=1.6)
        tw = tag(s, x + 3.0, y + 5.6, label)
        text(x + 6.0 + tw, baseline(y + 5.6, TITLE), title, TITLE, INK, 'bold', width=w - 9.0 - tw)
        for k, line in enumerate(lines):
            text(x + 3.0, y + 15.6 + 5.4 * k, line, NOTE, INK, width=w - 6.0)
        example(s, x + 3.0, y + h - 3.4, ex, width=w - 6.0)

    label, title, lines = L['publish']
    duty(PUB, label, title, lines, L['publish_ex'])
    label, title, lines = L['rely']
    duty(RELY, label, title, lines, L['rely_ex'])

    # The shared memory --------------------------------------------------------------------------
    x, y, w, h = MEM
    rect(*MEM, '#FBFCFE', ACC, .5, r=1.6)
    text(x + 3.0, y + 7.0, L['memory'], TITLE, ACC_DK, 'bold')
    text(x + 3.0, y + 13.6, L['defs'], NOTE, INK, width=w - 6.0)
    cy, cx = y + 16.4, x + 3.0
    for name, sub in L['chips']:
        cw = max(measure(name, NOTE), measure(sub, NOTE)) + 4.0
        rect(cx, cy, cw, 11.0, ACC_PALE, None, r=1.0)
        text(cx + 2.0, cy + 4.6, name, NOTE, INK)
        if sub:
            text(cx + 2.0, cy + 9.4, sub, NOTE - 1, ACC_DK)
        cx += cw + 2.0
    if cx - 2.0 > x + w - 3.0:
        raise ValueError(f'definition chips need {cx - 2.0 - x + 3.0:.1f} mm; {w:.1f} mm available')
    text(x + 3.0, y + h - 7.6, L['results'], NOTE, MUTED, width=w - 6.0)
    text(x + 3.0, y + h - 2.6, L['results2'], NOTE, MUTED, width=w - 6.0)

    # Maintain and improve, below the memory ------------------------------------------------------
    x, y, w, h = MAINT
    rect(*MAINT, WHITE, PANEL_EDGE, .45, r=1.6)
    label, line1, line2 = L['maint']
    tw = tag(s, x + 3.0, y + 5.0, label)
    text(x + 6.0 + tw, baseline(y + 5.0, NOTE), line1, NOTE, INK, width=w - 9.0 - tw)
    w2 = text(x + 6.0 + tw, baseline(y + 10.6, NOTE), line2, NOTE, INK)
    example(s, x + 10.0 + tw + w2, baseline(y + 10.6, NOTE), L['maint_ex'], width=w - 13.0 - tw - w2)

    # Arrows: learner -> publish -> memory -> rely <-> users; maintenance <-> memory and database ----
    xa = PUB[0] + PUB[2] - 14.0
    route([(xa, TOP[1] + TOP[3]), (xa, PUB[1])], LEARN, THIN, length=HEAD)
    text(xa - 2.0, 30.0 - 1.4, L['candidate'], NOTE, LEARN, align='right')
    ym = PUB[1] + 21.0
    route([(PUB[0] + PUB[2], ym), (MEM[0], ym)], LEARN, THICK, length=HEAD)
    route([(MEM[0] + MEM[2], ym), (RELY[0], ym)], USE, THIN, length=HEAD)
    xd, xu = RELY[0] + 12.0, RELY[0] + 20.0
    route([(xd, USERS[1] + USERS[3]), (xd, RELY[1])], USE, THIN, length=HEAD)
    route([(xu, RELY[1]), (xu, USERS[1] + USERS[3])], USE, THIN, length=HEAD)
    text(xd - 2.0, 30.0 - 1.4, L['ask'], NOTE, USE, align='right')
    text(xu + 2.0, 30.0 - 1.4, L['answer'], NOTE, USE)
    xr = MEM[0] + MEM[2] / 2
    route([(xr, MAINT[1]), (xr, MEM[1] + MEM[3])], INK, THICK, length=HEAD)
    text(xr + 2.4, baseline((MAINT[1] + MEM[1] + MEM[3]) / 2, NOTE), L['revise'], NOTE, INK)
    xq = 182.0                                    # onto the table versions
    route([(xq, MAINT[1] + MAINT[3]), (xq, DB[1] - 2.8)], SLATE, THIN, dash=DASH, length=HEAD)
    text(xq + 2.4, baseline((MAINT[1] + MAINT[3] + DB[1] - 2.8) / 2, NOTE), L['checks'], NOTE, SLATE)
    xe = RELY[0] + RELY[2] / 2 + 14.0
    route([(xe, RELY[1] + RELY[3]), (xe, DB[1] - 2.8)], EXEC, THIN, length=HEAD)
    for k, line in enumerate(L['run']):
        text(xe + 2.4, 97.0 + 5.4 * k, line, NOTE, EXEC)

    # Database and writers -------------------------------------------------------------------------
    x, y, w, h = DB
    slab(s, DB)
    text(x + 4.0, baseline(y + h / 2, TITLE), L['db'], TITLE, INK, 'bold')
    tx = x + 28.0
    for k, label in enumerate(('`store_sales`', '`date_dim`', '…')):
        table_card(s, tx + 28.0 * k, 26.0, y + 2.0, h - 4.0, label, (1,) if k == 0 else ())
    vx = tx + 28.0 * 3 + 2.0
    rect(vx, y + 2.0, 48.0, h - 4.0, WHITE, EDGE, .28, r=.8)
    a, b = L['versions']
    text(vx + 2.6, baseline(y + h / 2, NOTE), a, NOTE, INK, 'bold')
    text(vx + 4.6 + measure(a, NOTE, 'bold'), baseline(y + h / 2, NOTE), b, NOTE, MUTED, width=48.0 - 7.2 - measure(a, NOTE, 'bold'))
    nx = 236.0                                    # the snapshot one query reads, under the execution arrow
    rect(nx, y + 2.0, x + w - 4.0 - nx, h - 4.0, WHITE, EXEC, .35, r=.8, dash=(1.6, 1.0))
    text(nx + 2.6, baseline(y + h / 2, NOTE), L['snapshot'], NOTE, EXEC)
    for k in range(2):
        table_card(s, nx + 16.0 + 17.0 * k, 14.0, y + 3.2, h - 6.4)
    t, *more = L['etl']
    text(4.0, 116.0, t, NOTE, INK, 'bold')
    for k, line in enumerate(more):
        text(4.0, 121.6 + 4.8 * k, line, NOTE - 1, MUTED)
    route([(26.0, 124.0), (x, 124.0)], INK, THIN, length=HEAD)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
