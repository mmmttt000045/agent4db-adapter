"""Deck figure 1 (system structure): how a user agent's two requests flow through MAVRA.

A user agent asks for a metric by name ("store revenue"); the query service
reads its definition from the shared memory; validation results missing for the
current data version are computed by maintenance and cached; a valid definition
(v2) goes back. The agent then sends SQL that names v2; the pre-execution check
reuses cached validation results on the query's snapshot and runs the SQL there.
Maintenance queries the database and writes validation results to the cache and
new revisions or invalidations to the definitions.
The built-in agent (an LLM) learns definitions and publishes them after
validation. Drawn at slide size (300 mm, 12-15 pt) for the report deck, with
everyday terms rather than the paper's notation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import style  # noqa: E402
from vecfig import measure  # noqa: E402
from parts import (DASH, EXEC, HEAD, LEARN, NOTE, PANEL_EDGE, THICK, THIN, TITLE, USE, WAIT,  # noqa: E402
                   baseline, box, legend_line, legend_pill, llm_badge, mark, node, person, slab, step,
                   table_card, titled)
from style import (ACC, ACC_DK, ACC_PALE, AMBER, AMBER_PALE, EDGE, FACE, FIELD, INK, MUTED,  # noqa: E402
                   RULE, SLATE, WHITE)

NAME = 'overview'
W, H = 300.0, 139.5

LABELS = {
    'zh': {
        'agents': '用户 agent', 'question': ('9 月门店', '营业额？'), 'sql': 'SQL',
        'declares': 'metrics: 营业额 v2', 'middleware': 'MAVRA 中间件',
        'paths': ('学习', '查询指标定义', '执行 SQL'), 'lines': ('调用 / 返回', '写入记忆', '读数据库'),
        'service': '查询服务', 'lookup': ('检索指标定义', '名称匹配；比较表版本'),
        'check': ('执行前验证', '同一快照内验证并执行'),
        'store': '共享记忆', 'store_note': '另有表统计信息、连接路径', 'defs': '指标定义',
        'def_chips': (('营业额 v2', '待验证', 'wait'), ('电子品类 v2', '待验证', 'wait'), ('退货金额 v2', '有效', 'ok')),
        'cache': '验证结果缓存', 'cache_note': '按（条件，表版本）缓存，跨定义共享',
        'cache_chips': (('日期键唯一', '表版本 v7', 'ok'), ('粒度键唯一', '表版本 v15', 'wait'),
                        ('日期键完整性', '表版本 v15', 'wait')),
        'agent': ('内置 agent（大模型）', '学习指标定义，提出优化写法'),
        'maint': ('维护', '执行验证 · 修复、优化或失效'),
        'req_text': '检索“营业额”', 'resp_text': '有效修订 v2', 'req_sql': '执行 SQL', 'resp_sql': '查询结果',
        'read': '读定义', 'reuse': ('复用', '验证结果'), 'missing': '未命中：执行验证',
        'store_result': '写入结果', 'revise': '新修订或失效', 'publish': '准入检查后发布',
        'run': '在快照上执行 SQL', 'qc': '验证查询、表版本',
        'db': '数据库', 'snapshot': '快照', 'etl': 'ETL / 写入方', 'write': '写入',
    },
    'en': {
        'agents': 'User agents', 'question': ('Store revenue', 'in September?'), 'sql': 'SQL',
        'declares': 'metrics: revenue v2', 'middleware': 'MAVRA middleware',
        'paths': ('learning', 'find definition', 'run SQL'),
        'lines': ('call / response', 'write to memory', 'read database'),
        'service': 'Query service', 'lookup': ('Find definition', 'match name, check data'),
        'check': ('Pre-run check', 'validate on one snapshot'),
        'store': 'Shared memory', 'store_note': 'also table profiles, join paths', 'defs': 'Definitions',
        'def_chips': (('revenue v2', 'pending', 'wait'), ('electr. v2', 'pending', 'wait'), ('returns v2', 'valid', 'ok')),
        'cache': 'Validation cache', 'cache_note': 'per (rule, data version), shared',
        'cache_chips': (('date key unique', 'version v7', 'ok'), ('one row/sale', 'version v15', 'wait'),
                        ('loss in bound', 'version v15', 'wait')),
        'agent': ('Built-in agent (LLM)', 'learns definitions, proposes rewrites'),
        'maint': ('Maintenance', 'checks · repair, optimize, retire'),
        'req_text': 'ask “revenue”', 'resp_text': 'valid v2', 'req_sql': 'run SQL', 'resp_sql': 'result',
        'read': 'read', 'reuse': ('reuse', 'results'), 'missing': 'missing: run check',
        'store_result': 'store', 'revise': 'new revision or retire', 'publish': 'admit, publish',
        'run': 'run SQL on the snapshot', 'qc': 'check SQL, data versions',
        'db': 'Database', 'snapshot': 'snapshot', 'etl': 'ETL / writers', 'write': 'write',
    },
}

FIELD_BOX = (50.0, 1.0, 249.0, 107.0)            # MAVRA's area
AGENT = (4.0, 33.0, 44.0, 44.0)
PA = (86.0, 30.0, 64.0, 50.0)                    # query service
LOOKUP = (89.0, 40.0, 58.0, 16.0)
CHECK = (89.0, 60.0, 58.0, 17.0)
OPT = (200.0, 4.0, 97.0, 18.0)                   # built-in agent, above the store
PB = (176.0, 30.0, 121.0, 49.0)                  # metric store
DEFS = (179.0, 40.0, 107.0, 15.5)                # leaves a channel on the right for maintenance
CACHE = (179.0, 58.0, 107.0, 20.0)
MAINT = (210.0, 89.0, 87.0, 16.0)                # maintenance, below the store
DB = (50.0, 116.5, 246.0, 19.0)
SNAP = (89.0, 57.0)                              # (x, w) of the snapshot region, under the check
VERS = (179.0, 52.0)                             # data versions, under the store
TABLES = (237.0, 58.0)                           # tables, under maintenance
Y_TEXT, Y_SQL, GAP = 45.0, 65.5, 4.5             # request arrows; responses run GAP mm below


def draw(s, lang):
    L = LABELS[lang]
    text, rect, route = s.text, s.rect, s.route

    def panel(b, title):
        x, y, w, h = b
        rect(*b, '#FBFCFE', PANEL_EDGE, .4, r=1.6)
        return text(x + 3.0, y + 6.5, title, TITLE, ACC_DK, 'bold', width=w - 6)

    # MAVRA's area, title and legend --------------------------------------------
    rect(*FIELD_BOX, FIELD, None, r=2.8)
    rect(53.5, 4.6, 1.1, 5.4, ACC)
    text(56.6, 9.4, L['middleware'], TITLE, ACC_DK, 'bold')
    x = 57.0
    for label, color, steps in zip(L['paths'], (LEARN, USE, EXEC), ('', '1–5', '6–8')):
        x += legend_pill(s, x, 17.0, label, color, steps) + 6.0
    x = 57.0
    for label, sw, color, dash in zip(L['lines'], (THIN, THICK, THIN), (INK, INK, SLATE),
                                      (None, None, DASH)):
        x += legend_line(s, x, 24.5, label, sw, color, dash) + 6.0

    # User agent: a question in text, then SQL --------------------------------------
    ax, ay, aw, ah = AGENT
    text(ax, 27.0, L['agents'], TITLE, INK, 'bold')
    node(s, AGENT)
    person(s, ax + 3.0, ay + 5.0)
    bx, by, bw, bh = ax + 10.5, ay + 3.0, aw - 13.5, 13.0
    rect(bx, by, bw, bh, ACC_PALE, ACC, .25, r=1.8)
    for k, line in enumerate(L['question']):
        text(bx + bw / 2, by + 5.4 + 5.2 * k, line, NOTE, ACC_DK, align='center', width=bw - 1.6)
    cx, cy, cw, ch = ax + 3.0, ay + 20.0, aw - 6.0, 21.0
    rect(cx, cy, cw, ch, WHITE, EDGE, .28, r=1.0)
    text(cx + 2.0, cy + 5.4, L['sql'], NOTE, MUTED, 'bold')
    for k, length in enumerate((cw - 11, cw - 6, cw - 14)):
        s.line(cx + 2.0, cy + 9.0 + 2.6 * k, cx + 2.0 + length, cy + 9.0 + 2.6 * k, RULE, .6)
    rect(cx + 1.5, cy + ch - 6.2, cw - 3.0, 5.0, ACC_PALE, None, r=1.0)
    text(cx + cw / 2, cy + ch - 2.3, L['declares'], NOTE - 1, ACC_DK, align='center', width=cw - 4.0)

    # Requests and responses ---------------------------------------------------------
    x0, x1 = ax + aw + 3.0, PA[0]
    lab = x0 + 7.6
    for (y_req, color, (n_req, n_resp), (req, resp), target) in (
            (Y_TEXT, USE, (1, 5), (L['req_text'], L['resp_text']), LOOKUP),
            (Y_SQL, EXEC, (6, 8), (L['req_sql'], L['resp_sql']), CHECK)):
        route([(x0, y_req), (target[0], y_req)], color, THIN, length=HEAD)
        route([(target[0], y_req + GAP), (x0, y_req + GAP)], color, THIN, length=HEAD)
        text(lab, y_req - 2.0, req, NOTE, color, width=x1 - lab - 1.0)
        text(lab, y_req + GAP + 5.8, resp, NOTE, color, width=x1 - lab - 1.0)
        step(s, x0 + 3.2, y_req - 3.6, n_req, color)
        step(s, x0 + 3.2, y_req + GAP + 4.4, n_resp, color)

    # Query service --------------------------------------------------------------------
    panel(PA, L['service'])
    titled(s, LOOKUP, *L['lookup'])
    titled(s, CHECK, *L['check'])

    # Built-in agent ---------------------------------------------------------------------
    ox, oy, ow, oh = OPT
    box(s, OPT, fill='#F7FAFE', stroke=ACC)
    llm_badge(s, ox + 6.5, oy + oh / 2, 3.6)
    title, note = L['agent']
    text(ox + 13.0, oy + 7.2, title, TITLE, INK, 'bold', width=ow - 15)
    text(ox + 13.0, oy + 14.0, note, NOTE, ACC_DK, width=ow - 15)

    # Shared memory: definitions and the validation cache ---------------------------------
    tw = panel(PB, L['store'])
    text(PB[0] + 7.0 + tw, PB[1] + 6.5, L['store_note'], NOTE, MUTED, width=OPT[0] + OPT[2] - 14.0 - PB[0] - tw)
    x, y, w, h = DEFS
    box(s, DEFS)
    tl = text(x + 3.0, baseline(y + h / 2, NOTE), L['defs'], NOTE, INK, 'bold')
    cw2 = min(27.0, (w - 3.0 - tl - 2.0 - 2.0 - 4.0) / 3)   # chips right-aligned, clear of the label
    for k, (name, state, kind) in enumerate(L['def_chips']):
        col, pale = (AMBER, AMBER_PALE) if kind == 'wait' else (ACC_DK, ACC_PALE)
        xx = x + w - 2.0 - (3 - k) * cw2 - (2 - k) * 2.0
        rect(xx, y + 1.5, cw2, h - 3.0, pale, None, r=1.0)
        rect(xx + 1.2, y + 2.8, 1.0, h - 5.6, col)
        text(xx + 3.4, y + 6.8, name, NOTE, INK, width=cw2 - 4.0)
        text(xx + 3.4, y + 12.2, state, NOTE, WAIT if col == AMBER else col, width=cw2 - 4.0)
    x, y, w, h = CACHE
    box(s, CACHE)
    tw = text(x + 3.0, y + 5.4, L['cache'], NOTE, INK, 'bold')
    text(x + 5.5 + tw, y + 5.4, L['cache_note'], NOTE, MUTED, width=w - 8.5 - tw)
    chip_w = (w - 6.0) / 3
    for k, (rule, version, kind) in enumerate(L['cache_chips']):
        xx = x + 1.5 + k * (chip_w + 1.5)
        missing = kind == 'wait'
        rect(xx, y + 7.5, chip_w, 11.0, AMBER_PALE if missing else FACE, AMBER if missing else EDGE,
             .3 if missing else .2, r=1.0)
        text(xx + 1.6, y + 12.0, rule, NOTE, INK, width=chip_w - 2.4)
        text(xx + 1.6, y + 17.0, version, NOTE, WAIT if missing else MUTED, width=chip_w - 6.0)
        mark(s, xx + chip_w - 2.6, y + 15.6, kind)

    # Maintenance --------------------------------------------------------------------------
    titled(s, MAINT, *L['maint'])

    # Inside MAVRA: read the definition, reuse cached results, fill the missing ones -----
    ga, gb = PA[0] + PA[2], PB[0]
    gm = (ga + gb) / 2
    yr = DEFS[1] + DEFS[3] / 2
    route([(DEFS[0], yr), (LOOKUP[0] + LOOKUP[2], yr)], USE, THIN, length=HEAD)
    text(gm, yr - 2.0, L['read'], NOTE, USE, align='center', width=gb - ga + 4)
    step(s, gm, yr + 4.2, 2, USE)
    yc = CACHE[1] + 10.5
    route([(CHECK[0] + CHECK[2], yc), (CACHE[0], yc)], EXEC, THIN, heads='both', length=HEAD)
    r1, r2 = L['reuse']
    text(gm, yc - 7.2, r1, NOTE, EXEC, align='center')
    text(gm, yc - 2.0, r2, NOTE, EXEC, align='center', width=gb - ga + 4)
    step(s, gm, yc + 4.2, 7, EXEC)
    # The missing results share one connector: maintenance computes them all and writes them back.
    miss = [CACHE[0] + 1.5 + k * (chip_w + 1.5) + chip_w / 2
            for k, c in enumerate(L['cache_chips']) if c[2] == 'wait']
    yb, yj, yt = CACHE[1] + 18.5, PB[1] + PB[3] + 1.5, MAINT[1]
    xn = (DEFS[0] + DEFS[2] + PB[0] + PB[2]) / 2     # maintenance -> definitions, right of the store
    xu = xn - 6.0 - measure(L['revise'], NOTE)
    xd = xu - 10.5 - measure(L['store_result'], NOTE)
    for xc in miss:
        route([(xc, yb), (xc, yj)], USE, THIN, heads=None)
    route([(min(miss[0], xd), yj), (max(miss[-1], xu), yj)], USE, THIN, heads=None)
    route([(xd, yj), (xd, yt)], USE, THIN, length=HEAD)
    route([(xu, yt), (xu, yj)], USE, THICK, length=HEAD)
    ym = (yj + yt) / 2
    w3 = text(xd - 2.0, baseline(ym, NOTE), L['missing'], NOTE, USE, align='right')
    step(s, xd - 2.0 - w3 - 4.0, ym, 3, USE)
    w4 = text(xu - 2.0, baseline(ym, NOTE), L['store_result'], NOTE, USE, align='right')
    step(s, xu - 2.0 - w4 - 4.0, ym, 4, USE)
    # Maintenance also writes the definitions: a repaired or cheaper revision, or an invalidation.
    route([(xn, yt), (xn, yr), (DEFS[0] + DEFS[2], yr)], INK, THICK, length=HEAD)
    text(xn - 2.0, baseline(ym, NOTE), L['revise'], NOTE, INK, align='right')
    # Learning: the built-in agent publishes into the definitions.
    xp = DEFS[0] + DEFS[2] - 10.0
    route([(xp, OPT[1] + OPT[3]), (xp, DEFS[1])], LEARN, THICK, length=HEAD)
    text(xp - 2.0, 28.6, L['publish'], NOTE, LEARN, align='right')

    # Database ---------------------------------------------------------------------------
    px, py, pw, ph = DB
    slab(s, DB)
    text(px + 4.0, baseline(py + ph / 2, TITLE), L['db'], TITLE, INK, 'bold', width=SNAP[0] - px - 6)
    top, inner = py + 2.0, ph - 4.0
    nx, nw = SNAP
    rect(nx, top, nw, inner, WHITE, EXEC, .35, r=.8, dash=(1.6, 1.0))
    text(nx + 2.5, baseline(top + inner / 2, NOTE), L['snapshot'], NOTE, EXEC, width=17)
    for k in range(3):
        table_card(s, nx + 21.0 + k * 12.0, 10.5, top + 1.2, inner - 2.4)
    vx, vw = VERS
    rect(vx, top, vw, inner, WHITE, EDGE, .28, r=.8)
    for k, (table, old, new) in enumerate((('`store_sales`', 14, 15), ('`date_dim`', 7, None))):
        yy = top + 4.6 + 6.4 * k
        if new:
            rect(vx + 1.0, yy - 3.0, vw - 2.0, 5.2, AMBER_PALE, AMBER, .28, r=.9)
        text(vx + 2.6, baseline(yy - .4, NOTE), table, NOTE, INK)
        value = f'v{old} → v{new}' if new else f'v{old}'
        text(vx + vw - 2.6, baseline(yy - .4, NOTE), value, NOTE, WAIT if new else INK, align='right')
    tx, tw_ = TABLES
    cw3 = (tw_ - 2.0) / 2
    for k, (label, changed) in enumerate((('`store_sales`', (1, 2)), ('`date_dim`', ()))):
        table_card(s, tx + k * (cw3 + 2.0), cw3, top, inner, label, changed,
                   outline=AMBER if changed else EDGE)

    # Reads and writes of the database ---------------------------------------------------
    xq = CHECK[0] + CHECK[2] / 2
    route([(xq, CHECK[1] + CHECK[3]), (xq, py - 3.2)], EXEC, THIN, length=HEAD)
    text(xq + 2.4, 97.0, L['run'], NOTE, EXEC)
    xr = TABLES[0] + 3.0
    route([(xr, MAINT[1] + MAINT[3]), (xr, py - 3.2)], SLATE, THIN, dash=DASH, length=HEAD)
    text(xr + 2.4, baseline((MAINT[1] + MAINT[3] + py - 3.2) / 2, NOTE), L['qc'], NOTE, SLATE)

    # Writers ---------------------------------------------------------------------------
    wx, wy = 5.0, 121.0
    text(4.0, 114.5, L['etl'], TITLE - 1, INK, 'bold')
    for off in (2.8, 1.4, 0):
        rect(wx + off, wy - off, 21.0, 12.0, WHITE, EDGE, .26, r=.8)
    for k in range(3):
        s.circle(wx + 3.4, wy + 3.0 + 3.2 * k, .8, AMBER)
        s.line(wx + 5.6, wy + 3.0 + 3.2 * k, wx + 17.6, wy + 3.0 + 3.2 * k, RULE, .6)
    yy = wy + 6.2
    route([(wx + 26.0, yy), (px, yy)], INK, THIN, length=HEAD)
    text((wx + 26.0 + px) / 2, yy - 2.2, L['write'], NOTE, MUTED, align='center', width=px - wx - 27)


if __name__ == '__main__':
    for path in style.build(sys.modules[__name__]):
        print(path)
