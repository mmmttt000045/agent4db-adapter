// Builds docs/mavra-system.pptx, a 12-slide Chinese deck that presents MAVRA as a memory
// middleware between data agents and the database: how it differs from Text-to-SQL, the
// problem, the architecture, what the memory holds and how it is managed, one real example,
// and two closing slides of experimental results. The three system figures come from
// tools/deck/figures/ (drawn by `python3 tools/figures/build.py --deck`, rendered to PNG).
// Every number comes from the archived run records or the paper's generated macros
// (overleaf/gen/*.tex). Wording uses standard database terms.
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
  violet: '6A58A3', paleViolet: 'EFECF7', red: 'B5392A', green: '2E7D4F',
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

// Bullet runs for band(): an optional bold heading line, then one bullet per item.
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
// A cell made of several lines.
const lines = (...parts) => ({ text: parts.map((p, k) => {
  const run = typeof p === 'string' ? { text: p, options: {} } : { text: p.text, options: { ...p.options } };
  if (k < parts.length - 1) run.options.breakLine = true;
  return run;
}) });
// A section heading inside a slide.
function heading(slide, value, y, color = C.blue) {
  text(slide, value, { x: M, y, w: W - 2 * M, h: 0.35, fontSize: 15, bold: true, color, valign: 'middle' });
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
  objects: [titlePh(0.3, 0.75, 30, C.ink, 'middle')], slideNumber: number(C.muted) });

function content(title, section) {
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: section });
  s.addText(title, { placeholder: 'title' });
  return s;
}

// 1 Title -------------------------------------------------------------------------
pres.addSection({ title: '开场' });
let s = pres.addSlide({ masterName: 'TITLE', sectionTitle: '开场' });
s.addText('MAVRA：数据智能体与数据库之间的\n记忆中间件', { placeholder: 'title' });
s.addText('持久化智能体获得的数据库知识 · 跨智能体共享 · 在数据更新下保持有效', { placeholder: 'body' });
s.addNotes('MAVRA 是部署在数据智能体与数据库之间的中间件。它做三件事：'
  + '把智能体在探索数据库时获得的知识持久化；跨智能体共享；在数据更新后维护这些知识的有效性——存在唯一修复时发布新修订，否则使其失效。'
  + '先说明它与 Text-to-SQL 的区别和要解决的问题，再说明架构、记忆的内容与管理方式，用一个例子走一遍，最后是实验结果。');

// 2 Text-to-SQL vs MAVRA --------------------------------------------------------------
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
    ['记忆', '智能体获得的数据库知识：表统计信息、连接路径、指标定义'],
    ['共享', '跨智能体、跨会话共享'],
    ['关注', '已有知识在当前数据上的有效性'],
  ] },
].forEach(({ x, tag, head, color, pale, rows }) => {
  s.addShape('roundRect', { x, y: 1.3, w: half, h: 3.65, fill: { color: pale }, line: { color: pale },
    rectRadius: 0.12, objectName: `card ${tag}` });
  text(s, tag, { x: x + 0.35, y: 1.5, w: half - 0.7, h: 0.4, fontSize: 16, bold: true, color });
  text(s, head, { x: x + 0.35, y: 1.95, w: half - 0.7, h: 0.55, fontSize: 22, bold: true, color: C.ink });
  rows.forEach(([k, v], i) => {
    const y = 2.8 + i * 0.5;
    text(s, k, { x: x + 0.35, y, w: 0.8, h: 0.42, fontSize: 16, bold: true, color, valign: 'middle' });
    text(s, v, { x: x + 1.2, y, w: half - 1.55, h: 0.42, fontSize: 16, valign: 'middle' });
  });
});
band(s, [
  { text: '两者处于不同层次：', options: { bold: true, color: C.blue } },
  { text: '任何 Text-to-SQL 模型或数据智能体都可以作为用户智能体接入 MAVRA。'
    + 'MAVRA 不生成 SQL；它向智能体提供经过验证的知识，并在查询执行前验证其有效性。' },
], { y: 5.2, h: 1.35, fill: C.paleAmber, size: 17 });
s.addNotes('Text-to-SQL 研究的是翻译：给定自然语言问题和数据库模式，生成一条 SQL，评价这条 SQL 是否正确。'
  + '它是无状态的：每个问题独立处理，不保留任何结果。'
  + 'MAVRA 不是新的 Text-to-SQL 方法，也不生成 SQL。它位于智能体与数据库之间，智能体对数据库的访问都经由它转发。'
  + '它关注的是另一个问题：智能体在探索中获得的知识——“营业额对应哪一列”“两张表如何连接”——如何持久化、如何共享、数据更新后是否仍然有效。'
  + '因此两者处于不同层次，任何 Text-to-SQL 模型都可以作为用户智能体接入 MAVRA。');

// 3 The problem: business rules are not in the schema; shared definitions go stale ---------------
s = content('问题：业务口径不在模式中；共享之后，数据更新又使定义失效', '问题');
heading(s, '① 无共享定义：同一问题三次独立求解。题目“9 月的门店营业额是多少？”只给名称，参考答案 1307.0 万', 1.15);
table(s, [
  ['', '所选度量列', '答案', '轮数'],
  ['无共享定义 · 第 1、2 次', 'ss_ext_sales_price（扩展销售额，折扣前）', bad('1413.8 万 ✗'), '5'],
  ['无共享定义 · 第 3 次', 'ss_net_paid（净支付额）', good('1307.0 万 ✓'), '5'],
  [strong('有 MAVRA · 3 次结果一致', C.blue), 'ss_net_paid（检索到共享的指标定义）', good('1307.0 万 ✓'), '3'],
], { x: M, y: 1.55, w: W - 2 * M, colW: [3.0, 6.0, 2.0, 1.133], size: 13 });
heading(s, '② 共享之后：定义发布后数据库持续更新，沿用已发布的定义', 3.2);
table(s, [
  ['更新', '数据库中的变化', '参考答案', '沿用已发布的定义'],
  ['增量加载', '追加新销售记录（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '旧行保留并标记为非当前（ss_is_current = 0），插入九折后的当前行，65,915 行', '1293.3 万',
    lines(bad('1430.1 万 ✗'), '新旧版本重复计入')],
  ['重复加载', '4 个月的销售批次被再次加载，+110,165 行', '1307.0 万', lines(bad('2613.9 万 ✗'), '9 月重复计入')],
], { x: M, y: 3.6, w: W - 2 * M, colW: [1.4, 6.0, 1.6, 3.133], size: 13 });
band(s, bulleted(null, C.red, [
  '选择哪一列由业务口径决定，模式中并不记录；无共享知识时每次重新推断，答案不稳定',
  '三种更新均为普通 DML、模式未变，查询仍成功执行；定义被共享，一处失效则所有使用方同时出错',
]), { y: 5.65, h: 1.05, size: 14 });
footnote(s, '记录：noctis results/scen-20261002，留出任务 M1-P1；无共享定义：dsv41flash-r1-a、r2-b、r3-a；MAVRA：r1–r3-g3fix--snap；'
  + '对照组“沿用已发布的定义”仅在模式变更时使定义失效，3 次运行答案相同。合成零售数据，年份略去。');
s.addNotes('两个问题，都来自实验的原始记录。'
  + '第一，业务口径不在模式中。题目只给“门店营业额”这个名称，无共享定义的智能体三次独立求解：两次选了折扣前的扩展销售额，错误；一次选了净支付额，正确。'
  + '事实表中有多个候选度量列，选哪一列是业务规则，模式里没有；每次重新推断，答案就不稳定。接入 MAVRA 后检索到共享的定义，三次都对，3 轮完成。'
  + '第二，共享之后，数据更新会使定义失效。增量加载没有问题；数据更正——旧行标记为非当前、再插入更正行——沿用定义会把新旧版本重复计入；重复加载让 9 月的值翻倍。'
  + '三种更新都是普通 DML，模式未变，基于模式变更的失效策略检测不到，查询也不报错，而定义是共享的，一处失效所有使用方一起错。'
  + '所以 MAVRA 不只是持久化知识，还要管理知识。');

// 4 Architecture ------------------------------------------------------------------------------
pres.addSection({ title: 'MAVRA' });
s = content('系统架构：请求路径', 'MAVRA');
figure(s, 'overview');
s.addNotes('左侧是用户智能体，发出两类请求。'
  + '蓝色 1–5 是检索指标定义：智能体只给出“营业额”，查询服务从共享记忆中读取定义；'
  + 'store_sales 的表版本已变，某个条件在新版本上尚无验证结果，交给维护执行验证，结果写入缓存，再返回有效修订 v2。'
  + '橙色 6–8 是执行 SQL：智能体的 SQL 声明依赖 v2，执行前验证复用缓存中的结果，在同一快照上执行。'
  + '紫色是学习：内置智能体学习到的定义，通过准入检查后写入共享记忆。共享记忆中还有表统计信息和连接路径，图中未展开。');

// 5 What the memory holds, and the tools through which agents use it -----------------------------
s = content('记忆的内容与接口', 'MAVRA');
table(s, [
  ['记忆类型', '内容', '智能体通过哪个工具使用', '数据更新后的处理'],
  [strong('表统计信息', C.blue), '列、类型、空值比例、不同值数、高频取值、样例行',
    'describe_table：表版本未变则返回缓存结果', '表版本变化：下次访问时重新采样'],
  [strong('连接路径', C.blue), '连接键、基数（N:1 / 1:1）、所需过滤谓词、未匹配行比例、已证伪的写法',
    'join_path', '任一表版本变化：重新验证“1”侧键的唯一性'],
  [strong('指标定义', C.blue), '业务口径、度量、粒度、时间维度、注意事项、示例查询，以及验证条件与学习证据',
    'find_metric 检索；run_sql 声明所依赖的修订，失效或被替代则拒绝', '依赖表版本变化：重新验证条件；不成立则修复或失效'],
  [strong('验证结果', C.blue), '条件、表版本、结果', '（内部）执行前在查询快照上验证时复用',
    '按（条件，表版本）键存储；跨定义、跨智能体共享'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [1.45, 3.9, 3.5, 3.283], size: 14 });
band(s, [
  { text: '记忆来源：', options: { bold: true, color: C.violet } },
  { text: '内置智能体（大模型）求解给定业务口径的学习任务，判定正确的轨迹抽取为指标定义，通过 7 项准入检查后发布；'
    + '用户智能体获得的表统计信息与连接路径同样写入。', options: { breakLine: true } },
  { text: '每条记忆附带：', options: { bold: true, color: C.violet } },
  { text: '依赖的表版本、状态（有效 / 待验证 / 失效）、修订号、写入者、使用者；每次响应附带通知，告知使用方其定义已失效或已修复。'
    + '第 1 次运行结束时共 70 条记忆，查询 995 次，696 次命中。' },
], { y: 4.95, h: 1.75, fill: C.paleViolet, size: 14 });
footnote(s, SOURCE);
s.addNotes('记忆分四类。表统计信息来自描述表；连接路径是已验证的两表连接方式，包括基数、所需过滤谓词、未匹配行比例和已证伪的写法；'
  + '指标定义最重要，除了业务口径、度量、粒度、时间维度，还带着它成立所依赖的验证条件和学习证据；验证结果按“条件 + 表版本”存储，跨定义共享。'
  + '从智能体看，这些都是工具：描述表、查询连接路径、检索指标定义、执行 SQL 时声明所依赖的修订。'
  + '记忆有两个来源：内置智能体学习指标定义，用户智能体探索时得到的统计信息和连接路径也写入。每条记忆附带依赖的表版本、状态、修订号、写入者和使用者。');

// 6 Five steps of memory management ----------------------------------------------------------
pres.addSection({ title: '记忆管理' });
s = content('记忆管理的五个环节', '记忆管理');
table(s, [
  ['环节', '触发', 'MAVRA 的处理', '门店营业额的记录'],
  [strong('写入', C.violet), '内置智能体正确求解一道学习任务', '抽取为结构化定义，通过 7 项准入检查后发布', '发布 v1：抽取 16.3 秒，准入检查 5.7 秒'],
  [strong('读取', C.blue), '用户智能体按名称检索', '依赖表版本未变：直接返回；已变：先维护再返回', '询问 9 月营业额：检索到 v1，3 轮答对'],
  [strong('使用', C.amber), '用户智能体执行 SQL 并声明所依赖的修订', '失效或被替代的修订拒绝；在查询快照上验证条件后执行', 'SQL 声明“门店营业额 v1”'],
  [strong('维护', C.blue), '数据更新后，定义首次被访问时', '仅重新验证受影响的条件；结果按（条件，表版本）缓存并共享',
    '增量加载后：6 条定义仅执行 2 次验证'],
  [strong('迭代', C.blue), '某条件不再成立', '存在唯一修复：发布新修订；否则失效并通知；学到新证据后重新发布',
    '数据更正：v1 → v2；重复加载：失效'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [1.2, 3.0, 4.6, 3.333], size: 15 });
band(s, [
  { text: '与 Text-to-SQL 的区别在于：', options: { bold: true, color: C.blue } },
  { text: '这五个环节均发生在单条查询的生成之外，跨问题、跨智能体、跨表版本。' },
], { y: 5.75, h: 0.9, fill: C.paleBlue, size: 16 });
footnote(s, SOURCE);
s.addNotes('记忆管理分五个环节，颜色与后面两张图一致。'
  + '写入：内置智能体正确求解学习任务，抽取为结构化定义，通过 7 项准入检查后发布。读取：用户智能体按名称检索，依赖表版本未变则直接返回，已变则先维护。'
  + '使用：执行 SQL 时声明所依赖的修订，失效的拒绝，在查询快照上验证条件后执行。'
  + '维护：数据更新后，定义首次被访问时，仅重新验证受影响的条件，结果缓存并共享——增量加载后，6 条依赖 store_sales 的定义只执行了 2 次验证。'
  + '迭代：条件不成立时，存在唯一修复则发布新修订，否则失效并通知。'
  + '这些都发生在单条查询的生成之外，这就是与 Text-to-SQL 的区别。');

// 7 Writing: from one solved task to one definition --------------------------------------
s = content('写入：从一次求解到一条定义', '记忆管理');
const lw = 5.6;
text(s, '学习任务', { x: M, y: 1.2, w: lw, h: 0.4, fontSize: 16, bold: true, color: C.violet });
s.addShape('roundRect', { x: M, y: 1.65, w: lw, h: 1.25, fill: { color: C.paleViolet },
  line: { color: C.paleViolet }, rectRadius: 0.08 });
text(s, '3 月的门店营业额是多少？口径：门店营业额 = 门店销售行的净支付额（store_sales.ss_net_paid）之和，'
  + '按销售日期归属期间。保留两位小数。', { x: M + 0.2, y: 1.75, w: lw - 0.4, h: 1.05, fontSize: 15, valign: 'middle' });
text(s, '内置智能体：5 轮、7 次工具调用、9.5 秒，最终 SQL', { x: M, y: 3.05, w: lw, h: 0.35,
  fontSize: 14, color: C.muted });
s.addShape('roundRect', { x: M, y: 3.45, w: lw, h: 1.55, fill: { color: C.grey }, line: { color: C.grey },
  rectRadius: 0.08 });
text(s, 'SELECT ROUND(SUM(ss.ss_net_paid), 2)\nFROM store_sales ss\nJOIN date_dim d\n  ON ss.ss_sold_date_sk = d.d_date_sk\nWHERE d.d_year = … AND d.d_moy = 3',
  { x: M + 0.2, y: 3.52, w: lw - 0.4, h: 1.4, fontSize: 13, fontFace: CODE, valign: 'middle' });
text(s, [
  { text: '答案 13,570,368.70，与参考答案一致 ✓', options: { bold: true, color: C.green, breakLine: true } },
  { text: '大模型将求解轨迹抽取为结构化定义（16.3 秒）；7 项准入检查全部通过（5 条查询，5.7 秒），发布为修订 v1。' },
], { x: M, y: 5.15, w: lw, h: 1.2, fontSize: 15, valign: 'top' });
const rx = M + lw + 0.35, rw = W - M - rx;
text(s, '写入记忆的定义（实验记录）', { x: rx, y: 1.2, w: rw, h: 0.4, fontSize: 16, bold: true, color: C.blue });
table(s, [
  ['字段', '内容'],
  ['名称', '门店营业额（别名：门店销售净额、store revenue）'],
  ['业务口径', '门店销售明细行净支付额（销售额 − 折扣，不含税）之和，按销售日期归属期间'],
  ['度量', 'store_sales 上 SUM(ss_net_paid)，无过滤谓词'],
  ['粒度 · 时间维度', '销售日 × 小票号 × 商品；按销售日关联 date_dim'],
  ['验证条件', '粒度键唯一；日期键唯一；日期键完整性'],
  ['证据 · 状态', '学习时的 SQL、答案与表版本；有效，修订 v1'],
], { x: rx, y: 1.65, w: rw, colW: [1.55, rw - 1.55], size: 12 });
band(s, [
  { text: '7 项准入检查：', options: { bold: true, color: C.violet } },
  { text: '业务依据 · 答案判定正确 · 静态合法性（列存在、连接沿已验证路径、不含任务字面量）· 粒度成立 · SQL 审查 · 重放示例 SQL · 重放规范 SQL（其他智能体读取的正是这些字段）。', options: { breakLine: true } },
  { text: '“答案判定正确”在部署中由指标负责人确认一次，或与已发布报表对账；此后的维护与修复不再依赖参考答案。' },
], { x: rx, y: 5.0, w: rw, h: 1.65, fill: C.paleViolet, size: 12 });
footnote(s, SOURCE);
s.addNotes('写入是记忆的入口。内置智能体得到一道给定业务口径的学习任务，5 轮写出 SQL，答案正确。'
  + '然后大模型将求解轨迹抽取为右边这条结构化定义：名称、业务口径、度量和粒度、时间维度、注意事项，以及 MAVRA 从中推出的三个验证条件和学习证据。'
  + '发布前通过 7 项准入检查，最关键的是最后一项：由定义字段编译的规范 SQL 必须得到相同答案，因为其他智能体读取的正是这些字段，遗漏过滤谓词或把月份写死都会在这里被发现。'
  + '“答案判定正确”在实验中用任务的参考答案；部署中由指标负责人确认一次，或与已发布报表对账。它只在写入时需要一次，此后的维护和修复都不依赖参考答案。');

// 8 Reading and using -------------------------------------------------------------------------
s = content('读取与使用：一次请求的处理路径', '记忆管理');
figure(s, 'lookup');
s.addNotes('上方是检索指标定义：名称匹配到“门店营业额”（“电子品类门店营业额”同样包含查询词，一并返回，由智能体依据口径说明选择）；'
  + '比较 store_sales 的表版本（14 → 15）；逐个条件查缓存：“粒度键唯一”电子品类的定义刚验证过，直接复用；'
  + 'date_dim 未变，复用；“日期键完整性”在版本 15 上没有结果，执行验证并写入缓存；最后返回有效修订 v2。'
  + '中间是验证结果缓存：按（条件，表版本）存储，表中标明写入者和复用的步骤。'
  + '下方是执行 SQL：先检查声明的 v2 是否有效；再在查询快照上验证——期间又有更新，表版本变为 16，'
  + '因此两个条件在快照内重新验证并写入缓存；最后在同一快照上执行。');

// 9 Maintenance and revision ---------------------------------------------------------------
s = content('维护与迭代：一条定义的生命周期', '记忆管理');
figure(s, 'lifecycle', 1.15, 4.5);
band(s, [
  { text: '修订规则：', options: { bold: true, color: C.blue } },
  { text: '同结构再次学到 → 为原定义记一次佐证；同名不同结构 → 并存，由智能体依据口径选择；'
    + '其他定义遇到相同的条件失败 → 复用验证结果与修复（门店营业额复用电子品类的修复，45.8 毫秒）；'
    + '失效后 → 重新学习，通过准入检查再作为新修订发布。' },
], { y: 5.75, h: 0.95, size: 14 });
s.addNotes('沿着门店营业额走一遍。内置智能体求解“3 月门店营业额”，答案判定正确、准入检查通过，发布 v1。'
  + '之后增量加载一批销售记录：条件仍成立，其他定义直接复用验证结果，仍为 v1。'
  + '再之后一批销售被更正：旧行标记为非当前，插入当前行——“粒度键唯一”不成立，v1 失效，不处理会把新旧版本重复计入。'
  + '修复搜索在低基数列上枚举等值谓词，只有“ss_is_current = 1”可行；按学习时刻重算 3 月，结果一致，发布 v2。'
  + '红框是另一种结果：批次重复加载，没有谓词能恢复唯一性，定义失效并通知使用方，等待重新学习。'
  + '下面是修订的其他规则：同结构再学到只记佐证；同名不同结构并存；相同条件失败复用修复；失效后重新学习再发布。');

// 10 Back to the example ------------------------------------------------------------------------
pres.addSection({ title: '回到例子' });
s = content('回到例子：引入 MAVRA 之后', '回到例子');
table(s, [
  ['更新', '数据库中的变化', '参考答案', '不维护（对照组）', 'MAVRA'],
  ['增量加载', '追加新销售记录（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓'),
    lines('条件仍成立，保持 v1', '6 条定义仅执行 2 次验证', good('2613.9 万 ✓'))],
  ['数据更正', '旧行保留并标记为非当前（ss_is_current = 0），插入九折后的当前行，65,915 行',
    '1293.3 万', lines(bad('1430.1 万 ✗'), '新旧版本重复计入'),
    lines('v1 失效 → 修复为 v2', '（谓词 ss_is_current = \'1\'）', good('1293.3 万 ✓'))],
  ['重复加载', '4 个月的销售批次被再次加载，+110,165 行', '1307.0 万', lines(bad('2613.9 万 ✗'), '9 月重复计入'),
    lines('无唯一修复 → 失效并通知', '智能体自行去重', { text: '3 次运行中 2 次答对', options: { bold: true } })],
], { x: M, y: 1.25, w: W - 2 * M, colW: [1.45, 3.75, 1.35, 2.0, 3.583], size: 14 });
band(s, [
  { text: '数据更正后的处理（系统记录）：', options: { bold: true, color: C.blue } },
  { text: '首个访问 store_sales 的请求触发验证，“粒度键唯一”不成立（1,065,915 行只有 1,000,000 个不同键，5.5 秒）→ v1 失效；'
    + '修复搜索得到唯一可行谓词 ss_is_current = \'1\'，4 项检查通过后发布 v2，共 28.7 秒；门店营业额复用该修复，45.8 毫秒。', options: { breakLine: true } },
  { text: '回归测试的基准：', options: { bold: true, color: C.blue } },
  { text: '按学习时刻 as-of 查询比较，学习时的 SQL 与修复后的定义都得到 1357.0 万，接受修复；'
    + '按当前数据比较得到 1489.1 万与 1342.4 万，会误拒正确的修复——学习时的 SQL 在当前数据上同样过期，它仅在学习时的快照上被判定正确。' },
], { y: 4.6, h: 2.1, size: 13 });
footnote(s, '对照组：仅在模式变更时使定义失效，3 次独立运行答案相同。MAVRA 栏为第 1 次运行；增量加载与数据更正 3 次运行结果相同。'
  + '“按当前数据比较”来自对照实验 dsv41flash-r1-g3fix--exref。' + DATA);
s.addNotes('回到前面那张表，加上 MAVRA 一栏。'
  + '增量加载：定义仍然有效，6 条依赖 store_sales 的定义一共只执行了 2 次验证。'
  + '数据更正：MAVRA 检测到“粒度键唯一”不成立，旧修订失效，修复搜索找到唯一可行的谓词，4 项检查通过后发布 v2，共 28.7 秒；门店营业额复用这个修复只用 45.8 毫秒；答案正确。'
  + '重复加载：没有谓词能修复，定义失效并通知智能体，智能体自行去重，3 次中 2 次正确。'
  + '回归测试为什么按学习时刻比较：学习任务问的是 3 月，恰在被更正的范围内。按当前数据比较，学习时的 SQL 本身就把旧行计入，得 1489 万，与修复后的 1342 万不一致，正确的修复会被拒绝；'
  + '我们实际跑过这个对照，确实被拒绝。按学习时刻比较两者都是 1357 万。学习时的答案是唯一被确认过的答案，所以修复只与它比较，不需要参考答案。');

// 11 Results: end to end -------------------------------------------------------------------------
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
  + '两个对照：单位变化不违反任何条件，所有方法同样过期，说明检测范围与命题一致；备份副本下修复有歧义，MAVRA 按规则使定义失效，检索示例碰巧答对，这是如实保留的负结果。');

// 12 Results: system level -------------------------------------------------------------------------
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
    lines('为整定义重查耗时的 14.0%；按表版本缓存验证查询可得同样节省（16.7%）', '100 万到 1,600 万行比例不变')],
], { x: M, y: 1.25, w: W - 2 * M, colW: [2.2, 4.0, 5.933], size: 14 });
band(s, [
  { text: '结论：', options: { bold: true, color: C.blue } },
  { text: '覆盖的更新全部检测到，不向使用方返回错误答案；修复以学习时刻为基准，不需要参考答案；同快照验证消除并发写入下的失效窗口。'
    + '维护效率与通用缓存相当，不是本文的贡献。' },
], { y: 5.85, h: 0.85, fill: C.paleBlue, size: 14 });
footnote(s, '来源：exp/2026-10-02-cache-baseline-tpcds（配对回放、回归基准、维护成本）、exp 快照压力测试（同快照验证），'
  + '与论文宏 \\Rp*、\\Tr*、\\Sn*、\\CbStag* 一致。错答 = 在条件已被破坏的数据上照常返回答案。');
s.addNotes('系统层实验不用大模型：固定各次运行学到的定义库，只改变维护方式，这样比较的是机制本身。'
  + '配对回放：合成数据 1,470 题次，MAVRA 在覆盖的更新下没有错答，99 个错答全部是单位变化这个对照；按模式变更失效有 629 个错答。TPC-DS 上用 99 个查询模板导出的定义，结果一致。'
  + '同快照验证：并发写入下 11,297 次使用没有一次在违反条件的数据上作答，先检查后执行有 3.8% 到 4.6%。'
  + '修复的回归基准：按学习时刻比较，修复成功的数量与使用标准答案参照完全相同；按当前数据比较会误拒正确的修复。'
  + '维护成本：19 条定义时为整定义重查的 14%，但按表版本缓存验证查询也能得到同样的节省，所以效率不是本文的贡献，贡献在于检查什么、何时可以依赖检查结果、失败后怎么办。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
