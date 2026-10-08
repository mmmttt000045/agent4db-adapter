// Builds docs/mavra-system.pptx, a 10-slide Chinese deck that tells MAVRA as one story: title; how it differs from
// Text-to-SQL; a shared rule breaks when the data changes (toy ledger, then the real record); MAVRA between agents and
// the database with its three responsibilities (publish, rely, maintain and improve); the running example, 门店营业额
// v1 (learned) → v2 (optimized) → v3 (repaired), as one table; publish (admission, the four conditions); rely (the traced
// use with a declared revision, table versions, the same snapshot); maintain and improve (v1 → v2 and v2 → v3 as
// recorded); results; guarantees, limits and three sentences. The user asked for 10 slides: don't add slides. The system
// figure comes from tools/deck/figures/ (drawn by `python3 tools/figures/build.py --deck`,
// rendered to PNG). Toy tables are marked 示意; every other number comes from the archived
// run records or the paper's generated macros (overleaf/gen/*.tex). Wording uses standard
// database terms, with a one-line plain reading beside each.
// Usage: node build-deck.js [--out path]
'use strict';

const fs = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

const ROOT = path.resolve(__dirname, '../..');
const FIG = path.join(__dirname, 'figures');
const at = process.argv.indexOf('--out');
const OUT = at > 0 ? path.resolve(process.argv[at + 1]) : path.join(ROOT, 'docs/mavra-system.pptx');

const FONT = 'Microsoft YaHei';
const CODE = 'Courier New';
const C = {
  ink: '1F2A37', muted: '5B6573', navy: '17233B', ice: 'CADCFC', white: 'FFFFFF', grey: 'F1F3F6',
  line: 'D5DBE3', blue: '1D5BA6', paleBlue: 'E8F0FA', amber: 'B5671A', paleAmber: 'FBF0E2',
  violet: '6A58A3', paleViolet: 'EFECF7', red: 'B5392A', green: '2E7D4F', paleGreen: 'E6F2EA',
};
const W = 13.333, M = 0.6;
const DATA = '数据为仿 TPC-DS 的合成零售数据（store_sales 100 万行），题目中的年份略去。';
const SOURCE = '记录：noctis results/scen-20261002/dsv41flash-r1-g3fix--snap（端到端实验第 1 次 MAVRA 运行）。' + DATA;
const TRACE_SOURCE = '记录：noctis results/scen-20261008-trace（metric-global-opt，--trace 逐次记录工具调用；DeepSeek V4.1 Flash）。' + DATA;
const LEARN_TIMING = '本次运行：抽取 12.7 秒，准入检查 5.6 秒。';

// Width / height of a figure PNG, from its header.
function aspect(file) {
  const buf = fs.readFileSync(file);
  return buf.readUInt32BE(16) / buf.readUInt32BE(20);
}

// Place a figure below the title, as large as fits and centred in the space left.
function figure(slide, name, top = 1.2, maxH = 5.75) {
  const file = path.join(FIG, `${name}-zh.png`);
  const r = aspect(file);
  let w = W - 2 * M, h = w / r;
  if (h > maxH) { h = maxH; w = h * r; }
  slide.addImage({ path: file, x: (W - w) / 2, y: top + (maxH - h) / 2, w, h, objectName: name });
}

function text(slide, value, opts) {
  slide.addText(value, { fontFace: FONT, color: C.ink, margin: 0, isTextBox: true, ...opts });
}

function footnote(slide, value) {
  text(slide, value, { x: M, y: 6.85, w: W - 2 * M - 0.8, h: 0.4, fontSize: 11, color: C.muted,
    valign: 'bottom' });
}

// A tinted rounded band holding text runs.
function band(slide, runs, { x = M, y, w = W - 2 * M, h, fill = C.grey, size = 16, valign = 'middle' }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08 });
  text(slide, runs, { x: x + 0.3, y: y + 0.1, w: w - 0.6, h: h - 0.2, fontSize: size, valign,
    paraSpaceAfter: 4 });
}

// Bullet runs: an optional bold heading line, then one bullet per item.
function bulleted(head, color, items) {
  const runs = head ? [{ text: head, options: { bold: true, color, breakLine: true } }] : [];
  return runs.concat(items.map((t, k) => ({ text: t, options: { bullet: true, breakLine: k < items.length - 1 } })));
}

// A plain table: header row in grey, body in white.
function table(slide, rows, { x, y, w, colW, size = 14, rowH }) {
  const head = rows[0].map((t) => (typeof t === 'string'
    ? { text: t, options: { bold: true, fill: { color: C.grey } } }
    : { text: t.text, options: { ...t.options, bold: true, fill: { color: C.grey } } }));
  const body = rows.slice(1).map((r) => r.map((c) => (typeof c === 'string' ? { text: c } : c)));
  slide.addTable([head, ...body], { x, y, w, colW, rowH, fontFace: FONT, fontSize: size, color: C.ink,
    valign: 'middle', border: { type: 'solid', pt: 1, color: C.line }, margin: [0.06, 0.1, 0.06, 0.1] });
}
const good = (t) => ({ text: t, options: { color: C.green, bold: true } });
const bad = (t) => ({ text: t, options: { color: C.red, bold: true } });
const strong = (t, color) => ({ text: t, options: { color, bold: true } });
const muted = (t) => ({ text: t, options: { color: C.muted } });
// A cell made of several lines.
const lines = (...parts) => ({ text: parts.map((p, k) => {
  const run = typeof p === 'string' ? { text: p, options: {} } : { text: p.text, options: { ...p.options } };
  if (k < parts.length - 1) run.options.breakLine = true;
  return run;
}) });
// A cell with a main line and a smaller second line (a call or a code fragment).
const sub = (main, second, code = true) => ({ text: [
  { text: main, options: { breakLine: true } },
  { text: second, options: { fontSize: 11, color: C.muted, fontFace: code ? CODE : FONT } },
] });
// A section heading inside a slide.
function heading(slide, value, x, y, w, color = C.blue) {
  text(slide, value, { x, y, w, h: 0.35, fontSize: 15, bold: true, color, valign: 'middle' });
}
// A tinted card with a numbered circle, a heading, a subtitle and a body.
function card(slide, { x, y, w, h, n, head, sub, body, color, pale, size = 14 }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: pale }, line: { color: pale },
    rectRadius: 0.12, objectName: `card ${head}` });
  slide.addShape('ellipse', { x: x + 0.3, y: y + 0.3, w: 0.5, h: 0.5, fill: { color }, line: { color } });
  text(slide, String(n), { x: x + 0.3, y: y + 0.3, w: 0.5, h: 0.5, fontSize: 18, bold: true,
    color: C.white, align: 'center', valign: 'middle' });
  text(slide, head, { x: x + 0.95, y: y + 0.3, w: w - 1.25, h: 0.5, fontSize: 19, bold: true, color, valign: 'middle' });
  text(slide, sub, { x: x + 0.3, y: y + 0.95, w: w - 0.6, h: 0.35, fontSize: 13, color: C.muted, valign: 'middle' });
  text(slide, body, { x: x + 0.3, y: y + 1.4, w: w - 0.6, h: h - 1.6, fontSize: size, valign: 'top',
    lineSpacingMultiple: 1.12 });
}

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.title = 'MAVRA：数据智能体与数据库之间的记忆中间件';
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

const titlePh = (y, h, size, color, valign) => ({ placeholder: { options: { name: 'title', type: 'title',
  x: M, y, w: W - 2 * M, h, fontFace: FONT, fontSize: size, bold: true, color, valign, align: 'left',
  margin: 0 }, text: '' } });
const number = (color) => ({ x: W - 1.1, y: 7.05, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color,
  align: 'right' });

pres.defineSlideMaster({ title: 'TITLE', background: { color: C.navy }, objects: [
  titlePh(1.9, 2.1, 40, C.white, 'bottom'),
  { placeholder: { options: { name: 'body', type: 'body', x: M, y: 4.3, w: W - 2 * M, h: 0.7,
    fontFace: FONT, fontSize: 22, color: C.ice, valign: 'top', align: 'left', margin: 0 }, text: '' } },
] });
pres.defineSlideMaster({ title: 'CONTENT', background: { color: C.white },
  objects: [titlePh(0.3, 0.75, 28, C.ink, 'middle')], slideNumber: number(C.muted) });

function content(title, section) {
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: section });
  s.addText(title, { placeholder: 'title' });
  return s;
}

// 1 Title -------------------------------------------------------------------------
pres.addSection({ title: '开场' });
let s = pres.addSlide({ masterName: 'TITLE', sectionTitle: '开场' });
s.addText('MAVRA：数据智能体与数据库之间的\n记忆中间件', { placeholder: 'title' });
s.addText('可维护的共享记忆：发布 · 依赖 · 维护与改进', { placeholder: 'body' });
s.addNotes('很多数据智能体在同一个数据库上工作。一个智能体学会了怎么算“营业额”，别的智能体也想用；'
  + '但数据库每天都在更新，学到的规则可能在不知不觉中不再适用，而 SQL 照样能执行。'
  + 'MAVRA 是放在智能体与数据库之间的中间件：保存智能体学到的规则，记住规则成立的条件，在规则被使用时保证条件在实际执行的数据上仍然成立，条件被破坏时修复或禁用。'
  + '顺序：问题 → MAVRA 与三项职责 → 贯穿全场的例子（门店营业额 v1 → v2 → v3）→ 发布 → 依赖 → 维护与改进 → 实验 → 边界与总结，共 10 页。');

// 2 Text-to-SQL vs MAVRA ----------------------------------------------------------------------
pres.addSection({ title: '问题' });
s = content('Text-to-SQL 与 MAVRA：不同层次的问题', '问题');
const half = (W - 2 * M - 0.4) / 2;
[
  { x: M, tag: 'Text-to-SQL', head: '将自然语言问题翻译为 SQL 查询', color: C.muted, pale: C.grey, rows: [
    ['输入', '自然语言问题 + 数据库模式（可附示例查询）'],
    ['输出', '一条 SQL 查询'],
    ['状态', '无状态：每个问题独立处理，不保留结果'],
    ['关注', '单条查询的正确性'],
  ] },
  { x: M + half + 0.4, tag: 'MAVRA', head: '智能体与数据库之间的记忆中间件', color: C.blue, pale: C.paleBlue, rows: [
    ['位置', '智能体对数据库的全部访问经由它转发'],
    ['记忆', '智能体获得的数据库知识：表统计、连接路径、指标定义'],
    ['共享', '跨智能体、跨会话共享'],
    ['关注', '已有知识在当前数据上的有效性'],
  ] },
].forEach(({ x, tag, head, color, pale, rows }) => {
  s.addShape('roundRect', { x, y: 1.15, w: half, h: 2.55, fill: { color: pale }, line: { color: pale },
    rectRadius: 0.12, objectName: `card ${tag}` });
  text(s, tag, { x: x + 0.35, y: 1.28, w: half - 0.7, h: 0.35, fontSize: 15, bold: true, color });
  text(s, head, { x: x + 0.35, y: 1.62, w: half - 0.7, h: 0.5, fontSize: 20, bold: true, color: C.ink });
  rows.forEach(([k, v], i) => {
    const y = 2.2 + i * 0.38;
    text(s, k, { x: x + 0.35, y, w: 0.75, h: 0.36, fontSize: 14, bold: true, color, valign: 'middle' });
    text(s, v, { x: x + 1.1, y, w: half - 1.45, h: 0.36, fontSize: 14, valign: 'middle' });
  });
});
heading(s, '实验记录：同一问题“9 月的门店营业额是多少？”（只给名称）三次独立求解', M, 3.8, W - 2 * M);
table(s, [
  ['', '所选度量列', '答案', '轮数'],
  ['无共享定义 · 第 1、2 次', 'ss_ext_sales_price（扩展销售额，折扣前）', bad('1413.8 万 ✗'), '5'],
  ['无共享定义 · 第 3 次', 'ss_net_paid（净支付额）', good('1307.0 万 ✓'), '5'],
  [strong('有 MAVRA · 3 次结果一致', C.blue), 'ss_net_paid（检索到共享的指标定义）', good('1307.0 万 ✓'), '3'],
], { x: M, y: 4.15, w: W - 2 * M, colW: [3.0, 6.0, 2.0, 1.133], size: 12 });
band(s, [
  { text: '两者处于不同层次：', options: { bold: true, color: C.blue } },
  { text: '任何 Text-to-SQL 模型或数据智能体都可以作为用户智能体接入 MAVRA。MAVRA 不生成 SQL；它提供经过验证的知识，并在查询执行前验证其有效性。', options: { breakLine: true } },
  { text: '业务口径不在模式中：', options: { bold: true, color: C.blue } },
  { text: 'Text-to-SQL 每次重新推断选哪一列，同一问题的答案不稳定；共享已验证的定义后，答案一致且轮数更少。' },
], { y: 5.8, h: 0.95, fill: C.paleAmber, size: 12 });
footnote(s, '记录：noctis results/scen-20261002，留出任务 M1-P1；无共享定义：dsv41flash-r1-a、r2-b、r3-a；MAVRA：r1–r3-g3fix--snap。' + DATA);
s.addNotes('先说清楚这不是一个 Text-to-SQL 工作。Text-to-SQL 研究的是翻译：给定自然语言问题和数据库模式，生成一条 SQL，评价这条 SQL 对不对；它是无状态的，每个问题独立处理，不保留任何结果。'
  + 'MAVRA 不生成 SQL。它位于智能体与数据库之间，智能体对数据库的访问都经由它转发；它关注的是智能体在探索中获得的知识——营业额对应哪一列、两张表怎么连——如何持久化、如何共享、数据更新后是否仍然有效。'
  + '下面是实验记录：题目只给“门店营业额”这个名称，无共享定义的智能体三次独立求解，两次选了折扣前的扩展销售额，错；一次选了净支付额，对。选哪一列是业务口径，模式里没有，Text-to-SQL 每次重新猜，答案不稳定。接入 MAVRA 后检索到共享的定义，三次都对，3 轮完成。'
  + '所以两者处于不同层次：任何 Text-to-SQL 模型都可以作为用户智能体接在 MAVRA 上面。');

// 3 The problem, on a toy ledger and then the real record ------------------------------------
s = content('问题：共享的计算规则会因数据变化而失效，而 SQL 不报错', '问题');
const colL = 5.9, colR = W - 2 * M - colL - 0.35, xR = M + colL + 0.35;
heading(s, '第一天（示意）：规则“营业额 = 每笔销售金额之和”成立', M, 1.1, colL);
table(s, [
  ['订单号', '金额', '状态'],
  ['001', '100 元', '当前'],
  ['002', '200 元', '当前'],
  ['003', '300 元', '当前'],
], { x: M, y: 1.45, w: colL, colW: [1.5, 1.6, 2.8], size: 12 });
text(s, [{ text: '按规则计算：600 元 ✓', options: { bold: true, color: C.green } }],
  { x: M, y: 3.05, w: colL, h: 0.35, fontSize: 14, valign: 'middle' });
heading(s, '第二天：订单 002 更正为 250 元，旧行保留并标记为非当前', xR, 1.1, colR);
table(s, [
  ['订单号', '金额', '状态'],
  ['001', '100 元', '当前'],
  ['002', '200 元', muted('旧记录')],
  ['002', '250 元', '当前'],
  ['003', '300 元', '当前'],
], { x: xR, y: 1.45, w: colR, colW: [1.5, 1.6, colR - 3.1], size: 12 });
text(s, [
  { text: '沿用规则：850 元 ✗（旧行也被计入）　正确答案：650 元', options: { bold: true, color: C.red, breakLine: true } },
  { text: '规则本身没有错，错的是规则的前提“每个订单号只有一行”不再成立。' },
], { x: xR, y: 3.3, w: colR, h: 0.55, fontSize: 12, valign: 'top' });
heading(s, '实验中的真实记录：定义发布后数据库持续更新，沿用已发布的定义（对照组）', M, 4.0, W - 2 * M);
table(s, [
  ['更新', '数据库中的变化', '参考答案', '沿用已发布的定义'],
  ['增量加载', '追加新销售记录（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '旧行保留并标记为非当前，插入九折后的当前行，65,915 行', '1293.3 万',
    bad('1430.1 万 ✗  新旧版本重复计入')],
  ['重复加载', '4 个月的销售批次被再次加载，+110,165 行', '1307.0 万', bad('2613.9 万 ✗  9 月重复计入')],
], { x: M, y: 4.35, w: W - 2 * M, colW: [1.3, 6.1, 1.5, 3.233], size: 12 });
band(s, [
  { text: '三种更新都是普通 DML，模式未变，查询仍成功执行：智能体会自信地给出错误答案；', options: { breakLine: true } },
  { text: '规则被所有智能体共享：一处失效，所有使用方同时出错。' },
], { y: 5.9, h: 0.8, fill: C.paleAmber, size: 12 });
footnote(s, '上半为示意例子；下半来自 noctis results/scen-20261002，dsv41flash-r1–r3-g3fix--schema（仅在模式变更时使定义失效，3 次运行答案相同）。' + DATA);
s.addNotes('先用一个示意的小账本。第一天三笔订单，规则“把每笔销售金额加起来”算出 600 元，正确。'
  + '第二天订单 002 被更正为 250 元，数据仓库常见的做法是旧行不删、标记为非当前，再插入一行新的。沿用规则会把 200 和 250 都加进去，得到 850 元，正确答案是 650 元。'
  + '注意：规则没有算错，是规则的前提“每个订单号只有一行”不再成立了。'
  + '下半是实验里的真实记录：增量加载没问题；数据更正后沿用定义多算 137 万；重复加载让 9 月翻倍。'
  + '三种更新都是普通 DML，表结构没变，查询不报错，智能体会非常自信地给出错误答案；而定义是共享的，一处失效所有智能体一起错。这就是 MAVRA 要解决的问题。');

// 4 MAVRA: where it sits and the three responsibilities ------------------------------------------
pres.addSection({ title: 'MAVRA' });
s = content('MAVRA：智能体与数据库之间的共享记忆层，承担三项职责', 'MAVRA');
{
  const file = path.join(FIG, 'overview-zh.png');
  const fh = 3.75, fw = fh * aspect(file);
  s.addImage({ path: file, x: M, y: 1.15, w: fw, h: fw / aspect(file), objectName: 'overview' });
  const cx = M + fw + 0.3, cw2 = W - M - cx;
  [
    { head: '① 发布', body: '什么可以进入共享记忆：只收判题成功、通过 7 项准入检查的知识，连同它成立的条件一起保存', color: C.violet, pale: C.paleViolet },
    { head: '② 依赖', body: '一次使用何时可以依赖它：智能体声明所依据的修订，条件在这条查询的快照上成立才执行', color: C.blue, pale: C.paleBlue },
    { head: '③ 维护与改进', body: '为所有使用者只做一次：数据变了就重新验证，能修则发新修订，修不好则失效；有更省的等价写法也发新修订', color: C.amber, pale: C.paleAmber },
  ].forEach((c, k) => {
    const y = 1.15 + k * 1.27;
    s.addShape('roundRect', { x: cx, y, w: cw2, h: 1.15, fill: { color: c.pale }, line: { color: c.pale }, rectRadius: 0.08 });
    text(s, c.head, { x: cx + 0.2, y: y + 0.08, w: cw2 - 0.4, h: 0.32, fontSize: 15, bold: true, color: c.color, valign: 'middle' });
    text(s, c.body, { x: cx + 0.2, y: y + 0.42, w: cw2 - 0.4, h: 0.68, fontSize: 11.5, valign: 'top' });
  });
}
band(s, [
  { text: '智能体看到的是工具：', options: { bold: true, color: C.blue } },
  { text: 'list_tables · describe_table · join_path · find_metric(名称) · run_sql(sql, metrics=[{key, revision}]) · final_answer。'
    + 'metrics 参数就是“声明”：这条 SQL 依据哪条定义的哪个修订。', options: { breakLine: true } },
  { text: '谁参与：', options: { bold: true, color: C.blue } },
  { text: '学习由内置智能体（大模型）完成，人只确认一次答案是否正确；维护由数据更新后第一个用到该定义的请求触发；修复有歧义时才交给人。' },
], { y: 5.2, h: 1.45, size: 12 });
s.addNotes('原来智能体直接访问数据库，现在 MAVRA 放在中间，不替代智能体，也不替代数据库。'
  + '图里紫色是学习：内置智能体学到的定义通过准入检查后写入共享记忆；蓝色是检索定义：表版本变了，缺少验证结果的条件交给维护执行，再返回有效修订；橙色是执行 SQL：智能体声明依据的修订，在同一快照上验证后执行。'
  + '右边三张卡就是 MAVRA 的三项职责，也是论文的三个问题：什么可以发布，何时可以依赖，由谁维护与改进。后面每一节讲一项。'
  + '智能体看到的只是几个工具，最关键的是 run_sql 的 metrics 参数——声明这条 SQL 用的是哪条定义的哪个版本，MAVRA 的保证就挂在这个声明上。');

// 5 The running example: three revisions of one definition ---------------------------------------
s = content('一个例子贯穿全场：门店营业额的三个修订', 'MAVRA');
text(s, [
  { text: '口径从来没变：', options: { bold: true, color: C.blue } },
  { text: '门店营业额 = 门店销售的净支付额之和，按销售日期归到各月。变的只是 SQL 怎么写——修订（v）就是同一条定义的第几版写法。' },
], { x: M, y: 1.1, w: W - 2 * M, h: 0.45, fontSize: 15, valign: 'middle' });
table(s, [
  ['版本', '为什么会有它', 'SQL 写法', '依赖的条件', '9 月的结果'],
  [strong('v1', C.blue), '智能体学到', 'SUM(ss_net_paid)，连接日期表按年月筛选', '粒度键唯一、日期键唯一、日期键完整性', good('1307.0 万 ✓')],
  [strong('v2', C.blue), '找到更省的写法', '同一个求和，不连接日期表，改成按日期键范围筛选', 'v1 的条件，再加“日期键按月连续”', lines(good('1307.0 万 ✓'), muted('同 v1，快约 20%'))],
  [strong('v3', C.blue), '数据更正后 v2 算错了', "v2 再加一个过滤 ss_is_current = '1'", '同上，在这个过滤之下成立', good('1293.3 万 ✓')],
], { x: M, y: 1.65, w: W - 2 * M, colW: [0.8, 2.3, 4.0, 3.0, 2.033], size: 14 });
text(s, bulleted(null, C.blue, [
  'v1 → v2 是换个更快的写法：两版结果完全一样，v1 也没坏，仍被接受（附提醒）',
  'v2 → v3 是数据变了：更正时旧行保留并标为非当前，v2 会把新旧两行都算进去（1430.1 万 ✗）；修复出 v3 后 v2 不能再用',
  'v3 也不是终点：数据再变可能有 v4；找不到可靠的修法就不出新修订，定义失效并通知。口径变了（比如改成含税）是另一条定义，不是新修订',
]), { x: M, y: 4.3, w: W - 2 * M, h: 1.2, fontSize: 13, valign: 'top', paraSpaceAfter: 4 });
band(s, [
  { text: '为什么要编号：', options: { bold: true, color: C.blue } },
  { text: '智能体执行 SQL 时声明“依据门店营业额 v2”；MAVRA 据此拒绝已停用的版本，只在该版本的条件成立时执行，并记下每个答案来自哪一版。'
    + '系统调用原文里的 revision: N 即 v(N+1)。' },
], { y: 5.65, h: 0.95, fill: C.paleBlue, size: 13 });
footnote(s, '9 月结果：v1 取自 results/scen-20261002（未做优化的 MAVRA 运行），v2、v3 取自 results/scen-20261008-trace；“快约 20%”为优化轮配对测量 29.1 → 23.3 ms。' + DATA);
s.addNotes('后面所有页面都用这一个例子。先说清楚 v 是什么：它是版本号，同一条定义的第几版写法，按时间往下记，不是一级比一级高的等级。'
  + '三个版本里口径从来没变，都是门店销售净支付额之和、按销售日期归月；变的只是 SQL 怎么写。'
  + 'v1 是智能体学到的：连接日期表按年月筛选。v2 是 MAVRA 找到的更省写法：不连接日期表，直接按日期键范围筛选，结果和 v1 完全一样，快约 20%，但多了一个前提——日期键按月连续，这个前提也成为 v2 的条件。'
  + 'v3 是数据更正之后：旧行保留并标为非当前，v2 会把新旧两行都算进去，得到 1430.1 万；MAVRA 找到唯一可行的过滤 ss_is_current = 1，修复出 v3，答案 1293.3 万。'
  + '编号的用处在于声明：智能体说“我用 v2”，MAVRA 就能判断 v2 现在还能不能用。');

// 6 Publish: how v1 got in --------------------------------------------------------------------------
pres.addSection({ title: '发布' });
s = content('发布：v1 是怎么进入共享记忆的', '发布');
const lw = 6.3, rx = M + lw + 0.3, rw = W - M - rx;
heading(s, '学习任务给定业务口径：“3 月的门店营业额是多少？”', M, 1.1, lw, C.violet);
table(s, [
  ['步骤', '发生了什么'],
  ['求解', '内置智能体 5 轮 7 次工具调用写出 SQL（第一次 find_metric 为空：还没人学过），答案 13,570,368.70 与参考答案一致'],
  ['抽取', '大模型把题面、SQL、算式、表元数据整理成知识卡，剥离题目参数（月份）'],
  ['准入', '7 项检查：业务依据 · 判定正确 · 静态合法 · 粒度成立 · SQL 审查 · 重放示例 SQL · 重放规范 SQL'],
  ['发布', 'metric:门店营业额 v1，连同条件、学习证据与表版本'],
  ['知识卡', lines('给智能体看的：度量 SUM(ss_net_paid)；粒度 销售日 × 小票号 × 商品；按销售日关联 date_dim；不含税',
    'MAVRA 保管的：条件、学习证据（SQL、答案、表版本）、状态、修订号、使用者')],
], { x: M, y: 1.45, w: lw, colW: [0.8, lw - 0.8], size: 11 });
heading(s, '发布时一并记下：从定义推出的四类条件', rx, 1.1, rw, C.blue);
table(s, [
  ['条件', '通俗地说', '检查方式'],
  ['粒度键唯一', '一件事不登记两次', '行数 = 不同键数（在定义的过滤之下）'],
  ['连接基数 N:1', '连接不能把一行变两行', '连接“1”侧的键唯一'],
  ['日期角色', '按指定的日期归期间，一个键只连出一个日期', '日期维键唯一'],
  ['日期键完整性', '不能突然有大量记录找不到日期', '未匹配率 ≤ 学习时 + 0.1 个百分点'],
], { x: rx, y: 1.45, w: rw, colW: [1.35, 2.15, rw - 3.5], size: 11 });
text(s, [
  { text: '命题 1：', options: { bold: true, color: C.blue } },
  { text: '业务前提成立且四类条件都成立时，规范 SQL 把每笔业务事件在其期间内恰好计一次。', options: { breakLine: true } },
  { text: '不保证一切：', options: { bold: true, color: C.red } },
  { text: '金额从元改成美元，行数和键都没变，四类条件发现不了（实验里的“单位变化”对照）。' },
], { x: rx, y: 3.95, w: rw, h: 1.3, fontSize: 12, valign: 'top', paraSpaceAfter: 3 });
band(s, [
  { text: '第 7 项最重要：', options: { bold: true, color: C.violet } },
  { text: '别的智能体只能读到这张知识卡。实验中被拦下的一例：提取时丢了“电子”类别过滤，智能体答的是 274.1 万，知识卡编译出的 SQL 会返回 1352.1 万。', options: { breakLine: true } },
  { text: '判定正确：', options: { bold: true, color: C.violet } },
  { text: '实验用参考答案；部署中由指标负责人确认一次。此后维护与修复不再需要参考答案。' },
], { y: 5.5, h: 1.15, fill: C.paleViolet, size: 12 });
footnote(s, TRACE_SOURCE + ' 拦下的一例：results/scen-20260930/glm53-r3（M5-L2，论文宏 \\PubEx*）。');
s.addNotes('第一项职责：发布。一条规则不是学到就直接相信。内置智能体拿到一道给定业务口径的学习任务，用 7 次工具调用写出 SQL，答案正确——实验里用参考答案判定，部署中由负责这个指标的人确认一次。'
  + '然后大模型把零散的学习过程整理成知识卡：给智能体看的“怎么算”，和 MAVRA 保管的“什么时候这样算是安全的”。题目里的月份这类参数要剥掉，否则别人拿到的是写死 3 月的 SQL。'
  + '再过 7 项检查，第 7 项最重要：只凭知识卡编译出的 SQL 必须得到同样答案。实验里真拦下过一例：提取时丢了“电子”这个类别过滤，原来的智能体答 274.1 万是对的，但别人拿到的 SQL 会返回 1352.1 万。'
  + '发布时同时记下四类条件，这就是 v1 成立的前提。命题 1 说它们够用：都成立时每笔业务恰好计一次；但金额换单位这种取值层面的变化发现不了。');

// 7 Rely: declare, validate on the query's snapshot, execute ----------------------------------------
pres.addSection({ title: '依赖' });
s = content('依赖：使用 v2 时先声明，在同一快照上验证后执行', '依赖');
const call = (t) => ({ text: t, options: { fontFace: CODE, fontSize: 10 } });
heading(s, '用户智能体 B 的真实调用（没见过的题：“9 月的门店营业额”）', M, 1.1, W - 2 * M, C.blue);
table(s, [
  ['轮', '调用', 'MAVRA 做什么 → 返回'],
  ['1', call('find_metric("门店营业额")'), '依赖的表版本未变 → 返回当前修订 v2：口径、度量、粒度、注意事项、示例 SQL'],
  ['2', call('describe_table("store_sales"), describe_table("date_dim")'), '表版本未变 → 直接返回记住的表统计信息'],
  ['3', call('run_sql(sql, metrics: [{key: "metric:门店营业额", revision: 1}])'), '声明 v2：核对是当前修订 → 在这条查询的快照上验证 v2 的四个条件（命中缓存则复用）→ 执行 → 13,069,651.80'],
  ['4', call('final_answer(answer, used: ["r1"])'), '溯源：答案 ← 查询 #1 ← 门店营业额 v2'],
], { x: M, y: 1.45, w: W - 2 * M, colW: [0.45, 5.0, W - 2 * M - 5.45], size: 11 });
const hw = 5.9, hx2 = M + hw + 0.35, hw2 = W - M - hx2;
heading(s, '表版本 + 验证结果缓存：没变的数据不重复检查', M, 3.75, hw);
text(s, bulleted(null, C.blue, [
  '每张表一个版本号，由语句级触发器在写入事务内更新：看到写入就一定看到版本变化',
  '版本没变：直接复用验证结果，跨定义、跨智能体共享；变了：首次使用时只重验受影响的条件（增量加载后 6 条定义只验证 2 次）',
]), { x: M, y: 4.1, w: hw, h: 1.3, fontSize: 12, valign: 'top', paraSpaceAfter: 3 });
heading(s, '为什么要同一快照：检查通过 ≠ 执行时仍成立', hx2, 3.75, hw2, C.amber);
text(s, bulleted(null, C.amber, [
  '10:00:00 检查通过 → 10:00:01 别人插入一行重复记录并提交 → 10:00:02 执行：在已被破坏的数据上作答',
  'MAVRA：读版本、验证条件、执行 SQL 都在同一个可重复读的只读事务里；版本相同才复用验证结果（引理 1）',
]), { x: hx2, y: 4.1, w: hw2, h: 1.3, fontSize: 12, valign: 'top', paraSpaceAfter: 3 });
band(s, [
  { text: '实验：', options: { bold: true, color: C.blue } },
  { text: '并发写入下 11,297 次使用，0 次在违反条件的数据上作答；先检查后执行为 3.8–4.6%；读延迟不变。', options: { breakLine: true } },
  { text: '声明了已停用的版本 → 拒绝并要求重新取定义；没有声明 → 照常执行与审查，但不在保证范围内。' },
], { y: 5.55, h: 1.05, fill: C.paleBlue, size: 12 });
footnote(s, TRACE_SOURCE + ' 并发数字来自快照压力测试（论文宏 \\Sn*）；10:00 的时刻为示意。');
s.addNotes('第二项职责：依赖。这是另一个智能体 B 做一道没见过的题的真实调用，4 轮。它检索到门店营业额 v2，照着示例写出 SQL，执行时在 metrics 参数里声明依据的是 v2。'
  + 'MAVRA 收到声明后做三件事：核对 v2 还是当前修订；在这条查询的快照上验证 v2 的四个条件；然后在同一个快照上执行。'
  + '为什么不每次都把几百万行重新检查一遍？因为每张表有版本号，版本没变，以前的验证结果就能复用，而且所有定义、所有智能体共享。'
  + '为什么要在同一快照？因为 10:00:00 检查通过、10:00:01 别人插了一条重复记录、10:00:02 执行，答案就错了。把检查和执行放进同一个只读事务，相当于给账本拍一张照片，检查和计算都在这张照片上做。'
  + '实验里并发写入下一万多次使用，没有一次在被破坏的数据上作答。');

// 8 Maintain and improve: v1 -> v2 and v2 -> v3 -----------------------------------------------------
pres.addSection({ title: '维护与改进' });
s = content('维护与改进：v1 → v2 换更快的写法，v2 → v3 修复数据变化', '维护与改进');
const mw = (W - 2 * M - 0.35) / 2, mx2 = M + mw + 0.35;
heading(s, '改进 v1 → v2：候选 → 等价 → 更省 → 发布', M, 1.1, mw, C.amber);
table(s, [
  ['环节', '门店营业额的真实记录'],
  ['候选', '规则改写：期间改用日期键范围过滤，不连接日期表（没有规则候选时才请大模型提议）'],
  ['等价', '学习时快照上与 v1 结果相同；当前快照 14 个期间结果全部相同；新前提“日期键按月连续”成立'],
  ['更省', '同一快照内配对 EXPLAIN ANALYZE：29.1 → 23.3 ms（−19.8%），95% 区间 [−9.1, −2.5]'],
  ['发布', 'v2，新前提成为它的条件；全部 9 条定义都得到更快的修订（省 15.6%–36.1%），后续 15 条查询有 9 条采用'],
], { x: M, y: 1.45, w: mw, colW: [0.8, mw - 0.8], size: 12 });
heading(s, '修复 v2 → v3：在数据更正后的一次 find_metric 里完成', mx2, 1.1, mw, C.blue);
table(s, [
  ['环节', '门店营业额的真实记录'],
  ['发现', '表版本变了 → 粒度查询：1,055,610 行只有 989,695 个键 → v2 失效'],
  ['搜索', "在低基数列上找等值过滤，必须每键一行且不丢键：唯一可行 ss_is_current = '1'"],
  ['唯一', '若“当前行”和“备份行”两种过滤都通过，说不出哪份是事实 → 不选，失效并交给人'],
  ['回归', '按学习时刻重算 3 月：学习时的 SQL 与 v3 都是 1357.0 万 → 发布 v3（若用当前数据比：1489.1 对 1342.4，会误拒正确的修复）'],
  ['用时', '发现、搜索、回归都在这一次调用里完成：54.5 秒（两条同名定义），之后的请求直接拿到 v3'],
], { x: mx2, y: 1.45, w: mw, colW: [0.8, mw - 0.8], size: 12 });
band(s, [
  { text: '修不好时：', options: { bold: true, color: C.red } },
  { text: '整批重复加载，没有过滤能恢复唯一性 → 定义失效并通知使用方，等重新学到再发布。', options: { breakLine: true } },
  { text: '同一个发布通道：', options: { bold: true, color: C.blue } },
  { text: '改进和修复出来的修订都要过检查，新前提都成为条件，所有使用者共享结果；之后的智能体在 find_metric 里直接拿到 v3 和通知。' },
], { y: 5.15, h: 1.4, size: 13 });
footnote(s, TRACE_SOURCE + ' 优化轮：results/scen-20261008-opt；回归的“当前数据”一行来自对照实验 dsv41flash-r1-g3fix--exref。');
s.addNotes('第三项职责：维护与改进，正好对应例子里的两次版本变化。'
  + '左边是 v1 到 v2，改进：规则改写把按年月连接日期表改成按日期键范围过滤；先验证等价——学习时的数据上和当前数据的 14 个期间结果全部相同；再验证更省——同一快照里配对测执行时间，快了 19.8%，置信区间整体小于 0。'
  + '注意新写法多了一个前提：日期键按月连续，它被记成 v2 的条件，以后数据变了也会检查。实验里 9 条定义都得到了更快的版本，后来的智能体多数照着新写法写。'
  + '右边是 v2 到 v3，修复：数据更正后，下一个检索门店营业额的请求触发维护，发现 105 万行只有 99 万个键，v2 失效；在低基数列上找过滤，只有 ss_is_current = 1 能恢复每键一行且不丢键；'
  + '如果两个过滤都可行，比如当前行和备份行，MAVRA 不擅自选；最后按学习时刻重算 3 月，和当初答案一致才发布 v3。必须用当初的数据比，因为今天的数据上当初的 SQL 也过期了。'
  + '修不好就失效并通知，不猜。');

// 9 Results ----------------------------------------------------------------------------------------
pres.addSection({ title: '实验结果' });
s = content('实验结果：共享带来准确，维护让它在数据变化后仍然准确', '实验结果');
const tw = 7.3, rx2 = M + tw + 0.35, rw2 = W - M - rx2;
heading(s, '端到端：DeepSeek V4.1 Flash，3 次独立运行', M, 1.1, tw, C.blue);
table(s, [
  ['方法', '数据未变', '11 种更新后', '5 种破坏性更新', '单位变化（对照）'],
  ['无共享定义', '49%', '32%', '19%', '22%'],
  ['检索历史查询示例', '100%', '76%', '57%', '48%'],
  ['检索示例 + 提示自行验证', '100%', '77%', '63%', '48%'],
  ['按模式变更失效', '100%', '75%', '59%', '48%'],
  ['整定义重查', '100%', '82%', '74%', '48%'],
  [strong('MAVRA', C.blue), strong('100%', C.green), strong('81%', C.green), strong('73%', C.green), '48%'],
], { x: M, y: 1.45, w: tw, colW: [2.5, 1.05, 1.15, 1.4, 1.2], size: 12 });
heading(s, '系统层：不用大模型，只换维护方式', rx2, 1.1, rw2, C.blue);
text(s, bulleted(null, C.blue, [
  '配对回放 1,470 题次：覆盖的更新下 0 错答；按模式变更失效 629 错答；TPC-DS 上结论相同',
  '并发写入 11,297 次使用：0 次在违反条件的数据上作答；先检查后执行 3.8–4.6%',
  '按学习时刻回归：修复成功的数量与使用标准答案参照相同',
  '维护耗时为整定义重查的 14%；按表版本缓存验证查询也能做到，效率不是贡献',
]), { x: rx2, y: 1.45, w: rw2, h: 3.3, fontSize: 12, valign: 'top', paraSpaceAfter: 4 });
band(s, bulleted(null, C.blue, [
  '共享本身：数据未变时 49% → 100%，每题 5.6 → 3.6 轮；建立记忆每轮 18.1 万 token、283 s，按时间 5 道题、按 token 26 道题后回本',
  '维护：5 种破坏性更新下 73%，检索示例 57%，提示它自行验证也只有 63%；MAVRA 与整定义重查答案相同',
  '负结果：单位变化所有方法同样过期；定义失效又修不好时，使用者每题 9.36 万 token，比独自探索（2.69 万）更费——下一步把使用者找到的修正经准入共享',
]), { y: 4.95, h: 1.7, size: 12 });
footnote(s, '5 种破坏性更新：退货状态行、保留旧行的销售更正、重复加载、商品维度 SCD Type 2、日期键格式变更。来源：exp/2026-10-02-scenarios-ds、'
  + 'exp/2026-10-02-cache-baseline-tpcds、快照压力测试；代价与回本由 tools/sharing-stats.py 算出。与论文宏 \\Ds*、\\Rp*、\\Sn*、\\Am* 一致。');
s.addNotes('左边是端到端：同一批题，每种方法独立跑 3 次。共享本身的收益很大：数据没变时从 49% 到 100%，任何共享方法都有，不是 MAVRA 独有。'
  + '区别出现在数据变化之后：5 种破坏性更新下 MAVRA 73%，检索历史示例 57%，提示它自己验证也只有 63%。MAVRA 和整定义重查答案相同——两者用同样的条件和修复，只是重查更费。'
  + '右边是系统层，不用大模型，固定学到的定义，只换维护方式：覆盖的更新下没有错答；并发下没有误答；回归测试不需要参考答案。维护效率和通用缓存相当，这一点我们不当成贡献。'
  + '代价：建立记忆每轮 18 万 token、不到 5 分钟，按时间 5 道题就回本。负结果也如实说：单位变化谁都发现不了；定义失效又修不好时，使用者会自己去修，花的 token 比独自探索还多，这是下一步要解决的。');

// 10 Guarantees, limits, and the three sentences ---------------------------------------------------
pres.addSection({ title: '边界与总结' });
s = content('MAVRA 的保证边界，以及三句话总结', '边界与总结');
const bw = 7.2, bx2 = M + bw + 0.35, bw2 = W - M - bx2;
table(s, [
  ['发生了什么', 'MAVRA 能做什么'],
  ['订单多了一条旧记录，有唯一的当前标志', good('检测，并修复为新修订')],
  ['整个批次被重复加载', lines('检测重复，', '没有谓词能恢复唯一性 → 失效并通知')],
  ['主表与备份副本都看起来合理', lines('无法判断哪份是业务事实', '→ 不擅自选择，失效并交给人确认')],
  ['金额从“元”改成“美元”，行数与键不变', bad('四类条件发现不了（单位变化对照）')],
  ['日期键有效，但指向了错误的日期', bad('发现不了：取值语义不在条件范围内')],
  ['SQL 没有在 run_sql 的 metrics 参数里声明依据的定义', bad('照常执行与审查，但不在条件保证范围内')],
], { x: M, y: 1.2, w: bw, colW: [3.5, bw - 3.5], size: 13 });
[
  ['问题', '智能体学到的数据库知识共享给别人后，会因数据变化悄悄失效，而 SQL 照常执行、不报错。', C.red, C.grey],
  ['方法', '共享记忆层承担三项职责：只发布通过准入、带条件的知识；条件在查询快照上成立才允许依赖；数据变化后替所有使用者修复或失效，并发布更省的等价修订。', C.blue, C.paleBlue],
  ['结果', '破坏性更新下答对 73%（检索示例 57%）；覆盖的更新 0 错答；并发写入下 0 次在被破坏的数据上作答；建立记忆按时间 5 道题后回本。', C.violet, C.paleViolet],
].forEach(([label, body, color, pale], k) => {
  const y = 1.2 + k * 1.5;
  s.addShape('roundRect', { x: bx2, y, w: bw2, h: 1.4, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1 });
  text(s, label, { x: bx2 + 0.25, y: y + 0.1, w: 1.0, h: 0.4, fontSize: 16, bold: true, color });
  text(s, body, { x: bx2 + 0.25, y: y + 0.45, w: bw2 - 0.5, h: 0.9, fontSize: 12, valign: 'top' });
});
band(s, [
  { text: '两点要分清：', options: { bold: true, color: C.blue } },
  { text: 'MAVRA 不判断业务含义是否正确（含税还是不含税，需要有人给出可信的口径）；它也不保证每条 SQL 都对，保护的是遵守接口、声明了受管修订的查询。' },
], { y: 5.75, h: 0.95, size: 13 });
s.addNotes('MAVRA 是严谨的管理员，但不是无所不知。能做的：旧记录有唯一的当前标志，检测并修复；整批重复加载，检测但修不了，失效并通知；主表和备份都合理，不擅自选，交给人。'
  + '做不到的：金额换了单位、日期键指向错误日期，行数和键都没变，四类条件发现不了；智能体没声明用了哪个修订，也不在保证范围内。'
  + '两点要分清：MAVRA 不判断业务含义对不对，那需要有人给口径；它也不保证每条 SQL 都对，保护的是声明了受管修订的查询。'
  + '最后三句话：问题——学到的知识共享出去后会因数据变化悄悄失效，SQL 却不报错；方法——共享记忆层替使用者把住发布、依赖、维护与改进三关；'
  + '结果——破坏性更新下 73% 对 57%，覆盖的更新 0 错答，并发下 0 次误答，建立记忆很快回本。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
