// MAVRA 汇报 PPT：数值全部从 overleaf/gen/*.tex 的宏读取，与论文一致。
// 用法：node build-deck.js /path/to/overleaf  →  mavra-report.pptx
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const { applyTheme } = require(process.env.SKILL_DIR + "/scripts/apply_theme.js");

const overleaf = process.argv[2] || "../../../../../home/zhanhao/mingtai/ppt/agentdb-mid/overleaf";
const M = {};
for (const f of ["numbers.tex", "scen-ds.tex", "review.tex", "numbers-prev.tex"]) {
  const p = path.join(overleaf, "gen", f);
  if (!fs.existsSync(p)) continue;
  const txt = fs.readFileSync(p, "utf8");
  const re = /\\newcommand\{\\(\w+)\}\{/g;
  let m;
  while ((m = re.exec(txt))) {
    let depth = 1, i = re.lastIndex, start = i;
    while (i < txt.length && depth > 0) { if (txt[i] === "{") depth++; else if (txt[i] === "}") depth--; i++; }
    M[m[1]] = txt.slice(start, i - 1).replace(/\{,\}/g, ",").replace(/\\,/g, " ");
    re.lastIndex = i;
  }
}
const n = (k) => (k in M ? M[k] : "–");

const THEME = {
  name: "MAVRA",
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  colors: {
    dk1: "1B2A41", lt1: "FFFFFF", dk2: "3D4C63", lt2: "EEF2F7",
    accent1: "2A78D6", accent2: "EB6834", accent3: "1BAF7A", accent4: "EDA100", accent5: "8E44AD", accent6: "6B6A66",
    hlink: "2A78D6", folHlink: "8E44AD",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "MAVRA：面向数据智能体的共享指标定义有效性维护";
pres.author = "Anonymous";
const C = pres.SchemeColor;
const W = 13.33, H = 7.5;

// ── 版式 ──
pres.defineSlideMaster({
  title: "TITLE", background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.1, w: 11.7, h: 1.6, fontSize: 40, bold: true, color: C.background1, align: "left", margin: 0 } } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.9, w: 11.7, h: 1.8, fontSize: 20, color: THEME.colors.lt2, align: "left", margin: 0 } } },
  ],
});
pres.defineSlideMaster({
  title: "SECTION", background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.6, w: 11.7, h: 1.4, fontSize: 36, bold: true, color: C.background1, align: "left", margin: 0 } } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.1, w: 11.7, h: 1.4, fontSize: 18, color: THEME.colors.lt2, align: "left", margin: 0 } } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: THEME.colors.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.9, fontSize: 30, bold: true, color: C.text1, align: "left", margin: 0 } } },
    { text: { text: "MAVRA · SIGMOD 2027 投稿汇报", options: { x: 0.6, y: 7.05, w: 6, h: 0.3, fontSize: 10, color: THEME.colors.dk2, margin: 0 } } },
  ],
  slideNumber: { x: 12.3, y: 7.05, w: 0.6, h: 0.3, fontSize: 10, color: THEME.colors.dk2 },
});

// ── 小部件 ──
function card(slide, x, y, w, h, head, body, color) {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: THEME.colors.lt2 }, line: { color: THEME.colors.lt2 }, rectRadius: 0.08, objectName: "card " + head });
  slide.addShape(pres.ShapeType.ellipse, { x: x + 0.2, y: y + 0.2, w: 0.32, h: 0.32, fill: { color: color || THEME.colors.accent1 }, line: { color: color || THEME.colors.accent1 }, objectName: "dot " + head });
  slide.addText(head, { x: x + 0.65, y: y + 0.12, w: w - 0.8, h: 0.5, fontSize: 16, bold: true, color: C.text1, margin: 0, isTextBox: true, objectName: "head " + head });
  slide.addText(body, { x: x + 0.2, y: y + 0.7, w: w - 0.4, h: h - 0.85, fontSize: 13, color: C.text2, margin: 0, isTextBox: true, valign: "top", objectName: "body " + head });
}
function stat(slide, x, y, w, big, label, color) {
  slide.addText(big, { x, y, w, h: 0.95, fontSize: String(big).length > 7 ? 28 : 40, bold: true, color: color || THEME.colors.accent1, margin: 0, isTextBox: true, objectName: "stat " + label });
  slide.addText(label, { x, y: y + 0.95, w, h: 0.75, fontSize: 12.5, color: C.text2, margin: 0, isTextBox: true, valign: "top", objectName: "label " + label });
}
function bullets(slide, items, x, y, w, h, size) {
  slide.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6 } })),
    { x, y, w, h, fontSize: size || 15, color: C.text1, margin: 0, isTextBox: true, valign: "top", objectName: "bullets" });
}
function tbl(slide, rows, x, y, w, colW, size) {
  const data = rows.map((r, i) => r.map((c) => ({ text: String(c), options: { bold: i === 0, fontSize: size || 12, color: i === 0 ? "FFFFFF" : THEME.colors.dk1, fill: { color: i === 0 ? THEME.colors.dk1 : i % 2 ? "FFFFFF" : THEME.colors.lt2 }, align: typeof c === "number" || /^[\d.,–%+-]+$/.test(String(c)) ? "right" : "left", valign: "middle", margin: 0.05 } })));
  slide.addTable(data, { x, y, w, colW, border: { type: "solid", color: "FFFFFF", pt: 1 }, fontFace: "+mn-lt", objectName: "table" });
}

// ── 1 封面 ──
pres.addSection({ title: "开场" });
let s = pres.addSlide({ masterName: "TITLE", sectionTitle: "开场" });
s.addText("MAVRA：面向数据智能体的共享指标定义有效性维护", { placeholder: "title" });
s.addText("Keeping Shared Metric Definitions Valid for Data Agents\nSIGMOD 2027 Research Track 投稿汇报 · 2026 年 10 月", { placeholder: "body" });
s.addNotes("汇报结构：问题—三个核心问题—模型与保证—实验—边界。");

// ── 2 一页看懂 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "开场" });
s.addText("共享学到的口径是变化数据库上的长期状态，纯数据更新会静默打破它", { placeholder: "title" });
card(s, 0.6, 1.5, 3.9, 2.6, "现象", "智能体靠探索学到“退货金额 = SUM(sr_return_amt)”，共享给所有智能体。ETL 改为状态流水后，每笔退货多一行“申请”：表结构没变，SQL 照常执行。", THEME.colors.accent2);
card(s, 4.7, 1.5, 3.9, 2.6, "后果", "单期查询返回 6,588,699.86，真值 3,294,349.93——没有任何报错。我们的轨迹里 32 个错误答案全部来自执行成功的 SQL。", THEME.colors.accent4);
card(s, 8.8, 1.5, 3.9, 2.6, "本文", "把口径的有效性证据当作一等的、版本化的状态：推出可执行条件并证明其充分，把每次声明使用绑定到查询自身快照上成立的结论，只做唯一且过回归的修复。", THEME.colors.accent1);
stat(s, 0.8, 4.5, 2.6, n("ScenAccNoShare") + "% → " + n("DsNoguardAll") + "%", "共享本身带来的端到端正确率提升", THEME.colors.accent5);
stat(s, 4.0, 4.5, 2.6, n("DsNoguardAll") + "% → " + n("ScenAccCond") + "%", "维护再带来的提升；已建模破坏下 " + n("DsNoguardModeled") + "% → " + n("DsCondModeled") + "%", THEME.colors.accent1);
stat(s, 7.2, 4.5, 2.6, "0", "维护后的定义在已建模变化下提供的错误答案（只看结构：" + n("RpSchemaWrongModeled") + "）", THEME.colors.accent3);
stat(s, 10.4, 4.5, 2.6, "0 / " + n("SnSnapAnswered"), "绑定快照执行下在违反条件的数据上作答的次数（执行前检查最多 " + n("SnPreUnannMax") + "%）", THEME.colors.accent2);

// ── 3 动机：负载 ──
pres.addSection({ title: "问题" });
s = pres.addSlide({ masterName: "SECTION", sectionTitle: "问题" });
s.addText("为什么是一个数据库问题", { placeholder: "title" });
s.addText("智能体重复的是知识，不是查询；口径一旦共享，就是变化数据库上的长期状态", { placeholder: "body" });

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "问题" });
s.addText("负载刻画：应用重复查询，智能体重复知识", { placeholder: "title" });
tbl(s, [
  ["", "应用负载（Redset，400 个集群，4.41 亿查询）", "智能体负载（100 个全新会话，521 次调用）"],
  ["重复的东西", "相同模板（半数集群 80% 查询完全重复）", "相同事实：93% 的查找重复此前会话已得到的事实"],
  ["SQL 文本复用", "结果缓存命中 34% 的读查询", "SQL 探查 38% 重复事实，但没有一条文本相同"],
  ["探索占比", "—", "68% 的调用用于查找与探查"],
  ["自行验证", "—", "只有 16% 的会话检查过键唯一性"],
  ["出错方式", "—", "32 个错误答案全部来自执行成功的 SQL；31 个发生在题目只给指标名时"],
], 0.6, 1.5, 12.1, [2.2, 4.6, 5.3], 12.5);
s.addText("结论：按查询文本的缓存捕获不到智能体的复用；共享口径有效，但它变成了必须维护的状态。", { x: 0.6, y: 5.6, w: 12.1, h: 0.6, fontSize: 15, italic: true, color: THEME.colors.accent1, margin: 0, isTextBox: true, objectName: "takeaway" });

// ── 5 三个问题与策略阶梯 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "问题" });
s.addText("保持共享口径正确要回答三个问题", { placeholder: "title" });
card(s, 0.6, 1.4, 3.9, 2.3, "检查什么？", "口径依赖的性质既不在 SQL 里，也不在表结构里：过滤后键唯一、连接不放大、日期按预期角色归期。结构演化支持看不到纯数据破坏；数据验证系统不知道哪个口径依赖哪条性质。", THEME.colors.accent1);
card(s, 4.7, 1.4, 3.9, 2.3, "何时可以依赖？", "检查通过只描述一个快照；核对与执行之间可能有写入提交，DML 统计既不随事务也不即时。并发写入下执行前检查有最多 " + n("SnPreUnannMax") + "% 的使用在违反条件的数据上作答。", THEME.colors.accent2);
card(s, 8.8, 1.4, 3.9, 2.3, "失败了怎么办？", "逐写入撤销丢掉仍然有效的知识；修复有风险——过滤能恢复每键一行却选错总体，回归测试能否发现取决于参照知道什么。", THEME.colors.accent4);
tbl(s, [
  ["策略", "正常追加", "纯数据破坏", "使用期间的写入", "每次更新的工作"],
  ["只看结构", "保留", "过期使用", "不检查", "无"],
  ["表级测试（dbt 式）", "保留", "隔离", "执行前检查", "按表声明的测试"],
  ["写入即撤销", "重学", "重学", "执行前检查", "大模型重学"],
  ["定义级重验（+ 版本缓存）", "保留", "修复", "执行前检查", "受影响定义的条件（去重）"],
  ["MAVRA", "保留", "有界修复", "同一快照", "变化触及的不同条件"],
], 0.6, 4.0, 12.1, [3.0, 1.6, 2.0, 2.4, 3.1], 12);

// ── 6 模型 ──
pres.addSection({ title: "方法" });
s = pres.addSlide({ masterName: "SECTION", sectionTitle: "方法" });
s.addText("有效性模型、使用时的保证、有界修复", { placeholder: "title" });
s.addText("命题 1：条件充分　·　引理 1：结论复用可靠　·　算法 1：唯一且过回归的修复", { placeholder: "body" });

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "方法" });
s.addText("模型：定义 = 业务含义 + 结构化实现 + 可执行条件 + 证据", { placeholder: "title" });
bullets(s, [
  "修订 m^r = (B, I, C, E, r)：实现 I 记录事实表、聚合、粒度、时间角色、连接引用、持久过滤；规范 SQL 由 I 编译",
  "四类条件，从 I 机械推出：过滤后键唯一 KeyUnique(T, K, φ)、连接多重性、时间角色、覆盖",
  "条件身份按语义而非文本：键列顺序、过滤写法不影响；结论按 (条件身份, 依赖表版本) 索引，跨定义、跨智能体复用",
], 0.6, 1.4, 6.4, 3.6, 14.5);
s.addShape(pres.ShapeType.roundRect, { x: 7.3, y: 1.4, w: 5.4, h: 4.9, fill: { color: THEME.colors.lt2 }, line: { color: THEME.colors.lt2 }, rectRadius: 0.08, objectName: "prop box" });
s.addText([
  { text: "命题 1（充分性）", options: { bold: true, color: THEME.colors.accent1, breakLine: true } },
  { text: "若业务前提 B1（事件与过滤后的键一一对应）、B2（度量表达式给出事件的度量值）成立，且四类条件在快照 D_s 上成立，则规范 SQL 对每个期间返回的，是角色日期落在该期间的事件度量值的聚合，每个事件恰好计一次；遗漏的只有关联不上日期维度的事件，其比例受覆盖条件约束。", options: { breakLine: true } },
  { text: " ", options: { breakLine: true } },
  { text: "检测边界由两条前提划定", options: { bold: true, color: THEME.colors.accent2, breakLine: true } },
  { text: "B2 关乎取值：单位变化不违反任何条件；B1 可被多个总体同时满足：备份副本后主表与副本各自每键一行，结构上无从区分。反过来，凡使事件被计两次或从所有期间消失的纯数据更新，都会违反某个条件。" },
], { x: 7.5, y: 1.55, w: 5.0, h: 4.6, fontSize: 12.5, color: C.text1, margin: 0, isTextBox: true, valign: "top", objectName: "prop text" });
s.addText("TPC-DS 99 个官方模板里自然存在共享：" + n("TpDefs") + " 个定义、" + n("TpConds") + " 个不同条件，每条件 " + n("TpPer") + " 个实例", { x: 0.6, y: 5.3, w: 6.4, h: 0.9, fontSize: 13, italic: true, color: THEME.colors.accent5, margin: 0, isTextBox: true, objectName: "sharing note" });

// ── 8 绑定快照 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "方法" });
s.addText("使用时的保证：绑定快照的执行", { placeholder: "title" });
const steps = ["开可重复读只读事务，读事务性版本", "收集声明修订的条件", "按 (身份, 快照版本) 查结论，否则在事务内检查", "任一条件失败即拒绝，交常规维护", "同一事务内执行业务 SQL"];
steps.forEach((t, i) => {
  const x = 0.6 + i * 2.45;
  s.addShape(pres.ShapeType.ellipse, { x, y: 1.5, w: 0.5, h: 0.5, fill: { color: THEME.colors.accent1 }, line: { color: THEME.colors.accent1 }, objectName: "step dot " + i });
  s.addText(String(i + 1), { x, y: 1.5, w: 0.5, h: 0.5, fontSize: 14, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "step no " + i });
  s.addText(t, { x, y: 2.1, w: 2.25, h: 1.2, fontSize: 12.5, color: C.text1, margin: 0, isTextBox: true, valign: "top", objectName: "step " + i });
});
s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 3.5, w: 7.2, h: 2.4, fill: { color: THEME.colors.lt2 }, line: { color: THEME.colors.lt2 }, rectRadius: 0.08, objectName: "lemma box" });
s.addText([
  { text: "引理 1（结论复用）", options: { bold: true, color: THEME.colors.accent1, breakLine: true } },
  { text: "事务性版本 v_s(T) 由语句级触发器在写事务内递增（按后端分片，取和）。两个快照对条件 c 读到的每张表版本相同 ⇒ c(D_s1) = c(D_s2)。证明：快照按已提交事务集合嵌套；写 T 的事务与其计数增量同时可见，版本相等意味着两快照之间没有写 T 的事务。默认的 DML 统计不满足这一性质——这正是第 7.3 节测到的空隙。" },
], { x: 0.8, y: 3.65, w: 6.8, h: 2.1, fontSize: 12.5, color: C.text1, margin: 0, isTextBox: true, valign: "top", objectName: "lemma text" });
stat(s, 8.2, 3.6, 2.2, n("SnPreUnannMin") + "–" + n("SnPreUnannMax") + "%", "执行前检查：不通知的写入下在违反条件数据上作答的使用", THEME.colors.accent2);
stat(s, 10.7, 3.6, 2.2, "0 / " + n("SnSnapAnswered"), "绑定快照：四组随机并发合计的违规次数", THEME.colors.accent3);
s.addText("读者中位延迟相同（" + n("SnStressPFiftyLo") + "–" + n("SnStressPFiftyHi") + " ms）；写者单行语句 " + n("SnWriteSeq") + "×，32 个并发写者分片后 " + n("SnWriteConcTT") + "×（不分片 " + n("SnWriteHotTT") + "×）", { x: 8.2, y: 5.6, w: 4.7, h: 0.9, fontSize: 11.5, color: C.text2, margin: 0, isTextBox: true, objectName: "cost note" });

// ── 9 修复 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "方法" });
s.addText("失败了怎么办：有界修复——唯一、不丢键、过回归，否则撤下", { placeholder: "title" });
bullets(s, [
  "算法 1：粒度失效时，枚举低基数列上的等值过滤 ψ = φ ∧ (a = v)；保留能恢复每键一行且不丢键的候选 P",
  "|P| ≠ 1 ⇒ 撤下：主表与备份副本各自每键一行，结构上分不出谁是业务真相；没有唯一性规则，搜索到的第一个过滤就会被发布",
  "唯一候选再过 G3–G5 与 G8：按学习题编译，与参照在当前数据上比较；回归只在变化触及学习期、且参照反映区分列时才提供证据",
  "修复期间到达的请求加入进行中的维护而不是被拒绝：同时到达下不可用从 " + n("WrCondOff") + " 降为 0，等待时间与数据库工作量不变",
], 0.6, 1.4, 7.6, 4.6, 14);
card(s, 8.5, 1.4, 4.2, 2.3, "参照决定修复能否成功", "同一批 " + n("RpPairN") + " 道配对题：判题参照答对 " + n("RpPairJudge") + "，智能体自己提炼的学习查询作参照答对 " + n("RpPairEx") + "（−" + n("RpRefDiff") + " 个百分点）；差别全部变为不可用，没有一题变错。", THEME.colors.accent2);
card(s, 8.5, 3.9, 4.2, 2.3, "反例：备份副本", "没有唯一性规则且参照预见来源列时，发布错误修复，4 道新题答错 2 道；有规则时两种参照下都撤下定义。规则不改变 3,000 道配对题的任何结果。", THEME.colors.accent4);

// ── 10 系统 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "方法" });
s.addText("系统：智能体与 PostgreSQL 之间的中间层", { placeholder: "title" });
["学习路径", "使用路径", "执行路径"].forEach((t, i) => {
  const desc = [
    "显式业务题 + 独立判题 ⇒ 离线提炼结构化候选 ⇒ G1–G7 准入（含规范 SQL 重放）",
    "find_metric：依赖版本变了先做条件维护（复用结论、撤销、修复），再返回当前有效修订与注意事项",
    "run_sql 声明使用的键与修订：拒绝不存在/已撤销/被替代的修订，审查 SQL，绑定快照模式下同快照核对并执行",
  ][i];
  card(s, 0.6 + i * 4.1, 1.4, 3.9, 2.6, t, desc, [THEME.colors.accent3, THEME.colors.accent1, THEME.colors.accent2][i]);
});
tbl(s, [
  ["组件", "内容"],
  ["工具端点", "列表、描述、连接路径查找与验证、find_metric、run_sql；答案附计算链"],
  ["存储", "内存中的版本化定义、连接路径、粒度条目、结论与证据"],
  ["版本检测", "默认：结构指纹 + DML 计数 + ETL 批次号；绑定快照模式：语句级触发器维护的事务性版本（16 片）"],
  ["规模", "约 6,600 行 Rust 中间层 + 4,200 行评测工具，40 个单元/集成测试；同样适用于语义层声明的口径"],
], 0.6, 4.3, 12.1, [2.2, 9.9], 12);

// ── 11 实验设计 ──
pres.addSection({ title: "实验" });
s = pres.addSlide({ masterName: "SECTION", sectionTitle: "实验" });
s.addText("实验：两层评估，两个负载", { placeholder: "title" });
s.addText("机制层固定智能体学到的库、只换维护方式；端到端跑完整智能体。合成零售数据 + 真实 TPC-DS SF1。", { placeholder: "body" });

s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "实验" });
s.addText("实验设计", { placeholder: "title" });
tbl(s, [
  ["研究问题", "实验", "规模"],
  ["Q1 纯数据变化下维护后的定义是否仍正确", "配对回放：固定学到的库，只换维护方式", n("RpLibs") + " 个库（" + n("RpDefs") + " 个定义，3 个大模型）× " + n("RpChanges") + " 种变化；另在 TPC-DS SF1 上回放模板导出的 " + n("TrDefs") + " 个定义"],
  ["Q2 并发写入下保证是否成立、代价如何", "确定性交错 + 随机并发，预检查对比绑定快照", "3 种交错 × 10 次；4 种设置 × 20 次（4 个读者）；1–32 个写者"],
  ["Q3 修复何时成功、何时撤下", "两种 G8 参照；备份副本反例；修复期间等待", "同上配对回放；唯一性规则开关"],
  ["Q4 维护代价，哪部分需要类型化条件", "受控基准：定义级 / 版本缓存 / 仅范围 / 条件级", "4–19 个定义，8–32 个智能体，100 万–1600 万行"],
  ["Q5 端到端对智能体的作用", "DeepSeek V4.1 Flash 智能体，11 种变化，9 种方法 × 3 次独立运行", n("ScenValidTasks") + " 道计分题；预先写定的分析方案与比较"],
], 0.6, 1.4, 12.1, [3.6, 4.0, 4.5], 11.5);
s.addText("方法：不共享、轨迹检索（AgentSM 式匹配基线）、轨迹检索 + 自验证提示、无守护、只看结构、表级测试（dbt 式）、写入即撤销、定义级、定义级 + 版本缓存、MAVRA、MAVRA（智能体参照）", { x: 0.6, y: 5.9, w: 12.1, h: 0.8, fontSize: 12, color: C.text2, margin: 0, isTextBox: true, objectName: "methods note" });

// ── 13 配对回放 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "实验" });
s.addText("Q1 配对回放：维护后的定义在已建模变化下零错误答案", { placeholder: "title" });
tbl(s, [
  ["方法", "答对", "提供但答错", "不可用（必要）", "不可用（不必要）", "维护 DB 秒"],
  ["只看结构", n("RpSchemaCorrect"), n("RpSchemaWrong"), n("RpSchemaNeeded"), n("RpSchemaUnneeded"), n("RpSchemaDB")],
  ["表级测试（dbt 式）", n("RpTableCorrect"), n("RpTableWrong"), n("RpTableNeeded"), n("RpTableUnneeded"), n("RpTableDB")],
  ["写入即撤销（不重学）", n("RpRevokeCorrect"), n("RpRevokeWrong"), n("RpRevokeNeeded"), n("RpRevokeUnneeded"), n("RpRevokeDB")],
  ["定义级", n("RpDefCorrect"), n("RpDefWrong"), n("RpDefNeeded"), n("RpDefUnneeded"), n("RpDefDB")],
  ["定义级 + 版本缓存", n("RpCacheCorrect"), n("RpCacheWrong"), n("RpCacheNeeded"), n("RpCacheUnneeded"), n("RpCacheDB")],
  ["MAVRA", n("RpCondCorrect"), n("RpCondWrong"), n("RpCondNeeded"), n("RpCondUnneeded"), n("RpCondDB")],
  ["MAVRA，智能体参照", n("RpExCorrect"), n("RpExWrong"), n("RpExNeeded"), n("RpExUnneeded"), n("RpExDB")],
], 0.6, 1.4, 8.0, [2.4, 1.0, 1.3, 1.3, 1.3, 0.7], 11.5);
bullets(s, [
  "各重验证方法的错误答案（" + n("RpCondWrong") + "）全部来自单位变化——没有任何条件刻画取值；已建模变化下为 0，只看结构为 " + n("RpSchemaWrongModeled"),
  "条件级、定义级、版本缓存逐题结果 " + n("RpSameCondDef") + "% 相同：端到端的差别来自各次运行学到的库",
  "表级测试同样零错误，但只能隔离：少答对的 " + n("RpTableOnlyCond") + " 题正是 MAVRA 在状态流水、版本化更正、维表拉链下修复的题",
  "不必要的不可用来自退货率在重复装载等变化下分子分母同步膨胀——粒度确实被破坏，撤销是保守而非错误",
], 8.9, 1.4, 3.9, 5.2, 12);

// ── 14 TPC-DS ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "实验" });
s.addText("Q1 在真实 TPC-DS 数据上重复：模板导出的定义库", { placeholder: "title" });
bullets(s, [
  "数据：dsdgen SF1，290 万行门店销售，24 张表；事实表主键改为普通索引、decimal 放宽（只改表示）",
  "定义库不是为本文编写的：从 99 个官方模板中提取、结构化实现能表达的 " + n("TrDefs") + " 个定义（" + n("TrJoinDefs") + " 个带维表关联、" + n("TrFilterDefs") + " 个带持久过滤）；" + n("TrSeeded") + " 个通过准入，" + n("TrSeedFailed") + " 个学习期为空",
  "11 种变化按相同类别施加在真实表上：整行复制、日期经 date_dim 换算；标准答案 = 定义本身 + 区分列过滤（与合成基准的判题参照相同）",
  "结果类别与合成数据一致：状态流水、版本化更正、维表拉链全部修复；重复装载、日期键改写、备份副本撤下定义；单位变化照旧答错",
], 0.6, 1.4, 6.8, 4.0, 13);
stat(s, 7.8, 1.5, 2.4, n("TrCondWrongModeled"), "MAVRA 在已建模变化下的错误答案（每种方法 " + n("TrCondN") + " 道题）", THEME.colors.accent3);
stat(s, 10.4, 1.5, 2.4, n("TrSchemaWrongModeled"), "只看结构的错误答案", THEME.colors.accent2);
stat(s, 7.8, 3.5, 2.4, n("TrCondRepairedTasks"), "经修复后答对的题次（状态过滤、当前版本过滤、关联路径修订）", THEME.colors.accent1);
stat(s, 10.4, 3.5, 2.4, n("TrTableNeeded") + "+" + n("TrTableUnneeded"), "表级测试隔离的题次（必要 + 不必要）", THEME.colors.accent4);
s.addText("智能体侧参照：" + n("TrPairN") + " 道配对题答对 " + n("TrPairEx") + "（判题参照 " + n("TrPairJudge") + "），变错 " + n("TrPairExWrong") + " 道——拒绝的仍是触及学习期的修复。维护时间以重复装载下的修复搜索为主（" + n("TrCondDuploadDB") + " / " + n("TrCondDB") + " 秒）：300 万行上逐个检查候选过滤后撤下定义。", { x: 0.6, y: 5.6, w: 12.1, h: 0.9, fontSize: 12.5, italic: true, color: THEME.colors.accent1, margin: 0, isTextBox: true, objectName: "tpcds takeaway" });

// ── 15 代价 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "实验" });
s.addText("Q4 维护代价：节省来自共享条件，通用版本缓存同样拿到", { placeholder: "title" });
s.addChart(pres.ChartType.bar, [
  { name: "相对定义级的 DB 时间（%）", labels: ["仅范围", "定义级 + 版本缓存", "MAVRA（条件级）"], values: [88, Number(n("CbStagCacheSix")), Number(n("CbStagCondSix"))] },
], { x: 0.6, y: 1.4, w: 6.2, h: 4.6, barDir: "col", chartColors: [THEME.colors.accent5, THEME.colors.accent6, THEME.colors.accent1], showValue: true, dataLabelPosition: "outEnd", dataLabelFontFace: "+mn-lt", dataLabelFontSize: 11, showLegend: false, showTitle: true, title: "19 个共享定义、错峰到达：相对定义级重验证的维护 DB 时间（%）", titleFontSize: 12, titleFontFace: "+mn-lt", catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLabelColor: THEME.colors.dk2, valAxisLabelColor: THEME.colors.dk2, valGridLine: { color: "DDDCD8", size: 0.5 }, catGridLine: { style: "none" }, valAxisMaxVal: 100 });
bullets(s, [
  "定义级时间随定义数增长（" + n("CbStagDefOne") + " → " + n("CbStagDefSix") + " s），MAVRA 与版本缓存几乎不随定义数增长",
  "零共享对照：所有方法为定义级的 " + n("CbZeroMin") + "–" + n("CbZeroMax") + "%——节省只来自共享，跟踪条件没有可见开销",
  "比例在 400 万行、32 个智能体、1600 万行上保持（" + n("EoneRatioSixteen") + "–" + n("EoneRatioFour") + "%）",
  "端到端：维护时间以修复搜索为主，两者都要做（" + n("ScenMaintRatio") + "%）；共享把留出题轮数从 " + n("ScenHoldTurnsNoShareModelA") + " 降到 " + n("ScenHoldTurnsCondModelA") + "，输入 token 省 " + n("ScenHoldTokSaveModelA") + "%",
  "因此效率不是本文的贡献：它是显式、版本化条件的性质；贡献在检查什么、何时可依赖、失败怎么办",
], 7.1, 1.4, 5.7, 5.0, 12.5);

// ── 16 端到端 ──
const methods = [["不共享", "DsNoShare", THEME.colors.accent3], ["轨迹检索", "DsTraj", THEME.colors.accent5], ["轨迹+自验证", "DsTrajVerify", "C39BD3"], ["无守护", "DsNoguard", "E87BA4"], ["只看结构", "DsSchema", THEME.colors.accent4], ["写入撤销", "DsRevoke", "1BAF7A"], ["定义级", "DsDef", THEME.colors.accent2], ["MAVRA", "DsCond", THEME.colors.accent1], ["MAVRA·智能体参照", "DsCondExref", "7FB2EA"]].filter((m) => m[1] + "All" in M);
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "实验" });
s.addText("Q5 端到端：共享带来大部分提升，维护在破坏性变化下拉开差距", { placeholder: "title" });
s.addChart(pres.ChartType.bar, [
  { name: "全部情形", labels: methods.map((m) => m[0]), values: methods.map((m) => Number(n(m[1] + "All"))) },
  { name: "已建模的破坏性变化", labels: methods.map((m) => m[0]), values: methods.map((m) => Number(n(m[1] + "Modeled"))) },
], { x: 0.6, y: 1.3, w: 8.0, h: 5.4, barDir: "col", barGrouping: "clustered", chartColors: [THEME.colors.accent1, THEME.colors.accent2], showValue: true, dataLabelPosition: "outEnd", dataLabelFontFace: "+mn-lt", dataLabelFontSize: 10, showLegend: true, legendPos: "t", legendFontFace: "+mn-lt", legendFontSize: 11, showTitle: true, title: "智能体 B 的正确率（%），DeepSeek V4.1 Flash，每种方法 3 次独立运行", titleFontSize: 12, titleFontFace: "+mn-lt", catAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 10, valAxisLabelFontFace: "+mn-lt", catAxisLabelColor: THEME.colors.dk2, valAxisLabelColor: THEME.colors.dk2, valGridLine: { color: "DDDCD8", size: 0.5 }, catGridLine: { style: "none" }, valAxisMaxVal: 100 });
bullets(s, [
  "留出题上 MAVRA 与轨迹检索都是 100%：数据不变时检索成功轨迹与共享定义一样有效",
  "已建模破坏下 MAVRA " + n("DsCondModeled") + "% 对轨迹检索 " + n("DsTrajModeled") + "%（+" + n("DsCmpModeledTraj") + "，区间 " + n("DsCmpModeledTrajLo") + "–" + n("DsCmpModeledTrajHi") + "）：检索到的 SQL 不带有效性状态，状态流水下照旧重复计数",
  "自验证提示：" + ("DsTrajVerifyModeled" in M ? "已建模破坏下 " + n("DsTrajVerifyModeled") + "%（MAVRA − 自验证 " + n("DsCmpModeledCondVerify") + "）" : "运行中"),
  "智能体参照下的 MAVRA：" + ("DsCondExrefModeled" in M ? "已建模破坏下 " + n("DsCondExrefModeled") + "%（相对轨迹检索 " + n("DsCmpModeledExrefTraj") + "）" : "运行中"),
  "如实报告：备份副本下轨迹检索 " + n("DsTrajMirror") + "% 高于 MAVRA " + n("DsCondMirror") + "%——撤下定义安全但放弃了对部分题仍正确的知识",
], 8.9, 1.4, 3.9, 5.3, 11.5);

// ── 17 边界 ──
pres.addSection({ title: "边界" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "边界" });
s.addText("边界与下一步", { placeholder: "title" });
card(s, 0.6, 1.4, 3.9, 2.4, "保证的范围", "覆盖声明了修订的使用；轨迹里 " + n("DuUndeclPct") + "% 的答案什么也没声明。条件不覆盖取值含义：单位变化不会被发现（命题 1 的 B2）。", THEME.colors.accent2);
card(s, 4.7, 1.4, 3.9, 2.4, "修复的语义", "修复恢复结构而非含义：唯一性规则挡住等价总体，回归只在参照区分时有效；有歧义的修复应带候选交人确认。去重与重映射键的算子可扩展到重复装载与日期键改写。", THEME.colors.accent4);
card(s, 8.8, 1.4, 3.9, 2.4, "泛化", "两个负载（合成、TPC-DS SF1 + 模板定义）上的变化都由我们注入；端到端一个大模型 × 3 次运行；场景未触发绑定快照执行。下一步：真实更新历史、更多模型。", THEME.colors.accent1);
bullets(s, [
  "投稿：SIGMOD 2027 Research，Round 4（摘要 10-10，正文 10-17）；英文稿正文 12 页，双语稿同源",
  "全部数值由脚本从原始运行生成（tools/paper-results.py、scen-stats.py、review-results.py），证据归档在 exp/",
], 0.6, 4.3, 12.1, 1.6, 13.5);

// ── 本轮改进 ──
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "边界" });
s.addText("本轮（10-02 → 10-03）针对评审意见做了什么", { placeholder: "title" });
card(s, 0.6, 1.4, 3.9, 2.5, "论证深度", "命题 1：四类条件充分并划定检测边界；引理 1：结论复用规则在事务性版本下可靠；算法 1：有界修复的三道关。引言与摘要改为正面陈述，共享与维护的增益分开报告。", THEME.colors.accent1);
card(s, 4.7, 1.4, 3.9, 2.5, "新基线", "dbt 式表级测试：零错误但只能隔离（少答对 342 题）。轨迹检索 + 自验证提示：告诉智能体检查什么，差距缩小 5 个百分点但仍差 11。", THEME.colors.accent4);
card(s, 8.8, 1.4, 3.9, 2.5, "外部效度与归因", "真实 TPC-DS SF1 + 99 个官方模板导出的 " + n("TrDefs") + " 个定义上重复配对回放；端到端用智能体自己的学习查询作修复参照，正确率不变（74% 对 73%），发布的修复减少。", THEME.colors.accent3);
bullets(s, [
  "相关工作补充 dbt / Great Expectations / 数据契约 / MetricFlow，说明与按表声明测试的区别：按定义推条件、结论约束定义、在读取的快照上生效",
  "全部增补运行的分析方案在启动前写定（exp/2026-10-02-scenarios-ds/README.md），结果如实报告：备份副本下轨迹检索仍优于 MAVRA",
  "页数：英文稿正文 12 页；为此删去共享示意图、实验概览表、分组柱状图与场景代价表，热力表保留全部 12 种情形 × 9 种方法",
], 0.6, 4.2, 12.1, 2.4, 13.5);

// ── 18 总结 ──
s = pres.addSlide({ masterName: "TITLE", sectionTitle: "边界" });
s.addText("总结：把共享口径的有效性当作一等的、版本化的状态", { placeholder: "title" });
s.addText("① 四类可执行条件，证明其充分并划定检测边界　② 结论按条件与版本索引，绑定快照执行并证明复用规则可靠　③ 唯一、不丢键、过回归的有界修复，否则撤下　④ 两个负载的配对回放、并发写入、代价、端到端：维护后的定义在已建模变化下零错误答案", { placeholder: "body" });

(async () => {
  const out = path.join(__dirname, "mavra-report.pptx");
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("wrote", out, "macros:", Object.keys(M).length);
})();
