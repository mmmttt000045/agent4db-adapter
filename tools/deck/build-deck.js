// Builds docs/mavra-system.pptx, a Chinese deck that presents MAVRA as a memory middleware
// between data agents and the database: how it differs from Text-to-SQL, what the memory
// holds, how it is written, read, used, maintained and revised, then one real example from
// the end-to-end study (store revenue under three everyday writes). The three system figures
// come from tools/deck/figures/ (drawn by `python3 tools/figures/build.py --deck`, rendered to
// PNG). Every number on the slides comes from the archived run records.
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
const DATA = '数据为仿 TPC-DS 的合成零售数据（100 万行门店销售），题目中的年份略去。';
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
s.addText('记住智能体学到的东西 · 共享给所有智能体 · 数据变了也保持正确', { placeholder: 'body' });
s.addNotes('MAVRA 是放在数据智能体和数据库之间的一个中间件。一句话概括它做的事：'
  + '把智能体探索数据库时学到的东西记下来，共享给其他智能体用，并在数据变化时保证这些记忆仍然正确——能修就修成新版本，修不了就停用。'
  + '先讲它和 Text-to-SQL 的区别，再讲记忆里存什么、怎么管理，最后用实验里的一个真实例子走一遍。');

// 2 Text-to-SQL vs MAVRA --------------------------------------------------------------
pres.addSection({ title: '问题' });
s = content('Text-to-SQL 和 MAVRA 解决的不是同一个问题', '问题');
const half = (W - 2 * M - 0.4) / 2;
[
  { x: M, tag: 'Text-to-SQL', head: '把一句话翻译成一条 SQL', color: C.muted, pale: C.grey, rows: [
    ['输入', '问题 + 表结构（可附几条示例 SQL）'],
    ['输出', '一条 SQL'],
    ['状态', '每个问题从头做，做完就忘'],
    ['关心', '这一条 SQL 写得对不对'],
  ] },
  { x: M + half + 0.4, tag: 'MAVRA', head: '智能体和数据库之间的记忆中间件', color: C.blue, pale: C.paleBlue, rows: [
    ['位置', '智能体对数据库的每个请求都经过它'],
    ['记住', '智能体学到的、关于这个库的知识'],
    ['共享', '一个智能体学会，所有智能体都能用'],
    ['关心', '记住的东西现在还对不对'],
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
  { text: '两者是上下游关系：', options: { bold: true, color: C.blue } },
  { text: 'Text-to-SQL 模型或任何数据智能体，都可以作为“用户智能体”接在 MAVRA 上面。'
    + 'MAVRA 不替它写 SQL，而是给它经过校验的记忆，并在 SQL 执行前把关。' },
], { y: 5.2, h: 1.35, fill: C.paleAmber, size: 17 });
s.addNotes('Text-to-SQL 研究的是翻译：给一句自然语言问题和表结构，生成一条 SQL，评价这条 SQL 对不对。'
  + '每个问题都是独立的，做完不留下任何东西。'
  + 'MAVRA 不是一个新的 Text-to-SQL 方法，它不生成 SQL。它在智能体下面、数据库上面，智能体对数据库的请求都经过它。'
  + '它关心的是另一个问题：智能体探索数据库时学到的知识——“营业额是哪一列”“这两张表怎么关联”——怎么记下来、怎么共享、数据变了之后还对不对。'
  + '所以两者是上下游关系，任何 Text-to-SQL 模型都可以作为用户智能体接在 MAVRA 上。');

// 3 Real record: the same question without shared memory -------------------------------
s = content('真实记录：不共享记忆，同一个问题问三次', '问题');
text(s, [
  { text: '题目：“9 月的门店营业额是多少？保留两位小数。”', options: { bold: true } },
  { text: '只说名称，不给口径。正确答案 1307.0 万。' },
], { x: M, y: 1.2, w: W - 2 * M, h: 0.5, fontSize: 17, valign: 'middle' });
table(s, [
  ['', '智能体选的列', '答案', '轮数', '输入 token'],
  ['不共享记忆 · 第 1 次', sub('ss_ext_sales_price', '折扣前的销售额', false), bad('1413.8 万 ✗'), '5', '10,957'],
  ['不共享记忆 · 第 2 次', sub('ss_ext_sales_price', '折扣前的销售额', false), bad('1413.8 万 ✗'), '5', '11,212'],
  ['不共享记忆 · 第 3 次', sub('ss_net_paid', '净支付额', false), good('1307.0 万 ✓'), '5', '10,440'],
  [strong('有 MAVRA · 3 次结果相同', C.blue), sub('ss_net_paid', '查记忆，拿到“门店营业额”的定义', false),
    good('1307.0 万 ✓'), '3', '8,467 – 8,824'],
], { x: M, y: 1.8, w: W - 2 * M, colW: [3.0, 4.3, 1.9, 1.0, 1.933], size: 14 });
band(s, bulleted('错的不是 SQL 语法，是业务知识', C.blue, [
  '销售表里像“营业额”的列有好几个：ss_ext_sales_price、ss_net_paid、ss_net_paid_inc_tax……选哪一列是业务口径，表结构里没写',
  'Text-to-SQL 和不共享记忆的智能体每次重新猜，同一个问题答案会变',
  '把学到的口径记下来、大家照着用：15 道题 × 3 次运行，数据不变时不共享只答对 49%，共享后 100%；每题从 5.6 轮降到 3.6 轮，输入 token 少 34%',
]), { y: 4.95, h: 1.8, size: 14 });
footnote(s, '记录：noctis results/scen-20261002，留出题 M1-P1；不共享（不共享指标定义）：dsv41flash-r1-a、r2-b、r3-a；'
  + 'MAVRA：r1–r3-g3fix--snap。合成零售数据，年份略去。');
s.addNotes('这是实验里的真实记录。题目只说“门店营业额”，不给口径。'
  + '不共享记忆的智能体独立跑了三次：两次选了折扣前的销售额 ss_ext_sales_price，答 1413.8 万，错；一次选了净支付额 ss_net_paid，答对。每次都是 5 轮。'
  + '有 MAVRA 的智能体先查记忆，拿到内置智能体学过的“门店营业额”定义，三次都选对，3 轮完成。'
  + '难点不在 SQL 语法，而在业务知识：表里好几列都像营业额，选哪一列是口径问题，表结构里没写。'
  + 'Text-to-SQL 每次都要重新猜，结果会变；把学到的口径记下来共享，准确率和成本都改善。');

// 4 The problem: memory goes stale ------------------------------------------------------
s = content('记住了还不够：数据一变，记忆可能悄悄过期', '问题');
text(s, '“门店营业额”记下来以后，数据库照常写入。之后再问“9 月门店营业额”，照旧用记住的定义：',
  { x: M, y: 1.2, w: W - 2 * M, h: 0.45, fontSize: 16, color: C.muted, valign: 'middle' });
table(s, [
  ['写入', '数据库里发生了什么', '正确答案', '照旧用记住的定义'],
  ['追加新数据', '把 9 月的销售复制一份、换新小票号，+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '部分销售被更正：旧行保留并标为非当前（ss_is_current = 0），新增九折的当前行，共 65,915 行',
    '1293.3 万', lines(bad('1430.1 万 ✗'), '新旧两版都算了')],
  ['重复装载', '4 个月的销售整批又装载了一次，+110,165 行', '1307.0 万', lines(bad('2613.9 万 ✗'), '9 月翻倍')],
], { x: M, y: 1.8, w: W - 2 * M, colW: [1.6, 5.4, 1.6, 3.533], size: 15 });
band(s, bulleted('问题在哪', C.red, [
  '三种写入都是普通的 INSERT / UPDATE，表结构没变：只看表结构的做法发现不了',
  'SQL 照样能跑、不报错：用这条记忆的智能体自己看不出来',
  '记忆被共享：一处过期，所有用它的智能体一起算错',
]), { y: 4.75, h: 1.85, size: 17 });
footnote(s, '“照旧用”即对照组：只在表结构变化时才让定义失效，3 次独立运行答案相同。' + DATA);
s.addNotes('共享记忆带来新问题：记忆是在某一份数据上学到的，数据会变。同一个问题“9 月门店营业额”，在三种日常写入之后分别再问一次，照旧用记住的定义。'
  + '追加新数据没问题。数据更正——数据仓库里常见的做法是旧行不删、标成非当前，再插一行新的——照旧用就会把新旧两版都加进去，多出 137 万。'
  + '重复装载，一批数据被导了两次，9 月直接翻倍。'
  + '这三种都是普通的写入，表结构没变，只看表结构的做法完全发现不了；SQL 也不报错。'
  + '所以 MAVRA 不只是“记下来”，更要管理记忆：知道每条记忆在什么前提下成立，数据变了重新检查。');

// 5 What MAVRA is: tools in front, memory management behind -----------------------------
pres.addSection({ title: 'MAVRA 是什么' });
s = content('MAVRA 是什么：智能体看到的是工具，背后是记忆管理', 'MAVRA 是什么');
table(s, [
  ['智能体调用', 'MAVRA 在背后做什么', '用到的记忆'],
  [sub('列出表', 'list_tables'), '返回表名、行数和注释', '—'],
  [sub('查看一张表', 'describe_table'), '数据没变：直接返回记住的表画像；变了：重新探查并记下', '表画像'],
  [sub('问两张表怎么关联', 'join_path'),
    '返回验证过的关联列、一对多关系、需要的过滤、关联不上的比例，以及试过但不对的写法', '关联路径'],
  [sub('按名称查指标定义', 'find_metric'),
    '依赖的表有写入：先重新校验；再返回有效版本、注意事项和示例 SQL', '指标定义、校验结果'],
  [sub('执行 SQL，注明用了哪条定义的哪一版', 'run_sql'),
    '版本已停用或已有新版：拒绝；否则在本次查询的快照上校验，再执行', '指标定义、校验结果'],
  ['每次返回', '附上提醒：你用过的记忆被停用或修复了', '使用记录'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [3.4, 6.5, 2.233], size: 14 });
band(s, [
  { text: '记忆从哪来：', options: { bold: true, color: C.violet } },
  { text: '内置智能体（大模型）专门回答给出口径的学习题，答对的解题过程被抽取成指标定义，通过 7 项校验才写进记忆；'
    + '用户智能体查过的表、验证过的关联也会记下来，所有智能体共用。' },
], { y: 5.65, h: 1.05, fill: C.paleViolet, size: 15 });
s.addNotes('从用户智能体的角度看，MAVRA 就是一组数据库工具：列出表、查看表、问两张表怎么关联、查指标定义、执行 SQL。'
  + '区别在背后：每个工具都先查记忆。查看表时，数据没变就直接返回记住的表画像；问关联时，返回以前验证过的关联方式和踩过的坑；'
  + '查指标定义时，如果依赖的表有写入，先重新校验再返回。'
  + '执行 SQL 时，智能体注明用了哪条定义的哪一版，过期的版本直接拒绝。每次返回还会附带提醒，告诉智能体它用过的记忆有变化。'
  + '记忆来自两处：内置智能体专门学习指标定义，用户智能体在探索中查过、验证过的东西也会记下来。');

// 6 Structure ------------------------------------------------------------------------------
s = content('系统结构：请求怎样经过 MAVRA', 'MAVRA 是什么');
figure(s, 'overview');
s.addNotes('左边是用户智能体，它发两种请求。'
  + '蓝色 1–5 是查询指标定义：智能体只说“营业额”，查询服务从共享记忆里读出定义；'
  + '销售表的数据变了，某条规则在新数据版本上还没有校验结果，就交给维护去校验，结果写入缓存，再返回有效的 v2。'
  + '橙色 6–8 是执行 SQL：智能体写好 SQL 并注明用的是 v2，执行前校验复用缓存里的结果，在同一快照上执行。'
  + '紫色是学习：内置智能体学到的定义，发布前校验通过才写进共享记忆。共享记忆里还有表画像和关联路径，图里没有展开。');

// 7 What the memory holds -------------------------------------------------------------------
s = content('记忆里存什么', 'MAVRA 是什么');
table(s, [
  ['记忆', '记了什么', '例子（门店营业额）', '数据变了怎么办'],
  [strong('表画像', C.blue), '列、类型、空值比例、不同值个数、常见取值、3 行样例', 'store_sales 每一列的情况',
    '表有写入：下次查看时重新探查'],
  [strong('关联路径', C.blue), '关联列、一对多关系、需要的过滤、关联不上的比例、试过但不对的写法',
    'store_sales → date_dim：ss_sold_date_sk = d_date_sk，多对一，1.03% 的销售关联不上',
    '任一张表有写入：重新校验“一”那一侧的键仍唯一'],
  [strong('指标定义', C.blue), '口径、计算、粒度、日期、注意事项、示例 SQL，以及校验规则',
    '门店营业额 v1：SUM(ss_net_paid)，每笔销售一行', '依赖的表有写入：重新校验规则；不成立就修复或停用'],
  [strong('校验结果', C.blue), '哪条规则、在哪个数据版本上、成立与否', '“每笔销售一行”在 store_sales 第 15 版上成立',
    '按（规则，数据版本）存：版本变了就算新的一条，所有记忆共用'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [1.45, 3.6, 3.9, 3.183], size: 14 });
band(s, [
  { text: '每条记忆都带着：', options: { bold: true, color: C.blue } },
  { text: '依赖哪些表的哪个数据版本、状态（有效 / 待校验 / 停用）、版本号、谁写的、谁用过。', options: { breakLine: true } },
  { text: '第 1 次运行结束时共 70 条记忆，被查 995 次，其中 696 次直接复用。' },
], { y: 5.0, h: 1.15, size: 15 });
footnote(s, SOURCE);
s.addNotes('记忆有四类。表画像是查看表时得到的列信息；关联路径是验证过的两表关联方式，包括一对多关系、需要加的过滤、有多少行关联不上，还有试过但证明不对的写法。'
  + '指标定义是最重要的一类：口径、怎么算、一行代表什么、按哪个日期归期，再加上它成立所依赖的校验规则。'
  + '校验结果按“规则 + 数据版本”存，同一条规则在同一个数据版本上只校验一次，所有记忆共用。'
  + '每条记忆都记着依赖哪些表的哪个版本、当前状态、版本号、谁写的、谁用过。实验第一次运行结束时一共 70 条记忆，被查了 995 次，696 次直接复用。');

// 8 One definition in full -------------------------------------------------------------------
s = content('一条指标定义记忆的全部内容（实验记录）', 'MAVRA 是什么');
const tw2 = (W - 2 * M - 0.3) / 2;
text(s, '给智能体看的（查询时返回）', { x: M, y: 1.2, w: tw2, h: 0.4, fontSize: 16, bold: true, color: C.blue });
table(s, [
  ['字段', '内容'],
  ['名称', '门店营业额（别名：门店销售净额、store revenue）'],
  ['口径', '门店销售明细行净支付额（销售额 − 折扣，不含税）之和，按销售日期归属期间'],
  ['计算', 'store_sales 上 SUM(ss_net_paid)，无过滤'],
  ['粒度', '销售日 + 小票号 + 商品：每笔销售一行'],
  ['日期', 'ss_sold_date_sk 关联 date_dim，按销售日'],
  ['注意事项', '① 内连接日期表会排除约 1.03% 关联不上的销售；② 用不含税的 ss_net_paid，不要和含税的 ss_net_paid_inc_tax 混用'],
  ['示例', '学习题和当时的 SQL'],
], { x: M, y: 1.65, w: tw2, colW: [1.25, tw2 - 1.25], size: 13 });
const xr = M + tw2 + 0.3;
text(s, 'MAVRA 自己管理的', { x: xr, y: 1.2, w: tw2, h: 0.4, fontSize: 16, bold: true, color: C.violet });
table(s, [
  ['字段', '内容'],
  ['依据', '学习题给出的口径（M1-L1）'],
  ['证据', '学习时的 SQL、答案 13,570,368.70、当时的数据版本；7 项发布前校验全部通过'],
  ['校验规则', '每笔销售一行；日期键唯一；丢行率不超标（学习时 1.03%）'],
  ['依赖', 'store_sales、date_dim 的数据版本'],
  ['状态', '有效，v1'],
  ['写入 / 使用', '内置智能体 A 写入；A、B 用过，被查 9 次'],
], { x: xr, y: 1.65, w: tw2, colW: [1.35, tw2 - 1.35], size: 13 });
band(s, [
  { text: '左边告诉智能体“怎么算”，右边让 MAVRA 判断“现在还能不能这么算”。', options: { bold: true, color: C.blue } },
  { text: 'Text-to-SQL 生成的 SQL 用完就丢，也不知道它在什么前提下成立。' },
], { y: 5.75, h: 0.95, fill: C.paleBlue, size: 15 });
footnote(s, SOURCE);
s.addNotes('这是实验里“门店营业额”这条记忆的原样内容。左边是用户智能体查询时拿到的：名称和别名、口径、怎么算、一行代表什么、按哪个日期归期、注意事项和示例。'
  + '右边是 MAVRA 自己管理、用来保证它仍然正确的：依据是什么、学习时的证据、校验规则、依赖哪些表的哪个版本、当前状态和版本号、谁写的谁用过。'
  + 'Text-to-SQL 里没有这样的东西：每次生成的 SQL 用完就丢，也不知道它在什么前提下成立。');

// 9 Five steps of memory management ----------------------------------------------------------
pres.addSection({ title: '记忆管理' });
s = content('记忆管理的五个环节', '记忆管理');
table(s, [
  ['环节', '什么时候', 'MAVRA 做什么', '门店营业额的记录'],
  [strong('写入', C.violet), '内置智能体答对一道学习题', '抽取成定义，过 7 项发布前校验，通过才发布', '发布 v1：抽取 16.3 秒，校验 5.7 秒'],
  [strong('读取', C.blue), '用户智能体按名称查', '依赖的表没变：直接返回；有写入：先维护再返回', '问 9 月营业额：查到 v1，3 轮答对'],
  [strong('使用', C.amber), '用户智能体执行 SQL，注明所用版本', '过期版本拒绝；在本次查询的快照上校验，再执行', 'SQL 注明“门店营业额 v1”'],
  [strong('维护', C.blue), '数据写入后，记忆第一次被用到时', '只重新校验受影响的规则；结果按（规则，数据版本）缓存共用',
    '追加新数据后：6 条定义只真正跑了 2 次校验'],
  [strong('迭代', C.blue), '某条规则不成立', '能唯一修好：发布 v2；修不了：停用并提醒；以后学到新证据再发布',
    '数据更正：v1 → v2；重复装载：停用'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [1.2, 3.0, 4.6, 3.333], size: 15 });
band(s, [
  { text: '和 Text-to-SQL 的区别就在这里：', options: { bold: true, color: C.blue } },
  { text: '这五个环节都发生在“生成一条 SQL”之外，跨问题、跨智能体、跨数据版本。' },
], { y: 5.75, h: 0.9, fill: C.paleBlue, size: 16 });
footnote(s, SOURCE);
s.addNotes('记忆管理分五个环节，颜色和后面两张图一致。'
  + '写入：内置智能体答对学习题，抽取成定义，过 7 项校验才发布。读取：用户智能体按名称查，依赖的表没变就直接返回，有写入就先维护。'
  + '使用：执行 SQL 时注明版本，过期的拒绝，在本次查询的快照上校验后再执行。'
  + '维护：数据写入后，记忆第一次被用到时，只重新校验受影响的规则，结果缓存共用——追加新数据后，6 条依赖销售表的定义只真正跑了 2 次校验。'
  + '迭代：规则不成立时，能唯一修好就发布新版本，修不了就停用并提醒。'
  + '这些都发生在“生成一条 SQL”之外，这就是和 Text-to-SQL 的区别。');

// 10 Writing: from one solved task to one memory -------------------------------------------
s = content('写入：从一次解题到一条记忆', '记忆管理');
const lw = 5.6;
text(s, '学习题', { x: M, y: 1.2, w: lw, h: 0.4, fontSize: 16, bold: true, color: C.violet });
s.addShape('roundRect', { x: M, y: 1.65, w: lw, h: 1.25, fill: { color: C.paleViolet },
  line: { color: C.paleViolet }, rectRadius: 0.08 });
text(s, '3 月的门店营业额是多少？口径：门店营业额 = 门店销售行的净支付额（store_sales.ss_net_paid）之和，'
  + '按销售日期归属期间。保留两位小数。', { x: M + 0.2, y: 1.75, w: lw - 0.4, h: 1.05, fontSize: 15, valign: 'middle' });
text(s, '内置智能体：5 轮、7 次工具调用、9.5 秒，最后的 SQL', { x: M, y: 3.05, w: lw, h: 0.35,
  fontSize: 14, color: C.muted });
s.addShape('roundRect', { x: M, y: 3.45, w: lw, h: 1.55, fill: { color: C.grey }, line: { color: C.grey },
  rectRadius: 0.08 });
text(s, 'SELECT ROUND(SUM(ss.ss_net_paid), 2)\nFROM store_sales ss\nJOIN date_dim d\n  ON ss.ss_sold_date_sk = d.d_date_sk\nWHERE d.d_year = … AND d.d_moy = 3',
  { x: M + 0.2, y: 3.52, w: lw - 0.4, h: 1.4, fontSize: 13, fontFace: CODE, valign: 'middle' });
text(s, [
  { text: '答案 13,570,368.70，与参考答案一致 ✓', options: { bold: true, color: C.green, breakLine: true } },
  { text: '大模型把解题过程抽取成定义（16.3 秒）；7 项校验全部通过（5 条查询，5.7 秒），发布为 v1。' },
], { x: M, y: 5.15, w: lw, h: 1.2, fontSize: 15, valign: 'top' });
const rx = M + lw + 0.35, rw = W - M - rx;
text(s, '发布前的 7 项校验', { x: rx, y: 1.2, w: rw, h: 0.4, fontSize: 16, bold: true, color: C.violet });
table(s, [
  ['校验', '防的是什么'],
  ['1 有口径依据', '题目明确给出了业务口径，不是猜的'],
  ['2 答案核验正确', '错误答案不进记忆'],
  ['3 字段合法', '列存在；计算只用允许的列；关联走验证过的路径；没把题目里的月份写死'],
  ['4 粒度成立', '在当前数据上“每笔销售一行”成立'],
  ['5 SQL 审查', '示例 SQL 符合记下的粒度和关联要求'],
  ['6 重放当初的 SQL', '再跑一次，答案相同'],
  ['7 重放标准 SQL', '按定义字段生成的 SQL 也得到同样答案：别的智能体读到的就是这些字段'],
], { x: rx, y: 1.65, w: rw, colW: [2.15, rw - 2.15], size: 13 });
band(s, [
  { text: '第 2 项在实际部署中：', options: { bold: true, color: C.violet } },
  { text: '实验用题目的参考答案；部署时由指标负责人确认一次，或与已发布的报表对账。之后的维护和修复都不再需要参考答案。' },
], { x: rx, y: 5.3, w: rw, h: 1.3, fill: C.paleViolet, size: 13 });
footnote(s, SOURCE);
s.addNotes('写入是记忆的入口。内置智能体拿到一道给出口径的学习题，5 轮写出 SQL，答案正确。'
  + '然后大模型把解题过程抽取成一条结构化的定义，再过 7 项校验：有口径依据、答案正确、字段合法、粒度成立、SQL 审查，以及两次重放——'
  + '当初的 SQL 再跑一次答案相同，按定义字段生成的标准 SQL 也得到相同答案。最后一项最关键，因为别的智能体读到的就是这些字段，漏一个过滤或者写死月份都会在这里被发现。'
  + '第 2 项“答案正确”在实验里用题目的参考答案；实际部署中是指标负责人确认一次，或者与已发布的报表对账。这只在写入时需要一次，之后的维护和修复都不需要参考答案。');

// 11 Reading and using -------------------------------------------------------------------------
s = content('读取与使用：一次请求怎么走', '记忆管理');
figure(s, 'lookup');
s.addNotes('上面一行是查询指标定义：按名称匹配到“门店营业额”（“电子品类门店营业额”也包含这几个字，一并返回，由智能体按口径说明挑选）；'
  + '再看销售表的数据版本有没有变（14 变成 15）；然后逐条规则查缓存：“每笔销售一行”电子品类那个指标刚校验过，直接复用；'
  + '日期表没变，复用；“丢行率不超标”在 15 上没有结果，现在校验并写入缓存；最后返回有效的 v2。'
  + '中间是校验结果缓存：按（规则，数据版本）存，表里写明谁写入、哪一步复用。'
  + '下面一行是执行 SQL：先检查注明的 v2 能不能用；再在这条查询的快照上校验——这期间又有写入，数据版本变成 16，'
  + '所以两条规则在快照里重新校验并写入缓存；最后在同一快照上执行。');

// 12 Maintenance and revision ---------------------------------------------------------------
s = content('维护与迭代：一条记忆的一生', '记忆管理');
figure(s, 'lifecycle');
s.addNotes('跟着门店营业额走一遍。内置智能体回答“3 月门店营业额”，答案核验正确、发布前校验通过，发布 v1。'
  + '之后追加一批新销售：规则仍成立，其他指标直接复用结果，还是 v1。'
  + '再之后有一批销售被更正：旧行保留但标成非当前，新增当前行——“每笔销售一行”不成立，v1 停用，不处理会把新旧两版都算进去。'
  + '修复时在取值少的列上试过滤，只有“只算当前行”可行；用学习时的数据重算 3 月，结果一致，发布 v2。'
  + '红框是另一种情况：一批销售被重复装载，没有任何过滤能修好，就停用并提醒，等待重新学习。');

// 13 Revision rules -------------------------------------------------------------------------
s = content('迭代：记忆的版本怎么变', '记忆管理');
table(s, [
  ['情况', 'MAVRA 怎么做', '实验记录'],
  ['同一指标又学到一次，算法相同', '不新增，给原记忆记一次佐证', '—'],
  ['同名，但算法不同', '两条并存；查询时都返回，由智能体按口径说明挑选',
    '“门店营业额”有两条：粒度一条含销售日，一条不含'],
  ['规则不成立，只有一种修法', '停用 v1，修复后发布 v2；注明 v1 的 SQL 被拒绝；修复期间来的请求等结果',
    '数据更正后：v1 → v2（加 ss_is_current = \'1\'）'],
  ['别的记忆遇到同样的问题', '直接复用已有的校验结果和修复', '门店营业额复用电子品类的修复，45.8 毫秒'],
  ['规则不成立，修不好（没有或不止一种修法）', '停用，提醒用过它的智能体', '重复装载后停用，智能体自己去重'],
  ['停用之后', '内置智能体再学到同样算法的解题过程，校验通过后作为新版本发布', '—'],
], { x: M, y: 1.25, w: W - 2 * M, colW: [3.1, 4.8, 4.233], size: 13 });
band(s, [
  { text: '重复装载后的提醒（据系统记录）：', options: { bold: true, color: C.red, breakLine: true } },
  { text: '你用过的“门店营业额”已停用：“每笔销售一行”不成立，1,099,860 行只有 989,695 个不同键（平均每键 1.11 行），'
    + '没有找到能恢复的过滤；之前基于它得到的结果建议复核。' },
], { y: 5.6, h: 1.1, size: 13 });
footnote(s, SOURCE);
s.addNotes('迭代就是记忆的版本怎么变。同一个指标又学到一次、算法一样，就不新增，只给原来那条记一次佐证。'
  + '名字一样但算法不同——实验里“门店营业额”学到了两种粒度——两条并存，查询时都返回，智能体按口径说明挑。'
  + '规则不成立而且只有一种修法，就停用旧版本、发布新版本，注明旧版本的 SQL 会被拒绝，修复期间来的请求等修复结果。'
  + '别的记忆碰到同样的问题，直接复用已有的结果和修复，门店营业额只用了 45.8 毫秒。'
  + '修不好就停用，并提醒用过它的智能体；之后内置智能体学到新的解题过程，校验通过再作为新版本发布。');

// 14 Back to the example: the same writes with MAVRA -------------------------------------------
pres.addSection({ title: '回到例子' });
s = content('回到例子：有了 MAVRA 之后', '回到例子');
table(s, [
  ['写入', '数据库里发生了什么', '正确答案', '不维护（对照组）', 'MAVRA'],
  ['追加新数据', '把 9 月的销售复制一份、换新小票号，+27,095 行', '2613.9 万', good('2613.9 万 ✓'),
    lines('规则仍成立，保持 v1', '6 条定义只跑了 2 次校验', good('2613.9 万 ✓'))],
  ['数据更正', '部分销售被更正：旧行保留并标为非当前（ss_is_current = 0），新增九折的当前行，共 65,915 行',
    '1293.3 万', lines(bad('1430.1 万 ✗'), '新旧两版都算了'),
    lines('停用 v1 → 修复为 v2', '（只算 ss_is_current = \'1\'）', good('1293.3 万 ✓'))],
  ['重复装载', '4 个月的销售整批又装载了一次，+110,165 行', '1307.0 万', lines(bad('2613.9 万 ✗'), '9 月翻倍'),
    lines('找不到修复 → 停用并提醒', '智能体自己去重', { text: '3 次运行中 2 次答对', options: { bold: true } })],
], { x: M, y: 1.3, w: W - 2 * M, colW: [1.45, 3.75, 1.35, 2.0, 3.583], size: 14 });
text(s, [
  { text: '同样三种写入，MAVRA 都发现了：', options: { bold: true, breakLine: true } },
  { text: '规则仍成立就继续用；能唯一修好就发布新版本；修不了就停用并提醒，不让错误答案悄悄出去。' },
], { x: M, y: 5.35, w: W - 2 * M, h: 1.0, fontSize: 16, valign: 'top' });
footnote(s, '对照组：只在表结构变化时才让定义失效，3 次独立运行答案相同。MAVRA 栏为第 1 次运行；'
  + '追加和更正 3 次运行结果相同，重复装载见表。' + DATA);
s.addNotes('回到开头那张表，加上 MAVRA 这一栏。'
  + '追加新数据：定义仍然对，MAVRA 重新校验后继续用；6 条依赖销售表的定义一共只跑了 2 次校验，其余直接复用。'
  + '数据更正：MAVRA 发现“每笔销售一行”不成立，停用旧定义，找到唯一的修复“只算当前行”，发布 v2，答对。'
  + '重复装载：没法用过滤修好，MAVRA 停用并提醒智能体，智能体自己去重，3 次里 2 次答对。'
  + '下一页看数据更正之后，MAVRA 具体一步步做了什么。');

// 15 Back to the example: what happened after the restatement ------------------------------------
s = content('数据更正之后，MAVRA 依次做了什么', '回到例子');
table(s, [
  ['', '发生了什么', '系统记录'],
  ['1', '第一个用到销售表的查询到来。先检查名称匹配到的“电子品类门店营业额”：销售表变了，重新校验“每笔销售一行”',
    { text: [{ text: '不成立：', options: { color: C.red, bold: true } },
      { text: '“1065915 行只有 1000000 个不同键（平均每键 1.07 行）”，用时 5.5 秒 → 停用 v1' }] }],
  ['2', '在取值少的列上逐个试过滤', '只有 ss_is_current = \'1\' 能做到每笔一行、一笔不少'],
  ['3', '对这个修复做 4 项检查：合法性、当前数据上的粒度、SQL 审查、回归测试',
    { text: [{ text: '全部通过 → 发布 v2', options: { color: C.green, bold: true } }, { text: '（1–3 步共 28.7 秒）' }] }],
  ['4', '接着检查“门店营业额”：同一条规则、同一个数据版本已经有结果',
    { text: [{ text: '复用校验结果和修复，' }, { text: '45.8 毫秒', options: { bold: true, color: C.blue } },
      { text: '就发布了 v2' }] }],
  ['5', '“门店退货率”要把销售和退货关联起来', '关联路径现在要求只用当前行 → 也修复为 v2'],
  ['6', '用户智能体 B 问“9 月门店营业额”',
    { text: [{ text: '收到 3 条提醒；SQL 带上 ss_is_current = \'1\'；答 ' },
      { text: '1293.3 万 ✓', options: { color: C.green, bold: true } }, { text: '（4 轮，61.7 秒）' }] }],
], { x: M, y: 1.3, w: W - 2 * M, colW: [0.45, 5.4, 6.283], size: 14 });
footnote(s, SOURCE);
s.addNotes('数据更正之后，第一个用到销售表的查询到来，先检查名称匹配到的电子品类营业额。MAVRA 一校验就发现每个销售键平均有 1.07 行，停用旧定义；'
  + '然后自动找修复，只有“只算当前行”这一个过滤可行，四项检查都过了，发布 v2，一共 28.7 秒。'
  + '接着检查门店营业额：它依赖的是同一条规则、同一个数据版本，结果和修复都直接复用，45.8 毫秒就好了。'
  + '退货率因为要关联销售表，也跟着修好。最后用户智能体收到提醒，按新定义写 SQL，答对。');

// 16 Back to the example: why the regression test uses learning-time data ---------------------------
s = content('回归测试为什么要用学习时的数据', '回到例子');
text(s, '学习题问的是 3 月，正好在被更正的范围里。回归测试拿内置智能体当初的 SQL 当标准，'
  + '和加了过滤的新定义各算一次 3 月：', { x: M, y: 1.3, w: W - 2 * M, h: 0.8, fontSize: 17, valign: 'top' });
table(s, [
  ['用哪份数据比', '当初的 SQL', '新定义（v2）', '结果'],
  ['学习时的数据', '1357.0 万', '1357.0 万', good('一致 → 接受修复 ✓')],
  ['现在的数据', '1489.1 万', '1342.4 万', bad('不一致 → 拒绝了正确的修复 ✗')],
], { x: M, y: 2.35, w: W - 2 * M, colW: [2.6, 2.6, 2.6, 4.333], size: 18, rowH: 0.65 });
band(s, [
  { text: '原因：', options: { bold: true, color: C.blue } },
  { text: '在现在的数据里，当初的 SQL 自己也过时了——它把更正前的旧行也算了进去（1489.1 万）。'
    + '它只在学习时的数据上被核验过是对的，所以只能在那份数据上当标准。这也是修复不需要参考答案的原因。' },
], { y: 4.6, h: 1.6, fill: C.paleBlue, size: 17 });
footnote(s, '“现在的数据”一行来自对照实验（回归测试改用当前数据，dsv41flash-r1-g3fix--exref），系统记录原文：'
  + '“结果 13423672.28 与期望 14890636.48 不一致”。');
s.addNotes('为什么回归测试不能直接用现在的数据？学习题问的是 3 月，而这次更正正好覆盖 3 月。'
  + '在现在的数据上，智能体当初写的 SQL 本身就会把旧版本也算进去，得到 1489 万；正确的新定义得到 1342 万，两者对不上，正确的修复就被拒了。'
  + '我们实际跑过这个对照：用现在的数据比，这个修复确实被拒绝。用学习时的数据比，两者都是 1357 万，修复被接受。'
  + '学习时的答案是唯一被确认过的答案，所以修复只和它比，不需要另外的参考答案。');

// 17 Compared with existing approaches ---------------------------------------------------------
pres.addSection({ title: '比较与小结' });
s = content('和已有做法比', '比较与小结');
table(s, [
  ['', 'Text-to-SQL / 不共享记忆的智能体', '检索历史 SQL 示例', '语义层（人工定义指标）', strong('MAVRA', C.blue)],
  [strong('记住什么', C.ink), '不记', '答对过的问题和当时的 SQL', '人写好的指标定义', '表画像、关联路径、指标定义，以及它们成立的前提'],
  [strong('谁来写', C.ink), '—', '答对后自动保存', '数据团队手写', '内置智能体学习，校验通过后自动发布'],
  [strong('数据变了', C.ink), '—', '不知道，照旧给出旧 SQL', '靠人发现、人改', '只重验受影响的规则；修复为新版本或停用'],
  [strong('执行前检查', C.ink), '—', '不检查', '不检查数据是否仍满足前提', '在本次查询的快照上校验'],
  [strong('数据不变时答对', C.ink), '49%', '100%', '—', strong('100%', C.green)],
  [strong('11 种数据变化后答对', C.ink), '32%', '76%', '—', strong('81%', C.green)],
  [strong('其中 5 种破坏性变化', C.ink), '19%', '57%（提示它自己核对：63%）', '—', strong('73%', C.green)],
], { x: M, y: 1.25, w: W - 2 * M, colW: [2.25, 2.4, 2.45, 2.25, 2.783], size: 14 });
footnote(s, '实验：DeepSeek V4.1 Flash，每种做法独立运行 3 次；“不共享记忆”为不共享指标定义的智能体。'
  + '5 种破坏性变化：退货状态行、销售更正（保留旧行）、重复装载、商品维表拉链、日期键换格式。语义层没有做实验。');
s.addNotes('把几种做法放在一起比。Text-to-SQL 或不共享记忆的智能体什么都不记，每次重新猜口径，数据不变时也只答对 49%。'
  + '检索历史 SQL 示例会记下答对过的 SQL，数据不变时和 MAVRA 一样好，但数据变了它不知道，照旧给出旧 SQL；'
  + '在 5 种破坏性变化下只答对 57%，提示它自己去核对也只有 63%，MAVRA 是 73%。'
  + '语义层是人写的指标定义，数据变了靠人发现、人改，执行时也不检查数据是否还满足前提；MAVRA 的维护同样可以用在语义层的定义上。');

// 18 Summary ------------------------------------------------------------------------------
s = pres.addSlide({ masterName: 'CLOSING', sectionTitle: '比较与小结' });
s.addText('小结', { placeholder: 'title' });
[
  ['定位', '数据智能体与数据库之间的记忆中间件；不生成 SQL，和 Text-to-SQL 是上下游'],
  ['记什么', '表画像、关联路径、指标定义，以及它们成立的前提（校验规则）和校验结果'],
  ['怎么管', '写入前 7 项校验；执行前在同一快照上校验；数据变了只重验受影响的规则'],
  ['怎么迭代', '能唯一修好就发布新版本，修不了就停用并提醒，学到新证据再发布'],
  ['效果', '数据不变：49% → 100%，每题 5.6 轮 → 3.6 轮；数据变化后：32% → 81%'],
].forEach(([label, body], k) => {
  const y = 1.7 + k * 1.05;
  s.addShape('roundRect', { x: M, y, w: 1.8, h: 0.7, fill: { color: C.blue }, line: { color: C.blue },
    rectRadius: 0.35, objectName: `label ${label}` });
  text(s, label, { x: M, y, w: 1.8, h: 0.7, fontSize: 20, bold: true, color: C.white, align: 'center',
    valign: 'middle' });
  text(s, body, { x: M + 2.2, y: y - 0.1, w: W - 2 * M - 2.2, h: 0.9, fontSize: 19, color: C.white,
    valign: 'middle' });
});
s.addNotes('五句话收尾。定位：MAVRA 是智能体和数据库之间的记忆中间件，不生成 SQL，和 Text-to-SQL 是上下游。'
  + '记什么：表画像、关联路径、指标定义，以及它们成立的前提。怎么管：写入前校验，执行前在同一快照上校验，数据变了只重验受影响的规则。'
  + '怎么迭代：能唯一修好就发新版本，修不了就停用并提醒。效果：数据不变时准确率从 49% 到 100%、轮数更少；数据变化后从 32% 到 81%。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
