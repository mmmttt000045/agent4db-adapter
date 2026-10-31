//! 指标经验的纯逻辑：题型、规范 SQL 编译、计算链求值、静态检查与离线提炼。
//! 需要数据库的门槛、守护、受限修复与回归在 `middle::metrics`。协议见 docs/history/metric-experience-protocol.md。

use crate::catalog::Catalog;
use crate::knowledge::{Basis, EmptyRule, JoinKind, Metric, TimeSpec, TimeStrategy};
use crate::llm::{Provider, Turn};
use crate::sqlscan;
use anyhow::{anyhow, bail, ensure, Result};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlparser::ast::{Expr, Ident, SetExpr, Statement, VisitMut, VisitorMut};
use sqlparser::dialect::PostgreSqlDialect;
use sqlparser::parser::Parser;
use std::collections::{BTreeMap, BTreeSet};
use std::ops::ControlFlow;
use std::sync::OnceLock;
use std::time::Instant;

/// 销售期间：年份 + 月份区间。
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Period {
    pub year: i32,
    pub m1: u32,
    pub m2: u32,
}

impl Period {
    pub fn month(y: i32, m: u32) -> Period {
        Period { year: y, m1: m, m2: m }
    }
}

/// 题型：单期汇总、跨期差值（前者减后者）、全年中取值最高的月份、比上一个月增加最多的月份、高于各月平均值的月份数。
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Ask {
    Single {
        period: Period,
    },
    Diff {
        a: Period,
        b: Period,
    },
    RankMonth {
        year: i32,
    },
    /// 全年中比上一个月增加最多的月份（2–12）
    PeakRise {
        year: i32,
    },
    /// 全年中取值高于各月平均值的月份个数（0–12）
    AboveMean {
        year: i32,
    },
}

impl Ask {
    /// 题目参数里的年份，用于发现被写进口径过滤的参数。
    pub fn years(&self) -> Vec<i32> {
        match self {
            Ask::Single { period } => vec![period.year],
            Ask::Diff { a, b } => vec![a.year, b.year],
            Ask::RankMonth { year } | Ask::PeakRise { year } | Ask::AboveMean { year } => vec![*year],
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
    let answer = parse_answer(&traj.answer);
    // 只引用一条查询时，答案可以在它第一行的任一列（Agent 常把中间量与结果放在同一行）
    if let Ok([Tok::Ref(n)]) = tokenize(&derivation).as_deref() {
        let row = results.get(n).and_then(|r| r["rows"][0].as_array().cloned()).unwrap_or_default();
        if let Some(v) = row.iter().filter_map(Value::as_str).map(parse_answer).find(|v| same_value(v, &answer, traj.decimals)) {
            return Ok(v);
        }
    }
    let cell = |n: usize| results.get(&n).and_then(first_cell);
    let value = eval_derivation(&derivation, &cell).map_err(|e| e.to_string())?;
    if !same_value(&value, &answer, traj.decimals) {
        return Err(format!("计算链结果 {value:?} 与答案 {} 不一致", traj.answer));
    }
    Ok(value)
}

// ───────────────────────── 规范 SQL ─────────────────────────

fn squash(s: &str) -> String {
    sqlscan::expression_key(s)
}

fn push_unique(v: &mut Vec<String>, seen: &mut BTreeSet<String>, f: &str) {
    if seen.insert(squash(f)) {
        v.push(format!("({})", f.trim()));
    }
}

/// 期间谓词：日期维度方式按维度的年、月列过滤；日期列方式按日期取值的半开区间过滤。
fn period_pred(t: &TimeSpec, fact: &str, p: &Period) -> String {
    if t.is_column() {
        let (tb, c) = t.column_of(fact);
        let (y2, m2) = if p.m2 >= 12 { (p.year + 1, 1) } else { (p.year, p.m2 + 1) };
        format!("{tb}.{c} >= date '{:04}-{:02}-01' and {tb}.{c} < date '{y2:04}-{m2:02}-01'", p.year, p.m1)
    } else if (p.m1, p.m2) == (1, 12) {
        format!("{}.{} = {}", t.dim, t.year_col, p.year)
    } else {
        format!("{d}.{} = {} and {d}.{} between {} and {}", t.year_col, p.year, t.month_col, p.m1, p.m2, d = t.dim)
    }
}

/// 按月比较的题型所用的月份（1–12）。
fn month_expr(t: &TimeSpec, fact: &str) -> String {
    if t.is_column() {
        let (tb, c) = t.column_of(fact);
        format!("extract(month from {tb}.{c})::int")
    } else {
        format!("{}.{}", t.dim, t.month_col)
    }
}

/// 当前编译器以事实表为根：每个非时间连接从事实表或此前已关联的表出发（星型与雪花型），指向被验证为至多一行的右侧。
/// 反向引用只证明左侧键唯一，不能阻止另一侧把事实行放大；同一张表出现两次（角色扮演维度）与自连接也不在当前契约内。
pub fn check_join_orientation(m: &Metric) -> Result<()> {
    let mut reached: BTreeSet<&str> = [m.fact.as_str()].into_iter().collect();
    for j in &m.joins {
        ensure!(
            reached.contains(j.left.as_str()) && !reached.contains(j.right.as_str()),
            "关联 {}⋈{} 必须从事实表 {} 或已关联的表指向至多一行的另一侧；反向、重复出现的表和自连接尚不支持",
            j.left,
            j.right,
            m.fact
        );
        reached.insert(j.right.as_str());
    }
    Ok(())
}

/// 由口径字段编译规范 SQL（G7、G8 与修复后的示例使用）。规范 SQL 不给表起别名：关联条件与期间谓词用表名限定列，
/// 度量按口径原文；各表过滤中的裸列按 filters 的所属表限定。左关联过滤留在 ON 中。
pub fn compile(m: &Metric, ask: &Ask) -> Result<String> {
    check_join_orientation(m)?;
    let time = m.time.as_ref().ok_or_else(|| anyhow!("口径没有时间定义，无法按期间编译"))?;
    ensure!(time.is_column() || !(time.dim.is_empty() || time.dim_col.is_empty()), "日期维度方式需要维度表与键列");
    let mut from = m.fact.clone();
    let mut wheres = vec![];
    let mut seen = BTreeSet::new();
    for j in &m.joins {
        let other = &j.right;
        let mut conds: Vec<String> = j.on.iter().map(|(l, r)| format!("{}.{l} = {other}.{r}", j.left)).collect();
        let mut seen_on = BTreeSet::new();
        for f in j.filters.get(other).into_iter().chain(m.filters.get(other)) {
            let f = qualify_owned_filter(other, f)?;
            match j.kind {
                JoinKind::Left => push_unique(&mut conds, &mut seen_on, &f),
                JoinKind::Inner => push_unique(&mut wheres, &mut seen, &f),
            }
        }
        if let Some(f) = j.filters.get(&j.left) {
            push_unique(&mut wheres, &mut seen, &qualify_owned_filter(&j.left, f)?);
        }
        let kw = if j.kind == JoinKind::Left { "left join" } else { "join" };
        from.push_str(&format!(" {kw} {other} on {}", conds.join(" and ")));
    }
    if let Some(f) = m.filters.get(&m.fact) {
        push_unique(&mut wheres, &mut seen, &qualify_owned_filter(&m.fact, f)?);
    }
    let joined = if time.is_column() {
        from.clone()
    } else {
        format!("{from} join {d} on {}.{} = {d}.{}", m.fact, time.fact_col, time.dim_col, d = time.dim)
    };
    let cond = |extra: String| {
        let mut w = wheres.clone();
        w.push(extra);
        w.join(" and ")
    };
    let pred = |p: &Period| period_pred(time, &m.fact, p);
    let year = |y: i32| pred(&Period { year: y, m1: 1, m2: 12 });
    let expr = if m.empty == EmptyRule::Zero { format!("coalesce({}, 0)", m.measure) } else { m.measure.clone() };
    // 日期键范围：期间的日期键集合是一个整数区间（条件“日期键按月连续”），事实表按键范围过滤，不连接维度表；
    // 按月排名仍需维度列，照旧连接
    let range = time.strategy == TimeStrategy::KeyRange;
    let value = |p: &Period| {
        if range {
            let pp = pred(p);
            let between = format!(
                "{}.{} between (select min({dc}) from {dim} where {pp}) and (select max({dc}) from {dim} where {pp})",
                m.fact,
                time.fact_col,
                dc = time.dim_col,
                dim = time.dim
            );
            format!("select {expr} as value from {from} where {}", cond(between))
        } else {
            format!("select {expr} as value from {joined} where {}", cond(pred(p)))
        }
    };
    // 按月比较的题型需要月份，日期维度方式下两种策略都连接维度
    let mo = month_expr(time, &m.fact);
    let monthly = |y: i32| format!("select {mo} as mo, {expr} as v from {joined} where {} group by 1", cond(year(y)));
    Ok(match ask {
        Ask::Single { period } => value(period),
        Ask::Diff { a, b } => format!("select ({}) - ({}) as value", value(a), value(b)),
        Ask::RankMonth { year: y } => format!(
            "select {mo} as value from {joined} where {} group by 1 order by {} desc nulls last, 1 limit 1",
            cond(year(*y)),
            m.measure
        ),
        Ask::PeakRise { year: y } => format!(
            "select mo as value from (select mo, v - lag(v) over (order by mo) as rise from ({}) m) r \
             where rise is not null order by rise desc nulls last, mo limit 1",
            monthly(*y)
        ),
        Ask::AboveMean { year: y } => {
            let m = monthly(*y);
            format!("select count(*) as value from ({m}) m where v > (select avg(v) from ({m}) a)")
        }
    })
}

// ───────────────────────── 特征定义（RelBench） ─────────────────────────

/// 特征的输出列名：小写字母、数字与下划线，不以数字开头。
pub fn feature_ident(name: &str) -> String {
    let mut s: String = name.trim().to_lowercase().chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '_' }).collect();
    while s.contains("__") {
        s = s.replace("__", "_");
    }
    let s = s.trim_matches('_').to_string();
    if s.is_empty() || s.starts_with(|c: char| c.is_ascii_digit()) {
        format!("f_{s}")
    } else {
        s
    }
}

/// 特征定义编译为对种子表 `s`（列：实体键 `seed_key`、`seed_time`）逐行的 LATERAL 聚合，别名 `alias`，值列为 `v`。
/// 关联与过滤的写法与 `compile` 相同；`时间列 <= s.seed_time` 与窗口下界写在 SQL 里，所以按定义执行不会读到种子时间之后的行；
/// LATERAL 里的聚合对每个种子恰好返回一行。
pub fn feature_lateral(m: &Metric, alias: &str, seed_key: &str) -> Result<String> {
    check_join_orientation(m)?;
    let e = m.entity.as_ref().ok_or_else(|| anyhow!("不是特征定义：没有 entity"))?;
    let time = m.time.as_ref().filter(|t| t.is_column()).ok_or_else(|| anyhow!("特征定义的时间须为日期列方式"))?;
    let (tt, tc) = time.column_of(&m.fact);
    let (vt, vc) = e.via_of(&m.fact);
    let mut from = m.fact.clone();
    let mut wheres = vec![];
    let mut seen = BTreeSet::new();
    for j in &m.joins {
        let other = &j.right;
        let mut conds: Vec<String> = j.on.iter().map(|(l, r)| format!("{}.{l} = {other}.{r}", j.left)).collect();
        let mut seen_on = BTreeSet::new();
        for f in j.filters.get(other).into_iter().chain(m.filters.get(other)) {
            let f = qualify_owned_filter(other, f)?;
            match j.kind {
                JoinKind::Left => push_unique(&mut conds, &mut seen_on, &f),
                JoinKind::Inner => push_unique(&mut wheres, &mut seen, &f),
            }
        }
        if let Some(f) = j.filters.get(&j.left) {
            push_unique(&mut wheres, &mut seen, &qualify_owned_filter(&j.left, f)?);
        }
        let kw = if j.kind == JoinKind::Left { "left join" } else { "join" };
        from.push_str(&format!(" {kw} {other} on {}", conds.join(" and ")));
    }
    if let Some(f) = m.filters.get(&m.fact) {
        push_unique(&mut wheres, &mut seen, &qualify_owned_filter(&m.fact, f)?);
    }
    match &e.anchor {
        // 关联实体：via 等于种子所指实体行上的 anchor 列
        Some(a) => wheres.push(format!("{vt}.{vc} = (select ent.{a} from {} ent where ent.{} = s.{seed_key})", e.table, e.key)),
        None => wheres.push(format!("{vt}.{vc} = s.{seed_key}")),
    }
    wheres.push(format!("{tt}.{tc} <= s.seed_time"));
    if let Some(d) = e.window_days {
        wheres.push(format!("{tt}.{tc} > s.seed_time - interval '{d} days'"));
    }
    // 度量里未限定的 seed_time 是这个种子的时间
    let measure = seed_time_re().replace_all(&m.measure, "${1}s.seed_time").to_string();
    let expr = match e.fill {
        Some(v) if v.is_finite() => format!("coalesce({measure}, {v})"),
        _ if m.empty == EmptyRule::Zero => format!("coalesce({measure}, 0)"),
        _ => measure,
    };
    Ok(format!("left join lateral (select ({expr})::double precision as v from {from} where {}) {alias} on true", wheres.join(" and ")))
}

fn seed_time_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(^|[^.\w])seed_time\b").unwrap())
}

/// 一组特征定义编译成交给 validate_features 的特征 SQL：以 `{seeds}` 为种子表，前两列为实体键与 seed_time，
/// 其后每个定义一列（列名为 `feature_ident(名称)`）。返回 SQL 与各定义的列名。
pub fn compose_features(defs: &[&Metric], seed_key: &str) -> Result<(String, Vec<String>)> {
    let mut sel = vec![format!("s.{seed_key}"), "s.seed_time".to_string()];
    let mut joins = vec![];
    let mut names = vec![];
    for (i, m) in defs.iter().enumerate() {
        let mut col = feature_ident(&m.name);
        while names.contains(&col) {
            col.push_str("_2");
        }
        let a = format!("f{i}");
        joins.push(feature_lateral(m, &a, seed_key)?);
        sel.push(format!("{a}.v as {col}"));
        names.push(col);
    }
    Ok((format!("select {} from {{seeds}} s {}", sel.join(", "), joins.join(" ")), names))
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

/// 把列前的表别名换成表名：`sr.sr_return_amt` → `store_returns.sr_return_amt`（规范 SQL 不给表起别名，提炼器却常照抄
/// 智能体 SQL 里的别名）。只改写“前缀.列”中列属于 `allowed` 里某张表、前缀本身不是这些表名的情形；其余原样保留，
/// 仍由 `check_expr` 判断。
pub fn qualify_aliases(expr: &str, allowed: &BTreeSet<String>, cat: &Catalog) -> String {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| Regex::new(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b").unwrap());
    re.replace_all(expr, |c: &regex::Captures| {
        let (prefix, col) = (c[1].to_lowercase(), &c[2]);
        if allowed.contains(&prefix) {
            return c[0].to_string();
        }
        let owners: Vec<&String> = cat.owners(&col.to_lowercase()).iter().filter(|t| allowed.contains(*t)).collect();
        match owners.as_slice() {
            [t] => format!("{t}.{col}"),
            _ => c[0].to_string(),
        }
    })
    .into_owned()
}

/// A table-keyed filter has a known owner even when joined tables share a column
/// name. Bind identifiers through the SQL AST; leave literals and function names
/// alone, and preserve the original text when no binding changes are needed.
fn qualify_owned_filter(table: &str, filter: &str) -> Result<String> {
    struct Bind<'a> {
        table: &'a str,
        changed: bool,
    }
    impl VisitorMut for Bind<'_> {
        type Break = ();
        fn pre_visit_expr(&mut self, expr: &mut Expr) -> ControlFlow<()> {
            if let Expr::Identifier(column) = expr {
                *expr = Expr::CompoundIdentifier(vec![Ident::new(self.table), column.clone()]);
                self.changed = true;
            }
            ControlFlow::Continue(())
        }
    }
    let mut statements = Parser::parse_sql(&PostgreSqlDialect {}, &format!("SELECT 1 WHERE {filter}"))?;
    ensure!(statements.len() == 1, "过滤必须是单个表达式");
    let Statement::Query(query) = &mut statements[0] else { bail!("过滤必须是表达式") };
    let SetExpr::Select(select) = query.body.as_mut() else { bail!("过滤必须是表达式") };
    let expression = select.selection.as_mut().ok_or_else(|| anyhow!("过滤不能为空"))?;
    let mut bind = Bind { table, changed: false };
    let _ = VisitMut::visit(expression, &mut bind);
    Ok(if bind.changed { expression.to_string() } else { filter.to_string() })
}

/// 表达式只能引用 `allowed` 中表的列与少量函数、关键字；不允许子查询与多语句。
/// 特征定义的度量另外允许的词：常用的标量函数，以及代表种子时间的 `seed_time`（编译时换成 `s.seed_time`，用于“距上次多少天”这类特征）。
pub const FEATURE_WORDS: &[&str] = &[
    "seed_time",
    "extract",
    "epoch",
    "date_part",
    "date_trunc",
    "date",
    "length",
    "char_length",
    "greatest",
    "least",
    "ln",
    "log",
    "sqrt",
    "power",
    "floor",
    "ceil",
    "exp",
    "sign",
    "mod",
    "trunc",
    "interval",
    "day",
    "days",
    "hour",
    "hours",
];

pub fn check_expr(expr: &str, allowed: &BTreeSet<String>, cat: &Catalog) -> std::result::Result<(), String> {
    check_expr_with(expr, allowed, cat, &[])
}

/// `check_expr`，另外允许 `extra` 里的词（特征定义用 `FEATURE_WORDS`）。
pub fn check_expr_with(expr: &str, allowed: &BTreeSet<String>, cat: &Catalog, extra: &[&str]) -> std::result::Result<(), String> {
    if expr.contains(';') || expr.contains("/*") || expr.contains("--") {
        return Err("表达式不能包含分号或注释".into());
    }
    // EXTRACT(field FROM x) 里的 FROM 不是子查询
    let expr = &extract_from_re().replace_all(expr, "extract(").to_string();
    for w in sqlscan::words(expr) {
        if w == "select" || w == "from" {
            return Err("表达式不能包含子查询".into());
        }
        // 口径内的表名只作列的限定前缀（store_returns.sr_return_amt）；规范 SQL 不给表起别名，这样写照样能执行
        if SQL_WORDS.contains(&w.as_str()) || extra.contains(&w.as_str()) || allowed.contains(&w) {
            continue;
        }
        let owners = cat.owners(&w);
        if owners.iter().any(|t| allowed.contains(t)) {
            continue;
        }
        match owners.first() {
            Some(t) => return Err(format!("{w} 属于表 {t}，不在口径涉及的表中")),
            None => return Err(format!("{w} 不是已知列或允许的函数")),
        }
    }
    Ok(())
}

fn extract_from_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)extract\s*\(\s*\w+\s+from\b").unwrap())
}

fn year_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\b(\d{4})\b").unwrap())
}

fn date_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\d{4}-\d{1,2}").unwrap())
}

/// 口径过滤只放口径必需条件：不在时间维度表上、不引用时间键或日期列、不含题目年份或日期字面量。
pub fn check_filter(
    fact: &str,
    table: &str,
    filter: &str,
    time: Option<&TimeSpec>,
    ask: &Ask,
    cat: &Catalog,
) -> std::result::Result<(), String> {
    if let Some(t) = time {
        if !t.is_column() && t.dim == table {
            return Err(format!("时间维度表 {table} 上的过滤属于查询参数"));
        }
        let (tt, col) = if t.is_column() { t.column_of(fact) } else { (fact.to_string(), t.fact_col.clone()) };
        if tt == table && sqlscan::words(filter).contains(&col.to_lowercase()) {
            return Err(format!("过滤引用了时间列 {col}，属于查询参数"));
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

/// 口径引用的列（表 → 列）：粒度、时间关联（日期维度的键、年、月列，或日期列）与关联键，聚合表达式与过滤中的列。
/// 结构依赖只比较这些列，无关列的增删不使口径失效。
pub fn columns(m: &Metric, cat: &Catalog) -> BTreeMap<String, BTreeSet<String>> {
    let mut out: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut add = |t: &str, c: &str| {
        out.entry(t.to_string()).or_default().insert(c.to_lowercase());
    };
    for c in &m.grain {
        add(&m.fact, c);
    }
    if let Some(t) = &m.time {
        if t.is_column() {
            let (tb, c) = t.column_of(&m.fact);
            add(&tb, &c);
        } else {
            add(&m.fact, &t.fact_col);
            add(&t.dim, &t.dim_col);
            add(&t.dim, &t.year_col);
            add(&t.dim, &t.month_col);
        }
    }
    for j in &m.joins {
        for (l, r) in &j.on {
            add(&j.left, l);
            add(&j.right, r);
        }
    }
    let exprs = std::iter::once(&m.measure).chain(m.filters.values()).chain(m.joins.iter().flat_map(|j| j.filters.values()));
    // 重名的列记到口径涉及的每张含有它的表上（宁可多记依赖）
    let tables = m.tables();
    for e in exprs {
        for w in sqlscan::words(e) {
            let owners: Vec<&String> = cat.owners(&w).iter().filter(|t| tables.contains(*t)).collect();
            if owners.is_empty() {
                if let Some(t) = cat.table_of(&w) {
                    add(t, &w);
                }
            }
            for t in owners {
                add(t, &w);
            }
        }
    }
    out
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
    let time = |m: &Metric| m.time.as_ref().map(|t| (t.fact_col.clone(), t.dim.clone(), t.dim_col.clone(), t.strategy));
    let grain = |m: &Metric| m.grain.iter().cloned().collect::<BTreeSet<_>>();
    a.fact == b.fact
        && squash(&a.measure) == squash(&b.measure)
        && grain(a) == grain(b)
        && time(a) == time(b)
        && joins(a) == joins(b)
        && filters(a) == filters(b)
        && a.empty == b.empty
        && a.entity == b.entity
}

/// 优化候选：在结构化定义上做保持语义的改写，由中间层逐一验证等价与代价后决定是否发布。
/// - 期间谓词改为日期键范围过滤（不连接日期维度；前提“日期键按月连续”成为新修订的条件）；
/// - 去掉口径里没有用到其任何列、也不带过滤的关联（左关联，或经验证不丢行的内关联）。
///
/// 可叠加时先给出叠加后的候选，再给出各单项。
pub fn rewrite_candidates(m: &Metric, cat: &Catalog) -> Vec<(String, Metric)> {
    let mut singles: Vec<(String, Metric)> = vec![];
    let range_ok = m.time.as_ref().is_some_and(|t| t.strategy == TimeStrategy::DimJoin && !t.dim.is_empty());
    if range_ok {
        let mut c = m.clone();
        let dim = m.time.as_ref().map(|t| t.dim.clone()).unwrap_or_default();
        if let Some(t) = c.time.as_mut() {
            t.strategy = TimeStrategy::KeyRange;
        }
        singles.push((format!("期间谓词改为日期键范围过滤，不连接 {dim}"), c));
    }
    // 表名作限定前缀，或某个词是该表的列（重名的列算作各表都用到），就算用到了这张表
    let used = |table: &str| -> bool {
        let exprs = std::iter::once(&m.measure).chain(m.filters.values()).chain(m.joins.iter().flat_map(|j| j.filters.values()));
        exprs.flat_map(|e| sqlscan::words(e)).any(|w| w == table || cat.owners(&w).iter().any(|o| o == table))
    };
    // 只去掉左连接：右侧在连接键上唯一（连接基数条件）时，左连接保留每个左表行恰好一次，去掉它结果不变。
    // 内连接会排除关联不上的行，去掉它的等价性要依赖一个不受维护的数据性质，因此不作为规则候选
    let mut dropped: Vec<String> = vec![];
    for (i, j) in m.joins.iter().enumerate() {
        let droppable = j.kind == JoinKind::Left
            && j.filters.is_empty()
            && !m.filters.contains_key(&j.right)
            && !used(&j.right)
            && !m.joins.iter().any(|o| o.left == j.right);
        if droppable {
            let mut c = m.clone();
            c.joins.remove(i);
            dropped.push(j.right.clone());
            singles.push((format!("去掉未使用的关联 {}", j.right), c));
        }
    }
    let mut out = vec![];
    if singles.len() > 1 {
        let mut c = m.clone();
        if range_ok {
            if let Some(t) = c.time.as_mut() {
                t.strategy = TimeStrategy::KeyRange;
            }
        }
        c.joins.retain(|j| !dropped.contains(&j.right));
        out.push((singles.iter().map(|(l, _)| l.as_str()).collect::<Vec<_>>().join("；"), c));
    }
    out.extend(singles);
    out
}

/// 候选是否就是某个规则改写（结构相同）：这类改写的等价由受维护的条件蕴含，不依赖抽样测试。
pub fn is_rule_rewrite(m: &Metric, cand: &Metric, cat: &Catalog) -> bool {
    rewrite_candidates(m, cat).iter().any(|(_, r)| same_structure(r, cand))
}

// ───────────────────────── 离线提炼 ─────────────────────────

const EXTRACT_SYSTEM: &str = "你是数据中间层的指标口径提炼器。输入是一次已被独立判定为成功的分析任务：题面、参与最终答案的 SQL 计算链、\
被中间层拦下的写法，以及相关表的元数据、已验证关联和粒度过滤。请总结题目所用业务指标的计算口径；题面给出了定义时以题面为准。\
只输出一个 JSON 对象，不要输出其他文字。字段：\n\
- name：指标名称，取题面中的业务名称\n\
- aliases：其他常见叫法，可以为空数组\n\
- definition：用一两句话说明口径\n\
- fact：事实表\n\
- measure：一个聚合表达式，如 sum(ss_net_paid)；只能引用 fact 与 joins 中表的列，不得包含子查询；列名在这些表之间重名时写成 表.列\n\
- grain：fact 上“一行对应一条业务记录”的键列数组\n\
- time：{\"role\": 时间角色（如“销售日”）, \"fact_col\": 事实表上的日期键列, \"dim\": 日期维度表, \"dim_col\": 维度表键列, \"grain\": \"day\" / \"month\" / \"year\"}；\
日期维度的年、月列不叫 d_year、d_moy 时另写 \"year_col\"、\"month_col\"；没有日期维度、期间由 DATE 列决定时写 \
{\"role\", \"fact_col\": \"表.日期列\", \"strategy\": \"column\", \"grain\"}，dim 与 dim_col 留空；与时间无关时为 null\n\
- joins：计算口径必需的关联（不含时间维度），每项 {\"left\": 多侧表, \"right\": 一侧表, \"on\": [[左表列, 右表列]], \"kind\": \"inner\" 或 \"left\", \"filters\": {表: 条件}}；\
left 是事实表或列表中前面已关联的表（雪花型可逐级关联）；必须与已验证关联的方向一致\n\
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

/// 清掉由中间层按已验证路径填写的元数据与来源信息（提炼器与优化器的输出都经此处理）。
fn scrub(m: &mut Metric) {
    m.basis = Basis::None;
    m.examples.clear();
    if let Some(t) = &mut m.time {
        t.loss_ratio = 0.0;
    }
    for j in &mut m.joins {
        j.key.clear();
        j.cardinality.clear();
        j.loss_ratio = 0.0;
        j.revision = 0;
    }
}

/// 解析提炼器输出。关联的键、基数、丢行比例和修订号由中间层按已验证路径填写，这里清空。
pub fn parse_draft(text: &str) -> std::result::Result<Draft, String> {
    let (Some(a), Some(b)) = (text.find('{'), text.rfind('}')) else { return Err("输出中没有 JSON 对象".into()) };
    if b < a {
        return Err("输出中没有 JSON 对象".into());
    }
    let raw: RawDraft = serde_json::from_str(&text[a..=b]).map_err(|e| format!("JSON 不符合格式：{e}"))?;
    let mut m = raw.metric;
    scrub(&mut m);
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

// ───────────────────────── 特征定义的提炼（RelBench） ─────────────────────────

const FEATURE_EXTRACT_SYSTEM: &str = "你是数据中间层的特征定义提炼器。输入是一次预测任务会话的结果：任务说明、种子表的实体列、\
提交的特征 SQL（以 {seeds} 为种子表，列为实体键与 seed_time）、按重要性排序的特征列，以及相关表的元数据与已验证关联。这次提交的验证分数优于参照。\
请把重要性靠前、形如“某个实体（或与它直接关联的实体，如帖子的作者）在种子时间之前（某个回看窗口内）对一张表的聚合”的特征列，各写成一条结构化的特征定义；\
同一张表上几个聚合的组合（如 sum(...) / nullif(count(*), 0)）也算一个聚合；跨不同表的聚合组合、种子表或实体表本身的列、窗口函数跳过。只输出一个 JSON 对象 {\"features\": [...]}，不要输出其他文字；\
最多 12 项，每项字段：\n\
- column：该特征在提交 SQL 输出中的列名\n\
- name：特征名称，英文小写加下划线，说明实体、度量与窗口，如 user_upvotes_received_91d\n\
- definition：一句话说明\n\
- fact：被聚合的表\n\
- measure：一个聚合表达式，如 count(*)、count(distinct votes.postid)、sum(posts.score)、avg(length(posts.body))；只能引用 fact 与 joins 中表的列，\
不得包含子查询或窗口函数；列名在这些表之间重名时写成 表.列；可以用 seed_time 表示这个种子的时间，例如距上一条评论的天数写成 \
extract(epoch from (seed_time - max(comments.creationdate))) / 86400；可用 exp、ln、greatest 等标量函数；结果必须是数值（不能是时间戳）\n\
- grain：fact 上一行对应一条记录的键列数组（通常是主键），只写列名、不带表名\n\
- time：{\"role\": 时间角色, \"fact_col\": \"表.列\"（决定这行是否在种子时间之前的时间列，在 fact 或 joins 中的表上）, \"strategy\": \"column\", \"grain\": \"day\"}\n\
- joins：从 fact 到实体列所在表必需的多对一关联，每项 {\"left\": 多侧表, \"right\": 一侧表, \"on\": [[左表列, 右表列]], \"kind\": \"inner\"}；\
left 是 fact 或列表中前面已关联的表；必须与已验证关联的方向一致；不需要时为空数组\n\
- filters：{表: 条件}，口径必需的行过滤，如 {\"votes\": \"votetypeid = 2\"}；不得包含日期、时间或种子相关的条件\n\
- entity：{\"table\": 任务的实体表, \"key\": 实体主键, \"via\": \"表.列\"（在 fact 或 joins 到达的表上）, \"window_days\": 回看天数或 null（全部历史）, \
\"anchor\": null 或实体表上的一列}；via 等于实体键时 anchor 为 null；聚合的是关联实体时（如帖子作者的徽章：实体表 posts，fact badges，via badges.userid），\
anchor 写实体表上指向它的列（owneruserid），表示 via 等于种子那一行实体的这一列\n\
- empty：计数类写 \"zero\"，其余写 \"null\"；提交的 SQL 用 coalesce(列, 常数) 给没有行的种子填值时（如距上次……多少天无记录取 9999），\
在 entity 里另写 \"fill\": 该常数";

#[derive(Debug)]
pub struct FeatureDraft {
    pub metric: Metric,
    /// 提交 SQL 输出里对应的列
    pub column: String,
}

#[derive(Deserialize)]
struct RawFeature {
    #[serde(flatten)]
    metric: Metric,
    column: String,
}

#[derive(Deserialize)]
struct RawFeatures {
    features: Vec<Value>,
}

#[derive(Debug, Default, Serialize)]
pub struct FeatureExtraction {
    #[serde(skip)]
    pub drafts: Vec<FeatureDraft>,
    /// 解析不了的单项（字段缺失或类型不对），不影响其他项
    pub skipped: Vec<String>,
    pub attempts: u32,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub seconds: f64,
    pub errors: Vec<String>,
}

/// 解析特征提炼器的输出；单项不合格时跳过并记下原因，整体不是 JSON 时报错。
pub fn parse_feature_drafts(text: &str) -> std::result::Result<(Vec<FeatureDraft>, Vec<String>), String> {
    let (Some(a), Some(b)) = (text.find('{'), text.rfind('}')) else { return Err("输出中没有 JSON 对象".into()) };
    if b < a {
        return Err("输出中没有 JSON 对象".into());
    }
    let raw: RawFeatures = serde_json::from_str(&text[a..=b]).map_err(|e| format!("JSON 不符合格式：{e}"))?;
    let (mut out, mut skipped) = (vec![], vec![]);
    for (i, v) in raw.features.into_iter().take(12).enumerate() {
        match serde_json::from_value::<RawFeature>(v) {
            Ok(r) => {
                let mut m = r.metric;
                scrub(&mut m);
                // 粒度键是事实表上的列：去掉事实表自己的表名前缀
                let prefix = format!("{}.", m.fact.trim());
                for c in &mut m.grain {
                    if let Some(rest) = c.trim().strip_prefix(&prefix) {
                        *c = rest.to_string();
                    }
                }
                if m.name.trim().is_empty() || m.fact.trim().is_empty() || m.measure.trim().is_empty() || m.entity.is_none() {
                    skipped.push(format!("第 {} 项：name、fact、measure、entity 不能为空", i + 1));
                    continue;
                }
                out.push(FeatureDraft { metric: m, column: r.column.trim().to_lowercase() });
            }
            Err(e) => skipped.push(format!("第 {} 项：{e}", i + 1)),
        }
    }
    Ok((out, skipped))
}

/// 调用模型提炼一次特征定义，格式错误时按固定次数重试；所有尝试的 token 与耗时都计入。
pub async fn extract_features(p: &Provider, input: &Value, max_attempts: u32) -> FeatureExtraction {
    let mut ex = FeatureExtraction::default();
    let t0 = Instant::now();
    let mut turns = vec![Turn::User(serde_json::to_string_pretty(input).unwrap_or_default())];
    for _ in 0..max_attempts.max(1) {
        ex.attempts += 1;
        let r = match p.chat(FEATURE_EXTRACT_SYSTEM, &turns, &[]).await {
            Ok(r) => r,
            Err(e) => {
                ex.errors.push(format!("{e:#}"));
                break;
            }
        };
        ex.input_tokens += r.input_tokens;
        ex.output_tokens += r.output_tokens;
        match parse_feature_drafts(&r.text) {
            Ok((d, s)) => {
                ex.drafts = d;
                ex.skipped = s;
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

// ───────────────────────── 优化提议 ─────────────────────────

const OPTIMIZE_SYSTEM: &str = "你是数据中间层的指标口径优化器。输入是一条已发布的指标口径（结构化字段）、它的规范 SQL 与执行计划、\
相关表的行数与列。请提出至多 3 个与原口径计算结果完全相同、但执行代价更低的改写。允许的改写：time.strategy 改为 \"key_range\"\
（事实表按日期键范围过滤，不连接日期维度）；去掉结果不依赖的关联；等价地简化聚合表达式或过滤写法。不得改变业务含义：\
度量所用的列、过滤的语义、粒度键必须与原口径一致，不得加入题目参数。只输出一个 JSON 数组，不要输出其他文字；每项是一个对象，\
字段与原口径相同（name, aliases, definition, fact, measure, grain, time{role, fact_col, dim, dim_col, grain, strategy}, joins, filters, \
empty, caveats），外加 rationale：一句话说明为什么等价且更省。中间层会逐一验证等价与代价，只有通过的才会发布。";

#[derive(Debug, Default, Serialize)]
pub struct Proposals {
    #[serde(skip)]
    pub drafts: Vec<(String, Metric)>,
    pub attempts: u32,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub seconds: f64,
    pub errors: Vec<String>,
}

/// 解析出的优化候选（说明, 口径）与被跳过单项的原因。
pub type Proposed = (Vec<(String, Metric)>, Vec<String>);

/// 解析优化器输出：一个 JSON 数组，每项是口径字段加 rationale。解析不了的单项跳过并记录。
pub fn parse_proposals(text: &str) -> std::result::Result<Proposed, String> {
    let (Some(a), Some(b)) = (text.find('['), text.rfind(']')) else { return Err("输出中没有 JSON 数组".into()) };
    if b < a {
        return Err("输出中没有 JSON 数组".into());
    }
    let arr: Vec<Value> = serde_json::from_str(&text[a..=b]).map_err(|e| format!("JSON 不符合格式：{e}"))?;
    let (mut out, mut errors) = (vec![], vec![]);
    for (i, mut v) in arr.into_iter().enumerate() {
        let Some(obj) = v.as_object_mut() else {
            errors.push(format!("第 {} 项不是对象", i + 1));
            continue;
        };
        for k in ["name", "definition", "fact", "measure"] {
            obj.entry(k).or_insert(Value::String(String::new()));
        }
        let rationale = obj.remove("rationale").and_then(|x| x.as_str().map(str::to_string)).unwrap_or_default();
        let mut m: Metric = match serde_json::from_value(v) {
            Ok(m) => m,
            Err(e) => {
                errors.push(format!("第 {} 项：{e}", i + 1));
                continue;
            }
        };
        scrub(&mut m);
        if m.fact.trim().is_empty() || m.measure.trim().is_empty() {
            errors.push(format!("第 {} 项缺少 fact 或 measure", i + 1));
            continue;
        }
        let label =
            if rationale.trim().is_empty() { format!("模型提议 {}", i + 1) } else { format!("模型提议：{}", rationale.trim()) };
        out.push((label, m));
    }
    Ok((out, errors))
}

/// 调用模型提出优化候选；格式错误时按固定次数重试，所有尝试的 token 与耗时都计入。
pub async fn propose(p: &Provider, input: &Value, max_attempts: u32) -> Proposals {
    let mut pr = Proposals::default();
    let t0 = Instant::now();
    let mut turns = vec![Turn::User(serde_json::to_string_pretty(input).unwrap_or_default())];
    for _ in 0..max_attempts.max(1) {
        pr.attempts += 1;
        let r = match p.chat(OPTIMIZE_SYSTEM, &turns, &[]).await {
            Ok(r) => r,
            Err(e) => {
                pr.errors.push(format!("{e:#}"));
                break;
            }
        };
        pr.input_tokens += r.input_tokens;
        pr.output_tokens += r.output_tokens;
        match parse_proposals(&r.text) {
            Ok((d, errs)) => {
                pr.drafts = d;
                pr.errors.extend(errs);
                break;
            }
            Err(e) => {
                pr.errors.push(e.clone());
                turns.push(Turn::Assistant { raw: r.raw });
                turns.push(Turn::User(format!("上一次输出无法解析：{e}。请只输出一个符合要求的 JSON 数组。")));
            }
        }
    }
    pr.seconds = t0.elapsed().as_secs_f64();
    pr
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalog::{Column, Table};
    use crate::knowledge::{EntityRef, JoinRef};

    #[test]
    fn compile_key_range_filters_by_date_key_bounds_without_joining_the_dimension() {
        let mut m = rate();
        m.time.as_mut().unwrap().strategy = TimeStrategy::KeyRange;
        let sql = compile(&m, &Ask::Single { period: Period::month(2001, 3) }).unwrap();
        let bounds = "store_sales.ss_sold_date_sk between (select min(d_date_sk) from date_dim where date_dim.d_year = 2001 \
                      and date_dim.d_moy between 3 and 3) and (select max(d_date_sk) from date_dim where date_dim.d_year = 2001 \
                      and date_dim.d_moy between 3 and 3)";
        assert!(sql.contains(bounds), "{sql}");
        assert!(!sql.contains("join date_dim"), "{sql}");
        let rank = compile(&m, &Ask::RankMonth { year: 2001 }).unwrap();
        assert!(rank.contains("join date_dim"), "按月排名仍需维度列：{rank}");
        assert!(!same_structure(&rate(), &m), "期间谓词的实现方式是结构的一部分");
    }

    #[test]
    fn feature_sql_bounds_every_row_by_the_seed_time_and_window() {
        let text = r#"{"features": [{"column": "up_91", "name": "User upvotes received 91d", "definition": "upvotes on the user's posts",
            "fact": "votes", "measure": "count(*)", "grain": ["votes.id"],
            "time": {"role": "vote time", "fact_col": "votes.creationdate", "strategy": "column", "grain": "day"},
            "joins": [{"left": "votes", "right": "posts", "on": [["postid", "id"]], "kind": "inner"}],
            "filters": {"votes": "votetypeid = 2"},
            "entity": {"table": "users", "key": "id", "via": "posts.owneruserid", "window_days": 91}, "empty": "zero"},
            {"column": "bad", "name": "no entity", "definition": "", "fact": "votes", "measure": "count(*)", "grain": ["id"]}]}"#;
        let (drafts, skipped) = parse_feature_drafts(text).unwrap();
        assert_eq!((drafts.len(), skipped.len()), (1, 1), "{skipped:?}");
        let m = &drafts[0].metric;
        assert_eq!(drafts[0].column, "up_91");
        assert_eq!(m.grain, vec!["id"]);
        let (sql, cols) = compose_features(&[m, m], "owneruserid").unwrap();
        assert_eq!(cols, vec!["user_upvotes_received_91d", "user_upvotes_received_91d_2"]);
        assert!(sql.starts_with("select s.owneruserid, s.seed_time, f0.v as user_upvotes_received_91d"), "{sql}");
        assert!(sql.contains("from {seeds} s left join lateral (select (coalesce(count(*), 0))::double precision as v from votes join posts on votes.postid = posts.id"), "{sql}");
        for part in [
            "posts.owneruserid = s.owneruserid",
            "votes.creationdate <= s.seed_time",
            "votes.creationdate > s.seed_time - interval '91 days'",
            "votetypeid = 2",
        ] {
            assert!(sql.contains(part), "{part} missing: {sql}");
        }
        let mut no_window = m.clone();
        no_window.entity.as_mut().unwrap().window_days = None;
        assert!(!feature_lateral(&no_window, "f0", "owneruserid").unwrap().contains("interval"));
        let mut period = m.clone();
        period.entity = None;
        assert!(feature_lateral(&period, "f0", "owneruserid").is_err());
        let mut recency = m.clone();
        recency.measure = "extract(epoch from (seed_time - max(votes.creationdate))) / 86400".into();
        let sql = feature_lateral(&recency, "f0", "owneruserid").unwrap();
        assert!(sql.contains("(s.seed_time - max(votes.creationdate))"), "{sql}");
        assert!(!sql.contains("s.s.seed_time"), "{sql}");
        // a related entity: votes on the seed post's owner's posts, keyed through posts.owneruserid of the seed post
        let mut owner = m.clone();
        owner.entity.as_mut().unwrap().table = "posts".into();
        owner.entity.as_mut().unwrap().anchor = Some("owneruserid".into());
        let sql = feature_lateral(&owner, "f0", "postid").unwrap();
        assert!(sql.contains("posts.owneruserid = (select ent.owneruserid from posts ent where ent.id = s.postid)"), "{sql}");
        // a seed with no rows takes the constant the submitted SQL filled in (coalesce(days_since_last, 9999))
        let mut filled = recency.clone();
        filled.entity.as_mut().unwrap().fill = Some(9999.0);
        let sql = feature_lateral(&filled, "f0", "owneruserid").unwrap();
        assert!(
            sql.contains("(coalesce(extract(epoch from (s.seed_time - max(votes.creationdate))) / 86400, 9999))::double precision"),
            "{sql}"
        );
        let parsed: EntityRef = serde_json::from_str(r#"{"table": "users", "key": "id", "via": "votes.userid", "fill": -1}"#).unwrap();
        assert_eq!(parsed.fill, Some(-1.0));
    }

    #[test]
    fn extract_from_is_not_a_subquery() {
        let allowed: BTreeSet<String> = ["store_sales".to_string()].into_iter().collect();
        let e = "extract(epoch from (seed_time - max(store_sales.ss_sold_date_sk))) / 86400";
        assert!(check_expr_with(e, &allowed, &cat(), FEATURE_WORDS).is_ok());
        assert!(check_expr_with("sum((select 1 from store_sales))", &allowed, &cat(), FEATURE_WORDS).is_err());
    }

    #[test]
    fn only_rule_forms_count_as_rule_rewrites() {
        let c = cat();
        let m = rate();
        let mut key_range = m.clone();
        key_range.time.as_mut().unwrap().strategy = TimeStrategy::KeyRange;
        key_range.definition = "模型写的说明不影响结构".into();
        assert!(is_rule_rewrite(&m, &key_range, &c), "模型提出的键范围改写与规则候选结构相同");
        let mut other = m.clone();
        other.measure = "sum(sr_return_amt) / sum(ss_net_paid) * 100.0".into();
        assert!(!is_rule_rewrite(&m, &other, &c), "改写了度量表达式的提议不是规则形式");
        assert!(!is_rule_rewrite(&m, &m, &c), "与当前修订相同不算改写");
    }

    #[test]
    fn rewrite_candidates_offer_key_range_and_drop_only_unused_joins() {
        // 退货率的度量用到 store_returns 的列，该关联不能去掉：只有日期键范围一个候选
        let c = rewrite_candidates(&rate(), &cat());
        assert_eq!(c.len(), 1, "{:?}", c.iter().map(|x| &x.0).collect::<Vec<_>>());
        assert_eq!(c[0].1.time.as_ref().unwrap().strategy, TimeStrategy::KeyRange);
        // 度量与过滤都不再用到 store_returns 时，该关联可以去掉：先给出叠加候选，再给出两个单项
        let mut unused = rate();
        unused.measure = "sum(ss_net_paid)".into();
        unused.filters.clear();
        unused.joins[0].filters.clear();
        unused.joins[0].kind = JoinKind::Left;
        let c = rewrite_candidates(&unused, &cat());
        assert_eq!(c.len(), 3, "{:?}", c.iter().map(|x| &x.0).collect::<Vec<_>>());
        assert!(c[0].1.joins.is_empty() && c[0].1.time.as_ref().unwrap().strategy == TimeStrategy::KeyRange);
        assert!(c.iter().skip(1).any(|(_, m)| m.joins.is_empty()));
        // 同样未使用的内连接不能去掉：它排除关联不上的行，去掉后可能多算
        unused.joins[0].kind = JoinKind::Inner;
        let c = rewrite_candidates(&unused, &cat());
        assert_eq!(c.len(), 1, "{:?}", c.iter().map(|x| &x.0).collect::<Vec<_>>());
        assert_eq!(c[0].1.joins.len(), 1);
    }

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
                loss_ratio: 0.0,
                strategy: TimeStrategy::DimJoin,
                year_col: "d_year".into(),
                month_col: "d_moy".into(),
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
                orphan_ratio: 0.0,
                revision: 0,
            }],
            filters: BTreeMap::new(),
            empty: EmptyRule::Unspecified,
            caveats: vec![],
            examples: vec![],
            basis: Basis::None,
            entity: None,
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
        // 只引用一条查询：答案可在第一行的其他列；算式仍取各查询的首个单元格
        results.insert(3, serde_json::json!({"rows": [["12179532.00", "2893422.10", "23.76"]]}));
        assert!(verify_chain(&traj(&["r3"], Some("r3"), "23.76"), &results).is_ok());
        assert!(verify_chain(&traj(&["r3"], Some("r3"), "23.70"), &results).is_err());
        assert!(verify_chain(&traj(&["r3", "r2"], Some("r3 / r2"), "23.76"), &results).is_err());
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
    fn owned_filters_bind_shared_columns_without_changing_literals() {
        assert_eq!(qualify_owned_filter("lineitem", "is_current = 1").unwrap(), "lineitem.is_current = 1");
        assert_eq!(qualify_owned_filter("part", "is_current = 'Y'").unwrap(), "part.is_current = 'Y'");
        assert_eq!(
            qualify_owned_filter("part", "coalesce(is_current, 'is_current') = 'Y'").unwrap(),
            "coalesce(part.is_current, 'is_current') = 'Y'"
        );
        assert_eq!(qualify_owned_filter("part", "part.is_current = 'Y'").unwrap(), "part.is_current = 'Y'");
        assert!(qualify_owned_filter("part", "is_current = 'Y'; select 2").is_err());
    }

    #[test]
    fn compile_keeps_left_join_filters_in_on_clause() {
        let m = rate();
        let p = |y, mo| Period::month(y, mo);
        let single = compile(&m, &Ask::Single { period: p(2002, 9) }).unwrap();
        assert!(single.contains(
            "left join store_returns on store_sales.ss_ticket_number = store_returns.sr_ticket_number \
             and store_sales.ss_item_sk = store_returns.sr_item_sk and (store_returns.sr_status = '完成')"
        ));
        assert!(single.contains(
            "join date_dim on store_sales.ss_sold_date_sk = date_dim.d_date_sk where date_dim.d_year = 2002 and date_dim.d_moy between 9 and 9"
        ));
        let diff = compile(&m, &Ask::Diff { a: p(2002, 9), b: p(2001, 6) }).unwrap();
        assert!(diff.starts_with("select (select ") && diff.contains(") - (select "));
        let rank = compile(&m, &Ask::RankMonth { year: 2001 }).unwrap();
        assert!(rank.ends_with("group by 1 order by 100.0 * sum(sr_return_amt) / sum(ss_net_paid) desc nulls last, 1 limit 1"));
        let peak = compile(&m, &Ask::PeakRise { year: 2002 }).unwrap();
        assert!(peak.contains("v - lag(v) over (order by mo) as rise from (select date_dim.d_moy as mo, 100.0 * sum(sr_return_amt)"));
        assert!(
            peak.contains("where date_dim.d_year = 2002 group by 1) m) r where rise is not null order by rise desc nulls last, mo limit 1")
        );
        let above = compile(&m, &Ask::AboveMean { year: 2002 }).unwrap();
        assert!(
            above.starts_with("select count(*) as value from (select date_dim.d_moy as mo,")
                && above.contains(") m where v > (select avg(v) from (")
        );
        let mut inner = m.clone();
        inner.joins[0].kind = JoinKind::Inner;
        let s = compile(&inner, &Ask::Single { period: p(2002, 9) }).unwrap();
        assert!(s.contains("where (store_returns.sr_status = '完成') and date_dim.d_year = 2002"));
        let mut literal_filters = m.clone();
        literal_filters.joins[0].filters.insert("store_returns".into(), "sr_status = 'A B'".into());
        literal_filters.filters.insert("store_returns".into(), "sr_status = 'AB'".into());
        let s = compile(&literal_filters, &Ask::Single { period: p(2002, 9) }).unwrap();
        assert!(s.contains("(store_returns.sr_status = 'A B') and (store_returns.sr_status = 'AB')"));
        let mut different_values = literal_filters.clone();
        different_values.filters.insert("store_returns".into(), "sr_status = 'A B'".into());
        assert!(!same_structure(&literal_filters, &different_values));
        let mut untimed = m;
        untimed.time = None;
        assert!(compile(&untimed, &Ask::RankMonth { year: 2001 }).is_err());
    }

    #[test]
    fn compile_rejects_reverse_fact_join_to_prevent_fanout() {
        let ask = Ask::Single { period: Period::month(2002, 9) };
        let mut m = rate();
        let j = &mut m.joins[0];
        std::mem::swap(&mut j.left, &mut j.right);
        for (l, r) in &mut j.on {
            std::mem::swap(l, r);
        }
        // Right-side uniqueness now proves the fact key, not the number of matching returns.
        assert!(compile(&m, &ask).unwrap_err().to_string().contains("反向"));
        m.joins[0].left = "item".into();
        m.joins[0].right = "store_returns".into();
        assert!(compile(&m, &ask).is_err());
        m.joins[0].left = m.fact.clone();
        m.joins[0].right = m.fact.clone();
        assert!(compile(&m, &ask).is_err());
    }

    #[test]
    fn filters_reject_query_parameters() {
        let c = cat();
        let m = rate();
        let ask = Ask::Single { period: Period::month(2002, 9) };
        let t = m.time.as_ref();
        assert!(check_filter("store_sales", "store_returns", "sr_status = '完成'", t, &ask, &c).is_ok());
        assert!(check_filter("store_sales", "date_dim", "d_year = 2002", t, &ask, &c).is_err());
        assert!(check_filter("store_sales", "store_sales", "ss_sold_date_sk > 5", t, &ask, &c).is_err());
        assert!(check_filter("store_sales", "store_sales", "ss_net_paid > 2002", t, &ask, &c).is_err());
        assert!(check_filter("store_sales", "store_returns", "sr_status = '2002-09'", t, &ask, &c).is_err());
        assert!(check_filter("store_sales", "store_returns", "ss_net_paid > 0", t, &ask, &c).is_err());
        let allowed: BTreeSet<String> = ["store_sales".to_string()].into_iter().collect();
        assert!(check_expr("sum(ss_net_paid)", &allowed, &c).is_ok());
        assert!(check_expr("sum(sr_return_amt)", &allowed, &c).is_err());
        assert!(check_expr("(select 1)", &allowed, &c).is_err());
        assert!(check_expr("sum(unknown_col)", &allowed, &c).is_err());
        // 口径内表名作列的限定前缀可以；口径外的表不行
        assert!(check_expr("sum(store_sales.ss_net_paid)", &allowed, &c).is_ok());
        assert!(check_expr("sum(store_returns.sr_return_amt)", &allowed, &c).is_err());
        let both: BTreeSet<String> = ["store_sales".to_string(), "store_returns".to_string()].into_iter().collect();
        assert!(check_expr("100.0 * sum(store_returns.sr_return_amt) / sum(store_sales.ss_net_paid)", &both, &c).is_ok());
        // 提炼器照抄的表别名改写成表名后可以通过；口径外的表、未知列与数字照旧
        let e = qualify_aliases("ROUND(SUM(sr.sr_return_amt) / NULLIF(SUM(ss.ss_net_paid), 0) * 100.0, 2)", &both, &c);
        assert_eq!(e, "ROUND(SUM(store_returns.sr_return_amt) / NULLIF(SUM(store_sales.ss_net_paid), 0) * 100.0, 2)");
        assert!(check_expr(&e, &both, &c).is_ok());
        assert_eq!(qualify_aliases("sum(sr.sr_return_amt)", &allowed, &c), "sum(sr.sr_return_amt)");
        assert_eq!(qualify_aliases("sum(x.unknown_col)", &both, &c), "sum(x.unknown_col)");
        assert_eq!(qualify_aliases("sum(store_sales.ss_net_paid)", &both, &c), "sum(store_sales.ss_net_paid)");
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

    #[test]
    fn referenced_columns_cover_keys_measure_and_filters() {
        let cols = columns(&rate(), &cat());
        let set = |xs: &[&str]| xs.iter().map(|x| x.to_string()).collect::<BTreeSet<String>>();
        assert_eq!(cols["store_sales"], set(&["ss_item_sk", "ss_net_paid", "ss_sold_date_sk", "ss_ticket_number"]));
        assert_eq!(cols["store_returns"], set(&["sr_item_sk", "sr_return_amt", "sr_status", "sr_ticket_number"]));
        assert_eq!(cols["date_dim"], set(&["d_date_sk", "d_moy", "d_year"]));
    }

    #[test]
    fn compile_date_column_calendar_and_snowflake_chain() {
        let mut m = rate();
        m.joins.clear();
        m.time = Some(TimeSpec {
            role: "交易日".into(),
            fact_col: "store_sales.ss_sold_date".into(),
            dim: String::new(),
            dim_col: String::new(),
            grain: "month".into(),
            loss_ratio: 0.0,
            strategy: TimeStrategy::Column,
            year_col: "d_year".into(),
            month_col: "d_moy".into(),
        });
        let single = compile(&m, &Ask::Single { period: Period::month(2002, 12) }).unwrap();
        assert!(
            single.contains("store_sales.ss_sold_date >= date '2002-12-01' and store_sales.ss_sold_date < date '2003-01-01'"),
            "{single}"
        );
        assert!(!single.contains("date_dim"), "{single}");
        let peak = compile(&m, &Ask::PeakRise { year: 2002 }).unwrap();
        assert!(peak.contains("select extract(month from store_sales.ss_sold_date)::int as mo,"), "{peak}");
        assert!(peak.contains("store_sales.ss_sold_date >= date '2002-01-01' and store_sales.ss_sold_date < date '2003-01-01' group by 1"));
        assert!(m.tables().iter().all(|t| !t.is_empty()), "日期列方式没有维度表：{:?}", m.tables());
        // 雪花型：事实表 → item → 第二层维表；第二层的过滤进 WHERE，关联条件用表名限定
        m.joins = vec![
            JoinRef {
                key: String::new(),
                left: "store_sales".into(),
                right: "item".into(),
                on: vec![("ss_item_sk".into(), "i_item_sk".into())],
                kind: JoinKind::Inner,
                filters: BTreeMap::new(),
                cardinality: String::new(),
                loss_ratio: 0.0,
                orphan_ratio: 0.0,
                revision: 0,
            },
            JoinRef {
                key: String::new(),
                left: "item".into(),
                right: "brand".into(),
                on: vec![("i_brand_id".into(), "b_id".into())],
                kind: JoinKind::Inner,
                filters: [("brand".to_string(), "brand.b_region = 'EU'".to_string())].into_iter().collect(),
                cardinality: String::new(),
                loss_ratio: 0.0,
                orphan_ratio: 0.0,
                revision: 0,
            },
        ];
        let s = compile(&m, &Ask::Single { period: Period::month(2002, 9) }).unwrap();
        assert!(s.contains("join item on store_sales.ss_item_sk = item.i_item_sk join brand on item.i_brand_id = brand.b_id"), "{s}");
        assert!(s.contains("where (brand.b_region = 'EU') and store_sales.ss_sold_date >= date '2002-09-01'"), "{s}");
        // 链必须从已到达的表出发
        m.joins.swap(0, 1);
        assert!(compile(&m, &Ask::Single { period: Period::month(2002, 9) }).is_err());
    }

    #[test]
    fn repeated_column_names_resolve_within_the_definition() {
        let col = |n: &str| Column { name: n.into(), dtype: "integer".into(), comment: None, n_distinct: None };
        let table =
            |n: &str, cols: &[&str]| Table { name: n.into(), comment: None, rows_est: 1.0, cols: cols.iter().map(|c| col(c)).collect() };
        let c = Catalog::from_tables(vec![
            table("trans", &["trans_id", "account_id", "amount", "type"]),
            table("loan", &["loan_id", "account_id", "amount"]),
            table("account", &["account_id", "district_id"]),
        ]);
        assert_eq!(c.table_of("amount"), None);
        assert_eq!(c.owners("amount"), ["loan".to_string(), "trans".to_string()]);
        let allowed: BTreeSet<String> = ["trans".to_string()].into_iter().collect();
        assert!(check_expr("sum(trans.amount)", &allowed, &c).is_ok());
        assert!(check_expr("sum(amount)", &allowed, &c).is_ok());
        assert!(check_expr("sum(district_id)", &allowed, &c).is_err());
        assert_eq!(qualify_aliases("sum(t1.amount)", &allowed, &c), "sum(trans.amount)");
        let both: BTreeSet<String> = ["trans".to_string(), "loan".to_string()].into_iter().collect();
        assert_eq!(qualify_aliases("sum(t1.amount)", &both, &c), "sum(t1.amount)", "两张表都有 amount 时不猜");
    }
}
