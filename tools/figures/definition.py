"""Deck figure 2 (the object): what one shared definition is, and why its conditions matter.

The second of three views of the method. Top: a definition is SQL plus the
conditions it holds under, and the conditions follow from the SQL's structure:
a sum over a fact table needs one row per business event (grain key unique); a
join to a dimension needs each key to match one row (date key unique); an inner
join must not lose fact rows (date-key completeness); the date-key range of
revision v2 needs each month's keys to be contiguous. Each condition is a check
query recorded when the definition is published. Bottom: the three everyday
writes of the deck's problem slide, each started from the same data, asking for
September store revenue. The SQL runs without error every time; incremental load
and duplicate load give the same 26,139,303.60, one right and one wrong, and only
grain-key uniqueness tells them apart.
Values: condition outcomes from the optimization run (noctis
results/scen-20261008-opt/metric-1791439498065570, maintenance events of the
append, revision and dupload phases: the grain check fails with 1,065,915 rows /
1,000,000 keys and 1,110,165 / 1,000,000, the coverage check passes, the two
date_dim conditions are skipped because date_dim was not written); answers of
the definition left as learned from results/scen-20261002
(dsv41flash-r1-g3fix--schema) with the reference answers of the same records.
Step numbers 1-7 give the reading order: the three columns of the top, then the
matrix's label column (writes, checks, the SQL's result, the verdict).
Colours from deckpal.py. Drawn at slide size (300 mm, 12-15 pt), Chinese only, standard database terms.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import PT, measure  # noqa: E402
from parts import HEAD, NOTE, THIN, TITLE, baseline, example, mark, step  # noqa: E402
from style import EDGE, INK, MUTED, RULE, WHITE  # noqa: E402
import deckpal as P  # noqa: E402

NAME = 'definition'
LANGS = ('zh',)                                  # the report deck is Chinese
W, H = 300.0, 134.0

LABELS = {
    'zh': {
        'top': '前提条件从 SQL 结构自动推导', 'top_note': '发布时随指标定义一起保存，每个前提对应一条校验 SQL',
        'heads': ('SQL 结构', '隐含的数据假设', '前提条件'),
        'rows': (('对事实表求和', '`SUM(ss_net_paid) FROM store_sales`', '粒度：一行对应一笔销售明细',
                  '主键唯一', '行数 = 不同主键数'),
                 ('关联日期维表，按月过滤', '`JOIN date_dim … WHERE d_moy = 9`', '关联基数 N:1：一个日期键对应一天',
                  '维表主键唯一', '`d_date_sk` 不重复'),
                 ('内连接', '`ON ss_sold_date_sk = d_date_sk`', '参照完整性：日期键都能关联到维表',
                  '参照完整性', '关联不上的行不超过学习时'),
                 ('改写为日期键范围过滤（v2）', '`ss_sold_date_sk BETWEEN …`', '连续性：每月的日期键连续',
                  '日期键连续', '每月日期键无空缺')),
        'bottom': '前提条件能识别出有害的写入', 'bottom_note': '三种写入均基于同一份初始数据，查询 9 月门店营业额',
        'writes': (('增量加载', '+27,095 行，新小票号'), ('数据更正', '+65,915 行，旧行保留、标记为非当前'),
                   ('重复加载', '+110,165 行，同一批数据重复加载')),
        'write_head': '写入类型', 'grain': '主键唯一',
        'grain_cells': (('通过', 'ok'), ('1,065,915 行，1,000,000 个主键', 'fail'), ('1,110,165 行，1,000,000 个主键', 'fail')),
        'others': '其余 3 个前提', 'others_cell': '通过',
        'answer': '原 SQL 的结果', 'answer_sub': '9 月，SQL 不报错',
        'answers': (('2613.9 万', '结果正确', 'ok'), ('1430.1 万', '应为 1293.3 万', 'fail'),
                    ('2613.9 万', '应为 1307.0 万', 'fail')),
        'verdict': '结论', 'verdicts': (('可以继续使用', P.PUBLISH_TEXT), ('不能直接使用', P.FAIL_TEXT),
                                       ('不能直接使用', P.FAIL_TEXT)),
    },
}

ROW0, ROW_H, ROW_P = 17.0, 12.0, 13.0             # the four structure rows
C1, C2, C3 = (4.0, 120.0), (132.0, 76.0), (216.0, 80.0)   # (left, width) of the three columns
TAB = (4.0, 79.0, 292.0, 53.0)                    # the matrix of writes
LABEL_W = 70.0


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def section(y, title, note):
        rect(4.0, y - 4.6, 1.1, 5.4, P.USE)
        tw = text(7.2, y, title, TITLE, P.USE_TEXT, 'bold')
        text(11.0 + tw, y, note, NOTE, MUTED)

    # Top: from the SQL's structure to the conditions ------------------------------------------
    section(6.4, L['top'], L['top_note'])
    for k, ((x, w), head) in enumerate(zip((C1, C2, C3), L['heads'])):   # reading order 1-3 across the columns
        step(s, x + 4.6, 14.0 - .34 * NOTE * PT, k + 1, P.USE, r=2.6)
        text(x + 8.8, 14.0, head, NOTE, INK, 'bold')
    for k, (part, code, prop, cond, gloss) in enumerate(L['rows']):
        y = ROW0 + ROW_P * k
        v2 = k == 3
        x, w = C1
        rect(x, y, w, ROW_H, WHITE, EDGE, .3, r=1.0)
        text(x + 2.4, y + 4.8, part, NOTE, INK, 'bold', width=w - 4.8)
        example(s, x + 2.4, y + 10.2, code, width=w - 4.8, size=NOTE - 1, color=P.EXAMPLE)
        x, w = C2
        rect(x, y, w, ROW_H, P.FIELD, None, r=1.0)
        text(x + 2.4, baseline(y + ROW_H / 2, NOTE), prop, NOTE, INK, width=w - 4.8)
        x, w = C3
        rect(x, y, w, ROW_H, P.MAINT_PALE if v2 else P.USE_PALE, None, r=1.0)    # v2's premise came from optimization
        text(x + 2.4, y + 4.8, cond, NOTE, P.MAINT_TEXT if v2 else P.USE_TEXT, 'bold', width=w - 4.8)
        text(x + 2.4, y + 10.0, gloss, NOTE - 1, MUTED, width=w - 4.8)
        ym = y + ROW_H / 2
        for (l, lw), r in ((C1, C2), (C2, C3)):
            route([(l + lw + .6, ym), (r[0] - .4, ym)], P.USE, THIN, length=HEAD)

    # Bottom: the three writes, the conditions, and what the unchanged SQL returns ----------------
    section(TAB[1] - 4.2, L['bottom'], L['bottom_note'])
    x, y, w, h = TAB
    rect(*TAB, WHITE, P.PANEL, .45, r=1.6)
    cw = (w - LABEL_W) / 3
    cols = [x + LABEL_W + cw * k for k in range(3)]
    heights = (14.0, 10.0, 9.0, 11.0, 9.0)        # header, grain, the other conditions, answers, verdict
    tops = [y]
    for hh in heights[:-1]:
        tops.append(tops[-1] + hh)
    if abs(tops[-1] + heights[-1] - (y + h)) > .01:
        raise ValueError('matrix rows do not fill the box')
    for t in tops[1:]:
        s.line(x + 2.0, t, x + w - 2.0, t, RULE, .3)
    for cx in cols:
        s.line(cx, y + 2.0, cx, y + h - 2.0, RULE, .3)
    rect(x + .4, tops[1], LABEL_W - .4, heights[1], P.PENDING_PALE, None)   # the condition that decides

    def cell_text(k, row, line, color=INK, style='sans', dy=0.0, size=NOTE):
        cx = cols[k] + 3.0
        return text(cx, baseline(tops[row] + heights[row] / 2 + dy, size), line, size, color, style,
                    width=cw - 9.0)

    for k, (name, what) in enumerate(L['writes']):
        cell_text(k, 0, name, INK, 'bold', -2.6)
        cell_text(k, 0, what, MUTED, dy=3.0, size=NOTE - 1)
    # Reading order 4-7 down the label column: the writes, the checks, what the SQL returns, the verdict.
    lx = x + 10.6
    for n, row in ((4, 0), (5, 1), (6, 3), (7, 4)):
        step(s, x + 5.6, tops[row] + heights[row] / 2, n, P.USE, r=2.6)
    text(lx, baseline(tops[0] + heights[0] / 2, NOTE), L['write_head'], NOTE, INK, 'bold')
    text(lx, baseline(tops[1] + heights[1] / 2, NOTE), L['grain'], NOTE, P.PENDING_TEXT, 'bold')
    text(lx, baseline(tops[2] + heights[2] / 2, NOTE), L['others'], NOTE, INK)
    text(lx, baseline(tops[3] + heights[3] / 2 - 2.4, NOTE), L['answer'], NOTE, INK)
    text(lx, baseline(tops[3] + heights[3] / 2 + 2.8, NOTE - 1), L['answer_sub'], NOTE - 1, MUTED)
    text(lx, baseline(tops[4] + heights[4] / 2, NOTE), L['verdict'], NOTE, INK, 'bold')
    for k in range(3):
        line, kind = L['grain_cells'][k]
        cell_text(k, 1, line, P.FAIL_TEXT if kind == 'fail' else INK)
        mark(s, cols[k] + cw - 4.0, tops[1] + heights[1] / 2, kind, P.OK, P.FAIL)
        cell_text(k, 2, L['others_cell'], MUTED)
        mark(s, cols[k] + cw - 4.0, tops[2] + heights[2] / 2, 'ok', P.OK, P.FAIL)
        value, note, kind = L['answers'][k]
        vw = cell_text(k, 3, value, INK, 'bold')
        text(cols[k] + 3.0 + vw + 2.4, baseline(tops[3] + heights[3] / 2, NOTE - 1), note, NOTE - 1,
             MUTED if kind == 'ok' else P.FAIL_TEXT, width=cw - 11.4 - vw)
        mark(s, cols[k] + cw - 4.0, tops[3] + heights[3] / 2, kind, P.OK, P.FAIL)
        verdict, color = L['verdicts'][k]
        cell_text(k, 4, verdict, color, 'bold')


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
