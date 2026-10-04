// MAVRA research presentation. Numerical results come from the paper's macros
// and the archived session / matched-producer studies. No external skill required.
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
  'sections/09-limitations.tex', 'sections/10-conclusion.tex', 'tables/workload.tex']) {
  read(path.relative(repo, path.join(overleaf, file)));
}

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
const W = 13.333333, H = 7.5;
const FONT = 'Microsoft YaHei';
const C = {
  navy: '1B2A41', ink: '24364D', muted: '53657A', light: 'EEF2F7', line: 'D9E2EE',
  blue: '2A78D6', orange: 'EB6834', green: '198861', gold: 'C48B0A', purple: '8250AD', white: 'FFFFFF',
};
pres.theme = { headFontFace: FONT, bodyFontFace: FONT, lang: 'zh-CN' };
pres.title = `MAVRA：共享指标定义的有效性维护 · ${reportDate}`;
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
function tx(s, text, x, y, w, h, size = 18, opts = {}) {
  boxCheck(x, y, w, h, typeof text === 'string' ? text.slice(0, 40) : 'rich text');
  s.addText(text, { x, y, w, h, fontFace: FONT, fontSize: size, color: C.ink, margin: 0,
    breakLine: false, valign: 'top', lineSpacingMultiple: 1.1, isTextBox: true,
    objectName: `text-${++objects}`, ...opts });
}
function shape(s, x, y, w, h, fill = C.light, line = fill, type = 'roundRect') {
  boxCheck(x, y, w, h, type);
  s.addShape(pres.ShapeType[type], { x, y, w, h, rectRadius: 0.08,
    fill: { color: fill }, line: { color: line, width: 0.8 }, objectName: `shape-${++objects}` });
}
function arrow(s, x1, y1, x2, y2, color = C.blue) {
  s.addShape(pres.ShapeType.line, { x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color, width: 1.8, beginArrowType: 'none', endArrowType: 'triangle' }, objectName: `arrow-${++objects}` });
}
function slide(title, section, source, notes, { dark = false, appendix = false } = {}) {
  const s = pres.addSlide();
  s.background = { color: dark ? C.navy : C.white };
  const page = slides.length + 1;
  slides.push({ page, title, section, source, appendix });
  if (!dark) {
    tx(s, `${appendix ? '附录 / ' : ''}${section}`, 0.6, 0.25, 11.8, 0.24, 10.5, { bold: true, color: C.blue, charSpacing: 1 });
    const titleSize = title.length > 34 ? 25 : title.length > 27 ? 27 : 29;
    tx(s, title, 0.6, 0.64, 12.1, 0.65, titleSize, { bold: true });
    shape(s, 0.6, 1.33, 12.1, 0.025, C.line, C.line, 'rect');
  }
  tx(s, `MAVRA · ${reportDate} 研究汇报`, 0.6, 7.1, 4.35, 0.22, 9.5, { color: dark ? 'C4D2E4' : C.muted });
  tx(s, source, 5.0, 7.1, 7.1, 0.22, 8.5, { color: dark ? 'C4D2E4' : C.muted, align: 'right' });
  tx(s, String(page).padStart(2, '0'), 12.2, 7.08, 0.5, 0.24, 10.5, { align: 'right', color: dark ? C.white : C.muted });
  s.addNotes(`${notes}\n\n依据：${source}\n报告日期：${reportDate}。内容对应当前 overleaf/ 正文；归档结果独立标注。`);
  return s;
}
function card(s, x, y, w, h, head, body, color = C.blue, size = 16.5) {
  shape(s, x, y, w, h);
  shape(s, x + 0.18, y + 0.24, 0.055, 0.28, color, color, 'rect');
  tx(s, head, x + 0.38, y + 0.18, w - 0.56, 0.52, 19, { bold: true, color });
  tx(s, body, x + 0.23, y + 0.91, w - 0.46, h - 1.1, size);
}
function stat(s, x, y, w, value, label, color = C.blue, size = 38, labelH = 0.85) {
  tx(s, value, x, y, w, 0.85, size, { bold: true, color });
  tx(s, label, x, y + 0.97, w, labelH, 15.5, { color: C.muted });
}
function bullets(s, items, x, y, w, h, size = 18, color = C.ink) {
  tx(s, items.map((text, i) => ({ text, options: { bullet: { indent: size }, hanging: 4,
    breakLine: i < items.length - 1, paraSpaceAfter: 12 } })), x, y, w, h, size, { color });
}
function takeaway(s, text, y = 6.28, color = C.blue) {
  shape(s, 0.6, y, 12.1, 0.57, C.light);
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

// 01 Cover.
let s = slide('MAVRA：共享指标定义的有效性维护', '开场', '论文标题 / 摘要',
  '这次汇报沿着论文当前主线展开：数据库替智能体保存已学定义成立的证据，随更新维护，并在使用时约束读取的数据。方法讲清三个问题，实验区分机制层正确性和智能体完整任务收益。', { dark: true });
tx(s, 'MAVRA', 0.8, 1.12, 11.6, 0.83, 52, { bold: true, color: C.white });
tx(s, '面向数据智能体的\n共享指标定义有效性维护', 0.8, 2.35, 11.7, 1.55, 34, { bold: true, color: C.white });
tx(s, 'Keeping Shared Metric Definitions Valid for Data Agents', 0.83, 4.36, 11.6, 0.44, 19, { color: 'D6E2F1' });
tx(s, `${reportDate.replace(/-/g, ' / ')}  ·  论文进展汇报  ·  SIGMOD 2027`, 0.83, 5.32, 11.6, 0.45, 18, { color: 'D6E2F1' });
tx(s, '问题与动机  →  有效性模型  →  维护与执行  →  实验与讨论', 0.83, 6.15, 11.6, 0.36, 15, { color: 'AFC4DE' });

// 02 Central claim and separate evidence.
s = slide('数据库必须替智能体记住：学到的定义为什么成立', '核心观点', '论文 §1 / §7；gen/scen-ds.tex、review.tex、session-latency.tex',
  '共享定义的业务含义长期存在，但 SQL 正确性依赖当前数据。三组数字分别来自端到端场景、并发写入机制实验和固定库会话实验；它们不是同一分母，不互相替代。73% 是智能体最终答案正确率，零违规是声明使用时条件成立的保证。');
card(s, 0.6, 1.66, 3.9, 2.4, '把前提变成条件', '从结构化定义推出粒度、连接多重性、时间角色与覆盖；证据随数据版本保存。', C.blue);
card(s, 4.7, 1.66, 3.9, 2.4, '让证据约束使用', '声明的修订只在条件成立的快照上执行；依赖版本一致才复用结论。', C.green);
card(s, 8.8, 1.66, 3.9, 2.4, '失效后有界修复', '修复必须不丢业务键、结构上唯一并通过回归；否则撤下定义。', C.orange);
stat(s, 0.82, 4.46, 3.75, `${n('DsCondModeled')}% / ${n('DsTrajModeled')}%`, '已建模破坏下：MAVRA / 轨迹检索\n智能体最终答案正确率', C.blue);
stat(s, 4.92, 4.46, 3.75, `0 / ${n('SnSnapAnswered')}`, '并发写入下：绑定快照执行\n在条件不成立的数据上作答的次数', C.green, 35);
stat(s, 9.02, 4.46, 3.65, `${n('SlNoneMean')} → ${n('SlCondMean')}`, '固定库会话：不共享 → MAVRA\n平均完成秒数', C.orange, 27);

// 03 Concrete producer / update / consumer story.
s = slide('SQL 照常执行，退货金额却被算了两次', '问题与动机', '论文 §1、§2.3；早期单期例子',
  '最初每个小票—商品键对应一条完成记录，SUM(sr_return_amt) 正确。ETL 追加申请状态行而不改表结构，新会话沿用共享 SQL 就会重复计数。这是论文引言中的实际单期例子。修复完成状态过滤还要检查是否丢键以及回归。');
card(s, 0.6, 1.65, 3.6, 2.5, 'Agent A 学到定义', '一笔退货 = 一条完成记录\n小票—商品键唯一\nSQL：SUM(sr_return_amt)', C.blue, 16);
card(s, 4.86, 1.65, 3.6, 2.5, 'ETL 追加状态流水', '同一退货又多一条申请行\n键不再唯一\n表名、列名、类型均不变', C.orange, 16);
card(s, 9.12, 1.65, 3.6, 2.5, 'Agent B 复用共享 SQL', '学习者的会话已经结束\n新会话没有基准真值\n执行成功也看不出重复计数', C.purple, 16);
arrow(s, 4.28, 2.8, 4.75, 2.8); arrow(s, 8.55, 2.8, 9.02, 2.8);
stat(s, 0.85, 4.62, 5.7, '6,588,699.86', '共享 SQL 返回的单期金额', C.orange, 37);
stat(s, 7.0, 4.62, 5.7, '3,294,349.93', '该期间实际的已完成退货金额', C.green, 37);
takeaway(s, '共享保存了业务知识，也让一次过期观测传播给之后的每个智能体。');

// 04 New introduction: what changes with agent consumers.
s = slide('使用者变成智能体后，三件事发生了变化', '问题与动机', '论文 §1（当前引言）',
  '这页对应新引言的三个变化。性质本身属于数据仓库的汇总正确性要求；变化在于这些前提由智能体观测、生产者与消费者脱钩、消费者不能靠执行成功识别破坏。已有共享记忆、数据测试和指标层构成背景；核心对象仍是指标定义的有效性生命周期。');
card(s, 0.6, 1.75, 3.9, 3.65, '前提从设计变成观测', '智能体在当前快照查明粒度和连接。\n\n观测通常只留在轨迹中；之后的纯数据更新可能打破它。', C.blue, 18);
card(s, 4.7, 1.75, 3.9, 3.65, '生产者与消费者脱钩', '定义在学习会话结束后继续存在，并服务全新的会话。\n\n一次过期的证据会影响所有复用者。', C.purple, 18);
card(s, 8.8, 1.75, 3.9, 3.65, '消费者看不出破坏', '表结构未变，SQL 不报错，结果仍像一个合理数字。\n\n消费者既没见过原证据，也没有真值。', C.orange, 18);
takeaway(s, '需要持续维护“定义—条件—证据”的联系，并让证据决定每次使用是否有效。');

// 05 Workload characterization.
s = slide('智能体反复获取的是知识，探查 SQL 写法却不同', '问题与动机', '论文 §2.1、工作负载表；exp/2026-10-01-workload-characterization/',
  '应用侧来自 Redset，400 个集群、4.41 亿条查询；智能体侧是100个全新DeepSeek会话、521次工具调用。93%的结构与事实查找在此前会话出现过，SQL探查中38%重复事实而没有逐字相同的SQL。按文本缓存无法服务这些SQL探查；大量结构查找可由元数据缓存服务。不要把所有重复事实都说成指标定义的独有收益。');
table(s, [
  ['观察', '应用负载：Redset', '智能体：100 个全新会话'],
  ['复用对象', '稳定的查询模板', '表结构、粒度、连接等事实'],
  ['重复程度', '半数集群 80% 查询完全重复', '93% 的查找重复此前事实'],
  ['SQL 探查', '34% 读查询由结果缓存回答', '38% 重复事实；逐字重复为 0'],
  ['探索与验证', '知识预先写在应用代码里', '68% 调用用于探索；16% 会话查键唯一性'],
  ['错误方式', '—', '32 个错误答案全部来自成功执行的 SQL'],
], 0.6, 1.68, [2.0, 4.3, 5.8], 0.68, 15);
takeaway(s, '共享能减少重复探索；支撑共享定义的事实仍需在更新后重验。');

// 06 Three research questions.
s = slide('保持共享口径正确，需要回答三个问题', '方法', '论文 §1、§4–6',
  '三个问题对应模型、同快照执行、有界修复。缓存解决重复检查的代价，但不独立回答检查哪些条件、证据在哪个快照有效、失败后怎样恢复。充分性有业务前提，执行保证覆盖声明了修订的查询。');
card(s, 0.6, 1.73, 3.9, 3.9, '该检查什么？', '定义依赖的数据性质不在 SQL 或表结构中明示。\n\n从结构化实现推导四类可执行条件。\n\n命题 1：业务前提下的充分性。', C.blue, 17);
card(s, 4.7, 1.73, 3.9, 3.9, '何时可以使用？', '刚通过的检查只描述一个快照；随后可能有写入提交。\n\n查询与检查读取同一快照。\n\n引理 1：事务性版本相同才复用。', C.green, 17);
card(s, 8.8, 1.73, 3.9, 3.9, '失效后怎么办？', '过滤可恢复每键一行，却选错业务总体。\n\n只发布唯一且经过回归的替代修订。\n\n算法 1：有界搜索与安全撤下。', C.orange, 17);
takeaway(s, '有效性证据成为可维护的状态，并直接约束共享定义的使用。');

// 07 System diagram: editable shapes.
s = slide('中间层贯通准入、维护和执行', '系统', '论文 §3、§5–6',
  '学习题给出显式业务定义，只有判题成功的计算链进入提炼与G1–G7准入。find_metric在依赖版本改变时维护，返回当前有效修订。run_sql声明定义键与修订；核对、SQL审查和可选的同快照执行约束它。默认DML统计不是事务性保证；绑定快照模式需启用事务性版本触发器。');
shape(s, 3.25, 1.65, 6.78, 4.3, C.light);
tx(s, 'MAVRA · 共享指标定义与有效性证据', 3.49, 1.9, 6.3, 0.45, 22, { bold: true, color: C.blue });
card(s, 0.6, 2.35, 2.2, 2.32, '数据智能体', '学习 / 新会话\n查找定义\n声明修订并查询', C.purple, 15);
card(s, 10.54, 2.35, 2.2, 2.32, 'PostgreSQL', '事实与维度表\nSQL 条件检查\n事务性版本', C.green, 15);
arrow(s, 2.87, 3.45, 3.18, 3.45); arrow(s, 10.09, 3.45, 10.46, 3.45);
for (const [i, head, body] of [
  [0, '准入', '成功轨迹 → 结构化候选\nG1–G7 重放后发布'],
  [1, '维护', '版本变化 → 条件重验\n复用 / 撤销 / 有界修复'],
  [2, '执行', '核对声明修订 → SQL 审查\n同快照验证与执行'],
]) {
  shape(s, 3.53, 2.65 + i * 0.94, 6.2, 0.78, C.white);
  tx(s, head, 3.75, 2.81 + i * 0.94, 1.12, 0.4, 19, { bold: true, color: C.blue });
  tx(s, body, 5.06, 2.76 + i * 0.94, 4.42, 0.64, 16);
}
tx(s, '条件结论按身份与依赖版本索引，跨定义、跨智能体共享', 3.52, 5.57, 6.15, 0.3, 13.5, { color: C.muted });
takeaway(s, 'find_metric 返回有效修订；run_sql 在使用时核对，并在绑定快照模式下保证条件成立。');

// 08 Formal model, concise proof and explicit premises.
s = slide('四类条件把数据前提变成可执行的证据', '模型与保证', '论文 §4；命题 1',
  '修订m^r=(B,I,C,E,r)，规范SQL由I编译。B1是业务事件与过滤后键值一一对应；B2是度量表达式给出事件真实度量。四类条件在这两个前提下保证每个保留事件在其角色期间贡献一次，日期覆盖限制遗漏。单位变化、结构等价的业务总体、合法但错误的日期键不由结构条件证明。');
tx(s, '修订 mʳ = (B, I, C, E, r)  =  业务含义 + 结构化实现 + 条件 + 证据 + 修订号', 0.63, 1.62, 12.02, 0.48, 18, { color: C.blue, bold: true });
table(s, [
  ['条件', '检查的性质'],
  ['过滤后键唯一性', '每个业务键在持久过滤后最多一行'],
  ['连接多重性', '允许的连接方向不会把事实行放大'],
  ['时间角色', '事实按声明的日期关系归入期间'],
  ['日期覆盖', '匹配不到日期维度的比例不超过准入时'],
], 0.6, 2.35, [2.37, 4.53], 0.62, 16);
card(s, 7.8, 2.35, 4.9, 3.1, '命题 1：充分性', '业务事件与过滤后的键一一对应，且度量表达式给出事件度量值时：\n\n四类条件成立 ⇒ 每个事件在其期间恰好贡献一次；遗漏受覆盖条件约束。', C.green, 16);
takeaway(s, '保证依赖业务前提；取值单位变化、等价总体和合法但错误的日期键需要额外语义证据。', 6.28, C.orange);

// 09 Selective maintenance and condition reuse.
s = slide('更新触及哪些条件，就维护哪些证据', '维护', '论文 §2.4、§4.3、§5.2；gen/review.tex',
  '这是受控定义库更新store_returns的例子：8个受影响定义要19次定义级检查，而依赖更新表的不同条件只有3个。结论键由语义条件身份和依赖表版本构成，相同键只执行一次检查。通用按SQL与版本索引的缓存能拿到大部分节省。TPC-DS自然共享的175定义是所有SELECT块提取结果，93定义是实际回放库，两者不能混淆。');
card(s, 0.6, 1.72, 3.2, 2.8, '一次数据更新', 'store_returns 变化\n\n未触及表的条件保留\n受影响条件进入重验', C.orange, 18);
arrow(s, 3.91, 3.06, 4.42, 3.06);
card(s, 4.56, 1.72, 3.65, 2.8, '定义级重验证', '8 个受影响定义\n\n重查全部条件\n共 19 次检查', C.purple, 18);
card(s, 8.99, 1.72, 3.7, 2.8, '按条件复用', '3 个不同的受影响条件\n\n每个版本只检查一次\n所有相关定义共享结论', C.blue, 18);
tx(s, '结论索引 = (条件身份, 依赖表版本)\n并发遇到同一检查时共享正在执行的工作', 0.83, 4.95, 5.3, 0.94, 18, { bold: true, color: C.blue });
tx(s, `TPC-DS 的 ${n('TpTemplates')} 个模板自然形成共享：\n${n('TpDefs')} 个定义 / ${n('TpConds')} 个不同条件 / 每条件 ${n('TpPer')} 个实例`, 6.7, 4.95, 5.8, 0.94, 17);
takeaway(s, '重验工作的单位是不同条件；通用版本缓存也能利用这种共享。');

// 10 Snapshot-bound execution.
s = slide('每次声明使用，绑定到查询自己的快照', '执行保证', '论文 §6.2；引理 1；snapshot_exec 为可选模式',
  '一条run_sql调用在可重复读只读事务中读取版本，收集条件，查缓存或同事务检查，失败即拒绝，成功再执行SQL。事务性表版本由写事务内部递增，读到相同依赖版本才允许复用。这个保证属于启用绑定快照模式后的显式声明使用，不属于所有未声明SQL，也不自动证明自写SQL等价于规范SQL。');
const steps = ['开启可重复读\n只读事务', '读取事务性版本\n收集修订条件', '按身份与版本查结论\n缺失则在事务内检查', '条件不成立：拒绝\n交给常规维护', '条件全部成立\n同一事务执行业务 SQL'];
for (let i = 0; i < steps.length; i++) {
  const x = 0.61 + i * 2.47;
  shape(s, x, 1.81, 2.22, 2.04, i === 3 ? 'FFF0E9' : C.light);
  tx(s, String(i + 1), x + 0.17, 1.99, 1.8, 0.5, 25, { bold: true, color: i === 3 ? C.orange : C.blue });
  tx(s, steps[i], x + 0.17, 2.72, 1.93, 0.95, 15);
  if (i < 4) arrow(s, x + 2.25, 2.82, x + 2.41, 2.82);
}
card(s, 0.6, 4.25, 7.15, 1.68, '引理 1：结论复用', '条件读到的每张依赖表事务性版本都相同 ⇒ 条件结论可复用。\n写入与版本增量在同一事务中提交、在同一快照中可见。', C.green, 15.5);
tx(s, '默认 DML 统计异步更新，\n相同统计值不能替代事务性版本。', 8.25, 4.63, 4.2, 1.05, 18, { color: C.orange, bold: true });
takeaway(s, '保证作用于声明的修订及其条件；启用绑定快照模式后，检查和查询读取同一数据状态。');

// 11 Bounded repair with three gates.
s = slide('失效后：唯一、不丢键、过回归才发布修复', '有界修复', '论文 §5.3；算法 1',
  '粒度失效后在低基数列枚举等值过滤。先保留恢复一键一行且不丢原业务键的候选，再要求候选恰好一个，之后G3–G5及G8回归。G8仅在更新触及学习期间且参照反映区分列时提供分辨力。重复装载无候选、备份副本多候选都撤下。修复进行中的其他请求等待已有维护结果。');
const repairGates = [
  ['恢复结构', '过滤后每键一行\n且保留全部业务键', C.blue],
  ['候选唯一', '没有候选或多个候选\n都撤下定义', C.purple],
  ['通过回归', 'G3–G5 重新准入\nG8 与学习参照比较', C.green],
];
repairGates.forEach(([head, body, color], i) => {
  card(s, 0.6 + i * 4.2, 1.75, 3.7, 2.32, head, body, color, 18);
  if (i < 2) arrow(s, 4.41 + i * 4.2, 2.9, 4.69 + i * 4.2, 2.9);
});
card(s, 0.6, 4.39, 5.95, 1.57, '状态流水：一个完成状态过滤', '恢复粒度且不丢键，再用学习题检验修复后的数值。', C.blue, 15.5);
card(s, 6.75, 4.39, 5.95, 1.57, '备份副本：两个总体都每键一行', '结构无法决定业务真相；候选不唯一时保持不可用。', C.orange, 15.5);
takeaway(s, '发布新修订需要三道关；回归参照的分辨力决定自动修复能覆盖多少变化。');

// 12 Experimental design.
s = slide('固定定义验证机制，完整会话验证任务收益', '实验设计', '论文 §7.1；exp/2026-10-02-scenarios-ds/、2026-10-03-session-latency/',
  'Q1–Q4固定定义和数据变化，只替换维护配置；Q5运行完整智能体，每种方法独立学习，所以跨方法正确率差异可能包含学习差异。9种端到端方法各3次，27次运行2586计分题。会话耗时实验固定3个已学库，4种方法每种54会话，总216；相同显式定义的积累实验也是216主分析会话，是另一个实验。');
table(s, [
  ['问题', '比较方式', '规模 / 证据'],
  ['Q1 更新后是否正确', '同一库配对回放', `${n('RpLibs')} 个库 / ${n('RpDefs')} 个定义 / ${n('RpChanges')} 种变化`],
  ['Q2 并发写入时有效', '执行前检查 vs 绑定快照', '确定性交错 + 四组随机并发设置'],
  ['Q3 何时修复或撤下', '回归参照 / 唯一性 / 等待', '配对题 + 备份副本反例'],
  ['Q4 维护工作量', '定义级 / 通用缓存 / 条件级', '100 万–1600 万行；8–32 个脚本智能体'],
  ['Q5 对智能体的作用', '完整学习与使用流程', `9 方法 × 3 次独立运行；${n('ScenValidTasks')} 道计分题`],
  ['Q5 完整会话耗时', '3 个固定库 × 4 种方法', `${n('SlSessions')} 个全新会话；每种方法 54 个`],
], 0.6, 1.65, [2.9, 4.0, 5.2], 0.6, 14.5);
takeaway(s, '机制层覆盖合成数据与真实 TPC-DS SF1；端到端主实验使用 DeepSeek V4.1 Flash。');

// 13 Paired replay, distinguish modeled errors from unit control.
s = slide('Q1：维护后的定义在已建模变化下零错误答案', '实验 / 配对回放', '论文 §7.2；gen/review.tex；同一库、同一变化配对',
  '表中包含全部1530题，单位变化属于未建模取值对照，MAVRA仍有101个错误；已建模变化下错误是0。定义级、通用缓存、条件级逐题答案完全一致。表级测试也把已建模破坏隔离，但少答对的342题由修复或定义本身过滤保留下来，不能全部说成修复题。不必要的不可用是指标比率偶然不受重复影响但粒度条件确已被破坏，属于保守撤下。');
table(s, [
  ['方法', '答对', '答错', '必要不可用', '保守不可用'],
  ['只看结构', n('RpSchemaCorrect'), n('RpSchemaWrong'), n('RpSchemaNeeded'), n('RpSchemaUnneeded')],
  ['表级测试（dbt 式）', n('RpTableCorrect'), n('RpTableWrong'), n('RpTableNeeded'), n('RpTableUnneeded')],
  ['定义级重验', n('RpDefCorrect'), n('RpDefWrong'), n('RpDefNeeded'), n('RpDefUnneeded')],
  ['定义级 + 版本缓存', n('RpCacheCorrect'), n('RpCacheWrong'), n('RpCacheNeeded'), n('RpCacheUnneeded')],
  ['MAVRA', n('RpCondCorrect'), n('RpCondWrong'), n('RpCondNeeded'), n('RpCondUnneeded')],
], 0.6, 1.75, [2.6, 1.0, 1.0, 1.5, 1.5], 0.59, 15, 5);
stat(s, 8.72, 1.95, 3.6, `0 vs ${n('RpSchemaWrongModeled')}`, '已建模变化下的错误答案\nMAVRA vs 只看结构', C.green, 35);
stat(s, 8.72, 4.03, 3.6, n('RpSameCondDef') + '%', '条件级、定义级、通用缓存\n逐题结果一致', C.blue, 35);
tx(s, `全表包含单位变化：各重验证方法的 ${n('RpCondWrong')} 个错误均来自这个取值语义对照。\n表级测试隔离破坏；MAVRA 多答对 ${n('RpTableOnlyCond')} 题，来自修复或定义自带过滤。`, 0.66, 5.48, 11.94, 0.79, 15.5);
takeaway(s, '配对回放隔离了学习差异：维护方式改变工作量，不改变这些题的答案。');

// 14 TPC-DS external validity.
s = slide('Q1：真实 TPC-DS SF1 上重复同一配对设计', '实验 / TPC-DS', '论文 §7.2；TPC-DS 模板导出的回放库；gen/review.tex',
  '数据来自dsdgen SF1，约290万行门店销售和24张表。93个结构化实现可表达的模板定义中91个通过准入，两项学习期为空。该93是回放库，175是自然共享统计。为注入重复等变化，事实表主键改普通索引，decimal表示放宽。每方法981题；MAVRA已建模变化0错，单位变化72错，修复279题。维护耗时主要是重复装载无解的过滤搜索。');
bullets(s, [
  'dsdgen SF1：约 290 万行门店销售，24 张表。',
  `99 个官方模板导出 ${n('TrDefs')} 个可表达定义；${n('TrSeeded')} 个通过准入。`,
  '相同的 11 类注入变化；状态流水、版本化更正、维表拉链可修复。',
  '重复装载、日期键改写、备份副本下撤下定义。',
], 0.6, 1.84, 6.45, 3.95, 18);
stat(s, 7.62, 1.83, 2.35, n('TrCondWrongModeled'), 'MAVRA 已建模变化下\n错误答案', C.green);
stat(s, 10.22, 1.83, 2.4, n('TrSchemaWrongModeled'), '只看结构\n错误答案', C.orange);
stat(s, 7.62, 4.02, 4.82, n('TrCondRepairedTasks'), `经修复答对的题次\n每种方法合计 ${n('TrCondN')} 道计分题`, C.blue);
takeaway(s, '定义库来自官方模板；变化仍由实验注入，单位语义变化仍超出四类条件。');

// 15 Snapshot evidence and writer cost correctly labeled as throughput.
s = slide('Q2：同快照执行消除了条件违规作答', '实验 / 并发写入', '论文 §7.3；gen/review.tex；四组随机并发设置',
  '不通知写入下执行前检查3.8–4.6%的使用在条件违规数据上作答；绑定快照在11297次作答里0违规。这是满足条件的保证，不是所有业务答案100%正确。读者中位延迟26–29ms无明显改变，触发器代价需要明确写吞吐相对无触发器：单写者0.70倍，32写者16分片0.97倍，不分片0.36倍。较小比值意味着吞吐下降，不能写成延迟成本倍数。');
stat(s, 0.86, 1.91, 5.7, `${n('SnPreUnannMin')}–${n('SnPreUnannMax')}%`, '执行前检查：未通知写入下\n在条件违规数据上作答的使用', C.orange, 43);
stat(s, 7.08, 1.91, 5.35, `0 / ${n('SnSnapAnswered')}`, '绑定快照：随机并发合计\n在条件违规数据上作答的使用', C.green, 43);
table(s, [
  ['读者 / 写者代价', '观测结果'],
  ['读者中位延迟', `${n('SnStressPFiftyLo')}–${n('SnStressPFiftyHi')} ms；两种模式相同`],
  ['单写者：相对无触发器的吞吐', `${n('SnWriteSeq')}×`],
  ['32 写者：16 分片 / 不分片吞吐', `${n('SnWriteConcTT')}× / ${n('SnWriteHotTT')}×`],
], 0.6, 4.25, [5.6, 6.5], 0.47, 15.5);
takeaway(s, '事务性版本把复用结论与快照绑定；写者吞吐代价取决于更新粒度和计数分片。');

// 16 Maintenance cost, no hard-coded scope statistic.
s = slide('Q4：共享条件减少维护，通用缓存也得到节省', '实验 / 维护代价', '论文 §7.5；gen/review.tex；19 定义、错峰到达',
  '图中定义级归一为100%。仅范围86.8%，通用版本缓存16.7%，MAVRA14.0%，都来自当前review宏，替换旧PPT里写死的88。零共享对照95–102%，说明节省来自复用且跟踪条件开销不可见。规模扩展比例12.0–13.0%是另一个实验，不和14.0%的原受控矩阵混作同一数据点。同时到达下在途合并已减掉重复，差距缩小。');
tx(s, '相对定义级的维护数据库时间（%）', 0.85, 1.65, 6.6, 0.24, 12, { color: C.muted });
chart(s, [{ name: '相对定义级的维护 DB 时间（%）', labels: ['定义级', '仅范围', '通用缓存', 'MAVRA'],
  values: [100, num('CbStagScopeSix'), num('CbStagCacheSix'), num('CbStagCondSix')] }], 0.6, 1.88, 7.04, 4.02, [C.blue], 115, { dataLabelFormatCode: '0.0' });
bullets(s, [
  `定义级随定义数增长：${n('CbStagDefOne')} → ${n('CbStagDefSix')} 秒。`,
  `19 个定义：MAVRA 为定义级的 ${n('CbStagCondSix')}%；通用缓存 ${n('CbStagCacheSix')}%。`,
  `零共享对照：所有方法为定义级的 ${n('CbZeroMin')}–${n('CbZeroMax')}%。`,
  `100 万–1600 万行规模实验：比例保持在 ${n('EoneRatioSixteen')}–${n('EoneRatioFour')}%。`,
], 8.0, 1.84, 4.66, 4.27, 17);
takeaway(s, '核心贡献是条件、使用保证和修复规则；结论复用的节省可由通用版本缓存得到。');

// 17 End-to-end accuracy, five readable baselines.
s = slide('Q5：共享提高准确率，维护在破坏性变化下起作用', '实验 / 端到端', '论文 §7.6；9 方法 × 3 次；gen/scen-ds.tex',
  '总体正确率不共享32%、无守护共享75%、MAVRA81%，不能将共享增益全归于维护。已建模破坏MAVRA73%，轨迹检索57%，自验证63%，智能体参照74%。预定比较73%-57%的未舍入差16，95%整群自助区间14–18。对自验证的差11来自未舍入统计，不能简单由显示舍入的73和63计算。固定库维护相同，跨端到端配置的差异还包含各自学习库差异。');
const methods = [['不共享', 'DsNoShare'], ['轨迹检索', 'DsTraj'], ['检索+自验证', 'DsTrajVerify'], ['无守护共享', 'DsNoguard'], ['MAVRA', 'DsCond']];
tx(s, '最终答案正确率（%）', 0.85, 1.57, 6.6, 0.24, 12, { color: C.muted });
chart(s, [
  { name: '全部情形', labels: methods.map((m) => m[0]), values: methods.map((m) => num(m[1] + 'All')) },
  { name: '已建模破坏', labels: methods.map((m) => m[0]), values: methods.map((m) => num(m[1] + 'Modeled')) },
], 0.6, 1.79, 7.95, 4.5, [C.blue, C.orange], 110);
bullets(s, [
  `共享本身：${n('DsNoShareAll')}% → ${n('DsNoguardAll')}%；维护后 ${n('DsCondAll')}%。`,
  `已建模破坏：${n('DsCondModeled')}% vs ${n('DsTrajModeled')}%；预定差 +${n('DsCmpModeledTraj')} 个百分点（95% 区间 ${n('DsCmpModeledTrajLo')}–${n('DsCmpModeledTrajHi')}）。`,
  `让检索者自行验证：${n('DsTrajVerifyModeled')}%；MAVRA 仍领先。`,
  `改用智能体学习 SQL 作修复参照：${n('DsCondExrefModeled')}%。`,
], 8.88, 1.83, 3.83, 4.33, 15.5);
takeaway(s, `备份副本下检索 ${n('DsTrajMirror')}% vs MAVRA ${n('DsCondMirror')}%：安全撤下会放弃部分仍正确的知识。`, 6.35, C.orange);

// 18 New fixed-library session study.
s = slide('新增会话证据：共享定义减少任务时间和 token', '实验 / 完整会话', '论文 §7.6；216 个固定库会话；gen/session-latency.tex',
  '三份固定已学库，每份4个有效定义，四种维护配置。每题全新会话、名称题，不共享组没有指标定义但基础中间层相同。完成时间包括LLM、工具和入场排队，学习与导入成本单列，答案缓存关闭。每方法54题，三种共享都54/54，不共享16/54。输入token每次尝试口径减少40.7%；每正确答案口径不同，不能混用。此处只支持相对不共享的任务收益。');
table(s, [
  ['方法', '正确 / 54', '平均完成 s', 'LLM 调用/题', '输入 token/尝试'],
  ['不共享定义', `${n('SlNoneCorrect')}/${n('SlNoneN')}`, n('SlNoneMean'), n('SlNoneRounds'), integer(sessionPolicy('no-share').tokens.input_tokens / sessionPolicy('no-share').n)],
  ['定义级重验', `${n('SlDefCorrect')}/${n('SlDefN')}`, n('SlDefMean'), n('SlDefRounds'), integer(sessionPolicy('definition').tokens.input_tokens / sessionPolicy('definition').n)],
  ['通用版本缓存', `${n('SlCacheCorrect')}/${n('SlCacheN')}`, n('SlCacheMean'), n('SlCacheRounds'), integer(sessionPolicy('definition-cache').tokens.input_tokens / sessionPolicy('definition-cache').n)],
  ['MAVRA', `${n('SlCondCorrect')}/${n('SlCondN')}`, n('SlCondMean'), n('SlCondRounds'), integer(sessionPolicy('condition').tokens.input_tokens / sessionPolicy('condition').n)],
], 0.6, 1.78, [2.6, 1.75, 2.4, 2.5, 2.85], 0.68, 16, 4);
stat(s, 0.84, 5.32, 3.45, `−${n('SlCondInputSaveNone')}%`, 'MAVRA 相对不共享\n每次尝试的输入 token', C.blue, 34, 0.6);
tx(s, '3 个固定库 × 4 种方法 × 18 个会话 = 216\n覆盖首次、热复用、正常追加、破坏后首用和突发', 4.7, 5.48, 7.9, 0.86, 18, { color: C.muted });

// 19 Include the complete latency result and model tail.
s = slide('完整延迟结果：更新后首用更快，突发仍有模型长尾', '实验 / 完整会话', 'exp/2026-10-03-session-latency/stats.json、report.md',
  '每个串行阶段每方法9个样本、突发18个。MAVRA追加后12.53秒、状态后28.41秒，低于通用缓存18.00/32.01；突发78.07高于58.05。一个356.23秒长尾中338.45秒来自LLM接口，全部保留。LLM接口时间包含网络、后端等待和重试，不能当成纯推理时间。全矩阵MAVRA均值37.68比通用缓存31.97更高，DB总工作量减少25.3%不推出整体加速。只有3库，描述性结果不宣称显著。');
tx(s, '平均完整会话完成时间（秒）', 0.85, 1.65, 6.6, 0.24, 12, { color: C.muted });
chart(s, [
  { name: '通用版本缓存', labels: ['追加后首用', '状态破坏后首用', '破坏后突发'], values: ['after-append', 'after-status', 'burst-status'].map((p) => phaseMean('definition-cache', p)) },
  { name: 'MAVRA', labels: ['追加后首用', '状态破坏后首用', '破坏后突发'], values: ['after-append', 'after-status', 'burst-status'].map((p) => phaseMean('condition', p)) },
], 0.6, 1.9, 7.02, 4.13, [C.muted, C.blue], 95, { dataLabelFormatCode: '0.00' });
card(s, 8.0, 1.89, 4.69, 1.85, '数据库工作量减少', `MAVRA 比通用缓存少 ${n('SlCondDBSaveCache')}% 的 DB 查询时间。`, C.blue, 16.5);
card(s, 8.0, 4.0, 4.69, 1.97, '整体延迟优势尚未建立', `全矩阵平均 ${n('SlCondMean')} vs ${n('SlCacheMean')} s。\n一次 ${n('SlSlowTotal')} s 长尾中，LLM 接口占 ${n('SlSlowLLM')} s。`, C.orange, 16);
takeaway(s, '测量包括 LLM、工具与排队；数据库工作量减少与完整会话加速需分别报告。', 6.35);

// 20 Matched business knowledge experiment, all four policies.
s = slide('业务定义相同、正确率相同时，共享仍减少探索', '实验 / 探索开销', '论文 §7.6；exp/2026-10-03-shared-memory/analysis/summary.json',
  '这项补充实验给消费者相同显式业务定义，三个匹配生产者流，四种方法复用相同生产者前缀，关闭答案缓存、消费者跨题写回和策略适应。216主分析会话，四组均54/54，因此开销差别不由业务含义是否已知或正确率差别解释。积累共享包括画像、连接路径和定义；这里不是只归因于指标定义，且消费者时间不含生产者学习和提炼成本。百分比从未舍入计数算出。');
const policies = [['隔离探索', 'isolated'], ['冻结共享', 'frozen'], ['逐步积累共享', 'accumulating'], ['轨迹检索', 'trajectory']];
table(s, [
  ['方法', '正确 / 54', '结构查找/题', 'SQL 探查/题', '平均完成 s'],
  ...policies.map(([label, policy]) => [label, `${memory.primary[policy].correct}/${memory.primary[policy].n}`,
    fixed(mem(policy, 'schema_calls')), fixed(mem(policy, 'sql_probes')), fixed(mem(policy, 'seconds'))]),
], 0.6, 1.84, [2.7, 1.75, 2.6, 2.5, 2.55], 0.64, 16, 3);
const schemaSaving = (1 - mem('accumulating', 'schema_calls') / mem('isolated', 'schema_calls')) * 100;
const probeSaving = (1 - mem('accumulating', 'sql_probes') / mem('isolated', 'sql_probes')) * 100;
stat(s, 0.85, 5.23, 3.7, `−${fixed(schemaSaving, 1)}%`, '积累共享相对隔离\n每题结构查找次数', C.blue, 34, 0.6);
stat(s, 5.0, 5.23, 3.6, `−${fixed(probeSaving, 1)}%`, '积累共享相对隔离\n每题 SQL 探查次数', C.green, 34, 0.6);
tx(s, '画像、连接路径和定义共同复用\n消费者完成时间不含生产者学习成本', 9.08, 5.63, 3.65, 0.87, 15.5, { color: C.muted });

// 21 Discussion: scope and concrete next steps.
s = slide('讨论：保证范围与下一步扩展', '讨论', '论文 §6.3、§7.6、§9；gen/review.tex',
  '声明条件成立不等于任何自写SQL都正确，规范编译是推荐的计算表示。此前样本25.7%答案未声明定义，声明正确修订仍1.3%错误。下一步扩展取值语义条件，识别未声明使用，增加去重和重映射修复。真实TPC-DS数据已覆盖但变化注入，端到端主实验一个模型3重复，不能称为真实生产更新历史。');
card(s, 0.6, 1.74, 3.9, 3.68, '使用保证', `声明修订 + 绑定快照模式：条件在所读数据上成立。\n\n未声明使用不受此契约约束；自写 SQL 仍可能偏离规范计算。`, C.blue, 17);
card(s, 4.7, 1.74, 3.9, 3.68, '语义与修复', '业务证据提供含义。结构条件不能识别单位变化或等价总体。\n\n下一步：取值条件、去重、日期键重映射。', C.orange, 17);
card(s, 8.8, 1.74, 3.9, 3.68, '评估与推广', '机制层：合成数据 + TPC-DS SF1。端到端：一个模型、3 次运行。\n\n下一步：真实更新历史、更多模型与业务库。', C.green, 17);
takeaway(s, `此前答案中 ${n('DuUndeclPct')}% 未声明定义；声明正确修订后仍有 ${n('DuDevPct')}% 因 SQL 偏离而答错。`, 6.28, C.orange);

// 22 Closing, before optional appendix.
s = slide('数据库持续维护共享定义成立的证据', '结论', '论文 §10',
  '收束回主张：学到的定义成为长期状态；四类条件明确什么要检查，事务性版本和同快照执行明确何时可用，唯一且回归的修复明确失败时怎么办。端到端正确率不等于机制保证，相对不共享的任务收益也不等于相对通用缓存全面更快。附录供问答使用。', { dark: true });
tx(s, '让共享知识在变化的数据上继续成立', 0.8, 1.16, 11.65, 0.9, 34, { bold: true, color: C.white });
tx(s, '①  定义推出条件：粒度、连接、时间角色、覆盖\n②  证据约束使用：按版本复用，在查询自身快照验证\n③  失效有界修复：不丢键、唯一、过回归，否则撤下\n④  同时衡量：正确性、维护工作量和完整任务开销', 0.86, 2.69, 11.55, 2.36, 23, { color: 'D8E5F3', paraSpaceAfter: 13 });
tx(s, '共享使智能体少探索；维护使已建模的数据破坏得到发现。', 0.86, 5.65, 11.55, 0.55, 21, { bold: true, color: '88B9F0' });

// 23 Appendix: baseline coverage (conceptual, not extra experimental cells).
s = slide('各类方法分别覆盖生命周期的哪些环节', '基线与定位', '论文 §2.4、基线表；概念对照',
  '这张表是机制定位，不表示所有行都运行了同一端到端矩阵。表级测试在配对回放运行；定义级+缓存在代价及固定库会话运行。端到端场景是9种方法，不是把此表或所有实验的配置合成更多方法。MAVRA绑定快照能力仅在相应模式启用时成立。', { appendix: true });
table(s, [
  ['方法', '正常更新', '条件破坏后', '使用时保证', '维护单位'],
  ['轨迹检索', '复用 SQL', '依赖智能体自行发现', '不绑定条件', '检索的成功轨迹'],
  ['只看结构', '保留', '结构未变时漏检', '结构 / 修订核对', '结构指纹'],
  ['表级测试（dbt 式）', '保留', '隔离相关表上的定义', '执行前的测试', '按表声明的测试'],
  ['写入即撤销', '撤下并重学', '撤下并重学', '执行前核对', '每次写入'],
  ['定义级 + 版本缓存', '保留', '同样的修复与回归', '执行前检查', '缓存检查 SQL'],
  ['MAVRA', '保留', '有界修复或撤下', '可绑定同一快照', '变化触及的不同条件'],
], 0.6, 1.73, [2.7, 1.63, 3.05, 2.46, 2.26], 0.64, 14, 6);
takeaway(s, '共享、验证和缓存构成基础；本文研究指标定义的有效性生命周期。');

// 24 Appendix: G8 reference and uniqueness evidence.
s = slide('修复参照决定自动化范围，唯一性挡住歧义', '修复细节', '论文 §7.4；gen/review.tex、scen-ds.tex',
  '配对1470题用智能体参照比判题参照少答对，但差别全部变成不可用，没有新增错误。端到端参照组74%对73%仅描述差异，不称相等；差1pp区间-1至3说明无明确准确率劣化证据。备份反例没有唯一性规则且参照预见来源列会错误发布，4题错2。有唯一性规则时两种参照都撤下。修复等待burst63降0说的是机制基准不可用，不是LLM正确题数。', { appendix: true });
table(s, [
  ['同一批配对题', '判题学习查询参照', '智能体学习 SQL 参照'],
  [`${n('RpPairN')} 道题：答对`, n('RpPairJudge'), n('RpPairEx')],
  ['新增错误', '—', '0（差别全部转为不可用）'],
  ['端到端：已建模破坏正确率', n('DsCondModeled') + '%', n('DsCondExrefModeled') + '%'],
], 0.6, 1.79, [4.6, 3.6, 3.9], 0.65, 16);
card(s, 0.6, 4.65, 5.95, 1.58, '反例：追加备份副本', '不要求候选唯一时可发布错误修复；要求唯一时两种参照均撤下。', C.orange, 16);
card(s, 6.75, 4.65, 5.95, 1.58, '修复期间等待', `同时到达的不可用从 ${n('WrCondOff')} 降为 0；请求共享已有维护结果。`, C.blue, 16);
takeaway(s, 'G8 只有在变化触及学习期间且参照反映区分列时，才提供额外分辨力。');

// 25 Appendix: directly map this deck's revision to current paper.
s = slide('本次更新对应论文的哪些变化', '论文与汇报同步', '当前 overleaf/；补充证据保留为论文相应段落的支持',
  '当前主线仍是共享指标定义有效性维护。10月3日晚共享数据库知识层重构已于10月4日回退；本汇报根据当前正文。新增会话和积累实验按当前摘要、引言、代价段落使用，不把策略排序或元数据诊断升级成论文主贡献。为可复算，所有宏缺失会报错，session宏与原始统计对齐，源哈希另存。', { appendix: true });
table(s, [
  ['论文变化', '汇报处理', '对应页'],
  ['摘要与引言强化中心主张', '新会话复用 + 三个变化 + 持续有效性证据', '2–6'],
  ['固定库完整会话证据进入正文', '正确率、时间、调用和 token；并列报告缓存基线', '18–19'],
  ['相同业务定义下的探索开销', '四组同为 54/54；结构查找、SQL 探查和时间', '20'],
  ['模型、命题、引理与有界修复', '保留三项方法贡献，配套机制层证据', '8–16'],
  ['讨论和研究边界', '声明使用、取值语义、修复歧义与真实更新历史', '21、24'],
], 0.6, 1.8, [3.5, 6.9, 1.7], 0.68, 15.5);
takeaway(s, '论文中的主张、证据口径与汇报一致；补充实验按其实际支持范围呈现。');

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
