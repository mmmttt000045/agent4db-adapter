// Builds docs/mavra-system.pptx, a 15-slide Chinese deck that tells MAVRA as one story:
// how it differs from Text-to-SQL; a shared rule breaks when the data changes (toy ledger, then the real record); the three
// things MAVRA does (what to check, when, what if it fails); where it sits; how a rule is
// admitted; the four conditions; table versions, lazy maintenance and the same-snapshot
// contract; repair with the uniqueness rule and the as-of regression test; the restatement
// story from the run record; two results slides; guarantees and limits. The three system
// figures come from tools/deck/figures/ (drawn by `python3 tools/figures/build.py --deck`,
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
s.addText('共享智能体学到的计算规则 · 记住规则成立的条件 · 数据变化后仍然正确', { placeholder: 'body' });
s.addNotes('很多数据智能体在同一个数据库上工作。一个智能体学会了怎么算“营业额”，别的智能体也想用；'
  + '但数据库每天都在更新，学到的规则可能在不知不觉中不再适用，而 SQL 照样能执行。'
  + 'MAVRA 是放在智能体与数据库之间的中间件：保存智能体学到的规则，记住规则成立的条件，在规则被使用时保证条件在实际执行的数据上仍然成立，条件被破坏时修复或禁用。'
  + '顺序：问题 → MAVRA 做的三件事 → 放在哪里 → 规则怎样存进去 → 检查什么 → 何时检查 → 失败后怎么办 → 一个完整的真实例子 → 实验 → 边界。');

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

// 3 What MAVRA does: three things = the paper's three questions ------------------------------
pres.addSection({ title: 'MAVRA' });
s = content('MAVRA 做三件事，对应论文的三个问题', 'MAVRA');
const cw = (W - 2 * M - 2 * 0.3) / 3;
[
  { n: 1, head: '记住规则成立的条件', sub: '检查什么', color: C.violet, pale: C.paleViolet,
    body: '从定义推出四类验证条件：粒度键唯一、连接基数 N:1、日期角色、日期键完整性。'
      + '条件与学习证据、表版本一起保存——不仅记住公式，还记住公式为什么成立。' },
  { n: 2, head: '使用前在实际执行的快照上检查', sub: '何时检查', color: C.blue, pale: C.paleBlue,
    body: '表版本未变：复用已有的验证结果；已变：在这条查询自己的快照内重新验证，通过后在同一快照上执行。'
      + '检查结果按（条件，表版本）缓存，跨定义、跨智能体共享。' },
  { n: 3, head: '唯一修复，否则失效', sub: '检查失败了怎么办', color: C.amber, pale: C.paleAmber,
    body: '恰好一个通过检查的修复：按学习时刻做回归测试，通过后发布新修订。'
      + '没有或不止一个：定义失效，通知使用方，交给人确认——宁可说“不知道怎么安全地修”，也不猜一个答案。' },
].forEach((c, k) => card(s, { ...c, x: M + k * (cw + 0.3), y: 1.25, w: cw, h: 3.5 }));
band(s, [
  { text: '整条逻辑链：', options: { bold: true, color: C.blue } },
  { text: '学到规则 → 记住它成立的条件 → 数据变化 → 使用前检查 → 安全则继续使用 → 不安全则尝试修复 → 修不好则失效并通知使用方。', options: { breakLine: true } },
  { text: 'MAVRA 不生成 SQL，也不判断业务含义；它保护的是“已经学会的规则在当前数据上还能不能用”。' },
], { y: 5.0, h: 1.5, size: 15 });
s.addNotes('把 MAVRA 想成一个很认真的账本管理员，它做三件事。'
  + '第一，记住规则成立的条件——比如每个订单号只能对应一笔有效销售。这对应论文的第一个问题：检查什么。'
  + '第二，使用规则前检查条件，而且是在这条查询实际执行的那份数据快照上检查。对应第二个问题：何时检查。'
  + '第三，条件不成立时，有唯一可靠的修法就修，否则禁止使用并通知。对应第三个问题：检查失败了怎么办。'
  + '整篇论文可以理解为给这三个问题各设计了一个可靠的答案。下面这条逻辑链是整个汇报的主线。');

// 4 Where it sits: architecture ------------------------------------------------------------------
s = content('MAVRA 放在哪里：智能体与数据库之间的中间件', 'MAVRA');
figure(s, 'overview', 1.15, 4.55);
band(s, [
  { text: '智能体看到的是工具：', options: { bold: true, color: C.blue } },
  { text: 'list_tables · describe_table · join_path · find_metric · run_sql（声明所依赖的指标修订）。', options: { breakLine: true } },
  { text: 'MAVRA 记四类记忆：', options: { bold: true, color: C.blue } },
  { text: '表统计信息、连接路径、指标定义、验证结果。最重要的是后两类：不仅记住公式，还记住公式成立的条件和最近一次检查是否通过。' },
], { y: 5.8, h: 0.9, size: 13 });
s.addNotes('原来智能体直接访问数据库，现在 MAVRA 放在中间，不替代智能体，也不替代数据库。'
  + '智能体看到的是一组工具：列出表、描述表、查询连接路径、检索指标定义、执行 SQL。'
  + '图中蓝色 1–5 是检索指标定义：智能体只说“营业额”，查询服务从共享记忆读出定义；表版本变了，缺少验证结果的条件交给维护执行，结果写入缓存，再返回有效修订 v2。'
  + '橙色 6–8 是执行 SQL：智能体声明依赖 v2，执行前验证复用缓存，在同一快照上执行。紫色是学习：内置智能体学到的定义通过准入检查后写入。'
  + 'MAVRA 记四类记忆：有什么表什么列、表之间怎么连、学会过哪些计算规则、这些规则依赖的条件最近检查是否通过。');

// 5 Admission: how a rule gets in ----------------------------------------------------------------
pres.addSection({ title: '检查什么' });
s = content('一条规则怎样存进去：准入', '检查什么');
const lw = 5.7, rx = M + lw + 0.35, rw = W - M - rx;
heading(s, '学习任务（给定业务口径）', M, 1.1, lw, C.violet);
s.addShape('roundRect', { x: M, y: 1.45, w: lw, h: 0.95, fill: { color: C.paleViolet }, line: { color: C.paleViolet }, rectRadius: 0.08 });
text(s, '3 月的门店营业额是多少？口径：门店营业额 = 门店销售行的净支付额（store_sales.ss_net_paid）之和，按销售日期归属期间。',
  { x: M + 0.2, y: 1.52, w: lw - 0.4, h: 0.8, fontSize: 13, valign: 'middle' });
text(s, [
  { text: '内置智能体 5 轮写出 SQL，答案 13,570,368.70 与参考答案一致 ✓', options: { bold: true, color: C.green, breakLine: true } },
  { text: '大模型将求解轨迹抽取为结构化定义（16.3 秒），7 项准入检查（5.7 秒）通过后发布为修订 v1。' },
], { x: M, y: 2.5, w: lw, h: 0.75, fontSize: 13, valign: 'top' });
heading(s, '写入记忆的定义（知识卡）v1', M, 3.35, lw, C.blue);
table(s, [
  ['给智能体看的', '度量 SUM(ss_net_paid)，无过滤谓词；粒度：销售日 × 小票号 × 商品；按销售日关联 date_dim；注意：不含税，内连接会排除 1.03% 未匹配行'],
  ['MAVRA 保管的', '验证条件：粒度键唯一、日期键唯一、日期键完整性；学习证据（学习时的 SQL、答案、表版本）、状态、修订号、使用者'],
], { x: M, y: 3.7, w: lw, colW: [1.45, lw - 1.45], size: 12 });
text(s, '智能体需要知道“怎么算”；MAVRA 需要知道“什么时候这样算是安全的”。',
  { x: M, y: 5.85, w: lw, h: 0.6, fontSize: 13, color: C.muted, valign: 'top' });
heading(s, '7 项准入检查', rx, 1.1, rw, C.violet);
table(s, [
  ['检查', '通俗地说'],
  ['1 业务依据', '规则有明确的业务口径，不是推测的'],
  ['2 答案判定正确', '当初的答案经独立判定是对的'],
  ['3 静态合法性', '列存在；连接沿已验证路径；没把题目里的月份写死'],
  ['4 粒度成立', '当前快照上粒度键唯一'],
  ['5 SQL 审查', '示例查询符合记录的粒度与连接要求'],
  ['6 重放示例 SQL', '当初的 SQL 重新执行，结果不变'],
  ['7 重放规范 SQL', '只凭这张知识卡编译出的 SQL 也得到同样答案'],
], { x: rx, y: 1.45, w: rw, colW: [1.9, rw - 1.9], size: 12 });
band(s, [
  { text: '第 7 项最重要：', options: { bold: true, color: C.violet } },
  { text: '其他智能体读到的只有这张知识卡。原来的智能体心里知道要过滤，知识卡没写，后来的智能体仍会算错。', options: { breakLine: true } },
  { text: '第 2 项在部署中：', options: { bold: true, color: C.violet } },
  { text: '实验用参考答案；部署中由指标负责人确认一次。此后维护与修复不再需要参考答案。' },
], { x: rx, y: 4.75, w: rw, h: 1.75, fill: C.paleViolet, size: 12 });
footnote(s, SOURCE);
s.addNotes('一条规则不是学到就直接相信，要走准入流程，像加入竞赛队要审核。'
  + '内置智能体拿到一道给定业务口径的学习任务，写出 SQL，答案正确。这一步 MAVRA 自己不能凭空知道业务规则对不对：实验里用参考答案，实际公司里由负责这个指标的人确认一次。'
  + '然后把零散的学习过程整理成一张知识卡，分两部分：给智能体看的“怎么算”，和 MAVRA 自己保管的“什么时候这样算是安全的”——验证条件、学习证据、表版本、使用者。'
  + '再过七道检查。第七道尤其重要：只凭这张知识卡重新编译出的 SQL 必须得到同样答案，因为别的智能体读到的只有这张卡，原来的智能体心里知道要过滤而卡上没写，后来的智能体就会算错。七道都通过才发布 v1。');

// 6 What is checked: the four conditions --------------------------------------------------------
s = content('检查什么：从定义推出的四类验证条件', '检查什么');
table(s, [
  ['条件', '通俗地说', '示意', '检查方式'],
  [strong('粒度键唯一', C.blue), '一件事不登记两次', '3 行只有 2 个订单号：002 出现了两次',
    '行数 = 不同键数（在定义的过滤谓词之下）'],
  [strong('连接基数 N:1', C.blue), '连接其他表不能把一行变两行', '门店表里门店 A 出现两次，一笔 100 元的销售连接后变成 200 元',
    '连接“1”侧的键唯一'],
  [strong('日期角色', C.blue), '一个日期键只连出一个日期，且按定义指定的日期（销售日而非退货日）', '销售日期键在日期维度中只有一行',
    '日期维键唯一'],
  [strong('日期键完整性', C.blue), '不能突然有大量记录找不到日期而漏算', '学习时 1.03% 的销售行关联不上日期；变成 8% 就不正常',
    '未匹配率 ≤ 学习时 + 0.1 个百分点'],
], { x: M, y: 1.2, w: W - 2 * M, colW: [1.6, 3.2, 4.1, 3.233], size: 13 });
band(s, [
  { text: '充分性命题（命题 1）：', options: { bold: true, color: C.blue } },
  { text: '业务前提成立且四类条件都成立时，规范 SQL 对每个期间把每笔业务事件恰好计一次；漏算只限于找不到日期键的那部分，并由完整性条件限定比例。', options: { breakLine: true } },
  { text: '它不保证一切：', options: { bold: true, color: C.red } },
  { text: '金额从元改成美元、日期键有效但指向错误日期——行数和键都没变，这四类条件发现不了。实验里的“单位变化”就是这样的对照。' },
], { y: 4.85, h: 1.75, size: 13 });
s.addNotes('MAVRA 从定义里推出四类条件。'
  + '粒度键唯一：每件事情只登记一次，检查行数是否等于不同键的数量，当然要在定义的过滤之下算。'
  + '连接基数：连接其他表时不能把一行变两行，比如门店表里同一个门店出现两次，一笔 100 元就会被算成 200 元；所以连接“1”那一侧的键必须唯一。'
  + '日期角色：一个日期键只能连出一个日期，而且要按定义指定的日期，销售日不能和退货日混。'
  + '日期键完整性：关联不上日期的记录会从按月统计里消失，学习时有 1.03%，允许 0.1 个百分点的容差，突然变成 8% 就不正常。'
  + '论文的充分性命题说：这四类条件都成立，规范 SQL 就把每笔业务事件恰好计一次。但它不保证一切，比如金额换了单位，行数和键都没变，发现不了——实验里的单位变化就是这个对照。');

// 7 When to check: table versions, lazy maintenance, the same snapshot --------------------------
pres.addSection({ title: '何时检查' });
s = content('何时检查：表版本、惰性维护，以及为什么要在同一快照内执行', '何时检查');
const hw = 6.1, hx2 = M + hw + 0.35, hw2 = W - M - hx2;
heading(s, '表版本 + 验证结果缓存：没变的数据不重复检查', M, 1.1, hw);
table(s, [
  ['时刻', 'store_sales 版本', '处理'],
  ['9:00', '10', '执行验证，记录“版本 10 上粒度键唯一”'],
  ['10:00', '10', '另一智能体使用：版本相同，直接复用'],
  ['14:00', '11', '有写入提交：旧结果不再适用，首次使用时重新验证受影响的条件'],
], { x: M, y: 1.45, w: hw, colW: [0.8, 1.8, hw - 2.6], size: 12 });
text(s, bulleted(null, C.blue, [
  '表版本由语句级触发器在写入事务内更新（分片计数器）：快照看到写入时一定也看到版本变化；DML 统计这类信号既不随事务提交也不即时',
  '惰性维护：更新后不立即全量重验，定义首次被使用时只重新验证与变化表相关的条件；实验中增量加载后 6 条定义仅执行 2 次验证',
]), { x: M, y: 3.35, w: hw, h: 1.7, fontSize: 12, valign: 'top', paraSpaceAfter: 4 });
heading(s, '为什么还要同一快照：检查通过 ≠ 执行时仍然成立', hx2, 1.1, hw2, C.amber);
table(s, [
  ['时刻', '发生了什么'],
  ['10:00:00', '验证通过：粒度键唯一'],
  ['10:00:01', '另一事务插入一行重复记录并提交'],
  ['10:00:02', '执行查询：在已被破坏的数据上作答，答案错误'],
], { x: hx2, y: 1.45, w: hw2, colW: [1.1, hw2 - 1.1], size: 12 });
text(s, bulleted(null, C.amber, [
  'MAVRA 的做法：run_sql 打开 REPEATABLE READ、READ ONLY 事务，在同一快照内读表版本、复用或重新验证条件、执行业务 SQL——其他人此时修改真实数据，不影响这条查询看到的那份',
  '引理 1：若两个快照看到的表版本相同，且每次写表都在同一事务内更新版本，则该版本上的验证结论可以安全复用——保证的是缓存复用安全，而不是“版本号相同就一定没事”',
]), { x: hx2, y: 3.35, w: hw2, h: 1.7, fontSize: 12, valign: 'top', paraSpaceAfter: 4 });
band(s, [
  { text: '实验：', options: { bold: true, color: C.blue } },
  { text: '并发写入下 11,297 次使用，MAVRA 0 次在违反条件的数据上作答；先检查后执行 3.8–4.6%；读延迟不变。' },
], { y: 5.3, h: 0.75, fill: C.paleBlue, size: 13 });
footnote(s, '时刻为示意；版本机制与引理见论文第 6 节；并发数字来自快照压力测试（\\Sn* 宏），增量加载的验证次数来自 ' + SOURCE.slice(3));
s.addNotes('100 个智能体每天都要查营业额，不能每问一次就把几百万行从头检查一遍。两个办法。'
  + '一是给每张表盖版本章：9 点在版本 10 上验证通过并记下来；10 点另一个智能体来用，版本没变，直接复用；下午 2 点有写入，版本变成 11，旧结论不再适用，等有人用时再重新验证受影响的条件。'
  + '版本必须可靠：由语句级触发器在写入事务内更新，看到写入就一定看到版本变化；PostgreSQL 自带的修改统计做不到这一点。'
  + '二是惰性维护：更新后不立即重验所有规则，使用时只验相关的条件。'
  + '但还有一个最容易被忽视的问题：10:00:00 检查通过，10:00:01 别人插入一条重复记录，10:00:02 执行查询就错了。检查正确不代表使用时还正确。'
  + 'MAVRA 用事务快照解决：在同一个可重复读的只读事务里读版本、验证条件、执行 SQL，相当于给账本拍一张照片，检查和计算都在这张照片上。'
  + '引理 1 说明什么时候可以复用验证结论。实验里并发写入下 11,297 次使用没有一次在被破坏的数据上作答。');

// 8 Reading and using: one request ----------------------------------------------------------------
s = content('读取与使用：一次请求的处理路径', '何时检查');
figure(s, 'lookup');
s.addNotes('上方是检索指标定义：名称匹配到“门店营业额”（电子品类的同名定义一并返回，由智能体按口径选择）；'
  + '比较 store_sales 的表版本（14 → 15）；逐个条件查缓存：“粒度键唯一”电子品类刚验证过，复用；date_dim 未变，复用；“日期键完整性”在版本 15 上没有结果，执行验证并写入缓存；返回有效修订 v2。'
  + '中间是验证结果缓存：按（条件，表版本）存储，写入者和复用步骤都标出来了。'
  + '下方是执行 SQL：先检查声明的 v2 是否有效；再在查询快照上验证——期间又有更新，表版本已是 16，两个条件在快照内重新验证并写入缓存；最后在同一快照上执行，得到 1293.3 万。');

// 9 What happens on failure: repair, uniqueness, regression ---------------------------------------
pres.addSection({ title: '失败后怎么办' });
s = content('检查失败了怎么办：唯一修复，按学习时刻回归，否则失效', '失败后怎么办');
heading(s, '修复：找一个谓词，恢复“每个键一行”且不丢键', M, 1.1, hw, C.amber);
table(s, [
  ['订单号', '金额', 'ss_is_current'],
  ['001', '100 元', '1'],
  ['002', '250 元', '1'],
  ['003', '300 元', '1'],
], { x: M, y: 1.45, w: hw, colW: [1.5, 1.6, hw - 3.1], size: 12 });
text(s, [{ text: "过滤 ss_is_current = '1' 之后：650 元 ✓", options: { bold: true, color: C.green } }],
  { x: M, y: 3.0, w: hw, h: 0.3, fontSize: 13, valign: 'middle' });
text(s, bulleted(null, C.amber, [
  '修复搜索在低基数列上枚举等值谓词，候选必须同时满足：过滤后每个键恰好一行；原有的键一个不丢（“只保留金额 > 200”能去重，但丢了订单 001，不算修复）',
  '唯一性：若 is_current = 1 与 is_backup = 1 都通过检查，表结构说不出哪一份是业务事实——不擅自选择，定义失效并交给人确认（实验中的“备份副本”）',
]), { x: M, y: 3.4, w: hw, h: 1.8, fontSize: 12, valign: 'top', paraSpaceAfter: 4 });
heading(s, '回归测试：新定义要在学习时的数据上复现当初的答案', hx2, 1.1, hw2, C.blue);
table(s, [
  ['比较所用的数据', '学习时的 SQL', '修复后的 v2', '结果'],
  ['学习时刻 as-of', '1357.0 万', '1357.0 万', good('一致 → 发布 v2')],
  ['当前数据', '1489.1 万', '1342.4 万', bad('不一致 → 误拒')],
], { x: hx2, y: 1.45, w: hw2, colW: [1.6, 1.25, 1.25, hw2 - 4.1], size: 12 });
text(s, bulleted(null, C.blue, [
  '像换一种解法重做老师已经判过的那道题：答案必须相同。但必须用当初那份数据——今天的数据已经变了，学习时的 SQL 在上面同样过期（把旧行也算进去得 1489.1 万），比不出新解法对不对',
  '学习时的答案是唯一被确认过的答案，所以修复不需要参考答案。数据仓库用时间旅行查询（FOR SYSTEM_TIME AS OF）取学习时刻的数据，原型保留学习时的副本',
]), { x: hx2, y: 3.0, w: hw2, h: 2.2, fontSize: 12, valign: 'top', paraSpaceAfter: 4 });
band(s, [
  { text: '发布 v2 之后：', options: { bold: true, color: C.blue } },
  { text: 'v1 失效，声明 v1 的查询被拒绝；修复期间到达的请求等待结果；其他定义遇到相同的条件失败直接复用验证结果与修复；修不好的定义失效并通知使用方，等学到新证据再发布。' },
], { y: 5.3, h: 0.95, fill: C.paleBlue, size: 13 });
footnote(s, '上表为示意；回归测试数字来自 ' + SOURCE.slice(3, SOURCE.indexOf('。') + 1)
  + '“当前数据”一行来自对照实验 dsv41flash-r1-g3fix--exref（系统记录：“结果 13423672.28 与期望 14890636.48 不一致”）。');
s.addNotes('回到订单 002。MAVRA 发现订单号重复，一行是旧记录，一行是当前记录。它去找一个过滤谓词：只保留 ss_is_current = 1，过滤后订单不再重复，总额 650 元。'
  + '但不能看到一个像样的条件就用。候选必须满足两件事：过滤后每个键恰好一行；原来的键一个不丢——“只保留金额大于 200”也能去重，但 100 元的订单没了，这不叫修复。'
  + '还要唯一：如果 is_current 和 is_backup 两个过滤都通过，表结构说不出哪份是业务事实，MAVRA 不擅自选，定义失效，交给人确认。宁可说不知道怎么安全地修，也不猜。'
  + '修复通过结构检查之后还要考一次试：像换一种解法重做老师判过的那道题，答案必须一样。必须用当初那份数据，因为今天的数据已经变了，当初的 SQL 在上面同样过期，我们实际跑过：按当前数据比，正确的修复会被拒绝。'
  + '通过后发布 v2，v1 失效。');

// 10 Lifecycle figure ------------------------------------------------------------------------------
s = content('一条定义的生命周期：学习、维护、修复、失效', '失败后怎么办');
figure(s, 'lifecycle', 1.15, 4.5);
band(s, [
  { text: '修订规则：', options: { bold: true, color: C.blue } },
  { text: '同结构再次学到 → 为原定义记一次佐证；同名不同结构 → 并存，由智能体依据口径选择；'
    + '其他定义遇到相同的条件失败 → 复用验证结果与修复；失效后 → 重新学习，通过准入检查再作为新修订发布。' },
], { y: 5.75, h: 0.95, size: 13 });
s.addNotes('把前面几页串在一张图上。内置智能体求解“3 月门店营业额”，判定正确、准入检查通过，发布 v1。'
  + '增量加载：条件仍成立，其他定义复用验证结果，仍为 v1。'
  + '数据更正：旧行标记为非当前，插入当前行——粒度键唯一不成立，v1 失效，不处理会把新旧版本都算进去。'
  + '修复搜索只有 ss_is_current = 1 可行；按学习时刻重算 3 月，结果一致，发布 v2。'
  + '红框是另一种结果：批次重复加载，没有谓词能恢复唯一性，定义失效并通知使用方，等待重新学习。');

// 11 The whole story on the real record ------------------------------------------------------------
pres.addSection({ title: '真实记录' });
s = content('完整的故事：数据更正之后，三条共享定义怎样一起被修好', '真实记录');
table(s, [
  ['', '事件', '系统记录'],
  ['1', '第一个智能体检索“电子品类门店营业额”。store_sales 的表版本已变，重新验证“粒度键唯一”',
    { text: [{ text: '不成立：', options: { color: C.red, bold: true } },
      { text: '1,065,915 行只有 1,000,000 个不同键（平均每键 1.07 行），耗时 5.5 秒 → v1 失效' }] }],
  ['2', '修复搜索：在低基数列上枚举等值谓词；4 项检查（静态合法性、粒度、SQL 审查、按学习时刻回归）',
    { text: [{ text: "唯一可行 ss_is_current = '1'，全部通过 → 发布 v2", options: { color: C.green, bold: true } }, { text: '（共 28.7 秒）' }] }],
  ['3', '第二个智能体检索“门店营业额”：同一张表、同一个粒度条件、同一个表版本',
    { text: [{ text: '复用验证结果与修复，' }, { text: '45.8 毫秒', options: { bold: true, color: C.blue } }, { text: '发布 v2' }] }],
  ['4', '“门店退货率”要连接 store_sales 与 store_returns', "连接路径现在要求谓词 ss_is_current = '1' → 同样修复为 v2"],
  ['5', '通知使用方：旧修订已被替代，请使用新修订',
    { text: [{ text: '智能体 B 收到 3 条通知，SQL 带上该谓词，答 ' }, { text: '1293.3 万 ✓', options: { color: C.green, bold: true } }, { text: '（4 轮）' }] }],
], { x: M, y: 1.2, w: W - 2 * M, colW: [0.45, 5.8, 5.883], size: 13 });
band(s, [
  { text: '这页要说明的不是“修得快”，而是：', options: { bold: true, color: C.blue } },
  { text: '一个智能体发现了共享知识的问题，MAVRA 修好后，所有相关智能体得到一致的新修订；同一个问题不必每个智能体各自重新发现、重新解决。', options: { breakLine: true } },
  { text: '三种更新的结果：', options: { bold: true, color: C.blue } },
  { text: '增量加载——条件仍成立，保持 v1（6 条定义仅 2 次验证）；数据更正——v1 → v2，1293.3 万 ✓；重复加载——无唯一修复，失效并通知，智能体自行去重，3 次运行中 2 次答对。' },
], { y: 5.0, h: 1.7, size: 13 });
footnote(s, SOURCE);
s.addNotes('把整套系统的合作串起来。三条共享定义——电子品类营业额、门店营业额、退货率——都依赖同一张销售表。数据更正之后：'
  + '第一个智能体来检索电子品类营业额，MAVRA 发现表版本变了，一验证，106 万行只有 100 万个键，重复了，v1 失效；修复搜索找到唯一可行的谓词，四项检查通过，发布 v2，共 28.7 秒。'
  + '第二个智能体来检索门店营业额，依赖同一张表、同一个条件、同一个版本，验证结果和修复直接复用，45.8 毫秒。'
  + '退货率要连接销售表，连接路径现在也要求这个谓词，同样修复。最后相关智能体收到通知，按新修订写 SQL，答案正确。'
  + '这页的重点不是快，而是一个智能体发现的问题修好后，所有相关智能体得到一致的新知识。');

// 12 Results: end to end ---------------------------------------------------------------------------
pres.addSection({ title: '实验结果' });
s = content('实验结果①：端到端（DeepSeek V4.1 Flash，3 次独立运行）', '实验结果');
table(s, [
  ['方法', '数据未变（15 题）', '11 种更新后（全部）', '其中 5 种破坏性更新', '单位变化（对照）', '备份副本（修复有歧义）'],
  ['无共享定义', '49%', '32%', '19%', '22%', '44%'],
  ['检索历史查询示例', '100%', '76%', '57%', '48%', '72%'],
  ['检索示例 + 提示自行验证', '100%', '77%', '63%', '48%', '67%'],
  ['按模式变更失效', '100%', '75%', '59%', '48%', '61%'],
  ['逐写入失效', '100%', '79%', '69%', '52%', '50%'],
  ['整定义重查', '100%', '82%', '74%', '48%', '61%'],
  [strong('MAVRA', C.blue), strong('100%', C.green), strong('81%', C.green), strong('73%', C.green), '48%', '56%'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [2.9, 1.8, 1.9, 2.0, 1.6, 1.933], size: 14 });
band(s, bulleted(null, C.blue, [
  '共享本身：数据未变时 49% → 100%，每题 5.6 → 3.6 轮，输入 token −34%（任何共享方法均获得）；216 个固定库会话中每任务 37.7 s，无共享 64.5 s',
  '维护：更新后 75% → 81%，破坏性更新下 59% → 73%；MAVRA 与整定义重查答案相同，差异来自各次运行学到的定义不同',
  '对照与负结果：单位变化不违反任何条件，所有方法同样过期；备份副本下修复有歧义，MAVRA 使定义失效，检索示例碰巧答对',
]), { y: 5.0, h: 1.7, size: 13 });
footnote(s, '5 种破坏性更新：退货状态行、保留旧行的销售更正、重复加载、商品维度 SCD Type 2、日期键格式变更。'
  + '来源：exp/2026-10-02-scenarios-ds、exp/2026-10-03-session-latency，与论文宏 \\Ds*、\\ScenHold*、\\Sl* 一致。');
s.addNotes('端到端实验：DeepSeek V4.1 Flash 智能体，每种方法独立运行 3 次，15 道留出题，再加 11 种数据更新。'
  + '共享本身的收益：数据未变时准确率从 49% 到 100%，轮数和 token 都下降——任何共享方法都有这个收益，不是 MAVRA 独有。'
  + '维护的收益：更新后从 75% 到 81%，5 种破坏性更新下从 59% 到 73%；检索历史示例即使提示它自行验证也只有 63%。MAVRA 与整定义重查答案相同，差异来自各次运行学到的定义不同。'
  + '两个对照：单位变化不违反任何条件，所有方法同样过期，与命题的范围一致；备份副本下修复有歧义，MAVRA 按规则使定义失效，检索示例碰巧答对，这是如实保留的负结果。'
  + '这些数字来自我们设定的实验，不是说在所有数据库和模型上都能达到。');

// 13 Results: system level -------------------------------------------------------------------------
s = content('实验结果②：系统层（无大模型，固定定义库，只改变维护方式）', '实验结果');
table(s, [
  ['实验', '设置', '结果'],
  ['配对回放（合成数据）', '3 种大模型学到的 15 个定义库、97 条定义；11 种更新；1,470 题次',
    lines({ text: 'MAVRA 933 题正确，覆盖的更新下 0 错答；99 错答全部为单位变化', options: { bold: true, color: C.green } },
      '按模式变更失效：629 错答；整定义重查与 MAVRA 逐题相同')],
  ['配对回放（TPC-DS）', '由 99 个查询模板导出 93 条定义，SF1，981 题次',
    lines({ text: 'MAVRA 630 题正确，错答 72（单位变化）', options: { bold: true, color: C.green } }, '按模式变更失效：437 错答')],
  ['同快照验证', '并发写入，11,297 次使用',
    lines({ text: '在违反条件的数据上作答：0 次', options: { bold: true, color: C.green } }, '先检查后执行：3.8–4.6%；读延迟不变')],
  ['修复的回归基准', '合成 1,470 / TPC-DS 981 题次',
    lines({ text: '按学习时刻 as-of 查询：933 / 630，与使用标准答案参照相同', options: { bold: true, color: C.green } },
      '按当前数据：780 / 360（误拒正确的修复）')],
  ['维护成本', '19 条共享定义，错峰到达',
    lines('为整定义重查耗时的 14.0%：很多定义依赖同一张表的同一个条件，只验共享的条件', '按表版本缓存验证查询可得同样节省（16.7%）；100 万到 1,600 万行比例不变')],
], { x: M, y: 1.25, w: W - 2 * M, colW: [2.2, 4.0, 5.933], size: 14 });
band(s, [
  { text: '结论：', options: { bold: true, color: C.blue } },
  { text: '覆盖的更新全部检测到，不向使用方返回错误答案；修复以学习时刻为基准，不需要参考答案；同快照验证消除并发写入下的失效窗口。'
    + '维护效率与通用缓存相当，不是本文的贡献。' },
], { y: 5.85, h: 0.85, fill: C.paleBlue, size: 14 });
footnote(s, '来源：exp/2026-10-02-cache-baseline-tpcds（配对回放、回归基准、维护成本）、快照压力测试（同快照验证），'
  + '与论文宏 \\Rp*、\\Tr*、\\Sn*、\\CbStag* 一致。错答 = 在条件已被破坏的数据上照常返回答案。');
s.addNotes('系统层实验不用大模型：固定各次运行学到的定义库，只改变维护方式，比较的是机制本身。'
  + '配对回放：合成数据 1,470 题次，MAVRA 在覆盖的更新下没有错答，99 个错答全部是单位变化这个对照；按模式变更失效有 629 个错答。TPC-DS 上用 99 个查询模板导出的定义，结论一致。'
  + '同快照验证：并发写入下 11,297 次使用没有一次在违反条件的数据上作答，先检查后执行有 3.8% 到 4.6%。'
  + '修复的回归基准：按学习时刻比较，修复成功的数量与使用标准答案参照完全相同；按当前数据比较会误拒正确的修复。'
  + '维护成本：19 条定义时为整定义重查的 14%，因为很多定义依赖同一张表的同一个条件；但按表版本缓存验证查询也能得到同样的节省，所以效率不是本文的贡献，贡献在于检查什么、何时可以依赖检查结果、失败后怎么办。');

// 14 Guarantees, limits, and the three sentences ---------------------------------------------------
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
  ['智能体没有声明所依赖的指标修订', bad('不在执行保证范围内')],
], { x: M, y: 1.2, w: bw, colW: [3.5, bw - 3.5], size: 13 });
[
  ['问题', 'AI 学会的计算规则会因数据变化而不再正确，但 SQL 仍能正常执行。', C.red, C.grey],
  ['方法', 'MAVRA 不仅保存规则，还保存规则成立的条件；使用时保证这些条件在实际执行的数据快照上仍然成立。', C.blue, C.paleBlue],
  ['贡献', '条件被破坏后，只有找到唯一且通过回归测试的修复才发布新修订，否则让旧修订失效，防止错误知识继续传播。', C.violet, C.paleViolet],
].forEach(([label, body, color, pale], k) => {
  const y = 1.2 + k * 1.45;
  s.addShape('roundRect', { x: bx2, y, w: bw2, h: 1.3, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1 });
  text(s, label, { x: bx2 + 0.25, y: y + 0.12, w: 1.0, h: 0.4, fontSize: 16, bold: true, color });
  text(s, body, { x: bx2 + 0.25, y: y + 0.5, w: bw2 - 0.5, h: 0.75, fontSize: 13, valign: 'top' });
});
band(s, [
  { text: '两点要分清：', options: { bold: true, color: C.blue } },
  { text: 'MAVRA 不判断业务含义是否正确（含税还是不含税，需要有人给出可信的口径）；它也不保证每条 SQL 都对，保护的是遵守接口、声明了受管修订的查询。' },
], { y: 5.75, h: 0.95, size: 13 });
s.addNotes('MAVRA 是严谨的管理员，但不是无所不知。能做的：旧记录有唯一的当前标志，检测并修复；整批重复加载，检测但修不了，失效并通知；主表和备份都合理，不擅自选，交给人。'
  + '做不到的：金额换了单位、日期键指向错误日期，行数和键都没变，四类条件发现不了；智能体没声明用了哪个修订，也不在保证范围内。'
  + '两点要分清：MAVRA 不判断业务含义对不对，那需要有人给口径；它也不保证每条 SQL 都对，保护的是声明了受管修订的查询。'
  + '最后三句话：问题——学会的规则会因数据变化而失效，SQL 却不报错；方法——保存规则成立的条件，使用时在实际执行的快照上保证成立；贡献——只有唯一且通过回归测试的修复才发布，否则失效，不让错误知识传播。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
