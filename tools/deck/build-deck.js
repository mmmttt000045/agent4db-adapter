// Builds docs/mavra-system.pptx, a 10-slide Chinese deck that tells MAVRA as one story: title; how it differs from
// Text-to-SQL; a shared rule breaks when the data changes (toy ledger, then the real record); MAVRA between agents and
// the database with its three responsibilities (publish, rely, maintain and improve); the running example, 门店营业额
// v1 (learned) → v2 (optimized) → v3 (repaired), as one table; publish (admission, the four conditions); rely (one
// recorded use, steps 1-8: declared revision, table versions, the same snapshot); maintain and improve (v1 → v2, then
// three writes and their three outcomes); results; guarantees, limits and three sentences. The user asked for 10
// slides: don't add slides. The three figures carry slides 4, 7 and 8; they come from tools/deck/figures/ (drawn by
// `python3 tools/figures/build.py --deck`, rendered to PNG). Toy tables are marked 示意; every other number comes from
// the archived run records or the paper's generated macros (overleaf/gen/*.tex); the slide footers only say which
// numbers are 示意 and which are recorded, and the record paths go at the end of each slide's speaker notes. Wording
// uses standard database terms, with a one-line plain reading beside each.
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
const RECORDED = '实验记录（来源见备注）。' + DATA;
const TRACE_SOURCE = 'noctis results/scen-20261008-trace（metric-global-opt，--trace 逐次记录工具调用；DeepSeek V4.1 Flash）';

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
  return { y: top + (maxH - h) / 2, h };
}

// A responsibility tag as in the figures: white bold text on a navy pill.
function tag(slide, value, x, y, w) {
  slide.addShape('roundRect', { x, y, w, h: 0.32, fill: { color: C.navy }, line: { color: C.navy }, rectRadius: 0.06 });
  text(slide, value, { x, y, w, h: 0.32, fontSize: 12, bold: true, color: C.white, align: 'center', valign: 'middle' });
}

function text(slide, value, opts) {
  slide.addText(value, { fontFace: FONT, color: C.ink, margin: 0, isTextBox: true, ...opts });
}

function footnote(slide, value) {
  text(slide, value, { x: M, y: 6.85, w: W - 2 * M - 0.8, h: 0.4, fontSize: 11, color: C.muted,
    valign: 'bottom' });
}

// Speaker notes, with the record paths behind the slide's numbers at the end.
function notes(slide, body, source) {
  slide.addNotes(source ? `${body}\n\n来源：${source}` : body);
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
pres.title = 'MAVRA：数据 agent 与数据库之间的共享记忆层';
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
s.addText('MAVRA：数据 agent 与数据库之间的\n共享记忆层', { placeholder: 'title' });
s.addText('保存 agent 学到的定义，让其他 agent 在数据变化后仍能放心复用', { placeholder: 'body' });
text(s, [
  { text: 'MAVRA = Metric-Aware Validation and Reuse for Agents', options: { breakLine: true } },
  { text: '组会汇报 · 2026 年 10 月' },
], { x: M, y: 5.4, w: W - 2 * M, h: 0.8, fontSize: 16, color: C.ice, valign: 'top', paraSpaceAfter: 6 });
s.addNotes('很多数据 agent 在同一个数据库上工作。一个 agent 学会了怎么算“营业额”，别的 agent 也想用；'
  + '但数据库每天都在更新，学到的定义可能在不知不觉中不再适用，而 SQL 照样能执行。'
  + 'MAVRA 是放在 agent 与数据库之间的中间件：保存 agent 学到的定义，记住定义成立的条件，在定义被使用时保证条件在实际执行的数据上仍然成立，条件被破坏时修复或失效。'
  + '名字是 Metric-Aware Validation and Reuse for Agents 的缩写：面向指标定义的验证与复用。'
  + '顺序：问题 → MAVRA 与三项职责 → 贯穿全场的例子（门店营业额 v1 → v2 → v3）→ 发布 → 依赖 → 维护与改进 → 实验 → 边界与总结，共 10 页。');

// 2 Background: what a data agent does, and how this differs from Text-to-SQL ------------------
pres.addSection({ title: '问题' });
s = content('背景：agent 要自己弄清“口径”，这和 Text-to-SQL 不是一回事', '问题');
text(s, [
  { text: '数据 agent：', options: { bold: true, color: C.blue } },
  { text: '接到“9 月门店营业额是多少”这样的业务问题，自己查看表、写 SQL、给出答案的大模型程序。'
    + '难点在口径——这个指标具体怎么算（用哪一列、含不含税、按哪个日期归月），它不写在表结构里。' },
], { x: M, y: 1.05, w: W - 2 * M, h: 0.6, fontSize: 13, valign: 'middle' });
const half = (W - 2 * M - 0.4) / 2;
[
  { x: M, head: 'Text-to-SQL：把自然语言问题翻译成 SQL', color: C.muted, pale: C.grey, rows: [
    ['输入', '自然语言问题 + 表结构（可附示例查询）'],
    ['输出', '一条 SQL 查询'],
    ['状态', '无状态：每个问题独立处理，不保留结果'],
    ['关注', '单条查询写得对不对'],
  ] },
  { x: M + half + 0.4, head: 'MAVRA：agent 与数据库之间的共享记忆层', color: C.blue, pale: C.paleBlue, rows: [
    ['位置', 'agent 对数据库的访问都经由它'],
    ['保存', 'agent 学到的定义（见下方），以及它成立的条件'],
    ['共享', '跨 agent、跨会话共享'],
    ['关注', '已有的定义在当前数据上还对不对'],
  ] },
].forEach(({ x, head, color, pale, rows }) => {
  s.addShape('roundRect', { x, y: 1.75, w: half, h: 2.0, fill: { color: pale }, line: { color: pale },
    rectRadius: 0.12, objectName: `card ${head}` });
  text(s, head, { x: x + 0.35, y: 1.85, w: half - 0.7, h: 0.42, fontSize: 17, bold: true, color });
  rows.forEach(([k, v], i) => {
    const y = 2.35 + i * 0.34;
    text(s, k, { x: x + 0.35, y, w: 0.75, h: 0.32, fontSize: 13, bold: true, color, valign: 'middle' });
    text(s, v, { x: x + 1.1, y, w: half - 1.45, h: 0.32, fontSize: 13, valign: 'middle' });
  });
});
heading(s, '实验记录：同一问题“9 月的门店营业额是多少？”（只给名称、不给口径）三次独立求解', M, 3.85, W - 2 * M);
table(s, [
  ['', '选的金额列', '答案', '交互轮数'],
  ['没有共享定义 · 第 1、2 次', 'ss_ext_sales_price（折扣前的销售额）', bad('1413.8 万 ✗'), '5'],
  ['没有共享定义 · 第 3 次', 'ss_net_paid（净支付额）', good('1307.0 万 ✓'), '5'],
  [strong('有 MAVRA · 3 次结果一致', C.blue), 'ss_net_paid（取到共享的定义）', good('1307.0 万 ✓'), '3'],
], { x: M, y: 4.2, w: W - 2 * M, colW: [3.0, 6.0, 2.0, 1.133], size: 12 });
band(s, [
  { text: '定义：', options: { bold: true, color: C.blue } },
  { text: 'agent 学到的一条计算规则，例如“门店营业额 = 门店销售的净支付额之和，按销售日期归月”。下文统一叫“定义”。', options: { breakLine: true } },
  { text: '两者处于不同层次：', options: { bold: true, color: C.blue } },
  { text: '任何 Text-to-SQL 模型或数据 agent 都可以接在 MAVRA 上；MAVRA 不生成 SQL，它保存、检查和维护 agent 学到的定义。', options: { breakLine: true } },
  { text: '也不同于：', options: { bold: true, color: C.blue } },
  { text: '指标层由人声明定义，声明的前提（如连接属性）运行时不验证；数据质量测试按表检查人写的约束，不知道哪条定义依赖它。' },
], { y: 5.72, h: 1.08, fill: C.paleAmber, size: 12 });
footnote(s, RECORDED);
notes(s, '先交代场景。数据 agent 是接到业务问题、自己查表写 SQL 给出答案的大模型程序。它最难的不是写 SQL，而是弄清口径：营业额用哪一列、含不含税、按哪个日期归月——这些不在表结构里。'
  + '下面是实验记录：只给“门店营业额”这个名称，没有共享定义的 agent 三次独立求解，两次选了折扣前的销售额，错；一次选了净支付额，对。每次重新猜，答案就不稳定。接入 MAVRA 取到共享的定义后，三次都对，只用 3 轮。'
  + '这也是它和 Text-to-SQL 的区别：Text-to-SQL 研究把一个问题翻译成一条 SQL，没有状态；MAVRA 不生成 SQL，它保存 agent 学到的定义，并负责这些定义在数据变化后还对不对。任何 Text-to-SQL 模型都可以接在 MAVRA 上面。'
  + '这里的“定义”就是一条学到的计算规则，后面一直用这个词。'
  + '它也和做数据库的同学熟悉的两类工具不同：指标层（如 Databricks metric views）由人声明定义，但声明的连接属性运行时不验证；数据质量测试（如 dbt tests、Deequ）按表检查人写的约束，却不知道哪条定义依赖它。MAVRA 的条件是从定义推出来的，所以知道哪条定义依赖哪个条件。'
  + '表里的“轮”是 agent 调用工具的回合。',
  'noctis results/scen-20261002，没见过的题 M1-P1（9 月门店营业额）；没有共享定义：dsv41flash-r1-a、r2-b、r3-a；MAVRA：dsv41flash-r1–r3-g3fix--snap。');

// 3 The problem, on a toy ledger and then the real record ------------------------------------
s = content('问题：共享的定义会因数据变化而失效，而 SQL 不报错', '问题');
const colL = 5.9, colR = W - 2 * M - colL - 0.35, xR = M + colL + 0.35;
heading(s, '第一天（示意）：定义“营业额 = 每笔销售金额之和”成立', M, 1.1, colL);
table(s, [
  ['订单号', '金额', '状态'],
  ['001', '100 元', '当前'],
  ['002', '200 元', '当前'],
  ['003', '300 元', '当前'],
], { x: M, y: 1.45, w: colL, colW: [1.5, 1.6, 2.8], size: 12 });
text(s, [{ text: '按定义计算：600 元 ✓', options: { bold: true, color: C.green } }],
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
  { text: '沿用定义：850 元 ✗（旧行也被计入）　正确答案：650 元', options: { bold: true, color: C.red, breakLine: true } },
  { text: '定义本身没有错，错的是它的前提“每个订单号只有一行”不再成立。' },
], { x: xR, y: 3.3, w: colR, h: 0.55, fontSize: 12, valign: 'top' });
heading(s, '实验中的真实记录：问 9 月门店营业额，每种更新都从原始数据开始，一直沿用最初学到的定义', M, 3.95, W - 2 * M);
table(s, [
  ['更新', '数据库中的变化', '参考答案', '沿用最初的定义'],
  ['增量加载', '追加一批 9 月的新销售（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '旧行保留并标记为非当前，插入九折后的当前行，65,915 行', '1293.3 万',
    bad('1430.1 万 ✗  新旧版本重复计入')],
  ['重复加载', '4 个月的销售批次被再次加载，+110,165 行', '1307.0 万', bad('2613.9 万 ✗  9 月重复计入')],
], { x: M, y: 4.3, w: W - 2 * M, colW: [1.3, 6.1, 1.5, 3.233], size: 12 });
band(s, [
  { text: '三种更新都是日常的数据写入，表结构没变、查询照常执行；定义是共享的，所有使用它的 agent 同时出错。', options: { breakLine: true } },
  { text: '同样翻倍，一对一错：', options: { bold: true, color: C.blue } },
  { text: '增量加载是新小票号，确实多卖了；重复加载是同一批小票号又出现一次——差别只在键有没有重复。', options: { breakLine: true } },
  { text: '所以：', options: { bold: true, color: C.blue } },
  { text: '只存定义不够，还要记下它成立的前提（下文叫“条件”），用之前先检查。数据更正一行就是第 5 页的 v2 → v3；账本的“状态”列在真实数据里叫 ss_is_current。' },
], { y: 5.8, h: 1.12, fill: C.paleAmber, size: 12 });
footnote(s, '上半为示意例子，下半为实验记录（来源见备注）。' + DATA);
notes(s, '先用一个示意的小账本。第一天三笔订单，定义“把每笔销售金额加起来”算出 600 元，正确。'
  + '第二天订单 002 被更正为 250 元，数据仓库常见的做法是旧行不删、标记为非当前，再插入一行新的。沿用定义会把 200 和 250 都加进去，得到 850 元，正确答案是 650 元。'
  + '注意：定义没有算错，是它的前提“每个订单号只有一行”不再成立了。'
  + '下半是实验里的真实记录，问的都是 9 月门店营业额，每种更新都从原始数据单独开始。增量加载追加了一批 9 月的新销售，换了新小票号，9 月确实翻倍，沿用定义算对；数据更正后沿用定义多算 137 万；重复加载把同样的行再装一次，9 月也翻倍，但这次是错的。'
  + '同一个 2613.9 万，一对一错，区别只在键有没有重复——这正是后面要检查的“粒度键唯一”。'
  + '三种更新都是日常的数据写入，表结构没变，查询不报错，agent 会非常自信地给出错误答案；而定义是共享的，一处失效所有 agent 一起错。'
  + '结论落在最后一行：只存定义不够，还要把它成立的前提记下来，用之前检查——这就是 MAVRA 的出发点。数据更正这一行，后面会作为 v2 到 v3 的例子再出现。',
  'noctis results/scen-20261002，dsv41flash-r1–r3-g3fix--schema（仅在模式变更时使定义失效，3 次运行答案相同）；增量加载 = 复制 9 月门店销售行并换新小票号（src/scenario.rs Change::Append）。');

// 4 MAVRA: where it sits and the three responsibilities ------------------------------------------
pres.addSection({ title: 'MAVRA' });
s = content('MAVRA：agent 与数据库之间的共享记忆层，承担三项职责', 'MAVRA');
{
  const { y, h } = figure(s, 'overview', 1.05, 5.02);
  // One line per responsibility under the figure, with the same navy tags the figure carries.
  const sy = y + h + 0.1, gap = 0.12;
  const widths = [3.72, 3.72, W - 2 * M - 2 * 3.72 - 2 * gap];
  let x = M;
  [
    { head: '发布', w: 0.62, body: '答案经确认正确、通过准入检查的定义，连同它成立的条件一起保存' },
    { head: '依赖', w: 0.62, body: '查询声明依据哪个定义的哪一版；条件在这条查询的快照上成立才执行' },
    { head: '维护与改进', w: 1.18, body: '数据变了替所有使用者重新验证：能修就发新修订，修不好就失效；也发布更快的等价写法' },
  ].forEach((c, k) => {
    s.addShape('roundRect', { x, y: sy, w: widths[k], h: 0.62, fill: { color: C.grey }, line: { color: C.grey },
      rectRadius: 0.06, objectName: `duty ${c.head}` });
    tag(s, c.head, x + 0.12, sy + 0.15, c.w);
    text(s, c.body, { x: x + c.w + 0.24, y: sy + 0.04, w: widths[k] - c.w - 0.34, h: 0.54, fontSize: 11, valign: 'middle' });
    x += widths[k] + gap;
  });
}
s.addNotes('接着上一页的结论：既然问题出在前提，MAVRA 就把定义和它的前提（条件）一起存，用之前检查。原来 agent 直接访问数据库，现在 MAVRA 放在中间，不替代 agent，也不替代数据库。'
  + '图上三个深色标签就是三项职责，也是论文的三个问题：什么可以发布，何时可以依赖，由谁维护与改进。后面三页各讲一项，第 7、8 页各用一张图展开。'
  + '两种 agent：内置 agent（右上）负责学习，学到的定义经准入检查后发布（紫色）；用户 agent（左边，可以有很多个）通过工具取用：find_metric(名称) 取定义，run_sql(sql, metrics=[{key, revision}]) 执行——metrics 参数就是“声明”这条 SQL 依据哪条定义的哪一版，MAVRA 的保证挂在这个声明上。人只确认一次学习答案是否正确，修复有歧义时才介入。'
  + '一次使用分 8 步：蓝色 1–5 是查找定义，橙色 6–8 是执行 SQL，第 7 页把这 8 步按真实记录逐步展开。黑色粗箭头是维护写回指标定义：修复或优化后发布新修订，修不好就标为失效。'
  + '图里的时刻：ETL 刚做了一次增量加载，store_sales 从 v14 变成 v15。读它的门店营业额和电子品类门店营业额变成待验证，不读它的退货金额仍有效；date_dim 没变，日期键唯一和按月连续两个结论直接复用（同一张卡片）；缺的两个结果由这次检索交给维护补上，写进缓存后两条定义共用。待验证不是存下来的状态，是使用时比较表版本得出的。'
  + '内置 agent 还能为已发布的定义提出更省的写法：维护先试规则改写，没有规则候选时才请它提议，候选都要通过等价和更省的验证才发布新修订（第 8 页）。准入检查和这些验证都是 MAVRA 在数据库上执行的查询，不由大模型判断。');

// 5 The running example: three revisions of one definition ---------------------------------------
s = content('一个例子贯穿全场：门店营业额的三个修订', 'MAVRA');
text(s, [
  { text: '口径从来没变：', options: { bold: true, color: C.blue } },
  { text: '门店营业额 = 门店销售的净支付额之和，按销售日期归到各月。变的只是 SQL 怎么写——修订（v）就是同一条定义的第几版写法。' },
], { x: M, y: 1.1, w: W - 2 * M, h: 0.45, fontSize: 15, valign: 'middle' });
table(s, [
  ['版本', '为什么会有它', 'SQL 写法', '依赖的条件', '9 月的结果'],
  [strong('v1', C.blue), 'agent 学到', 'SUM(ss_net_paid)，连接日期表按年月筛选', '粒度键唯一、日期键唯一、日期键完整性', good('1307.0 万 ✓')],
  [strong('v2', C.blue), '找到更省的写法', '同一个求和，不连接日期表，改成按日期键范围筛选', 'v1 的条件，再加“日期键按月连续”', lines(good('1307.0 万 ✓'), muted('同 v1，快约 20%'))],
  [strong('v3', C.blue), '数据更正后 v2 算错了', "v2 再加一个过滤 ss_is_current = '1'", '同上，在这个过滤之下成立', good('1293.3 万 ✓')],
], { x: M, y: 1.65, w: W - 2 * M, colW: [0.8, 2.3, 4.0, 3.0, 2.033], size: 14 });
text(s, [
  { text: '条件的白话：', options: { bold: true, color: C.blue } },
  { text: '粒度键唯一 = 一笔销售只登记一次；日期键唯一 = 一个日期编号只对应一天；日期键完整性 = 不会突然有大量记录找不到日期；日期键按月连续 = 每个月的日期编号首尾相接（条件从哪来见第 6 页）' },
], { x: M, y: 3.95, w: W - 2 * M, h: 0.55, fontSize: 12, valign: 'top' });
text(s, bulleted(null, C.blue, [
  'v1 → v2 是换个更快的写法：两版结果完全一样，v1 也没坏，仍被接受（附提醒）',
  'v2 → v3 是数据变了（就是第 3 页那次“数据更正”）：旧行保留并标为非当前，v2 会把新旧两行都算进去（1430.1 万 ✗）；修复出 v3 后 v2 和 v1 都不能再用',
  'v3 也不是终点：数据再变可能有 v4；找不到可靠的修法就不出新修订，定义失效并通知。口径变了（比如改成含税）是另一条定义，不是新修订',
]), { x: M, y: 4.58, w: W - 2 * M, h: 1.05, fontSize: 13, valign: 'top', paraSpaceAfter: 3 });
band(s, [
  { text: '为什么要编号：', options: { bold: true, color: C.blue } },
  { text: 'agent 执行 SQL 时声明“依据门店营业额 v2”；MAVRA 据此拒绝已停用的版本，只在该版本的条件成立时执行，并记下每个答案来自哪一版。'
    + '系统调用原文里的 revision: N 即 v(N+1)。' },
], { y: 5.75, h: 0.95, fill: C.paleBlue, size: 13 });
footnote(s, '实验记录（来源见备注）；“快约 20%”为配对测量 29.1 → 23.3 ms。' + DATA);
notes(s, '后面所有页面都用这一个例子。先说清楚 v 是什么：它是版本号，同一条定义的第几版写法，按时间往下记，不是一级比一级高的等级。'
  + '三个版本里口径从来没变，都是门店销售净支付额之和、按销售日期归月；变的只是 SQL 怎么写。'
  + 'v1 是 agent 学到的：连接日期表按年月筛选。v2 是 MAVRA 找到的更省写法：不连接日期表，直接按日期键范围筛选，结果和 v1 完全一样，快约 20%，但多了一个前提——日期键按月连续，这个前提也成为 v2 的条件。'
  + 'v3 是数据更正之后：旧行保留并标为非当前，v2 会把新旧两行都算进去，得到 1430.1 万；MAVRA 找到唯一可行的过滤 ss_is_current = 1，修复出 v3，答案 1293.3 万。'
  + '编号的用处在于声明：agent 说“我用 v2”，MAVRA 就能判断 v2 现在还能不能用。',
  '9 月结果：v1 取自 noctis results/scen-20261002（未做优化的 MAVRA 运行），v2、v3 取自 ' + TRACE_SOURCE + '；“快约 20%”为优化轮 results/scen-20261008-opt 的配对测量。');

// 6 Publish: how v1 got in --------------------------------------------------------------------------
pres.addSection({ title: '发布' });
s = content('发布：v1 是怎么进入共享记忆的', '发布');
const lw = 6.3, rx = M + lw + 0.3, rw = W - M - rx;
heading(s, '学习任务（给定口径）：“3 月的门店营业额是多少？”', M, 1.1, lw, C.violet);
table(s, [
  ['步骤', '发生了什么'],
  ['求解', '内置 agent 5 轮 7 次工具调用写出 SQL（第一次 find_metric 为空：还没人学过），答案 13,570,368.70 与参考答案一致'],
  ['抽取', '大模型把题面、SQL、算式、表元数据整理成一张知识卡（定义存进共享记忆的样子），剥离题目参数（月份）'],
  ['准入', '7 项检查：① 有业务依据 ② 答案判定正确 ③ 引用的表和列都存在、没写死月份 ④ 当前数据上一笔只一行 ⑤ SQL 符合粒度和连接要求 ⑥ 重跑原 SQL 结果不变 ⑦ 只凭知识卡生成的 SQL（规范 SQL）也算出同样答案'],
  ['发布', 'metric:门店营业额 v1，连同条件、学习证据与表版本'],
  ['知识卡', lines('给 agent 看的：度量 SUM(ss_net_paid)；粒度 销售日 × 小票号 × 商品；按销售日关联 date_dim；不含税',
    'MAVRA 保管的：条件、学习证据（SQL、答案、表版本）、状态、修订号、使用者')],
], { x: M, y: 1.45, w: lw, colW: [0.8, lw - 0.8], size: 11 });
heading(s, '发布时一并记下：从定义推出的四类条件', rx, 1.1, rw, C.blue);
table(s, [
  ['条件', '通俗地说', '检查方式'],
  ['粒度键唯一', '一件事不登记两次', '行数 = 不同键数（在定义的过滤之下）'],
  ['连接基数 N:1', '连接不能把一行变两行', '被连接表的键唯一'],
  ['日期角色', '按指定的日期归期间，一个键只连出一个日期', '日期键唯一'],
  ['日期键完整性', '不能突然有大量记录找不到日期', '未匹配率 ≤ 学习时 + 0.1 个百分点'],
], { x: rx, y: 1.45, w: rw, colW: [1.35, 2.15, rw - 3.5], size: 11 });
text(s, [
  { text: '本例：', options: { bold: true, color: C.blue } },
  { text: '只连接日期表，前两类都落到“日期键唯一”，所以 v1 有 3 个条件；v2 再加“日期键按月连续”（每月日期编号首尾相接），共 4 个。', options: { breakLine: true } },
  { text: '命题 1：', options: { bold: true, color: C.blue } },
  { text: '业务前提成立且四类条件都成立时，规范 SQL 把每笔业务事件在其期间内恰好计一次。', options: { breakLine: true } },
  { text: '不保证一切：', options: { bold: true, color: C.red } },
  { text: '数值的含义变了它发现不了。例如上游改成按“分”记金额，数值整体 ×100，行数和键都没变（实验里的“单位变化”对照）。' },
], { x: rx, y: 4.02, w: rw, h: 1.55, fontSize: 12, valign: 'top', paraSpaceAfter: 3 });
band(s, [
  { text: '第 ⑦ 项最重要：', options: { bold: true, color: C.violet } },
  { text: '别的 agent 只能读到这张知识卡，拿到的是规范 SQL。实验中被拦下的一例：提取时丢了“电子”类别过滤，agent 答的是 274.1 万，知识卡编译出的 SQL 会返回 1352.1 万。', options: { breakLine: true } },
  { text: '判定正确：', options: { bold: true, color: C.violet } },
  { text: '实验用参考答案；部署中由指标负责人确认一次。此后维护与修复不再需要参考答案。' },
], { y: 5.65, h: 1.05, fill: C.paleViolet, size: 12 });
footnote(s, RECORDED);
notes(s, '第一项职责：发布。一条定义不是学到就直接相信。内置 agent 拿到一道给定业务口径的学习任务，用 7 次工具调用写出 SQL，答案正确——实验里用参考答案判定，部署中由负责这个指标的人确认一次。'
  + '然后大模型把零散的学习过程整理成知识卡：给 agent 看的“怎么算”，和 MAVRA 保管的“什么时候这样算是安全的”。题目里的月份这类参数要剥掉，否则别人拿到的是写死 3 月的 SQL。'
  + '再过 7 项检查，第 7 项最重要：只凭知识卡编译出的 SQL 必须得到同样答案。实验里真拦下过一例：提取时丢了“电子”这个类别过滤，原来的 agent 答 274.1 万是对的，但别人拿到的 SQL 会返回 1352.1 万。'
  + '发布时同时记下四类条件，这就是 v1 成立的前提。门店营业额只连接日期表，连接基数和日期角色检查的都是日期表的键唯一，所以落到一个“日期键唯一”上：v1 有 3 个条件，v2 换成日期键范围写法后多一个“按月连续”，共 4 个，第 7 页说的四个条件就是这些。'
  + '命题 1 说它们够用：都成立时每笔业务恰好计一次。'
  + '但数值层面的变化发现不了：实验里的“单位变化”是从某月起，上游改成按“分”记金额，所有金额乘以 100，行数、键、连接都没变，四类条件全部照样成立，agent 拿到的 9 月营业额是 13.07 亿，正确是 1307.0 万。'
  + '这在现实里会发生：微信支付的接口按“分”记金额，支付宝按“元”记，两路数据合进同一张表时漏了换算，就是这种错误；上游系统升级改了单位而 ETL 没跟着改，也是一样。'
  + '为什么不加一条“数值不能突变”的条件？因为只看数据分不清真增长和单位变化：第 3 页的增量加载也让 9 月翻了一倍，那是真的多卖了。这类问题要靠懂业务的人或数据质量监控（看分布、设阈值、人工确认）来发现，MAVRA 把它列为边界。',
  TRACE_SOURCE + '；拦下的一例：results/scen-20260930/glm53-r3（M5-L2，论文宏 \\PubEx*）。');

// 7 Rely: one use, steps 1-8 of the overview, from the record --------------------------------------
pres.addSection({ title: '依赖' });
s = content('依赖：使用 v2 时先声明，在同一快照上验证后执行', '依赖');
{
  const { y, h } = figure(s, 'lookup', 1.05, 5.2);
  band(s, [
    { text: '实验：', options: { bold: true, color: C.blue } },
    { text: '并发写入下 11,297 次使用，0 次在违反条件的数据上作答（检查与执行不在同一快照时为 3.8–4.6%）；读延迟不变。' },
  ], { y: y + h + 0.08, h: 0.46, fill: C.paleBlue, size: 12 });
}
footnote(s, '图中的调用、耗时与数值为实验记录，表版本号为示意（来源见备注）。' + DATA);
notes(s, '第二项职责：依赖。这张图把第 4 页的第 1–8 步按一次真实使用展开，编号和第 4 页一致。场景是第 3 页的增量加载：store_sales 刚追加了一批 9 月的新销售，表版本从 v14 变成 v15（版本号是示意）。用户 agent B 问 9 月的门店营业额。'
  + '第 1 步，B 调用 find_metric("门店营业额")。第 2 步，名称匹配到两条定义：门店营业额和电子品类门店营业额，都已经是优化后的 v2；它们记下的 store_sales 版本是 v14，现在是 v15，所以要验证。'
  + '第 3 步交给维护：两条定义都读 store_sales，粒度键唯一和日期键完整性这两项条件完全相同，只执行一次——粒度检查 5.3 秒、完整性 0.15 秒，是在维护电子品类时执行的；轮到门店营业额时两项都直接复用，0 条查询、0.3 毫秒。date_dim 没变，它上面的两项条件根本不用看。'
  + '第 4 步把结果写进验证结果缓存，键是（条件，表版本）：同一条件在同一表版本上只验证一次，所有定义、所有 agent 共享；v14 上的旧结果不再命中。第 5 步返回门店营业额 v2，附口径和示例 SQL。'
  + '第 6 步，B 照示例写出按日期键范围求和的 SQL，调用 run_sql，在 metrics 里声明 revision: 1，也就是 v2（系统内部从 0 编号）。第 7 步是执行前验证：先核对声明——v2 是当前修订，通过；如果声明的是已经失效的修订（比如数据更正后修复出了 v3，再声明 v2），直接拒绝并要求重新 find_metric；如果声明的是被优化替代的 v1，它自己的条件成立就接受并提醒改用新修订；没有声明的 SQL 照常执行和审查，但不在条件保证范围内。'
  + '然后在这条查询的快照上验证 v2 的 4 个条件：快照里正是 store_sales v15、date_dim v7，4 个结果缓存里都有，全部复用，没有执行任何验证查询。'
  + '为什么要在同一快照？如果 10:00:00 检查通过、10:00:01 别人插入一条重复记录并提交、10:00:02 再执行，答案就错了。MAVRA 把检查和执行放进同一个可重复读的只读事务：快照是查询开始那一刻数据的样子，执行期间别人提交的写入这条查询看不到；如果快照里已经是更新的表版本，就在这个快照上当场验证，不成立就拒绝执行。版本号在写入事务里由触发器更新，所以快照读到的版本恰好对应它看到的数据，论文的引理 1 证明了版本相同时复用验证结果是安全的。'
  + '第 8 步在同一快照上执行，29 毫秒，结果 26,139,303.60，与参考答案一致；final_answer 里 used: ["r1"] 的 r1 是本次会话的第 1 次查询，不是修订号，所以答案能追溯到查询 #1，再追溯到门店营业额 v2。B 这道题共 4 轮、6 次工具调用。'
  + '下面一行是并发实验：一万多次使用，没有一次在被破坏的数据上作答；对照是先检查、再另开事务执行，3.8–4.6% 的使用答在了被破坏的数据上。',
  'noctis results/scen-20261008-opt/metric-1791439498065570（metric-global-opt，增量加载阶段 M1-P1：记录的 declared、answer、db 计量；events.append 中电子品类门店营业额与门店营业额的 maintenance 事件）；并发数字来自快照压力测试（论文宏 \\Sn*）。');

// 8 Maintain and improve: v1 -> v2, then three writes and their three outcomes -----------------------
pres.addSection({ title: '维护与改进' });
s = content('维护与改进：换更快的写法；数据变了就验证、修复或失效', '维护与改进');
{
  const { y, h } = figure(s, 'lifecycle', 1.05, 5.2);
  band(s, [
    { text: '同一个发布通道：', options: { bold: true, color: C.blue } },
    { text: '改进和修复出的修订都要通过检查，新前提成为条件；实验中 9 条定义都得到更快的修订，执行时间省 15.6%–36.1%。' },
  ], { y: y + h + 0.08, h: 0.46, size: 12 });
}
footnote(s, '实验记录，表版本号为示意（来源见备注）。' + DATA);
notes(s, '第三项职责：维护与改进。这张图是门店营业额这一条定义的一生，上面一行回顾它怎么来的，下面三行是数据变化后的三种结局，正好对应第 3 页的三种日常写入。'
  + '第 1、2 步是发布（第 6 页讲过）：内置 agent 用 5 轮、7 次工具调用答对 3 月门店营业额，通过 7 项准入检查，发布 v1，带 3 个条件。'
  + '第 3 步是改进：规则改写把按年月连接日期表改成按日期键范围过滤。先验证等价——学习时的数据上和当前数据的 14 个期间结果全部相同；再验证更省——同一快照里配对测执行时间，29.1 到 23.3 毫秒，快 19.8%，置信区间整体小于 0。新写法多了一个前提：日期键按月连续，它成为 v2 的第 4 个条件，以后数据变了也要检查。实验里 9 条定义都得到了更快的修订，后来 15 条查询有 9 条照着新写法写。'
  + '下面三行都从同一个状态开始：store_sales 有一次写入，下次使用 v2 之前先验证它的条件。'
  + '增量加载：多出 27,095 行，都是新小票号，4 个条件都成立，v2 继续有效——这就是第 7 页那次使用，9 月 2613.9 万，答对。'
  + '数据更正：旧行保留并标为非当前，多出 65,915 行。粒度检查发现 1,065,915 行只有 1,000,000 个键，v2 失效。第 4 步修复搜索：在取值很少的列上找“列 = 值”的过滤，必须一笔一行且不丢键，只有 ss_is_current = 1 可行；如果有两种过滤都可行（比如一份当前数据、一份备份），MAVRA 不擅自选，失效并交给人。'
  + '第 5 步回归测试：用学习时那份数据重算 3 月，学习时的 SQL 和 v3 都是 1357.0 万，一致才接受。必须用学习时的数据比：在今天的数据上，学习时的 SQL 本身也算错了（1489.1 万对 v3 的 1342.4 万），会误拒正确的修复。'
  + '第 6 步发布 v3，9 月 1293.3 万，答对；不维护、沿用 v2 会得 1430.1 万。发现、搜索、回归都在一次 find_metric 里完成，trace 运行中门店营业额的两条同名定义共用了 54.5 秒，之后的请求直接拿到 v3。'
  + '重复加载：4 个月的销售批次被再装一次，多出 110,165 行，粒度键唯一同样不成立，但在取值很少的列上找不到能恢复唯一性的过滤，定义失效并通知使用方；声明 v2 的查询被拒绝，agent 只能自己从头探索，等重新学到再发布。'
  + '还有一种情况图里没画：数据只破坏了 v2 新增的前提（比如日期维度重新装载、某个月换了新键，日期键不再按月连续），而 v1 的条件都成立。这时只撤下 v2、恢复 v1，不去搜索修复；实验里 4 条定义都这样回退，之后 20 个答案全对。',
  'noctis results/scen-20261008-opt/metric-1791439498065570（metric-global-opt：优化轮计时；增量加载、数据更正、重复加载三个阶段门店营业额的 maintenance、revoked、repair_* 事件与 M1-P1 答案）；学习与 54.5 秒：' + TRACE_SOURCE + '；不维护时的 1430.1 万：results/scen-20261002 dsv41flash-r1-g3fix--schema；回归在今天数据上的对比来自对照实验 dsv41flash-r1-g3fix--exref；v1 回退：论文 §7.8（gen/premise.tex）。');

// 9 Results ----------------------------------------------------------------------------------------
pres.addSection({ title: '实验结果' });
s = content('实验结果：共享提高准确率，检查与修复让数据变化后答对最多', '实验结果');
heading(s, '端到端：DeepSeek V4.1 Flash agent，每种方法独立运行 3 次', M, 1.1, W - 2 * M, C.blue);
table(s, [
  ['方法', '做法', '数据未变', '11 种更新后', '5 种破坏性更新', '单位变化（对照）'],
  ['没有共享定义', '每次自己从头探索', '49%', '32%', '19%', '22%'],
  ['检索历史示例', '存下成功的问答和 SQL，按相似度取回参考，不检查', '100%', '76%', '57%', '48%'],
  ['检索示例 + 自行验证', '同上，并提示 agent 自己检查数据', '100%', '77%', '63%', '48%'],
  ['按表结构变化失效', '共享定义，只在表结构变化时停用', '100%', '75%', '59%', '48%'],
  [strong('MAVRA · 每次全部重查', C.blue), '消融：同样的检查与修复，去掉增量复用、每次全查', '100%', '82%', '74%', '48%'],
  [strong('MAVRA', C.blue), '共享定义，只重查受影响的条件，同一快照执行', strong('100%', C.green), strong('81%', C.green), strong('73%', C.green), '48%'],
], { x: M, y: 1.45, w: W - 2 * M, colW: [2.2, 4.75, 1.1, 1.25, 1.5, 1.333], size: 12 });
band(s, bulleted(null, C.blue, [
  '共享本身：数据未变时 49% → 100%，每题 5.6 → 3.6 轮；没见过的新题每题 75.6 s → 8.5 s（快 8.9 倍），token 少 39%',
  '维护：5 种破坏性更新下 MAVRA 73%，检索示例 57%，提示 agent 自行验证也只有 63%；去掉增量复用的消融准确率相同，准确率来自检查与修复本身',
  '剩下的错出在检测到但修不好的两种更新：重复加载 59%、日期键格式变更 15%（定义失效，agent 只能自己探索）；其余三种 93%–100%',
  '系统层（不用大模型，只换维护方式）：条件覆盖的更新下 0 错答（按表结构变化失效 629 错答）；并发写入下 0 次在被破坏的数据上作答；回归不需要标准答案',
  '负结果：单位变化所有方法同样过期；定义失效又修不好时，使用者每题 9.36 万 token，比独自探索（2.69 万）更费——下一步把使用者找到的修正经准入共享',
]), { y: 4.3, h: 2.45, size: 12 });
footnote(s, '11 种更新 = 4 种正常写入 + 5 种破坏性更新 + 备份副本 + 单位变化。破坏性更新：退货状态行、保留旧行的销售更正、重复加载、商品维度保留历史版本、日期键格式变更；单位变化：从某月起上游改按“分”记金额（数值 ×100），条件发现不了，作为对照。');
notes(s, '表里每种方法都写了做法。没有共享定义：每次自己探索。检索历史示例：把成功的问答存下来，按相似度取回参考，但不检查数据变没变。“每次全部重查”是 MAVRA 的消融：检查与修复完全一样，只是去掉增量复用，每次把定义的条件全部重查一遍。'
  + '读法：数据没变时，任何共享方法都从 49% 升到 100%——这是共享本身的收益，不是 MAVRA 独有。区别在数据变化之后：5 种破坏性更新下 MAVRA 73%，检索历史示例 57%，提示它自己验证也只有 63%。'
  + '消融和 MAVRA 准确率相同（差的 1 个点来自两种更新上共 3 道题，方向相反），说明准确率来自检查与修复本身，不来自增量复用。增量复用只省时间：受控实验里 19 条共享条件的定义，维护时间降到全部重查的 14%，但按表版本缓存验证结果的通用缓存也能到 17%，所以论文里不把效率当成贡献。'
  + '73% 不是 100%，剩下的错集中在两种更新：重复加载和日期键格式变更都能检测到，但没有过滤能修好，定义失效，agent 只能自己重新探索，正确率分别是 59% 和 15%；退货状态行、保留旧行的更正、商品维度保留历史版本这三种都能修复，93%–100%。'
  + '系统层不用大模型，固定学到的定义、只换维护方式：条件覆盖的更新下没有错答，并发下没有误答，回归测试不需要标准答案。'
  + '性能和负结果：有了共享记忆，没见过的新题每题从 75.6 秒降到 8.5 秒，快 8.9 倍，token 少 39%，每个正确答案的 token 少 70%；单位变化（上游改按分记金额）谁都发现不了，剩下 48% 是本来就不受影响的题，比如问的是变化之前的月份；定义失效又修不好时，使用者自己去修，花的 token 比独自探索还多，这是下一步。',
  'exp/2026-10-02-scenarios-ds（scen-stats.json：MAVRA = metric-global-snap，消融 = metric-global-def，逐种更新的正确率在 per_change）、快照压力测试、exp/2026-10-02-cache-baseline-tpcds、tools/sharing-stats.py（论文宏 \\Ds*、\\Rp*、\\Sn*、\\Cb*、\\Am*）。');

// 10 Guarantees, limits, and the three sentences ---------------------------------------------------
pres.addSection({ title: '边界与总结' });
s = content('MAVRA 的保证边界，以及三句话总结', '边界与总结');
const bw = 7.2, bx2 = M + bw + 0.35, bw2 = W - M - bx2;
table(s, [
  ['发生了什么', 'MAVRA 能做什么'],
  ['订单多了一条旧记录，有唯一的当前标志', good('检测，并修复为新修订')],
  ['整个批次被重复加载', lines('检测到重复，', '没有过滤能恢复一笔一行 → 失效并通知')],
  ['主表与备份副本都看起来合理', lines('无法判断哪份是业务事实', '→ 不擅自选择，失效并交给人确认')],
  ['上游改成按“分”记金额（数值 ×100），行数与键不变', bad('四类条件发现不了（单位变化对照）')],
  ['日期键能连上，但指错了日子（例：时区换算把 10 月 1 日凌晨的销售记成 9 月 30 日）', bad('发现不了：每个键都连上唯一的日期，日子对不对数据库里没有依据')],
  ['SQL 没有在 run_sql 的 metrics 参数里声明依据的定义', bad('照常执行与审查，但不在条件保证范围内')],
], { x: M, y: 1.2, w: bw, colW: [3.5, bw - 3.5], size: 13 });
[
  ['问题', 'agent 学到的定义共享给别人后，会因数据变化悄悄失效，而 SQL 照常执行、不报错。', C.red, C.grey],
  ['方法', '共享记忆层承担三项职责：只发布通过准入、带条件的定义；条件在查询快照上成立才允许使用；数据变化后替所有使用者修复或失效，并发布更快的等价版本。', C.blue, C.paleBlue],
  ['结果', '破坏性更新下答对 73%（检索示例 57%）；条件覆盖的更新 0 错答；并发写入下 0 次在被破坏的数据上作答；共享让任务快 8.9 倍。', C.violet, C.paleViolet],
].forEach(([label, body, color, pale], k) => {
  const y = 1.2 + k * 1.5;
  s.addShape('roundRect', { x: bx2, y, w: bw2, h: 1.4, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1 });
  text(s, label, { x: bx2 + 0.25, y: y + 0.1, w: 1.0, h: 0.4, fontSize: 16, bold: true, color });
  text(s, body, { x: bx2 + 0.25, y: y + 0.45, w: bw2 - 0.5, h: 0.9, fontSize: 12, valign: 'top' });
});
band(s, [
  { text: '两点要分清：', options: { bold: true, color: C.blue } },
  { text: 'MAVRA 不判断业务含义是否正确（含税还是不含税，需要有人给出可信的口径）；它也不保证每条 SQL 都对，保护的是在 run_sql 里声明了所依据定义版本的查询。' },
], { y: 5.75, h: 0.95, size: 13 });
s.addNotes('MAVRA 是严谨的管理员，但不是无所不知。能做的：旧记录有唯一的当前标志，检测并修复；整批重复加载，检测但修不了，失效并通知；主表和备份都合理，不擅自选，交给人。'
  + '做不到的有两类，都是数值本身错了、结构没错，行数和键都没变，四类条件发现不了。一是上游改成按分记金额。'
  + '二是日期键能连上、但指错了日子：比如门店系统按 UTC 记时间，北京时间 10 月 1 日凌晨 2 点的销售被记成 9 月 30 日 18 点，算进了 9 月；或者迟到的数据按入库那天记日期，而不是按销售那天。'
  + '这时每个日期键都存在、都只对应一天，日期键唯一和日期键完整性都成立，只是这笔销售被归到了错误的月份。哪一天是真正的销售日，数据库里没有依据，只有源系统知道，要靠和源系统对账来发现。'
  + '这一条是从条件的定义直接推出的边界（论文命题 1 之后写明），实验里没有专门构造这种更新；单位变化则是实验里的对照。'
  + '两类都一样：单看数据分不清是真变化还是错误，要靠懂业务的人或数据质量监控；agent 没声明用了哪个修订，也不在保证范围内。'
  + '两点要分清：MAVRA 不判断业务含义对不对，那需要有人给口径；它也不保证每条 SQL 都对，保护的是声明了受管修订的查询。'
  + '最后三句话：问题——学到的定义共享出去后会因数据变化悄悄失效，SQL 却不报错；方法——共享记忆层替使用者把住发布、依赖、维护与改进三关；'
  + '结果——破坏性更新下 73% 对 57%，条件覆盖的更新 0 错答，并发下 0 次误答，共享让任务快 8.9 倍。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
