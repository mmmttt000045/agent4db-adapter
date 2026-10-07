// Builds docs/mavra-system.pptx: a short, plain Chinese deck that explains
// MAVRA's structure, functions and workflows with simple native diagrams
// (editable shapes, no paper figures). Usage: node build-deck.js [--out path]
'use strict';

const path = require('path');
const pptxgen = require('pptxgenjs');

const ROOT = path.resolve(__dirname, '../..');
const at = process.argv.indexOf('--out');
const OUT = at > 0 ? path.resolve(process.argv[at + 1]) : path.join(ROOT, 'docs/mavra-system.pptx');

const FONT = 'Microsoft YaHei';
const C = {
  ink: '1F2A37', muted: '5B6573', navy: '17233B', ice: 'CADCFC', white: 'FFFFFF', line: 'C9D1DB',
  grey: 'F1F3F6', field: 'EEF3FA',
  blue: '1D5BA6', paleBlue: 'E8F0FA',          // request handling
  teal: '1F7A72', paleTeal: 'E3F2F0',          // shared store
  violet: '6A58A3', paleViolet: 'EFECF7',      // learning and maintenance
  amber: 'B5671A', paleAmber: 'FBF0E2',        // data and writes
  red: 'B5392A', paleRed: 'FBEAE7', green: '2E7D4F', paleGreen: 'E6F3EA',
};
const W = 13.333, M = 0.6;

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.title = 'MAVRA：系统结构、功能与工作流';
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
const S = pres.shapes;

// ---------------------------------------------------------------- helpers

function text(slide, value, opts) {
  slide.addText(value, { fontFace: FONT, color: C.ink, margin: 0, isTextBox: true, valign: 'top',
    ...opts });
}

// pptxgenjs takes text insets in points as [left, right, bottom, top]; give them in
// inches, either one number or [top, right, bottom, left].
function inset(m) {
  if (typeof m === 'number') return m * 72;
  const [t, r, b, l] = m;
  return [l * 72, r * 72, b * 72, t * 72];
}

// A rounded box with text inside; value may be a string or runs.
function box(slide, value, { x, y, w, h, fill = C.white, border = C.line, bw = 1, size = 16, color = C.ink,
  bold = false, align = 'center', valign = 'middle', shape = S.ROUNDED_RECTANGLE, margin = 0.12 }) {
  slide.addText(value, { shape, x, y, w, h, fill: { color: fill }, line: { color: border, width: bw },
    rectRadius: 0.1, fontFace: FONT, fontSize: size, color, bold, align, valign, margin: inset(margin),
    lineSpacingMultiple: 1.1 });
}

// Runs for a box: a bold heading line and a body.
function headed(head, body, color, headSize = 20, bodySize = 16) {
  return [
    { text: head, options: { bold: true, color, fontSize: headSize, breakLine: true } },
    { text: body, options: { fontSize: bodySize, color: C.ink } },
  ];
}

// Straight or elbowed arrow through the given points (inches); head at the end.
function arrow(slide, pts, color = C.muted, width = 2) {
  for (let i = 0; i + 1 < pts.length; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
    const line = { color, width };
    if (i + 2 === pts.length) line.endArrowType = 'triangle';
    slide.addShape(S.LINE, {
      x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
      flipH: x2 < x1, flipV: y2 < y1, line,
    });
  }
}

function circle(slide, n, x, y, color, d = 0.55, size = 20) {
  slide.addText(String(n), { shape: S.OVAL, x, y, w: d, h: d, fill: { color }, line: { color },
    fontFace: FONT, fontSize: size, bold: true, color: C.white, align: 'center', valign: 'middle',
    margin: 0 });
}

// ---------------------------------------------------------------- layouts

const titlePh = (y, h, size, color, valign) => ({ placeholder: { options: { name: 'title', type: 'title',
  x: M, y, w: W - 2 * M, h, fontFace: FONT, fontSize: size, bold: true, color, valign, align: 'left',
  margin: 0 }, text: '' } });
const number = (color) => ({ x: W - 1.1, y: 7.0, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color,
  align: 'right' });

pres.defineSlideMaster({ title: 'TITLE', background: { color: C.navy }, objects: [
  titlePh(2.1, 1.9, 40, C.white, 'bottom'),
  { placeholder: { options: { name: 'body', type: 'body', x: M, y: 4.3, w: W - 2 * M, h: 0.7,
    fontFace: FONT, fontSize: 22, color: C.ice, valign: 'top', align: 'left', margin: 0 }, text: '' } },
] });
pres.defineSlideMaster({ title: 'CONTENT', background: { color: C.white },
  objects: [titlePh(0.35, 0.8, 30, C.ink, 'middle')], slideNumber: number(C.muted) });
pres.defineSlideMaster({ title: 'CLOSING', background: { color: C.navy },
  objects: [titlePh(0.6, 0.9, 32, C.white, 'middle')], slideNumber: number(C.ice) });

function content(title, section) {
  const s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: section });
  s.addText(title, { placeholder: 'title' });
  return s;
}

// ---------------------------------------------------------------- 1 title

pres.addSection({ title: '开场' });
let s = pres.addSlide({ masterName: 'TITLE', sectionTitle: '开场' });
s.addText('MAVRA：让智能体共享的指标口径，\n数据变了也不出错', { placeholder: 'title' });
s.addText('系统结构 · 功能 · 工作流', { placeholder: 'body' });
s.addNotes('这次只讲系统：它要解决什么问题、由哪几部分组成、各做什么、请求怎么走、口径坏了怎么办。'
  + '全程用一个例子：门店退货金额。');

// ---------------------------------------------------------------- 2 problem

s = content('问题：共享的口径会悄悄过期', '开场');
const pw = (W - 2 * M - 3 * 0.45) / 4;
[
  ['① 学会', '智能体 A 学会：\n退货金额 =\n退货表金额加起来', C.violet, C.paleViolet],
  ['② 共享', '口径存起来，\n智能体 B、C\n直接拿来用', C.blue, C.paleBlue],
  ['③ 数据变了', 'ETL 给每笔退货\n多写一行“申请”\n表结构没变', C.amber, C.paleAmber],
  ['④ 悄悄算错', 'B 算 5 月退货：\n658.9 万\n实际 329.4 万', C.red, C.paleRed],
].forEach(([head, body, color, pale], k) => {
  const x = M + k * (pw + 0.45);
  box(s, headed(head, body, color, 22, 17), { x, y: 1.75, w: pw, h: 2.6, fill: pale, border: pale });
  if (k < 3) arrow(s, [[x + pw + 0.07, 3.05], [x + pw + 0.38, 3.05]], C.muted, 2.5);
});
box(s, [
  { text: 'SQL 照样能跑、不报错，用口径的智能体发现不了。', options: { bold: true, breakLine: true } },
  { text: 'MAVRA 要做的：记住每个口径依赖什么条件，数据变了就检查，用之前再核对。', options: {} },
], { x: M, y: 4.9, w: W - 2 * M, h: 1.4, fill: C.grey, border: C.grey, size: 20, align: 'left',
  margin: 0.3 });
s.addNotes('先讲清楚问题。智能体 A 花了很多步学会“门店退货金额”怎么算，口径被存下来给别的智能体用。'
  + '后来 ETL 改了写法，每笔退货多写一行“申请”状态，表结构没变，SQL 还能跑，'
  + '但同一笔退货被算了两次，5 月的答案翻倍。用口径的智能体没有标准答案，发现不了。'
  + 'MAVRA 就是来管这件事的。');

// ---------------------------------------------------------------- 3 structure

pres.addSection({ title: '结构与功能' });
s = content('系统结构：MAVRA 在智能体和数据库之间', '结构与功能');
box(s, '用户端智能体（很多个）', { x: 3.4, y: 1.35, w: 6.5, h: 0.8, fill: C.grey, border: C.line,
  size: 20, bold: true });
arrow(s, [[5.6, 2.15], [5.6, 2.85]], C.ink, 2.25);
arrow(s, [[7.7, 2.85], [7.7, 2.15]], C.ink, 2.25);
text(s, '问口径、发 SQL', { x: 3.2, y: 2.3, w: 2.25, h: 0.4, fontSize: 16, align: 'right' });
text(s, '口径、查询结果', { x: 7.85, y: 2.3, w: 2.6, h: 0.4, fontSize: 16 });
box(s, '', { x: 0.9, y: 2.85, w: 11.5, h: 2.45, fill: C.field, border: C.field });
text(s, 'MAVRA 中间件', { x: 1.2, y: 2.98, w: 4, h: 0.4, fontSize: 18, bold: true, color: C.blue });
[
  ['请求处理', '接待智能体的请求', C.blue],
  ['共享知识库', '存口径和检查结果', C.teal],
  ['学习与维护', '学口径、管口径', C.violet],
].forEach(([name, role, color], k) => {
  box(s, headed(name, role, color, 22, 16), { x: 1.25 + k * 3.7, y: 3.5, w: 3.4, h: 1.5, border: color,
    bw: 2 });
});
arrow(s, [[6.65, 5.3], [6.65, 5.85]], C.ink, 2.25);
text(s, '读数据、跑检查、执行查询', { x: 6.85, y: 5.38, w: 3.4, h: 0.4, fontSize: 16 });
box(s, 'SQL 数据库', { x: 5.15, y: 5.85, w: 3.0, h: 1.05, shape: S.CAN, fill: C.paleAmber,
  border: C.amber, bw: 1.5, size: 20, bold: true });
box(s, 'ETL / 写入方', { x: 10.0, y: 6.05, w: 2.4, h: 0.7, fill: C.grey, border: C.line, size: 16 });
arrow(s, [[10.0, 6.4], [8.2, 6.4]], C.amber, 2.25);
text(s, '不断写入新数据', { x: 8.35, y: 6.48, w: 1.7, h: 0.35, fontSize: 14, color: C.amber });
s.addNotes('智能体不直接碰数据库：问口径、发 SQL 都经过 MAVRA。'
  + 'MAVRA 里面三块：请求处理负责接待；共享知识库存口径和检查结果；学习与维护负责学新口径、在数据变化后管好旧口径。'
  + '数据库那边，ETL 一直在写新数据，这就是口径会过期的原因。');

// ---------------------------------------------------------------- 4 functions

s = content('三个模块各管什么', '结构与功能');
const fw = (W - 2 * M - 2 * 0.35) / 3;
[
  ['接', '请求处理', C.blue, C.paleBlue, [
    '智能体问“某指标怎么算”：返回现在能用的口径',
    '智能体发 SQL：先核对它用的口径还成立，再执行',
    '口径过时或停用：拒绝，并告诉智能体']],
  ['存', '共享知识库', C.teal, C.paleTeal, [
    '口径：怎么算，依赖哪些条件（如“每笔退货只有一行”）',
    '检查结果：哪个条件、在哪份数据上、成不成立',
    '所有智能体共用同一份']],
  ['学', '学习与维护', C.violet, C.paleViolet, [
    '学：内置的大模型智能体答题，答对且通过检查才发布口径',
    '管：数据变了就重新检查条件',
    '坏了：能唯一修好就发新版，修不好就停用']],
].forEach(([glyph, name, color, pale, items], k) => {
  const x = M + k * (fw + 0.35);
  box(s, '', { x, y: 1.45, w: fw, h: 5.35, fill: pale, border: pale });
  circle(s, glyph, x + 0.35, 1.75, color, 0.75, 24);
  text(s, name, { x: x + 1.3, y: 1.85, w: fw - 1.5, h: 0.55, fontSize: 24, bold: true, color });
  text(s, items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i + 1 < items.length,
    paraSpaceAfter: 12 } })), { x: x + 0.35, y: 2.8, w: fw - 0.7, h: 3.8, fontSize: 18 });
});
s.addNotes('三个模块的分工。请求处理是前台；共享知识库是记忆，除了口径本身，还存每个条件的检查结果；'
  + '学习与维护是后台：内置的分析优化器（一个大模型智能体）负责学新口径，维护负责在数据变化后检查、修复或停用。');

// ---------------------------------------------------------------- 5 lookup workflow

pres.addSection({ title: '工作流' });
s = content('工作流①：智能体来问“退货金额怎么算”', '工作流');
box(s, '智能体：“5 月门店退货金额是多少？”——它只知道指标名', { x: M, y: 1.35, w: W - 2 * M, h: 0.6,
  fill: C.grey, border: C.grey, size: 17, align: 'left', margin: 0.25 });
const lw = (W - 2 * M - 3 * 0.42) / 4;
[
  ['按名字找', '“退货金额”\n→ 找到口径\n“门店退货金额”'],
  ['看数据变没变', '它用的表\nstore_returns\n刚有新写入'],
  ['需要就重新检查', '查过的：直接用\n没查过的：现在查'],
  ['返回口径', '怎么算 + 参考 SQL\n智能体照着写'],
].forEach(([head, body], k) => {
  const x = M + k * (lw + 0.42);
  box(s, headed(head, body, C.blue, 20, 17), { x, y: 2.55, w: lw, h: 2.3, fill: C.paleBlue,
    border: C.paleBlue, valign: 'top', margin: [0.75, 0.15, 0.1, 0.15] });
  circle(s, k + 1, x + lw / 2 - 0.27, 2.2, C.blue);
  if (k < 3) arrow(s, [[x + lw + 0.06, 3.7], [x + lw + 0.36, 3.7]], C.blue, 2.5);
});
box(s, [{ text: '数据没变：', options: { bold: true, color: C.green } },
  { text: '跳过第 3 步，直接返回' }], { x: M, y: 5.3, w: 5.8, h: 0.75, fill: C.paleGreen,
  border: C.paleGreen, size: 17, align: 'left', margin: 0.25 });
box(s, [{ text: '口径已停用：', options: { bold: true, color: C.red } },
  { text: '告诉智能体“这个口径现在不能用”' }], { x: M + 6.2, y: 5.3, w: W - 2 * M - 6.2, h: 0.75,
  fill: C.paleRed, border: C.paleRed, size: 17, align: 'left', margin: 0.25 });
s.addNotes('智能体只说“退货金额”。第一步按名字或别名找到口径；第二步看这个口径用到的表有没有被写过；'
  + '写过就进入第三步，重新确认它依赖的条件——这里能复用就复用，下一页专门讲；最后把口径和参考 SQL 返回。'
  + '数据没变就直接返回；口径已经停用就明确告诉智能体。');

// ---------------------------------------------------------------- 6 reuse

s = content('检查结果：查一次，大家都能用', '工作流');
box(s, headed('门店退货金额', '需要：每笔退货只有一行', C.blue, 20, 16),
  { x: M, y: 1.6, w: 3.4, h: 1.3, fill: C.paleBlue, border: C.paleBlue });
box(s, headed('门店退货率', '需要：每笔退货只有一行', C.blue, 20, 16),
  { x: M, y: 3.7, w: 3.4, h: 1.3, fill: C.paleBlue, border: C.paleBlue });
box(s, [
  { text: '检查结果', options: { bold: true, color: C.teal, fontSize: 20, breakLine: true } },
  { text: '条件：每笔退货只有一行', options: { breakLine: true } },
  { text: '数据版本：第 15 版', options: { breakLine: true } },
  { text: '结论：成立 ✓', options: { bold: true, color: C.green } },
], { x: 5.2, y: 2.1, w: 3.6, h: 2.4, border: C.teal, bw: 2, size: 17, align: 'left', margin: 0.25 });
arrow(s, [[4.0, 2.25], [4.6, 2.25], [4.6, 2.9], [5.2, 2.9]], C.blue, 2);
arrow(s, [[4.0, 4.35], [4.6, 4.35], [4.6, 3.7], [5.2, 3.7]], C.blue, 2);
text(s, '先到的：现在查，存起来', { x: M, y: 3.0, w: 3.6, h: 0.35, fontSize: 15, color: C.muted });
text(s, '后到的：直接拿结果', { x: M, y: 5.1, w: 3.6, h: 0.35, fontSize: 15, color: C.muted });
arrow(s, [[8.8, 3.3], [9.5, 3.3]], C.amber, 2.25);
box(s, headed('又有新数据写入', '版本变成第 16 版：\n这条结果对新数据不算数，\n下次用到时重查', C.amber, 20, 16),
  { x: 9.5, y: 2.1, w: 3.23, h: 2.4, fill: C.paleAmber, border: C.paleAmber });
box(s, [
  { text: '规则：', options: { bold: true, color: C.teal } },
  { text: '检查结果按“条件 + 数据版本”存。同一个条件、同一份数据，不管哪个口径、哪个智能体用到，只查一次。',
    options: { breakLine: true } },
  { text: '数据版本：一张表每被写入一次，版本号加 1。', options: { color: C.muted, fontSize: 15 } },
], { x: M, y: 5.6, w: W - 2 * M, h: 1.2, fill: C.grey, border: C.grey, size: 17, align: 'left',
  margin: 0.25 });
s.addNotes('这是 MAVRA 省工作量的地方。很多口径依赖同一个条件，比如退货金额和退货率都要求“每笔退货只有一行”。'
  + '检查结果按“条件 + 数据版本”保存：退货率先查过，退货金额再来就直接用。'
  + '表一被写入，版本号就变，旧结果对新数据不再算数，下次用到时重查一次，再存起来。');

// ---------------------------------------------------------------- 7 execution workflow

s = content('工作流②：智能体执行 SQL', '工作流');
box(s, '智能体按拿到的口径写好 SQL，发给 MAVRA', { x: M, y: 1.35, w: W - 2 * M, h: 0.6,
  fill: C.grey, border: C.grey, size: 17, align: 'left', margin: 0.25 });
const ew = (W - 2 * M - 2 * 0.5) / 3;
[
  ['声明', 'SQL 里写明：\n用“退货金额”第 2 版'],
  ['核对', '这一版还有效吗？\n它的条件在“这一刻的数据”上\n还成立吗？（能复用就复用）'],
  ['执行', '在同一份数据上跑 SQL\n5 月退货金额：329.4 万'],
].forEach(([head, body], k) => {
  const x = M + k * (ew + 0.5);
  box(s, headed(head, body, C.amber, 20, 17), { x, y: 2.55, w: ew, h: 2.1, fill: C.paleAmber,
    border: C.paleAmber, valign: 'top', margin: [0.75, 0.15, 0.1, 0.15] });
  circle(s, k + 1, x + ew / 2 - 0.27, 2.2, C.amber);
  if (k < 2) arrow(s, [[x + ew + 0.08, 3.6], [x + ew + 0.42, 3.6]], C.amber, 2.5);
});
const xc = M + ew + 0.5 + ew / 2;
arrow(s, [[xc, 4.65], [xc, 5.15]], C.red, 2);
box(s, [{ text: '不成立或版本过时：', options: { bold: true, color: C.red } },
  { text: '拒绝执行，提示智能体重新查口径' }], { x: xc - 3.6, y: 5.15, w: 7.2, h: 0.65,
  fill: C.paleRed, border: C.paleRed, size: 17, margin: 0.2 });
text(s, [{ text: '“这一刻的数据”：', options: { bold: true } },
  { text: '核对和执行看同一个数据库快照。核对完、执行前有人写入，也不会让核对白做。' }],
  { x: M, y: 6.15, w: W - 2 * M - 0.8, h: 0.6, fontSize: 15, color: C.muted });
s.addNotes('智能体拿到口径后写 SQL，并在请求里声明用的是哪个口径的哪一版。'
  + 'MAVRA 先核对：这一版有没有被替换或停用；再在这条查询要读的那份数据上确认条件成立，能复用的检查结果直接用。'
  + '核对和执行用同一个数据库快照，所以中间即使有写入，也不会出现“核对时对、执行时错”。');

// ---------------------------------------------------------------- 8 lifecycle

s = content('工作流③：一个口径的一生', '工作流');
const bw = 2.75, by = 1.5, bh = 1.15, gx = 0.35;
const X = (k) => M + 0.1 + k * (bw + gx);
[
  ['学习', '大模型答题，判对才收', C.violet, C.paleViolet],
  ['发布口径', '第 1 版（修好后第 2 版）', C.violet, C.paleViolet],
  ['智能体使用', '查口径、执行 SQL', C.blue, C.paleBlue],
  ['数据被写入', '例：多了“申请”行', C.amber, C.paleAmber],
].forEach(([head, body, color, pale], k) => {
  box(s, headed(head, body, color, 18, 14), { x: X(k), y: by, w: bw, h: bh, fill: pale, border: pale });
  if (k < 3) arrow(s, [[X(k) + bw + 0.05, by + bh / 2], [X(k + 1) - 0.05, by + bh / 2]], C.muted, 2);
});
const dw = 3.0, dx = X(3) + bw / 2 - dw / 2, d1y = 3.1, dh = 1.2, d2y = 4.8;
arrow(s, [[dx + dw / 2, by + bh], [dx + dw / 2, d1y]], C.muted, 2);
box(s, '条件还成立？', { x: dx, y: d1y, w: dw, h: dh, shape: S.DIAMOND, fill: C.white, border: C.ink,
  bw: 1.5, size: 16, bold: true, margin: 0 });
arrow(s, [[dx, d1y + dh / 2], [X(2) + bw / 2, d1y + dh / 2], [X(2) + bw / 2, by + bh]], C.green, 2);
text(s, '成立：继续用', { x: X(2) + bw / 2 + 0.15, y: d1y + dh / 2 - 0.42, w: 2.2, h: 0.35,
  fontSize: 15, bold: true, color: C.green });
arrow(s, [[dx + dw / 2, d1y + dh], [dx + dw / 2, d2y]], C.red, 2);
text(s, '不成立：先停用', { x: dx + dw / 2 - 2.12, y: d1y + dh + 0.02, w: 2.0, h: 0.35, fontSize: 15,
  bold: true, color: C.red, align: 'right' });
box(s, '有唯一修复？', { x: dx, y: d2y, w: dw, h: dh, shape: S.DIAMOND, fill: C.white, border: C.ink,
  bw: 1.5, size: 16, bold: true, margin: 0 });
arrow(s, [[dx, d2y + dh / 2], [X(1) + bw / 2, d2y + dh / 2], [X(1) + bw / 2, by + bh]], C.violet, 2);
text(s, '有：发布新版本', { x: X(1) + bw / 2 + 0.15, y: d2y + dh / 2 - 0.42, w: 2.4, h: 0.35,
  fontSize: 15, bold: true, color: C.violet });
arrow(s, [[dx + dw / 2, d2y + dh], [dx + dw / 2, 6.55], [X(0) + bw / 2, 6.55], [X(0) + bw / 2, by + bh]],
  C.red, 2);
text(s, '没有：保持停用，等重新学习', { x: X(0) + bw / 2 + 0.15, y: 6.1, w: 4.0, h: 0.35, fontSize: 15,
  bold: true, color: C.red });
s.addNotes('把一个口径从生到死串起来。内置的大模型智能体答题学会口径，通过检查后发布第 1 版，各个智能体使用。'
  + '数据被写入后，MAVRA 检查它依赖的条件：成立就继续用；不成立就先停用，再看能不能修。'
  + '有唯一的修复，就发布第 2 版，回到使用；没有，就保持停用，等以后重新学习。下一页看具体怎么修。');

// ---------------------------------------------------------------- 9 repair example

s = content('修复的例子：退货表多了“申请”行', '工作流');
text(s, 'store_returns（示意）', { x: M, y: 1.4, w: 5, h: 0.4, fontSize: 16, bold: true });
const head = (t) => ({ text: t, options: { bold: true, fill: { color: C.grey } } });
const hot = (t) => ({ text: t, options: { fill: { color: C.paleAmber }, color: C.amber, bold: true } });
s.addTable([
  [head('小票'), head('商品'), head('金额'), head('状态')],
  ['1001', '7', '120', '完成'],
  [hot('1001'), hot('7'), hot('120'), hot('申请（新）')],
  ['1002', '3', '80', '完成'],
], { x: M, y: 1.85, w: 4.6, colW: [1.0, 0.9, 1.0, 1.7], rowH: 0.48, fontFace: FONT, fontSize: 16,
  color: C.ink, align: 'center', valign: 'middle', border: { type: 'solid', color: C.line, pt: 1 } });
box(s, [{ text: '检查：每笔退货只有一行？ ', options: {} },
  { text: '✗ 不成立', options: { bold: true, color: C.red, breakLine: true } },
  { text: '→ 第 1 版先停用', options: { bold: true, color: C.red } }],
  { x: M, y: 4.05, w: 4.6, h: 1.05, fill: C.paleRed, border: C.paleRed, size: 17, align: 'left',
    margin: 0.2 });
arrow(s, [[5.35, 3.0], [6.0, 3.0]], C.muted, 2.5);
text(s, '修复：在取值很少的列上试过滤', { x: 6.1, y: 1.4, w: 6.6, h: 0.4, fontSize: 16, bold: true });
const ok = (t) => ({ text: t, options: { color: C.green, bold: true } });
s.addTable([
  [head('试的过滤'), head('每笔一行'), head('一笔不少'), head('结论')],
  ['只算“完成”', ok('✓'), ok('✓'), ok('可用')],
  ['只算“申请”', ok('✓'), { text: '✗ 早期退货没有申请行', options: { color: C.red } },
    { text: '不行', options: { color: C.red, bold: true } }],
], { x: 6.1, y: 1.85, w: 6.63, colW: [1.6, 1.25, 2.68, 1.1], rowH: 0.5, fontFace: FONT, fontSize: 16,
  color: C.ink, align: 'center', valign: 'middle', border: { type: 'solid', color: C.line, pt: 1 } });
box(s, [{ text: '只有一个能用 → 再核对：', options: { bold: true, color: C.violet } },
  { text: '用学习时的数据（4 月）重算，新旧口径都是 313.3 万 ✓', options: { breakLine: true } },
  { text: '→ 发布第 2 版：只算“完成”的行', options: { bold: true, color: C.violet } }],
  { x: 6.1, y: 3.55, w: 6.63, h: 1.3, fill: C.paleViolet, border: C.paleViolet, size: 17, align: 'left',
    margin: 0.2 });
box(s, [{ text: '修不了就不修：', options: { bold: true, color: C.red } },
  { text: '如果追加了整份备份，“只算主表”和“只算备份”都能做到每笔一行，没法判断哪个对——宁可停用，不乱猜。' }],
  { x: M, y: 5.5, w: W - 2 * M, h: 1.0, fill: C.grey, border: C.grey, size: 17, align: 'left',
    margin: 0.25 });
s.addNotes('具体看怎么修。新写进来的“申请”行让同一笔退货出现两行，“每笔退货只有一行”不成立，第 1 版先停用。'
  + '修复时在取值很少的列上逐个试过滤：只算“完成”能做到每笔一行、一笔不少；只算“申请”会丢掉早期退货。'
  + '只有一个能用，再用学习时的数据核对，新口径算出的 4 月答案和当初一样，就发布第 2 版。'
  + '如果有两个过滤都能用，比如追加了整份备份，就没法判断，宁可停用。');

// ---------------------------------------------------------------- 10 summary

pres.addSection({ title: '小结' });
s = pres.addSlide({ masterName: 'CLOSING', sectionTitle: '小结' });
s.addText('小结', { placeholder: 'title' });
[
  ['结构', '智能体 ↔ MAVRA（请求处理、共享知识库、学习与维护）↔ 数据库'],
  ['功能', '学口径、存口径、查口径；数据变了就检查；用之前再核对'],
  ['工作流', '查口径 → 执行 SQL；数据变了 → 检查 → 修复或停用 → 重新学习'],
].forEach(([label, body], k) => {
  const y = 1.9 + k * 1.5;
  box(s, label, { x: M, y, w: 1.6, h: 0.7, fill: C.blue, border: C.blue, size: 20, bold: true,
    color: C.white });
  text(s, body, { x: M + 2.0, y: y - 0.1, w: W - 2 * M - 2.0, h: 0.9, fontSize: 20, color: C.white,
    valign: 'middle' });
});
s.addNotes('三句话收尾：结构是智能体和数据库之间的三个模块；功能是学、存、查口径，数据变了检查，用之前核对；'
  + '工作流是查口径、执行 SQL，以及口径坏了以后检查、修复或停用、重新学习。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
