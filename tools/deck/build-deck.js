// Builds docs/mavra-system.pptx, a 19-slide Chinese deck that tells MAVRA as one story:
// how it differs from Text-to-SQL; a shared rule breaks when the data changes (toy ledger, then the real record); the three
// responsibilities of the shared memory layer (publish, rely, maintain and improve); where it sits, its tools and the
// traced learning and use calls; publish: admission and the four conditions; rely: table versions, lazy maintenance and
// the same-snapshot contract; maintain and improve: repair with the uniqueness rule and the as-of regression test, then
// optimization revisions, then the lifecycle figure; the restatement as traced; two results slides; guarantees and
// limits. One running example numbers the revisions: 门店营业额 v1 (learned) → v2 (optimized) → v3 (repaired). The three system
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
  + '顺序：问题 → MAVRA 承担的三项职责 → 放在哪里 → 发布 → 依赖 → 维护与改进 → 一个完整的真实例子 → 实验 → 边界。');

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
s = content('MAVRA 承担三项职责，对应论文的三个问题', 'MAVRA');
const cw = (W - 2 * M - 2 * 0.3) / 3;
[
  { n: 1, head: '发布', sub: '什么可以进入共享记忆', color: C.violet, pale: C.paleViolet,
    body: '只接收判题成功的任务；提取成结构化定义，剥离题目参数；7 项准入检查，'
      + '包括重放其他智能体将读到的规范 SQL；连同四类验证条件保存为修订 v1。'
      + '实验中拦下一例：提取时丢了类别过滤，规范 SQL 返回 1352.1 万，正确值 274.1 万。' },
  { n: 2, head: '依赖', sub: '一次使用何时可以依赖它', color: C.blue, pale: C.paleBlue,
    body: '智能体在 run_sql 中声明所依据的修订。表版本未变：复用已有的验证结果；已变：在这条查询自己的快照内重新验证，'
      + '通过后在同一快照上执行。验证结果按（条件，表版本）缓存，跨定义、跨智能体共享。' },
  { n: 3, head: '维护与改进', sub: '为所有使用者只做一次', color: C.amber, pale: C.paleAmber,
    body: '条件失败：恰好一个修复且按学习时刻回归通过，才发布新修订；否则失效并通知。'
      + '仍然有效：找到等价且更省的写法，抽样期间结果一致、配对测量更快，才发布新修订；'
      + '新写法依赖的前提（日期键按月连续）作为条件一并维护。' },
].forEach((c, k) => card(s, { ...c, x: M + k * (cw + 0.3), y: 1.25, w: cw, h: 3.5 }));
band(s, [
  { text: '整条逻辑链：', options: { bold: true, color: C.blue } },
  { text: '学到规则 → 准入后发布（带条件）→ 使用时声明修订 → 在查询快照上验证后执行 → 数据变化后维护：能修则修，修不好则失效并通知 → 有更省的等价写法则发布新修订。', options: { breakLine: true } },
  { text: 'MAVRA 不生成 SQL，也不判断业务含义；它决定共享的知识能否发布、能否被依赖，并替所有使用者维护它。' },
], { y: 5.0, h: 1.5, size: 15 });
footnote(s, '被拦下的一例：noctis results/scen-20260930/glm53-r3（M5-L2 电子品类门店营业额，准入第 7 项规范 SQL 重放），与论文宏 \\PubEx* 一致。');
s.addNotes('把 MAVRA 想成一个很认真的账本管理员，它替所有用账本的人做三件事。'
  + '第一，发布：一个智能体做对了一道题，不等于它的整条轨迹都值得别人相信。MAVRA 只把可复用的部分提取成结构化定义，把题目里的月份这类参数剥掉，'
  + '再检查别人将要读到的规范 SQL 能不能复现答案。实验里真有一例：提取时丢了“电子”类别过滤，规范 SQL 返回 1352.1 万，正确是 274.1 万，被准入拦下。'
  + '第二，依赖：别人用这条规则时，要在 run_sql 里声明依据哪个修订；MAVRA 在这条查询实际执行的那份数据快照上确认条件成立，才执行。'
  + '第三，维护与改进：数据变了，由 MAVRA 检查一次、修复一次，所有使用者共享结果；有唯一可靠的修法就修，否则禁止使用并通知。'
  + '规则仍然有效时，如果找到等价且更快的写法，也作为新修订发布给所有人，新写法依赖的前提同样受维护。'
  + '整篇论文就是给这三个问题各设计了一个可靠的答案。下面这条逻辑链是整个汇报的主线。');

// 4 Where it sits: architecture ------------------------------------------------------------------
s = content('MAVRA 放在哪里：智能体与数据库之间的中间件', 'MAVRA');
figure(s, 'overview', 1.1, 4.2);
band(s, [
  { text: '智能体看到的是工具：', options: { bold: true, color: C.blue } },
  { text: 'list_tables · describe_table · join_path · find_metric(名称) · run_sql(sql, metrics=[{key, revision}])——metrics 参数就是“声明”：这条 SQL 依据哪条定义的哪个修订。'
    + 'MAVRA 记四类记忆：表统计信息、连接路径、指标定义、验证结果。', options: { breakLine: true } },
  { text: '谁参与：', options: { bold: true, color: C.blue } },
  { text: '学习——内置智能体（大模型）求解给定口径的任务，抽取模型整理成定义，7 项准入检查自动执行，人只在“答案判定正确”确认一次；'
    + '使用——用户智能体检索、声明、执行；维护——由数据更新后第一个用到该定义的请求触发，MAVRA 执行，期间到达的请求等待结果；'
    + '优化——学习之后 MAVRA 自动做一轮；修复有歧义时才交给人。' },
], { y: 5.35, h: 1.4, size: 12 });
s.addNotes('原来智能体直接访问数据库，现在 MAVRA 放在中间，不替代智能体，也不替代数据库。'
  + '智能体看到的是一组工具：列出表、描述表、查询连接路径、检索指标定义、执行 SQL。'
  + '图中蓝色 1–5 是检索指标定义：智能体只说“营业额”，查询服务从共享记忆读出定义；表版本变了，缺少验证结果的条件交给维护执行，结果写入缓存，再返回有效修订 v2。'
  + '橙色 6–8 是执行 SQL：智能体声明依赖 v2，执行前验证复用缓存，在同一快照上执行。紫色是学习：内置智能体学到的定义通过准入检查后写入。'
  + 'MAVRA 记四类记忆：有什么表什么列、表之间怎么连、学会过哪些计算规则、这些规则依赖的条件最近检查是否通过。');

// 4a Every tool an agent can call: parameters, what MAVRA does, what comes back --------------------
s = content('智能体能调用的全部工具：参数、MAVRA 做什么、返回什么', 'MAVRA');
const mono = (t) => ({ text: t, options: { fontFace: CODE, fontSize: 9 } });
table(s, [
  ['工具', '参数', 'MAVRA 做什么（读 / 写哪类记忆）', '返回'],
  [mono('list_tables'), '—', '读目录', '表名、估计行数、列数、注释'],
  [mono('describe_table'), mono('table'), '表版本未变：返回记住的表统计信息；已变：重新采样并写入（表统计信息）',
    mono('{table, row_count, columns:[{name, type, null_ratio, distinct_est, common_values}], sample_rows, source: reused|explored}')],
  [mono('join_path'), mono('table_a, table_b'), '已有验证过的连接路径：直接返回；没有：按列名找候选，抽样扇出 + 行数守恒 + 键唯一验证，写入路径与证伪的写法（连接路径）',
    mono('{paths:[{left, right, on, cardinality, filters, loss_ratio}], known_bad:[{on, reason, fanout}], source}')],
  [mono('check_join'), mono('left, right, on'), '验证一个具体的连接写法，结果同样写入（连接路径）', mono('{valid, path | bad, source}')],
  [mono('find_metric'), mono('query, tables?'), '名称 / 别名匹配；依赖表版本已变：先维护（重新验证 → 修复或失效）；记下使用者（指标定义、验证结果）',
    mono('{metrics:[{key, revision, definition, fact, measure, grain, time, joins, filters, caveats, examples}], ambiguous, unavailable:[{key, revision, status}]}')],
  [mono('run_sql'), mono('sql, metrics?: [{key, revision}]'), '只读检查；声明的修订：核对有效且为当前，在这条查询的快照上验证其条件；执行前审查（证伪的连接写法、必需的粒度过滤）；记录溯源（验证结果、使用记录）',
    mono('{result:{columns, rows, row_count}, ref: "rN", source: executed|reused|snapshot} 或 {rejected, reason, suggestion | required_filter}')],
  [mono('final_answer'), mono('answer, used:["rN"], derivation'), '结束任务；按算式核算答案；溯源：答案 ← 查询 #N ← 声明的定义修订', '—'],
  [mono('ask_clarification'), mono('question'), '口径不明且工具无法给出时结束任务', '—'],
  ['每次返回', '—', '附带 notices（使用记录）', mono('notices: ["你用过的经验「…」已撤销（…）", "已发布等价且更省的修订 rN…"]')],
], { x: M, y: 1.15, w: W - 2 * M, colW: [1.4, 2.3, 4.7, 3.733], size: 10 });
band(s, [
  { text: '编号约定：', options: { bold: true, color: C.blue } },
  { text: '贯穿全场的例子“门店营业额”依次有 v1（学到）→ v2（优化为日期键范围）→ v3（数据更正后修复）三个修订。调用原文里的 revision: N 即 v(N+1)；'
    + 'ref / used / derivation 里的 rN 是本会话第 N 条查询的结果，下文写作“查询 #N”。', options: { breakLine: true } },
  { text: '内置智能体用同一套工具学习，', options: { bold: true, color: C.violet } },
  { text: '判定正确后由抽取模型整理成知识卡（不含业务行）。轨迹检索基线另有 find_trajectory(query)，不做维护。' },
], { y: 5.95, h: 0.8, size: 10 });
s.addNotes('这是智能体能调用的全部工具，一行一个：参数是什么，MAVRA 在背后读写哪类记忆，返回什么字段。'
  + '前四个是探索工具，结果都会记下来给后来的智能体复用；find_metric 是读取定义，依赖表版本变了会先维护；run_sql 带 metrics 参数就是声明，MAVRA 据此核对修订、在快照上验证条件、记录溯源；'
  + 'final_answer 提交答案并说明用了哪几条查询；每次返回都可能附带通知。内置智能体用同一套工具做学习任务，学到的轨迹再由抽取模型整理成知识卡。');

// 4b Learning: the built-in agent's real tool calls (from the trace) ---------------------------------
s = content('学习：内置智能体 A 的真实调用序列（M1-L1，5 轮 7 次）', 'MAVRA');
const call = (t) => ({ text: t, options: { fontFace: CODE, fontSize: 10 } });
table(s, [
  ['轮', '调用', 'MAVRA 返回', '耗时'],
  ['1', call('list_tables()'), '表名、估计行数、注释', '0 ms'],
  ['1', call('find_metric("门店营业额")'), '{metrics: [], note: "没有匹配的已验证指标口径"} —— 还没人学过', '0 ms'],
  ['2', call('describe_table("store_sales")'), '列、类型、空值比例、不同值数、样例：ss_sold_date_sk 空值 1.03%，ss_net_paid …', '133 ms'],
  ['2', call('describe_table("date_dim")'), 'd_date_sk、d_year {2000,2001,2002}、d_moy …；注释“2000-01-01 至 2002-12-31”', '3 ms'],
  ['3', call('join_path("store_sales", "date_dim")'), '{paths: [{on: [ss_sold_date_sk = d_date_sk], right_unique: true, loss_ratio: 1.03%, evidence: "1000000 行中 989695 行关联得上"}], known_bad: [], source: explored}', '155 ms'],
  ['4', call('run_sql("SELECT ROUND(SUM(ss.ss_net_paid), 2) FROM store_sales ss JOIN date_dim d ON … WHERE d.d_year = 2001 AND d.d_moy = 3")'),
    '{result: [["13570368.70"]], ref: "r1", source: executed}', '31 ms'],
  ['5', call('final_answer(answer: "13570368.70", used: ["r1"], derivation: "r1")'), '任务结束；答案 ← 查询 #1', '—'],
], { x: M, y: 1.15, w: W - 2 * M, colW: [0.4, 4.6, 6.3, 0.833], size: 11 });
band(s, [
  { text: '智能体退出之后，MAVRA 接着做：', options: { bold: true, color: C.violet } },
  { text: '① 判定：答案与参考答案一致（部署中由指标负责人确认一次）；② 抽取：把题面、查询 #1 的 SQL 与算式、被拦下的写法、两张表的元数据与已验证连接交给抽取模型，得到知识卡 JSON；'
    + '③ 7 项准入检查：业务依据、判定正确、静态合法、粒度（select count(*), count(distinct 粒度键) from store_sales …）、SQL 审查、重放查询 #1 的 SQL、重放由字段编译的规范 SQL；'
    + '④ 发布 metric:门店营业额 v1（revision 0），写入依赖的表版本与证据。' + LEARN_TIMING },
], { y: 5.0, h: 1.7, size: 12 });
footnote(s, TRACE_SOURCE);
s.addNotes('这是内置智能体学习时真实的 7 次工具调用，来自带 --trace 的运行记录。第 1 轮它并行调了两个工具：列出表，以及检索“门店营业额”——此时还没人学过，返回空。'
  + '第 2 轮描述两张表，第 3 轮问两张表怎么连接，MAVRA 现场验证并记下这条连接路径（一侧键唯一，1.03% 关联不上）。第 4 轮执行 SQL 得到查询 #1，第 5 轮提交答案并说明答案就是查询 #1。'
  + '智能体退出后 MAVRA 接着做四件事：判定、抽取、7 项准入检查、发布 v1。');

// 4c Use: the user agent's real tool calls on a held-out question -----------------------------------
s = content('使用：用户智能体 B 的真实调用序列（留出题 M1-P1，4 轮 6 次）', 'MAVRA');
table(s, [
  ['轮', '调用', 'MAVRA 做什么 → 返回', '耗时'],
  ['1', call('list_tables()'), '表名、估计行数、注释', '0 ms'],
  ['1', call('find_metric("门店营业额")'),
    '名称匹配到 2 条（门店营业额、门店营业额#2，都是 v2，即优化后的 revision 1）；依赖表版本未变 → {ambiguous: true, metrics: [{key: "metric:门店营业额", revision: 1, definition, measure: sum(ss_net_paid), grain, time, caveats: ["不含税…", "期间谓词按日期键范围过滤，前提是日期键按月连续…"], examples}]}', '4 ms'],
  ['2', call('describe_table("store_sales")  describe_table("date_dim")'), '表版本未变 → 直接返回记住的表统计信息', '3 ms'],
  ['3', call('run_sql("select round(sum(ss_net_paid), 2) as value from store_sales where ss_sold_date_sk between (select min(d_date_sk) from date_dim where d_year = 2002 and d_moy = 9) and (select max(d_date_sk) …)", metrics: [{key: "metric:门店营业额", revision: 1}])'),
    '声明 v2：核对有效且为当前修订；在这条查询的快照上验证 v2 的条件（粒度键唯一、日期键唯一、日期键完整性、日期键按月连续，命中缓存则复用）；执行 → {result: [["13069651.80"]], ref: "r1"}（查询 #1）', '24 ms'],
  ['4', call('final_answer(answer: "13069651.80", used: ["r1"], derivation: "r1")'), '溯源：答案 ← 查询 #1 ← metric:门店营业额 v2', '—'],
], { x: M, y: 1.15, w: W - 2 * M, colW: [0.4, 4.6, 6.3, 0.833], size: 11 });
table(s, [
  ['声明的修订…', 'MAVRA 的回应（运行记录原文）'],
  ['已被修复替代（数据更正后仍声明修复前的修订）', bad('拒绝：“指标经验 metric:门店营业额 已修订为 r1（你引用的是 r0），请重新调用 find_metric”')],
  ['已失效（重复加载后）', bad('拒绝：“当前不可用：已撤销：粒度守卫失败：store_sales(ss_item_sk, ss_ticket_number) 是否唯一，1110165 行只有 1000000 个不同键”')],
  ['已被等价且更省的修订替代', good('接受，附通知：“已发布等价且更省的修订 r1（你引用的 r0 仍可用），建议重新调用 find_metric”')],
  ['没有声明', '照常执行与审查（连接写法、粒度过滤），但不在“条件成立”的保证范围内'],
], { x: M, y: 4.7, w: W - 2 * M, colW: [3.2, 8.933], size: 10 });
footnote(s, TRACE_SOURCE + ' v2 是优化轮发布的日期键范围修订（第 14 页）。拒绝文字取自 results/scen-20261002（未做优化，r1 即修复后的修订）。');
s.addNotes('这是用户智能体做留出题时真实的 6 次调用。第 1 轮并行：列出表，检索“门店营业额”——匹配到两条、都是 v2（优化后的修订），MAVRA 看依赖表版本没变，直接返回定义、度量、粒度、注意事项和示例。'
  + '第 2 轮描述两张表，直接拿到记住的统计信息。第 3 轮执行 SQL，并在 metrics 参数里声明依据 metric:门店营业额 v2——注意它照着示例写出了日期键范围的写法。'
  + 'MAVRA 核对 v2 有效且是当前修订，在这条查询的快照上验证 v2 的四个条件，执行，返回查询 #1。第 4 轮提交答案，溯源记下答案来自查询 #1、查询 #1 依据门店营业额 v2。'
  + '下面是声明的修订处在另外四种状态时 MAVRA 的真实回应。');

// 5 Admission: how a rule gets in ----------------------------------------------------------------
pres.addSection({ title: '发布' });
s = content('发布：一条规则怎样进入共享记忆（准入）', '发布');
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
s = content('发布时一并记下：从定义推出的四类验证条件', '发布');
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
pres.addSection({ title: '依赖' });
s = content('依赖：表版本、惰性维护，以及为什么要在同一快照内执行', '依赖');
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
s = content('读取与使用：一次请求的处理路径', '依赖');
figure(s, 'lookup');
s.addNotes('上方是检索指标定义：名称匹配到“门店营业额”（电子品类的同名定义一并返回，由智能体按口径选择）；'
  + '比较 store_sales 的表版本（14 → 15）；逐个条件查缓存：“粒度键唯一”电子品类刚验证过，复用；date_dim 未变，复用；“日期键完整性”在版本 15 上没有结果，执行验证并写入缓存；返回有效修订 v2。'
  + '中间是验证结果缓存：按（条件，表版本）存储，写入者和复用步骤都标出来了。'
  + '下方是执行 SQL：先检查声明的 v2 是否有效；再在查询快照上验证——期间又有更新，表版本已是 16，两个条件在快照内重新验证并写入缓存；最后在同一快照上执行，得到 1293.3 万。');

// 9 What happens on failure: repair, uniqueness, regression ---------------------------------------
pres.addSection({ title: '维护与改进' });
s = content('维护：检查失败时唯一修复，按学习时刻回归，否则失效', '维护与改进');
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
  ['比较所用的数据', '学习时的 SQL', '修复后的 v3', '结果'],
  ['学习时刻 as-of', '1357.0 万', '1357.0 万', good('一致 → 发布 v3')],
  ['当前数据', '1489.1 万', '1342.4 万', bad('不一致 → 误拒')],
], { x: hx2, y: 1.45, w: hw2, colW: [1.6, 1.25, 1.25, hw2 - 4.1], size: 12 });
text(s, bulleted(null, C.blue, [
  '像换一种解法重做老师已经判过的那道题：答案必须相同。但必须用当初那份数据——今天的数据已经变了，学习时的 SQL 在上面同样过期（把旧行也算进去得 1489.1 万），比不出新解法对不对',
  '学习时的答案是唯一被确认过的答案，所以修复不需要参考答案。数据仓库用时间旅行查询（FOR SYSTEM_TIME AS OF）取学习时刻的数据，原型保留学习时的副本',
]), { x: hx2, y: 3.0, w: hw2, h: 2.2, fontSize: 12, valign: 'top', paraSpaceAfter: 4 });
band(s, [
  { text: '发布 v3 之后：', options: { bold: true, color: C.blue } },
  { text: 'v2 失效，声明旧修订的查询被拒绝；修复期间到达的请求等待结果；其他定义遇到相同的条件失败直接复用验证结果与修复；修不好的定义失效并通知使用方，等学到新证据再发布。' },
], { y: 5.3, h: 0.95, fill: C.paleBlue, size: 13 });
footnote(s, '上表为示意；回归测试数字来自 ' + SOURCE.slice(3, SOURCE.indexOf('。') + 1)
  + '“当前数据”一行来自对照实验 dsv41flash-r1-g3fix--exref（系统记录：“结果 13423672.28 与期望 14890636.48 不一致”）。');
s.addNotes('回到订单 002。MAVRA 发现订单号重复，一行是旧记录，一行是当前记录。它去找一个过滤谓词：只保留 ss_is_current = 1，过滤后订单不再重复，总额 650 元。'
  + '但不能看到一个像样的条件就用。候选必须满足两件事：过滤后每个键恰好一行；原来的键一个不丢——“只保留金额大于 200”也能去重，但 100 元的订单没了，这不叫修复。'
  + '还要唯一：如果 is_current 和 is_backup 两个过滤都通过，表结构说不出哪份是业务事实，MAVRA 不擅自选，定义失效，交给人确认。宁可说不知道怎么安全地修，也不猜。'
  + '修复通过结构检查之后还要考一次试：像换一种解法重做老师判过的那道题，答案必须一样。必须用当初那份数据，因为今天的数据已经变了，当初的 SQL 在上面同样过期，我们实际跑过：按当前数据比，正确的修复会被拒绝。'
  + '通过后发布 v3，v2 失效。');

// 10 Improvement: optimization revisions: equivalent, cheaper rewrites published and shared ----------------
s = content('改进：常见指标的写法可以更省——验证等价与代价后作为新修订共享', '维护与改进');
const ow = 6.2, ox2 = M + ow + 0.3, ow2 = W - M - ox2;
heading(s, '怎么做：候选 → 等价 → 更省 → 发布', M, 1.1, ow);
table(s, [
  ['环节', '内容'],
  ['候选', '规则改写：期间谓词改为日期键范围过滤（不连接日期维度）、去掉未使用的关联；模型提议；智能体成功轨迹中的不同写法'],
  ['等价', '结构合法、粒度成立；新前提成立（日期键按月连续）；学习时快照上与当前修订结果相同；当前快照上 14 个样本期间结果全部相同'],
  ['更省', '同一快照内对每个期间配对做 EXPLAIN ANALYZE，先后交替；执行时间配对差的 95% 区间整体低于 0，且平均节省 ≥ 10%'],
  ['发布', '作为同一定义的新修订；旧修订仍正确，宽限可用并通知使用方；新前提成为该修订的条件，随数据更新维护，不成立则失效'],
], { x: M, y: 1.45, w: ow, colW: [0.9, ow - 0.9], size: 12 });
heading(s, '真实记录：端到端实验的优化轮（store_sales 100 万行）', ox2, 1.1, ow2, C.amber);
table(s, [
  ['项目', '系统记录'],
  ['候选', '期间谓词改为日期键范围过滤，不连接 date_dim'],
  ['新写法', "ss_sold_date_sk between (select min(d_date_sk) from date_dim where …) and (select max(d_date_sk) …)"],
  ['等价', '9 条定义都通过：学习时快照一致；当前快照 14 个期间全部一致'],
  ['代价', lines('门店营业额 29.1 → 23.3 ms（−19.8%），95% 区间 [−9.1, −2.5]', '9 条定义省 15.6%–36.1%（退货率 173 → 111 ms）')],
  ['发布', lines(good('9 条定义全部 v1 → v2，474 秒'), '之后留出与 11 种更新 78/96 答对（未优化 77/96）')],
], { x: ox2, y: 1.45, w: ow2, colW: [0.9, ow2 - 0.9], size: 12 });
band(s, [
  { text: '更省的写法同样有前提：', options: { bold: true, color: C.blue } },
  { text: '日期键范围等价于维度连接，只在日期键按月连续时成立。这个前提被记为新修订的条件，与粒度、连接、日期条件一样维护；前提被破坏时该修订失效，回到维度连接的写法。', options: { breakLine: true } },
  { text: '效率不是靠猜：', options: { bold: true, color: C.blue } },
  { text: '等价与代价都在同一个快照上按期间配对验证，达不到证据门槛就不发布；发布后所有智能体共享新写法。' },
], { y: 5.25, h: 1.45, size: 12 });
footnote(s, '记录：noctis results/scen-20261008-opt/metric-1791439498065570（metric-global-opt，DeepSeek V4.1 Flash，第 1 次运行）；'
  + '对照为 dsv41flash-r1-g3fix--snap。留出题中 15 条用户智能体查询有 9 条采用了新写法。' + DATA);
s.addNotes('前面讲的都是“保持正确”。这页讲“变得更省”：常见指标的写法常常有更省的等价形式，比如按期间统计时不连接日期维度，直接按日期键范围过滤。'
  + 'MAVRA 的做法和修复一样严格：候选可以来自规则、模型提议或智能体的成功轨迹；先验证等价——结构合法、新前提成立、学习时快照和当前快照上 14 个样本期间结果全部相同；'
  + '再验证更省——同一快照内配对做 EXPLAIN ANALYZE，配对差的 95% 区间整体低于 0 且平均省 10% 以上；都通过才作为新修订发布，旧修订宽限可用并通知使用方。'
  + '右边是百万行端到端实验的真实记录：9 条定义都改为日期键范围过滤，14 个期间全部一致，执行时间省 15.6% 到 36.1%，全部发布为 v2；之后的留出题和 11 种数据变化答对 78/96，和未优化时相同。'
  + '关键是最后一句：更省的写法同样有前提，日期键按月连续；它被当作条件维护，前提被破坏时该修订失效。');

// 11 Lifecycle figure ------------------------------------------------------------------------------
s = content('一条定义的生命周期：学习、优化、维护、修复、失效', '维护与改进');
figure(s, 'lifecycle', 1.15, 4.5);
band(s, [
  { text: '修订规则：', options: { bold: true, color: C.blue } },
  { text: '同结构再次学到 → 为原定义记一次佐证；同名不同结构 → 并存，由智能体依据口径选择；'
    + '其他定义遇到相同的条件失败 → 复用验证结果与修复；失效后 → 重新学习，通过准入检查再作为新修订发布。' },
], { y: 5.75, h: 0.95, size: 13 });
s.addNotes('把前面几页串在一张图上。内置智能体求解“3 月门店营业额”，判定正确、准入检查通过，发布 v1。'
  + '第 3 步是优化：规则改写把期间谓词改为日期键范围，14 个样本期间结果一致、执行时间省 19.8%，发布 v2；新前提“日期键按月连续”成为 v2 的条件，v1 宽限可用。'
  + '之后一批销售被更正：旧行标记为非当前，插入当前行——“粒度键唯一”不成立，v2 失效，不处理会把新旧版本都算进去。'
  + '修复搜索在低基数列上枚举等值谓词，只有“ss_is_current = 1”可行；按学习时刻重算 3 月，结果一致，发布 v3。'
  + '红框是另一种结果：批次重复加载，没有谓词能恢复唯一性，定义失效并通知使用方，等待重新学习。');

// 12 The restatement as it really happened: B's calls and the queries MAVRA ran behind them --------
pres.addSection({ title: '真实记录' });
s = content('数据更正之后：B 的真实调用序列与 MAVRA 背后的查询', '真实记录');
table(s, [
  ['', '调用', 'MAVRA 做什么 → 返回', '耗时'],
  ['0', call("ETL：insert into store_sales (…, ss_is_current) select …, 0 …;  update store_sales set ss_net_paid = round(ss_net_paid * 0.9, 2) …"),
    '65,915 行被更正（旧行保留为非当前，当前行改九折）；语句级触发器把 store_sales 的表版本 +1', '—'],
  ['1', call('list_tables()  find_metric("门店营业额")'),
    lines('store_sales 版本已变 → 在这次调用里维护匹配到的 2 条定义：粒度查询 select count(*), count(distinct (粒度键)) … → 1,055,610 行 / 989,695 键，不成立 → v2 失效；',
      "修复搜索（pg_stats 低基数列，… group by ss_is_current）→ 唯一可行 ss_is_current = '1'；4 项检查含学习时快照上的回归 → 发布 v3（31.6 秒；#2 22.9 秒）",
      '→ 返回 2 条 v3 定义（示例 SQL 已带过滤）+ notices ×2'), '54.5 s'],
  ['2', call('describe_table("store_sales")  describe_table("date_dim")'), '版本已变 → 重新采样并更新表统计信息', '166 ms'],
  ['3', call('run_sql("select ss_is_current, count(*) … group by ss_is_current")  — 无过滤的探查 ×2'),
    bad("执行前审查拦下：“表 store_sales 现在每个键有多行（状态流水）；统计前需要加过滤 ss_is_current = '1'，否则会重复计算” → {rejected, required_filter}"), '5 ms'],
  ['4', call("run_sql(\"select count(*), count(distinct (…)) … where ss_is_current = '1'\")"), '通过 → 查询 #1：1,000,000 行 = 1,000,000 键', '9.5 s'],
  ['5', call("run_sql(\"select round(sum(ss_net_paid), 2) as value from store_sales where ss_is_current = '1' and ss_sold_date_sk between (select min(d_date_sk) …) and (select max(d_date_sk) …)\")"),
    '执行 → 查询 #2 = 12,932,888.04（这条没有声明 metrics：照常审查执行，不在条件保证范围内）', '26 ms'],
  ['6', call('final_answer(answer: "12932888.04", used: ["r2"], derivation: "r2")'), good('正确 ✓；同一阶段的 M1-T1 声明了 revision 2（v3），答 −9,803.47 ✓'), '—'],
], { x: M, y: 1.15, w: W - 2 * M, colW: [0.35, 4.3, 6.7, 0.783], size: 10 });
band(s, [
  { text: '三种更新的结果（百万行端到端）：', options: { bold: true, color: C.blue } },
  { text: '增量加载——条件仍成立，保持当前修订（6 条定义仅 2 次验证）；数据更正——失效 → 修复为新修订，1293.3 万 ✓；重复加载——无唯一修复，失效并通知，智能体自行去重，3 次运行中 2 次答对。' },
], { y: 6.1, h: 0.6, size: 10 });
footnote(s, TRACE_SOURCE + ' 维护耗时取自 maintenance 事件；三种更新的结果取自 results/scen-20261002。');
s.addNotes('这是数据更正之后用户智能体 B 真实的调用序列。第 1 轮它检索“门店营业额”，这一次 MAVRA 发现 store_sales 的版本变了，就在这次调用里完成了维护：'
  + '粒度查询发现 105 万行只有 99 万个键，v2 失效；修复搜索在低基数列上按值分组，只有 ss_is_current = 1 能恢复每键一行且不丢键；四项检查包括学习时快照上的回归，发布 v3；另一条同名定义复用结论。所以这次 find_metric 花了 54 秒，返回的是带过滤的新定义和两条通知。'
  + '第 3 轮 B 自己先探查了没加过滤的 SQL，被执行前审查拦下两次，原因写得很具体：这张表现在每个键多行，统计前要加过滤。第 4 轮加了过滤再查，通过；第 5 轮算出 9 月的值，正确。'
  + '诚实地说，这一条 run_sql 没有声明 metrics，所以它不在条件保证范围内——但审查仍然拦住了错误写法；同阶段的另一题声明了 revision 2，即 v3。');

// 13 Results: end to end ---------------------------------------------------------------------------
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
], { x: M, y: 1.15, w: W - 2 * M, colW: [2.9, 1.8, 1.9, 2.0, 1.6, 1.933], size: 12 });
band(s, bulleted(null, C.blue, [
  '共享本身：数据未变时 49% → 100%，每题 5.6 → 3.6 轮，输入 token −34%（任何共享方法均获得）；216 个固定库会话中每任务 37.7 s，无共享 64.5 s',
  '维护：更新后 75% → 81%，破坏性更新下 59% → 73%；MAVRA 与整定义重查答案相同，差异来自各次运行学到的定义不同',
  '代价与回本：建立记忆每轮 18.1 万 token、283 s（学习、抽取、准入）；之后每道留出题 1.09 万 token、8.5 s，独自探索 1.79 万 token、75.6 s'
    + '——按时间 5 道题后回本，按 token 26 道题后回本',
  '对照与负结果：单位变化不违反任何条件，所有方法同样过期；备份副本下修复有歧义，MAVRA 使定义失效，检索示例碰巧答对；'
    + '定义失效且修不好时，使用者每题 9.36 万 token，比独自探索（2.69 万）更费，正确率 42% 对 24%——下一步把使用者找到的修正经准入共享',
]), { y: 4.35, h: 2.4, size: 12 });
footnote(s, '5 种破坏性更新：退货状态行、保留旧行的销售更正、重复加载、商品维度 SCD Type 2、日期键格式变更。'
  + '来源：exp/2026-10-02-scenarios-ds、exp/2026-10-03-session-latency；代价与回本由 tools/sharing-stats.py 从同一批记录算出。与论文宏 \\Ds*、\\ScenHold*、\\Sl*、\\Am* 一致。');
s.addNotes('端到端实验：DeepSeek V4.1 Flash 智能体，每种方法独立运行 3 次，15 道留出题，再加 11 种数据更新。'
  + '共享本身的收益：数据未变时准确率从 49% 到 100%，轮数和 token 都下降——任何共享方法都有这个收益，不是 MAVRA 独有。'
  + '维护的收益：更新后从 75% 到 81%，5 种破坏性更新下从 59% 到 73%；检索历史示例即使提示它自行验证也只有 63%。MAVRA 与整定义重查答案相同，差异来自各次运行学到的定义不同。'
  + '代价：建立记忆每轮 18.1 万 token、283 秒；之后每道题使用者省 7 千 token、67 秒，按时间 5 道题、按 token 26 道题就回本，维护每次变化只做一次。'
  + '两个对照：单位变化不违反任何条件，所有方法同样过期，与命题的范围一致；备份副本下修复有歧义，MAVRA 按规则使定义失效，检索示例碰巧答对，这是如实保留的负结果。'
  + '还有一个负结果：定义失效又修不好时，工作退回给使用者，它们每题花 9.36 万 token，比独自探索还多，因为通知告诉了它们哪里坏了、它们会自己去修，正确率更高但更费。下一步是把使用者找到的修正经准入共享，只付一次。'
  + '这些数字来自我们设定的实验，不是说在所有数据库和模型上都能达到。');

// 14 Results: system level -------------------------------------------------------------------------
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
  + '维护成本：19 条定义时为整定义重查的 14%，因为很多定义依赖同一张表的同一个条件；但按表版本缓存验证查询也能得到同样的节省，所以效率不是本文的贡献，贡献在于什么可以发布、何时可以依赖、维护与改进由这一层替所有使用者承担。');

// 15 Guarantees, limits, and the three sentences ---------------------------------------------------
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
