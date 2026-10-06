// MAVRA research presentation (2026-10-12), written for an audience new to the
// direction. Numbers come from the paper's result macros and the archived
// session / matched-producer studies; the build fails if any of them is missing
// or if the paper and the archive disagree.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const pptxgen = require('pptxgenjs');

const args = process.argv.slice(2);
const positional = args[0] && !args[0].startsWith('--') ? args.shift() : null;
function option(flag, fallback) {
  const i = args.indexOf(flag);
  if (i < 0) return fallback;
  if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`Missing value for ${flag}`);
  return args[i + 1];
}
const overleaf = path.resolve(positional || path.join(__dirname, '../../overleaf'));
const repo = path.dirname(overleaf);
const reportDate = option('--date', new Date().toISOString().slice(0, 10));
if (!/^\d{4}-\d{2}-\d{2}$/.test(reportDate) || new Date(reportDate).toISOString().slice(0, 10) !== reportDate) {
  throw new Error('Report date must be a valid YYYY-MM-DD date');
}
const output = path.resolve(option('--out', path.join(repo, `docs/mavra-report-${reportDate}.pptx`)));
const sources = new Map();
function read(relative) {
  const file = path.join(repo, relative);
  const data = fs.readFileSync(file);
  sources.set(relative, crypto.createHash('sha256').update(data).digest('hex'));
  return data.toString('utf8');
}
const M = {};
for (const file of ['numbers.tex', 'scen-ds.tex', 'review.tex', 'numbers-prev.tex', 'session-latency.tex']) {
  const relative = path.relative(repo, path.join(overleaf, 'gen', file));
  const text = read(relative);
  const re = /\\newcommand\{\\(\w+)\}\{/g;
  let match;
  while ((match = re.exec(text))) {
    let depth = 1, i = re.lastIndex;
    const start = i;
    while (i < text.length && depth) {
      if (text[i] === '{') depth++;
      else if (text[i] === '}') depth--;
      i++;
    }
    if (depth) throw new Error(`Unclosed macro ${match[1]} in ${file}`);
    M[match[1]] = text.slice(start, i - 1).replace(/\{,\}/g, ',').replace(/\\,/g, ' ');
    re.lastIndex = i;
  }
}
const usedMacros = new Set();
function n(key) {
  if (!(key in M)) throw new Error(`Missing paper result macro: ${key}`);
  usedMacros.add(key);
  return M[key];
}
function num(key) {
  const value = Number(n(key).replace(/,/g, ''));
  if (!Number.isFinite(value)) throw new Error(`Non-numeric result macro: ${key}`);
  return value;
}
const session = JSON.parse(read('exp/2026-10-03-session-latency/stats.json'));
const memory = JSON.parse(read('exp/2026-10-03-shared-memory/analysis/summary.json')).memory;
const sessionPolicy = (name) => {
  const row = session.by_policy.find((r) => r.policy === name);
  if (!row) throw new Error(`Missing session policy: ${name}`);
  return row;
};
const phaseMean = (policy, phase) => {
  const row = session.rows.find((r) => r.policy === policy && r.phase === phase);
  if (!row) throw new Error(`Missing phase: ${policy}/${phase}`);
  return row.mean_completion_s;
};
const fixed = (value, digits = 2) => value.toFixed(digits);
const integer = (value) => Math.round(value).toLocaleString('en-US');
const mem = (policy, key) => memory.primary[policy].per_attempt[key];
// Fail before writing if the paper and the archived study have diverged.
for (const [prefix, policy] of [['None', 'no-share'], ['Def', 'definition'], ['Cache', 'definition-cache'], ['Cond', 'condition']]) {
  const row = sessionPolicy(policy);
  if (Number(n(`Sl${prefix}N`)) !== row.n || Number(n(`Sl${prefix}Correct`)) !== row.correct || n(`Sl${prefix}Mean`) !== fixed(row.mean_completion_s)) {
    throw new Error(`Paper/archive mismatch for ${policy}`);
  }
}
for (const file of ['paper.tex', 'sections/abstract.tex', 'sections/01-introduction.tex', 'sections/02-background.tex',
  'sections/03-overview.tex', 'sections/04-model.tex', 'sections/05-maintenance.tex', 'sections/06-enforcement.tex',
  'sections/evaluation/setup.tex', 'sections/evaluation/validity.tex', 'sections/evaluation/concurrency.tex',
  'sections/evaluation/repair.tex', 'sections/evaluation/maintenance-cost.tex', 'sections/evaluation/scenarios.tex',
  'sections/09-limitations.tex', 'sections/10-conclusion.tex', 'tables/workload.tex', 'figures/scenario-changes.tex']) {
  read(path.relative(repo, path.join(overleaf, file)));
}

// ---------------------------------------------------------------- styling ----
const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
const W = 13.333333, H = 7.5;
const FONT = 'Microsoft YaHei';
const C = {
  navy: '1B2A41', ink: '24364D', muted: '53657A', light: 'EEF2F7', line: 'D9E2EE', white: 'FFFFFF',
  blue: '2A78D6', orange: 'EB6834', green: '198861', purple: '8250AD', gold: 'C48B0A',
  paleBlue: 'E6EFFB', paleOrange: 'FDEDE4', paleGreen: 'E3F2EB', palePurple: 'EFE8F7',
};
pres.theme = { headFontFace: FONT, bodyFontFace: FONT, lang: 'zh-CN' };
pres.title = `MAVRA：让数据智能体共享的指标定义在数据变化后依然正确 · ${reportDate}`;
pres.subject = 'Keeping Shared Metric Definitions Valid for Data Agents';
pres.author = 'MAVRA';
pres.company = 'Research';
pres.lang = 'zh-CN';
const slides = [];
let objects = 0;
function boxCheck(x, y, w, h, label) {
  if (![x, y, w, h].every(Number.isFinite) || x < -0.001 || y < -0.001 || w < 0 || h < 0 || x + w > W + 0.02 || y + h > H + 0.02) {
    throw new Error(`Out of slide bounds: ${label}: ${[x, y, w, h].join(', ')}`);
  }
}
function tx(s, text, x, y, w, h, size = 17, opts = {}) {
  boxCheck(x, y, w, h, typeof text === 'string' ? text.slice(0, 40) : 'rich text');
  s.addText(text, { x, y, w, h, fontFace: FONT, fontSize: size, color: C.ink, margin: 0,
    breakLine: false, valign: 'top', lineSpacingMultiple: 1.12, isTextBox: true,
    objectName: `text-${++objects}`, ...opts });
}
function shape(s, x, y, w, h, fill = C.light, line = fill, type = 'roundRect', radius = 0.1) {
  boxCheck(x, y, w, h, type);
  s.addShape(pres.ShapeType[type], { x, y, w, h, rectRadius: radius,
    fill: { color: fill }, line: { color: line, width: 0.8 }, objectName: `shape-${++objects}` });
}
function circle(s, x, y, d, color, text, size = 15, textColor = C.white) {
  boxCheck(x, y, d, d, 'circle');
  s.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color }, line: { color, width: 0 }, objectName: `circle-${++objects}` });
  if (text !== undefined) tx(s, String(text), x, y, d, d, size, { bold: true, color: textColor, align: 'center', valign: 'middle' });
}
function arrow(s, x1, y1, x2, y2, color = C.blue, width = 1.8) {
  s.addShape(pres.ShapeType.line, { x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color, width, beginArrowType: 'none', endArrowType: 'triangle' }, objectName: `arrow-${++objects}` });
}
function slide(title, section, source, notes, { dark = false, appendix = false } = {}) {
  const s = pres.addSlide();
  s.background = { color: dark ? C.navy : C.white };
  const page = slides.length + 1;
  slides.push({ page, title, section, source, appendix });
  if (!dark) {
    tx(s, `${appendix ? '附录 · ' : ''}${section}`, 0.6, 0.28, 11.8, 0.26, 11, { bold: true, color: C.blue, charSpacing: 1.5 });
    const titleSize = title.length > 30 ? 25 : title.length > 24 ? 27 : 29;
    tx(s, title, 0.6, 0.6, 12.1, 0.72, titleSize, { bold: true, color: C.navy });
  }
  tx(s, `MAVRA · ${reportDate} 组会汇报`, 0.6, 7.1, 4.35, 0.22, 9.5, { color: dark ? 'C4D2E4' : C.muted });
  tx(s, source, 5.0, 7.1, 7.1, 0.22, 8.5, { color: dark ? 'C4D2E4' : C.muted, align: 'right' });
  tx(s, String(page).padStart(2, '0'), 12.2, 7.08, 0.5, 0.24, 10.5, { align: 'right', color: dark ? C.white : C.muted });
  s.addNotes(`${notes}\n\n依据：${source}\n报告日期：${reportDate}。内容对应当前 overleaf/ 正文；归档结果单独标注。`);
  return s;
}
function card(s, x, y, w, h, head, body, color = C.blue, { size = 16, badge = null, fill = C.light, headSize = 18 } = {}) {
  shape(s, x, y, w, h, fill, fill);
  let hx = x + 0.24;
  if (badge !== null) { circle(s, x + 0.22, y + 0.22, 0.44, color, badge, 15); hx = x + 0.8; }
  tx(s, head, hx, y + 0.24, w - (hx - x) - 0.2, 0.46, headSize, { bold: true, color, valign: 'middle' });
  tx(s, body, x + 0.24, y + 0.9, w - 0.48, h - 1.06, size);
}
function stat(s, x, y, w, value, label, color = C.blue, size = 38, labelH = 0.85) {
  tx(s, value, x, y, w, 0.85, size, { bold: true, color });
  tx(s, label, x, y + 0.97, w, labelH, 15, { color: C.muted });
}
function bullets(s, items, x, y, w, h, size = 17, color = C.ink, space = 12) {
  tx(s, items.map((text, i) => ({ text, options: { bullet: { indent: size }, hanging: 4,
    breakLine: i < items.length - 1, paraSpaceAfter: space } })), x, y, w, h, size, { color });
}
function takeaway(s, text, y = 6.3, color = C.blue, fill = C.light) {
  shape(s, 0.6, y, 12.1, 0.57, fill, fill);
  tx(s, text, 0.82, y + 0.12, 11.66, 0.34, 16, { color, bold: true });
}
function table(s, rows, x, y, widths, rowH = 0.6, size = 15, highlight = null) {
  const w = widths.reduce((a, b) => a + b, 0);
  boxCheck(x, y, w, rowH * rows.length, 'table');
  const data = rows.map((row, i) => row.map((cell, j) => ({ text: String(cell), options: {
    bold: i === 0 || (highlight !== null && i === highlight), fontSize: size,
    color: i === 0 ? C.white : highlight === i ? C.blue : C.ink,
    fill: { color: i === 0 ? C.navy : i % 2 ? C.white : C.light },
    align: j > 0 && /^[\d.,%+−/ –-]+$/.test(String(cell)) ? 'right' : 'left',
    valign: 'middle', margin: [0.045, 0.085, 0.045, 0.085],
  } })));
  s.addTable(data, { x, y, w, colW: widths, rowH, fontFace: FONT, fontSize: size,
    border: { type: 'solid', color: C.white, pt: 1.2 }, autoPage: false, objectName: `table-${++objects}` });
}
function chart(s, data, x, y, w, h, colors, max = 100, options = {}) {
  boxCheck(x, y, w, h, 'chart');
  s.addChart(pres.ChartType.bar, data, {
    x, y, w, h, barDir: 'col', barGrouping: 'clustered', chartColors: colors,
    showLegend: data.length > 1, legendPos: 'b', legendFontFace: FONT, legendFontSize: 12,
    showValue: true, dataLabelPosition: 'outEnd', dataLabelFontFace: FONT, dataLabelFontSize: 13,
    catAxisLabelFontFace: FONT, catAxisLabelFontSize: 12, catAxisLabelColor: C.muted,
    valAxisLabelFontFace: FONT, valAxisLabelFontSize: 10, valAxisLabelColor: C.muted,
    valAxisMinVal: 0, valAxisMaxVal: max, valGridLine: { color: C.line, width: 0.5 },
    catGridLine: { style: 'none' }, showBorder: false, showCatName: false,
    showTitle: false, showShadow: false, chartArea: { fill: { color: C.white }, border: { color: C.white, pt: 0 } },
    plotArea: { fill: { color: C.white }, border: { color: C.white, pt: 0 } }, ...options,
  });
}
// A numbered process step: tinted box, number circle, heading, body.
function step(s, x, y, w, h, number, head, body, color = C.blue, fill = C.light, size = 15) {
  shape(s, x, y, w, h, fill, fill);
  circle(s, x + 0.2, y + 0.2, 0.42, color, number, 15);
  tx(s, head, x + 0.74, y + 0.2, w - 0.9, 0.44, 17, { bold: true, color, valign: 'middle' });
  tx(s, body, x + 0.22, y + 0.8, w - 0.42, h - 0.95, size);
}

// ================================================================ slides ====
// 01 Cover.
let s = slide('MAVRA', '封面', '论文标题 / 摘要',
  '开场一句话：数据智能体会把“业务指标怎么算”自己摸索出来，并把结果共享给后面的会话；数据一变，这些共享的 SQL 可能悄悄算错。我们做的事是让数据库替智能体记住“这个定义为什么成立”，数据变了就重新核对，用的时候只在核对通过的数据上执行，坏了谨慎修，修不了就让它失效。今天先讲背景和问题，再讲做法和实验，最后是进展和想讨论的问题。', { dark: true });
tx(s, 'MAVRA', 0.8, 1.05, 11.6, 0.83, 52, { bold: true, color: C.white });
tx(s, '让数据智能体共享的指标定义\n在数据变化后依然正确', 0.8, 2.25, 11.7, 1.6, 34, { bold: true, color: C.white });
tx(s, 'Keeping Shared Metric Definitions Valid for Data Agents', 0.83, 4.3, 11.6, 0.44, 19, { color: 'D6E2F1' });
tx(s, `${reportDate.replace(/-/g, ' / ')}  ·  组会汇报  ·  投稿目标 SIGMOD 2027`, 0.83, 5.25, 11.6, 0.45, 18, { color: 'D6E2F1' });
tx(s, '背景  →  问题  →  做法  →  实验  →  进展与讨论', 0.83, 6.1, 11.6, 0.36, 15, { color: 'AFC4DE' });

// 02 One-page summary.
s = slide('一页看懂：问题、做法和效果', '概要', '论文摘要；gen/scen-ds.tex、review.tex、session-latency.tex',
  `这页是给第一次接触这个方向的听众的地图。四个框按“背景—问题—做法—效果”排列，后面每一节都对应其中一个框。三个数字分别来自三组不同实验，不是同一个分母：${n('DsCondModeled')}% 对 ${n('DsTrajModeled')}% 是真实智能体在破坏性数据变化下的最终答案正确率；0 违规是并发写入下的系统层实验；64 秒到 38 秒是固定定义库的会话实验。`);
card(s, 0.6, 1.62, 2.85, 3.95, '背景', '大模型智能体靠探索数据库来回答业务问题。\n\n“退货金额怎么算”这类口径是业务知识，表结构里没有；学一次很贵，所以越来越多系统让智能体把学到的口径共享给后来的会话。', C.blue, { badge: '1', size: 15 });
card(s, 3.68, 1.62, 2.85, 3.95, '问题', '共享的口径是在某一时刻的数据上学到的。\n\n日常的数据更新（比如多了一种状态行）不改表结构，却让共享的 SQL 照常执行、悄悄返回错误汇总值；用它的智能体看不出来。', C.orange, { badge: '2', size: 15 });
card(s, 6.76, 1.62, 2.85, 3.95, '做法', '让数据库替智能体记住“定义为什么成立”：\n\n把成立条件记录为可执行检查，随数据版本维护，查询只在检查通过的数据上执行；坏了只做唯一且过回归的修复，否则让它失效。', C.green, { badge: '3', size: 15 });
card(s, 9.84, 1.62, 2.85, 3.95, '效果', `破坏性数据变化下，智能体正确率 ${n('DsCondModeled')}%，对照的轨迹检索 ${n('DsTrajModeled')}%。\n\n并发写入下零次在违规数据上作答。\n\n使用者的任务从 ${n('SlNoneMean')} 秒缩到 ${n('SlCondMean')} 秒，token 少 ${n('SlCondInputSaveNone')}%。`, C.purple, { badge: '4', size: 15 });
takeaway(s, '一句话：共享让智能体少探索；维护让共享的知识在变化的数据上继续成立。', 5.95);

// 03 Background: what a data agent does.
s = slide('数据智能体：先摸清数据库，再写 SQL 回答业务问题', '背景', `论文 §2.1、§2.2；工作负载刻画 exp/2026-10-01-workload-characterization/`,
  '先解释“数据智能体”：一个大模型，拿到业务问题后不能直接写 SQL，它要先用工具列出表、看列、试探几条 SQL，弄清楚数据长什么样，最后才给答案。这页右边列的四件事就是它每道题都要摸索的内容。强调一点：真正难的不是 SQL 语法，而是弄清“这个指标到底怎么算”。下面的两个数字说明摸索的代价：不共享任何知识时，每道题平均要 5.6 轮工具交互，正确率只有 32%。');
const flow = [['业务问题', '“上个月门店\n退货金额是多少？”', C.purple], ['智能体', '大模型\n规划与推理', C.blue], ['工具调用', '列出表 · 查看列\n试探 SQL · 执行', C.blue], ['PostgreSQL', '事实表与维度表', C.green], ['答案', '金额 + 计算过程', C.purple]];
flow.forEach(([head, body, color], i) => {
  const x = 0.6 + i * 2.5;
  shape(s, x, 1.7, 2.2, 1.55, C.light, C.light);
  tx(s, head, x + 0.2, 1.84, 1.8, 0.4, 17, { bold: true, color });
  tx(s, body, x + 0.2, 2.3, 1.85, 0.85, 14, { color: C.ink });
  if (i < flow.length - 1) arrow(s, x + 2.22, 2.47, x + 2.48, 2.47);
});
card(s, 0.6, 3.6, 6.4, 2.45, '每道题都要摸清的事', '① 哪张表装着退货，哪一列是金额\n② 一笔退货对应几行（粒度）\n③ 用哪个日期把退货归到“上个月”\n④ 哪些行不该算（取消、申请中……）', C.blue, { size: 15.5 });
stat(s, 7.5, 3.75, 2.5, `${n('ScenHoldTurnsNoShareModelA')} 轮`, '不共享知识时\n每道题的工具交互轮数', C.orange, 36);
stat(s, 10.3, 3.75, 2.4, `${n('DsNoShareAll')}%`, '不共享知识时\n端到端正确率', C.orange, 36);
takeaway(s, '真正难的不是写 SQL，而是弄清“口径”：哪些行算一次、怎么归期、怎么过滤。');

// 04 Background: what a metric definition is and why it is business knowledge.
s = slide('“口径”是业务知识，表结构里没有', '背景', '论文 §1、§2.2；Spider 2.0、BIRD 的数字取自原论文',
  '用退货金额把“口径”讲具体：事实表、度量、粒度、日期角色、过滤。这些东西 SQL 里不写、表结构也不保证，是业务上的约定。右边三个数字说明智能体离不开这类知识：Spider 2.0 的企业级任务上，o1-preview 智能体只完成 21.3%；BIRD 上给 GPT-4 专家标注的业务知识后正确率从 34.9% 升到 54.9%；我们自己的实验里，把学到的口径共享给新会话，正确率从 32% 升到 75%。所以口径要么有人告诉它，要么它自己摸索出来再记住。');
card(s, 0.6, 1.62, 5.6, 4.45, '退货金额的口径', '事实表　store_returns\n度量　　SUM(sr_return_amt)\n粒度　　小票号 + 商品 = 一笔退货\n时间　　按退货日期归期\n过滤　　只算“已完成”的退货\n\n这五条 SQL 里不会写明，表结构也不强制。', C.blue, { size: 16 });
const evid = [[`${'21.3'}%`, 'Spider 2.0 企业级任务上\no1-preview 智能体的完成率', C.orange], ['34.9% → 54.9%', 'BIRD：给 GPT-4 专家标注的\n业务知识前后的正确率', C.green], [`${n('DsNoShareAll')}% → ${n('DsNoguardAll')}%`, '我们的实验：新会话拿到\n共享口径前后的正确率', C.blue]];
evid.forEach(([v, l, color], i) => {
  shape(s, 6.6, 1.62 + i * 1.5, 6.1, 1.35, C.white, C.line);
  tx(s, v, 6.85, 1.78 + i * 1.5, 2.9, 0.6, 26, { bold: true, color, valign: 'middle' });
  tx(s, l, 9.75, 1.72 + i * 1.5, 2.85, 1.15, 13.5, { color: C.muted, valign: 'middle' });
});
takeaway(s, '口径必须有人告诉智能体，或者由它自己摸索出来再记住，否则每道题都从零开始。');

// 05 Background: the trend toward shared learned definitions.
s = slide('趋势：把智能体学到的口径共享给后来的会话', '背景', '论文 §1、§2.2、§8；gen/numbers.tex（留出题的轮数与 token）',
  '业界和学术界都在往这个方向走：指标层让工程师手工声明口径；DataLab 这类系统从脚本历史和血缘里推导；AgentSM 这类工作直接复用智能体的成功轨迹。共享的收益很明确，下面三个数字是我们端到端实验里“不共享”对“共享”的差别。但共享之后，口径就变成了一个长期存在的东西，而它底下的数据库每天都在变。这就是下一节的问题。');
card(s, 0.6, 1.62, 3.9, 2.55, '人工声明的指标层', 'Databricks metric views、dbt 语义层：\n工程师手工写出度量、键和关联。', C.purple, { badge: 'A', size: 15 });
card(s, 4.7, 1.62, 3.9, 2.55, '从历史里推导', 'DataLab：用大模型从脚本历史和血缘\n生成派生列的计算逻辑。', C.purple, { badge: 'B', size: 15 });
card(s, 8.8, 1.62, 3.9, 2.55, '复用智能体轨迹', 'AgentSM、智能体记忆系统：\n把成功轨迹存起来，按题面检索复用。', C.purple, { badge: 'C', size: 15 });
stat(s, 0.85, 4.45, 3.6, `${n('DsNoShareAll')}% → ${n('DsNoguardAll')}%`, '共享口径后的端到端正确率', C.blue, 32);
stat(s, 4.95, 4.45, 3.6, `${n('ScenHoldTurnsNoShareModelA')} → ${n('ScenHoldTurnsCondModelA')} 轮`, '每道留出题的工具交互轮数', C.blue, 32);
stat(s, 9.05, 4.45, 3.6, `−${n('ScenHoldTokSaveModelA')}%`, '每道留出题的输入 token', C.blue, 32);
takeaway(s, '共享的口径成了“长期状态”，可它底下的数据库每天都在变。', 6.3, C.orange, C.paleOrange);

// 06 Problem: the concrete story.
s = slide('SQL 照常执行，退货金额却被算了两次', '问题', '论文 §1、§2.3（贯穿例子）',
  '这是论文引言里的例子，建议讲慢一点。第一步：Agent A 探索时发现每笔退货只有一条“完成”记录，小票号加商品就能唯一确定一笔退货，于是直接 SUM。第二步：ETL 改动后，每笔新退货还会多一条“申请中”的状态行；表名、列名、类型都没变。第三步：Agent B 复用共享的 SQL，照常执行，结果把很多退货算了两次：某个期间返回 659 万，正确值是 329 万。学的那个会话已经结束，用的会话没见过当初的证据，执行成功也看不出错。');
card(s, 0.6, 1.65, 3.6, 2.55, 'Agent A 学到口径', '每笔退货 = 一条“完成”记录\n小票号 + 商品 唯一\nSQL：SUM(sr_return_amt)', C.blue, { badge: '1', size: 15 });
card(s, 4.86, 1.65, 3.6, 2.55, 'ETL 追加状态变更行', '每笔新退货多一条“申请中”行\n键不再唯一\n表名、列名、类型都没变', C.orange, { badge: '2', size: 15 });
card(s, 9.12, 1.65, 3.6, 2.55, 'Agent B 复用 SQL', '学习者的会话早已结束\n新会话没有基准真值\n执行成功，看不出重复计数', C.purple, { badge: '3', size: 15 });
arrow(s, 4.28, 2.9, 4.78, 2.9); arrow(s, 8.54, 2.9, 9.04, 2.9);
stat(s, 0.85, 4.55, 5.7, '6,588,699.86', '共享 SQL 返回的单期退货金额', C.orange, 37);
stat(s, 7.0, 4.55, 5.7, '3,294,349.93', '该期间真实的已完成退货金额', C.green, 37);
takeaway(s, '共享保存了业务知识，也让一次过期的观测传播给之后的每个智能体。', 6.3, C.orange, C.paleOrange);

// 07 Problem: why existing safeguards do not catch it.
s = slide('为什么现有手段挡不住', '问题', `论文 §1、§2.4、§7.2、§7.6；gen/review.tex、scen-ds.tex`,
  `听众可能会问：数据库和数据工程不是早有一套工具吗？四条路逐一说明。按表结构跟踪变化：表没变，什么也看不到，回放实验里按模式变更失效给出 ${n('RpSchemaWrongModeled')} 个错误答案。dbt 式的数据测试：按表测，不知道哪个口径依赖哪条性质，测试一失败只能让整张表上的定义全部失效，少答对 ${integer(num('RpCondCorrect') - num('RpTableCorrect'))} 题。指标层：Databricks 的文档明确写了声明的连接性质“不在运行时验证”。让智能体自己查：轨迹里只有 16% 的会话会检查键唯一性；就算提示它去查，破坏性变化下也只从 ${n('DsTrajModeled')}% 提到 ${n('DsTrajVerifyModeled')}%，而由系统维护是 ${n('DsCondModeled')}%。`);
card(s, 0.6, 1.62, 2.85, 3.75, '按表结构跟踪', '表名、列名、类型都没变，\n所以什么也看不到。', C.orange, { badge: '1', size: 15, headSize: 16.5 });
tx(s, `${n('RpSchemaWrongModeled')} 个错误答案`, 0.84, 4.5, 2.4, 0.4, 17, { bold: true, color: C.orange });
tx(s, '回放实验，按模式变更失效', 0.84, 4.9, 2.4, 0.3, 12.5, { color: C.muted });
card(s, 3.68, 1.62, 2.85, 3.75, '数据质量测试', 'dbt 式按表测试：不知道哪个口径依赖哪条性质，失败只能让整张表上的口径失效。', C.orange, { badge: '2', size: 15, headSize: 16.5 });
tx(s, `少答对 ${n('RpTableOnlyCond')} 题`, 3.92, 4.5, 2.4, 0.4, 17, { bold: true, color: C.orange });
tx(s, '都是能修复或本可保留的', 3.92, 4.9, 2.4, 0.3, 12.5, { color: C.muted });
card(s, 6.76, 1.62, 2.85, 3.75, '指标层靠人声明', '连接性质靠人声明。Databricks 文档：该性质“不在运行时验证”。', C.orange, { badge: '3', size: 15, headSize: 16.5 });
tx(s, '声明 ≠ 核对', 7.0, 4.5, 2.4, 0.4, 17, { bold: true, color: C.orange });
tx(s, '放大行数时度量直接错', 7.0, 4.9, 2.4, 0.3, 12.5, { color: C.muted });
card(s, 9.84, 1.62, 2.85, 3.75, '智能体自己检查', '只有 16% 的会话查键唯一性；提示它检查，也要每次重新找出区分列。', C.orange, { badge: '4', size: 15, headSize: 16.5 });
tx(s, `${n('DsTrajModeled')}% → ${n('DsTrajVerifyModeled')}%`, 10.08, 4.5, 2.5, 0.4, 17, { bold: true, color: C.orange });
tx(s, `系统维护时为 ${n('DsCondModeled')}%`, 10.08, 4.9, 2.4, 0.3, 12.5, { color: C.muted });
takeaway(s, '缺的是一个专门记录、维护“口径成立条件”并在使用时核对的机制。', 5.85);

// 08 The idea in four steps.
s = slide('我们的做法：数据库替智能体记住“定义为什么成立”', '做法', '论文 §1、§3–§6',
  '这是整个工作的主线，后面四页分别展开。第一步“记录”：从口径的结构化定义里推出四类可执行条件，就是上一页说的“成立条件”。第二步“维护”：条件的检查结果按数据版本保存；数据更新后只重查被触及的条件，检查结果在所有依赖它的口径和智能体之间共享。第三步“约束使用”：声明了口径的查询只在条件成立的那份数据快照上执行。第四步“处理失效”：条件不再成立时，只接受唯一且通过回归测试的修复，否则让口径失效，宁可不可用也不给错答案。');
const idea = [
  ['记录', '从口径推出四类\n可执行的成立条件', '该检查什么？', C.blue],
  ['维护', '检查结果按数据版本保存\n更新后只重查受影响条件', '什么时候要重查？', C.green],
  ['约束使用', '查询只在条件成立的\n快照上执行', '什么时候可以用？', C.purple],
  ['处理失效', '唯一且过回归才修复\n否则让口径失效', '坏了怎么办？', C.orange],
];
idea.forEach(([head, body, q, color], i) => {
  const x = 0.6 + i * 3.1;
  step(s, x, 1.75, 2.8, 2.6, i + 1, head, body, color, C.light, 15.5);
  shape(s, x, 4.55, 2.8, 0.72, C.white, C.line);
  tx(s, q, x + 0.2, 4.55, 2.4, 0.72, 15.5, { color, bold: true, valign: 'middle', align: 'center' });
  if (i < 3) arrow(s, x + 2.82, 3.05, x + 3.08, 3.05);
});
tx(s, '口径的有效性证据成为数据库里一等的、带版本的状态，而不是留在某次探索的轨迹里。', 0.85, 5.55, 11.6, 0.4, 16, { color: C.muted });
takeaway(s, '对应论文的三项贡献：条件与充分性命题、同快照验证与复用引理、有界修复算法。', 6.3);

// 09 Step 1: the four conditions.
s = slide('记录：四类条件，用退货金额来看', '做法 · 记录', '论文 §4.2、§4.3；命题 1',
  '每一行先用白话说这个条件在保证什么，再说在退货金额里具体是什么，最后说数据库里怎么查。这四类条件都能写成 SQL 查询，返回“违反的证据”或空。命题 1 是论文的第一项形式化结果：在两条业务前提下（业务事件和过滤后的键一一对应；度量列就是事件的度量），四类条件成立就能保证规范 SQL 把每笔业务事件在它所属的期间恰好算一次，遗漏只限于完整性条件约束的那部分。命题同时划清了边界：单位换算这类取值变化不违反任何条件，条件看不到。');
table(s, [
  ['条件', '白话', '退货金额里是', '怎么查'],
  ['过滤后键唯一', '一笔业务事件只有一行', '“已完成”过滤后，小票号+商品唯一', '按键分组找重复'],
  ['连接多重性', '关联维度表不会放大行数', '退货 → 商品表是多对一', '维表侧的键唯一'],
  ['日期角色', '事实按正确的日期归期', '退货日期 → 日期维度多对一', '日期键多对一'],
  ['日期键完整性', '事实不会悄悄掉出所有期间', '匹配不到日期的比例不高于准入时', '比例对比'],
], 0.6, 1.65, [1.9, 3.1, 4.3, 2.8], 0.62, 14.5);
card(s, 0.6, 4.95, 12.1, 1.25, '命题 1（充分性）', '在业务前提下，四类条件成立 ⇒ 规范 SQL 把每笔业务事件在其期间恰好计数一次，遗漏仅限完整性条件约束的部分。', C.green, { size: 15, headSize: 17 });
takeaway(s, '边界也由命题划定：单位换算、两份一样合法的总体、合法但错误的日期键，条件看不到。', 6.3, C.orange, C.paleOrange);

// 10 Step 2: maintenance by versions and shared verdicts.
s = slide('维护：更新触及哪些条件，就只重查哪些', '做法 · 维护', '论文 §4.4、§5.2；gen/review.tex',
  '条件的检查结果按“条件的规范形式 + 它读的那些表的版本”索引。表没变，检查结果继续有效；表变了，只有读到这张表的条件需要重查，而且一个条件的检查结果被所有依赖它的口径和智能体共享。右边是受控实验里的一个例子：更新 store_returns 后，有 8 个口径受影响；逐个口径重查要跑 19 次检查，但其实只涉及 3 个不同的条件。TPC-DS 的 99 个官方模板里共享更明显。要诚实地说：这种节省大部分用一个按版本索引的检查缓存也能拿到，所以论文不把它当主要贡献。');
step(s, 0.6, 1.7, 3.6, 1.85, '1', '表的版本变了', '写事务里递增的事务性版本，\n或默认的 DML 统计', C.green, C.light, 14.5);
step(s, 0.6, 3.75, 3.6, 1.85, '2', '找到读这张表的条件', '只有它们进入重查；\n其余条件的检查结果保留', C.green, C.light, 14.5);
arrow(s, 2.4, 3.57, 2.4, 3.73, C.green);
step(s, 4.45, 1.7, 3.6, 1.85, '3', '重查并保存检查结果', '索引 = (条件的规范形式, 依赖表版本)\n同一检查并发到达时只跑一次', C.green, C.light, 14.5);
step(s, 4.45, 3.75, 3.6, 1.85, '4', '所有口径共享检查结果', '一个检查结果服务所有需要\n同一条件的口径和智能体', C.green, C.light, 14.5);
arrow(s, 4.22, 2.62, 4.43, 2.62, C.green); arrow(s, 6.25, 3.57, 6.25, 3.73, C.green);
stat(s, 8.5, 1.85, 4.2, '19 次 → 3 次', '更新 store_returns：8 个口径受影响\n逐口径重查 19 次，不同条件只有 3 个', C.blue, 34, 0.95);
stat(s, 8.5, 4.05, 4.2, `${n('TpDefs')} / ${n('TpConds')}`, `TPC-DS 的 ${n('TpTemplates')} 个模板：口径数 / 不同条件数\n平均每个条件被 ${n('TpPer')} 个口径共享`, C.blue, 34, 0.95);
takeaway(s, '维护工作量按“不同条件”计，不按口径数计；这部分节省通用的版本缓存也能拿到。');

// 11 Step 3: snapshot-bound execution.
s = slide('约束使用：检查和查询必须看同一份数据', '做法 · 约束使用', '论文 §6.2；引理 1；同快照验证为可选模式',
  '上面一行是常见做法：先检查，通过后再执行查询。问题是两步之间可能有写入提交，查询读到的已经是新数据，检查结果对它不成立——我们的并发实验里这种情况占 3.8% 到 4.6%。下面一行是我们的做法：把检查和查询放进同一个可重复读事务，读同一个快照；别处算好的检查结果只有在依赖表的事务性版本完全相同时才复用，这就是引理 1。要说明一点：默认的 DML 统计是异步更新的，统计值相同不代表数据相同，所以这个保证需要事务性版本（由写事务内的触发器维护）。');
tx(s, '先检查后执行（常见做法）', 0.6, 1.62, 5, 0.35, 15, { bold: true, color: C.orange });
const pre = [['检查通过', C.green], ['写入提交', C.orange], ['查询执行', C.orange], ['在违规数据上作答', C.orange]];
pre.forEach(([t, color], i) => {
  const x = 0.6 + i * 3.08;
  shape(s, x, 2.0, 2.75, 0.8, i === 0 ? C.paleGreen : C.paleOrange, i === 0 ? C.paleGreen : C.paleOrange);
  tx(s, t, x + 0.15, 2.0, 2.45, 0.8, 15.5, { bold: true, color, align: 'center', valign: 'middle' });
  if (i < 3) arrow(s, x + 2.77, 2.4, x + 3.06, 2.4, C.muted);
});
tx(s, '同快照验证（MAVRA）', 0.6, 3.1, 5, 0.35, 15, { bold: true, color: C.green });
shape(s, 0.6, 3.48, 9.0, 0.8, C.paleGreen, C.paleGreen);
tx(s, '同一个可重复读事务：读取版本 → 复用或执行检查 → 条件全部成立才执行业务 SQL', 0.8, 3.48, 8.7, 0.8, 15.5, { bold: true, color: C.green, valign: 'middle' });
shape(s, 9.84, 3.48, 2.86, 0.8, C.paleOrange, C.paleOrange);
tx(s, '任一条件不成立：拒绝', 9.99, 3.48, 2.6, 0.8, 15.5, { bold: true, color: C.orange, align: 'center', valign: 'middle' });
card(s, 0.6, 4.6, 7.15, 1.55, '引理 1（检查结果复用）', '两个快照里，条件读到的每张表的事务性版本都相同 ⇒ 条件在两个快照上的检查结果相同。', C.green, { size: 15, headSize: 17 });
card(s, 7.95, 4.6, 4.75, 1.55, '为什么要事务性版本', '默认 DML 统计异步更新；统计值相同不代表数据相同。', C.orange, { size: 15, headSize: 17 });
takeaway(s, `并发写入下：先检查后执行 ${n('SnPreUnannMin')}–${n('SnPreUnannMax')}% 的使用在违规数据上作答，同快照验证一次也没有。`);

// 12 Step 4: bounded repair.
s = slide('处理失效：三道关才发布修复，否则让它失效', '做法 · 处理失效', '论文 §5.3；算法 1；§7.4',
  '条件不成立时，有两种结局：修好，或让它失效。修复只做一件事：在低基数列上找一个等值过滤。三道关：过滤后要恢复“一键一行”而且不丢任何业务键；候选过滤必须恰好一个；再通过准入检查，并在学习时快照上用学习题做回归测试。用两个例子说明为什么要“唯一”：状态变更行的例子里，“状态=完成”是唯一能恢复粒度的过滤，修复成功；备份副本的例子里，“来源=主库”和“来源=备份”都能恢复粒度，结构上分不出哪个是真实业务数据，所以让它失效。宁可不可用，也不发布可能错的修复。');
const gates = [['恢复结构', '过滤后每个业务键一行，\n且不丢任何业务键', C.blue], ['候选唯一', '没有候选或多个候选，\n都让口径失效', C.purple], ['通过回归', '重新通过准入检查，\n在学习时快照上比对数值', C.green]];
gates.forEach(([head, body, color], i) => {
  step(s, 0.6 + i * 4.2, 1.7, 3.7, 2.15, i + 1, head, body, color, C.light, 15);
  if (i < 2) arrow(s, 4.33 + i * 4.2, 2.77, 4.77 + i * 4.2, 2.77);
});
card(s, 0.6, 4.2, 5.95, 1.9, '状态变更行：修复成功', '“状态 = 完成”是唯一能恢复一键一行的过滤；回归测试通过后发布新修订。', C.green, { size: 15, headSize: 17 });
card(s, 6.75, 4.2, 5.95, 1.9, '备份副本：让口径失效', '“来源 = 主库”和“来源 = 备份”都能恢复粒度，结构上分不出真伪，所以让它失效。', C.orange, { size: 15, headSize: 17 });
takeaway(s, '宁可让口径失效，也不发布可能错的修复；修复进行中的请求等待结果，不重复算。');

// 13 The system.
s = slide('MAVRA：智能体与 PostgreSQL 之间的中间件', '系统', '论文 §3；约 6,600 行 Rust，40 个测试',
  '系统是一个 HTTP 中间件，智能体通过它的工具接口访问数据库。三条路径：准入——判题成功的学习轨迹被提取成结构化口径，通过七项准入检查后发布；维护——依赖的表版本变了就按条件重查、复用检查结果、置为失效或修复；执行——智能体在 run_sql 里声明用到的口径和修订号，中间件核对修订、审查 SQL，并在同快照模式下在同一事务里验证和执行。版本来源有两种：默认的表指纹加 DML 统计，和由语句级触发器维护的事务性版本。');
shape(s, 3.25, 1.65, 6.78, 4.35, C.light, C.light);
tx(s, 'MAVRA · 共享口径与有效性证据', 3.49, 1.88, 6.3, 0.45, 21, { bold: true, color: C.blue });
card(s, 0.6, 2.35, 2.2, 2.4, '数据智能体', '学习会话 / 新会话\n查找口径\n声明修订并查询', C.purple, { size: 14.5, headSize: 17 });
card(s, 10.54, 2.35, 2.2, 2.4, 'PostgreSQL', '事实与维度表\n条件检查 SQL\n事务性表版本', C.green, { size: 14.5, headSize: 17 });
arrow(s, 2.87, 3.5, 3.18, 3.5); arrow(s, 10.09, 3.5, 10.46, 3.5);
[['准入', '成功轨迹 → 结构化口径\n七项准入检查重放后发布'], ['维护', '版本变化 → 按条件重查\n复用检查结果 / 失效 / 有界修复'], ['执行', '核对声明的修订 → SQL 审查\n可选：同一快照验证并执行']].forEach(([head, body], i) => {
  shape(s, 3.53, 2.6 + i * 0.98, 6.2, 0.82, C.white, C.white);
  tx(s, head, 3.75, 2.6 + i * 0.98, 1.1, 0.82, 18, { bold: true, color: C.blue, valign: 'middle' });
  tx(s, body, 5.0, 2.6 + i * 0.98, 4.55, 0.82, 14.5, { valign: 'middle' });
});
tx(s, '口径、连接路径、粒度条目、检查结果和证据都带版本，保存在中间件的知识库里', 3.52, 5.58, 6.3, 0.3, 12.5, { color: C.muted });
takeaway(s, '对智能体来说只是多了两个工具：find_metric 返回当前有效的口径，run_sql 在使用时核对。');

// 14 Experimental design.
s = slide('两层实验：先固定口径验证机制，再让真实智能体跑完整任务', '实验', '论文 §7.1；表 2、表 3',
  '实验分两层，这样能把“维护机制对不对”和“智能体学得好不好”分开。系统层固定口径和数据变化，只替换维护方式：定义库回放（3 个大模型学到的 15 个口径库，加上从 TPC-DS 99 个官方模板导出的库，各经历 11 种数据变化）、并发写入、维护代价（100 万到 1600 万行）。端到端层用 DeepSeek V4.1 Flash 跑完整智能体：5 个指标，先学再用，11 种数据变化，9 种方法各独立跑 3 次，共 2586 道计分题；另有 216 个固定口径库的完整会话用来量任务时间和 token。右边列出 11 种数据变化是什么，其中单位换算是条件看不到的对照。');
card(s, 0.6, 1.62, 5.85, 4.5, '系统层：口径固定，只换维护方式', `定义库回放：${n('RpLibs')} 个学到的口径库（${n('RpDefs')} 个口径）+ TPC-DS 模板库，各 ${n('RpChanges')} 种数据变化\n\n并发写入：先检查后执行 vs 同快照验证，确定性交错 + 随机并发\n\n维护代价：定义级 / 检查结果缓存 / MAVRA，100 万–1600 万行，8–32 个脚本智能体`, C.blue, { badge: '1', size: 14.5 });
card(s, 6.65, 1.62, 6.05, 4.5, '端到端：真实智能体完整任务', `DeepSeek V4.1 Flash；5 个指标先学再用，只给指标名\n\n${n('RpChanges')} 种数据变化：状态变更行、多版本更正、缓慢变化维、重复加载、日期键格式变化（条件能发现）；备份副本（修复有歧义）；4 种正常追加；单位换算（对照）\n\n9 种方法 × 3 次独立运行，${n('ScenValidTasks')} 道计分题；另有 ${n('SlSessions')} 个固定库会话量时间与 token`, C.purple, { badge: '2', size: 14.5 });
takeaway(s, '系统层回答“维护对不对、贵不贵”，端到端回答“对使用者有没有用”。');

// 15 Q1 results.
s = slide(`数据变化后：维护后的口径零错误答案，按模式变更失效 ${n('RpSchemaWrongModeled')} 个`, '实验 · 正确性', '论文 §7.2；gen/review.tex；图 4',
  `定义库回放把同一个口径库放在不同维护方式下经历同样的变化，所以差异只来自维护；所有方法都用智能体自己的学习 SQL 作回归对照，在学习时快照上比较。在条件能发现的变化下，MAVRA 没有给出任何错误答案，按模式变更失效给出 ${n('RpSchemaWrongModeled')} 个；真实 TPC-DS 数据上是 ${n('TrCondWrongModeled')} 对 ${n('TrSchemaWrongModeled')}。dbt 式的表级测试也能让被破坏的口径失效，但不会修，少答对 ${integer(num('RpCondCorrect') - num('RpTableCorrect'))} 题。条件级、定义级和检查结果缓存三种重验方式逐题答案完全一样，说明端到端里它们的差异来自学到的库而不是维护。图里的 ${n('RpCondWrong')} 个错误全部来自单位换算这个对照，它不违反任何条件，论文明确把它划在边界之外。`);
table(s, [
  ['维护方式', '答对', '答错', '其中：条件能发现的变化下答错'],
  ['按模式变更失效', n('RpSchemaCorrect'), n('RpSchemaWrong'), n('RpSchemaWrongModeled')],
  ['表级测试（dbt 式）', n('RpTableCorrect'), n('RpTableWrong'), n('RpTableWrongModeled')],
  ['定义级重验', n('RpDefCorrect'), n('RpDefWrong'), n('RpCondWrongModeled')],
  ['MAVRA', n('RpCondCorrect'), n('RpCondWrong'), n('RpCondWrongModeled')],
], 0.6, 1.7, [2.7, 1.1, 1.1, 3.3], 0.6, 15, 4);
tx(s, `每种方法 ${n('RpCondN')} 道配对题；${n('RpCondWrong')} 个错误全部来自单位换算这个对照。`, 0.62, 4.85, 8.0, 0.35, 13.5, { color: C.muted });
stat(s, 9.0, 1.75, 3.7, `0 vs ${n('RpSchemaWrongModeled')}`, '条件能发现的变化下的错误答案\nMAVRA vs 按模式变更失效（学到的库）', C.green, 34);
stat(s, 9.0, 3.65, 3.7, `0 vs ${n('TrSchemaWrongModeled')}`, '同样的对比，真实 TPC-DS 数据\n（99 个官方模板导出的口径库）', C.green, 34);
takeaway(s, `表级测试也能让被破坏的口径失效，但不会修：MAVRA 多答对 ${n('RpTableOnlyCond')} 题，来自修复或口径自带的过滤。`, 5.6);

// 16 Q2 results.
s = slide('并发写入：先检查后执行 4.6% 违规作答，同快照验证一次没有', '实验 · 使用时的保证', '论文 §7.3；gen/review.tex；表 5',
  '随机交错的并发实验：一边有写入者反复装载重复数据，一边有读者声明口径查询。先检查后执行在没有通知的写入下有 3.8% 到 4.6% 的作答落在违反条件的数据上；同快照验证在 11,297 次作答里一次也没有。读者的中位延迟两种模式一样，因为快照模式复用了维护阶段的检查结果。代价在写入者这边：每条写语句多一次计数器更新，单写者吞吐是无触发器的 0.70 倍，32 个并发写者分片计数后 0.97 倍，不分片会掉到 0.36 倍。');
stat(s, 0.86, 1.8, 5.7, `${n('SnPreUnannMin')}–${n('SnPreUnannMax')}%`, '先检查后执行：未通知的写入下\n在违规数据上作答的使用', C.orange, 42);
stat(s, 7.08, 1.8, 5.35, `0 / ${n('SnSnapAnswered')}`, '同快照验证：随机并发合计\n在违规数据上作答的使用', C.green, 42);
table(s, [
  ['代价', '观测结果'],
  ['读者中位延迟', `${n('SnStressPFiftyLo')}–${n('SnStressPFiftyHi')} ms，两种模式相同`],
  ['单写者吞吐（相对无触发器）', `${n('SnWriteSeq')}×`],
  ['32 个并发写者：分片计数 / 不分片', `${n('SnWriteConcTT')}× / ${n('SnWriteHotTT')}×`],
], 0.6, 4.15, [5.6, 6.5], 0.5, 15);
takeaway(s, '保证来自事务性版本：写入和版本递增在同一事务里提交，读者看到其一就看到其二。');

// 17 Q4 results.
s = slide('维护代价：共享条件后，只需定义级重验的 14%', '实验 · 代价', '论文 §7.5；gen/review.tex；19 个口径、错峰到达',
  '受控实验里，19 个口径共享条件，8 个脚本智能体错峰使用。把逐口径重查全部条件的“定义级”记为 100%：只缩小范围不复用检查结果是 86.8%，按 SQL 文本和版本缓存检查结果的检查结果缓存是 16.7%，MAVRA 是 14.0%。两点要如实讲：一是节省来自检查结果共享，检查结果缓存几乎拿到同样的节省，所以这不是论文的主要贡献；二是比例从 100 万行到 1600 万行都稳定在 12% 到 13%。');
tx(s, '维护数据库时间，相对定义级（%）', 0.85, 1.62, 6.6, 0.24, 12, { color: C.muted });
chart(s, [{ name: '相对定义级的维护 DB 时间（%）', labels: ['定义级', '仅缩小范围', '检查结果缓存', 'MAVRA'],
  values: [100, num('CbStagScopeSix'), num('CbStagCacheSix'), num('CbStagCondSix')] }], 0.6, 1.85, 7.04, 4.1, [C.blue], 115, { dataLabelFormatCode: '0.0' });
bullets(s, [
  `定义级随口径数增长：${n('CbStagDefOne')} → ${n('CbStagDefSix')} 秒。`,
  `19 个口径：MAVRA 为定义级的 ${n('CbStagCondSix')}%，检查结果缓存 ${n('CbStagCacheSix')}%。`,
  `100 万到 1600 万行：比例稳定在 ${n('EoneRatioSixteen')}–${n('EoneRatioFour')}%。`,
  `口径之间没有共享条件时，所有方法都是定义级的 ${n('CbZeroMin')}–${n('CbZeroMax')}%。`,
], 8.0, 1.85, 4.66, 4.2, 16);
takeaway(s, '节省来自检查结果共享，检查结果缓存也能拿到；论文的贡献在条件、使用保证和修复规则。', 6.3, C.orange, C.paleOrange);

// 18 Q5 results.
s = slide(`端到端：共享把正确率从 ${n('DsNoShareAll')}% 提到 ${n('DsNoguardAll')}%，维护再拉开 ${n('DsCmpModeledTraj')} 个点`, '实验 · 真实智能体', '论文 §7.6；gen/scen-ds.tex；9 种方法 × 3 次',
  `蓝柱是全部情形，橙柱是条件能发现的破坏性变化。先看蓝柱：不共享 ${n('DsNoShareAll')}%，共享但不验证 ${n('DsNoguardAll')}%，MAVRA ${n('DsCondAll')}%，所以共享本身是最大的一步。再看橙柱：破坏性变化下，MAVRA ${n('DsCondModeled')}%，模仿 AgentSM 的轨迹检索 ${n('DsTrajModeled')}%，预先登记的比较差 ${n('DsCmpModeledTraj')} 个百分点，95% 区间 ${n('DsCmpModeledTrajLo')} 到 ${n('DsCmpModeledTrajHi')}；让检索的智能体自己检查这些性质，也只到 ${n('DsTrajVerifyModeled')}%。右下角是一个诚实的反例：备份副本的变化下 MAVRA 让口径失效了，智能体要自己重找，这一组反而输给检索。`);
const methods = [['不共享', 'DsNoShare'], ['轨迹检索', 'DsTraj'], ['检索 + 自检', 'DsTrajVerify'], ['共享不验证', 'DsNoguard'], ['MAVRA', 'DsCond']];
tx(s, '智能体最终答案正确率（%）', 0.85, 1.6, 6.6, 0.24, 12, { color: C.muted });
chart(s, [
  { name: '全部情形', labels: methods.map((m) => m[0]), values: methods.map((m) => num(m[1] + 'All')) },
  { name: '条件能发现的破坏性变化', labels: methods.map((m) => m[0]), values: methods.map((m) => num(m[1] + 'Modeled')) },
], 0.6, 1.82, 7.95, 4.45, [C.blue, C.orange], 110);
bullets(s, [
  `共享本身：${n('DsNoShareAll')}% → ${n('DsNoguardAll')}%；再加维护 ${n('DsCondAll')}%。`,
  `破坏性变化：MAVRA ${n('DsCondModeled')}% vs 轨迹检索 ${n('DsTrajModeled')}%；预登记的差 +${n('DsCmpModeledTraj')}（95% 区间 ${n('DsCmpModeledTrajLo')}–${n('DsCmpModeledTrajHi')}）。`,
  `让检索的智能体自己检查：${n('DsTrajVerifyModeled')}%，仍落后 ${n('DsCmpModeledCondVerify')} 个点。`,
], 8.85, 1.85, 3.85, 3.3, 15);
tx(s, `反例：备份副本下 MAVRA 让口径失效，这一组 ${n('DsCondMirror')}% 低于检索的 ${n('DsTrajMirror')}%。`, 8.85, 5.3, 3.85, 0.9, 14, { color: C.orange, bold: true });
takeaway(s, '共享提高准确率；维护让共享的口径在数据变了之后仍然可靠。', 6.35);

// 19 Client-side cost.
s = slide('对使用者：任务更快、调用更少、token 更少', '实验 · 使用者的开销', '论文 §7.6；gen/session-latency.tex；exp/2026-10-03-shared-memory/analysis/summary.json',
  '两组实验。上面的表是固定口径库的会话实验：每道题一个全新会话，不共享的智能体 54 题只答对 16 题、平均 64 秒；有共享口径的三种方法都 54 题全对，MAVRA 平均 38 秒，输入 token 少 40.7%。要说清楚：这个节省来自共享，定义级和检查结果缓存也在 32、33 秒，维护方式之间没有延迟优势。下面一行是另一个实验：所有智能体都拿到相同的业务定义、正确率相同，只看探索开销——逐步积累的共享知识把每题的结构查找从 3.5 次减到 2.5 次，SQL 探查从 0.20 次减到 0.06 次。');
table(s, [
  ['方法', '答对 / 54', '平均完成（秒）', 'LLM 调用 / 题', '输入 token / 次尝试'],
  ['不共享口径', `${n('SlNoneCorrect')}/${n('SlNoneN')}`, n('SlNoneMean'), n('SlNoneRounds'), integer(sessionPolicy('no-share').tokens.input_tokens / sessionPolicy('no-share').n)],
  ['定义级重验', `${n('SlDefCorrect')}/${n('SlDefN')}`, n('SlDefMean'), n('SlDefRounds'), integer(sessionPolicy('definition').tokens.input_tokens / sessionPolicy('definition').n)],
  ['检查结果缓存', `${n('SlCacheCorrect')}/${n('SlCacheN')}`, n('SlCacheMean'), n('SlCacheRounds'), integer(sessionPolicy('definition-cache').tokens.input_tokens / sessionPolicy('definition-cache').n)],
  ['MAVRA', `${n('SlCondCorrect')}/${n('SlCondN')}`, n('SlCondMean'), n('SlCondRounds'), integer(sessionPolicy('condition').tokens.input_tokens / sessionPolicy('condition').n)],
], 0.6, 1.65, [2.6, 1.75, 2.5, 2.4, 2.85], 0.56, 15, 4);
const schemaSaving = (1 - mem('accumulating', 'schema_calls') / mem('isolated', 'schema_calls')) * 100;
const probeSaving = (1 - mem('accumulating', 'sql_probes') / mem('isolated', 'sql_probes')) * 100;
stat(s, 0.85, 4.75, 3.0, `−${n('SlCondInputSaveNone')}%`, 'MAVRA 相对不共享\n每次尝试的输入 token', C.blue, 32, 0.6);
stat(s, 4.05, 4.75, 3.0, `−${fixed(schemaSaving, 1)}%`, '业务定义相同时\n每题的结构查找次数', C.green, 32, 0.6);
stat(s, 7.25, 4.75, 3.0, `−${fixed(probeSaving, 1)}%`, '业务定义相同时\n每题的 SQL 探查次数', C.green, 32, 0.6);
tx(s, `节省来自共享：定义级 ${n('SlDefMean')} 秒、检查结果缓存 ${n('SlCacheMean')} 秒，维护方式之间没有延迟优势。`, 10.4, 4.8, 2.3, 1.4, 13, { color: C.muted });
takeaway(s, `${n('SlSessions')} 个全新会话：不共享 ${n('SlNoneCorrect')}/54 答对、${n('SlNoneMean')} 秒；MAVRA 54/54、${n('SlCondMean')} 秒。`, 6.35);

// 20 Boundaries.
s = slide('保证的范围，和现在还做不到的', '讨论', '论文 §6.3、§7.6、§9',
  '主动把边界讲清楚，比被问到再解释好。第一，使用时的保证只覆盖声明了口径的查询：此前样本里 25.7% 的答案没有声明口径；声明了正确修订仍有 1.3% 因为自己写的 SQL 偏离规范计算而答错。第二，四类条件是结构条件，看不到取值语义（单位换算）和两份同样合法的总体（备份副本），这两类需要业务证据。第三，评估的局限：系统层的数据变化是我们注入的，不是真实的更新历史；端到端主实验只有一个模型、每种方法 3 次，更早一轮三个模型的趋势一致。');
card(s, 0.6, 1.65, 3.9, 3.85, '保证只覆盖声明的使用', `声明口径 + 同快照验证：条件在所读数据上成立。\n\n未声明的 SQL 不在契约内；此前样本中 ${n('DuUndeclPct')}% 的答案未声明口径，声明正确修订后仍有 ${n('DuDevPct')}% 因 SQL 偏离而答错。`, C.blue, { badge: '1', size: 14.5 });
card(s, 4.7, 1.65, 3.9, 3.85, '条件看不到取值语义', '单位换算不违反任何条件；备份副本里两份总体都合法。\n\n这两类要靠业务证据；修复也只会加过滤，还不会去重或重映射键。', C.orange, { badge: '2', size: 14.5 });
card(s, 8.8, 1.65, 3.9, 3.85, '评估的局限', '数据变化由我们注入，不是真实更新历史。\n\n端到端主实验一个模型、每种方法 3 次；更早一轮三个模型趋势一致。', C.green, { badge: '3', size: 14.5 });
takeaway(s, '下一步：取值层面的条件、识别未声明的使用、去重和重映射修复、真实更新历史。', 5.85);

// 21 Contributions and status.
s = slide('论文贡献与当前进展', '进展', '当前 overleaf/；docs/research-status.md',
  '左边是论文的四项贡献，和前面“记录—维护—约束使用—处理失效”一一对应。右边是进展：论文完整初稿已经写完并通过了一轮引用核对，目前 15 页，正文比 12 页上限多出约 0.6 页需要压缩；代码和全部实验数据都在仓库主线上，可复算；10 月 7 日模型配额重置后补跑其他模型的端到端实验。');
card(s, 0.6, 1.62, 6.0, 4.5, '四项贡献', '① 把共享口径建模为依赖四类可执行条件的可维护知识，并证明条件的充分性（命题 1）\n\n② 把每次声明的使用绑定到查询自身快照上成立的证据，复用规则可靠（引理 1）\n\n③ 有界修复算法：唯一、不丢键、过回归，否则让它失效（算法 1）\n\n④ 实现与两层评估：定义库回放、TPC-DS、并发、代价、端到端', C.blue, { size: 14.5 });
card(s, 6.8, 1.62, 5.9, 4.5, '进展与下一步', '✓ 论文完整初稿，投稿目标 SIGMOD 2027 研究track\n✓ 摘要、引言按“问题—做法—效果”重写，引用逐条核对\n✓ 代码、工具和实验数据在仓库主线上，可复算\n\n○ 正文约 12.6 页，需压缩 0.6 页\n○ 10 月 7 日配额重置后补跑其他模型\n○ 真实更新历史、取值条件、未声明使用', C.green, { size: 14.5 });
takeaway(s, '方法、证明、系统和实验已经闭环；剩下的是压缩篇幅和补强评估。');

// 22 Closing.
s = slide('让共享知识在变化的数据上继续成立', '结束', '论文 §10',
  '收束回一句话：学到的口径成了长期状态；四类条件说明要查什么，事务性版本和同快照验证说明什么时候可以用，唯一且过回归的修复说明坏了怎么办。最后列出三个想请老师把关的问题：定位是否站得住、评估要补哪一项最有说服力、投稿目标与时间。', { dark: true });
tx(s, '让共享知识在变化的数据上继续成立', 0.8, 1.0, 11.65, 0.85, 34, { bold: true, color: C.white });
tx(s, '①  记录：从口径推出粒度、连接、日期角色、日期键完整性四类条件\n②  维护：检查结果按数据版本保存，更新后只重查受影响的条件\n③  约束使用：查询只在条件成立的快照上执行\n④  处理失效：唯一且过回归才修复，否则让它失效', 0.86, 2.15, 11.55, 2.2, 20, { color: 'D8E5F3', paraSpaceAfter: 10 });
shape(s, 0.8, 4.65, 11.7, 2.15, '24364D', '24364D');
tx(s, '想请老师把关的三个问题', 1.05, 4.8, 11.2, 0.4, 18, { bold: true, color: '88B9F0' });
tx(s, '1. 定位：聚焦“共享指标口径的有效性维护”，而不是更宽的“智能体共享记忆层”，这样切是否站得住？\n2. 评估：端到端一个模型 × 3 次、数据变化由我们注入；补哪一项最有说服力？\n3. 投稿：按 SIGMOD 2027 研究track，正文再压 0.6 页；目标与时间是否合适？', 1.05, 5.25, 11.2, 1.45, 15.5, { color: 'D8E5F3', paraSpaceAfter: 6 });

// ---------------------------------------------------------- appendix ----
// A1 Formal model.
s = slide('形式化：定义、命题 1、引理 1 与算法 1', '形式化', '论文 §4、§6.2、§5.3',
  '问答备用。修订 m^r=(B,I,C,E,r)：业务含义、结构化实现、条件集、证据、修订号；规范 SQL 由 I 编译。命题 1 的两条业务前提：B1 业务事件与过滤后的键值一一对应；B2 度量表达式在事件行上给出该事件的度量。引理 1 依赖 PostgreSQL 快照的嵌套性和“写入与版本递增同事务”。算法 1 的候选来自低基数列上的等值过滤。', { appendix: true });
tx(s, '修订  mʳ = (B, I, C, E, r)   业务含义 · 结构化实现 · 条件集 · 证据 · 修订号；规范 SQL 由 I 编译', 0.63, 1.62, 12.0, 0.45, 16.5, { color: C.blue, bold: true });
card(s, 0.6, 2.25, 5.95, 1.95, '命题 1（充分性）', 'B1、B2 与 C(mʳ) 在快照 Dₛ 上成立 ⇒ 对每个期间 p，规范 SQL 返回角色日期落在 p 内的事件度量的聚合，每个事件恰好贡献一次；遗漏仅为日期键匹配不到日期维度的事件，其比例受完整性条件约束。', C.green, { size: 13.5, headSize: 16 });
card(s, 6.75, 2.25, 5.95, 1.95, '引理 1（检查结果复用）', '两个快照 s₁、s₂ 中，条件 c 读到的每张表 T 的事务性版本相同 ⇒ c(D_{s₁}) = c(D_{s₂})。证明用快照嵌套与“写入和版本递增在同一事务提交”。', C.purple, { size: 13.5, headSize: 16 });
card(s, 0.6, 4.4, 12.1, 1.7, '算法 1（有界修复）', '粒度条件失效 → 在低基数列上枚举等值过滤 → 保留恢复一键一行且不丢业务键的候选 → 候选恰好一个 → 通过准入检查 G3–G5 与学习时快照上的回归 G8 → 发布新修订；任一步失败则让口径失效。', C.orange, { size: 13.5, headSize: 16 });
takeaway(s, '命题划定检测边界：取值变化、结构等价的总体、合法但错误的日期键不由结构条件证明。', 6.3, C.orange, C.paleOrange);

// A2 Repair reference and the uniqueness counterexample.
s = slide('回归测试放在学习时快照上做：不需要标准答案也能修好', '修复细节', '论文 §5.3、§7.4；gen/review.tex',
  `问答备用。智能体的学习 SQL 只在学习时的那份数据上被判过对。MAVRA 把它和修复后的定义放在学习时快照上比较（数仓用 time travel，原型在准入时复制相关表）：同一批 ${n('RpCurPairN')} 道题答对 ${n('RpCurPairCond')} 道，多版本更正 ${n('RpCurRevisionCond')}/${n('RpCurRevisionN')}、缓慢变化维 ${n('RpCurDimhistCond')}/${n('RpCurDimhistN')} 全部修好。同样的测试放在当前数据上只答对 ${n('RpCurPairOther')} 道：多版本更正之后智能体的 SQL 会把旧版本也算进去，正确的修复也被拒绝。预先写入区分列的标准答案 SQL 答对 ${n('RpGoldPairOther')} 道。TPC-DS 上是 ${n('TrCurPairCond')} 对 ${n('TrCurPairOther')}（共 ${n('TrCurPairN')} 道）。端到端实验早于这个改动，G8 在当前数据上比较，口径失效后智能体自己推出过滤，正确率 ${n('DsCondModeled')}%。备份副本反例：不要求候选唯一时，一个预见来源列的参照会让错误修复发布；要求唯一后都让口径失效。`, { appendix: true });
table(s, [
  ['同一批题：答对', 'G8 在学习时快照上（MAVRA）', 'G8 在当前数据上'],
  [`定义库回放（${n('RpCurPairN')} 道）`, n('RpCurPairCond'), n('RpCurPairOther')],
  ['其中：多版本更正', `${n('RpCurRevisionCond')}/${n('RpCurRevisionN')}`, `${n('RpCurRevisionOther')}/${n('RpCurRevisionN')}`],
  ['其中：缓慢变化维', `${n('RpCurDimhistCond')}/${n('RpCurDimhistN')}`, `${n('RpCurDimhistOther')}/${n('RpCurDimhistN')}`],
  [`TPC-DS（${n('TrCurPairN')} 道）`, n('TrCurPairCond'), n('TrCurPairOther')],
], 0.6, 1.7, [4.6, 3.9, 3.6], 0.56, 15.5);
card(s, 0.6, 4.6, 5.95, 1.55, '反例：追加备份副本', '不要求候选唯一时可发布错误修复；要求唯一时让口径失效。', C.orange, { size: 15, headSize: 17 });
card(s, 6.75, 4.6, 5.95, 1.55, '修复期间等待', `同时到达的不可用从 ${n('WrCondOff')} 降为 0；后到的请求共享已有的维护结果。`, C.blue, { size: 15, headSize: 17 });
takeaway(s, '参照只在它被判对的快照上可信；放回那个快照，就不需要标准答案。');

// A3 Baseline coverage.
s = slide('各类方法分别覆盖生命周期的哪些环节', '基线与定位', '论文 §2.4、表 3；概念对照',
  '问答备用。这张表是机制定位，不表示所有行都跑了同一个端到端矩阵：表级测试在定义库回放里跑；定义级加缓存在代价实验和固定库会话里跑；端到端场景是 9 种方法。', { appendix: true });
table(s, [
  ['方法', '正常更新', '条件破坏后', '使用时保证', '维护单位'],
  ['轨迹检索', '复用 SQL', '靠智能体自己发现', '不绑定条件', '检索到的成功轨迹'],
  ['按模式变更失效', '保留', '结构未变时漏检', '结构 / 修订核对', '结构指纹'],
  ['表级测试（dbt 式）', '保留', '让相关表上的口径失效', '先测试后执行', '按表声明的测试'],
  ['写入即失效', '失效并重学', '失效并重学', '执行前核对', '每次写入'],
  ['定义级 + 版本缓存', '保留', '同样的修复与回归', '先检查后执行', '缓存的检查 SQL'],
  ['MAVRA', '保留', '有界修复或让它失效', '可绑定同一快照', '变化触及的不同条件'],
], 0.6, 1.7, [2.7, 1.63, 3.05, 2.46, 2.26], 0.62, 14, 6);
takeaway(s, '共享、验证和缓存是基础设施；本文研究的是口径的有效性生命周期。');

// A4 Full session-latency result.
s = slide('完整会话延迟：更新后首用更快，突发到达仍有模型长尾', '完整会话', 'exp/2026-10-03-session-latency/stats.json、report.md',
  '问答备用，也是对“MAVRA 比检查结果缓存更快吗”的诚实回答：不是。更新后首次使用 MAVRA 更快（追加后 12.53 对 18.00 秒，破坏后 28.41 对 32.01），但突发到达时 78 对 58 秒，一次 356 秒的长尾里 338 秒是模型接口时间。全矩阵平均 37.68 对 31.97 秒；数据库工作量少 25.3% 推不出整体更快。只有 3 个库，描述性结果。', { appendix: true });
tx(s, '平均完整会话完成时间（秒）', 0.85, 1.62, 6.6, 0.24, 12, { color: C.muted });
chart(s, [
  { name: '检查结果缓存', labels: ['追加后首用', '破坏后首用', '破坏后突发到达'], values: ['after-append', 'after-status', 'burst-status'].map((p) => phaseMean('definition-cache', p)) },
  { name: 'MAVRA', labels: ['追加后首用', '破坏后首用', '破坏后突发到达'], values: ['after-append', 'after-status', 'burst-status'].map((p) => phaseMean('condition', p)) },
], 0.6, 1.88, 7.02, 4.15, [C.muted, C.blue], 95, { dataLabelFormatCode: '0.00' });
card(s, 8.0, 1.88, 4.69, 1.9, '数据库工作量减少', `MAVRA 比检查结果缓存少 ${n('SlCondDBSaveCache')}% 的数据库查询时间。`, C.blue, { size: 15, headSize: 17 });
card(s, 8.0, 4.05, 4.69, 2.0, '整体延迟优势不成立', `全矩阵平均 ${n('SlCondMean')} 对 ${n('SlCacheMean')} 秒；一次 ${n('SlSlowTotal')} 秒的长尾中模型接口占 ${n('SlSlowLLM')} 秒。`, C.orange, { size: 15, headSize: 17 });
takeaway(s, '测量包括模型、工具与排队；数据库工作量和完整会话时间要分开报告。', 6.35);

// A5 Workload characterization.
s = slide('应用重复的是查询，智能体重复的是知识', '工作负载刻画', '论文 §2.1；exp/2026-10-01-workload-characterization/',
  '问答备用。应用侧是 Amazon Redset，400 个集群 4.41 亿条查询；智能体侧是 100 个互不共享的 DeepSeek 会话。应用反复发同样的查询模板，结果缓存就能服务；智能体反复获取的是表结构、粒度、连接这些事实，SQL 写法每次都不同，按文本的缓存一条也服务不了。另外两点：错误答案全部来自执行成功的 SQL；只有 16% 的会话会检查键唯一性。', { appendix: true });
table(s, [
  ['观察', '应用负载：Redset', '智能体：100 个全新会话'],
  ['复用对象', '稳定的查询模板', '表结构、粒度、连接等事实'],
  ['重复程度', '半数集群 80% 的查询完全重复', '93% 的查找重复此前会话获得的事实'],
  ['SQL 探查', '34% 的读查询由结果缓存回答', '38% 重复事实；逐字相同的 SQL 为 0'],
  ['探索与验证', '知识预先写在应用代码里', '68% 的调用用于探索；16% 的会话查键唯一性'],
  ['错误方式', '—', '32 个错误答案全部来自成功执行的 SQL'],
], 0.6, 1.7, [2.0, 4.3, 5.8], 0.66, 15);
takeaway(s, '共享能减少重复探索；支撑共享口径的事实仍需在更新后重验。');

(async () => {
  fs.mkdirSync(path.dirname(output), { recursive: true });
  await pres.writeFile({ fileName: output });
  const provenance = {
    reportDate, slides: slides.length, mainSlides: slides.filter((r) => !r.appendix).length,
    sources: Object.fromEntries(sources), macros: Object.fromEntries([...usedMacros].sort().map((key) => [key, M[key]])),
    outline: slides,
  };
  fs.writeFileSync(output.replace(/\.pptx$/i, '.sources.json'), JSON.stringify(provenance, null, 2) + '\n');
  console.log(`Wrote ${output}: ${slides.length} slides (${provenance.mainSlides} main + ${slides.length - provenance.mainSlides} appendix), ${usedMacros.size} checked paper macros.`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
