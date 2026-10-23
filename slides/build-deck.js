// Builds slides/build/mavra-system.pptx, a 17-slide Chinese deck for listeners new to the field. Each slide makes one point
// that takes a minute or two to present: the slide carries the keywords, numbers and figures, the presenter does the
// talking, and the full script sits in the speaker notes. Order: title; the problem (sharing learned metric
// definitions makes agents consistent and fast; one everyday write makes a shared definition silently wrong; what
// MAVRA is, next to Text-to-SQL); the running example (one request, 9 月门店营业额: how the user agent handles it,
// and what it gets after three different writes); the method from three views, one figure each, each followed by the
// same request told in that view: architecture (the request step by step), data model (the four preconditions of
// 门店营业额 v2), lifecycle (repair to v3 after a data correction; invalidation after a duplicate load); results
// (accuracy, correctness); limits; summary.
// The figures come from slides/figures/ (drawn by `python3 tools/figures/build.py --deck` on noctis, rendered to
// PNG). Each figure states the mechanism in general terms and marks the running example (门店营业额) with a brown 例;
// the example slides carry the same brown 例 tag and number their rows with the figure's step numbers.
// The toy ledger is marked 示意; every other number comes from the archived run records or the paper's generated
// macros (overleaf/gen/*.tex); record paths go at the end of each slide's speaker notes. Wording uses the terms
// common in the database and data-warehouse industry (SQL, 前提条件, 版本, 校验, 主键唯一, 参照完整性, 拉链表 …).
// Usage: node build-deck.js [--out path]
'use strict';

const fs = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

const ROOT = path.resolve(__dirname, '..');
const FIG = path.join(__dirname, 'figures');
const at = process.argv.indexOf('--out');
const OUT = at > 0 ? path.resolve(process.argv[at + 1]) : path.join(ROOT, 'slides/build/mavra-system.pptx');

const FONT = 'Microsoft YaHei';
// Colours after the Nature (NPG) palette, the same hues as the figures (tools/figures/deckpal.py): navy for use and
// the deck's accent, green for publish and passed checks, cyan for maintain and optimize, salmon for pending, red for
// failures, brown for the running example, lavender for the summary; text set in a hue uses a shade dark enough to
// read on white.
const C = {
  ink: '1F2A37', muted: '5B6573', navy: '1E2A4A', ice: 'D3DAEB', white: 'FFFFFF', grey: 'F2F4F8',
  line: 'D5DBE3', blue: '3C5488', paleBlue: 'E9EDF5', amber: 'C4603F', paleAmber: 'FDECE6',
  violet: '5B6A94', paleViolet: 'EEF0F6', red: 'D23F29', green: '00826D', paleGreen: 'E3F4EF',
  cyan: '24809A', paleCyan: 'E2F3F7', brown: '7E6148',
};
const MONO = 'Consolas';
const W = 13.333, M = 0.6;
const RECORDED = '实验记录（来源见备注）；数据为仿 TPC-DS 的合成零售数据，题目中的年份略去。';
const FIGURE_NOTE = '按图中编号阅读；棕色“例”为贯穿示例，取自实验记录（来源见备注）。';
const OPT_RUN = 'noctis results/scen-20261008-opt/metric-1791439498065570（metric-global-opt）';
const TRACE_RUN = 'noctis results/scen-20261008-trace（--trace 逐次记录工具调用，副本 exp/2026-10-08-optimize/trace）';

// Width / height of a figure PNG, from its header.
function aspect(file) {
  const buf = fs.readFileSync(file);
  return buf.readUInt32BE(16) / buf.readUInt32BE(20);
}

// Place a figure below the title, as large as fits and centred in the space left.
function figure(slide, name, top, maxH) {
  const file = path.join(FIG, `${name}-zh.png`);
  const r = aspect(file);
  let w = W - 2 * M, h = w / r;
  if (h > maxH) { h = maxH; w = h * r; }
  slide.addImage({ path: file, x: (W - w) / 2, y: top, w, h, objectName: name });
  return { y: top, h };
}

function text(slide, value, opts) {
  slide.addText(value, { fontFace: FONT, color: C.ink, margin: 0, isTextBox: true, ...opts });
}

// One line across the slide: a short lead-in above a table, or the slide's take-away below it.
function line(slide, value, { y, h = 0.5, size = 18, color = C.ink, bold = false, align = 'left' }) {
  text(slide, value, { x: M, y, w: W - 2 * M, h, fontSize: size, color, bold, align, valign: 'middle' });
}

function footnote(slide, value) {
  text(slide, value, { x: M, y: 6.85, w: W - 2 * M - 0.8, h: 0.4, fontSize: 11, color: C.muted, valign: 'bottom' });
}

// Speaker notes, with the record paths behind the slide's numbers at the end.
function notes(slide, body, source) {
  slide.addNotes(source ? `${body}\n\n来源：${source}` : body);
}

// A plain table: header row in grey, body in white.
function table(slide, rows, { x = M, y, w = W - 2 * M, colW, size = 18, rowH, pad = 0.08 }) {
  const head = rows[0].map((t) => (typeof t === 'string'
    ? { text: t, options: { bold: true, fill: { color: C.grey } } }
    : { text: t.text, options: { ...t.options, bold: true, fill: { color: C.grey } } }));
  const body = rows.slice(1).map((r) => r.map((c) => (typeof c === 'string' ? { text: c } : c)));
  slide.addTable([head, ...body], { x, y, w, colW, rowH, fontFace: FONT, fontSize: size, color: C.ink,
    valign: 'middle', border: { type: 'solid', pt: 1, color: C.line }, margin: [pad, 0.12, pad, 0.12] });
}
const good = (t) => ({ text: t, options: { color: C.green, bold: true } });
const bad = (t) => ({ text: t, options: { color: C.red, bold: true } });
const strong = (t, color) => ({ text: t, options: { color, bold: true } });
const para = (t, options = {}) => ({ text: t, options: { breakLine: true, ...options } });

// A table cell holding the figure's step numbers (①…⑩) in the colour of their responsibility.
const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩';
const step = (nums, color) => ({ text: nums.map((n) => CIRCLED[n - 1]).join(''),
  options: { color, bold: true, align: 'center', fontSize: 20 } });

// The brown 例 tag of the figures, at the right end of an example slide's title.
function exampleTag(slide) {
  slide.addText('例', { x: W - M - 0.62, y: 0.47, w: 0.62, h: 0.42, shape: 'roundRect', rectRadius: 0.06,
    fill: { color: C.brown }, line: { color: C.brown }, fontFace: FONT, fontSize: 18, bold: true, color: C.white,
    align: 'center', valign: 'middle', margin: 0, objectName: 'example tag' });
}

// A tinted card: a bold heading, then a few short lines.
function card(slide, { x, y, w, h, head, body, color, pale, size = 20, headSize = 24 }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1,
    objectName: `card ${head}` });
  const headH = headSize / 40 + 0.1;
  text(slide, head, { x: x + 0.35, y: y + 0.25, w: w - 0.7, h: headH, fontSize: headSize, bold: true, color,
    valign: 'middle' });
  text(slide, body, { x: x + 0.35, y: y + 0.45 + headH, w: w - 0.7, h: h - 0.65 - headH, fontSize: size,
    valign: 'top', paraSpaceAfter: 10 });
}

// A card led by one big number.
function stat(slide, { x, y, w, h, big, head, body, color, pale }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1,
    objectName: `stat ${head}` });
  text(slide, big, { x: x + 0.4, y: y + 0.3, w: w - 0.8, h: 1.3, fontSize: 72, bold: true, color, valign: 'middle' });
  text(slide, head, { x: x + 0.4, y: y + 1.7, w: w - 0.8, h: 0.55, fontSize: 24, bold: true, valign: 'middle' });
  text(slide, body, { x: x + 0.4, y: y + 2.35, w: w - 0.8, h: h - 2.55, fontSize: 17, color: C.muted, valign: 'top' });
}

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.title = 'MAVRA：面向数据 agent 的可维护共享记忆';
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

// A figure slide: the figure as large as the slide allows, nothing else but the reading hint.
function figureSlide(title, name, maxH = 5.55) {
  const s = content(title, '方法');
  figure(s, name, 1.15, maxH);
  footnote(s, FIGURE_NOTE);
  return s;
}

// 1 Title -------------------------------------------------------------------------------------------
pres.addSection({ title: '开场' });
let s = pres.addSlide({ masterName: 'TITLE', sectionTitle: '开场' });
s.addText('MAVRA：面向数据 agent 的\n可维护共享记忆', { placeholder: 'title' });
s.addText('让 agent 学到的指标定义可被安全复用，并随数据变化持续维护', { placeholder: 'body' });
text(s, [
  para('MAVRA = Metric-Aware Validation and Reuse for Agents'),
  { text: '组会汇报 · 2026 年 10 月' },
], { x: M, y: 5.4, w: W - 2 * M, h: 0.8, fontSize: 16, color: C.ice, valign: 'top', paraSpaceAfter: 6 });
notes(s, '先用一句话说明这项工作：多个数据 agent 在同一个数据库上回答业务问题。一个 agent 学会了“门店营业额”的口径和 SQL，'
  + '我们希望其他 agent 直接复用，而不是每次从零摸索；难点在于数据持续写入，学到的指标定义可能静默失效。'
  + 'MAVRA 是位于 agent 和数据库之间的共享记忆层，负责让共享的指标定义可靠：只发布通过校验的定义；查询执行前校验其前提在当前数据上仍然成立；数据变化后统一维护与优化。'
  + '汇报顺序：问题（第 2–4 页）→ 贯穿示例，一个用户请求（第 5–6 页）→ 方法的三个视角，每个视角一张图，再用示例讲一遍（第 7–13 页）→ 实验结果（第 14–15 页）→ 边界与总结（第 16–17 页）。每页只讲一件事。');

// 2 Sharing learned definitions ----------------------------------------------------------------------
pres.addSection({ title: '问题' });
s = content('共享 agent 学到的指标定义：结果一致，速度更快', '问题');
line(s, '难点在口径：用哪一列金额？按哪个日期归属月份？表结构里没有。', { y: 1.3, h: 0.6, size: 20, color: C.muted });
{
  const gap = 0.5, half = (W - 2 * M - gap) / 2;
  card(s, { x: M, y: 2.2, w: half, h: 3.4, head: '无共享：每次各自摸索', color: C.muted, pale: C.grey, size: 24, body: [
    para('同一问题求解三次'),
    para('两次选错金额列 ✗', { color: C.red, bold: true }),
    { text: '新问题准确率 49%' },
  ] });
  card(s, { x: M + half + gap, y: 2.2, w: half, h: 3.4, head: '共享指标定义', color: C.blue, pale: C.paleBlue, size: 24,
    body: [
    para('三次都用同一定义 ✓', { color: C.green, bold: true }),
    para('新问题准确率 100%'),
    { text: '单题提速 2.5–8.9 倍' },
  ] });
}
footnote(s, RECORDED);
notes(s, '先交代场景。数据 agent 基于大模型，接到“9 月门店营业额是多少”这类业务问题后，自主查看表结构、编写 SQL 并给出结果。它的难点不在 SQL 语法，而在指标口径：营业额用哪一列金额、按哪个日期归属月份，这些信息不在表结构里。'
  + '左侧是实验记录：只给出“门店营业额”这个名称，没有共享定义的 agent 独立求解三次，两次选用了折扣前销售额（ss_ext_sales_price），得到 1413.8 万，错误；一次选用了实付金额（ss_net_paid），得到 1307.0 万，正确。每次重新摸索，结果就不稳定；45 道未参与学习的新问题，准确率只有 49%。'
  + '右侧：把一个 agent 学到的指标定义共享出去，三次均命中同一定义，结果正确，交互从 5 轮降到 3 轮；新问题准确率 100%，单题提速 2.5–8.9 倍：两轮实验分别是 33.4 → 13.2 秒（2.5 倍，token 减少 30%）和 75.6 → 8.5 秒（8.9 倍，token 减少 39%），倍数随大模型接口的响应时间变化。这是共享本身带来的提升。'
  + '这里的“指标定义”指 agent 学到的计算规则，例如：门店营业额 = 门店销售实付金额之和，按销售日期归属月份。'
  + '共享也带来新的问题：数据持续写入，指标定义可能静默失效——下一页给出例子。',
  'noctis results/scen-20261002，未参与学习的问题 M1-P1（9 月门店营业额）；无共享：dsv41flash-r1-a、r2-b、r3-a；MAVRA：dsv41flash-r1–r3-g3fix--snap；'
  + '49% → 100% 与 5 轮 → 3 轮：论文宏 \\Ds*；提速与 token：tools/sharing-stats.py，2.5 倍、33.4 → 13.2 秒、30% 为 results/scen-20261010（overleaf/gen/sharing.tex 的 \\AmHold*），8.9 倍、75.6 → 8.5 秒、39% 为 results/scen-20261002。');

// 3 The difficulty: a toy ledger ---------------------------------------------------------------------
s = content('难点：一次日常写入，共享的定义就静默算错', '问题');
line(s, '指标定义：营业额 = SUM(金额)', { y: 1.25, size: 20, color: C.muted });
{
  const gap = 0.8, colL = (W - 2 * M - gap) / 2, xR = M + colL + gap;
  line(s, '第一天', { y: 1.95, size: 20, bold: true, color: C.blue });
  table(s, [
    ['订单号', '金额', '状态'],
    ['001', '100 元', '当前'],
    ['002', '200 元', '当前'],
    ['003', '300 元', '当前'],
  ], { x: M, y: 2.5, w: colL, colW: [1.8, 2.0, colL - 3.8], rowH: 0.5 });
  text(s, [{ text: '营业额 = 600 元 ✓', options: { bold: true, color: C.green } }],
    { x: M, y: 4.65, w: colL, h: 0.5, fontSize: 22, valign: 'middle' });
  text(s, '第二天：002 更正为 250 元，旧行保留', { x: xR, y: 1.95, w: colL, h: 0.5, fontSize: 20, bold: true,
    color: C.blue, valign: 'middle' });
  table(s, [
    ['订单号', '金额', '状态'],
    ['001', '100 元', '当前'],
    ['002', '200 元', { text: '历史', options: { color: C.muted } }],
    ['002', '250 元', '当前'],
    ['003', '300 元', '当前'],
  ], { x: xR, y: 2.5, w: colL, colW: [1.8, 2.0, colL - 3.8], rowH: 0.5 });
  text(s, [{ text: '营业额 = 850 元 ✗（应为 650）', options: { bold: true, color: C.red } }],
    { x: xR, y: 5.15, w: colL, h: 0.5, fontSize: 22, valign: 'middle' });
}
line(s, '错的不是 SQL，而是它默认的前提：每个订单只有一行', { y: 5.95, h: 0.6, size: 22, bold: true, color: C.blue });
footnote(s, '示意。');
notes(s, '用一个示意的小账本说明难点。指标定义是“营业额 = 金额之和”。第一天有三笔订单，算出 600 元，结果正确。'
  + '第二天订单 002 更正为 250 元。数据仓库的常见做法是保留旧行、标记为历史，再插入一行当前记录。沿用原定义会把 200 和 250 都计入，得到 850 元，正确结果是 650 元。'
  + 'SQL 本身没有错，也不报错；出错的是它隐含的前提“每个订单只有一行”。这类写入是日常的 ETL 操作，表结构没有变化，agent 会给出错误结果且毫无察觉；而指标定义是共享的，一处失效，所有引用它的 agent 同时出错。'
  + '所以只共享 SQL 不够，还要把前提显式保存下来，在使用前校验——这是 MAVRA 的出发点。');

// 4 What MAVRA is, next to Text-to-SQL ---------------------------------------------------------------
s = content('MAVRA：agent 与数据库之间的共享记忆层', '问题');
table(s, [
  ['', 'Text-to-SQL', 'MAVRA'],
  [strong('处理对象', C.muted), '一个问题', 'agent 学到的指标定义'],
  [strong('产出', C.muted), '一条 SQL', '经过校验、可复用的共享记忆'],
  [strong('状态', C.muted), '不保留', '保存，并随数据变化维护'],
], { y: 1.6, colW: [2.2, 4.4, 5.533], size: 22, rowH: 0.85 });
line(s, '两者互补：MAVRA 不生成 SQL，可配合任意 Text-to-SQL 模型或 agent', { y: 5.35, h: 0.6, size: 20, color: C.blue,
  bold: true });
notes(s, '说明 MAVRA 是什么，以及它和 Text-to-SQL 的区别。Text-to-SQL 研究如何把一个问题转换成一条 SQL，每次独立，不保留状态。'
  + 'MAVRA 不生成 SQL，它处在 agent 和数据库之间，保存 agent 学到的指标定义，并保证这些定义在数据变化后仍然正确。两者可以配合使用：用户 agent 用什么模型写 SQL 都可以。'
  + 'MAVRA 也不同于指标平台（由人工声明指标，运行时不校验声明中的关联关系）和数据质量规则（按表校验人工编写的规则，不知道哪个指标依赖哪条规则）：MAVRA 的前提条件由系统从 SQL 推导，因此清楚每个指标依赖哪些前提。'
  + '它承担三项职责：发布——只让通过校验的定义进入共享记忆；使用——查询执行前在当前数据上校验定义的前提；维护与优化——数据变化后统一修复或置为失效，并发布更快的等价 SQL。后面用一个例子把这三件事讲具体。');

// 5 The running example: one request ---------------------------------------------------------------
pres.addSection({ title: '示例' });
s = content('贯穿示例：用户 agent 问“9 月门店营业额是多少？”', '示例');
exampleTag(s);
line(s, '背景：门店营业额已学会并共享（v2）；store_sales 刚做过一次增量加载', { y: 1.3, h: 0.6, size: 20,
  color: C.muted });
table(s, [
  ['', '用户 agent B', 'MAVRA'],
  [strong('1', C.blue), 'find_metric("门店营业额")', '返回指标定义 v2：口径、SQL、前提'],
  [strong('2', C.blue), 'run_sql(SQL，声明使用 v2)', '校验前提，通过后执行'],
  [strong('3', C.blue), good('回答 2613.9 万 ✓'), '返回结果'],
], { y: 2.2, colW: [0.8, 5.4, 5.933], size: 22, rowH: 0.85 });
footnote(s, RECORDED);
notes(s, '这是贯穿全文的示例，后面三个视角都用它来讲。用户 agent B 收到的问题是：“9 月的门店营业额是多少？保留两位小数。”就是第 2 页那道题。题中只有指标名称，没有口径。'
  + '背景：此前内置 agent 完成过一次学习任务“3 月的门店营业额是多少？”，题中给出了口径——门店销售明细的实付金额（ss_net_paid）之和，按销售日期归属月份。它用 5 轮、7 次工具调用写出关联日期维表、按月过滤的 SQL，得到 1357.0 万，结果正确；MAVRA 从中提取指标定义，发布前校验 7 项全部通过，发布为 v1。'
  + '之后 MAVRA 的优化把按月关联日期维表改写为日期键范围过滤，14 个期间结果一致，执行时间 29.1 → 23.3 毫秒，发布为 v2。B 提问之前，store_sales 刚做过一次增量加载。'
  + 'B 的处理分三步。第 1 步调用 find_metric，按名称查询共享的指标定义，拿到 v2 的口径、SQL 和前提条件。第 2 步参照 v2 的 SQL 写出本题 SQL，调用 run_sql 执行，并在 metrics 参数中声明所用的是门店营业额 v2；MAVRA 先校验 v2 的前提在当前数据上是否成立，成立才执行。第 3 步，B 回答 2613.9 万，正确。'
  + 'B 不需要自己摸索口径；这个定义现在还能不能用，由 MAVRA 负责判断。下一页看如果写入换成别的类型会怎样。',
  OPT_RUN + '：学习 M1-L1（records、learning、events.learn）、优化（optimizing.rounds）、append 阶段 M1-P1 的记录（4 轮、6 次工具调用、12.2 秒，metrics 声明门店营业额 revision 1 = v2，答案 26,139,303.60）。');

// 6 The same request after three writes ---------------------------------------------------------------
s = content('同一个请求，三种写入之后', '示例');
exampleTag(s);
line(s, '三种写入都发生在 store_sales 上，各自基于同一份初始数据', { y: 1.3, h: 0.6, size: 20, color: C.muted });
table(s, [
  ['写入', '沿用原定义', 'MAVRA'],
  [strong('增量加载', C.ink), good('2613.9 万 ✓'), good('v2 照常使用：2613.9 万 ✓')],
  [strong('数据更正', C.ink), bad('1430.1 万 ✗'), good('修复为 v3：1293.3 万 ✓')],
  [strong('重复加载', C.ink), bad('2613.9 万 ✗'), strong('无法修复：指标失效，通知 B', C.amber)],
], { y: 2.2, colW: [2.4, 3.6, 6.133], size: 22, rowH: 0.85 });
footnote(s, RECORDED);
notes(s, '同一个请求，把 B 提问之前的写入换成三种日常写入，三种写入各自从同一份初始数据开始。'
  + '增量加载：追加了一批 9 月新销售，小票号都是新的，9 月销售额确实翻倍。沿用原定义结果正确；MAVRA 校验后前提都成立，v2 照常使用，2613.9 万。'
  + '数据更正：旧行保留并标记为非当前，再插入更正后的行，共 65,915 行。沿用原定义多算了 137 万，得到 1430.1 万；MAVRA 发现主键不再唯一，自动修复——加上过滤条件 ss_is_current = \'1\'，发布 v3，B 用 v3 得到 1293.3 万，正确。'
  + '重复加载：4 个月的销售批次被原样再加载一次。沿用原定义得到 2613.9 万——和增量加载的结果一模一样，但这次是错的。MAVRA 发现主键不再唯一，而重复的行与原行完全相同，没有过滤条件能修复，于是将指标置为失效并通知 B，不返回错误结果；B 只能自行探索，本次 19 次工具调用、158 秒后答对 1307.0 万。'
  + '要点：三种写入 SQL 都不报错；MAVRA 先校验前提，成立则使用，不成立则修复，无法修复则置为失效。接下来从三个视角看它是怎么做到的。',
  OPT_RUN + ' 的 append / revision / dupload 三个阶段（M1-P1 的 records 与 events：maintenance、revoked、repair_*、ref_rejected）；'
  + '沿用原定义：noctis results/scen-20261002 dsv41flash-r1-g3fix--schema（仅在表结构变更时失效）；写入行数：writes.*.truth_rows / hidden_rows；重复加载 = 完全相同的行再装载一次（src/scenario.rs Change::Duplicate）。');

// 7 View one: architecture ---------------------------------------------------------------------------------
pres.addSection({ title: '方法' });
s = figureSlide('视角一 · 系统架构：MAVRA 的位置与三项职责', 'structure');
notes(s, '第一个视角是系统架构：MAVRA 处在什么位置，承担哪些职责。图中按编号阅读：1–2 是发布（绿色），3–6 是使用（藏青），7–9 是数据写入后的维护与优化（青色）。'
  + '上方是两类 agent：左侧的内置 agent 基于大模型，负责学习；右侧的用户 agent 可以有很多个，负责提问、编写 SQL、复用指标定义。一次学习，多次复用。'
  + '中间是共享记忆：每个指标定义保存口径、SQL、前提条件和版本号，此外按（前提，表版本）缓存校验结果，跨指标、跨 agent 复用。'
  + '第 1 步，内置 agent 完成学习任务，提交候选定义。第 2 步，发布前校验：结果经确认正确（实验中用参考答案判定，生产环境由指标负责人确认一次），并且按定义重新生成的 SQL 能在学习时的数据上复现相同结果，通过后连同前提条件一起入库。'
  + '第 3 步，用户 agent 取指标定义，再提交 SQL 并声明所用的指标版本。第 4 步，执行前校验读取该版本的前提条件和已缓存的校验结果。第 5 步，在本次查询的快照上校验前提，通过后在同一快照上执行，校验与执行之间其他事务提交的写入对本次查询不可见。第 6 步，返回有效版本和查询结果。'
  + '第 7 步，ETL 照常写入，MAVRA 不拦截写入；每次写入在同一事务内递增表版本号。第 8 步，下次使用时 MAVRA 比较表版本，只对受影响的前提执行校验查询。第 9 步，把结果写回共享记忆：通过则继续使用；不通过则自动修复并发布新版本，无法修复则置为失效。此外，发现结果等价且执行更快的 SQL 时，校验后也发布为新版本。'
  + '发布前校验、执行前校验和自动修复都是 MAVRA 在数据库上执行的 SQL，不依赖大模型判断。下一页把示例请求按这些编号走一遍。',
  '学习：' + TRACE_RUN + '；v2 计时与增量加载后的 9 月结果：' + OPT_RUN + '。');

// 8 View one, the example: the request step by step ----------------------------------------------------
s = content('视角一 · 例：这个请求在系统中的步骤', '方法');
exampleTag(s);
table(s, [
  ['图中编号', '本例中按先后发生的事'],
  [step([1, 2], C.green), '此前：学习，发布 v1；优化后为 v2'],
  [step([7], C.cyan), '增量加载：store_sales 表版本加一'],
  [step([3], C.blue), 'B：find_metric("门店营业额")'],
  [step([8], C.cyan), '只校验受影响的 2 个前提：5.5 秒'],
  [step([9], C.cyan), '校验通过：v2 有效，返回给 B'],
  [step([3], C.blue), 'B：run_sql(SQL，声明使用 v2)'],
  [step([4, 5], C.blue), '同一快照：核对前提（复用结果）并执行，29 毫秒'],
  [step([6], C.blue), good('返回 2613.9 万 ✓')],
], { y: 1.25, colW: [1.8, 10.333], size: 20, rowH: 0.6 });
footnote(s, RECORDED);
notes(s, '把示例请求放到架构图上，编号与上一页图中一致，按实际发生的先后排列。'
  + '①②此前：内置 agent 学习“3 月门店营业额”，提交候选定义；发布前校验通过后入库，为 v1；之后经优化发布 v2。'
  + '⑦：ETL 做增量加载，向 store_sales 追加 27,095 行 9 月新销售，小票号都是新的；写入在同一事务内递增 store_sales 的表版本。MAVRA 不拦截写入，此时也不做任何校验。'
  + '③：B 调用 find_metric("门店营业额")，MAVRA 匹配到门店营业额，以及名称相近的电子品类门店营业额。'
  + '⑧：返回之前先做维护。比较表版本，发现只有 store_sales 变了，于是只执行读到 store_sales 的两条校验 SQL——主键唯一 5.3 秒、参照完整性 0.15 秒；date_dim 没有写入，其上的维表主键唯一和日期键连续不重新校验。这两条结果被几个指标定义共用，只执行一次。'
  + '⑨：前提全部通过，v2 继续有效，校验结果按（前提，表版本）写入缓存；B 拿到 v2 的口径、SQL 和前提。'
  + '③（第二次）：B 参照 v2 的 SQL 写出本题 SQL（按 9 月的日期键范围过滤），调用 run_sql，在 metrics 参数中声明门店营业额 v2（调用里写作 revision: 1，版本号从 0 开始）。'
  + '④⑤：执行前校验读取 v2 的 4 个前提，当前表版本下都有校验结果，直接复用，不再执行校验 SQL；随后在同一快照上执行 B 的 SQL，耗时 29 毫秒。⑥：返回有效版本和结果 26,139,303.60，B 回答 2613.9 万，正确。'
  + '整个请求 B 用了 4 轮、6 次工具调用、12.2 秒。要点：校验发生在使用时，且只校验受写入影响的前提；结果被其他指标和后续查询复用。',
  OPT_RUN + ' append 阶段：M1-P1 的记录（run、db.by_kind：校验 0 条、执行 1 条 29.2 ms；metric_use.declared = 门店营业额 revision 1）与 events.append 的 maintenance 事件'
  + '（电子品类门店营业额执行粒度 5,311.8 ms、覆盖 152.8 ms，门店营业额 reused，date_dim 上两个条件 skipped）；增量加载行数：writes.append.truth_rows。');

// 9 View two: the data model -------------------------------------------------------------------------------
s = figureSlide('视角二 · 数据模型：每个指标定义都附带前提条件', 'definition');
notes(s, '第二个视角是数据模型：共享记忆里保存的到底是什么。一个指标定义 = 口径 + SQL + 前提条件 + 版本号。图中按编号阅读：上半部分 1–3 从左到右，下半部分 4–7 从上到下。'
  + '上半部分（1 SQL 结构 → 2 隐含的数据假设 → 3 前提条件）说明前提条件从哪里来：由系统根据 SQL 的结构自动推导。对事实表求和，隐含“一行对应一笔销售明细”的粒度假设，对应的前提是主键唯一，即行数等于不同主键（小票号，商品）的数量；'
  + '关联日期维表并按月过滤，隐含 N:1 的关联基数，对应维表主键唯一，否则关联会使行数膨胀；内连接会丢弃关联不上的行，因此要求关联不上的行不超过学习时的比例（容差 0.1 个百分点），即参照完整性。'
  + '论文中把前提分为四类：粒度、关联基数、日期角色、参照完整性；门店营业额只关联日期维表，关联基数和日期角色都归结为“维表主键唯一”，所以 v1 有 3 个前提。v2 把期间过滤改写为日期键范围，这种写法还要求每月的日期键连续，因此新增第 4 个前提“日期键连续”。'
  + '下半部分说明为什么需要前提条件。第 4 行是三种写入。先看第 6 行：SQL 都不报错，增量加载和重复加载的结果都是 2613.9 万，一对一错；数据更正后多算了 137 万。'
  + '再看第 5 行，前提条件能把它们区分开：增量加载新增的都是新小票号，主键唯一校验通过；数据更正和重复加载后，行数都多于不同主键数，主键唯一校验不通过。第 7 行是结论。'
  + '前提条件也有覆盖不到的情况，例如金额单位由元改为分，行数和主键都不变，后面的边界页会说明。下一页看门店营业额 v2 的 4 个前提具体怎么校验。',
  '前提校验结果：' + OPT_RUN + ' 的 maintenance 与 revoked 事件（append、revision、dupload 三个阶段）；'
  + '沿用原定义的结果与正确结果：noctis results/scen-20261002 dsv41flash-r1-g3fix--schema；前提的四类划分与命题 1：论文 §4。');

// 10 View two, the example: the four preconditions of v2 --------------------------------------------------
s = content('视角二 · 例：门店营业额 v2 的 4 个前提', '方法');
exampleTag(s);
line(s, 'v2 的 SQL', { y: 1.2, h: 0.45, size: 18, bold: true, color: C.blue });
text(s, [
  para('SELECT ROUND(SUM(ss_net_paid), 2) FROM store_sales'),
  { text: 'WHERE ss_sold_date_sk BETWEEN :月初日期键 AND :月末日期键' },
], { x: M, y: 1.65, w: W - 2 * M, h: 0.7, fontSize: 15, fontFace: MONO, valign: 'middle' });
table(s, [
  ['前提', '校验 SQL 检查什么', '学习时的基准'],
  [strong('主键唯一', C.blue), '行数 = 不同（小票号，商品）数', '1,000,000 = 1,000,000'],
  [strong('维表主键唯一', C.blue), 'date_dim 的日期键不重复', '1,096 个日期键'],
  [strong('参照完整性', C.blue), '关联不上 date_dim 的销售行占比', '1.03%'],
  [strong('日期键连续', C.cyan), '每个月的日期键连续、首尾相接', '36 个月全部连续'],
], { y: 2.5, colW: [2.6, 5.6, 3.933], size: 20, rowH: 0.66 });
line(s, '前提 = 一条校验 SQL + 学习时的基准值，随定义一起保存', { y: 6.1, h: 0.6, size: 20, bold: true, color: C.blue });
footnote(s, RECORDED);
notes(s, '这一页展示共享记忆里“门店营业额 v2”这条记录带的前提条件。最上面是 v2 的 SQL：对 store_sales 的实付金额求和，按日期键范围过滤当月（年份条件略去）。'
  + '记录里除了 SQL，还有口径（门店销售明细的实付金额之和，按销售日期归属月份）、版本号、依赖的表及表版本、证据（学习任务 3 月 1357.0 万，发布前校验 7 项通过；优化时 14 个期间结果一致），以及给 agent 看的说明，例如约 1.03% 的销售行没有匹配的日期，按口径不计入。'
  + '表中是 v2 的 4 个前提。每个前提对应一条校验 SQL，发布时在学习时的数据上执行一次，记下基准值。'
  + '主键唯一：行数等于不同（小票号，商品）的数量，学习时都是 1,000,000。维表主键唯一：date_dim 的 1,096 个日期键互不重复。参照完整性：关联不上 date_dim 的销售行占比，学习时 1.03%，之后不得超过 1.03% 加 0.1 个百分点。日期键连续：36 个月，每个月的日期键都连续，相邻月份首尾相接；这一条是优化成 v2 时新增的（青色）。'
  + '写入之后只重跑读到被写表的那几条：三种写入都只改 store_sales，所以只重算主键唯一和参照完整性两条。增量加载后 1,027,095 行、1,027,095 个主键，通过；数据更正后 1,065,915 行只有 1,000,000 个主键，重复加载后 1,110,165 行只有 1,000,000 个，不通过。参照完整性三次都通过（1.00%、0.97%、0.93%）。',
  OPT_RUN + ' metric_report.entries（门店营业额 revision 1：口径、示例 SQL、说明、依赖表版本、证据）；三种写入后的校验值：events.append / revision / dupload 的 maintenance 与 revoked 事件（loss、行数与主键数）；'
  + '增量加载后的行数 = 1,000,000 + writes.append.truth_rows（主键唯一通过即行数等于主键数）；日期键连续的月份数：论文 §7.8（gen/premise.tex）。');

// 11 View three: the lifecycle -------------------------------------------------------------------------------
s = figureSlide('视角三 · 生命周期：校验、修复、优化与失效', 'process');
notes(s, '第三个视角是生命周期：一个指标定义随着数据变化会经历哪些状态。图中按编号 1–10 阅读：先沿中间一行从左到右，再看上方的优化，最后沿下方一行从右到左。颜色与第一张图的三项职责对应：绿色是发布，藏青是使用，青色是维护与优化，橙粉是待校验，红色虚线是指标失效。'
  + '第 1 步学习：内置 agent 完成学习任务、提取指标定义。第 2 步发布前校验：通过后入库，同时保存前提条件和证据。第 3 步“有效”是指标定义的正常状态：使用方声明指标版本后直接使用。'
  + '第 4 步优化：MAVRA 为已发布的定义寻找更快的 SQL，只有在各期间结果一致、并且在同一快照内配对测量确实更快时，才发布为新版本，新 SQL 依赖的假设也加入前提条件。'
  + '第 5 步待校验：指标定义依赖的表一旦发生写入，就进入待校验状态——这个状态并不持久化，而是在使用时比较表版本得出的；写入发生时不做任何处理。'
  + '第 6 步执行前校验：下次使用时，在本次查询的快照上只校验受影响的前提，校验结果按表版本缓存、跨指标复用。校验通过，回到第 3 步继续使用。'
  + '校验不通过，进入下方一行。第 7 步自动修复：在取值较少的列上寻找“列 = 值”形式的过滤条件，要求能恢复前提且不丢失主键，并且可行的过滤条件必须唯一。第 8 步回归测试：在学习时的数据上重算，结果必须与学习时一致。第 9 步发布新版本，回到第 3 步；引用旧版本的查询会被拒绝。'
  + '第 10 步：如果找不到可行的过滤条件，或者可行的不止一个（例如同时存在主表和备份），MAVRA 不自动选择，而是将指标置为失效并通知使用方，等待重新学习（回到第 1 步）。'
  + '图中未画出的一种情况：写入只破坏了优化时新增的前提（例如某个月的日期键被重新编号、不再连续），而 v1 的前提都成立，此时只撤下 v2、恢复 v1；实验中 4 个指标定义这样回退，之后 20 个查询结果全部正确。'
  + '后面两页用示例分别讲修复（数据更正）和失效（重复加载）两条路径。',
  '学习：' + TRACE_RUN + '；优化计时、三种写入的 maintenance / revoked / repair_* 事件与 9 月结果：' + OPT_RUN
  + '；恢复 v1：论文 §7.8（gen/premise.tex）。');

// 12 View three, the example: a data correction repairs v2 into v3 ------------------------------------------
s = content('视角三 · 例：数据更正后，v2 修复为 v3', '方法');
exampleTag(s);
table(s, [
  ['图中编号', '本例中发生的事'],
  [step([5], C.amber), '数据更正：旧行保留，+65,915 行'],
  [step([6], C.blue), bad('主键唯一 ✗：1,065,915 行，1,000,000 个主键')],
  [step([7], C.cyan), '自动修复：唯一可行的过滤条件 ss_is_current = \'1\''],
  [step([8], C.cyan), '回归测试：重算 3 月，仍为 1357.0 万 ✓'],
  [step([9], C.cyan), '发布 v3，用时 19.3 秒'],
  [step([3], C.blue), good('B 声明使用 v3：1293.3 万 ✓')],
], { y: 1.4, colW: [1.8, 10.333], size: 20, rowH: 0.7 });
footnote(s, RECORDED);
notes(s, '修复路径，编号对应上一页的生命周期图。⑤：数据更正把 65,915 行销售更正了一次——旧行保留并标记为非当前（ss_is_current = \'0\'），再插入更正后的行；v2 进入待校验。'
  + '⑥：B 下次查询时校验，主键唯一不通过：1,065,915 行只有 1,000,000 个不同主键，v2 失效。'
  + '⑦：自动修复。MAVRA 在取值较少的列上搜索“列 = 值”形式的过滤条件，要求加上之后主键恢复唯一，并且一个主键都不丢；可行的过滤条件必须唯一。结果只有 ss_is_current = \'1\' 一个可行。'
  + '⑧：回归测试，在学习时的数据上用新 SQL 重算 3 月，仍为 1357.0 万，与学习时一致。'
  + '⑨：发布 v3；此后引用 v2 的查询会被拒绝，并提示改用 v3。门店营业额这一次维护与修复共 19.3 秒，全部是 MAVRA 在数据库上执行的 SQL，不依赖大模型。'
  + '③：v3 进入有效状态。B 拿到 v3 和变更通知，声明使用 v3，得到 1293.3 万，正确；若不维护、沿用 v2，结果是 1430.1 万。'
  + '这次请求 B 共用了 112 秒，其中包括这一轮里 3 个相关指标定义的维护与修复；B 有一条没加过滤条件的探查 SQL 被执行前审查拒绝，并提示需加 ss_is_current = \'1\'。',
  OPT_RUN + ' revision 阶段：events.revision（revoked：1,065,915 行只有 1,000,000 个不同键；repair_candidate：ss_is_current = \'1\'；repair_promoted：G3、G4、G5、G8 通过；maintenance wall 19.3 s）、'
  + 'M1-P1 的记录（metric_use.declared = 门店营业额 revision 2 = v3，答案 12,932,888.04，112 秒，1 次拒绝）；沿用 v2 的 1430.1 万：noctis results/scen-20261002 dsv41flash-r1-g3fix--schema。');

// 13 View three, the example: a duplicate load invalidates the definition -----------------------------------
s = content('视角三 · 例：重复加载后，指标失效', '方法');
exampleTag(s);
table(s, [
  ['图中编号', '本例中发生的事'],
  [step([5], C.amber), '重复加载：4 个月的批次原样再加载，+110,165 行'],
  [step([6], C.blue), bad('主键唯一 ✗：1,110,165 行，1,000,000 个主键')],
  [step([7], C.cyan), '自动修复：重复行与原行完全相同，没有可用的过滤条件'],
  [step([10], C.red), strong('指标失效：拒绝引用，通知使用方', C.red)],
  [{ text: 'B', options: { color: C.blue, bold: true, align: 'center', fontSize: 20 } }, 'B 自行探索：19 次工具调用后答对'],
], { y: 1.4, colW: [1.8, 10.333], size: 20, rowH: 0.7 });
line(s, '无法修复时置为失效，不静默返回错误结果', { y: 5.75, h: 0.6, size: 20, bold: true, color: C.blue });
footnote(s, RECORDED);
notes(s, '失效路径。⑤：重复加载把 6 月到 9 月的门店销售批次原样再加载了一次，共 110,165 行；v2 进入待校验。'
  + '⑥：校验主键唯一不通过，1,110,165 行只有 1,000,000 个不同主键。'
  + '⑦：自动修复失败。重复的行与原行完全相同，没有任何一列能把它们区分开，所以找不到能恢复主键唯一的过滤条件。'
  + '⑩：MAVRA 不猜，将门店营业额置为失效并通知使用方：find_metric 不再返回它，声明它的查询被拒绝，拒绝时说明原因（主键不唯一，1,110,165 行只有 1,000,000 个主键）。'
  + '这一步本身的维护用了 20.0 秒。B 收到通知后只能自行探索，本次用了 19 次工具调用、158 秒，最后自己写了去重 SQL，答对 1307.0 万；若沿用原定义，会静默得到 2613.9 万。'
  + '失效之后由 agent 自行探索，结果不一定对：实验结果页会看到，这类写入后的准确率是 59%。要点：MAVRA 宁可失效，也不返回错误结果。',
  OPT_RUN + ' dupload 阶段：events.dupload（revoked：1,110,165 行只有 1,000,000 个不同键；repair_failed：没有找到能恢复唯一性的过滤；ref_rejected；maintenance wall 20.0 s）、'
  + 'M1-P1 的记录（19 次工具调用、158 秒、答案 13,069,651.80 正确，未声明指标版本）；重复加载的定义：src/scenario.rs Change::Duplicate（完全相同的行）。');

// 14 Results: accuracy ----------------------------------------------------------------------------------------
pres.addSection({ title: '结果' });
s = content('实验结果：数据变化后，MAVRA 的准确率最高', '结果');
table(s, [
  ['方法', '数据不变', '11 类写入后', '破坏性写入后'],
  ['无共享', '49%', '32%', '19%'],
  ['检索历史示例', '100%', '76%', '57%'],
  ['检索示例 + 自行校验', '100%', '77%', '63%'],
  ['按表结构变更失效', '100%', '75%', '59%'],
  [strong('MAVRA', C.blue), good('100%'), good('81%'), good('73%')],
], { y: 1.4, colW: [4.4, 2.4, 2.6, 2.733], size: 22, rowH: 0.75 });
footnote(s, '端到端准确率，DeepSeek V4.1 Flash agent，每种方法独立运行 3 次；实验记录（来源见备注）。');
notes(s, '端到端准确率，每种方法独立运行 3 次。数据不变时，所有共享方法都是 100%，比无共享的 49% 高很多——这是共享本身带来的提升，任何共享方法都具备。'
  + '差别出现在数据变化之后。各方法的做法：无共享，每次从零探索；检索历史示例，是 agent 记忆中常见的做法，保存成功的问答和 SQL，按相似度检索作为参考，但不校验数据是否变化；检索示例 + 自行校验，再提示 agent 自己校验数据；按表结构变更失效，共享定义，只在表结构变化时失效；MAVRA，共享定义并做前提校验、自动修复与失效。'
  + '11 类写入 = 4 类常规写入 + 5 类破坏性写入（退货状态流水、更正保留旧行、重复加载、商品维表拉链表、日期键格式变更）+ 备份副本 + 金额单位变化。5 类破坏性写入后，MAVRA 73%，检索历史示例 57%，自行校验也只有 63%，仅按表结构变更失效 59%。'
  + 'MAVRA 还有一个消融版本“每次全量重新校验”（校验与修复相同，去掉按表版本复用），准确率为 82% / 74%，与 MAVRA 相当，说明准确率来自校验与修复本身；按表版本复用只节省时间，论文不把效率作为贡献。'
  + '73% 不是 100%：剩余错误集中在两类写入——重复加载和日期键格式变更都能检测到，但没有过滤条件能修复，指标失效后由 agent 自行重新探索，准确率分别为 59% 和 15%；其余三类破坏性写入都能自动修复，准确率 93%–100%。',
  'exp/2026-10-02-scenarios-ds（scen-stats.json：MAVRA = metric-global-snap，消融 = metric-global-def，各类写入的准确率在 per_change；论文宏 \\Ds*）。');

// 15 Results: no silent wrong answers --------------------------------------------------------------------------
s = content('实验结果：前提能检测到的写入，0 次静默错误', '结果');
{
  const gap = 0.5, half = (W - 2 * M - gap) / 2;
  stat(s, { x: M, y: 1.5, w: half, h: 3.6, big: '0', head: '错误结果', color: C.green, pale: C.paleGreen,
    body: '受控实验，前提可检测的写入；对照：仅按表结构变更失效 629 个' });
  stat(s, { x: M + half + gap, y: 1.5, w: half, h: 3.6, big: '0', head: '违反前提的执行', color: C.green,
    pale: C.paleGreen, body: '并发写入下 11,297 次查询；对照：校验与执行不在同一快照 3.8–4.6%' });
}
footnote(s, '实验记录（来源见备注）。');
notes(s, '第二组结果是正确性。左边：在不使用大模型、固定已学指标定义、只更换维护方式的受控实验中，凡是前提能检测到的写入，MAVRA 没有一个错误结果；仅按表结构变更失效的做法有 629 个错误结果。'
  + '右边：并发写入下 11,297 次查询，没有一次基于违反前提的数据返回结果——因为校验和执行在同一个快照上。如果校验与执行不在同一快照，这一比例是 3.8–4.6%。'
  + '注意限定条件：“前提能检测到的写入”。金额单位由元改为分这类写入，前提检测不到，下一页说明。',
  'exp/2026-10-02-cache-baseline-tpcds 与快照压力测试（论文宏 \\Rp*、\\Sn*）。');

// 16 Limits --------------------------------------------------------------------------------------------------
pres.addSection({ title: '总结' });
s = content('边界：能做到与做不到', '总结');
{
  const gap = 0.5, half = (W - 2 * M - gap) / 2;
  card(s, { x: M, y: 1.5, w: half, h: 3.4, head: '能做到', color: C.green, pale: C.paleGreen, size: 22, body: [
    para('历史行 + 当前标记：自动修复'),
    para('整批重复加载：置为失效并通知'),
    { text: '主表与备份并存：交由人工确认' },
  ] });
  card(s, { x: M + half + gap, y: 1.5, w: half, h: 3.4, head: '做不到', color: C.red, pale: C.grey, size: 22, body: [
    para('数值错、行数与主键不变（元 → 分）'),
    para('判断业务口径本身是否正确'),
    { text: '未声明指标版本的 SQL' },
  ] });
}
notes(s, '边界需要说明清楚。能做到的：保留历史行且有唯一当前标记时（例如数据更正），检测并自动修复为新版本；整批重复加载，能检测但无法修复，置为失效并通知；主表和备份同时存在、无法判断哪份是业务事实时，不自动选择，交由人工确认。'
  + '做不到的：数值本身错误而结构没有变化，行数和主键都不变，前提条件无法检测——例如上游改为按分记账，所有方法都出错；又如时区换算把 10 月 1 日凌晨的销售记到 9 月 30 日，每个日期键都存在且唯一，只是日期错了，数据库中没有依据，需要与源系统对账才能发现。'
  + 'MAVRA 也不判断业务口径是否正确，例如是否含税，这需要业务方确认；它保障的是在 run_sql 中声明了指标版本的查询，未声明的 SQL 正常执行和审查，但不在保证范围内。');

// 17 Summary -------------------------------------------------------------------------------------------------
s = content('总结', '总结');
{
  const gap = 0.35, cw = (W - 2 * M - 2 * gap) / 3;
  [
    ['问题', 'agent 学到的指标定义被共享后，会因日常写入静默失效', C.red, C.paleAmber],
    ['方法', '为定义推导前提；发布、使用时校验；写入后修复或失效', C.blue, C.paleBlue],
    ['结果', '新问题 49% → 100%；破坏性写入后 73%；0 次静默错误', C.violet, C.paleViolet],
  ].forEach(([head, body, color, pale], k) => {
    card(s, { x: M + k * (cw + gap), y: 1.5, w: cw, h: 3.6, head, body, color, pale, size: 22, headSize: 28 });
  });
}
notes(s, '三句话总结。问题：agent 学到的指标定义被共享后，可能因日常数据写入而静默失效，SQL 不报错，结果却是错的。'
  + '方法：共享记忆层，为每个指标定义自动推导前提条件，在发布、使用、维护与优化三个环节把关——发布前校验；执行前在查询快照上校验；数据变化后统一校验，能修复则发布新版本，不能修复则置为失效，并发布更快的等价 SQL。'
  + '结果：共享使新问题准确率从 49% 提升到 100%、提速 2.5–8.9 倍；破坏性写入后 MAVRA 准确率 73%，检索历史示例 57%；前提可检测的写入下没有错误结果，并发下没有一次违反前提的执行。');

fs.mkdirSync(path.dirname(OUT), { recursive: true });
pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
