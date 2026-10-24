"""MAVRA between agents and the database: share exploration, save tokens/time.

The left side repeats schema/value/join exploration for three sessions; the
right side makes the shared memory layer the central object, with one
publication path and reuse paths for later agents. Database changes feed a
small upkeep path inside the layer. The bottom reports the population
study's measured token saving and end-to-end speedup relative to no memory;
values and population size are read from the paper's generated macros.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import PT  # noqa: E402
import style  # noqa: E402
from style import ACC, ACC_DK, ACC_PALE, AMBER, EDGE, FACE, INK, MUTED, RULE, WHITE  # noqa: E402

NAME = 'metric-record'
W, H = style.COLUMN, 66.0
TITLE, BODY, SMALL = 7.6, 7.0, 6.7
LEARN, LEARN_PALE = '#7A68B0', '#F0ECF8'
PP = style.macros('population')
AGENTS, TOKEN_SAVE, SPEEDUP = (PP[k] for k in ('PpAgents', 'PpMavraTokSaveNone', 'PpMavraSpeedupNone'))

LABELS = {
    'en': {
        'alone': '(a) Separate sessions', 'shared': '(b) Shared memory',
        'questions': ('A: Mar?', 'B: Sep?', 'C: Q3?'),
        'explore': 'repeat exploration', 'publish': 'publish', 'reuse': 'reuse',
        'memory': 'MAVRA · shared memory', 'fields': 'grain · filters · joins',
        'upkeep': 'validate · maintain', 'updates': 'updates', 'db': 'Database',
        'study': f'TPC-DS · {AGENTS} agents · vs. no memory',
        'tokens': f'{TOKEN_SAVE}% fewer tokens', 'time': f'{SPEEDUP}× speedup',
    },
    'zh': {
        'alone': '(a) 各自探索', 'shared': '(b) 共享记忆',
        'questions': ('A: 三月?', 'B: 九月?', 'C: Q3?'),
        'explore': '重复探索', 'publish': '发布', 'reuse': '复用',
        'memory': 'MAVRA · 共享记忆层', 'fields': '粒度 · 过滤 · 连接',
        'upkeep': '验证 · 维护', 'updates': '更新', 'db': '数据库',
        'study': f'TPC-DS · {AGENTS} 个智能体 · 相对无记忆',
        'tokens': f'token 减少 {TOKEN_SAVE}%', 'time': f'加速 {SPEEDUP} 倍',
    },
}


def draw(s, lang):
    L = LABELS[lang]

    def label(x, y, value, size=BODY, color=INK, weight='sans', align='left', width=None):
        return s.text(x, y + .34 * size * PT, value, size, color, weight, align, width)

    def arrow(points, color=ACC, width=.22, heads='end', dash=None):
        s.route(points, color, width, heads=heads, dash=dash, radius=.65, length=.9)

    def schema(x, y):
        s.rect(x - 1.45, y - 1.3, 2.9, 2.6, WHITE, LEARN, .2, r=.15)
        s.line(x - 1.45, y - .35, x + 1.45, y - .35, LEARN, .17)
        s.line(x - .4, y - .35, x - .4, y + 1.3, LEARN, .17)
        s.line(x - 1.45, y + .5, x + 1.45, y + .5, LEARN, .17)

    def probe(x, y):
        s.circle(x - .3, y - .2, 1.05, WHITE, LEARN, .23)
        s.line(x + .4, y + .55, x + 1.4, y + 1.5, LEARN, .35)

    def join(x, y):
        s.rect(x - 1.6, y - 1.3, 1.1, 1.4, WHITE, LEARN, .18, r=.12)
        s.rect(x + .5, y - .1, 1.1, 1.4, WHITE, LEARN, .18, r=.12)
        s.line(x - .5, y - .6, x + .9, y - .6, LEARN, .2)
        s.line(x + .9, y - .6, x + .9, y - .1, LEARN, .2)

    def person(x, y, color):
        s.circle(x, y - 1.1, .9, color)
        s.rect(x - 1.5, y + .15, 3, 1.8, color, None, r=.65)

    def database(x, y, w, h):
        # A cylinder makes the common database visually distinct from memory.
        s.rect(x, y + 1.1, w, h - 2.2, FACE, EDGE, .2)
        s.curve((x, y + h - 1.1), (x, y + h + .4), (x + w, y + h + .4),
                (x + w, y + h - 1.1), EDGE, .2)
        s.line(x, y + h - 2, x, y + h - 1.1, EDGE, .2)
        s.line(x + w, y + h - 2, x + w, y + h - 1.1, EDGE, .2)
        s.curve((x, y + 1.1), (x, y - .4), (x + w, y - .4), (x + w, y + 1.1), EDGE, .2)
        s.curve((x, y + 1.1), (x, y + 2.6), (x + w, y + 2.6), (x + w, y + 1.1), EDGE, .2)

    label(.8, 3, L['alone'], TITLE, INK, 'bold', width=28)
    label(33.2, 3, L['shared'], TITLE, ACC_DK, 'bold', width=49)
    s.line(29.4, 6.3, 29.4, 45.8, RULE, .16)

    # No shared layer: every session takes its own full exploration path.
    for x, agent in zip((5.0, 13.2, 21.4), 'ABC'):
        person(x, 9, LEARN)
        label(x, 14, agent, BODY, LEARN, 'bold', 'center')
        arrow([(x, 16.2), (x, 20.0)], LEARN)
        s.rect(x - 3.1, 20.5, 6.2, 18.6, LEARN_PALE, LEARN, .18, r=.7)
        schema(x, 24.0)
        probe(x, 29.8)
        join(x, 35.6)
        arrow([(x, 39.7), (x, 47.5)], LEARN, heads='both')
    # White background separates the short label from the three arrows.
    s.rect(.8, 41.1, 25.7, 3.3, WHITE)
    label(13.6, 42.7, L['explore'], SMALL, LEARN, align='center', width=25.7)

    # Agents sit above one prominent layer; their requests produce different
    # SQL from the same learned definition, without the repeated icon stacks.
    centers = (40.6, 58.2, 75.8)
    for x, q in zip(centers, L['questions']):
        person(x, 8.6, ACC)
        s.rect(x - 7.3, 12, 14.6, 5.0, FACE, RULE, .17, r=.5)
        label(x, 14.5, q, BODY, INK, align='center', width=13.7)
    arrow([(40.6, 17.6), (40.6, 23.4)], LEARN, .3)
    label(36.0, 20.5, L['publish'], SMALL, LEARN, align='center', width=8)
    for x in centers[1:]:
        arrow([(x, 17.6), (x, 23.4)], ACC, .3, heads='both')
    label(66.9, 20.5, L['reuse'], SMALL, ACC_DK, align='center', width=11)

    s.rect(32.6, 24, 50.6, 16.5, ACC_PALE, ACC, .32, r=.8)
    label(57.9, 27.2, L['memory'], 8.2, ACC_DK, 'bold', 'center', 47)
    label(57.9, 31.9, 'revenue = SUM(paid)', BODY, INK, 'code', 'center', 47)
    label(57.9, 35.1, L['fields'], SMALL, INK, align='center', width=47)
    s.line(34.2, 37, 81.6, 37, '#B2CCE9', .15)
    s.poly([(43.2, 38.7), (43.7, 39.2), (44.7, 38.1)], None, ACC, .25, closed=False)
    label(57.9, 38.8, L['upkeep'], SMALL, MUTED, align='center', width=28)

    arrow([(55.1, 41.1), (55.1, 47.5)], ACC, .32, heads='both')
    label(58.1, 44.5, 'SQL', BODY, ACC_DK, width=9)
    arrow([(79.7, 47.5), (79.7, 41.1)], AMBER, .23, dash=(.8, .6))
    label(76.8, 44.5, L['updates'], SMALL, AMBER, align='right', width=12)
    database(.8, 48.2, 82.4, 6.8)
    label(42, 52.0, L['db'], 8.2, INK, 'bold', 'center')

    # Actual workload-level results, with their baseline and scope on the
    # figure. This is not a quantitative scale for the schematic above.
    label(42.3, 58.3, L['study'], SMALL, MUTED, align='center', width=81)
    label(21.3, 63, L['tokens'], 9.2, ACC_DK, 'bold', 'center', 40)
    label(64.2, 63, L['time'], 9.2, ACC_DK, 'bold', 'center', 38)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
