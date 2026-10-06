"""Figure: accuracy of agent B by data change and method, as a heatmap.

Rows are the twelve settings grouped by the condition they target, with what
each update does; columns are the nine methods. Cells carry the accuracy and
a neutral shade (blue stays reserved for MAVRA); a red corner marks settings
where at least 25% of the tasks used a stale definition. Data: the per-cell
counts in exp/2026-10-02-scenarios-ds/paper-results.json, aggregated the way
tools/paper-results.py does; row labels come from that script. Every value
the text prints (\\ScenAcc* in gen/numbers.tex) is checked.
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vecfig import measure  # noqa: E402
import style  # noqa: E402
from scenario_groups import KEY  # noqa: E402
from style import ACC, ACC_DK, INK, MUTED, RED, WHITE  # noqa: E402

NAME = 'scenario-changes'
W, H = style.TEXTWIDTH, 62.0
DATA = style.ROOT / 'exp/2026-10-02-scenarios-ds/paper-results.json'
STALE = .25                      # share of tasks that used a stale definition

_spec = importlib.util.spec_from_file_location('paper_results', style.ROOT / 'tools/paper-results.py')
paper_results = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paper_results)
PHASES, CLASSES = paper_results.PHASES, paper_results.CLASSES
MODES = paper_results.shown_modes()

HEAD = {  # column heads, two lines; abbreviations of the method names in Table 3
    'en': {'middle': ('No', 'sharing'), 'traj-global': ('Trajectory', 'retrieval'),
           'traj-verify': ('Traj. +', 'self-check'), 'metric-global-noguard': ('No', 'validation'),
           'metric-global-schema': ('Schema', 'change'), 'metric-global-revoke': ('Invalidate-', 'on-write'),
           'metric-global-def': ('Definition-', 'level'), 'metric-global-snap': ('', 'MAVRA'),
           'metric-global-exref': ('MAVRA,', 'G8 current'), 'metric-global': ('MAVRA', '(gold SQL)')},
    'zh': {'middle': ('', '不共享'), 'traj-global': ('', '轨迹检索'),
           'traj-verify': ('轨迹检索', '+ 自检'), 'metric-global-noguard': ('共享', '不验证'),
           'metric-global-schema': ('按模式', '变更失效'), 'metric-global-revoke': ('写入即', '失效'),
           'metric-global-def': ('', '定义级'), 'metric-global-snap': ('', 'MAVRA'),
           'metric-global-exref': ('MAVRA', '当前数据'), 'metric-global': ('MAVRA', '标准答案')},
}
TEXT = {
    'en': {'class': 'Class', 'change': 'Change', 'what': 'What the update does',
           'mean': 'Mean over the {} settings', 'scale': 'Accuracy (%)',
           'stale': 'At least 25% of the tasks used a stale definition'},
    'zh': {'class': '类别', 'change': '数据变化', 'what': '更新内容', 'mean': '{} 种情形平均',
           'scale': '正确率（%）', 'stale': '至少 25% 的题使用了过期定义'},
}
RAMP = [(0, '#F4F3F0'), (.5, '#CBC7C1'), (1, '#6E6A65')]   # neutral, light to dark
LABEL, CELL, HEADPT = 6.3, 6.3, 6.2    # font sizes, pt


def shade(v):
    for (a, ca), (b, cb) in zip(RAMP, RAMP[1:]):
        if v <= b:
            t = (v - a) / (b - a)
            rgb = [round(int(ca[i:i + 2], 16) * (1 - t) + int(cb[i:i + 2], 16) * t)
                   for i in (1, 3, 5)]
            return '#' + ''.join(f'{c:02X}' for c in rgb)
    return RAMP[-1][1]


def load():
    """Accuracy and stale share per (mode, phase), as tools/paper-results.py computes them."""
    data = json.loads(DATA.read_text(encoding='utf-8'))
    acc, stale = data['accuracy'], data['stale']
    models = sorted({key.split('|')[0] for key in acc})
    cells = {}
    for mode in MODES:
        for phase, *_ in PHASES:
            rates = [k / n for k, n in (acc.get(f'{m}|{mode}|{phase}', (0, 0)) for m in models) if n]
            s, n = stale[f'{mode}|{phase}']
            cells[mode, phase] = (sum(rates) / len(rates) if rates else None,
                                  n > 0 and s / n >= STALE)
    printed = style.macros('numbers')
    means = {}
    for mode in MODES:
        vals = [cells[mode, p][0] for p, *_ in PHASES if cells[mode, p][0] is not None]
        means[mode] = sum(vals) / len(vals)
        style.agree(f'ScenAcc{KEY[mode]}', f'{100 * means[mode]:.0f}', printed[f'ScenAcc{KEY[mode]}'])
        for phase, *_ in PHASES:
            name = f'ScenAcc{KEY[mode]}{phase.capitalize()}'
            if name in printed:
                style.agree(name, f'{100 * cells[mode, phase][0]:.0f}', printed[name])
    return cells, means


def draw(s, lang):
    cells, means = load()
    T, text = TEXT[lang], s.text
    zh = lang == 'zh'
    rows = [(CLASSES[cls][zh], (zh_change if zh else en_change).replace('\\ ', ' '),
             zh_what if zh else en_what, phase, cls)
            for phase, cls, en_change, zh_change, en_what, zh_what in PHASES]
    col_class = max(measure(r[0], LABEL) for r in rows) + 2.2
    col_change = max(measure(r[1], LABEL) for r in rows) + 2.2
    col_what = max(measure(r[2], LABEL) for r in rows) + 2.6
    x_change, x_what, x_cells = col_class, col_class + col_change, col_class + col_change + col_what
    cw = (W - x_cells) / len(MODES)

    head_bottom, pitch, gap = 9.6, 3.05, .8
    # Column heads: method swatch and two-line name.
    for j, mode in enumerate(MODES):
        cx = x_cells + cw * (j + .5)
        _, color = style.method(mode, lang)
        s.rect(cx - .8, .6, 1.6, 1.6, color, None, r=.2)
        first, second = HEAD[lang][mode]
        mavra = mode == 'metric-global-snap'
        for line, y in ((first, 5.4), (second, 8.3)):
            if line:
                text(cx, y, line, HEADPT, ACC_DK if mavra else INK, 'bold' if mavra else 'sans',
                     'center', width=cw - .4)
    for x, label in ((0, T['class']), (x_change, T['change']), (x_what, T['what'])):
        text(x, 8.3, label, LABEL, INK, 'bold')
    s.line(0, head_bottom, W, head_bottom, MUTED, .2)

    y, prev = head_bottom + .7, None
    for cls_label, change, what, phase, cls in rows:
        if prev is not None and cls != prev:
            y += gap
        base = y + pitch / 2 + .8
        if cls != prev:
            text(0, base, cls_label, LABEL, INK, width=col_class - .8)
        prev = cls
        text(x_change, base, change, LABEL, INK, width=col_change - .8)
        text(x_what, base, what, LABEL, MUTED, width=col_what - .8)
        for j, mode in enumerate(MODES):
            v, stale = cells[mode, phase]
            x0 = x_cells + cw * j
            if v is None:
                text(x0 + cw / 2, base, '–', CELL, MUTED, align='center')
                continue
            s.rect(x0 + .3, y + .2, cw - .6, pitch - .4, shade(v), None, r=.35)
            text(x0 + cw / 2, base, f'{100 * v:.0f}', CELL, WHITE if v >= .8 else INK,
                 align='center')
            if stale:
                tx, ty = x0 + cw - .3, y + .2
                s.poly([(tx - 1.5, ty), (tx, ty), (tx, ty + 1.5)], RED, None)
        y += pitch

    s.line(0, y + .45, W, y + .45, MUTED, .16)
    base = y + .45 + pitch / 2 + .9
    text(0, base, T['mean'].format(len(PHASES)), LABEL, INK, 'bold')
    for j, mode in enumerate(MODES):
        mavra = mode == 'metric-global-snap'
        text(x_cells + cw * (j + .5), base, f'{100 * means[mode]:.0f}', CELL,
             ACC_DK if mavra else INK, 'bold', 'center')
    table_bottom = y + .45 + pitch + .3
    s.line(0, table_bottom, W, table_bottom, MUTED, .2)

    # MAVRA's column framed in its color.
    j = MODES.index('metric-global-snap')
    s.rect(x_cells + cw * j + .05, .2, cw - .1, table_bottom - .2, None, ACC, .3, r=.6)

    # Legend: the shade ramp and the stale mark.
    ly = table_bottom + 3.4
    text(0, ly + .55, T['scale'], LABEL, MUTED)
    rx = measure(T['scale'], LABEL) + 1.8 + measure('0', LABEL) + 1.0
    steps = 40
    for k in range(steps):
        s.rect(rx + k * .6, ly - 1.2, .62, 1.9, shade(k / (steps - 1)), None)
    for v, align in ((0, 'right'), (100, 'left')):
        text(rx - .8 if v == 0 else rx + steps * .6 + .8, ly + .55, str(v), LABEL, MUTED,
             align=align)
    sx = rx + steps * .6 + 7.5
    s.rect(sx, ly - 1.2, 3.2, 1.9, shade(.6), None, r=.3)
    s.poly([(sx + 3.2 - 1.5, ly - 1.2), (sx + 3.2, ly - 1.2), (sx + 3.2, ly + .3)], RED, None)
    text(sx + 4.4, ly + .55, T['stale'], LABEL, MUTED)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
