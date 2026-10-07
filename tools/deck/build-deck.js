// Builds docs/mavra-system.pptx, a Chinese deck that explains MAVRA's structure,
// functions and workflows around three figures in tools/deck/figures/ (drawn by
// `python3 tools/figures/build.py --deck`, rendered to PNG), followed by one real
// example from the end-to-end study (store revenue under three everyday writes).
// Every number on the example slides comes from the archived run records.
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
const SOURCE = '记录：noctis results/scen-20261002/dsv41flash-r1-g3fix--snap（端到端实验第 1 次 MAVRA 运行）。'
  + '数据为仿 TPC-DS 的合成零售数据（100 万行门店销售），题目中的年份略去。';

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

// A tinted card with a numbered circle, a heading and a body.
function card(slide, { x, y, w, h, n, head, body, color, pale, size = 16 }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: pale }, line: { color: pale },
    rectRadius: 0.12, objectName: `card ${head}` });
  slide.addShape('ellipse', { x: x + 0.3, y: y + 0.3, w: 0.55, h: 0.55, fill: { color }, line: { color } });
  text(slide, String(n), { x: x + 0.3, y: y + 0.3, w: 0.55, h: 0.55, fontSize: 20, bold: true,
    color: C.white, align: 'center', valign: 'middle' });
  text(slide, head, { x: x + 0.3, y: y + 1.05, w: w - 0.6, h: 0.45, fontSize: 20, bold: true, color });
  text(slide, body, { x: x + 0.3, y: y + 1.6, w: w - 0.6, h: h - 1.8, fontSize: size, valign: 'top',
    lineSpacingMultiple: 1.15 });
}

// A plain table: header row in grey, body in white, 14 pt.
function table(slide, rows, { x, y, w, colW, size = 14, rowH }) {
  const head = rows[0].map((t) => ({ text: t, options: { bold: true, fill: { color: C.grey } } }));
  const body = rows.slice(1).map((r) => r.map((c) => (typeof c === 'string' ? { text: c } : c)));
  slide.addTable([head, ...body], { x, y, w, colW, rowH, fontFace: FONT, fontSize: size, color: C.ink,
    valign: 'middle', border: { type: 'solid', pt: 1, color: C.line }, margin: [0.06, 0.1, 0.06, 0.1] });
}
const good = (t) => ({ text: t, options: { color: C.green, bold: true } });
const bad = (t) => ({ text: t, options: { color: C.red, bold: true } });

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.title = 'MAVRA：系统结构、功能与工作流';
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

const titlePh = (y, h, size, color, valign) => ({ placeholder: { options: { name: 'title', type: 'title',
  x: M, y, w: W - 2 * M, h, fontFace: FONT, fontSize: size, bold: true, color, valign, align: 'left',
  margin: 0 }, text: '' } });
const number = (color) => ({ x: W - 1.1, y: 7.05, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color,
  align: 'right' });

pres.defineSlideMaster({ title: 'TITLE', background: { color: C.navy }, objects: [
  titlePh(2.1, 1.9, 40, C.white, 'bottom'),
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
s.addText('MAVRA：让智能体共享的指标定义，\n数据变了也不出错', { placeholder: 'title' });
s.addText('一个真实例子 · 系统结构 · 功能 · 工作流', { placeholder: 'body' });
s.addNotes('先看实验里的一个真实例子：智能体学会的指标定义，遇到日常的数据写入会悄悄算错。'
  + '然后讲 MAVRA 怎么解决：由哪几部分组成、各做什么、一次请求怎么走；最后回到这个例子，看 MAVRA 实际是怎么处理的。');

// 2 Example: the learned definition -----------------------------------------------
pres.addSection({ title: '例子' });
s = content('一个真实例子：智能体学会了“门店营业额”', '例子');
text(s, '学习题', { x: M, y: 1.25, w: 5.8, h: 0.4, fontSize: 16, bold: true, color: C.violet });
s.addShape('roundRect', { x: M, y: 1.7, w: 5.8, h: 1.25, fill: { color: C.paleViolet },
  line: { color: C.paleViolet }, rectRadius: 0.08 });
text(s, '3 月的门店营业额是多少？口径：门店营业额 = 门店销售行的净支付额（store_sales.ss_net_paid）之和，'
  + '按销售日期归属期间。保留两位小数。', { x: M + 0.2, y: 1.8, w: 5.4, h: 1.05, fontSize: 15, valign: 'middle' });
text(s, '内置智能体：5 轮、7 次工具调用、9.5 秒，最后的 SQL', { x: M, y: 3.15, w: 5.8, h: 0.35,
  fontSize: 14, color: C.muted });
s.addShape('roundRect', { x: M, y: 3.55, w: 5.8, h: 1.55, fill: { color: C.grey }, line: { color: C.grey },
  rectRadius: 0.08 });
text(s, 'SELECT ROUND(SUM(ss.ss_net_paid), 2)\nFROM store_sales ss\nJOIN date_dim d\n  ON ss.ss_sold_date_sk = d.d_date_sk\nWHERE d.d_year = … AND d.d_moy = 3',
  { x: M + 0.2, y: 3.62, w: 5.4, h: 1.4, fontSize: 13, fontFace: CODE, valign: 'middle' });
text(s, [
  { text: '答案 13,570,368.70，与标准答案一致 ✓', options: { bold: true, color: C.green, breakLine: true } },
  { text: '大模型把解题过程抽取成定义（10 秒）；7 项发布前校验全部通过（2.0 秒），发布为 v1。' },
], { x: M, y: 5.25, w: 5.8, h: 1.2, fontSize: 15, valign: 'top' });
text(s, '存进指标库的定义（v1）', { x: 6.75, y: 1.25, w: 5.98, h: 0.4, fontSize: 16, bold: true, color: C.blue });
table(s, [
  ['字段', '内容'],
  ['名称', '门店营业额（别名：门店销售净额）'],
  ['口径', '门店销售明细行净支付额之和，按销售日期归属期间'],
  ['计算', 'store_sales 上 SUM(ss_net_paid)，无过滤条件'],
  ['粒度', '销售日 + 小票号 + 商品，即每笔销售一行'],
  ['日期', 'ss_sold_date_sk 关联 date_dim（销售日）'],
  ['校验规则', '每笔销售一行；日期键唯一；丢行率不超标（学习时 1.03%）'],
  ['证据', '学习题、学习时的 SQL 和答案、当时的数据版本'],
], { x: 6.75, y: 1.7, w: 5.98, colW: [1.2, 4.78], size: 14 });
footnote(s, SOURCE);
s.addNotes('先看实验里的真实记录。内置智能体拿到一道给出口径的题，几步就写出 SQL，答案和标准答案一致。'
  + '然后大模型把它整理成右边这条定义，MAVRA 从定义里推出三条校验规则：每笔销售一行、日期键唯一、丢行率不超标。'
  + '学习时有 1.03% 的销售关联不到日期表，这个比例被记下来，以后超过才算异常。');

// 3 The problem: the same question after three everyday writes, without maintenance ----------
s = content('数据每天都在写入：照旧用这个定义会怎样', '例子');
table(s, [
  ['写入', '数据库里发生了什么', '正确答案', '照旧用学到的定义'],
  ['追加新数据', '把 9 月的销售复制一份、换新小票号，+27,095 行', '2613.9 万', good('2613.9 万 ✓')],
  ['数据更正', '部分销售被更正：旧行保留并标为非当前（ss_is_current = 0），新增九折的当前行，共 65,915 行',
    '1293.3 万', { text: [{ text: '1430.1 万 ✗', options: { color: C.red, bold: true, breakLine: true } },
      { text: '新旧两版都算了' }] }],
  ['重复装载', '4 个月的销售整批又装载了一次，+110,165 行', '1307.0 万',
    { text: [{ text: '2613.9 万 ✗', options: { color: C.red, bold: true, breakLine: true } },
      { text: '9 月翻倍' }] }],
], { x: M, y: 1.3, w: W - 2 * M, colW: [1.6, 5.4, 1.6, 3.53], size: 15 });
s.addShape('roundRect', { x: M, y: 4.55, w: W - 2 * M, h: 1.9, fill: { color: C.grey }, line: { color: C.grey },
  rectRadius: 0.08 });
text(s, [
  { text: '问题在哪', options: { bold: true, color: C.red, breakLine: true } },
  { text: '三种写入都是普通的 INSERT / UPDATE，表结构没变：只看表结构的做法发现不了', options: { bullet: true, breakLine: true } },
  { text: 'SQL 照样能跑、不报错：用这个定义的智能体自己看不出来', options: { bullet: true, breakLine: true } },
  { text: '定义被很多智能体共享：一处过期，所有用它的智能体一起算错', options: { bullet: true } },
], { x: M + 0.3, y: 4.65, w: W - 2 * M - 0.6, h: 1.7, fontSize: 17, valign: 'middle', paraSpaceAfter: 4 });
footnote(s, '“照旧用学到的定义”即对照组：只在表结构变化时才让定义失效，3 次独立运行答案相同。'
  + SOURCE.slice(SOURCE.indexOf('数据为')));
s.addNotes('同一个问题“9 月门店营业额”，在三种日常写入之后分别再问一次，智能体照旧用学到的定义。'
  + '追加新数据没问题。数据更正——数据仓库里很常见的做法是旧行不删、标成非当前，再插一行新的——照旧用就会把新旧两版都加进去，多出 137 万。'
  + '重复装载，一批数据被导了两次，9 月直接翻倍。'
  + '这三种都是普通的数据写入，表结构没变，只看表结构的做法完全发现不了；SQL 也不报错，用的人看不出来。这就是 MAVRA 要解决的问题。');

// 4 What MAVRA does ---------------------------------------------------------------
pres.addSection({ title: '功能与结构' });
s = content('MAVRA 做三件事', '功能与结构');
text(s, '例子里的问题：学到的指标定义被很多智能体共享，数据一变就可能悄悄算错，而且没人发现。'
  + 'MAVRA 是位于智能体和数据库之间的中间件，负责：', {
  x: M, y: 1.25, w: W - 2 * M, h: 0.85, fontSize: 16, color: C.muted, valign: 'top' });
const cw = (W - 2 * M - 2 * 0.3) / 3;
[
  { n: 1, head: '学习指标定义', color: C.violet, pale: C.paleViolet,
    body: '内置智能体（大模型）回答给出口径的题目；答案核验正确、发布前校验通过，才把定义发布到指标库，所有智能体共用。' },
  { n: 2, head: '数据变了就重新校验', color: C.blue, pale: C.paleBlue,
    body: '记录每个指标定义依赖的校验规则（如“每笔销售一行”）。数据一变，只重新校验受影响的规则；校验结果按（规则，数据版本）缓存，大家共用。规则不成立就修复，修不了就停用。' },
  { n: 3, head: '执行前把关', color: C.amber, pale: C.paleAmber,
    body: '智能体的 SQL 注明用的是哪个指标的哪一版；执行前在这条查询的快照上校验规则，过期或已停用的版本直接拒绝。' },
].forEach((c, k) => card(s, { ...c, x: M + k * (cw + 0.3), y: 2.4, w: cw, h: 4.2 }));
s.addNotes('回到刚才的问题：指标定义被共享，数据会变，定义可能悄悄算错，而且没人发现。'
  + 'MAVRA 做三件事：学习指标定义（紫色）、数据变了就重新校验（蓝色）、执行前把关（橙色）。'
  + '后面三张图用的是同一套颜色，讲的都是“门店营业额”这个例子。');

// 5 Structure -------------------------------------------------------------------------
s = content('系统结构：一次请求怎样经过 MAVRA', '功能与结构');
figure(s, 'overview');
s.addNotes('左边是用户智能体，它发两种请求。'
  + '蓝色 1–5 是查询指标定义：智能体只说“营业额”，查询服务从指标库读出定义；'
  + '销售表的数据变了，某条规则在新数据版本上还没有校验结果，就交给维护去校验，结果写入缓存，再返回有效的 v2。'
  + '橙色 6–8 是执行 SQL：智能体写好 SQL 并注明用的是 v2，执行前校验复用缓存里的结果，在同一快照上执行。'
  + '紫色是学习：内置智能体学到的定义，发布前校验通过才进入指标库。');

// 6 Workflow: query and execution ------------------------------------------------------
pres.addSection({ title: '工作流' });
s = content('工作流①：查询指标定义，再执行 SQL', '工作流');
figure(s, 'lookup');
s.addNotes('上面一行是查询指标定义：按名称匹配到“门店营业额”（“电子品类门店营业额”也包含这几个字，一并返回，由智能体按口径说明挑选）；'
  + '再看销售表的数据版本有没有变（14 变成 15）；然后逐条规则查缓存：“每笔销售一行”电子品类那个指标刚校验过，直接复用；'
  + '日期表没变，复用；“丢行率不超标”在 15 上没有结果，现在校验并写入缓存；最后返回有效的 v2。'
  + '中间是校验结果缓存：按（规则，数据版本）存，表里写明谁写入、哪一步复用。'
  + '下面一行是执行 SQL：先检查注明的 v2 能不能用；再在这条查询的快照上校验——这期间又有写入，数据版本变成 16，'
  + '所以两条规则在快照里重新校验并写入缓存；最后在同一快照上执行。');

// 7 Workflow: learning and maintenance ---------------------------------------------------
s = content('工作流②：指标定义的学习、停用与修复', '工作流');
figure(s, 'lifecycle');
s.addNotes('跟着门店营业额走一遍，接下来三页回到开头的例子，看真实记录。'
  + '内置智能体回答“3 月门店营业额”，答案核验正确、发布前校验通过，发布 v1。'
  + '之后追加一批新销售：规则仍成立，其他指标直接复用结果，还是 v1。'
  + '再之后有一批销售被更正：旧行保留但标成非当前，新增当前行——“每笔销售一行”不成立，v1 停用，不处理会把新旧两版都算进去。'
  + '修复时在取值少的列上试过滤，只有“只算当前行”可行；用学习时的数据重算 3 月，结果一致，发布 v2。'
  + '红框是另一种情况：一批销售被重复装载，没有任何过滤能修好，就停用并提醒，等待重新学习。');

// 8 Back to the example: the same writes with MAVRA -------------------------------------------------
pres.addSection({ title: '回到例子' });
s = content('回到例子：有了 MAVRA 之后', '回到例子');
table(s, [
  ['写入', '数据库里发生了什么', '正确答案', '不维护（对照组）', 'MAVRA'],
  ['追加新数据', '把 9 月的销售复制一份、换新小票号，+27,095 行', '2613.9 万', good('2613.9 万 ✓'),
    { text: [{ text: '规则仍成立，保持 v1', options: { breakLine: true } },
      { text: '6 个指标只跑了 2 次校验', options: { breakLine: true } },
      { text: '2613.9 万 ✓', options: { color: C.green, bold: true } }] }],
  ['数据更正', '部分销售被更正：旧行保留并标为非当前（ss_is_current = 0），新增九折的当前行，共 65,915 行',
    '1293.3 万', { text: [{ text: '1430.1 万 ✗', options: { color: C.red, bold: true, breakLine: true } },
      { text: '新旧两版都算了' }] },
    { text: [{ text: '停用 v1 → 修复为 v2', options: { breakLine: true } },
      { text: '（只算 ss_is_current = \'1\'）', options: { breakLine: true } },
      { text: '1293.3 万 ✓', options: { color: C.green, bold: true } }] }],
  ['重复装载', '4 个月的销售整批又装载了一次，+110,165 行', '1307.0 万',
    { text: [{ text: '2613.9 万 ✗', options: { color: C.red, bold: true, breakLine: true } },
      { text: '9 月翻倍' }] },
    { text: [{ text: '找不到修复 → 停用并提醒', options: { breakLine: true } },
      { text: '智能体自己去重', options: { breakLine: true } },
      { text: '3 次运行中 2 次答对', options: { bold: true } }] }],
], { x: M, y: 1.3, w: W - 2 * M, colW: [1.45, 3.75, 1.35, 2.0, 3.58], size: 14 });
text(s, [
  { text: '同样三种写入，MAVRA 都发现了：', options: { bold: true, breakLine: true } },
  { text: '规则仍成立就继续用；能唯一修好就发布新版本；修不了就停用并提醒，不让错误答案悄悄出去。' },
], { x: M, y: 5.35, w: W - 2 * M, h: 1.0, fontSize: 16, valign: 'top' });
footnote(s, '对照组：只在表结构变化时才让定义失效，3 次独立运行答案相同。MAVRA 栏为第 1 次运行；'
  + '追加和更正 3 次运行结果相同，重复装载见表。' + SOURCE.slice(SOURCE.indexOf('数据为')));
s.addNotes('回到开头那张表，加上 MAVRA 这一栏。'
  + '追加新数据：定义仍然对，MAVRA 重新校验后继续用；而且电子品类、退货率等 6 个依赖销售表的指标，一共只跑了 2 次校验，其余直接复用。'
  + '数据更正：MAVRA 发现“每笔销售一行”不成立，停用旧定义，找到唯一的修复“只算当前行”，发布 v2，答对。'
  + '重复装载：一批数据被导了两次，没法用过滤修好，MAVRA 停用并提醒智能体，智能体自己去重，3 次里 2 次答对。'
  + '下一页看数据更正之后，MAVRA 具体一步步做了什么。');

// 9 Back to the example: what happened after the restatement ------------------------------------
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
    { text: [{ text: '复用校验结果和修复，', options: {} },
      { text: '45.8 毫秒', options: { bold: true, color: C.blue } }, { text: '就发布了 v2' }] }],
  ['5', '“门店退货率”要把销售和退货关联起来', '关联路径现在要求只用当前行 → 也修复为 v2'],
  ['6', '用户智能体 B 问“9 月门店营业额”',
    { text: [{ text: '收到 3 条提醒；SQL 带上 ss_is_current = \'1\'；答 ', options: {} },
      { text: '1293.3 万 ✓', options: { color: C.green, bold: true } }, { text: '（4 轮，61.7 秒）' }] }],
], { x: M, y: 1.3, w: W - 2 * M, colW: [0.45, 5.4, 6.28], size: 14 });
footnote(s, SOURCE);
s.addNotes('数据更正之后，第一个用到销售表的查询到来，先检查名称匹配到的电子品类营业额。MAVRA 一校验就发现每个销售键平均有 1.07 行，停用旧定义；'
  + '然后自动找修复，只有“只算当前行”这一个过滤可行，四项检查都过了，发布 v2，一共 28.7 秒。'
  + '接着检查门店营业额：它依赖的是同一条规则、同一个数据版本，结果和修复都直接复用，45.8 毫秒就好了。'
  + '退货率因为要关联销售表，也跟着修好。最后用户智能体收到提醒，按新定义写 SQL，答对。');

// 10 Back to the example: why the regression test uses learning-time data ---------------------------
s = content('回归测试为什么要用学习时的数据', '回到例子');
text(s, '学习题问的是 3 月，正好在被更正的范围里。回归测试拿内置智能体当初的 SQL 当标准，'
  + '和加了过滤的新定义各算一次 3 月：', { x: M, y: 1.3, w: W - 2 * M, h: 0.8, fontSize: 17, valign: 'top' });
table(s, [
  ['用哪份数据比', '当初的 SQL', '新定义（v2）', '结果'],
  ['学习时的数据', '1357.0 万', '1357.0 万', good('一致 → 接受修复 ✓')],
  ['现在的数据', '1489.1 万', '1342.4 万', bad('不一致 → 拒绝了正确的修复 ✗')],
], { x: M, y: 2.35, w: W - 2 * M, colW: [2.6, 2.6, 2.6, 4.33], size: 18, rowH: 0.65 });
s.addShape('roundRect', { x: M, y: 4.6, w: W - 2 * M, h: 1.5, fill: { color: C.paleBlue },
  line: { color: C.paleBlue }, rectRadius: 0.08 });
text(s, [
  { text: '原因：', options: { bold: true, color: C.blue } },
  { text: '在现在的数据里，当初的 SQL 自己也过时了——它把更正前的旧行也算了进去（1489.1 万）。'
    + '它只在学习时的数据上被核验过是对的，所以只能在那份数据上当标准。' },
], { x: M + 0.3, y: 4.7, w: W - 2 * M - 0.6, h: 1.3, fontSize: 17, valign: 'middle' });
footnote(s, '“现在的数据”一行来自对照实验（回归测试改用当前数据，dsv41flash-r1-g3fix--exref），系统记录原文：'
  + '“结果 13423672.28 与期望 14890636.48 不一致”。');
s.addNotes('为什么回归测试不能直接用现在的数据？学习题问的是 3 月，而这次更正正好覆盖 3 月。'
  + '在现在的数据上，智能体当初写的 SQL 本身就会把旧版本也算进去，得到 1489 万；正确的新定义得到 1342 万，两者对不上，正确的修复就被拒了。'
  + '我们实际跑过这个对照：用现在的数据比，这个修复确实被拒绝。'
  + '用学习时的数据比，两者都是 1357 万，修复被接受。');

// 11 Summary ------------------------------------------------------------------------------
pres.addSection({ title: '小结' });
s = pres.addSlide({ masterName: 'CLOSING', sectionTitle: '小结' });
s.addText('小结', { placeholder: 'title' });
[
  ['结构', '用户智能体 → MAVRA（查询服务、指标库、内置智能体与维护）→ 数据库'],
  ['功能', '学习指标定义；数据变了重新校验，校验结果缓存共用；执行前在同一快照上校验'],
  ['工作流', '查指标定义 → 执行 SQL；数据变化 → 校验 → 修复或停用 → 重新学习'],
  ['例子', '追加、更正、重复装载都是日常写入，表结构不变；MAVRA 都能发现，能修就修，修不了就停用'],
].forEach(([label, body], k) => {
  const y = 1.75 + k * 1.25;
  s.addShape('roundRect', { x: M, y, w: 1.6, h: 0.7, fill: { color: C.blue }, line: { color: C.blue },
    rectRadius: 0.35, objectName: `label ${label}` });
  text(s, label, { x: M, y, w: 1.6, h: 0.7, fontSize: 20, bold: true, color: C.white, align: 'center',
    valign: 'middle' });
  text(s, body, { x: M + 2.0, y: y - 0.1, w: W - 2 * M - 2.0, h: 0.9, fontSize: 19, color: C.white,
    valign: 'middle' });
});
s.addNotes('四句话收尾：结构、功能、工作流，以及例子说明的事——日常写入就会让共享的定义悄悄出错，'
  + 'MAVRA 能发现，能唯一修好就修，修不了就停用，不让错误答案出去。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
