"""Parts shared by the report deck's three run figures (run_publish, run_use, run_maintain).

The run figures follow the look of the deck's view figures (structure.py, definition.py,
process.py): hand-placed boxes sized to their text, a section bar with a title and a
muted note, tags and pills in the responsibility colours of deckpal.py, numbered
badges for the reading order, brown 例 lines for recorded values. Coordinates are
millimetres from the top-left; font sizes are points.
"""
from vecfig import PT, measure
from parts import NOTE, TITLE, baseline, example, mark, step
from style import INK, MUTED, WHITE
import deckpal as P

SMALL = NOTE - 1                                  # 11 pt
TINY = NOTE - 2                                   # 10 pt
CODE_FILL = '#F5F6F8'


def section(s, x, y, title, note=None, color=P.USE, text_color=P.USE_TEXT):
    """A section heading: a short bar, the bold title, and a muted note after it; y is the baseline."""
    s.rect(x, y - 4.6, 1.1, 5.4, color)
    tw = s.text(x + 3.2, y, title, TITLE, text_color, 'bold')
    if note:
        s.text(x + 7.0 + tw, y, note, NOTE, MUTED)
    return tw


def pill(s, x, yc, label, fill, color=WHITE, size=SMALL, style='bold', edge=None, dash=None, h=5.8):
    """A rounded label; (x, yc) its left edge and vertical centre. Returns its width."""
    w = measure(label, size, style) + 4.4
    s.rect(x, yc - h / 2, w, h, fill, edge, .35, r=h / 2 if edge is None else 1.4, dash=dash)
    s.text(x + 2.2, baseline(yc, size), label, size, color, style)
    return w


def pill_width(label, size=SMALL, style='bold'):
    return measure(label, size, style) + 4.4


def panel(s, b, edge=P.PANEL, fill=WHITE, sw=.45, dash=None):
    s.rect(*b, fill, edge, sw, r=1.6, dash=dash)


def headed(s, b, title, n=None, color=P.USE, tag_label=None, edge=P.PANEL, fill=WHITE, title_color=INK,
           sw=.45, dash=None, size=TITLE):
    """A box with an optional step badge or tag before a bold title. Returns the x where the title ends."""
    x, y, w, h = b
    panel(s, b, edge, fill, sw, dash)
    tx = x + 3.0
    if n is not None:
        step(s, x + 5.8, y + 6.4, n, color, r=3.0)
        tx = x + 11.2
    if tag_label:
        tx += pill(s, tx, y + 6.4, tag_label, color) + 2.6
    return tx + s.text(tx, baseline(y + 6.4, size), title, size, title_color, 'bold', width=x + w - 2.5 - tx)


def check(s, x, y, label, kind='ok', size=NOTE, color=INK, style='sans', width=None):
    """A tick or cross and a label on baseline y; returns the width used."""
    mark(s, x + 1.4, y - .34 * size * PT - .1, kind, P.OK, P.FAIL)
    return 4.6 + s.text(x + 4.6, y, label, size, color, style, width=None if width is None else width - 4.6)


def ex(s, x, y, label, width=None, size=NOTE):
    """A brown 例 line (a recorded value)."""
    return example(s, x, y, label, width=width, size=size, color=P.EXAMPLE)


def badge(s, x, y, n, color, r=2.6):
    step(s, x, y, n, color, r=r)


def code_panel(s, b, lines, size=SMALL, pitch=4.9, fill=CODE_FILL, edge='#D9DDE3', first=5.4):
    """SQL in the code font; a line is a string or a list of (text, colour) runs."""
    x, y, w, h = b
    s.rect(*b, fill, edge, .3, r=1.2)
    yy = y + first
    for line in lines:
        runs = [(line, INK)] if isinstance(line, str) else line
        total = sum(measure(t, size, 'code') for t, _ in runs)
        if total > w - 4.0:
            raise ValueError(f'{"".join(t for t, _ in runs)!r} is {total:.1f} mm wide; {w - 4.0:.1f} mm available')
        xx = x + 2.4
        for t, c in runs:
            xx += s.text(xx, yy, t, size, c, 'code')
        yy += pitch
    if yy - pitch + 2.0 > y + h + 1e-6:
        raise ValueError(f'code panel needs {yy - pitch + 2.0 - y:.1f} mm; it is {h:.1f} mm high')


def bubble(s, b, fill, edge, tail_x=None, tail_up=False):
    """A speech bubble: a rounded box with a small tail at tail_x on its bottom (or top) edge."""
    x, y, w, h = b
    s.rect(*b, fill, edge, .35, r=1.6)
    if tail_x is not None:
        if tail_up:
            s.poly([(tail_x - 2.2, y + .2), (tail_x, y - 2.6), (tail_x + 2.2, y + .2)], fill, None)
            s.line(tail_x - 2.2, y, tail_x, y - 2.6, edge, .35)
            s.line(tail_x, y - 2.6, tail_x + 2.2, y, edge, .35)
        else:
            s.poly([(tail_x - 2.2, y + h - .2), (tail_x, y + h + 2.6), (tail_x + 2.2, y + h - .2)], fill, None)
            s.line(tail_x - 2.2, y + h, tail_x, y + h + 2.6, edge, .35)
            s.line(tail_x, y + h + 2.6, tail_x + 2.2, y + h, edge, .35)


def window(s, b, title, right=None, fill=WHITE, edge='#C9CED6', bar='#EEF0F4'):
    """A window-like panel: a title bar with three dots, for a log of tool calls."""
    x, y, w, h = b
    s.rect(*b, fill, edge, .4, r=1.6)
    s.rect(x + .2, y + .2, w - .4, 7.0, bar, None, r=1.4)
    s.rect(x + .2, y + 4.0, w - .4, 3.2, bar, None)
    for k, c in enumerate(('#E8796B', '#E9B949', '#6CBF7A')):
        s.circle(x + 4.0 + 3.6 * k, y + 3.7, 1.05, c)
    s.text(x + 16.0, baseline(y + 3.7, SMALL), title, SMALL, INK, 'bold')
    if right:
        s.text(x + w - 3.0, baseline(y + 3.7, TINY), right, TINY, MUTED, align='right')
