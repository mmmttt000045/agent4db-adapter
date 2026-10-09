// Builds docs/mavra-system.pptx, an 8-slide Chinese deck for listeners new to the field. It says what the work is
// before how it works: title; what we do (agents re-derive business meaning, sharing learned definitions makes them
// fast and consistent, the data keeps changing; how this differs from Text-to-SQL); the difficulty (a shared
// definition silently goes wrong after an everyday write: a toy ledger, then the recorded three writes); then the
// method from three angles, one figure each: structure (where MAVRA sits, its three responsibilities), the object
// (a definition carries conditions derived from its SQL, which tell harmful writes from harmless ones), the process
// (what happens to a definition as the data changes, as a state diagram); results; summary and limits.
// The figures come from tools/deck/figures/ (drawn by `python3 tools/figures/build.py --deck` on noctis, rendered to
// PNG). Each figure states the mechanism in general terms and marks the running example (门店营业额) with a teal 例.
// The toy ledger is marked 示意; every other number comes from the archived run records or the paper's generated
// macros (overleaf/gen/*.tex); record paths go at the end of each slide's speaker notes. Wording uses standard
// database terms, explained once in plain words.
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
const FIGURE_NOTE = '图中绿色“例”是贯穿全场的例子，取自实验记录（来源见备注）；数据为仿 TPC-DS 的合成零售数据。';
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
s.addText('一个 agent 学到的指标定义，所有 agent 都能放心复用——数据变了也一样', { placeholder: 'body' });
text(s, [
  para('MAVRA = Metric-Aware Validation and Reuse for Agents'),
  { text: '组会汇报 · 2026 年 10 月' },
], { x: M, y: 5.4, w: W - 2 * M, h: 0.8, fontSize: 16, color: C.ice, valign: 'top', paraSpaceAfter: 6 });
notes(s, '一句话先讲清楚我在做什么：很多数据 agent 在同一个数据库上回答业务问题。一个 agent 学会了“门店营业额怎么算”，'
  + '我希望别的 agent 直接复用，而不是每次重新摸索；难点在于数据库每天都在写入，学到的定义可能悄悄变错。'
  + 'MAVRA 就是放在 agent 和数据库之间的共享记忆层，负责让共享的定义可靠：只发布经过检查的定义，使用时保证它在所读的数据上仍然成立，数据变了替所有使用者维护和改进。'
  + '顺序：我们在做什么 → 难点 → 从三个角度看方法（结构、对象、过程），各一张图 → 实验结果 → 总结与边界，共 8 页。');

// 2 What we do -----------------------------------------------------------------------------------------
pres.addSection({ title: '问题' });
s = content('我们在做什么：把 agent 学到的口径变成可靠的共享记忆', '问题');
text(s, [
  { text: '数据 agent：', options: { bold: true, color: C.blue } },
  { text: '接到“9 月门店营业额是多少”这样的问题，自己查表、写 SQL、给出答案的大模型程序。'
    + '难的是口径：用哪一列金额、按哪个日期归月——这些不写在表结构里。' },
], { x: M, y: 1.1, w: W - 2 * M, h: 0.62, fontSize: 15, valign: 'middle' });
{
  const half = (W - 2 * M - 0.4) / 2;
  card(s, { x: M, y: 1.9, w: half, h: 2.3, head: '没有共享：每个 agent 自己摸索口径', color: C.muted, pale: C.grey, body: [
    para('同一个问题独立求解三次：'),
    para('两次选了折扣前的销售额：1413.8 万 ✗', { color: C.red }),
    para('一次选了净支付额：1307.0 万 ✓'),
    { text: '没见过的新题，正确率 49%' },
  ] });
  card(s, { x: M + half + 0.4, y: 1.9, w: half, h: 2.3, head: '共享定义：学一次，所有 agent 复用', color: C.blue,
    pale: C.paleBlue, body: [
      para('三次都取到同一条定义：1307.0 万 ✓'),
      para('交互从 5 轮降到 3 轮'),
      para('没见过的新题，正确率 49% → 100%'),
      { text: '每题 75.6 秒 → 8.5 秒，快 8.9 倍' },
    ] });
}
band(s, [
  para('难点：数据库每天都在写入。', { bold: true, color: C.red }),
  para('共享的定义可能悄悄变错，SQL 却照常执行、不报错；定义是共享的，一处错，所有使用它的 agent 一起错。'),
  { text: '我们的工作 MAVRA：', options: { bold: true, color: C.blue } },
  { text: 'agent 与数据库之间的共享记忆层——只发布经过检查的定义；每次使用时保证它在所读的数据上仍然成立；数据变了，替所有使用者维护和改进。' },
], { y: 4.4, h: 1.45, fill: C.paleAmber, size: 15 });
text(s, [
  { text: '和 Text-to-SQL 不在同一层：', options: { bold: true, color: C.blue } },
  { text: 'Text-to-SQL 把一个问题翻译成一条 SQL，处理完什么也不留下；MAVRA 不生成 SQL，管理的是 agent 学到、要被反复使用的定义。任何 Text-to-SQL 模型或 agent 都可以接在 MAVRA 上。' },
], { x: M, y: 6.0, w: W - 2 * M, h: 0.7, fontSize: 13, valign: 'top' });
footnote(s, RECORDED);
notes(s, '先交代场景。数据 agent 是接到业务问题、自己查表写 SQL 给出答案的大模型程序。它最难的不是写 SQL，而是弄清口径：营业额用哪一列、按哪个日期归月——这些不在表结构里。'
  + '左边是实验记录：只给“门店营业额”这个名称，没有共享定义的 agent 三次独立求解，两次选了折扣前的销售额，错；一次选了净支付额，对。每次重新猜，答案就不稳定；45 道没见过的新题，正确率只有 49%。'
  + '右边：把一个 agent 学到的定义共享出去，三次都对，只用 3 轮；新题正确率 100%，每题从 75.6 秒降到 8.5 秒，快 8.9 倍，token 少 39%。这是共享本身带来的提升。'
  + '这里的“定义”就是一条学到的计算规则，比如门店营业额 = 门店销售的净支付额之和，按销售日期归月，后面一直用这个词。'
  + '但共享有代价：数据库每天都在写入，定义可能悄悄变错——下一页就是例子。我们的工作 MAVRA 就是解决这个问题的共享记忆层。'
  + '和 Text-to-SQL 的区别：Text-to-SQL 研究把一个问题翻译成一条 SQL，没有状态；MAVRA 不生成 SQL，它保存 agent 学到的定义，并负责这些定义在数据变化后还对不对。'
  + '它也不同于指标层（人声明定义，声明的连接属性运行时不验证）和数据质量测试（按表检查人写的约束，不知道哪条定义依赖它）：MAVRA 的条件是从定义推出来的，所以知道哪条定义依赖哪个条件。',
  'noctis results/scen-20261002，没见过的题 M1-P1（9 月门店营业额）；没有共享定义：dsv41flash-r1-a、r2-b、r3-a；MAVRA：dsv41flash-r1–r3-g3fix--snap；'
  + '49% → 100% 与 5 轮 → 3 轮：论文宏 \\Ds*；75.6 → 8.5 秒、token 少 39%：tools/sharing-stats.py（\\AmHold*）。');

// 3 The difficulty: a toy ledger, then the recorded three writes -----------------------------------------
s = content('难点：数据在变，共享的定义会悄悄出错，而 SQL 不报错', '问题');
{
  const colL = 5.9, colR = W - 2 * M - colL - 0.35, xR = M + colL + 0.35;
  heading(s, '示意 · 第一天：定义“营业额 = 金额之和”', M, 1.1, colL);
  table(s, [
    ['订单号', '金额', '状态'],
    ['001', '100 元', '当前'],
    ['002', '200 元', '当前'],
    ['003', '300 元', '当前'],
  ], { x: M, y: 1.48, w: colL, colW: [1.5, 1.6, 2.8], size: 12, rowH: 0.28, pad: 0.02 });
  text(s, [{ text: '按定义计算：600 元 ✓', options: { bold: true, color: C.green } }],
    { x: M, y: 2.72, w: colL, h: 0.35, fontSize: 15, valign: 'middle' });
  heading(s, '第二天：订单 002 更正为 250 元，旧行保留', xR, 1.1, colR);
  table(s, [
    ['订单号', '金额', '状态'],
    ['001', '100 元', '当前'],
    ['002', '200 元', { text: '旧记录', options: { color: C.muted } }],
    ['002', '250 元', '当前'],
    ['003', '300 元', '当前'],
  ], { x: xR, y: 1.48, w: colR, colW: [1.5, 1.6, colR - 3.1], size: 12, rowH: 0.28, pad: 0.02 });
  text(s, [{ text: '沿用定义：850 元 ✗（应为 650 元）', options: { bold: true, color: C.red } }],
    { x: xR, y: 2.92, w: colR, h: 0.35, fontSize: 15, valign: 'middle' });
}
heading(s, '实验中的真实记录：问 9 月门店营业额，每种写入都从同一份数据开始，一直沿用学到的定义', M, 3.5, W - 2 * M);
table(s, [
  ['日常写入', '数据库中的变化', '正确答案', '沿用定义的答案'],
  ['增量加载', '追加一批 9 月的新销售（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '旧行保留并标为非当前，插入更正后的行，+65,915 行', '1293.3 万', bad('1430.1 万 ✗')],
  ['重复加载', '4 个月的销售批次被再装一次，+110,165 行', '1307.0 万', bad('2613.9 万 ✗')],
], { x: M, y: 3.88, w: W - 2 * M, colW: [1.5, 6.4, 1.8, 2.433], size: 13 });
band(s, [
  { text: '定义本身没错，错的是它默认的前提：', options: { bold: true, color: C.blue } },
  para('“每笔销售只出现一次”。三种写入都不改表结构，SQL 照常执行；增量加载和重复加载甚至得到同一个数，一对一错。'),
  { text: '所以：', options: { bold: true, color: C.blue } },
  { text: '只共享 SQL 不够，要把它成立的前提写成可以检查的条件，和定义一起保存，用之前检查。' },
], { y: 5.6, h: 1.1, fill: C.paleAmber, size: 14 });
footnote(s, '上半为示意例子，下半为实验记录（来源见备注）。' + DATA);
notes(s, '先用一个示意的小账本。第一天三笔订单，定义“把金额加起来”算出 600 元，正确。'
  + '第二天订单 002 被更正为 250 元，数据仓库常见的做法是旧行不删、标记为非当前，再插入一行新的。沿用定义会把 200 和 250 都加进去，得到 850 元，正确答案是 650 元。'
  + '定义没有算错，是它的前提“每个订单只有一行”不再成立了。'
  + '下半是实验里的真实记录，问的都是 9 月门店营业额，每种写入都从原始数据单独开始。增量加载追加了一批 9 月的新销售，换了新小票号，9 月确实翻倍，沿用定义算对；数据更正后沿用定义多算了 137 万；重复加载把同样的行再装一次，9 月也翻倍，但这次是错的。'
  + '同一个 2613.9 万，一对一错，区别只在同一笔销售有没有出现两次——下一组图里叫“粒度键唯一”。'
  + '三种写入都是日常的数据写入，表结构没变，查询不报错，agent 会非常自信地给出错误答案；而定义是共享的，一处失效所有 agent 一起错。所以只存 SQL 不够，还要把前提记下来、用之前检查——这就是 MAVRA 的出发点。',
  'noctis results/scen-20261002，dsv41flash-r1–r3-g3fix--schema（只在表结构变化时使定义失效，3 次运行答案相同）；增量加载 = 复制 9 月门店销售行并换新小票号（src/scenario.rs Change::Append）；数据更正 = Change::Revision。');

// 4 Angle one: structure ----------------------------------------------------------------------------------
pres.addSection({ title: '方法' });
s = content('角度一 · 结构：MAVRA 在 agent 与数据库之间，承担三项职责', '方法');
{
  const { y, h } = figure(s, 'structure', 1.1, 4.95);
  band(s, [
    { text: '学一次，用很多次：', options: { bold: true, color: C.blue } },
    { text: '发布管“什么能进共享记忆”，依赖管“这次查询能不能用”，维护与改进管“数据变了怎么办”，替所有使用者只做一次。' },
  ], { y: y + h + 0.12, h: 0.55, fill: C.paleBlue, size: 14 });
}
footnote(s, FIGURE_NOTE);
notes(s, '从三个角度看方法，这是第一个：结构，MAVRA 放在哪里、做哪几件事。'
  + '上面是两种 agent：左边的内置 agent 是大模型，负责学习——解题，再从答案里把定义抽取出来；右边的用户 agent 可以有很多个，提问、写 SQL，复用定义。学一次，用很多次。'
  + 'MAVRA 在中间，核心是共享记忆：每条指标定义存的是写法、它成立的条件和修订号（下一页细讲），另外按（条件，表版本）存验证结果，所有定义、所有 agent 共享。'
  + '围绕共享记忆有三项职责。发布：候选定义要通过准入检查——答案经判定正确（实验里用参考答案，部署时由负责这个指标的人确认一次），并且只凭定义重新生成的 SQL 在学习时的数据上算出同一个答案，才连同条件一起写入。例子：门店营业额 v1，3 月 1357.0 万。'
  + '依赖：用户 agent 执行 SQL 时声明自己依据的是哪条定义的哪一版（run_sql 的 metrics 参数）；MAVRA 在这条查询的快照上确认条件成立，再在同一快照上执行，检查和执行之间别人提交的写入看不见。例子：增量加载之后声明 v2，9 月 2613.9 万，与参考答案一致。'
  + '维护与改进：表有写入后，下次使用时重新验证条件；成立就继续用，不成立就修复成新修订，修不好就让定义失效；另外，找到等价且更快的写法，也验证后发布为新修订。例子：数据更正后修复出 v3；日期键范围的写法快 19.8%，成为 v2。'
  + '最下面是数据库：ETL 照常写入，MAVRA 不拦截写入；每次写入在同一事务里把表版本加 1，MAVRA 靠比较表版本知道哪些条件需要重新验证。准入检查、验证、修复都是 MAVRA 在数据库上执行的查询，不由大模型判断。',
  '学习与 3 月 1357.0 万：' + TRACE_RUN + '；v2 计时与增量加载后的 9 月答案：' + OPT_RUN + '。');

// 5 Angle two: the object ---------------------------------------------------------------------------------
s = content('角度二 · 对象：每条定义带着它成立的条件', '方法');
{
  const { y, h } = figure(s, 'definition', 1.1, 4.95);
  band(s, [
    { text: '条件不是人写的规则，而是从写法推出来的：', options: { bold: true, color: C.blue } },
    { text: '写法用到了数据的哪些性质，就检查哪些性质。SQL 都不报错时，只有条件能分辨哪次写入让定义变错。' },
  ], { y: y + h + 0.12, h: 0.55, fill: C.paleBlue, size: 14 });
}
footnote(s, FIGURE_NOTE);
notes(s, '第二个角度：对象，共享记忆里存的到底是什么。一条定义 = 写法（SQL）+ 它成立的条件 + 修订号。'
  + '上半讲条件从哪来。条件是从写法的结构推出来的：在事实表上求和，就要求每笔销售只出现一次——粒度键唯一，也就是行数等于不同的（小票号，商品）数；'
  + '连接日期维度、按月筛选，就要求一个日期键只对应一天——日期键唯一，否则连接会把行放大；内连接会丢掉连不上的行，所以要求连不上日期的行不多于学习时（容差 0.1 个百分点）——日期键完整性。'
  + '论文里是四类：粒度、连接基数、日期角色、完整性；门店营业额只连接日期表，连接基数和日期角色都落到“日期键唯一”上，所以 v1 有 3 个条件。v2 把期间改写成日期键范围，这个写法额外要求每个月的日期键首尾相接，于是多了第 4 个条件“日期键按月连续”。'
  + '每个条件都是一条检查查询，发布时连同学习时的基准值一起记下，之后由 MAVRA 在数据库上执行。'
  + '下半是为什么要这样做：第 3 页的三种写入都从同一份数据开始。SQL 都不报错；增量加载和重复加载算出同一个 2613.9 万，一个对一个错；数据更正多算了 137 万。'
  + '条件把它们分开了：增量加载多出的都是新小票号，粒度键唯一成立，可以继续用；数据更正后 1,065,915 行只有 1,000,000 个键，重复加载后 1,110,165 行只有 1,000,000 个键，粒度键唯一不成立，不能直接用。其余 3 个条件三种情况下都成立，日期表没有被写，它上面的两个条件不用重查。'
  + '不能直接用之后怎么办，是下一页的内容。条件也有它管不到的地方，比如金额单位从元变成分，行数和键都不变，最后一页会讲。',
  '条件结论：' + OPT_RUN + ' 的 maintenance 事件（append、revision、dupload 三个阶段：粒度检查 1,065,915 行 / 1,000,000 键与 1,110,165 / 1,000,000，覆盖检查通过，date_dim 未写入、两项条件跳过）；'
  + '沿用定义的答案与正确答案：noctis results/scen-20261002 dsv41flash-r1-g3fix--schema；条件的四类与命题 1：论文 §4。');

// 6 Angle three: the process ------------------------------------------------------------------------------
s = content('角度三 · 过程：数据变化后，定义被验证、修复、改进或失效', '方法');
{
  const { y, h } = figure(s, 'process', 1.1, 4.95);
  band(s, [
    { text: '不悄悄给错答案：', options: { bold: true, color: C.blue } },
    { text: '验证推迟到下次使用、只查受写入影响的条件；修复只接受唯一的过滤并做回归测试；修不好就失效并通知使用方。' },
  ], { y: y + h + 0.12, h: 0.55, fill: C.paleBlue, size: 14 });
}
footnote(s, FIGURE_NOTE);
notes(s, '第三个角度：过程，一条定义随着数据变化会经历什么。这是一张状态图，颜色对应第一张图的三项职责：紫色是发布，蓝色是依赖，黑色是维护与改进，红色虚线是定义失效。'
  + '左边是发布：内置 agent 解题、抽取定义；准入检查通过后发布，同时记下条件和证据。例子：3 月门店营业额 1357.0 万，判定正确，发布 v1，带 3 个条件。'
  + '中间的“有效”是定义平时的状态：使用方声明修订号后直接使用。上方是改进：MAVRA 为已发布的定义寻找更快的写法，必须在每个期间结果都一致、同一快照里配对计时确实更快，才发布为新修订，新写法依赖的前提也成为新条件。例子：期间改为日期键范围，14 个期间结果一致，29.1 → 23.3 毫秒，快 19.8%，成为 v2，新增条件“日期键按月连续”。'
  + '定义读的表一有写入，它就变成待验证——这不是存下来的状态，是使用时比较表版本得出的；写入那一刻什么也不做，等下次使用时再验证，只查受影响的条件，结果按表版本缓存、跨定义共享。'
  + '条件成立，就继续使用。例子：增量加载之后，9 月 2613.9 万，和参考答案一致。'
  + '条件不成立，进入修复：先做修复搜索，在取值很少的列上找“列 = 值”的过滤谓词，要求恢复条件且不丢键，而且可行的过滤必须唯一；再做回归测试：在学习时那份数据上重算，答案必须和学习时一样；通过后发布新修订，声明旧修订的查询会被拒绝。'
  + '例子：数据更正后粒度键唯一不成立，只有 ss_is_current = \'1\' 可行，3 月重算仍是 1357.0 万，发布 v3，9 月 1293.3 万，答对；不维护、沿用 v2 会得 1430.1 万。'
  + '如果找不到可行的过滤，或者可行的不止一个（比如一份当前数据、一份备份），MAVRA 不擅自选，定义失效，通知使用方：声明它的查询被拒绝，使用方自己探索作答，等待重新学习。例子：重复加载后没有过滤能恢复唯一性。'
  + '图里没画的一种情况：数据只破坏了改进时新增的前提（比如某个月的日期键被重新编号，不再连续），而 v1 的条件都成立，这时只撤下 v2、恢复 v1；实验里 4 条定义这样回退，之后 20 个答案全对。',
  '学习：' + TRACE_RUN + '；改进计时、三种写入的 maintenance / revoked / repair_* 事件与 9 月答案：' + OPT_RUN
  + '；沿用 v2 的 1430.1 万：results/scen-20261002 dsv41flash-r1-g3fix--schema；恢复 v1：论文 §7.8（gen/premise.tex）。');

// 7 Results -------------------------------------------------------------------------------------------------
pres.addSection({ title: '结果' });
s = content('实验结果：共享让 agent 又快又准，数据变化后 MAVRA 答对最多', '结果');
{
  const gap = 0.3, cw = (W - 2 * M - 2 * gap) / 3;
  [
    { big: '8.9 倍', head: '共享', color: C.blue, pale: C.paleBlue,
      body: '没见过的新题每题 75.6 秒 → 8.5 秒；正确率 49% → 100%' },
    { big: '73%', head: '维护', color: C.green, pale: C.paleGreen,
      body: '5 种破坏性写入后的正确率；检索历史示例 57%，不共享 19%' },
    { big: '0', head: '保证', color: C.violet, pale: C.paleViolet,
      body: '条件能发现的写入下 0 错答（只在表结构变化时失效：629 错答）；并发写入下 0 次在违反条件的数据上作答' },
  ].forEach(({ big, head, color, pale, body }, k) => {
    const x = M + k * (cw + gap);
    s.addShape('roundRect', { x, y: 1.1, w: cw, h: 1.8, fill: { color: pale }, line: { color: pale }, rectRadius: 0.1,
      objectName: `stat ${head}` });
    text(s, head, { x: x + 0.25, y: 1.17, w: 1.2, h: 0.4, fontSize: 14, bold: true, color: C.muted, valign: 'middle' });
    text(s, big, { x: x + 0.25, y: 1.5, w: cw - 0.5, h: 0.6, fontSize: 32, bold: true, color, valign: 'middle' });
    text(s, body, { x: x + 0.25, y: 2.12, w: cw - 0.5, h: 0.72, fontSize: 12, valign: 'top' });
  });
}
heading(s, '端到端：DeepSeek V4.1 Flash agent，每种方法独立运行 3 次，答对的比例', M, 3.02, W - 2 * M);
table(s, [
  ['方法', '做法', '数据未变', '11 种写入后', '破坏性写入后'],
  ['没有共享定义', '每次自己从头探索', '49%', '32%', '19%'],
  ['检索历史示例', '存下成功的问答和 SQL，按相似度取回参考，不检查', '100%', '76%', '57%'],
  ['检索示例 + 自行验证', '同上，并提示 agent 自己检查数据', '100%', '77%', '63%'],
  ['按表结构变化失效', '共享定义，只在表结构变化时停用', '100%', '75%', '59%'],
  [strong('MAVRA', C.blue), '共享定义，带条件验证、修复与失效', good('100%'), good('81%'), good('73%')],
], { x: M, y: 3.38, w: W - 2 * M, colW: [2.5, 5.133, 1.4, 1.5, 1.6], size: 13, rowH: 0.34 });
band(s, [
  { text: '还做不到的：', options: { bold: true, color: C.red } },
  { text: '重复加载、日期键格式变更能检测到但修不好（定义失效，agent 自己探索，正确率 59%、15%）；金额单位从元改成分，行数和键都不变，条件发现不了，所有方法同样答错。' },
], { y: 5.85, h: 0.9, size: 13 });
footnote(s, '11 种写入 = 4 种正常写入 + 5 种破坏性写入（退货状态行、保留旧行的更正、重复加载、商品维度保留历史版本、日期键格式变更）+ 备份副本 + 单位变化。');
notes(s, '上面三个数各对应一件事。共享：没见过的新题每题从 75.6 秒降到 8.5 秒，快 8.9 倍，正确率从 49% 到 100%，这是共享本身的提升，任何共享方法都有。'
  + '维护：区别在数据变化之后。5 种破坏性写入下 MAVRA 73%，检索历史示例 57%，提示它自己检查数据也只有 63%，只在表结构变化时停用 59%。'
  + '保证：在不用大模型、固定学到的定义、只换维护方式的受控实验里，条件能发现的写入下 MAVRA 没有错答，只在表结构变化时失效的做法有 629 个错答；并发写入下 11,297 次使用，没有一次在违反条件的数据上作答，检查和执行不在同一快照时这个比例是 3.8–4.6%。'
  + '表里每种方法都写了做法。“检索历史示例”是 agent 记忆里常见的做法：把成功的问答存下来，按相似度取回参考，但不检查数据变没变。'
  + 'MAVRA 还有一个消融“每次全部重查”（同样的检查与修复，去掉按表版本复用），准确率 82% / 74%，和 MAVRA 相同，说明准确率来自检查与修复本身；按表版本复用只省时间，论文不把效率当成贡献。'
  + '73% 不是 100%：剩下的错集中在两种写入——重复加载和日期键格式变更都能检测到，但没有过滤能修好，定义失效，agent 只能自己重新探索，正确率分别是 59% 和 15%；其余三种破坏性写入都能修复，93%–100%。'
  + '单位变化（上游改按分记金额，数值乘 100）谁都发现不了，作为对照，表里没列；它下面各共享方法都是 48%，剩下答对的是本来就不受影响的题。',
  'exp/2026-10-02-scenarios-ds（scen-stats.json：MAVRA = metric-global-snap，消融 = metric-global-def，逐种写入的正确率在 per_change；论文宏 \\Ds*）、'
  + 'exp/2026-10-02-cache-baseline-tpcds 与快照压力测试（\\Rp*、\\Sn*）、tools/sharing-stats.py（\\AmHold*）。');

// 8 Summary and limits ----------------------------------------------------------------------------------------
pres.addSection({ title: '总结' });
s = content('总结：MAVRA 做什么，不做什么', '总结');
{
  const gap = 0.3, cw = (W - 2 * M - 2 * gap) / 3;
  [
    ['问题', 'agent 学到的定义共享给别人后，会因日常的数据写入悄悄变错，而 SQL 照常执行、不报错。', C.red, C.paleAmber],
    ['方法', '共享记忆层，每条定义带着从写法推出的条件：只发布通过准入的定义；条件在查询的快照上成立才使用；数据变了替所有使用者验证、修复或失效，并发布更快的等价写法。', C.blue, C.paleBlue],
    ['结果', '共享让新题快 8.9 倍、正确率 49% → 100%；破坏性写入后答对 73%（检索示例 57%）；条件能发现的写入 0 错答，并发下 0 次误答。', C.violet, C.paleViolet],
  ].forEach(([head, body, color, pale], k) => {
    card(s, { x: M + k * (cw + gap), y: 1.15, w: cw, h: 2.75, head, body, color, pale, size: 16 });
  });
  const half = (W - 2 * M - 0.4) / 2;
  card(s, { x: M, y: 4.15, w: half, h: 2.5, head: '能做到', color: C.green, pale: C.paleGreen, size: 15, body: [
    para('旧记录有唯一的当前标志：检测，并修复为新修订'),
    para('整批重复加载：检测到，修不好就失效并通知'),
    { text: '主表与备份都看起来合理：不擅自选择，交给人确认' },
  ] });
  card(s, { x: M + half + 0.4, y: 4.15, w: half, h: 2.5, head: '做不到', color: C.red, pale: C.grey, size: 15, body: [
    para('数值本身错了而行和键都没变（如金额单位从元改成分）'),
    para('判断业务含义对不对（含不含税，要有人给口径）'),
    { text: '未声明所依据修订的 SQL：照常执行，不在保证内' },
  ] });
}
notes(s, '三句话：问题——学到的定义共享出去后会因日常写入悄悄变错，SQL 却不报错；方法——共享记忆层，定义带着从写法推出的条件，把住发布、依赖、维护与改进三关；结果——共享让 agent 又快又准，数据变化后答对最多，条件能发现的写入不出错。'
  + '边界要说清楚。能做的：旧记录有唯一的当前标志，检测并修复；整批重复加载，检测到但修不了，失效并通知；主表和备份都合理时不擅自选，交给人。'
  + '做不到的：数值本身错了、结构没错，行数和键都没变，条件发现不了——比如上游改成按分记金额；或者时区换算把 10 月 1 日凌晨的销售记成 9 月 30 日，每个日期键都存在、都只对应一天，只是日子错了，数据库里没有依据，要靠和源系统对账。'
  + 'MAVRA 也不判断业务含义对不对，那需要有人给口径；它保护的是在 run_sql 里声明了所依据修订的查询，没声明的照常执行和审查，但不在保证范围内。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
