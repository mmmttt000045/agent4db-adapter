// Builds docs/mavra-system.pptx, a Chinese deck that presents MAVRA as a memory middleware
// between data agents and the database: how it differs from Text-to-SQL, what the memory
// holds, how it is written, read, used, maintained and revised, then one real example from
// the end-to-end study (store revenue under three everyday updates). The three system figures
// come from tools/deck/figures/ (drawn by `python3 tools/figures/build.py --deck`, rendered to
// PNG). Every number on the slides comes from the archived run records. Wording uses standard
// database terms (table version, revision, predicate, grain, cardinality, invalidation,
// admission, snapshot) rather than coined or colloquial names.
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

// Bullet runs for band(): a bold heading line, then one bullet per item.
function bulleted(head, color, items) {
  return [
    { text: head, options: { bold: true, color, breakLine: true } },
    ...items.map((t, k) => ({ text: t, options: { bullet: true, breakLine: k < items.length - 1 } })),
  ];
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
// A cell with a main line and a smaller second line (a tool name or a code fragment).
const sub = (main, second, code = true) => ({ text: [
  { text: main, options: { breakLine: true } },
  { text: second, options: { fontSize: 11, color: C.muted, fontFace: code ? CODE : FONT } },
] });
// A cell made of several lines.
const lines = (...parts) => ({ text: parts.map((p, k) => {
  const run = typeof p === 'string' ? { text: p, options: {} } : { text: p.text, options: { ...p.options } };
  if (k < parts.length - 1) run.options.breakLine = true;
  return run;
}) });

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
pres.defineSlideMaster({ title: 'CLOSING', background: { color: C.navy },
  objects: [titlePh(0.6, 0.9, 32, C.white, 'middle')], slideNumber: number(C.ice) });

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
  + '先说明它与 Text-to-SQL 的区别，再说明记忆的内容与管理方式，最后用端到端实验中的一个例子走一遍。');

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

// 3 Real record: the same question without shared definitions ---------------------------
s = content('实验记录：无共享定义时，同一问题三次独立求解', '问题');
text(s, [
  { text: '题目：“9 月的门店营业额是多少？保留两位小数。”', options: { bold: true } },
  { text: '仅给出指标名称，不给出业务口径。参考答案 1307.0 万。' },
], { x: M, y: 1.2, w: W - 2 * M, h: 0.5, fontSize: 17, valign: 'middle' });
table(s, [
  ['', '所选度量列', '答案', '轮数', '输入 token'],
  ['无共享定义 · 第 1 次', sub('ss_ext_sales_price', '扩展销售额（折扣前）', false), bad('1413.8 万 ✗'), '5', '10,957'],
  ['无共享定义 · 第 2 次', sub('ss_ext_sales_price', '扩展销售额（折扣前）', false), bad('1413.8 万 ✗'), '5', '11,212'],
  ['无共享定义 · 第 3 次', sub('ss_net_paid', '净支付额', false), good('1307.0 万 ✓'), '5', '10,440'],
  [strong('有 MAVRA · 3 次结果一致', C.blue), sub('ss_net_paid', '检索到共享的指标定义', false),
    good('1307.0 万 ✓'), '3', '8,467 – 8,824'],
], { x: M, y: 1.8, w: W - 2 * M, colW: [3.0, 4.3, 1.9, 1.0, 1.933], size: 14 });
band(s, bulleted('错误来自业务口径，而非 SQL 语法', C.blue, [
  '事实表中存在多个候选度量列（ss_ext_sales_price、ss_net_paid、ss_net_paid_inc_tax 等）；选择哪一列由业务口径决定，模式中并不记录',
  '无共享知识时，每次独立推断口径，同一问题的答案不稳定',
  '共享已验证的指标定义后：15 道题 × 3 次运行，数据未变时准确率从 49% 升至 100%，每题平均 5.6 轮降至 3.6 轮，输入 token 减少 34%',
]), { y: 4.95, h: 1.8, size: 14 });
footnote(s, '记录：noctis results/scen-20261002，留出任务 M1-P1；无共享定义（仍共享表统计信息与连接路径）：dsv41flash-r1-a、r2-b、r3-a；'
  + 'MAVRA：r1–r3-g3fix--snap。合成零售数据，年份略去。');
s.addNotes('这是实验中的原始记录。题目只给出指标名称“门店营业额”，不给业务口径。'
  + '无共享定义的智能体独立求解三次：两次选择了折扣前的扩展销售额 ss_ext_sales_price，答 1413.8 万，错误；一次选择净支付额 ss_net_paid，答案正确。每次 5 轮。'
  + '接入 MAVRA 的智能体先检索记忆，得到内置智能体学习到的“门店营业额”定义，三次均正确，3 轮完成。'
  + '错误不在 SQL 语法，而在业务口径：事实表中有多个候选度量列，选择哪一列是业务规则，模式中并不记录。'
  + 'Text-to-SQL 每次重新推断，答案不稳定；共享已验证的定义后，准确率和成本同时改善。');

// 4 The problem: shared definitions go stale ------------------------------------------------
s = content('共享之后：数据更新可能使定义静默失效', '问题');
text(s, '“门店营业额”的定义发布后，数据库持续接受更新。之后再次询问“9 月门店营业额”，沿用已发布的定义：',
  { x: M, y: 1.2, w: W - 2 * M, h: 0.45, fontSize: 16, color: C.muted, valign: 'middle' });
table(s, [
  ['更新', '数据库中的变化', '参考答案', '沿用已发布的定义'],
  ['增量加载', '追加一批新的销售记录（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '部分销售被更正：旧行保留并标记为非当前（ss_is_current = 0），插入九折后的当前行，共 65,915 行',
    '1293.3 万', lines(bad('1430.1 万 ✗'), '新旧版本重复计入')],
  ['重复加载', '4 个月的销售批次被再次加载，+110,165 行', '1307.0 万', lines(bad('2613.9 万 ✗'), '9 月重复计入')],
], { x: M, y: 1.8, w: W - 2 * M, colW: [1.6, 5.4, 1.6, 3.533], size: 15 });
band(s, bulleted('问题所在', C.red, [
  '三种更新均为普通 DML（INSERT / UPDATE），模式未变：基于模式变更的失效策略无法检测',
  '查询仍成功执行，不报错：使用方无法从执行结果察觉',
  '定义被共享：一处失效，所有使用方同时出错',
]), { y: 4.75, h: 1.85, size: 17 });
footnote(s, '“沿用已发布的定义”为对照组：仅在模式变更时使定义失效；3 次独立运行答案相同。' + DATA);
s.addNotes('共享带来新的问题：定义是在某一快照上学习的，数据会继续更新。同一问题“9 月门店营业额”，在三种常见更新之后分别再问一次，沿用已发布的定义。'
  + '增量加载没有问题。数据更正——数据仓库中常见的做法是旧行不删除、标记为非当前，再插入更正后的行——沿用定义会把新旧版本重复计入，多出 137 万。'
  + '重复加载，同一批次被加载两次，9 月的值翻倍。'
  + '三种更新都是普通 DML，模式未变，基于模式变更的失效策略完全检测不到；查询也不报错。'
  + '因此 MAVRA 不只是持久化知识，还要管理知识：记录每条定义成立的条件，数据更新后重新验证。');

// 5 What MAVRA is: tools in front, memory management behind -----------------------------
pres.addSection({ title: 'MAVRA 是什么' });
s = content('MAVRA 的接口：智能体调用工具，中间件管理记忆', 'MAVRA 是什么');
table(s, [
  ['智能体调用的工具', 'MAVRA 的处理', '涉及的记忆'],
  [sub('列出表', 'list_tables'), '返回表名、估计行数与注释', '—'],
  [sub('描述表', 'describe_table'), '表版本未变：返回缓存的表统计信息；已变：重新采样并更新', '表统计信息'],
  [sub('查询连接路径', 'join_path'),
    '返回已验证的连接键、基数（N:1 / 1:1）、所需过滤谓词、未匹配行比例，以及已证伪的连接写法', '连接路径'],
  [sub('检索指标定义', 'find_metric'),
    '依赖表的版本已变：先重新验证；返回有效修订、注意事项与示例查询', '指标定义、验证结果'],
  [sub('执行 SQL，声明所依赖的指标修订', 'run_sql'),
    '修订已失效或已被替代：拒绝；否则在查询快照上验证条件后执行', '指标定义、验证结果'],
  ['每次响应', '附带通知：所用定义已失效或已修复', '使用者记录'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [3.4, 6.5, 2.233], size: 14 });
band(s, [
  { text: '记忆的来源：', options: { bold: true, color: C.violet } },
  { text: '内置智能体（大模型）求解给定业务口径的学习任务；判定正确的求解轨迹被抽取为结构化指标定义，通过 7 项准入检查后发布。'
    + '用户智能体获得的表统计信息与已验证的连接路径同样写入记忆，供所有智能体共享。' },
], { y: 5.65, h: 1.05, fill: C.paleViolet, size: 15 });
s.addNotes('从用户智能体的角度看，MAVRA 是一组数据库工具：列出表、描述表、查询连接路径、检索指标定义、执行 SQL。'
  + '区别在于每个工具都先访问记忆：描述表时，表版本未变就返回缓存的统计信息；查询连接路径时，返回已验证的连接键、基数和已证伪的写法；'
  + '检索指标定义时，依赖表的版本已变则先重新验证再返回。'
  + '执行 SQL 时，智能体声明所依赖的指标修订，失效或被替代的修订直接拒绝。每次响应附带通知，告知智能体其使用过的定义有变化。'
  + '记忆有两个来源：内置智能体学习指标定义；用户智能体在探索中获得的表统计信息和连接路径也写入记忆。');

// 6 Structure ------------------------------------------------------------------------------
s = content('系统架构：请求路径', 'MAVRA 是什么');
figure(s, 'overview');
s.addNotes('左侧是用户智能体，发出两类请求。'
  + '蓝色 1–5 是检索指标定义：智能体只给出“营业额”，查询服务从共享记忆中读取定义；'
  + 'store_sales 的表版本已变，某个条件在新版本上尚无验证结果，交给维护执行验证，结果写入缓存，再返回有效修订 v2。'
  + '橙色 6–8 是执行 SQL：智能体的 SQL 声明依赖 v2，执行前验证复用缓存中的结果，在同一快照上执行。'
  + '紫色是学习：内置智能体学习到的定义，通过准入检查后写入共享记忆。共享记忆中还有表统计信息和连接路径，图中未展开。');

// 7 What the memory holds -------------------------------------------------------------------
s = content('记忆的内容', 'MAVRA 是什么');
table(s, [
  ['类型', '内容', '示例（门店营业额）', '数据更新后的处理'],
  [strong('表统计信息', C.blue), '列、类型、空值比例、不同值数、高频取值、样例行', 'store_sales 各列的统计信息',
    '表版本变化：下次访问时重新采样'],
  [strong('连接路径', C.blue), '连接键、基数、所需过滤谓词、未匹配行比例、已证伪的写法',
    'store_sales → date_dim：ss_sold_date_sk = d_date_sk，N:1，1.03% 的销售行未匹配',
    '任一表版本变化：重新验证“1”侧键的唯一性'],
  [strong('指标定义', C.blue), '业务口径、度量、粒度、时间维度、注意事项、示例查询，以及验证条件',
    '门店营业额 v1：SUM(ss_net_paid)，粒度为小票 × 商品', '依赖表版本变化：重新验证条件；不成立则修复或失效'],
  [strong('验证结果', C.blue), '条件、表版本、结果', '“粒度键唯一”在 store_sales 版本 15 上成立',
    '按（条件，表版本）键存储：版本变化即为新条目；跨定义共享'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [1.45, 3.6, 3.9, 3.183], size: 14 });
band(s, [
  { text: '每条记忆附带：', options: { bold: true, color: C.blue } },
  { text: '依赖的表及其版本、状态（有效 / 待验证 / 失效）、修订号、写入者、使用者。', options: { breakLine: true } },
  { text: '第 1 次运行结束时共 70 条记忆，查询 995 次，其中 696 次直接命中。' },
], { y: 5.0, h: 1.15, size: 15 });
footnote(s, SOURCE);
s.addNotes('记忆分四类。表统计信息是描述表时得到的列级信息；连接路径是已验证的两表连接方式，包括基数、所需的过滤谓词、未匹配行比例，以及已证伪的写法。'
  + '指标定义是最重要的一类：业务口径、度量、粒度、时间维度，以及它成立所依赖的验证条件。'
  + '验证结果按“条件 + 表版本”存储，同一条件在同一表版本上只验证一次，跨定义共享。'
  + '每条记忆附带依赖的表及其版本、状态、修订号、写入者和使用者。第 1 次运行结束时共 70 条记忆，查询 995 次，696 次直接命中。');

// 8 One definition in full -------------------------------------------------------------------
s = content('一条指标定义的完整记录（实验数据）', 'MAVRA 是什么');
const tw2 = (W - 2 * M - 0.3) / 2;
text(s, '返回给智能体的部分', { x: M, y: 1.2, w: tw2, h: 0.4, fontSize: 16, bold: true, color: C.blue });
table(s, [
  ['字段', '内容'],
  ['名称', '门店营业额（别名：门店销售净额、store revenue）'],
  ['业务口径', '门店销售明细行净支付额（销售额 − 折扣，不含税）之和，按销售日期归属期间'],
  ['度量', 'store_sales 上 SUM(ss_net_paid)，无过滤谓词'],
  ['粒度', '销售日 × 小票号 × 商品：每行一笔销售明细'],
  ['时间维度', 'ss_sold_date_sk → date_dim，按销售日'],
  ['注意事项', '① 与日期维度内连接会排除约 1.03% 未匹配的销售行；② 使用不含税的 ss_net_paid，勿与含税的 ss_net_paid_inc_tax 混用'],
  ['示例', '学习任务与当时的 SQL'],
], { x: M, y: 1.65, w: tw2, colW: [1.25, tw2 - 1.25], size: 13 });
const xr = M + tw2 + 0.3;
text(s, '由 MAVRA 维护的部分', { x: xr, y: 1.2, w: tw2, h: 0.4, fontSize: 16, bold: true, color: C.violet });
table(s, [
  ['字段', '内容'],
  ['依据', '学习任务给定的业务口径（M1-L1）'],
  ['证据', '学习时的 SQL、答案 13,570,368.70、当时的表版本；7 项准入检查全部通过'],
  ['验证条件', '粒度键唯一；日期键唯一；日期键完整性（学习时未匹配率 1.03%）'],
  ['依赖', 'store_sales、date_dim 的表版本'],
  ['状态', '有效，修订 v1'],
  ['写入 / 使用', '内置智能体 A 写入；A、B 使用，命中 9 次'],
], { x: xr, y: 1.65, w: tw2, colW: [1.35, tw2 - 1.35], size: 13 });
band(s, [
  { text: '左侧告诉智能体如何计算，右侧让 MAVRA 判断该计算在当前数据上是否仍然有效。', options: { bold: true, color: C.blue } },
  { text: 'Text-to-SQL 生成的查询用后即弃，也不记录其成立的前提。' },
], { y: 5.75, h: 0.95, fill: C.paleBlue, size: 15 });
footnote(s, SOURCE);
s.addNotes('这是实验中“门店营业额”这条记忆的完整记录。左侧是用户智能体检索时得到的：名称和别名、业务口径、度量、粒度、时间维度、注意事项和示例。'
  + '右侧是 MAVRA 自己维护、用于判断它是否仍然有效的：依据、学习时的证据、验证条件、依赖的表版本、状态和修订号、写入者和使用者。'
  + 'Text-to-SQL 没有这样的结构：生成的查询用后即弃，也不记录它在什么前提下成立。');

// 9 Five steps of memory management ----------------------------------------------------------
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

// 10 Writing: from one solved task to one definition --------------------------------------
s = content('写入：从一次成功求解到一条定义', '记忆管理');
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
text(s, '7 项准入检查', { x: rx, y: 1.2, w: rw, h: 0.4, fontSize: 16, bold: true, color: C.violet });
table(s, [
  ['检查', '目的'],
  ['1 业务依据', '学习任务明确给出业务口径，而非推测'],
  ['2 答案判定正确', '错误答案不进入记忆'],
  ['3 静态合法性', '列存在；度量仅使用允许的列；连接沿已验证路径；包含必需的粒度过滤且不含任务字面量'],
  ['4 粒度成立', '当前快照上粒度键唯一'],
  ['5 SQL 审查', '示例查询符合记录的粒度与连接要求'],
  ['6 重放示例 SQL', '重新执行，结果与答案一致'],
  ['7 重放规范 SQL', '由定义字段编译的查询得到相同结果：其他智能体读取的正是这些字段'],
], { x: rx, y: 1.65, w: rw, colW: [2.15, rw - 2.15], size: 13 });
band(s, [
  { text: '第 2 项在部署中的来源：', options: { bold: true, color: C.violet } },
  { text: '实验使用任务的参考答案；部署中由指标负责人确认一次，或与已发布的报表对账。此后的维护与修复不再依赖参考答案。' },
], { x: rx, y: 5.3, w: rw, h: 1.3, fill: C.paleViolet, size: 13 });
footnote(s, SOURCE);
s.addNotes('写入是记忆的入口。内置智能体得到一道给定业务口径的学习任务，5 轮写出 SQL，答案正确。'
  + '然后大模型将求解轨迹抽取为结构化定义，再通过 7 项准入检查：业务依据、答案判定正确、静态合法性、粒度成立、SQL 审查，以及两次重放——'
  + '示例 SQL 重新执行结果一致，由定义字段编译的规范 SQL 也得到相同结果。最后一项最关键：其他智能体读取的正是这些字段，遗漏过滤谓词或把月份写死都会在这里被发现。'
  + '第 2 项“答案判定正确”在实验中使用任务的参考答案；部署中由指标负责人确认一次，或与已发布的报表对账。它只在写入时需要一次，此后的维护和修复都不依赖参考答案。');

// 11 Reading and using -------------------------------------------------------------------------
s = content('读取与使用：一次请求的处理路径', '记忆管理');
figure(s, 'lookup');
s.addNotes('上方是检索指标定义：名称匹配到“门店营业额”（“电子品类门店营业额”同样包含查询词，一并返回，由智能体依据口径说明选择）；'
  + '比较 store_sales 的表版本（14 → 15）；逐个条件查缓存：“粒度键唯一”电子品类的定义刚验证过，直接复用；'
  + 'date_dim 未变，复用；“日期键完整性”在版本 15 上没有结果，执行验证并写入缓存；最后返回有效修订 v2。'
  + '中间是验证结果缓存：按（条件，表版本）存储，表中标明写入者和复用的步骤。'
  + '下方是执行 SQL：先检查声明的 v2 是否有效；再在查询快照上验证——期间又有更新，表版本变为 16，'
  + '因此两个条件在快照内重新验证并写入缓存；最后在同一快照上执行。');

// 12 Maintenance and revision ---------------------------------------------------------------
s = content('维护与迭代：一条定义的生命周期', '记忆管理');
figure(s, 'lifecycle');
s.addNotes('沿着门店营业额走一遍。内置智能体求解“3 月门店营业额”，答案判定正确、准入检查通过，发布 v1。'
  + '之后增量加载一批销售记录：条件仍成立，其他定义直接复用验证结果，仍为 v1。'
  + '再之后一批销售被更正：旧行标记为非当前，插入当前行——“粒度键唯一”不成立，v1 失效，不处理会把新旧版本重复计入。'
  + '修复搜索在低基数列上枚举等值谓词，只有“ss_is_current = 1”可行；按学习时刻重算 3 月，结果一致，发布 v2。'
  + '红框是另一种结果：批次重复加载，没有谓词能恢复唯一性，定义失效并通知使用方，等待重新学习。');

// 13 Revision rules -------------------------------------------------------------------------
s = content('迭代：定义修订的演化规则', '记忆管理');
table(s, [
  ['情形', 'MAVRA 的处理', '实验记录'],
  ['同一指标再次学到相同结构的定义', '不新增，为原定义记录一次佐证', '—'],
  ['同名但结构不同', '两条并存；检索时同时返回，由智能体依据口径说明选择',
    '“门店营业额”有两条：粒度一条含销售日，一条不含'],
  ['条件不成立，存在唯一修复', 'v1 失效，发布修复后的 v2；声明 v1 的查询被拒绝；修复期间到达的请求等待其结果',
    '数据更正后：v1 → v2（增加谓词 ss_is_current = \'1\'）'],
  ['其他定义遇到相同的条件失败', '直接复用已有的验证结果与修复', '门店营业额复用电子品类的修复，45.8 毫秒'],
  ['条件不成立，无唯一修复（无候选或多个候选）', '失效，通知使用方', '重复加载后失效；智能体自行去重'],
  ['失效之后', '内置智能体再次学到相同结构的定义，通过准入检查后作为新修订发布', '—'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [3.1, 4.8, 4.233], size: 13 });
band(s, [
  { text: '重复加载后发送给使用方的通知（据系统记录整理）：', options: { bold: true, color: C.red, breakLine: true } },
  { text: '你使用过的“门店营业额”已失效：“粒度键唯一”不成立，1,099,860 行只有 989,695 个不同键（平均每键 1.11 行），'
    + '未找到能恢复唯一性的谓词；此前基于它得到的结果建议复核。' },
], { y: 5.6, h: 1.1, size: 13 });
footnote(s, SOURCE);
s.addNotes('迭代即定义修订的演化。同一指标再次学到相同结构的定义，不新增，只为原定义记录一次佐证。'
  + '同名但结构不同——实验中“门店营业额”学到了两种粒度——两条并存，检索时同时返回，由智能体依据口径说明选择。'
  + '条件不成立且存在唯一修复，旧修订失效、发布新修订，声明旧修订的查询被拒绝，修复期间到达的请求等待修复结果。'
  + '其他定义遇到相同的条件失败，直接复用已有的验证结果和修复，门店营业额只用了 45.8 毫秒。'
  + '无唯一修复则失效，并通知使用方；之后内置智能体学到新的定义，通过准入检查再作为新修订发布。');

// 14 Back to the example: the same updates with MAVRA -------------------------------------------
pres.addSection({ title: '回到例子' });
s = content('回到例子：引入 MAVRA 之后', '回到例子');
table(s, [
  ['更新', '数据库中的变化', '参考答案', '不维护（对照组）', 'MAVRA'],
  ['增量加载', '追加一批新的销售记录（新小票号），+27,095 行', '2613.9 万', good('2613.9 万 ✓'),
    lines('条件仍成立，保持 v1', '6 条定义仅执行 2 次验证', good('2613.9 万 ✓'))],
  ['数据更正', '部分销售被更正：旧行保留并标记为非当前（ss_is_current = 0），插入九折后的当前行，共 65,915 行',
    '1293.3 万', lines(bad('1430.1 万 ✗'), '新旧版本重复计入'),
    lines('v1 失效 → 修复为 v2', '（谓词 ss_is_current = \'1\'）', good('1293.3 万 ✓'))],
  ['重复加载', '4 个月的销售批次被再次加载，+110,165 行', '1307.0 万', lines(bad('2613.9 万 ✗'), '9 月重复计入'),
    lines('无唯一修复 → 失效并通知', '智能体自行去重', { text: '3 次运行中 2 次答对', options: { bold: true } })],
], { x: M, y: 1.3, w: W - 2 * M, colW: [1.45, 3.75, 1.35, 2.0, 3.583], size: 14 });
text(s, [
  { text: '三种更新 MAVRA 均检测到：', options: { bold: true, breakLine: true } },
  { text: '条件成立则继续使用；存在唯一修复则发布新修订；否则失效并通知，不向使用方返回错误答案。' },
], { x: M, y: 5.35, w: W - 2 * M, h: 1.0, fontSize: 16, valign: 'top' });
footnote(s, '对照组：仅在模式变更时使定义失效，3 次独立运行答案相同。MAVRA 栏为第 1 次运行；'
  + '增量加载与数据更正 3 次运行结果相同，重复加载见表。' + DATA);
s.addNotes('回到前面那张表，加上 MAVRA 一栏。'
  + '增量加载：定义仍然有效，MAVRA 重新验证后继续使用；6 条依赖 store_sales 的定义一共只执行了 2 次验证，其余复用。'
  + '数据更正：MAVRA 检测到“粒度键唯一”不成立，旧修订失效，找到唯一修复“只取当前行”，发布 v2，答案正确。'
  + '重复加载：没有谓词能修复，MAVRA 使定义失效并通知智能体，智能体自行去重，3 次中 2 次正确。'
  + '下一页看数据更正之后 MAVRA 的具体处理过程。');

// 15 Back to the example: what happened after the restatement ------------------------------------
s = content('数据更正之后：MAVRA 的处理过程', '回到例子');
table(s, [
  ['', '事件', '系统记录'],
  ['1', '更新后首个访问 store_sales 的请求到达。先处理名称匹配到的“电子品类门店营业额”：表版本已变，重新验证“粒度键唯一”',
    { text: [{ text: '不成立：', options: { color: C.red, bold: true } },
      { text: '“1065915 行只有 1000000 个不同键（平均每键 1.07 行）”，耗时 5.5 秒 → v1 失效' }] }],
  ['2', '在低基数列上枚举等值谓词', '仅 ss_is_current = \'1\' 能恢复键唯一且不丢失键'],
  ['3', '对该修复执行 4 项检查：静态合法性、当前快照上的粒度、SQL 审查、回归测试',
    { text: [{ text: '全部通过 → 发布 v2', options: { color: C.green, bold: true } }, { text: '（1–3 步共 28.7 秒）' }] }],
  ['4', '接着处理“门店营业额”：相同条件、相同表版本已有结果',
    { text: [{ text: '复用验证结果与修复，' }, { text: '45.8 毫秒', options: { bold: true, color: C.blue } },
      { text: '发布 v2' }] }],
  ['5', '“门店退货率”需要连接 store_sales 与 store_returns', '连接路径现在要求谓词 ss_is_current = \'1\' → 同样修复为 v2'],
  ['6', '用户智能体 B 询问“9 月门店营业额”',
    { text: [{ text: '收到 3 条通知；SQL 带上 ss_is_current = \'1\'；答 ' },
      { text: '1293.3 万 ✓', options: { color: C.green, bold: true } }, { text: '（4 轮，61.7 秒）' }] }],
], { x: M, y: 1.3, w: W - 2 * M, colW: [0.45, 5.4, 6.283], size: 14 });
footnote(s, SOURCE);
s.addNotes('数据更正之后，首个访问 store_sales 的请求到达，先处理名称匹配到的电子品类营业额。MAVRA 一验证就发现每个粒度键平均 1.07 行，旧修订失效；'
  + '随后修复搜索，只有“ss_is_current = 1”这一个谓词可行，四项检查全部通过，发布 v2，共 28.7 秒。'
  + '接着处理门店营业额：它依赖相同的条件和相同的表版本，验证结果和修复直接复用，45.8 毫秒完成。'
  + '退货率需要连接 store_sales，连接路径现在要求该谓词，也修复为 v2。最后用户智能体收到通知，按新修订写 SQL，答案正确。');

// 16 Back to the example: why the regression test uses learning-time data ---------------------------
s = content('回归测试为何以学习时刻为基准', '回到例子');
text(s, '学习任务询问的是 3 月，恰在被更正的范围内。回归测试以内置智能体学习时的 SQL 为基准，'
  + '与修复后的定义各计算一次 3 月：', { x: M, y: 1.3, w: W - 2 * M, h: 0.8, fontSize: 17, valign: 'top' });
table(s, [
  ['比较所用的数据', '学习时的 SQL', '修复后的定义（v2）', '结果'],
  ['学习时刻（as-of 查询）', '1357.0 万', '1357.0 万', good('一致 → 接受修复 ✓')],
  ['当前数据', '1489.1 万', '1342.4 万', bad('不一致 → 误拒正确的修复 ✗')],
], { x: M, y: 2.35, w: W - 2 * M, colW: [2.6, 2.6, 2.6, 4.333], size: 18, rowH: 0.65 });
band(s, [
  { text: '原因：', options: { bold: true, color: C.blue } },
  { text: '在当前数据上，学习时的 SQL 本身已经过期——它同样把更正前的旧行计入（1489.1 万）。'
    + '它仅在学习时的快照上被判定正确，因此只能在该快照上作为基准；这也是修复不需要参考答案的原因。'
    + '数据仓库通过时间旅行查询（FOR SYSTEM_TIME AS OF）提供学习时刻的数据。' },
], { y: 4.6, h: 1.6, fill: C.paleBlue, size: 16 });
footnote(s, '“当前数据”一行来自对照实验（回归测试改用当前数据，dsv41flash-r1-g3fix--exref），系统记录原文：'
  + '“结果 13423672.28 与期望 14890636.48 不一致”。');
s.addNotes('为什么回归测试不能直接用当前数据？学习任务询问的是 3 月，而这次更正恰好覆盖 3 月。'
  + '在当前数据上，学习时的 SQL 本身就会把旧版本计入，得到 1489 万；正确的新修订得到 1342 万，两者不一致，正确的修复就被拒绝了。'
  + '我们实际跑过这个对照：用当前数据比较，这个修复确实被拒绝。按学习时刻比较，两者都是 1357 万，修复被接受。'
  + '学习时的答案是唯一被确认过的答案，所以修复只与它比较，不需要另外的参考答案。数据仓库用时间旅行查询提供学习时刻的数据。');

// 17 Compared with existing approaches ---------------------------------------------------------
pres.addSection({ title: '比较与小结' });
s = content('与现有方法的比较', '比较与小结');
table(s, [
  ['', 'Text-to-SQL / 无共享定义的智能体', '检索历史查询示例', '语义层（人工维护的指标定义）', strong('MAVRA', C.blue)],
  [strong('记忆内容', C.ink), '无', '已正确回答的问题及其 SQL', '人工编写的指标定义', '表统计信息、连接路径、指标定义及其成立的条件'],
  [strong('写入方式', C.ink), '—', '答对后自动保存', '数据团队手工编写', '内置智能体学习，通过准入检查后自动发布'],
  [strong('数据更新后', C.ink), '—', '不感知，继续返回旧 SQL', '依赖人工发现与修改', '仅重新验证受影响的条件；修复为新修订或失效'],
  [strong('执行前验证', C.ink), '—', '无', '不验证数据是否仍满足定义的前提', '在查询快照上验证条件'],
  [strong('数据未变时准确率', C.ink), '49%', '100%', '—', strong('100%', C.green)],
  [strong('11 种数据更新后', C.ink), '32%', '76%', '—', strong('81%', C.green)],
  [strong('其中 5 种破坏性更新', C.ink), '19%', '57%（提示其自行验证：63%）', '—', strong('73%', C.green)],
], { x: M, y: 1.25, w: W - 2 * M, colW: [2.25, 2.4, 2.45, 2.25, 2.783], size: 14 });
footnote(s, '实验：DeepSeek V4.1 Flash，每种方法独立运行 3 次；“无共享定义”的智能体仍共享表统计信息与连接路径。'
  + '5 种破坏性更新：退货状态行、保留旧行的销售更正、重复加载、商品维度 SCD Type 2、日期键格式变更。语义层未做实验；MAVRA 的维护同样适用于语义层中声明的定义。');
s.addNotes('把几种方法放在一起比较。Text-to-SQL 或无共享定义的智能体不保留任何知识，每次重新推断口径，数据未变时准确率也只有 49%。'
  + '检索历史查询示例保存答对过的 SQL，数据未变时与 MAVRA 一样好，但数据更新后它不感知，继续返回旧 SQL；'
  + '在 5 种破坏性更新下只有 57%，提示它自行验证也只有 63%，MAVRA 是 73%。'
  + '语义层是人工编写的指标定义，数据更新后依赖人工发现和修改，执行时也不验证数据是否仍满足前提；MAVRA 的维护同样适用于语义层中声明的定义。');

// 18 Summary ------------------------------------------------------------------------------
s = pres.addSlide({ masterName: 'CLOSING', sectionTitle: '比较与小结' });
s.addText('小结', { placeholder: 'title' });
[
  ['定位', '智能体与数据库之间的记忆中间件；不生成 SQL，与 Text-to-SQL 处于不同层次'],
  ['记忆内容', '表统计信息、连接路径、指标定义，及其成立的验证条件与验证结果'],
  ['管理方式', '写入前 7 项准入检查；执行前在同一快照上验证；更新后仅重新验证受影响的条件'],
  ['迭代方式', '存在唯一修复则发布新修订；否则失效并通知；学到新证据后重新发布'],
  ['效果', '数据未变：49% → 100%，每题 5.6 轮 → 3.6 轮；数据更新后：32% → 81%'],
].forEach(([label, body], k) => {
  const y = 1.7 + k * 1.05;
  s.addShape('roundRect', { x: M, y, w: 1.8, h: 0.7, fill: { color: C.blue }, line: { color: C.blue },
    rectRadius: 0.35, objectName: `label ${label}` });
  text(s, label, { x: M, y, w: 1.8, h: 0.7, fontSize: 20, bold: true, color: C.white, align: 'center',
    valign: 'middle' });
  text(s, body, { x: M + 2.2, y: y - 0.1, w: W - 2 * M - 2.2, h: 0.9, fontSize: 19, color: C.white,
    valign: 'middle' });
});
s.addNotes('五句话收尾。定位：MAVRA 是智能体与数据库之间的记忆中间件，不生成 SQL，与 Text-to-SQL 处于不同层次。'
  + '记忆内容：表统计信息、连接路径、指标定义，及其成立的条件。管理方式：写入前准入检查，执行前在同一快照上验证，数据更新后仅重新验证受影响的条件。'
  + '迭代方式：存在唯一修复则发布新修订，否则失效并通知。效果：数据未变时准确率从 49% 到 100%、轮数更少；数据更新后从 32% 到 81%。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
