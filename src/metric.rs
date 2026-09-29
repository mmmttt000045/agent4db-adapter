//! 指标经验的纯逻辑：题型、规范 SQL 编译、计算链求值、静态检查与离线提炼。
//! 需要数据库的门槛、守护、受限修复与回归在 `middle::metrics`。协议见 docs/metric-experience-protocol.md。

use crate::catalog::Catalog;
use crate::knowledge::{Basis, EmptyRule, JoinKind, Metric, TimeSpec};
use crate::llm::{Provider, Turn};
use crate::sqlscan;
use crate::workload::Period;
use anyhow::{anyhow, bail, ensure, Result};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;
use std::time::Instant;

/// 题型：单期汇总、跨期差值（前者减后者）、全年中取值最高的月份。
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Ask {
    Single { period: Period },
    Diff { a: Period, b: Period },
    RankMonth { year: i32 },
}

impl Ask {
    /// 题目参数里的年份，用于发现被写进口径过滤的参数。
    pub fn years(&self) -> Vec<i32> {
        match self {
            Ask::Single { period } => vec![period.year],
            Ask::Diff { a, b } => vec![a.year, b.year],
            Ask::RankMonth { year } => vec![*year],
        }
    }
}

/// 一条来源轨迹。`judged` 只来自独立判题：Agent 声明完成、SQL 执行成功都不算。
#[derive(Clone, Debug, Serialize)]
pub struct Trajectory {
    pub task: String,
    pub question: String,
    pub ask: Ask,
    pub basis: Basis,
    pub judged: bool,
    pub decimals: u32,
    pub answer: String,
    pub used: Vec<String>,
    pub derivation: Option<String>,
    /// 学习题的判题查询，只用于修复后的 G8 回归；实际部署对应业务方确认
    pub judge: Option<String>,
}

// ───────────────────────── 答案与比较 ─────────────────────────

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(untagged)]
pub enum Answer {
    Num(f64),
    Text(String),
}

pub fn parse_answer(s: &str) -> Answer {
    let t = s.trim().replace('−', "-");
    if let Ok(x) = t.parse::<f64>() {
        if x.is_finite() {
            return Answer::Num(x);
        }
    }
    let cleaned: String = t.chars().filter(|c| c.is_ascii_digit() || *c == '.' || *c == '-').collect();
    match cleaned.parse::<f64>() {
        Ok(x) if x.is_finite() => Answer::Num(x),
        _ => Answer::Text(t.trim().to_string()),
    }
}

/// 在答案精度上相等：数值差不超过末位的一半（另加浮点余量），文本忽略大小写与首尾空白。
pub fn same_value(a: &Answer, b: &Answer, decimals: u32) -> bool {
    match (a, b) {
        (Answer::Num(x), Answer::Num(y)) => (x - y).abs() <= 0.5 * 10f64.powi(-(decimals as i32)) + 1e-9 * x.abs().max(y.abs()) + 1e-12,
        (Answer::Text(x), Answer::Text(y)) => x.trim().eq_ignore_ascii_case(y.trim()),
        _ => false,
    }
}

// ───────────────────────── 计算链 ─────────────────────────

pub fn ref_index(r: &str) -> Option<usize> {
    r.trim().trim_start_matches(['r', 'R']).parse().ok()
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Tok {
    Num(f64),
    Ref(usize),
    Op(char),
}

fn tokenize(s: &str) -> Result<Vec<Tok>> {
    let cs: Vec<char> = s.chars().collect();
    let mut out = vec![];
    let mut i = 0;
    while i < cs.len() {
        let c = cs[i];
        if c.is_whitespace() {
            i += 1;
        } else if c.is_ascii_digit() || c == '.' {
            let start = i;
            while i < cs.len() && (cs[i].is_ascii_digit() || cs[i] == '.') {
                i += 1;
            }
            let t: String = cs[start..i].iter().collect();
            out.push(Tok::Num(t.parse().map_err(|_| anyhow!("无法解析数字 {t}"))?));
        } else if c == 'r' || c == 'R' {
            let start = i + 1;
            i += 1;
            while i < cs.len() && cs[i].is_ascii_digit() {
                i += 1;
            }
            let t: String = cs[start..i].iter().collect();
            out.push(Tok::Ref(t.parse().map_err(|_| anyhow!("查询编号应形如 r2"))?));
        } else {
            let op = match c {
                '×' => '*',
                '÷' => '/',
                '−' => '-',
                '+' | '-' | '*' | '/' | '(' | ')' => c,
                _ => bail!("算式只允许 r1..rn、数字、加减乘除和括号，遇到 {c}"),
            };
            out.push(Tok::Op(op));
            i += 1;
        }
    }
    Ok(out)
}

struct Calc<'a> {
    toks: Vec<Tok>,
    pos: usize,
    cell: &'a dyn Fn(usize) -> Option<String>,
}

impl Calc<'_> {
    fn peek(&self) -> Option<Tok> {
        self.toks.get(self.pos).copied()
    }
    fn expr(&mut self) -> Result<f64> {
        let mut v = self.term()?;
        while let Some(Tok::Op(o @ ('+' | '-'))) = self.peek() {
            self.pos += 1;
            let r = self.term()?;
            v = if o == '+' { v + r } else { v - r };
        }
        Ok(v)
    }
    fn term(&mut self) -> Result<f64> {
        let mut v = self.factor()?;
        while let Some(Tok::Op(o @ ('*' | '/'))) = self.peek() {
            self.pos += 1;
            let r = self.factor()?;
            v = if o == '*' { v * r } else { v / r };
        }
        Ok(v)
    }
    fn factor(&mut self) -> Result<f64> {
        let t = self.peek().ok_or_else(|| anyhow!("算式不完整"))?;
        self.pos += 1;
        match t {
            Tok::Op('-') => Ok(-self.factor()?),
            Tok::Op('(') => {
                let v = self.expr()?;
                ensure!(self.peek() == Some(Tok::Op(')')), "括号不匹配");
                self.pos += 1;
                Ok(v)
            }
            Tok::Num(x) => Ok(x),
            Tok::Ref(n) => {
                let c = (self.cell)(n).ok_or_else(|| anyhow!("r{n} 没有结果或首个单元格为空"))?;
                c.trim().parse().map_err(|_| anyhow!("r{n} 的首个单元格不是数值：{c}"))
            }
            Tok::Op(o) => bail!("算式在 {o} 处不合法"),
        }
    }
}

/// Agent 常在算式后附说明（如 `r1（按销售日）`、`r1 - r2 (r2 为去年)`），只取开头的算式：
/// 截到第一个算式外的字符，去掉尾部残留的运算符与未闭合的左括号。
pub fn leading_expr(s: &str) -> &str {
    let ok = |c: char| c.is_whitespace() || c.is_ascii_digit() || "rR.+-*/()×÷−".contains(c);
    let mut e = &s[..s.find(|c: char| !ok(c)).unwrap_or(s.len())];
    loop {
        e = e.trim_end_matches(|c: char| c.is_whitespace() || "rR.+-*/×÷−(".contains(c));
        if e.matches('(').count() <= e.matches(')').count() {
            return e;
        }
        e = &e[..e.rfind('(').unwrap_or(0)];
    }
}

/// 算式里引用的查询编号（算式后的说明文字忽略）。
pub fn refs_in(expr: &str) -> Result<BTreeSet<usize>> {
    Ok(tokenize(leading_expr(expr))?.into_iter().filter_map(|t| if let Tok::Ref(n) = t { Some(n) } else { None }).collect())
}

/// 按算式重算答案。`cell(n)` 是第 n 条查询结果的首个单元格。只有一个编号时保留文本（如类别名）。
pub fn eval_derivation(expr: &str, cell: &dyn Fn(usize) -> Option<String>) -> Result<Answer> {
    let toks = tokenize(expr)?;
    if let [Tok::Ref(n)] = toks.as_slice() {
        let c = cell(*n).ok_or_else(|| anyhow!("r{n} 没有结果或首个单元格为空"))?;
        return Ok(parse_answer(&c));
    }
    let mut calc = Calc { toks, pos: 0, cell };
    let v = calc.expr()?;
    ensure!(calc.pos == calc.toks.len(), "算式有多余内容");
    ensure!(v.is_finite(), "算式结果不是有限数值");
    Ok(Answer::Num(v))
}

fn first_cell(result: &Value) -> Option<String> {
    result["rows"][0][0].as_str().map(str::to_string)
}

/// 验证计算链：按 derivation 重算，结果须与提交的答案一致。`results` 为本任务 r{n} → 结果集。
pub fn verify_chain(traj: &Trajectory, results: &BTreeMap<usize, Value>) -> std::result::Result<Answer, String> {
    let derivation = match (&traj.derivation, traj.used.as_slice()) {
        (Some(d), _) if !leading_expr(d).is_empty() => leading_expr(d).to_string(),
        (_, [one]) => one.clone(),
        _ => return Err("计算链缺失：没有 derivation，used 也不是恰好一条".into()),
    };
    let used: BTreeSet<usize> = traj.used.iter().filter_map(|r| ref_index(r)).collect();
    let refs = refs_in(&derivation).map_err(|e| e.to_string())?;
    if refs.is_empty() {
        return Err("derivation 没有引用任何查询".into());
    }
    for n in &refs {
        if !results.contains_key(n) {
            return Err(format!("r{n} 不在本任务的查询记录中"));
        }
        if !used.is_empty() && !used.contains(n) {
            return Err(format!("derivation 引用了 used 之外的 r{n}"));
        }
    }
    let cell = |n: usize| results.get(&n).and_then(first_cell);
    let value = eval_derivation(&derivation, &cell).map_err(|e| e.to_string())?;
    if !same_value(&value, &parse_answer(&traj.answer), traj.decimals) {
        return Err(format!("计算链结果 {value:?} 与答案 {} 不一致", traj.answer));
    }
    Ok(value)
}

// ───────────────────────── 规范 SQL ─────────────────────────

fn squash(s: &str) -> String {
    s.to_lowercase().chars().filter(|c| !c.is_whitespace()).collect()
}

fn push_unique(v: &mut Vec<String>, seen: &mut BTreeSet<String>, f: &str) {
    if seen.insert(squash(f)) {
        v.push(format!("({})", f.trim()));
    }
}

fn period_pred(p: &Period) -> String {
    if (p.m1, p.m2) == (1, 12) {
        format!("d_year = {}", p.year)
    } else {
        format!("d_year = {} and d_moy between {} and {}", p.year, p.m1, p.m2)
    }
}

/// 由口径字段编译规范 SQL（G7、G8 与修复后的示例使用）。列名不加表别名（本数据集列名全局唯一）；
/// 期间谓词按 date_dim 的 d_year / d_moy 约定生成。左关联的过滤放在 ON 中，避免把左关联变成内关联。
pub fn compile(m: &Metric, ask: &Ask) -> Result<String> {
    let time = m.time.as_ref().ok_or_else(|| anyhow!("口径没有时间定义，无法按期间编译"))?;
    ensure!(time.dim == "date_dim", "规范编译只支持 date_dim 日历（d_year、d_moy）");
    let mut from = m.fact.clone();
    let mut wheres = vec![];
    let mut seen = BTreeSet::new();
    for j in &m.joins {
        let other = if j.left == m.fact {
            &j.right
        } else if j.right == m.fact {
            &j.left
        } else {
            bail!("关联 {}⋈{} 不经过事实表 {}", j.left, j.right, m.fact);
        };
        let mut conds: Vec<String> = j.on.iter().map(|(l, r)| format!("{l} = {r}")).collect();
        let mut seen_on = BTreeSet::new();
        for f in j.filters.get(other).into_iter().chain(m.filters.get(other)) {
            match j.kind {
                JoinKind::Left => push_unique(&mut conds, &mut seen_on, f),
                JoinKind::Inner => push_unique(&mut wheres, &mut seen, f),
            }
        }
        if let Some(f) = j.filters.get(&m.fact) {
            push_unique(&mut wheres, &mut seen, f);
        }
        let kw = if j.kind == JoinKind::Left { "left join" } else { "join" };
        from.push_str(&format!(" {kw} {other} on {}", conds.join(" and ")));
    }
    if let Some(f) = m.filters.get(&m.fact) {
        push_unique(&mut wheres, &mut seen, f);
    }
    from.push_str(&format!(" join {} on {} = {}", time.dim, time.fact_col, time.dim_col));
    let cond = |extra: String| {
        let mut w = wheres.clone();
        w.push(extra);
        w.join(" and ")
    };
    let expr = if m.empty == EmptyRule::Zero { format!("coalesce({}, 0)", m.measure) } else { m.measure.clone() };
    let value = |p: &Period| format!("select {expr} as value from {from} where {}", cond(period_pred(p)));
    Ok(match ask {
        Ask::Single { period } => value(period),
        Ask::Diff { a, b } => format!("select ({}) - ({}) as value", value(a), value(b)),
        Ask::RankMonth { year } => format!(
            "select d_moy as value from {from} where {} group by d_moy order by {} desc nulls last, d_moy limit 1",
            cond(format!("d_year = {year}")),
            m.measure
        ),
    })
}

// ───────────────────────── 静态检查（G3 的纯逻辑部分） ─────────────────────────

const SQL_WORDS: &[&str] = &[
    "sum",
    "count",
    "avg",
    "min",
    "max",
    "distinct",
    "coalesce",
    "nullif",
    "case",
    "when",
    "then",
    "else",
    "end",
    "and",
    "or",
    "not",
    "null",
    "is",
    "in",
    "between",
    "like",
    "as",
    "round",
    "abs",
    "filter",
    "where",
    "true",
    "false",
    "cast",
    "numeric",
    "decimal",
    "int",
    "integer",
    "bigint",
    "float",
    "double",
    "precision",
    "real",
    "text",
    "varchar",
];

/// 表达式只能引用 `allowed` 中表的列与少量函数、关键字；不允许子查询与多语句。
pub fn check_expr(expr: &str, allowed: &BTreeSet<String>, cat: &Catalog) -> std::result::Result<(), String> {
    if expr.contains(';') || expr.contains("/*") || expr.contains("--") {
        return Err("表达式不能包含分号或注释".into());
    }
    for w in sqlscan::words(expr) {
        if w == "select" || w == "from" {
            return Err("表达式不能包含子查询".into());
        }
        if SQL_WORDS.contains(&w.as_str()) {
            continue;
        }
        match cat.table_of(&w) {
            Some(t) if allowed.contains(t) => {}
            Some(t) => return Err(format!("{w} 属于表 {t}，不在口径涉及的表中")),
            None => return Err(format!("{w} 不是已知列或允许的函数")),
        }
    }
    Ok(())
}

fn year_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\b(\d{4})\b").unwrap())
}

fn date_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\d{4}-\d{1,2}").unwrap())
}

/// 口径过滤只放口径必需条件：不在时间维度表上、不引用时间键、不含题目年份或日期字面量。
pub fn check_filter(table: &str, filter: &str, time: Option<&TimeSpec>, ask: &Ask, cat: &Catalog) -> std::result::Result<(), String> {
    if let Some(t) = time {
        if t.dim == table {
            return Err(format!("时间维度表 {table} 上的过滤属于查询参数"));
        }
        if sqlscan::words(filter).contains(&t.fact_col) {
            return Err(format!("过滤引用了时间键 {}，属于查询参数", t.fact_col));
        }
    }
    check_expr(filter, &[table.to_string()].into_iter().collect(), cat)?;
    if date_re().is_match(filter) {
        return Err("过滤包含日期字面量，属于查询参数".into());
    }
    for cap in year_re().captures_iter(filter) {
        if ask.years().iter().any(|y| cap[1] == y.to_string()) {
            return Err(format!("过滤包含题目参数 {}", &cap[1]));
        }
    }
    Ok(())
}

/// 口径结构是否相同（不看名称、示例、说明文字与关联元数据）。
pub fn same_structure(a: &Metric, b: &Metric) -> bool {
    let joins = |m: &Metric| -> BTreeSet<String> {
        m.joins
            .iter()
            .map(|j| {
                let mut on: Vec<String> = j.on.iter().map(|(l, r)| format!("{l}={r}")).collect();
                on.sort();
                let f: Vec<String> = j.filters.iter().map(|(t, f)| format!("{t}:{}", squash(f))).collect();
                format!("{}>{}:{}:{:?}:{}", j.left, j.right, on.join(","), j.kind, f.join(","))
            })
            .collect()
    };
    let filters = |m: &Metric| -> Vec<String> { m.filters.iter().map(|(t, f)| format!("{t}:{}", squash(f))).collect() };
    let time = |m: &Metric| m.time.as_ref().map(|t| (t.fact_col.clone(), t.dim.clone(), t.dim_col.clone()));
    let grain = |m: &Metric| m.grain.iter().cloned().collect::<BTreeSet<_>>();
    a.fact == b.fact
        && squash(&a.measure) == squash(&b.measure)
        && grain(a) == grain(b)
        && time(a) == time(b)
        && joins(a) == joins(b)
        && filters(a) == filters(b)
        && a.empty == b.empty
}

// ───────────────────────── 离线提炼 ─────────────────────────

const EXTRACT_SYSTEM: &str = "你是数据中间层的指标口径提炼器。输入是一次已被独立判定为成功的分析任务：题面、参与最终答案的 SQL 计算链、\
被中间层拦下的写法，以及相关表的元数据、已验证关联和粒度过滤。请总结题目所用业务指标的计算口径；题面给出了定义时以题面为准。\
只输出一个 JSON 对象，不要输出其他文字。字段：\n\
- name：指标名称，取题面中的业务名称\n\
- aliases：其他常见叫法，可以为空数组\n\
- definition：用一两句话说明口径\n\
- fact：事实表\n\
- measure：一个聚合表达式，如 sum(ss_net_paid)；只能引用 fact 与 joins 中表的列，不得包含子查询\n\
- grain：fact 上“一行对应一条业务记录”的键列数组\n\
- time：{\"role\": 时间角色（如“销售日”）, \"fact_col\": 事实表上的日期键列, \"dim\": 日期维度表, \"dim_col\": 维度表键列, \"grain\": \"day\" / \"month\" / \"year\"}；与时间无关时为 null\n\
- joins：计算口径必需的关联（不含时间维度），每项 {\"left\": 多侧表, \"right\": 一侧表, \"on\": [[左表列, 右表列]], \"kind\": \"inner\" 或 \"left\", \"filters\": {表: 条件}}；必须与已验证关联的方向一致\n\
- filters：{表: 条件}，只写口径必需的条件（例如每条记录只计一次所需的状态过滤）；不得包含年份、月份、日期范围、排名个数等题目参数\n\
- empty：题面说明无数据按 0 计写 \"zero\"，说明为空写 \"null\"，未说明写 \"unspecified\"\n\
- caveats：注意事项数组，如被拦下的写法及原因、关联丢行比例\n\
- example_sql：一条可以独立得到本题最终答案的 PostgreSQL 查询，结果应与计算链一致";

#[derive(Debug)]
pub struct Draft {
    pub metric: Metric,
    pub example_sql: String,
}

#[derive(Debug, Default, Serialize)]
pub struct Extraction {
    #[serde(skip)]
    pub draft: Option<Draft>,
    pub attempts: u32,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub seconds: f64,
    pub errors: Vec<String>,
}

#[derive(Deserialize)]
struct RawDraft {
    #[serde(flatten)]
    metric: Metric,
    example_sql: String,
}

/// 解析提炼器输出。关联的键、基数、丢行比例和修订号由中间层按已验证路径填写，这里清空。
pub fn parse_draft(text: &str) -> std::result::Result<Draft, String> {
    let (Some(a), Some(b)) = (text.find('{'), text.rfind('}')) else { return Err("输出中没有 JSON 对象".into()) };
    if b < a {
        return Err("输出中没有 JSON 对象".into());
    }
    let raw: RawDraft = serde_json::from_str(&text[a..=b]).map_err(|e| format!("JSON 不符合格式：{e}"))?;
    let mut m = raw.metric;
    m.basis = Basis::None;
    m.examples.clear();
    for j in &mut m.joins {
        j.key.clear();
        j.cardinality.clear();
        j.loss_ratio = 0.0;
        j.revision = 0;
    }
    if m.name.trim().is_empty() || m.fact.trim().is_empty() || m.measure.trim().is_empty() {
        return Err("name、fact、measure 不能为空".into());
    }
    Ok(Draft { metric: m, example_sql: raw.example_sql })
}

/// 调用模型提炼一次，格式错误时按固定次数重试；所有尝试的 token 与耗时都计入。
pub async fn extract(p: &Provider, input: &Value, max_attempts: u32) -> Extraction {
    let mut ex = Extraction::default();
    let t0 = Instant::now();
    let mut turns = vec![Turn::User(serde_json::to_string_pretty(input).unwrap_or_default())];
    for _ in 0..max_attempts.max(1) {
        ex.attempts += 1;
        let r = match p.chat(EXTRACT_SYSTEM, &turns, &[]).await {
            Ok(r) => r,
            Err(e) => {
                ex.errors.push(format!("{e:#}"));
                break;
            }
        };
        ex.input_tokens += r.input_tokens;
        ex.output_tokens += r.output_tokens;
        match parse_draft(&r.text) {
            Ok(d) => {
                ex.draft = Some(d);
                break;
            }
            Err(e) => {
                ex.errors.push(e.clone());
                turns.push(Turn::Assistant { raw: r.raw });
                turns.push(Turn::User(format!("上一次输出无法解析：{e}。请只输出一个符合要求的 JSON 对象。")));
            }
        }
    }
    ex.seconds = t0.elapsed().as_secs_f64();
    ex
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalog::{Column, Table};
    use crate::knowledge::JoinRef;

    fn cat() -> Catalog {
        let t = |name: &str, cols: &[&str]| Table {
            name: name.into(),
            comment: None,
            rows_est: 1.0,
            cols: cols.iter().map(|c| Column { name: (*c).into(), dtype: "int".into(), comment: None, n_distinct: None }).collect(),
        };
        Catalog::from_tables(vec![
            t("store_sales", &["ss_sold_date_sk", "ss_ticket_number", "ss_item_sk", "ss_net_paid"]),
            t("store_returns", &["sr_ticket_number", "sr_item_sk", "sr_return_amt", "sr_status"]),
            t("date_dim", &["d_date_sk", "d_year", "d_moy"]),
        ])
    }

    fn rate() -> Metric {
        let mut filters = BTreeMap::new();
        filters.insert("store_returns".to_string(), "sr_status = '完成'".to_string());
        Metric {
            name: "门店退货率".into(),
            aliases: vec![],
            definition: String::new(),
            fact: "store_sales".into(),
            measure: "100.0 * sum(sr_return_amt) / sum(ss_net_paid)".into(),
            grain: vec!["ss_ticket_number".into(), "ss_item_sk".into()],
            time: Some(TimeSpec {
                role: "销售日".into(),
                fact_col: "ss_sold_date_sk".into(),
                dim: "date_dim".into(),
                dim_col: "d_date_sk".into(),
                grain: "day".into(),
            }),
            joins: vec![JoinRef {
                key: String::new(),
                left: "store_sales".into(),
                right: "store_returns".into(),
                on: vec![("ss_ticket_number".into(), "sr_ticket_number".into()), ("ss_item_sk".into(), "sr_item_sk".into())],
                kind: JoinKind::Left,
                filters,
                cardinality: String::new(),
                loss_ratio: 0.0,
                revision: 0,
            }],
            filters: BTreeMap::new(),
            empty: EmptyRule::Unspecified,
            caveats: vec![],
            examples: vec![],
            basis: Basis::None,
        }
    }

    #[test]
    fn derivation_evaluates_chain_arithmetic() {
        let cell = |n: usize| match n {
            1 => Some("100.5".to_string()),
            2 => Some("40".to_string()),
            3 => Some("家居".to_string()),
            _ => None,
        };
        assert_eq!(eval_derivation("r1 - r2", &cell).unwrap(), Answer::Num(60.5));
        assert_eq!(eval_derivation("(r1 − r2) × 2 ÷ 4", &cell).unwrap(), Answer::Num(30.25));
        assert_eq!(eval_derivation("-r2 + 1", &cell).unwrap(), Answer::Num(-39.0));
        assert_eq!(eval_derivation("r3", &cell).unwrap(), Answer::Text("家居".into()));
        assert!(eval_derivation("r3 + 1", &cell).is_err());
        assert!(eval_derivation("r9", &cell).is_err());
        assert!(eval_derivation("r1 / (r2 - 40)", &cell).is_err());
        assert!(eval_derivation("r1; drop", &cell).is_err());
        assert_eq!(refs_in("r1 - r12").unwrap(), [1, 12].into_iter().collect());
    }

    #[test]
    fn chain_must_match_answer_and_used() {
        let mut results = BTreeMap::new();
        results.insert(1, serde_json::json!({"rows": [["10.004"]]}));
        results.insert(2, serde_json::json!({"rows": [["3"]]}));
        let traj = |used: &[&str], derivation: Option<&str>, answer: &str| Trajectory {
            task: "t".into(),
            question: String::new(),
            ask: Ask::RankMonth { year: 2001 },
            basis: Basis::None,
            judged: true,
            decimals: 2,
            answer: answer.into(),
            used: used.iter().map(|s| s.to_string()).collect(),
            derivation: derivation.map(str::to_string),
            judge: None,
        };
        assert!(verify_chain(&traj(&["r1", "r2"], Some("r1 - r2"), "7.00"), &results).is_ok());
        assert!(verify_chain(&traj(&["r1"], None, "10.00"), &results).is_ok());
        assert!(verify_chain(&traj(&["r1", "r2"], None, "7"), &results).is_err());
        assert!(verify_chain(&traj(&["r1"], Some("r1 - r2"), "7"), &results).is_err());
        assert!(verify_chain(&traj(&[], Some("r1 - r2"), "8"), &results).is_err());
        assert!(verify_chain(&traj(&[], Some("r3"), "8"), &results).is_err());
        // 算式后的说明文字忽略
        assert!(verify_chain(&traj(&["r1"], Some("r1（按销售日）"), "10.00"), &results).is_ok());
        assert!(verify_chain(&traj(&[], Some("r1 - r2 (r2 为去年)"), "7.00"), &results).is_ok());
    }

    #[test]
    fn leading_expr_drops_trailing_notes() {
        assert_eq!(leading_expr("r1（按销售日）"), "r1");
        assert_eq!(leading_expr("r1 - r2 (r2 为去年)"), "r1 - r2");
        assert_eq!(leading_expr("(r1 - r2) / r2 × 100%"), "(r1 - r2) / r2 × 100");
        assert_eq!(leading_expr("r1 revenue"), "r1");
        assert_eq!(leading_expr("r2."), "r2");
        assert_eq!(leading_expr("见上"), "");
    }

    #[test]
    fn answers_compare_at_answer_precision() {
        assert!(same_value(&parse_answer("12,345.68 元"), &parse_answer("12345.675"), 2));
        assert!(!same_value(&parse_answer("12345.69"), &parse_answer("12345.675"), 2));
        assert!(same_value(&parse_answer("−3.5"), &Answer::Num(-3.5), 2));
        assert!(same_value(&parse_answer("9 月"), &parse_answer("9"), 0));
        assert!(!same_value(&parse_answer("8"), &parse_answer("9"), 0));
    }

    #[test]
    fn compile_keeps_left_join_filters_in_on_clause() {
        let m = rate();
        let p = |y, mo| Period::month(y, mo);
        let single = compile(&m, &Ask::Single { period: p(2002, 9) }).unwrap();
        assert!(single.contains(
            "left join store_returns on ss_ticket_number = sr_ticket_number and ss_item_sk = sr_item_sk and (sr_status = '完成')"
        ));
        assert!(single.contains("join date_dim on ss_sold_date_sk = d_date_sk where d_year = 2002 and d_moy between 9 and 9"));
        let diff = compile(&m, &Ask::Diff { a: p(2002, 9), b: p(2001, 6) }).unwrap();
        assert!(diff.starts_with("select (select ") && diff.contains(") - (select "));
        let rank = compile(&m, &Ask::RankMonth { year: 2001 }).unwrap();
        assert!(rank.ends_with("group by d_moy order by 100.0 * sum(sr_return_amt) / sum(ss_net_paid) desc nulls last, d_moy limit 1"));
        let mut inner = m.clone();
        inner.joins[0].kind = JoinKind::Inner;
        let s = compile(&inner, &Ask::Single { period: p(2002, 9) }).unwrap();
        assert!(s.contains("where (sr_status = '完成') and d_year = 2002"));
        let mut untimed = m;
        untimed.time = None;
        assert!(compile(&untimed, &Ask::RankMonth { year: 2001 }).is_err());
    }

    #[test]
    fn filters_reject_query_parameters() {
        let c = cat();
        let m = rate();
        let ask = Ask::Single { period: Period::month(2002, 9) };
        let t = m.time.as_ref();
        assert!(check_filter("store_returns", "sr_status = '完成'", t, &ask, &c).is_ok());
        assert!(check_filter("date_dim", "d_year = 2002", t, &ask, &c).is_err());
        assert!(check_filter("store_sales", "ss_sold_date_sk > 5", t, &ask, &c).is_err());
        assert!(check_filter("store_sales", "ss_net_paid > 2002", t, &ask, &c).is_err());
        assert!(check_filter("store_returns", "sr_status = '2002-09'", t, &ask, &c).is_err());
        assert!(check_filter("store_returns", "ss_net_paid > 0", t, &ask, &c).is_err());
        let allowed: BTreeSet<String> = ["store_sales".to_string()].into_iter().collect();
        assert!(check_expr("sum(ss_net_paid)", &allowed, &c).is_ok());
        assert!(check_expr("sum(sr_return_amt)", &allowed, &c).is_err());
        assert!(check_expr("(select 1)", &allowed, &c).is_err());
        assert!(check_expr("sum(unknown_col)", &allowed, &c).is_err());
    }

    #[test]
    fn draft_parsing_resets_join_metadata() {
        let text = r#"好的：{"name":"门店营业额","definition":"净支付额之和","fact":"store_sales","measure":"sum(ss_net_paid)",
            "grain":["ss_ticket_number","ss_item_sk"],"time":{"role":"销售日","fact_col":"ss_sold_date_sk","dim":"date_dim","dim_col":"d_date_sk","grain":"day"},
            "joins":[{"left":"store_sales","right":"store_returns","on":[["ss_ticket_number","sr_ticket_number"]],"kind":"left","revision":7}],
            "empty":"zero","example_sql":"select 1"}"#;
        let d = parse_draft(text).unwrap();
        assert_eq!(d.metric.empty, EmptyRule::Zero);
        assert_eq!(d.metric.joins[0].kind, JoinKind::Left);
        assert_eq!(d.metric.joins[0].revision, 0);
        assert_eq!(d.example_sql, "select 1");
        assert!(parse_draft("没有输出").is_err());
        assert!(parse_draft(r#"{"name":"x"}"#).is_err());
        let mut b = rate();
        b.name = "别名".into();
        b.measure = "100.0*SUM(sr_return_amt)/sum(ss_net_paid)".into();
        assert!(same_structure(&rate(), &b));
        b.filters.insert("store_sales".into(), "ss_net_paid > 0".into());
        assert!(!same_structure(&rate(), &b));
    }
}
