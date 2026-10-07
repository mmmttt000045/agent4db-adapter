// Builds docs/mavra-system.pptx, a short Chinese deck that explains MAVRA's
// structure, functions and workflows around the three system figures in
// tools/deck/figures/ (built by `python3 tools/figures/build.py --deck` and
// rendered to PNG). Usage: node build-deck.js [--out path]
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
  ink: '1F2A37', muted: '5B6573', navy: '17233B', ice: 'CADCFC', white: 'FFFFFF',
  blue: '1D5BA6', paleBlue: 'E8F0FA', amber: 'B5671A', paleAmber: 'FBF0E2',
  violet: '6A58A3', paleViolet: 'EFECF7', red: 'B5392A', paleRed: 'FBEAE7',
};
const W = 13.333, M = 0.6;                      // slide width and side margin, inches

// Width / height of a figure PNG, from its header.
function aspect(file) {
  const buf = fs.readFileSync(file);
  return buf.readUInt32BE(16) / buf.readUInt32BE(20);
}

function figure(slide, name, top, maxH) {
  const file = path.join(FIG, `${name}-zh.png`);
  const r = aspect(file);
  let w = W - 2 * M, h = w / r;
  if (h > maxH) { h = maxH; w = h * r; }
  slide.addImage({ path: file, x: (W - w) / 2, y: top, w, h, objectName: name });
  return top + h;
}

function text(slide, value, opts) {
  slide.addText(value, { fontFace: FONT, color: C.ink, margin: 0, isTextBox: true, ...opts });
}

// A tinted card with a numbered circle, a heading and a body.
function card(slide, { x, y, w, h, n, head, body, color, pale, size = 15 }) {
  slide.addShape('roundRect', { x, y, w, h, fill: { color: pale }, line: { color: pale },
    rectRadius: 0.12, objectName: `card ${head}` });
  let top = y + (n ? 0.3 : 0.2);
  if (n) {
    slide.addShape('ellipse', { x: x + 0.3, y: top, w: 0.55, h: 0.55, fill: { color }, line: { color } });
    text(slide, String(n), { x: x + 0.3, y: top, w: 0.55, h: 0.55, fontSize: 20, bold: true,
      color: C.white, align: 'center', valign: 'middle' });
    top += 0.75;
  }
  text(slide, head, { x: x + 0.3, y: top, w: w - 0.6, h: 0.45, fontSize: 20, bold: true, color });
  const by = top + 0.55;
  text(slide, body, { x: x + 0.3, y: by, w: w - 0.6, h: y + h - by - 0.2, fontSize: size,
    valign: 'top', lineSpacingMultiple: 1.15 });
}

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.title = 'MAVRA：系统结构、功能与工作流';
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

pres.defineSlideMaster({
  title: 'TITLE', background: { color: C.navy },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: 0.8, y: 2.2, w: 11.7, h: 1.8,
      fontFace: FONT, fontSize: 40, bold: true, color: C.white, valign: 'bottom', align: 'left', margin: 0 },
      text: '' } },
    { placeholder: { options: { name: 'body', type: 'body', x: 0.8, y: 4.3, w: 11.7, h: 0.7,
      fontFace: FONT, fontSize: 22, color: C.ice, valign: 'top', margin: 0 }, text: '' } },
  ],
});
pres.defineSlideMaster({
  title: 'CONTENT', background: { color: C.white },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: M, y: 0.35, w: W - 2 * M, h: 0.8,
      fontFace: FONT, fontSize: 30, bold: true, color: C.ink, valign: 'middle', align: 'left', margin: 0 },
      text: '' } },
  ],
  slideNumber: { x: W - 1.1, y: 7.0, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color: C.muted,
    align: 'right' },
});
pres.defineSlideMaster({
  title: 'CLOSING', background: { color: C.navy },
  objects: [
    { placeholder: { options: { name: 'title', type: 'title', x: 0.8, y: 0.6, w: 11.7, h: 0.9,
      fontFace: FONT, fontSize: 32, bold: true, color: C.white, valign: 'middle', align: 'left', margin: 0 },
      text: '' } },
  ],
  slideNumber: { x: W - 1.1, y: 7.0, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 10, color: C.ice,
    align: 'right' },
});

// 1 Title -----------------------------------------------------------------------
pres.addSection({ title: '开场' });
let s = pres.addSlide({ masterName: 'TITLE', sectionTitle: '开场' });
s.addText('MAVRA：让共享的指标口径\n在数据变化后仍然可靠', { placeholder: 'title' });
s.addText('系统结构 · 功能 · 工作流', { placeholder: 'body' });
s.addNotes('这次只讲系统本身：它由哪几部分组成、各做什么、一个请求怎么走、口径怎么维护。'
  + '三张图讲的是同一个例子：门店退货金额。');

// 2 What MAVRA does ---------------------------------------------------------------
pres.addSection({ title: '功能与结构' });
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '功能与结构' });
s.addText('MAVRA 做三件事', { placeholder: 'title' });
text(s, '数据智能体学到的指标口径（例如“门店退货金额怎么算”）会被很多智能体共享；数据一变，口径可能悄悄算错。'
  + 'MAVRA 是位于智能体和数据库之间的中间件，负责：', {
  x: M, y: 1.3, w: W - 2 * M, h: 0.85, fontSize: 16, color: C.muted, valign: 'top' });
const cw = (W - 2 * M - 2 * 0.3) / 3;
[
  { n: 1, head: '学习并共享口径', color: C.violet, pale: C.paleViolet,
    body: '内置分析优化器（一个大模型智能体）回答给出口径的学习题；判题正确后提取成定义，通过准入检查才发布，所有用户端智能体共用。' },
  { n: 2, head: '数据变了就维护', color: C.blue, pale: C.paleBlue,
    body: '记录每个定义依赖的条件，例如“每笔退货一行”。表一变，只重查受影响的条件；检查结果按“条件 + 表版本”保存，跨定义、跨智能体复用。条件失败就修复，修不了就失效。' },
  { n: 3, head: '使用时把关', color: C.amber, pale: C.paleAmber,
    body: '智能体的 SQL 要声明用了哪个定义的哪个修订。执行前在这条查询的同一快照上核对条件；过时或已失效的修订直接拒绝。' },
].forEach((c, k) => card(s, { ...c, x: M + k * (cw + 0.3), y: 2.5, w: cw, h: 3.9, size: 16 }));
s.addNotes('先用一句话说清问题：口径被共享，数据会变，口径可能悄悄算错。'
  + 'MAVRA 就做三件事：学到口径并共享（紫色）、数据变了就维护（蓝色）、使用时把关（橙色）。'
  + '后面三张图里用的是同一套颜色。');

// 3 Structure ----------------------------------------------------------------------
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '功能与结构' });
s.addText('系统结构：一个请求怎样流经 MAVRA', { placeholder: 'title' });
let bottom = figure(s, 'overview', 1.35, 4.9);
text(s, [
  { text: '请求处理', options: { bold: true, color: C.blue } },
  { text: '：查找、同快照验证      ' },
  { text: '共享知识库', options: { bold: true, color: C.blue } },
  { text: '：定义、检查结果      ' },
  { text: '学习与维护', options: { bold: true, color: C.violet } },
  { text: '：分析优化器、维护' },
], { x: M, y: bottom + 0.35, w: W - 2 * M, h: 0.45, fontSize: 16 });
s.addNotes('左边是用户端智能体，它发两种请求。'
  + '蓝色 1–5 是文本请求：智能体只说“退货金额”，查找从共享知识库读出定义；'
  + '如果某个条件在当前表版本上还没有检查结果，就交给维护去查，查完存回去，再把有效定义返回。'
  + '橙色 6–8 是 SQL 请求：智能体写好 SQL 并声明用了修订 2，同快照验证复用已有的检查结果，在同一快照上执行查询。'
  + '紫色是学习：分析优化器学到的定义经准入检查后发布进来。');

// 4 Workflow: request handling -----------------------------------------------------
pres.addSection({ title: '工作流' });
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '工作流' });
s.addText('工作流①：查找有效定义，在快照上执行', { placeholder: 'title' });
bottom = figure(s, 'lookup', 1.3, 5.1);
text(s, [
  { text: '检查结果的复用：', options: { bold: true, color: C.blue } },
  { text: '按“条件 + 表版本”保存，能复用就复用，只有表版本变了才重新检查。' },
], { x: M, y: bottom + 0.2, w: W - 2 * M - 1.2, h: 0.45, fontSize: 16 });
s.addNotes('上面一行是查找：先按名称匹配，再比较定义读过的表有没有变（store_returns 从 14 变成 15），'
  + '然后逐个条件查检查结果：“每笔退货一行”退货率已经查过，直接复用；date_dim 没变，复用；'
  + '“日期不丢失”在 15 上没有结果，现在查并存进去。最后返回有效的修订 2。'
  + '下面一行是执行：智能体按返回的字段写 SQL，声明修订 2；先核对这个修订能不能用，'
  + '再在查询的快照上核对条件——这期间又有一次写入，表版本变成 16，所以两个条件在快照里重查并存入；'
  + '最后在同一快照上执行，得到 3,294,349.93。中间的表就是检查结果，列出谁存的、哪一步复用了它。');

// 5 Workflow: learning and maintenance ---------------------------------------------
s = pres.addSlide({ masterName: 'CONTENT', sectionTitle: '工作流' });
s.addText('工作流②：口径的学习、失效与修复', { placeholder: 'title' });
bottom = figure(s, 'lifecycle', 1.35, 4.2);
const tw = (W - 2 * M - 2 * 0.3) / 3;
[
  { head: '正常写入', color: C.blue, pale: C.paleBlue,
    body: '只重查受影响的条件，其余结果复用；修订不变' },
  { head: '破坏性写入', color: C.amber, pale: C.paleAmber,
    body: '先失效；只有唯一的修复且回归测试通过，才发布新修订' },
  { head: '没有唯一修复', color: C.red, pale: C.paleRed,
    body: '宁可失效，等新的判题任务重新学习' },
].forEach((c, k) => card(s, { ...c, x: M + k * (tw + 0.3), y: bottom + 0.3, w: tw, h: 7.0 - bottom - 0.3,
  size: 14 }));
s.addNotes('跟着退货金额这个定义走一遍。分析优化器回答“4 月门店退货金额”，答案判对、通过准入，发布修订 1。'
  + '之后追加迟到的退货，这是正常写入：条件仍成立，没变的表直接复用结果，还是修订 1。'
  + '再之后每笔退货多了一行申请状态，这是破坏性写入：“每笔退货一行”不成立，修订 1 失效，'
  + '不维护的话 5 月的答案会翻倍。修复时在取值很少的列上逐个试过滤，只有 sr_status = 完成 能恢复每笔退货一行，'
  + '而且在学习时刻的数据上和智能体当初的 SQL 答案相同，于是发布修订 2。'
  + '红框是另一种情况：追加整份备份副本后有两个过滤都能用，无法判断哪个对，就宁可失效，等重新学习。');

// 6 Summary --------------------------------------------------------------------------
pres.addSection({ title: '小结' });
s = pres.addSlide({ masterName: 'CLOSING', sectionTitle: '小结' });
s.addText('小结', { placeholder: 'title' });
[
  ['结构', '请求处理、共享知识库、学习与维护三个模块，位于用户端智能体和 SQL 数据库之间'],
  ['功能', '学习并共享口径；数据变化后维护；使用时在同一快照上把关'],
  ['工作流', '文本请求查到有效定义，SQL 请求在快照上验证并执行；检查结果跨定义、跨智能体复用'],
].forEach(([label, body], k) => {
  const y = 1.9 + k * 1.5;
  s.addShape('roundRect', { x: M, y, w: 1.6, h: 0.7, fill: { color: C.blue }, line: { color: C.blue },
    rectRadius: 0.35, objectName: `label ${label}` });
  text(s, label, { x: M, y, w: 1.6, h: 0.7, fontSize: 20, bold: true, color: C.white, align: 'center',
    valign: 'middle' });
  text(s, body, { x: M + 2.0, y: y - 0.1, w: W - 2 * M - 2.0, h: 0.9, fontSize: 20, color: C.white,
    valign: 'middle' });
});
s.addNotes('最后用三句话收尾：结构是三个模块；功能是学习、维护、把关；'
  + '工作流是先查有效定义、再在快照上验证执行，检查结果能复用就复用。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
