"""Vector drawing kit for the paper's figures.

Coordinates are millimetres from the top-left corner of the figure; line
widths and arrow sizes are millimetres too, font sizes are points. Output is
a ReportLab PDF in which every glyph is an outline, so the figure embeds no
fonts and looks the same in pdfLaTeX, XeLaTeX and every viewer.

Text uses the acmart fonts: Linux Biolinum for labels, Libertine for math
letters, Inconsolata zi4 (the paper's \\code font) for code, with Noto Sans
CJK SC as the fallback for Chinese. Plain text is laid out with fontTools
(cmap, advances, GPOS pair kerning). Segments in $...$ are laid out by matplotlib's MathText with
Libertine letters and STIX for missing symbols; segments in `...` use the
code font. Both kinds share one baseline, so a label can mix them freely.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache

os.environ.setdefault('MPLBACKEND', 'Agg')

import matplotlib as mpl
import numpy as np
from fontTools.agl import toUnicode
from fontTools.pens.basePen import BasePen
from fontTools.t1Lib import T1Font
from fontTools.ttLib import TTFont
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.ft2font import LoadFlags
from matplotlib.mathtext import MathTextParser
from matplotlib.path import Path as MplPath
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as rl_canvas

MM = 72 / 25.4          # points per millimetre
PT = 25.4 / 72          # millimetres per point
NONZERO = getattr(rl_canvas, 'FILL_NON_ZERO', 1)


# ---------------------------------------------------------------- fonts

def _kpse(name):
    path = subprocess.run(['kpsewhich', name], capture_output=True,
                          text=True).stdout.strip()
    if not path:
        raise SystemExit(f'kpsewhich cannot find {name}; install the TeX '
                         'libertine and inconsolata fonts')
    return path


def _fc(family, style):
    out = subprocess.run(['fc-match', '-f', '%{file}\n%{index}',
                          f'{family}:style={style}'],
                         capture_output=True, text=True).stdout.split('\n')
    return out[0], int(out[1] or 0)


class Font:
    """One face, loaded on first use: outlines, advances, GPOS kerning.

    OpenType/TrueType faces (also inside a .ttc) and Type 1 .pfb files work;
    a Type 1 face maps characters through its glyph names and has no kerning.
    """

    def __init__(self, locate, family=None):
        self._locate, self._family, self.glyphs = locate, family, None

    def _load(self):
        if self.glyphs is not None:
            return
        path, index = self._locate()
        self.outlines = {}
        self.type1 = path.endswith('.pfb')
        if self.type1:
            self.glyphs = T1Font(path).getGlyphSet()
            self.upm = 1000
            self.cmap = {}
            for name in self.glyphs:
                char = toUnicode(name)
                if len(char) == 1:
                    self.cmap.setdefault(ord(char), name)
            self.kern = lambda a, b: 0
            return
        tt = TTFont(path, fontNumber=index, lazy=True)
        name = tt['name'].getDebugName(1)
        if self._family and name != self._family:
            raise SystemExit(f'{path} face {index} is {name!r}, '
                             f'expected {self._family!r}')
        self.upm = tt['head'].unitsPerEm
        self.cmap = tt.getBestCmap()
        self.hmtx = tt['hmtx']
        self.glyphs = tt.getGlyphSet()
        self.kern = _pair_kerning(tt)

    def has(self, ch):
        self._load()
        return ord(ch) in self.cmap

    def outline(self, glyph):
        if glyph not in self.outlines:
            pen = _Recorder(self.glyphs)
            self.glyphs[glyph].draw(pen)
            self.outlines[glyph] = tuple(pen.ops)
        return self.outlines[glyph]

    def advance(self, glyph):
        if self.type1:
            self.outline(glyph)              # a Type 1 width is known once drawn
            return self.glyphs[glyph].width
        return self.hmtx[glyph][0]


class _Recorder(BasePen):
    """Glyph outline as M/L/C/Z commands; quadratics become cubics."""

    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.ops = []

    def _moveTo(self, p):
        self.ops.append(('M', *p))

    def _lineTo(self, p):
        self.ops.append(('L', *p))

    def _curveToOne(self, p1, p2, p3):
        self.ops.append(('C', *p1, *p2, *p3))

    def _closePath(self):
        self.ops.append(('Z',))

    _endPath = _closePath


def _pair_kerning(tt):
    """x-advance adjustment for a glyph pair from the GPOS 'kern' feature."""
    if 'GPOS' not in tt or not tt['GPOS'].table.FeatureList:
        return lambda a, b: 0
    table = tt['GPOS'].table
    indices = sorted({i for rec in table.FeatureList.FeatureRecord
                      if rec.FeatureTag == 'kern'
                      for i in rec.Feature.LookupListIndex})
    lookups = []
    for index in indices:
        lookup = table.LookupList.Lookup[index]
        subtables = []
        for sub in lookup.SubTable:
            kind = lookup.LookupType
            if kind == 9:
                kind, sub = sub.ExtensionLookupType, sub.ExtSubTable
            if kind != 2:
                continue
            if sub.Format == 1:
                pairs = {}
                for first, pairset in zip(sub.Coverage.glyphs, sub.PairSet):
                    pairs[first] = {r.SecondGlyph: _xadv(r.Value1)
                                    for r in pairset.PairValueRecord}
                subtables.append((1, pairs))
            else:
                subtables.append((2, (set(sub.Coverage.glyphs),
                                      sub.ClassDef1.classDefs,
                                      sub.ClassDef2.classDefs,
                                      sub.Class1Record)))
        lookups.append(subtables)

    @lru_cache(maxsize=None)
    def kern(a, b):
        total = 0
        for subtables in lookups:
            for fmt, data in subtables:
                if fmt == 1:
                    if a in data and b in data[a]:
                        total += data[a][b]
                        break
                else:
                    cover, cd1, cd2, records = data
                    if a in cover:
                        cell = records[cd1.get(a, 0)].Class2Record[cd2.get(b, 0)]
                        total += _xadv(cell.Value1)
                        break
        return total
    return kern


def _xadv(value):
    return (getattr(value, 'XAdvance', 0) or 0) if value is not None else 0


_TEX = {
    'biolinum': 'LinBiolinum_R.otf', 'biolinum-bold': 'LinBiolinum_RB.otf',
    'libertine': 'LinLibertine_R.otf', 'libertine-italic': 'LinLibertine_RI.otf',
    'libertine-bold': 'LinLibertine_RB.otf', 'inconsolata': 'Inconsolata-zi4r.pfb',
}
FONTS = {key: Font(lambda f=file: (_kpse(f), 0)) for key, file in _TEX.items()}
FONTS['cjk'] = Font(lambda: _fc('Noto Sans CJK SC', 'Regular'), 'Noto Sans CJK SC')
FONTS['cjk-bold'] = Font(lambda: _fc('Noto Sans CJK SC', 'Bold'), 'Noto Sans CJK SC')

# Text styles: the first font that has a character draws it.
STYLES = {
    'sans': ('biolinum', 'cjk'),
    'bold': ('biolinum-bold', 'cjk-bold'),
    'serif': ('libertine', 'cjk'),
    'code': ('inconsolata', 'cjk'),
}


# ----------------------------------------------------------------- math

_MATH_READY = False
_PARSER = MathTextParser('path')
_REF = 100.0    # layout size; keeps MathText's integer rounding below 1% em


def _math_fonts():
    global _MATH_READY
    if _MATH_READY:
        return
    for key in ('libertine', 'libertine-italic', 'libertine-bold', 'biolinum'):
        font_manager.fontManager.addfont(_kpse(_TEX[key]))
    mpl.rcParams.update({
        'mathtext.fontset': 'custom',
        'mathtext.rm': 'Linux Libertine O',
        'mathtext.it': 'Linux Libertine O:italic',
        'mathtext.bf': 'Linux Libertine O:bold',
        'mathtext.sf': 'Linux Biolinum O',
        'mathtext.cal': 'Linux Libertine O:italic',
        'mathtext.fallback': 'stix',
    })
    _MATH_READY = True


@dataclass(frozen=True)
class _Math:
    width: float        # points
    glyphs: tuple       # per glyph: M/L/C/Z commands in points, baseline y = 0
    rects: tuple        # fraction bars and similar rules


@lru_cache(maxsize=None)
def _math(expression, size):
    _math_fonts()
    parsed = _PARSER.parse(expression, dpi=72,
                           prop=FontProperties(size=_REF, math_fontfamily='custom'))
    k = size / _REF
    glyphs = []
    for font, glyph_size, code, ox, oy in parsed.glyphs:
        font.set_size(float(glyph_size), 72)
        font.load_char(int(code), flags=LoadFlags.NO_HINTING)
        vertices, codes = font.get_path()
        if len(vertices) == 0:
            continue
        v = np.asarray(vertices, dtype=float).copy()
        v[:, 0] += ox
        v[:, 1] += oy
        glyphs.append(_mpl_commands(MplPath(v * k, np.asarray(codes))))
    rects = tuple(tuple(k * float(t) for t in r) for r in parsed.rects)
    return _Math(parsed.width * k, tuple(glyphs), rects)


def _mpl_commands(path):
    out, current, start = [], (0.0, 0.0), (0.0, 0.0)
    for v, code in path.iter_segments(curves=True, simplify=False):
        v = [float(t) for t in v]
        if code == MplPath.MOVETO:
            current = start = (v[0], v[1])
            out.append(('M', *current))
        elif code == MplPath.LINETO:
            current = (v[0], v[1])
            out.append(('L', *current))
        elif code == MplPath.CURVE3:
            (sx, sy), (qx, qy, ex, ey) = current, v
            out.append(('C', sx + 2 * (qx - sx) / 3, sy + 2 * (qy - sy) / 3,
                        ex + 2 * (qx - ex) / 3, ey + 2 * (qy - ey) / 3, ex, ey))
            current = (ex, ey)
        elif code == MplPath.CURVE4:
            out.append(('C', *v))
            current = (v[4], v[5])
        elif code == MplPath.CLOSEPOLY:
            out.append(('Z',))
            current = start
    return tuple(out)


# ------------------------------------------------------------- layout

_SEGMENT = re.compile(r'(\$[^$]+\$|`[^`]+`)')


def _layout(s, size, style):
    """Glyph runs for a label: (x offset pt, kind, payload); total width pt."""
    items, x = [], 0.0
    for part in _SEGMENT.split(s):
        if not part:
            continue
        if part[0] == '$':
            m = _math(part, size)
            items.append((x, 'math', m))
            x += m.width
            continue
        fonts = STYLES['code' if part[0] == '`' else style]
        text = part[1:-1] if part[0] == '`' else part
        prev = None
        for ch in text:
            font = next((FONTS[f] for f in fonts if FONTS[f].has(ch)), None)
            if font is None:
                raise ValueError(f'no font has {ch!r} (U+{ord(ch):04X}) in {s!r}')
            glyph = font.cmap[ord(ch)]
            k = size / font.upm
            if prev and prev[0] is font:
                x += font.kern(prev[1], glyph) * k
            items.append((x, 'glyph', (font, glyph, k)))
            x += font.advance(glyph) * k
            prev = (font, glyph)
    return items, x


def measure(s, size, style='sans'):
    """Advance width of a label, in millimetres."""
    return _layout(s, size, style)[1] * PT


# -------------------------------------------------------------- sheet

def color(value):
    return HexColor(value) if isinstance(value, str) else value


class Sheet:
    """A figure page with top-left millimetre coordinates."""

    def __init__(self, path, width, height):
        self.W, self.H = width, height
        self.c = rl_canvas.Canvas(str(path), pagesize=(width * MM, height * MM),
                                  invariant=1, pageCompression=1)
        self.c.setAuthor('')
        self.c.setCreator('')
        self.c.setLineJoin(1)
        self.c.setLineCap(1)

    def save(self):
        self.c.showPage()
        self.c.save()

    def _xy(self, x, y):
        return x * MM, (self.H - y) * MM

    def _style(self, fill, stroke, sw, dash=None):
        c = self.c
        if fill is not None:
            c.setFillColor(color(fill))
        if stroke is not None:
            c.setStrokeColor(color(stroke))
            c.setLineWidth(sw * MM)
        c.setDash([d * MM for d in dash] if dash else [])

    # Shapes -------------------------------------------------------------

    def rect(self, x, y, w, h, fill=None, stroke=None, sw=.15, r=0, dash=None):
        c = self.c
        c.saveState()
        self._style(fill, stroke, sw, dash)
        X, Y = self._xy(x, y + h)
        if r:
            c.roundRect(X, Y, w * MM, h * MM, r * MM,
                        fill=fill is not None, stroke=stroke is not None)
        else:
            c.rect(X, Y, w * MM, h * MM,
                   fill=fill is not None, stroke=stroke is not None)
        c.restoreState()

    def poly(self, points, fill=None, stroke=None, sw=.15, closed=True, dash=None):
        c = self.c
        c.saveState()
        self._style(fill, stroke, sw, dash)
        p = c.beginPath()
        p.moveTo(*self._xy(*points[0]))
        for pt in points[1:]:
            p.lineTo(*self._xy(*pt))
        if closed:
            p.close()
        c.drawPath(p, fill=fill is not None and closed, stroke=stroke is not None,
                   fillMode=NONZERO)
        c.restoreState()

    def line(self, x1, y1, x2, y2, stroke, sw=.15, dash=None):
        self.poly([(x1, y1), (x2, y2)], None, stroke, sw, closed=False, dash=dash)

    def curve(self, p0, p1, p2, p3, stroke, sw=.15, dash=None):
        """Cubic Bézier from p0 to p3 with control points p1 and p2."""
        c = self.c
        c.saveState()
        self._style(None, stroke, sw, dash)
        p = c.beginPath()
        p.moveTo(*self._xy(*p0))
        p.curveTo(*self._xy(*p1), *self._xy(*p2), *self._xy(*p3))
        c.drawPath(p, fill=0, stroke=1)
        c.restoreState()

    def marker(self, x, y, kind, size, fill, stroke=None, sw=.12):
        """Plot marker centred on (x, y); size is its width in mm."""
        r = size / 2
        if kind == 'circle':
            self.circle(x, y, r, fill, stroke, sw)
        elif kind == 'square':
            r *= .9
            self.rect(x - r, y - r, 2 * r, 2 * r, fill, stroke, sw)
        elif kind == 'triangle':
            r *= 1.15
            self.poly([(x, y - r), (x + .87 * r, y + .5 * r), (x - .87 * r, y + .5 * r)],
                      fill, stroke, sw)
        elif kind == 'diamond':
            self.poly([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill, stroke, sw)
        else:
            raise ValueError(f'unknown marker {kind!r}')

    def circle(self, x, y, r, fill=None, stroke=None, sw=.15):
        c = self.c
        c.saveState()
        self._style(fill, stroke, sw)
        c.circle(*self._xy(x, y), r * MM, fill=fill is not None,
                 stroke=stroke is not None)
        c.restoreState()

    def head(self, x, y, angle, fill, length=1.2):
        """Arrowhead with its tip at (x, y), pointing along angle (radians)."""
        ux, uy = math.cos(angle), math.sin(angle)
        half = .42 * length
        pts = [(x, y),
               (x - length * ux - half * uy, y - length * uy + half * ux),
               (x - .72 * length * ux, y - .72 * length * uy),
               (x - length * ux + half * uy, y - length * uy - half * ux)]
        self.poly(pts, fill, None)

    def route(self, points, stroke, sw=.2, heads='end', dash=None,
              radius=1.0, length=1.2):
        """Orthogonal polyline with rounded corners and exact arrowheads.

        heads is 'end', 'start', 'both' or None. The stroke stops inside each
        head so its cap never shows past the tip.
        """
        pts = [tuple(map(float, p)) for p in points]
        body = list(pts)
        if heads in ('end', 'both'):
            body[-1] = _towards(pts[-1], pts[-2], .7 * length)
        if heads in ('start', 'both'):
            body[0] = _towards(pts[0], pts[1], .7 * length)
        c = self.c
        c.saveState()
        self._style(None, stroke, sw, dash)
        p = c.beginPath()
        p.moveTo(*self._xy(*body[0]))
        for i in range(1, len(body) - 1):
            (ax, ay), (bx, by), (cx, cy) = body[i - 1], body[i], body[i + 1]
            la, lb = math.hypot(bx - ax, by - ay), math.hypot(cx - bx, cy - by)
            r = min(radius, la / 2, lb / 2)
            ix, iy = bx + (ax - bx) * r / la, by + (ay - by) * r / la
            ox, oy = bx + (cx - bx) * r / lb, by + (cy - by) * r / lb
            p.lineTo(*self._xy(ix, iy))
            p.curveTo(*self._xy(ix + (bx - ix) * .5523, iy + (by - iy) * .5523),
                      *self._xy(ox + (bx - ox) * .5523, oy + (by - oy) * .5523),
                      *self._xy(ox, oy))
        p.lineTo(*self._xy(*body[-1]))
        c.drawPath(p, fill=0, stroke=1)
        c.restoreState()
        if heads in ('end', 'both'):
            (ax, ay), (bx, by) = pts[-2], pts[-1]
            self.head(bx, by, math.atan2(by - ay, bx - ax), stroke, length)
        if heads in ('start', 'both'):
            (ax, ay), (bx, by) = pts[1], pts[0]
            self.head(bx, by, math.atan2(by - ay, bx - ax), stroke, length)

    # Text ---------------------------------------------------------------

    def text(self, x, y, s, size, fill, style='sans', align='left', width=None):
        """Draw a label with its baseline at y; returns its width in mm.

        width, when given, is the room available: a longer label is an error,
        so a layout change cannot silently push text out of its box.
        """
        items, total = _layout(s, size, style)
        if width is not None and total * PT > width + 1e-6:
            raise ValueError(f'{s!r} is {total * PT:.1f} mm wide; '
                             f'{width:.1f} mm available')
        x0 = x - {'left': 0, 'center': total * PT / 2, 'right': total * PT}[align]
        X, Y = self._xy(x0, y)
        c = self.c
        c.saveState()
        c.setFillColor(color(fill))
        for dx, kind, payload in items:
            if kind == 'glyph':
                font, glyph, k = payload
                c.saveState()
                c.translate(X + dx, Y)
                c.scale(k, k)
                self._fill_commands(font.outline(glyph))
                c.restoreState()
            else:
                c.saveState()
                c.translate(X + dx, Y)
                for commands in payload.glyphs:
                    self._fill_commands(commands)
                for rx, ry, rw, rh in payload.rects:
                    c.rect(rx, ry, rw, rh, fill=1, stroke=0)
                c.restoreState()
        c.restoreState()
        return total * PT

    def _fill_commands(self, commands):
        if not commands:
            return
        p = self.c.beginPath()
        for op, *v in commands:
            if op == 'M':
                p.moveTo(*v)
            elif op == 'L':
                p.lineTo(*v)
            elif op == 'C':
                p.curveTo(*v)
            else:
                p.close()
        self.c.drawPath(p, fill=1, stroke=0, fillMode=NONZERO)


class Scale:
    """Linear map from data values [d0, d1] to page millimetres [p0, p1]."""

    def __init__(self, d0, d1, p0, p1):
        self.d0, self.d1, self.p0, self.p1 = d0, d1, p0, p1

    def __call__(self, v):
        return self.p0 + (v - self.d0) * (self.p1 - self.p0) / (self.d1 - self.d0)


def _towards(a, b, d):
    """Point d mm from a towards b."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    return a[0] + (b[0] - a[0]) * d / length, a[1] + (b[1] - a[1]) * d / length
