// Builds docs/mavra-system.pptx, an 8-slide Chinese deck for listeners new to the field. It says what the work is
// before how it works: title; what we do (agents re-derive business meaning, sharing learned definitions makes them
// fast and consistent, the data keeps changing; how this differs from Text-to-SQL); the difficulty (a shared
// definition silently goes wrong after an everyday write: a toy ledger, then the recorded three writes); then the
// method from three views, one figure each: architecture (where MAVRA sits, its three responsibilities), data model
// (a definition carries preconditions derived from its SQL, which tell harmful writes from harmless ones), lifecycle
// (what happens to a definition as the data changes, as a state diagram); results; summary and limits.
// The figures come from tools/deck/figures/ (drawn by `python3 tools/figures/build.py --deck` on noctis, rendered to
// PNG). Each figure states the mechanism in general terms and marks the running example (门店营业额) with a teal 例.
// The toy ledger is marked 示意; every other number comes from the archived run records or the paper's generated
// macros (overleaf/gen/*.tex); record paths go at the end of each slide's speaker notes. Wording uses the terms
// common in the database and data-warehouse industry (SQL, 前提条件, 版本, 校验, 主键唯一, 参照完整性, 拉链表 …),
// in written, declarative sentences.
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
const C = {
  ink: '1F2A37', muted: '5B6573', navy: '17233B', ice: 'CADCFC', white: 'FFFFFF', grey: 'F1F3F6',
  line: 'D5DBE3', blue: '1D5BA6', paleBlue: 'E8F0FA', amber: 'B5671A', paleAmber: 'FBF0E2',
  violet: '6A58A3', paleViolet: 'EFECF7', red: 'B5392A', green: '2E7D4F', paleGreen: 'E6F2EA', teal: '2F7A70',
};
const W = 13.333, M = 0.6;
const DATA = '数据为仿 TPC-DS 的合成零售数据（store_sales 100 万行），题目中的年份略去。';
const RECORDED = '实验记录（来源见备注）。' + DATA;
const FIGURE_NOTE = '按图中编号顺序阅读；绿色“例”为贯穿全文的示例，取自实验记录（来源见备注）；数据为仿 TPC-DS 的合成零售数据。';
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

function footnote(slide, value) {
  text(slide, value, { x: M, y: 6.85, w: W - 2 * M - 0.8, h: 0.4, fontSize: 11, color: C.muted, valign: 'bottom' });
}

// Speaker notes, with the record paths behind the slide's numbers at the end.
function notes(slide, body, source) {
  slide.addNotes(source ? `${body}\n\n来源：${source}` : body);
}

// A tinted rounded band holding text runs.
function band(slide, runs, { x = M, y, w = W - 2 * M, h, fill = C.grey, size = 15, valign = 'middle' }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08 });
  text(slide, runs, { x: x + 0.3, y: y + 0.08, w: w - 0.6, h: h - 0.16, fontSize: size, valign, paraSpaceAfter: 4 });
}

// A plain table: header row in grey, body in white.
function table(slide, rows, { x, y, w, colW, size = 14, rowH, pad = 0.06 }) {
  const head = rows[0].map((t) => (typeof t === 'string'
    ? { text: t, options: { bold: true, fill: { color: C.grey } } }
    : { text: t.text, options: { ...t.options, bold: true, fill: { color: C.grey } } }));
  const body = rows.slice(1).map((r) => r.map((c) => (typeof c === 'string' ? { text: c } : c)));
  slide.addTable([head, ...body], { x, y, w, colW, rowH, fontFace: FONT, fontSize: size, color: C.ink,
    valign: 'middle', border: { type: 'solid', pt: 1, color: C.line }, margin: [pad, 0.1, pad, 0.1] });
}
const good = (t) => ({ text: t, options: { color: C.green, bold: true } });
const bad = (t) => ({ text: t, options: { color: C.red, bold: true } });
const strong = (t, color) => ({ text: t, options: { color, bold: true } });
const para = (t, options = {}) => ({ text: t, options: { breakLine: true, ...options } });

function heading(slide, value, x, y, w, color = C.blue) {
  text(slide, value, { x, y, w, h: 0.35, fontSize: 15, bold: true, color, valign: 'middle' });
}

// A tinted card: a bold heading, then body runs.
function card(slide, { x, y, w, h, head, body, color, pale, size = 15 }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1,
    objectName: `card ${head}` });
  text(slide, head, { x: x + 0.3, y: y + 0.18, w: w - 0.6, h: 0.45, fontSize: 18, bold: true, color, valign: 'middle' });
  text(slide, body, { x: x + 0.3, y: y + 0.72, w: w - 0.6, h: h - 0.85, fontSize: size, valign: 'top',
    paraSpaceAfter: 5 });
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
  + '汇报顺序：我们在做什么 → 难点 → 从三个视角介绍方法（系统架构、数据模型、生命周期），各一张图 → 实验结果 → 总结与边界，共 8 页。');

// 2 What we do -----------------------------------------------------------------------------------------
pres.addSection({ title: '问题' });
s = content('我们在做什么：把 agent 学到的指标口径变成可靠的共享记忆', '问题');
text(s, [
  { text: '数据 agent：', options: { bold: true, color: C.blue } },
  { text: '基于大模型，接到“9 月门店营业额是多少”这类业务问题后，自主查看表结构、编写 SQL 并给出结果。'
    + '难点在指标口径：用哪一列金额、按哪个日期归属月份，这些信息不在表结构里。' },
], { x: M, y: 1.1, w: W - 2 * M, h: 0.62, fontSize: 15, valign: 'middle' });
{
  const half = (W - 2 * M - 0.4) / 2;
  card(s, { x: M, y: 1.9, w: half, h: 2.3, head: '无共享：每个 agent 各自摸索口径', color: C.muted, pale: C.grey, body: [
    para('同一问题独立求解三次：'),
    para('两次选用折扣前销售额：1413.8 万 ✗', { color: C.red }),
    para('一次选用实付金额：1307.0 万 ✓'),
    { text: '未参与学习的新问题，准确率 49%' },
  ] });
  card(s, { x: M + half + 0.4, y: 1.9, w: half, h: 2.3, head: '共享指标定义：一次学习，多 agent 复用', color: C.blue,
    pale: C.paleBlue, body: [
      para('三次均命中同一指标定义：1307.0 万 ✓'),
      para('交互轮数从 5 轮降至 3 轮'),
      para('未参与学习的新问题，准确率 49% → 100%'),
      { text: '单题耗时 75.6 秒 → 8.5 秒，提速 8.9 倍' },
    ] });
}
band(s, [
  para('难点：数据持续写入。', { bold: true, color: C.red }),
  para('数据变化可能使共享的指标定义静默失效（SQL 不报错，结果出错）；一处失效，所有引用它的 agent 同时出错。'),
  { text: 'MAVRA：', options: { bold: true, color: C.blue } },
  { text: '位于 agent 与数据库之间的共享记忆层——只发布通过校验的指标定义；查询执行前校验其前提在当前数据上仍然成立；数据变化后统一维护与优化。' },
], { y: 4.4, h: 1.45, fill: C.paleAmber, size: 15 });
text(s, [
  { text: '与 Text-to-SQL 的区别：', options: { bold: true, color: C.blue } },
  { text: 'Text-to-SQL 将单个问题转换为一条 SQL，不保留状态；MAVRA 不生成 SQL，而是管理 agent 学到、需要反复复用的指标定义，可与任意 Text-to-SQL 模型或 agent 配合使用。' },
], { x: M, y: 6.0, w: W - 2 * M, h: 0.7, fontSize: 13, valign: 'top' });
footnote(s, RECORDED);
notes(s, '先交代场景。数据 agent 基于大模型，接到业务问题后自主查看表结构、编写 SQL 并给出结果。它的难点不在 SQL 语法，而在指标口径：营业额用哪一列金额、按哪个日期归属月份，这些信息不在表结构里。'
  + '左侧是实验记录：只给出“门店营业额”这个名称，没有共享定义的 agent 独立求解三次，两次选用了折扣前销售额（ss_ext_sales_price），结果错误；一次选用了实付金额（ss_net_paid），结果正确。每次重新摸索，结果就不稳定；45 道未参与学习的新问题，准确率只有 49%。'
  + '右侧：把一个 agent 学到的指标定义共享出去，三次均命中同一定义，结果正确，交互只需 3 轮；新问题准确率 100%，单题耗时从 75.6 秒降到 8.5 秒，提速 8.9 倍，token 减少 39%。这是共享本身带来的提升。'
  + '这里的“指标定义”指 agent 学到的计算规则，例如：门店营业额 = 门店销售实付金额之和，按销售日期归属月份。'
  + '共享也带来新的问题：数据持续写入，指标定义可能静默失效——下一页给出例子。MAVRA 就是为解决这个问题设计的共享记忆层。'
  + '与 Text-to-SQL 的区别：Text-to-SQL 研究如何把一个问题转换成一条 SQL，不保留状态；MAVRA 不生成 SQL，它保存 agent 学到的指标定义，并保证这些定义在数据变化后仍然正确。'
  + '它也不同于指标平台（由人工声明指标，运行时不校验声明中的关联关系）和数据质量规则（按表校验人工编写的规则，不知道哪个指标依赖哪条规则）：MAVRA 的前提条件由系统从 SQL 推导，因此清楚每个指标依赖哪些前提。',
  'noctis results/scen-20261002，未参与学习的问题 M1-P1（9 月门店营业额）；无共享：dsv41flash-r1-a、r2-b、r3-a；MAVRA：dsv41flash-r1–r3-g3fix--snap；'
  + '49% → 100% 与 5 轮 → 3 轮：论文宏 \\Ds*；75.6 → 8.5 秒、token 减少 39%：tools/sharing-stats.py（\\AmHold*）。');

// 3 The difficulty: a toy ledger, then the recorded three writes -----------------------------------------
s = content('难点：数据变化会使指标定义静默失效，SQL 不报错', '问题');
{
  const colL = 5.9, colR = W - 2 * M - colL - 0.35, xR = M + colL + 0.35;
  heading(s, '示意 · 第一天：指标“营业额 = 金额之和”', M, 1.1, colL);
  table(s, [
    ['订单号', '金额', '状态'],
    ['001', '100 元', '当前'],
    ['002', '200 元', '当前'],
    ['003', '300 元', '当前'],
  ], { x: M, y: 1.48, w: colL, colW: [1.5, 1.6, 2.8], size: 12, rowH: 0.28, pad: 0.02 });
  text(s, [{ text: '按指标定义计算：600 元 ✓', options: { bold: true, color: C.green } }],
    { x: M, y: 2.72, w: colL, h: 0.35, fontSize: 15, valign: 'middle' });
  heading(s, '第二天：订单 002 更正为 250 元，旧行保留', xR, 1.1, colR);
  table(s, [
    ['订单号', '金额', '状态'],
    ['001', '100 元', '当前'],
    ['002', '200 元', { text: '历史', options: { color: C.muted } }],
    ['002', '250 元', '当前'],
    ['003', '300 元', '当前'],
  ], { x: xR, y: 1.48, w: colR, colW: [1.5, 1.6, colR - 3.1], size: 12, rowH: 0.28, pad: 0.02 });
  text(s, [{ text: '沿用原定义：850 元 ✗（应为 650 元）', options: { bold: true, color: C.red } }],
    { x: xR, y: 2.92, w: colR, h: 0.35, fontSize: 15, valign: 'middle' });
}
heading(s, '实验记录：查询 9 月门店营业额；三种写入均基于同一份初始数据，始终沿用学到的指标定义', M, 3.5, W - 2 * M);
table(s, [
  ['写入类型', '数据变化', '正确结果', '沿用原定义的结果'],
  ['增量加载', '追加一批 9 月新销售（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '旧行保留并标记为非当前，插入更正后的行，+65,915 行', '1293.3 万', bad('1430.1 万 ✗')],
  ['重复加载', '4 个月的销售批次被重复加载，+110,165 行', '1307.0 万', bad('2613.9 万 ✗')],
], { x: M, y: 3.88, w: W - 2 * M, colW: [1.5, 6.4, 1.8, 2.433], size: 13 });
band(s, [
  { text: 'SQL 本身没有错，出错的是它隐含的数据假设：', options: { bold: true, color: C.blue } },
  para('“每笔销售只有一行”。三种写入都不改变表结构，SQL 正常执行；增量加载与重复加载的结果完全相同，却一对一错。'),
  { text: '结论：', options: { bold: true, color: C.blue } },
  { text: '只共享 SQL 不够，还要把隐含假设显式化为可执行的前提条件，随指标定义一起保存，并在使用前校验。' },
], { y: 5.6, h: 1.1, fill: C.paleAmber, size: 14 });
footnote(s, '上半为示意，下半为实验记录（来源见备注）。' + DATA);
notes(s, '先看一个示意的小账本。第一天有三笔订单，指标“营业额 = 金额之和”算出 600 元，结果正确。'
  + '第二天订单 002 更正为 250 元。数据仓库的常见做法是保留旧行、标记为历史，再插入一行当前记录。沿用原定义会把 200 和 250 都计入，得到 850 元，正确结果是 650 元。'
  + 'SQL 本身没有错，是它隐含的假设“每个订单只有一行”不再成立。'
  + '下半部分是实验中的真实记录，查询的都是 9 月门店营业额，三种写入各自从原始数据开始。增量加载追加了一批 9 月新销售，小票号都是新的，9 月销售额确实翻倍，沿用原定义结果正确；数据更正后，沿用原定义多算了 137 万；重复加载把同一批数据又加载了一次，9 月同样翻倍，但这次是错的。'
  + '同样是 2613.9 万，一对一错，区别只在于同一笔销售是否出现了两次，也就是主键是否重复。'
  + '三种写入都是日常的 ETL 操作，表结构没有变化，SQL 不报错，agent 会给出错误结果且毫无察觉；而指标定义是共享的，一处失效，所有引用它的 agent 同时出错。因此只保存 SQL 不够，还要把前提显式保存下来、在使用前校验，这是 MAVRA 的出发点。',
  'noctis results/scen-20261002，dsv41flash-r1–r3-g3fix--schema（仅在表结构变更时失效，3 次运行结果相同）；增量加载 = 复制 9 月门店销售行并更换小票号（src/scenario.rs Change::Append）；数据更正 = Change::Revision。');

// 4 View one: architecture ---------------------------------------------------------------------------------
pres.addSection({ title: '方法' });
s = content('视角一 · 系统架构：MAVRA 的位置与三项职责', '方法');
{
  const { y, h } = figure(s, 'structure', 1.1, 4.95);
  band(s, [
    { text: '一次学习，多次复用：', options: { bold: true, color: C.blue } },
    { text: '发布决定哪些定义可以进入共享记忆；使用决定一次查询能否引用某个版本；维护与优化在数据变化后统一处理，结果由所有使用方共享。' },
  ], { y: y + h + 0.12, h: 0.55, fill: C.paleBlue, size: 14 });
}
footnote(s, FIGURE_NOTE);
notes(s, '下面从三个视角介绍方法。第一个视角是系统架构：MAVRA 处在什么位置，承担哪些职责。图中按编号阅读：1–2 是发布（紫色），3–6 是使用（蓝色），7–9 是数据写入后的维护与优化（黑色）。'
  + '上方是两类 agent：左侧的内置 agent 基于大模型，负责学习；右侧的用户 agent 可以有很多个，负责提问、编写 SQL、复用指标定义。一次学习，多次复用。'
  + '中间是共享记忆：每个指标定义保存口径、SQL、前提条件和版本号（下一页展开），此外按（前提，表版本）缓存校验结果，跨指标、跨 agent 复用。'
  + '第 1 步，内置 agent 完成学习任务，提交候选定义。第 2 步，发布前校验：结果经确认正确（实验中用参考答案判定，生产环境由指标负责人确认一次），并且按定义重新生成的 SQL 能在学习时的数据上复现相同结果，通过后连同前提条件一起入库。例：门店营业额 v1，3 月 1357.0 万。'
  + '第 3 步，用户 agent 取指标定义，再提交 SQL 并声明所用的指标版本（run_sql 的 metrics 参数）。第 4 步，执行前校验读取该版本的前提条件和已缓存的校验结果。第 5 步，在本次查询的快照上校验前提，通过后在同一快照上执行，校验与执行之间其他事务提交的写入对本次查询不可见。第 6 步，返回有效版本和查询结果。例：增量加载后声明 v2，9 月 2613.9 万，结果正确。'
  + '第 7 步，ETL 照常写入，MAVRA 不拦截写入；每次写入在同一事务内递增表版本号。第 8 步，下次使用时 MAVRA 比较表版本，只对受影响的前提执行校验查询。第 9 步，把结果写回共享记忆：通过则继续使用；不通过则自动修复并发布新版本，无法修复则置为失效。此外，发现结果等价且执行更快的 SQL 时，校验后也发布为新版本。例：数据更正后修复得到 v3；日期键范围过滤的写法快 19.8%，成为 v2。'
  + '发布前校验、执行前校验和自动修复都是 MAVRA 在数据库上执行的 SQL，不依赖大模型判断。',
  '学习与 3 月 1357.0 万：' + TRACE_RUN + '；v2 计时与增量加载后的 9 月结果：' + OPT_RUN + '。');

// 5 View two: the data model -------------------------------------------------------------------------------
s = content('视角二 · 数据模型：每个指标定义都附带前提条件', '方法');
{
  const { y, h } = figure(s, 'definition', 1.1, 4.95);
  band(s, [
    { text: '前提条件由系统从 SQL 推导，而非人工编写：', options: { bold: true, color: C.blue } },
    { text: 'SQL 依赖哪些数据假设，就校验哪些假设。SQL 都不报错时，只有前提条件能识别出导致结果出错的写入。' },
  ], { y: y + h + 0.12, h: 0.55, fill: C.paleBlue, size: 14 });
}
footnote(s, FIGURE_NOTE);
notes(s, '第二个视角是数据模型：共享记忆里保存的到底是什么。一个指标定义 = 口径 + SQL + 前提条件 + 版本号。图中按编号阅读：上半部分 1–3 从左到右，下半部分 4–7 从上到下。'
  + '上半部分（1 SQL 结构 → 2 隐含的数据假设 → 3 前提条件）说明前提条件从哪里来：由系统根据 SQL 的结构自动推导。对事实表求和，隐含“一行对应一笔销售明细”的粒度假设，对应的前提是主键唯一，即行数等于不同主键（小票号，商品）的数量；'
  + '关联日期维表并按月过滤，隐含 N:1 的关联基数，对应维表主键唯一，否则关联会使行数膨胀；内连接会丢弃关联不上的行，因此要求关联不上的行不超过学习时的比例（容差 0.1 个百分点），即参照完整性。'
  + '论文中把前提分为四类：粒度、关联基数、日期角色、参照完整性；门店营业额只关联日期维表，关联基数和日期角色都归结为“维表主键唯一”，所以 v1 有 3 个前提。v2 把期间过滤改写为日期键范围，这种写法还要求每月的日期键连续，因此新增第 4 个前提“日期键连续”。'
  + '每个前提对应一条校验 SQL，发布时连同学习时的基准值一起保存，之后由 MAVRA 在数据库上执行。'
  + '下半部分说明为什么需要前提条件。第 4 行是上一页的三种写入，都基于同一份初始数据。先看第 6 行：SQL 都不报错，增量加载和重复加载的结果都是 2613.9 万，一对一错；数据更正后多算了 137 万。'
  + '再看第 5 行，前提条件能把它们区分开：增量加载新增的都是新小票号，主键唯一校验通过，可以继续使用；数据更正后 1,065,915 行只有 1,000,000 个不同主键，重复加载后 1,110,165 行只有 1,000,000 个，主键唯一校验不通过，不能直接使用。其余 3 个前提在三种情况下都通过；日期维表没有写入，其上的两个前提无需重新校验。第 7 行是结论。'
  + '校验不通过之后如何处理，是下一页的内容。前提条件也有覆盖不到的情况，例如金额单位由元改为分，行数和主键都不变，最后一页会说明。',
  '前提校验结果：' + OPT_RUN + ' 的 maintenance 事件（append、revision、dupload 三个阶段：粒度校验 1,065,915 行 / 1,000,000 个主键与 1,110,165 / 1,000,000，参照完整性校验通过，date_dim 无写入、两个前提跳过）；'
  + '沿用原定义的结果与正确结果：noctis results/scen-20261002 dsv41flash-r1-g3fix--schema；前提的四类划分与命题 1：论文 §4。');

// 6 View three: the lifecycle -------------------------------------------------------------------------------
s = content('视角三 · 生命周期：校验、修复、优化与失效', '方法');
{
  const { y, h } = figure(s, 'process', 1.1, 4.95);
  band(s, [
    { text: '不静默返回错误结果：', options: { bold: true, color: C.blue } },
    { text: '校验延迟到下次使用，且只校验受写入影响的前提；修复只接受唯一的过滤条件，并经回归测试；无法修复则置为失效并通知使用方。' },
  ], { y: y + h + 0.12, h: 0.55, fill: C.paleBlue, size: 14 });
}
footnote(s, FIGURE_NOTE);
notes(s, '第三个视角是生命周期：一个指标定义随着数据变化会经历哪些状态。图中按编号 1–10 阅读：先沿中间一行从左到右，再看上方的优化，最后沿下方一行从右到左。颜色与第一张图的三项职责对应：紫色是发布，蓝色是使用，黑色是维护与优化，红色虚线是指标失效。'
  + '第 1 步学习：内置 agent 完成学习任务、提取指标定义。第 2 步发布前校验：通过后入库，同时保存前提条件和证据。例：3 月门店营业额 1357.0 万，结果正确，发布 v1，带 3 个前提。'
  + '第 3 步“有效”是指标定义的正常状态：使用方声明指标版本后直接使用。'
  + '第 4 步优化：MAVRA 为已发布的定义寻找更快的 SQL，只有在各期间结果一致、并且在同一快照内配对测量确实更快时，才发布为新版本，新 SQL 依赖的假设也加入前提条件。例：期间过滤改写为日期键范围，14 个期间结果一致，29.1 → 23.3 毫秒，快 19.8%，成为 v2，新增前提“日期键连续”。'
  + '第 5 步待校验：指标定义依赖的表一旦发生写入，就进入待校验状态——这个状态并不持久化，而是在使用时比较表版本得出的；写入发生时不做任何处理。'
  + '第 6 步执行前校验：下次使用时，在本次查询的快照上只校验受影响的前提，校验结果按表版本缓存、跨指标复用。校验通过，回到第 3 步继续使用。例：增量加载后，9 月 2613.9 万，结果正确。'
  + '校验不通过，进入下方一行。第 7 步自动修复：在取值较少的列上寻找“列 = 值”形式的过滤条件，要求能恢复前提且不丢失主键，并且可行的过滤条件必须唯一。第 8 步回归测试：在学习时的数据上重算，结果必须与学习时一致。第 9 步发布新版本，回到第 3 步；引用旧版本的查询会被拒绝。'
  + '例：数据更正后主键重复，只有 ss_is_current = \'1\' 可行，3 月重算仍为 1357.0 万，发布 v3，9 月 1293.3 万，结果正确；若不维护、沿用 v2，结果为 1430.1 万。'
  + '第 10 步：如果找不到可行的过滤条件，或者可行的不止一个（例如同时存在主表和备份），MAVRA 不自动选择，而是将指标置为失效并通知使用方：引用它的查询被拒绝，由使用方自行处理，等待重新学习（回到第 1 步）。例：重复加载后，没有过滤条件能消除主键重复。'
  + '图中未画出的一种情况：写入只破坏了优化时新增的前提（例如某个月的日期键被重新编号、不再连续），而 v1 的前提都成立，此时只撤下 v2、恢复 v1；实验中 4 个指标定义这样回退，之后 20 个查询结果全部正确。',
  '学习：' + TRACE_RUN + '；优化计时、三种写入的 maintenance / revoked / repair_* 事件与 9 月结果：' + OPT_RUN
  + '；沿用 v2 的 1430.1 万：results/scen-20261002 dsv41flash-r1-g3fix--schema；恢复 v1：论文 §7.8（gen/premise.tex）。');

// 7 Results -------------------------------------------------------------------------------------------------
pres.addSection({ title: '结果' });
s = content('实验结果：共享提升效率与准确率，数据变化后 MAVRA 准确率最高', '结果');
{
  const gap = 0.3, cw = (W - 2 * M - 2 * gap) / 3;
  [
    { big: '8.9 倍', head: '共享', color: C.blue, pale: C.paleBlue,
      body: '未参与学习的新问题，单题耗时 75.6 秒 → 8.5 秒；准确率 49% → 100%' },
    { big: '73%', head: '维护', color: C.green, pale: C.paleGreen,
      body: '5 类破坏性写入后的准确率；检索历史示例 57%，无共享 19%' },
    { big: '0', head: '正确性', color: C.violet, pale: C.paleViolet,
      body: '前提可检测的写入下错误结果为 0（仅按表结构变更失效：629 个）；并发写入下 0 次基于违反前提的数据返回结果' },
  ].forEach(({ big, head, color, pale, body }, k) => {
    const x = M + k * (cw + gap);
    s.addShape('roundRect', { x, y: 1.1, w: cw, h: 1.8, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1,
      objectName: `stat ${head}` });
    text(s, head, { x: x + 0.25, y: 1.17, w: 1.2, h: 0.4, fontSize: 14, bold: true, color: C.muted, valign: 'middle' });
    text(s, big, { x: x + 0.25, y: 1.5, w: cw - 0.5, h: 0.6, fontSize: 32, bold: true, color, valign: 'middle' });
    text(s, body, { x: x + 0.25, y: 2.12, w: cw - 0.5, h: 0.72, fontSize: 12, valign: 'top' });
  });
}
heading(s, '端到端准确率：DeepSeek V4.1 Flash agent，每种方法独立运行 3 次', M, 3.02, W - 2 * M);
table(s, [
  ['方法', '机制', '数据不变', '11 类写入后', '破坏性写入后'],
  ['无共享', '每次从零探索', '49%', '32%', '19%'],
  ['检索历史示例', '保存成功的问答与 SQL，按相似度检索，不做校验', '100%', '76%', '57%'],
  ['检索示例 + 自行校验', '同上，并提示 agent 自行校验数据', '100%', '77%', '63%'],
  ['按表结构变更失效', '共享定义，仅在表结构变更时失效', '100%', '75%', '59%'],
  [strong('MAVRA', C.blue), '共享定义 + 前提校验、自动修复与失效', good('100%'), good('81%'), good('73%')],
], { x: M, y: 3.38, w: W - 2 * M, colW: [2.5, 5.133, 1.4, 1.5, 1.6], size: 13, rowH: 0.34 });
band(s, [
  { text: '局限：', options: { bold: true, color: C.red } },
  { text: '重复加载、日期键格式变更可检测，但无法自动修复（指标失效后由 agent 自行探索，准确率 59%、15%）；金额单位由元改为分时，行数与主键不变，前提条件无法检测，所有方法均出错。' },
], { y: 5.85, h: 0.9, size: 13 });
footnote(s, '11 类写入 = 4 类常规写入 + 5 类破坏性写入（退货状态流水、更正保留旧行、重复加载、商品维表拉链表、日期键格式变更）+ 备份副本 + 金额单位变化。');
notes(s, '上方三个数字分别对应三点。共享：未参与学习的新问题，单题耗时从 75.6 秒降到 8.5 秒，提速 8.9 倍，准确率从 49% 提升到 100%；这是共享本身带来的提升，任何共享方法都具备。'
  + '维护：差别出现在数据变化之后。5 类破坏性写入下，MAVRA 准确率 73%，检索历史示例 57%，提示 agent 自行校验数据也只有 63%，仅按表结构变更失效 59%。'
  + '正确性：在不使用大模型、固定已学指标定义、只更换维护方式的受控实验中，前提可检测的写入下 MAVRA 没有错误结果，仅按表结构变更失效的做法有 629 个错误结果；并发写入下 11,297 次查询，没有一次基于违反前提的数据返回结果，而校验与执行不在同一快照时，这一比例为 3.8–4.6%。'
  + '表中列出了每种方法的机制。“检索历史示例”是 agent 记忆中常见的做法：保存成功的问答，按相似度检索作为参考，但不校验数据是否变化。'
  + 'MAVRA 还有一个消融版本“每次全量重新校验”（校验与修复相同，去掉按表版本复用），准确率为 82% / 74%，与 MAVRA 相当，说明准确率来自校验与修复本身；按表版本复用只节省时间，论文不把效率作为贡献。'
  + '73% 不是 100%：剩余错误集中在两类写入——重复加载和日期键格式变更都能检测到，但没有过滤条件能修复，指标失效后由 agent 自行重新探索，准确率分别为 59% 和 15%；其余三类破坏性写入都能自动修复，准确率 93%–100%。'
  + '金额单位变化（上游改为按分记账，数值乘以 100）所有方法都无法发现，作为对照未列入表中；该场景下各共享方法均为 48%，答对的是本身不受影响的问题。',
  'exp/2026-10-02-scenarios-ds（scen-stats.json：MAVRA = metric-global-snap，消融 = metric-global-def，各类写入的准确率在 per_change；论文宏 \\Ds*）、'
  + 'exp/2026-10-02-cache-baseline-tpcds 与快照压力测试（\\Rp*、\\Sn*）、tools/sharing-stats.py（\\AmHold*）。');

// 8 Summary and limits ----------------------------------------------------------------------------------------
pres.addSection({ title: '总结' });
s = content('总结：能力与边界', '总结');
{
  const gap = 0.3, cw = (W - 2 * M - 2 * gap) / 3;
  [
    ['问题', 'agent 学到的指标定义被共享后，可能因日常数据写入而静默失效，SQL 不报错，结果却是错的。', C.red, C.paleAmber],
    ['方法', '共享记忆层，为每个指标定义自动推导前提条件：发布前校验；执行前在查询快照上校验；数据变化后统一校验、修复或失效，并发布更快的等价 SQL。', C.blue, C.paleBlue],
    ['结果', '共享使新问题提速 8.9 倍、准确率 49% → 100%；破坏性写入后准确率 73%（检索示例 57%）；前提可检测的写入下 0 错误，并发下 0 次违规执行。', C.violet, C.paleViolet],
  ].forEach(([head, body, color, pale], k) => {
    card(s, { x: M + k * (cw + gap), y: 1.15, w: cw, h: 2.75, head, body, color, pale, size: 16 });
  });
  const half = (W - 2 * M - 0.4) / 2;
  card(s, { x: M, y: 4.15, w: half, h: 2.5, head: '能做到', color: C.green, pale: C.paleGreen, size: 15, body: [
    para('保留历史行且有唯一当前标记：检测并自动修复为新版本'),
    para('整批重复加载：可检测，无法修复时置为失效并通知'),
    { text: '主表与备份并存：有歧义，不自动选择，交由人工确认' },
  ] });
  card(s, { x: M + half + 0.4, y: 4.15, w: half, h: 2.5, head: '做不到', color: C.red, pale: C.grey, size: 15, body: [
    para('数值错误但行数与主键不变（如金额单位由元改为分）'),
    para('判断业务口径是否正确（如是否含税，需业务方确认）'),
    { text: '未声明指标版本的 SQL：正常执行，但不在保证范围内' },
  ] });
}
notes(s, '三句话总结。问题：agent 学到的指标定义被共享后，可能因日常数据写入而静默失效，SQL 不报错；方法：共享记忆层，为指标定义自动推导前提条件，在发布、使用、维护与优化三个环节把关；结果：共享提升了效率和准确率，数据变化后 MAVRA 准确率最高，前提可检测的写入下没有错误结果。'
  + '边界需要说明清楚。能做到的：保留历史行且有唯一当前标记时，检测并自动修复；整批重复加载，能检测但无法修复，置为失效并通知；主表和备份同时存在、无法判断哪份是业务事实时，不自动选择，交由人工确认。'
  + '做不到的：数值本身错误而结构没有变化，行数和主键都不变，前提条件无法检测——例如上游改为按分记账；又如时区换算把 10 月 1 日凌晨的销售记到 9 月 30 日，每个日期键都存在且唯一，只是日期错了，数据库中没有依据，需要与源系统对账才能发现。'
  + 'MAVRA 也不判断业务口径是否正确，这需要业务方确认；它保障的是在 run_sql 中声明了指标版本的查询，未声明的 SQL 正常执行和审查，但不在保证范围内。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
