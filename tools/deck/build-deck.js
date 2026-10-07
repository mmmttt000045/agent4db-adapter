// Builds docs/mavra-system.pptx, a short Chinese deck that explains MAVRA's
// structure, functions and workflows around three figures in tools/deck/figures/
// (drawn by `python3 tools/figures/build.py --deck`, rendered to PNG).
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
  ink: '1F2A37', muted: '5B6573', navy: '17233B', ice: 'CADCFC', white: 'FFFFFF',
  blue: '1D5BA6', paleBlue: 'E8F0FA', amber: 'B5671A', paleAmber: 'FBF0E2',
  violet: '6A58A3', paleViolet: 'EFECF7',
};
const W = 13.333, M = 0.6;

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

// A tinted card with an optional numbered circle, a heading and a body.
function card(slide, { x, y, w, h, n, head, body, color, pale, size = 16 }) {
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
s.addText('系统结构 · 功能 · 工作流', { placeholder: 'body' });
s.addNotes('这次只讲系统：它由哪几部分组成、各做什么、一次请求怎么走、指标定义坏了怎么办。'
  + '三张图讲的是同一个例子：门店退货金额。');

// 2 What MAVRA does ---------------------------------------------------------------
pres.addSection({ title: '功能与结构' });
s = content('MAVRA 做三件事', '功能与结构');
text(s, '数据智能体学到的指标定义（例如“门店退货金额怎么算”）会被很多智能体共享；数据一变，定义可能悄悄算错。'
  + 'MAVRA 是位于智能体和数据库之间的中间件，负责：', {
  x: M, y: 1.25, w: W - 2 * M, h: 0.85, fontSize: 16, color: C.muted, valign: 'top' });
const cw = (W - 2 * M - 2 * 0.3) / 3;
[
  { n: 1, head: '学习指标定义', color: C.violet, pale: C.paleViolet,
    body: '内置智能体（大模型）回答给出口径的题目；答案核验正确、发布前校验通过，才把定义发布到指标库，所有智能体共用。' },
  { n: 2, head: '数据变了就重新校验', color: C.blue, pale: C.paleBlue,
    body: '记录每个指标定义依赖的校验规则（如“每笔退货一行”）。数据一变，只重新校验受影响的规则；校验结果按（规则，数据版本）缓存，大家共用。规则不成立就修复，修不了就停用。' },
  { n: 3, head: '执行前把关', color: C.amber, pale: C.paleAmber,
    body: '智能体的 SQL 注明用的是哪个指标的哪一版；执行前在这条查询的快照上校验规则，过期或已停用的版本直接拒绝。' },
].forEach((c, k) => card(s, { ...c, x: M + k * (cw + 0.3), y: 2.4, w: cw, h: 4.2 }));
s.addNotes('先用一句话说清问题：指标定义被共享，数据会变，定义可能悄悄算错。'
  + 'MAVRA 做三件事：学习指标定义（紫色）、数据变了就重新校验（蓝色）、执行前把关（橙色）。'
  + '后面三张图用的是同一套颜色。');

// 3 Structure -------------------------------------------------------------------------
s = content('系统结构：一次请求怎样经过 MAVRA', '功能与结构');
figure(s, 'overview');
s.addNotes('左边是用户智能体，它发两种请求。'
  + '蓝色 1–5 是查询指标定义：智能体只说“退货金额”，查询服务从指标库读出定义；'
  + '它依赖的数据变了，而某条规则在新数据版本上还没有校验结果，就交给维护去校验，结果写入缓存，再返回有效的 v2。'
  + '橙色 6–8 是执行 SQL：智能体写好 SQL 并注明用的是 v2，执行前校验直接复用缓存里的校验结果，在同一快照上执行。'
  + '紫色是学习：内置智能体学到的定义，发布前校验通过才进入指标库。');

// 4 Workflow: query and execution ------------------------------------------------------
pres.addSection({ title: '工作流' });
s = content('工作流①：查询指标定义，再执行 SQL', '工作流');
figure(s, 'lookup');
s.addNotes('上面一行是查询指标定义：先按名称匹配；再看它用到的表的数据版本有没有变（store_returns 从 14 变成 15）；'
  + '然后逐条规则查缓存：“每笔退货一行”退货率已经校验过，直接复用；date_dim 没变，复用；'
  + '“退货都有日期”在 15 上没有结果，现在校验并写入缓存；最后返回有效的 v2。'
  + '中间是校验结果缓存：按（规则，数据版本）存，表里写明谁写入、哪一步复用。'
  + '下面一行是执行 SQL：先检查注明的 v2 能不能用；再在这条查询的快照上校验——这期间又有写入，数据版本变成 16，'
  + '所以两条规则在快照里重新校验并写入缓存；最后在同一快照上执行，结果 329.4 万。');

// 5 Workflow: learning and maintenance ---------------------------------------------------
s = content('工作流②：指标定义的学习、停用与修复', '工作流');
figure(s, 'lifecycle');
s.addNotes('跟着退货金额这个指标走一遍。内置智能体回答“4 月门店退货金额”，答案核验正确、发布前校验通过，发布 v1。'
  + '之后追加迟到的退货，这是普通写入：规则仍成立，没变的表直接用缓存，还是 v1。'
  + '再之后每笔退货多了一行“申请”状态，这是破坏性写入：“每笔退货一行”不成立，v1 停用，'
  + '不处理的话 5 月的答案会翻倍。修复时在取值少的列上逐个试过滤，只有 sr_status = 完成 能恢复每笔退货一行；'
  + '再用学习时的数据重算，结果和当初一致，于是发布 v2。'
  + '红框是另一种情况：追加了整份备份数据，两个过滤都可行，无法判断哪个对，就停用，等待重新学习。');

// 6 Summary ------------------------------------------------------------------------------
pres.addSection({ title: '小结' });
s = pres.addSlide({ masterName: 'CLOSING', sectionTitle: '小结' });
s.addText('小结', { placeholder: 'title' });
[
  ['结构', '用户智能体 → MAVRA（查询服务、指标库、内置智能体与维护）→ 数据库'],
  ['功能', '学习指标定义；数据变了重新校验，校验结果缓存共用；执行前在同一快照上校验'],
  ['工作流', '查指标定义 → 执行 SQL；数据变化 → 校验 → 修复或停用 → 重新学习'],
].forEach(([label, body], k) => {
  const y = 1.9 + k * 1.5;
  s.addShape('roundRect', { x: M, y, w: 1.6, h: 0.7, fill: { color: C.blue }, line: { color: C.blue },
    rectRadius: 0.35, objectName: `label ${label}` });
  text(s, label, { x: M, y, w: 1.6, h: 0.7, fontSize: 20, bold: true, color: C.white, align: 'center',
    valign: 'middle' });
  text(s, body, { x: M + 2.0, y: y - 0.1, w: W - 2 * M - 2.0, h: 0.9, fontSize: 20, color: C.white,
    valign: 'middle' });
});
s.addNotes('三句话收尾：结构是查询服务、指标库、内置智能体与维护；功能是学习、校验、执行前把关；'
  + '工作流是先查有效的指标定义、再在快照上校验并执行，校验结果能复用就复用。');

pres.writeFile({ fileName: OUT }).then(() => console.log(OUT));
