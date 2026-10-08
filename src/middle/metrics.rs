//! 指标经验的生命周期：提炼输入、晋升门槛（G1–G7）、查找与守护、执行端引用检查、受限修复与学习题回归（G8）。
//! 依赖表有写入后的维护方式见 `Maint`：逐写入撤销、只看结构、定义级重验、条件级重验。

use super::{inc, join_key, outcome_text, scope_prefix, snap_key, ver_sig, Ctx, Maint, Middle, SqlCall, TaskLog};
use crate::catalog::{self, TableVersion};
use crate::checks::{same_on, Check, On, Outcome};
use crate::db::QKind;
use crate::knowledge::{Basis, Content, Entry, Example, JoinPath, Metric, Status, TimeSpec, TimeStrategy};
use crate::metric::{self, Answer, Ask, Draft, Trajectory};
use crate::sqlscan;
use anyhow::Result;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::time::Instant;

/// find_metric 每次最多返回的条目数（各组相同的检索预算）。
const FIND_BUDGET: usize = 3;

/// 覆盖条件的容差：事实表关联不上时间维度的行占比最多比准入基线高 0.1 个百分点。
const COVERAGE_TOLERANCE: f64 = 0.001;

/// 验证证据：来源任务、判题值与各门槛记录。不随 find_metric 返回。
#[derive(Clone, Debug, Serialize)]
pub struct MetricEvidence {
    pub task: String,
    pub ask: Ask,
    pub decimals: u32,
    pub value: Option<Answer>,
    /// 轨迹发生时的表版本
    pub versions: BTreeMap<String, TableVersion>,
    pub gates: Vec<Value>,
    /// 同结构口径被其他轨迹再次得出的次数（只作佐证，不改变状态）
    pub corroborations: u32,
    pub repaired: bool,
    /// 学习题的判题查询，供修复后的 G8 回归在当前快照上重算期望值
    pub judge: Option<String>,
    /// 已发布的优化修订数（等价且更省的改写）
    #[serde(default)]
    pub optimized: u32,
}

enum Checked {
    Valid(Entry),
    /// 附带给 Agent 看的原因
    Unavailable(Entry, String),
    Missing,
}

enum Breach {
    /// 逐写入撤销：不检查条件，依赖表有写入即撤销
    Write(String),
    Schema(String),
    Join {
        idx: usize,
        path: Option<JoinPath>,
        reason: String,
    },
    Time(String),
    /// 事实行无法归入期间（时间关联丢行比例超过基线）；不在受限修复范围
    Coverage(String),
    Grain(String),
}

impl Breach {
    fn reason(&self) -> String {
        match self {
            Breach::Write(r)
            | Breach::Schema(r)
            | Breach::Time(r)
            | Breach::Coverage(r)
            | Breach::Grain(r)
            | Breach::Join { reason: r, .. } => r.clone(),
        }
    }
}

fn blocked(s: &Status) -> Option<String> {
    match s {
        Status::Valid => None,
        Status::Revoked(r) => Some(format!("已撤销：{r}")),
        Status::Candidate(_) => Some("修复待验证或未通过验证，暂不可用".to_string()),
    }
}

/// 结构依赖只看口径引用的列（`used`）：引用列都在且类型不变时，无关列的增删不算结构变化。
/// 没有列信息时按整表结构指纹判断。
fn schema_breach(
    e: &Entry,
    used: &BTreeMap<String, BTreeSet<String>>,
    cur: &HashMap<String, TableVersion>,
    changed: &[String],
) -> Option<Breach> {
    for t in changed {
        let (Some(now), Some(then)) = (cur.get(t), e.deps.get(t)) else { return Some(Breach::Schema(format!("表 {t} 不存在"))) };
        if now.schema == then.schema {
            continue;
        }
        match used.get(t).filter(|_| !then.cols.is_empty()) {
            Some(cols) => {
                if let Some(c) = cols.iter().find(|c| now.col_sig(c) != then.col_sig(c)) {
                    return Some(Breach::Schema(format!("表 {t} 的列 {c} 已删除或改变类型")));
                }
            }
            None => return Some(Breach::Schema(format!("表 {t} 的结构已变化"))),
        }
    }
    None
}

fn squash(s: &str) -> String {
    sqlscan::expression_key(s)
}

/// 已通过的 `known` 蕴含 `c` 通过：同表、同过滤的键唯一性，`known` 的键列是 `c` 的子集。
/// 检查只统计键列全不为空且满足过滤的行；键列变多时这些行只会变少，子集键唯一则超集键也唯一。
fn implies(known: &Check, c: &Check) -> bool {
    match (known, c) {
        (Check::KeyUnique { table: t1, cols: c1, filter: f1 }, Check::KeyUnique { table: t2, cols: c2, filter: f2 }) => {
            let norm = |f: &Option<String>| f.as_deref().map(squash).unwrap_or_default();
            t1 == t2 && norm(f1) == norm(f2) && c1.iter().all(|x| c2.contains(x))
        }
        _ => false,
    }
}

/// 同一条件：键唯一性按表、列集合与过滤 token 比较，保留字符串值，其他检查要求完全相同。
fn same_cond(a: &Check, b: &Check) -> bool {
    match (a, b) {
        (Check::KeyUnique { table: t1, cols: c1, filter: f1 }, Check::KeyUnique { table: t2, cols: c2, filter: f2 }) => {
            let norm = |f: &Option<String>| f.as_deref().map(squash).unwrap_or_default();
            t1 == t2 && c1.iter().collect::<BTreeSet<_>>() == c2.iter().collect::<BTreeSet<_>>() && norm(f1) == norm(f2)
        }
        _ => a == b,
    }
}

pub(super) type Gate = std::result::Result<(), String>;

pub(super) fn record(gates: &mut Vec<Value>, gate: &str, r: Gate) -> Option<(String, String)> {
    match r {
        Ok(()) => {
            gates.push(json!({"gate": gate, "pass": true}));
            None
        }
        Err(e) => {
            gates.push(json!({"gate": gate, "pass": false, "reason": e}));
            Some((gate.to_string(), e))
        }
    }
}

/// 门槛不通过就停止，返回 (门槛, 原因)。
macro_rules! gate {
    ($gates:expr, $name:expr, $r:expr) => {
        if let Some(f) = record($gates, $name, $r) {
            return Ok(Some(f));
        }
    };
}

/// `sub` 中每个过滤都出现在 `sup` 的同表条件里。
fn covers(sup: &BTreeMap<String, String>, sub: &BTreeMap<String, String>) -> bool {
    sub.iter().all(|(t, f)| sup.get(t).is_some_and(|x| sqlscan::contains_filter(x, f)))
}

pub(super) fn metric_of(e: &Entry) -> Option<&Metric> {
    if let Content::Metric(m) = &e.content {
        Some(m)
    } else {
        None
    }
}

fn view(e: &Entry) -> Value {
    let Some(m) = metric_of(e) else { return Value::Null };
    let mut v = serde_json::to_value(m).unwrap_or_default();
    v["key"] = json!(e.key);
    v["revision"] = json!(e.revision);
    v["depends_on"] = json!(e.deps);
    v
}

/// 覆盖条件：事实表按时间键关联时间维度后的行数，与事实表行数比较。它读事实表与维度表，任一有写入都要重查。
fn coverage_check(m: &Metric) -> Option<Check> {
    let t = m.time.as_ref()?;
    Some(Check::RowConservation {
        left: m.fact.clone(),
        right: t.dim.clone(),
        on: vec![(t.fact_col.clone(), t.dim_col.clone())],
        lf: None,
        rf: None,
    })
}

/// 关联不上的行占比（空键或孤儿键）。
fn loss_of(o: &Outcome) -> f64 {
    (1.0 - o.metrics["join_ratio"].as_f64().unwrap_or(1.0)).max(0.0)
}

/// 规范 SQL 实际作用于事实表的过滤：口径过滤与各关联上的事实表过滤（`metric::compile` 都放进 WHERE），去重后合取。
fn fact_filter(m: &Metric) -> Option<String> {
    let mut fs: Vec<&String> = vec![];
    for f in m.filters.get(&m.fact).into_iter().chain(m.joins.iter().filter_map(|j| j.filters.get(&m.fact))) {
        if !fs.iter().any(|x| squash(x) == squash(f)) {
            fs.push(f);
        }
    }
    match fs.as_slice() {
        [] => None,
        [f] => Some((*f).clone()),
        _ => Some(fs.iter().map(|f| format!("({f})")).collect::<Vec<_>>().join(" and ")),
    }
}

/// 粒度条件。键列排序，使列顺序不同的同一条件得到相同的检查键（在途合并按检查键进行）。
pub(super) fn grain_check(m: &Metric) -> Check {
    let mut cols = m.grain.clone();
    cols.sort();
    Check::KeyUnique { table: m.fact.clone(), cols, filter: fact_filter(m) }
}

/// 日期键连续条件：期间谓词按日期键范围过滤的修订所依赖（`TimeStrategy::KeyRange`）。
pub(super) fn time_contiguity_check(t: &TimeSpec) -> Check {
    Check::DateKeysContiguous { dim: t.dim.clone(), key: t.dim_col.clone(), year_col: "d_year".into(), month_col: "d_moy".into() }
}

/// 绑定快照执行要核对的条件（与 `metric_breach` 维护的条件一致）：各关联一侧的键唯一性、时间维度键的唯一性、
/// 覆盖（附准入基线）、粒度；日期键范围修订另加日期键连续。返回条件与覆盖基线（只有覆盖条件有）。
fn bound_conditions(m: &Metric) -> Vec<(Check, Option<f64>)> {
    let mut out = vec![];
    for j in &m.joins {
        let mut cols: Vec<String> = j.on.iter().map(|(_, r)| r.clone()).collect();
        cols.sort();
        out.push((Check::KeyUnique { table: j.right.clone(), cols, filter: j.filters.get(&j.right).cloned() }, None));
    }
    if let Some(t) = &m.time {
        out.push((Check::KeyUnique { table: t.dim.clone(), cols: vec![t.dim_col.clone()], filter: None }, None));
        if let Some(c) = coverage_check(m) {
            out.push((c, Some(t.loss_ratio + COVERAGE_TOLERANCE)));
        }
        if t.strategy == TimeStrategy::KeyRange {
            out.push((time_contiguity_check(t), None));
        }
    }
    out.push((grain_check(m), None));
    out
}

impl TaskLog {
    /// 参与最终答案的查询：used 与 derivation 引用的编号；两者都没有时取全部。
    fn used_calls(&self, traj: &Trajectory) -> Vec<&SqlCall> {
        let mut used: BTreeSet<usize> = traj.used.iter().filter_map(|r| metric::ref_index(r)).collect();
        if let Some(d) = &traj.derivation {
            used.extend(metric::refs_in(d).unwrap_or_default());
        }
        self.calls.iter().filter(|c| used.is_empty() || used.contains(&c.index)).collect()
    }

    /// 按 derivation 重算并与答案核对。
    pub fn verify(&self, traj: &Trajectory) -> std::result::Result<Answer, String> {
        let results: BTreeMap<usize, Value> = self.calls.iter().map(|c| (c.index, c.result.clone())).collect();
        metric::verify_chain(traj, &results)
    }

    /// 计算链涉及表的版本；链条中途版本变化视为快照不一致。
    fn chain_versions(&self, traj: &Trajectory) -> std::result::Result<BTreeMap<String, TableVersion>, String> {
        let mut v = BTreeMap::new();
        for c in self.used_calls(traj) {
            for (t, x) in &c.deps {
                if let Some(prev) = v.insert(t.clone(), x.clone()) {
                    if prev != *x {
                        return Err(format!("表 {t} 在计算链中途发生了变化"));
                    }
                }
            }
        }
        Ok(v)
    }
}

impl Middle {
    pub(super) fn mfk(&self, ctx: &Ctx, key: &str) -> String {
        format!("{}|{}", scope_prefix(self.cfg.metric_scope, ctx), key)
    }

    pub(super) fn metric_event(&self, v: Value) {
        self.metric_events.lock().push(v);
    }

    /// 取出并清空指标经验事件（实验按阶段切分）。
    pub fn take_metric_events(&self) -> Vec<Value> {
        std::mem::take(&mut *self.metric_events.lock())
    }

    fn is_repaired(&self, fk: &str) -> bool {
        self.metric_evidence.lock().get(fk).is_some_and(|x| x.repaired)
    }

    /// 全部指标条目：(完整键, 条目, 验证证据)。
    pub fn metric_entries(&self) -> Vec<(String, Entry, Option<MetricEvidence>)> {
        let entries: Vec<(String, Entry)> =
            self.store.scan("").into_iter().filter(|(_, e)| matches!(e.content, Content::Metric(_))).collect();
        let ev = self.metric_evidence.lock();
        entries
            .into_iter()
            .map(|(k, e)| {
                let x = ev.get(&k).cloned();
                (k, e, x)
            })
            .collect()
    }

    pub fn metric_report(&self) -> Value {
        let entries: Vec<Value> = self
            .metric_entries()
            .into_iter()
            .map(|(fk, e, ev)| {
                json!({"full_key": fk, "key": e.key, "revision": e.revision, "status": e.status, "created_by": e.created_by,
                       "hits": e.hits, "consumers": e.consumers, "depends_on": e.deps, "metric": metric_of(&e), "evidence": ev})
            })
            .collect();
        json!({"entries": entries})
    }

    // ───────────────────────── 提炼与晋升 ─────────────────────────

    /// 提炼器输入：题面、计算链 SQL、被拦下的写法与元数据。不含业务行和结果值。
    pub fn extract_input(&self, ctx: &Ctx, traj: &Trajectory, log: &TaskLog) -> Value {
        let calls = log.used_calls(traj);
        let mut tables = BTreeSet::new();
        for c in &calls {
            tables.extend(sqlscan::tables(&c.sql, &self.cat));
        }
        let meta: Vec<Value> = tables
            .iter()
            .filter_map(|t| self.cat.table(t))
            .map(|t| {
                let cols: Vec<Value> = t.cols.iter().map(|c| json!({"name": c.name, "type": c.dtype, "comment": c.comment})).collect();
                json!({"table": t.name, "comment": t.comment, "columns": cols})
            })
            .collect();
        let list: Vec<&String> = tables.iter().collect();
        let mut joins = vec![];
        for (i, a) in list.iter().enumerate() {
            for b in &list[i + 1..] {
                if let Some(Entry { content: Content::Join { paths, .. }, status: Status::Valid, .. }) =
                    self.store.get(&self.fk(ctx, &join_key(a, b)))
                {
                    for p in paths {
                        joins.push(json!({"left": p.left, "right": p.right, "on": p.on, "filters": p.filters,
                                          "cardinality": p.cardinality(), "loss_ratio": p.loss_ratio}));
                    }
                }
            }
        }
        let grains: Vec<Value> = tables
            .iter()
            .filter_map(|t| match self.store.get(&self.fk(ctx, &format!("grain:{t}"))) {
                Some(Entry { content: Content::Profile(g), status: Status::Valid, .. }) => Some(g),
                _ => None,
            })
            .collect();
        let rejected: Vec<Value> = log.rejections.iter().map(|r| json!({"sql": r["sql"], "reason": r["reason"]})).collect();
        let chain: Vec<Value> = calls.iter().map(|c| json!({"ref": format!("r{}", c.index), "sql": c.sql})).collect();
        json!({
            "question": traj.question,
            "chain": chain,
            "derivation": traj.derivation.clone().or_else(|| traj.used.first().cloned()),
            "rejected": rejected,
            "tables": meta,
            "verified_joins": joins,
            "grain_filters": grains,
        })
    }

    /// 提交一条提炼结果：依次过 G1–G7，全部通过才在授权范围内共享，否则保持候选。
    pub async fn submit_metric(&self, ctx: &Ctx, draft: Draft, traj: &Trajectory, log: &TaskLog) -> Result<Value> {
        let mut m = draft.metric;
        m.basis = traj.basis.clone();
        let sql = draft.example_sql.trim().trim_end_matches(';').trim().to_string();
        let example_ref = sql.clone();
        m.examples = vec![Example { question: traj.question.clone(), sql }];
        let mut gates = vec![];
        let failed = self.promotion_gates(ctx, &mut m, traj, log, &mut gates).await?;
        let task = traj.task.clone();
        let base = format!("metric:{}", m.name.trim());
        let prefix = self.mfk(ctx, &base);
        let existing: Vec<(String, Entry)> =
            self.store.scan(&prefix).into_iter().filter(|(k, _)| *k == prefix || k.starts_with(&format!("{prefix}#"))).collect();
        let same = existing.iter().find(|(_, e)| metric_of(e).is_some_and(|x| metric::same_structure(x, &m))).cloned();
        if let Some((k, e)) = same.as_ref().filter(|(_, e)| e.status == Status::Valid) {
            let v = match &failed {
                None => {
                    if let Some(ev) = self.metric_evidence.lock().get_mut(k) {
                        ev.corroborations += 1;
                    }
                    json!({"event": "corroborated", "key": e.key, "revision": e.revision, "task": task, "gates": gates})
                }
                Some((g, r)) => {
                    json!({"event": "candidate", "key": e.key, "task": task, "failed_gate": g, "reason": r, "gates": gates,
                           "note": "同结构的有效条目已存在，未覆盖"})
                }
            };
            self.metric_event(v.clone());
            return Ok(v);
        }
        let (fk, rev) = match &same {
            Some((k, e)) => (k.clone(), e.revision + 1),
            None if existing.is_empty() => (prefix.clone(), 0),
            None => (format!("{prefix}#{}", existing.len() + 1), 0),
        };
        let key = fk.split_once('|').map_or_else(|| fk.clone(), |(_, k)| k.to_string());
        let deps = self.deps_for(&m.tables()).await?;
        let guards = vec![grain_check(&m)];
        let mut e = self.new_entry(ctx, &key, Content::Metric(Box::new(m)), deps, guards);
        e.revision = rev;
        e.status = match &failed {
            None => Status::Valid,
            Some((g, r)) => Status::Candidate(format!("{g}：{r}")),
        };
        self.store.put(&fk, e);
        let evidence = MetricEvidence {
            task: task.clone(),
            ask: traj.ask,
            decimals: traj.decimals,
            value: log.verify(traj).ok(),
            versions: log.chain_versions(traj).unwrap_or_default(),
            gates: gates.clone(),
            corroborations: 0,
            repaired: false,
            judge: if self.cfg.g8_example { Some(example_ref) } else { traj.judge.clone() },
            optimized: 0,
        };
        self.metric_evidence.lock().insert(fk, evidence);
        let v = json!({
            "event": if failed.is_none() { "promoted" } else { "candidate" },
            "key": key, "revision": rev, "task": task,
            "failed_gate": failed.as_ref().map(|f| f.0.clone()), "reason": failed.as_ref().map(|f| f.1.clone()), "gates": gates,
        });
        self.metric_event(v.clone());
        Ok(v)
    }

    async fn promotion_gates(
        &self,
        ctx: &Ctx,
        m: &mut Metric,
        traj: &Trajectory,
        log: &TaskLog,
        gates: &mut Vec<Value>,
    ) -> Result<Option<(String, String)>> {
        gate!(gates, "G1", if matches!(m.basis, Basis::None) { Err("没有口径依据".into()) } else { Ok(()) });
        let value = match (traj.judged, log.verify(traj)) {
            (false, _) => return Ok(record(gates, "G2", Err("来源任务未被独立判定为成功".into()))),
            (true, Err(e)) => return Ok(record(gates, "G2", Err(format!("计算链：{e}")))),
            (true, Ok(v)) => {
                record(gates, "G2", Ok(()));
                v
            }
        };
        gate!(gates, "G3", self.static_gate(ctx, m, &traj.ask).await?);
        gate!(gates, "G4", self.grain_gate(ctx, m, false).await);
        let example = m.examples.first().map(|x| x.sql.clone()).unwrap_or_default();
        gate!(gates, "G5", self.review_gate(ctx, &example).await?);
        let g6 = match log.chain_versions(traj) {
            Ok(v) => {
                let cur = self.deps_for(&v.keys().cloned().collect::<Vec<_>>()).await?;
                if cur == v {
                    self.value_gate(&example, &value, traj.decimals).await
                } else {
                    Err("数据快照已变化，无法复现".into())
                }
            }
            Err(e) => Err(e),
        };
        gate!(gates, "G6", g6);
        let g7 = match metric::compile(m, &traj.ask) {
            Ok(sql) => self.value_gate(&sql, &value, traj.decimals).await,
            Err(e) => Err(format!("{e:#}")),
        };
        gate!(gates, "G7", g7);
        Ok(None)
    }

    /// 维护评测用：直接提交一条给定口径（不经提炼），走 G3、G4、G5 与字段复现（规范 SQL 对判题查询在当前快照上的结果）。
    /// 各组使用同一批口径与同一判题查询，维护对照不受提炼随机性影响；判题查询同时供修复后的 G8 使用。
    pub async fn seed_metric(&self, ctx: &Ctx, mut m: Metric, ask: Ask, decimals: u32, judge: &str) -> Result<Value> {
        m.basis = Basis::Confirmed { by: "maint-bench".into() };
        let sql = metric::compile(&m, &ask)?;
        m.examples = vec![Example { question: format!("{}（学习参数）", m.name), sql }];
        let mut gates = vec![];
        let failed = self.seed_gates(ctx, &mut m, &ask, decimals, judge, &mut gates).await?;
        let key = format!("metric:{}", m.name.trim());
        let fk = self.mfk(ctx, &key);
        let deps = self.deps_for(&m.tables()).await?;
        let guards = vec![grain_check(&m)];
        let mut e = self.new_entry(ctx, &key, Content::Metric(Box::new(m)), deps.clone(), guards);
        // 重新提交（逐写入撤销组的重新提炼）得到新修订号
        e.revision = self.store.get(&fk).map_or(0, |x| x.revision + 1);
        e.status = match &failed {
            None => Status::Valid,
            Some((g, r)) => Status::Candidate(format!("{g}：{r}")),
        };
        self.store.put(&fk, e);
        let evidence = MetricEvidence {
            task: key.clone(),
            ask,
            decimals,
            value: None,
            versions: deps,
            gates: gates.clone(),
            corroborations: 0,
            repaired: false,
            judge: Some(judge.to_string()),
            optimized: 0,
        };
        self.metric_evidence.lock().insert(fk.clone(), evidence);
        let revision = self.store.get(&fk).map_or(0, |x| x.revision);
        Ok(json!({"key": key, "revision": revision, "promoted": failed.is_none(), "failed_gate": failed.as_ref().map(|f| f.0.clone()),
                  "reason": failed.as_ref().map(|f| f.1.clone()), "gates": gates}))
    }

    async fn seed_gates(
        &self,
        ctx: &Ctx,
        m: &mut Metric,
        ask: &Ask,
        decimals: u32,
        judge: &str,
        gates: &mut Vec<Value>,
    ) -> Result<Option<(String, String)>> {
        gate!(gates, "G3", self.static_gate(ctx, m, ask).await?);
        // 条件级维护下准入也复用同一粒度条件在当前版本上的结论（与修复回归相同）
        gate!(gates, "G4", self.grain_gate(ctx, m, self.cfg.cond_reuse).await);
        let example = m.examples.first().map(|x| x.sql.clone()).unwrap_or_default();
        gate!(gates, "G5", self.review_gate(ctx, &example).await?);
        let g7 = match self.vquery(QKind::Metric, judge).await {
            Ok(r) => self.value_gate(&example, &metric::parse_answer(r.cell(0, 0).unwrap_or("NULL")), decimals).await,
            Err(e) => Err(format!("判题查询失败：{e:#}")),
        };
        gate!(gates, "G7", g7);
        Ok(None)
    }

    /// G3：表列存在；关联属于已验证路径且方向一致、包含路径要求的过滤；聚合表达式与过滤只引用口径内的表；
    /// 非时间连接必须从事实表指向一侧；过滤不含题目参数；必需的粒度过滤都在。
    /// 顺带按已验证路径填写关联的键、基数、丢行比例与修订号。
    pub(super) async fn static_gate(&self, ctx: &Ctx, m: &mut Metric, ask: &Ask) -> Result<Gate> {
        macro_rules! bad {
            ($($t:tt)*) => { return Ok(Err(format!($($t)*))) };
        }
        for t in m.tables() {
            if self.cat.table(&t).is_none() {
                bad!("表 {t} 不存在");
            }
            if !ctx.role.allows(&t) {
                bad!("无权访问表 {t}");
            }
        }
        let Some(fact) = self.cat.table(&m.fact) else { bad!("事实表 {} 不存在", m.fact) };
        if m.grain.is_empty() {
            bad!("缺少粒度键");
        }
        if let Some(c) = m.grain.iter().find(|c| fact.col(c).is_none()) {
            bad!("粒度列 {c} 不在表 {}", m.fact);
        }
        let time = m.time.clone();
        if let Some(t) = &time {
            if !matches!(t.grain.as_str(), "day" | "month" | "year") {
                bad!("时间粒度应为 day / month / year：{}", t.grain);
            }
            if t.role.trim().is_empty() {
                bad!("没有写明时间角色");
            }
            if fact.col(&t.fact_col).is_none() {
                bad!("时间键 {} 不在事实表 {}", t.fact_col, m.fact);
            }
            if self.cat.table(&t.dim).and_then(|d| d.col(&t.dim_col)).is_none() {
                bad!("维度列 {}.{} 不存在", t.dim, t.dim_col);
            }
            let on = vec![(t.fact_col.clone(), t.dim_col.clone())];
            match self.verdict(ctx, &m.fact, &t.dim, &on).await?.0 {
                Ok(p) => {
                    if let Some(tm) = m.time.as_mut() {
                        tm.loss_ratio = p.loss_ratio;
                    }
                }
                Err(x) => bad!("时间关联 {}={} 未通过验证：{}", t.fact_col, t.dim_col, x.reason),
            }
            // 提炼器有时把时间关联也写进 joins；规范编译会另加时间关联，重复会使 G7 报“表名被指定多次”
            let flip = vec![(t.dim_col.clone(), t.fact_col.clone())];
            let fact = m.fact.clone();
            m.joins.retain(|j| {
                let tables = (j.left == fact && j.right == t.dim) || (j.left == t.dim && j.right == fact);
                !(tables && (j.on == on || j.on == flip))
            });
        }
        if let Err(e) = metric::check_join_orientation(m) {
            bad!("{e}");
        }
        let mut allowed: BTreeSet<String> = [m.fact.clone()].into_iter().collect();
        for j in m.joins.iter_mut() {
            if self.cat.validate_join(&j.left, &j.right, &j.on).is_err() {
                bad!("关联 {}⋈{} 的列不存在或重复", j.left, j.right);
            }
            let p = match self.verdict(ctx, &j.left, &j.right, &j.on).await?.0 {
                Ok(p) => p,
                Err(x) => bad!("关联 {}⋈{} 不是已验证路径：{}", j.left, j.right, x.reason),
            };
            if p.left != j.left || p.right != j.right {
                bad!("关联方向与已验证路径不一致：多侧应为 {}，一侧应为 {}", p.left, p.right);
            }
            if !covers(&j.filters, &p.filters) {
                bad!("关联 {}⋈{} 缺少已验证路径要求的过滤 {:?}", j.left, j.right, p.filters);
            }
            for (t, f) in &j.filters {
                if t != &j.left && t != &j.right {
                    bad!("关联过滤所在表 {t} 不在该关联中");
                }
                if let Err(e) = metric::check_filter(t, f, time.as_ref(), ask, &self.cat) {
                    bad!("关联过滤 {t}：{e}");
                }
            }
            let jk = join_key(&j.left, &j.right);
            j.revision = self.store.get(&self.fk(ctx, &jk)).map_or(0, |e| e.revision);
            j.key = jk;
            j.cardinality = p.cardinality().to_string();
            j.loss_ratio = p.loss_ratio;
            allowed.insert(j.left.clone());
            allowed.insert(j.right.clone());
        }
        // 提炼器常照抄智能体 SQL 里的表别名，规范 SQL 不起别名：先把别名改写成表名再检查
        m.measure = metric::qualify_aliases(&m.measure, &allowed, &self.cat);
        for (t, f) in m.filters.iter_mut() {
            *f = metric::qualify_aliases(f, &[t.clone()].into_iter().collect(), &self.cat);
        }
        if let Err(e) = metric::check_expr(&m.measure, &allowed, &self.cat) {
            bad!("聚合表达式：{e}");
        }
        for (t, f) in &m.filters {
            if !allowed.contains(t) {
                bad!("过滤所在表 {t} 不在口径中");
            }
            if let Err(e) = metric::check_filter(t, f, time.as_ref(), ask, &self.cat) {
                bad!("过滤 {t}：{e}");
            }
        }
        for t in &allowed {
            if let Some(Entry { content: Content::Profile(g), status: Status::Valid, .. }) =
                self.store.get(&self.fk(ctx, &format!("grain:{t}")))
            {
                let f = g["filter"].as_str().unwrap_or_default().to_string();
                let has = |x: Option<&String>| x.is_some_and(|x| sqlscan::contains_filter(x, &f));
                if !has(m.filters.get(t)) && !m.joins.iter().any(|j| has(j.filters.get(t))) {
                    bad!("表 {t} 需要粒度过滤 {f}");
                }
            }
        }
        Ok(Ok(()))
    }

    /// G4：事实表在粒度键上唯一（带口径过滤）。`reuse`：同一条件在当前版本上已有结论就复用（条件级维护的修复回归用）；
    /// 晋升时各组都重新执行。
    pub(super) async fn grain_gate(&self, ctx: &Ctx, m: &Metric, reuse: bool) -> Gate {
        let c = grain_check(m);
        let r = if reuse {
            self.cond_check(ctx, &c, QKind::Metric).await.map(|x| x.0)
        } else {
            self.exec_check(ctx, &c, QKind::Metric).await.map(|x| x.0)
        };
        match r {
            Ok(o) if o.pass => Ok(()),
            Ok(o) => Err(format!("{}：{}", c.describe(), outcome_text(&c, &o))),
            Err(e) => Err(format!("执行失败：{e:#}")),
        }
    }

    /// 条件结论复用：读到的表在当前版本上已有同一条件的有效结论（来自其他定义、关联守卫或更早的检查）就复用；
    /// 没有同一条件时，已通过的更弱条件（同表同过滤、键列更少的键唯一性）蕴含本条件通过；都没有才执行（相同检查在途合并）。
    /// 返回结论与来源：reused / implied / executed / merged。
    pub(super) async fn cond_check(&self, ctx: &Ctx, c: &Check, kind: QKind) -> Result<(Outcome, &'static str)> {
        let deps = self.deps_for(&c.tables()).await?;
        let known: Vec<(Check, Outcome)> = self
            .store
            .scan(&self.fk(ctx, "check:"))
            .into_iter()
            .filter(|(_, x)| x.status == Status::Valid && x.deps == deps)
            .filter_map(|(_, x)| match x.content {
                Content::CheckResult { check, outcome } => Some((check, outcome)),
                _ => None,
            })
            .collect();
        if let Some((_, o)) = known.iter().find(|(k, _)| same_cond(k, c)) {
            return Ok((o.clone(), "reused"));
        }
        if let Some((_, o)) = known.iter().find(|(k, o)| o.pass && implies(k, c)) {
            return Ok((o.clone(), "implied"));
        }
        let (o, merged) = self.exec_check(ctx, c, kind).await?;
        Ok((o, if merged { "merged" } else { "executed" }))
    }

    /// G5：示例是单条只读查询，并通过 run_sql 的执行前审查。
    pub(super) async fn review_gate(&self, ctx: &Ctx, sql: &str) -> Result<Gate> {
        let s = sql.trim().trim_end_matches(';').trim();
        let low = s.to_lowercase();
        if !(low.starts_with("select") || low.starts_with("with")) || s.contains(';') {
            return Ok(Err("示例不是单条只读查询".into()));
        }
        let tables: Vec<String> = sqlscan::tables(s, &self.cat).into_iter().collect();
        if let Err(e) = self.allowed(ctx, &tables.iter().map(String::as_str).collect::<Vec<_>>()) {
            return Ok(Err(format!("{e:#}")));
        }
        Ok(match self.review_sql(ctx, s, &tables).await? {
            None => Ok(()),
            Some(rej) => Err(format!("审查拦下：{}", rej["reason"].as_str().unwrap_or_default())),
        })
    }

    /// 执行 SQL，第一行须有一个单元格在答案精度上等于 `expect`（示例 SQL 常把中间量与结果放在同一行；
    /// 规范 SQL 只有一列）；执行失败算不通过。
    /// G8 的学习时快照版本：参照查询与替代修订在同一个只读事务里执行，数据是学习时快照——单独的快照库
    /// （`schema` 为空），或同一库里保存学习时数据的模式（以它为 search_path）。
    pub(super) async fn learned_snapshot_gate(&self, db: &crate::db::Db, schema: Option<&str>, reference: &str, sql: &str, decimals: u32) -> Gate {
        let run = async {
            let snap = db.snapshot().await?;
            if let Some(schema) = schema {
                snap.query(QKind::Metric, &format!("set local search_path to \"{schema}\"")).await?;
            }
            let r = snap.query(QKind::Metric, reference).await;
            let c = snap.query(QKind::Metric, sql).await;
            snap.commit().await?;
            Ok::<_, anyhow::Error>((r, c))
        };
        match run.await {
            Err(e) => Err(format!("学习时快照不可用：{e:#}")),
            Ok((Err(e), _)) => Err(format!("参照查询在学习时快照上失败：{e:#}")),
            Ok((_, Err(e))) => Err(format!("替代修订在学习时快照上执行失败：{e:#}")),
            Ok((Ok(r), Ok(c))) => {
                let expect = metric::parse_answer(r.cell(0, 0).unwrap_or("NULL"));
                match c.rows.first() {
                    None => Err("学习时快照上结果为空".into()),
                    Some(row) if row.iter().flatten().any(|v| metric::same_value(&metric::parse_answer(v), &expect, decimals)) => Ok(()),
                    Some(_) => Err(format!("学习时快照上结果 {} 与参照 {expect:?} 不一致", c.cell(0, 0).unwrap_or("NULL"))),
                }
            }
        }
    }

    async fn value_gate(&self, sql: &str, expect: &Answer, decimals: u32) -> Gate {
        match self.vquery(QKind::Metric, sql).await {
            Err(e) => Err(format!("执行失败：{e:#}")),
            Ok(r) => match r.rows.first() {
                None => Err("结果为空".into()),
                Some(row) if row.iter().flatten().any(|c| metric::same_value(&metric::parse_answer(c), expect, decimals)) => Ok(()),
                Some(_) => Err(format!("结果 {} 与期望 {expect:?} 不一致", r.cell(0, 0).unwrap_or("NULL"))),
            },
        }
    }

    // ───────────────────────── 查找、守护与执行端检查 ─────────────────────────

    /// 工具 find_metric：按名称或别名匹配本范围内的指标经验，经守护后返回有效条目。
    pub async fn find_metric(&self, ctx: &Ctx, query: &str, tables: &[String]) -> Result<Value> {
        let q = query.trim().to_lowercase();
        let prefix = format!("{}|metric:", scope_prefix(self.cfg.metric_scope, ctx));
        let (mut hits, mut unavailable, mut found) = (vec![], vec![], vec![]);
        for (fk, e) in self.store.scan(&prefix) {
            let Some(m) = metric_of(&e) else { continue };
            // 从未晋升的候选不对外提供，也不暴露
            if matches!(e.status, Status::Candidate(_)) && !self.is_repaired(&fk) {
                continue;
            }
            let names: Vec<String> =
                std::iter::once(&m.name).chain(&m.aliases).map(|n| n.trim().to_lowercase()).filter(|n| !n.is_empty()).collect();
            let name_ok = !q.is_empty() && names.iter().any(|n| n.contains(&q) || q.contains(n.as_str()));
            let table_ok = tables.is_empty() || m.tables().iter().any(|t| tables.contains(t));
            if !name_ok || !table_ok {
                continue;
            }
            if hits.len() + unavailable.len() >= FIND_BUDGET {
                break;
            }
            match self.metric_check(ctx, &fk).await? {
                Checked::Valid(e) => {
                    self.store.update(&fk, |x| {
                        x.hits += 1;
                        x.consumers.insert(ctx.agent.clone());
                    });
                    found.push((e.key.clone(), e.revision));
                    hits.push(view(&e));
                }
                Checked::Unavailable(e, r) => unavailable.push(json!({"key": e.key, "revision": e.revision, "status": r})),
                Checked::Missing => {}
            }
        }
        self.note_find(ctx, &found);
        let mut v = json!({"metrics": hits, "ambiguous": hits.len() > 1});
        if !unavailable.is_empty() {
            v["unavailable"] = json!(unavailable);
        }
        if hits.is_empty() {
            v["note"] = json!("没有匹配的已验证指标口径");
        }
        Ok(v)
    }

    /// 查找时的守护。依赖表没有变化直接返回；有变化时按 `metric_maint` 维护一次。
    /// 同一定义、同一依赖版本的维护在途合并：并发的使用者等同一个结论，不重复撤销与修复。
    async fn metric_check(&self, ctx: &Ctx, fk: &str) -> Result<Checked> {
        let Some(e) = self.store.get(fk) else { return Ok(Checked::Missing) };
        if metric_of(&e).is_none() || !e.deps.keys().all(|t| ctx.role.allows(t)) {
            return Ok(Checked::Missing);
        }
        if let Some(r) = blocked(&e.status) {
            // 正在维护（已撤销、修复回归中）：加入那次维护，结束后读最新状态（维护刚结束时也重读一次）
            if self.cfg.wait_repair {
                let pending = self.maint_inflight.lock().get(fk).cloned();
                if let Some(key) = pending {
                    self.flight_v.run(self.cfg.singleflight, &key, || async { Ok(Value::Null) }).await?;
                    self.metric_event(json!({"event": "repair_waited", "key": e.key, "revision": e.revision, "agent": ctx.agent}));
                }
                return Ok(match self.store.get(fk) {
                    Some(x) if x.status == Status::Valid => Checked::Valid(x),
                    Some(x) => {
                        let r = blocked(&x.status).unwrap_or_default();
                        Checked::Unavailable(x, r)
                    }
                    None => Checked::Missing,
                });
            }
            return Ok(Checked::Unavailable(e, r));
        }
        if self.cfg.metric_maint == Maint::Off {
            return Ok(Checked::Valid(e));
        }
        let cur = self.versions().await?;
        if e.deps.iter().all(|(t, v)| cur.get(t) == Some(v)) {
            return Ok(Checked::Valid(e));
        }
        let key = format!("maint:{fk}@{}", ver_sig(&e.deps));
        self.maint_inflight.lock().insert(fk.to_string(), key.clone());
        let r = self
            .flight_v
            .run(self.cfg.singleflight, &key, || crate::timing::measure("maintenance", self.maintain(ctx, fk, &e, &cur)))
            .await;
        {
            let mut m = self.maint_inflight.lock();
            if m.get(fk) == Some(&key) {
                m.remove(fk);
            }
        }
        let (_, merged) = r?;
        if merged {
            self.metric_event(json!({"event": "maintenance_merged", "key": e.key, "revision": e.revision, "agent": ctx.agent}));
        }
        // 修复当场回归通过时这里读到的是新修订，本次请求即可使用
        Ok(match self.store.get(fk) {
            Some(x) if x.status == Status::Valid => Checked::Valid(x),
            Some(x) => {
                let r = blocked(&x.status).unwrap_or_default();
                Checked::Unavailable(x, r)
            }
            None => Checked::Missing,
        })
    }

    /// 依赖表有写入后的一次维护。结果分开记录：待验证后通过（refreshed）；条件不成立而正式撤销，随后受限修复
    /// （repaired / revoked）；逐写入撤销（revoked_on_write，只能重新提炼）。每个条件记下处理方式：
    /// skipped（读到的表未变化）、reused（同一版本已有结论）、executed、merged、forced（定义级强制重跑）、checked（交给关联经验判断）。
    async fn maintain(&self, ctx: &Ctx, fk: &str, e: &Entry, cur: &HashMap<String, TableVersion>) -> Result<Value> {
        let Some(m) = metric_of(e).cloned() else { return Ok(Value::Null) };
        // 读到旧条目之后、进入维护之前，别人已经维护完（刷新、撤销或修复）：不再重做，调用方重新读取最新状态
        if !self.store.get(fk).is_some_and(|x| x.revision == e.revision && x.deps == e.deps && x.status == Status::Valid) {
            let v = json!({"event": "maintenance_superseded", "key": e.key, "revision": e.revision, "agent": ctx.agent});
            self.metric_event(v.clone());
            return Ok(v);
        }
        let t0 = Instant::now();
        let before = self.db.meter.snap();
        let policy = self.cfg.metric_maint;
        let changed: Vec<String> = e.deps.iter().filter(|(t, v)| cur.get(*t) != Some(*v)).map(|(t, _)| t.clone()).collect();
        let mut conds = vec![];
        let breach = match policy {
            Maint::Off => None,
            Maint::Revoke => Some(Breach::Write(format!("依赖表 {} 有写入（逐写入撤销）", changed.join("、")))),
            Maint::Schema => schema_breach(e, &metric::columns(&m, &self.cat), cur, &changed),
            Maint::Definition | Maint::Condition => self.metric_breach(ctx, &m, e, cur, &changed, &mut conds).await?,
        };
        let outcome = match breach {
            None => {
                let deps: BTreeMap<String, TableVersion> =
                    e.deps.keys().filter_map(|t| cur.get(t).map(|v| (t.clone(), v.clone()))).collect();
                self.store.update(fk, |x| x.deps = deps);
                "refreshed"
            }
            Some(b) => {
                let reason = b.reason();
                let reextract = matches!(b, Breach::Write(_));
                self.revoke(fk, e, reason.clone(), true);
                self.metric_event(json!({"event": "revoked", "key": e.key, "revision": e.revision, "reason": reason, "agent": ctx.agent,
                                         "policy": policy.name(), "reextract": reextract}));
                if reextract {
                    "revoked_on_write"
                } else {
                    crate::timing::measure("repair", self.restricted_repair(ctx, fk, e, &m, b)).await?;
                    if self.store.get(fk).is_some_and(|x| x.status == Status::Valid) {
                        "repaired"
                    } else {
                        "revoked"
                    }
                }
            }
        };
        let d = crate::db::diff(&before, &self.db.meter.snap());
        let v = json!({
            "event": "maintenance", "policy": policy.name(), "key": e.key, "revision": e.revision, "agent": ctx.agent,
            "changed": changed, "conditions": conds, "outcome": outcome, "wall_ms": t0.elapsed().as_secs_f64() * 1000.0,
            // 计量取自全局计数，并发时会混入其他请求；维护评测按变化事件整体计量
            "db": {"queries": d.queries, "ms": d.db_ms, "by_kind": d.by_kind},
        });
        self.metric_event(v.clone());
        Ok(v)
    }

    /// 定义级与条件级重验共用的条件判断，按关联、时间关联、粒度的顺序，遇到第一个不成立的条件即返回。
    /// 定义级（Definition）：全部条件都重跑，关联与时间关联经验的守卫也强制重跑。
    /// 条件级（Condition）：只查读到了变化表的条件；关联与时间关联交给关联经验，由它按守卫涉及的表决定是否重跑；
    /// 关联经验在别处被修订或撤销（修订号变化、路径消失、过滤不再覆盖）时按待验证处理。开启 `cond_reuse` 时，
    /// 粒度条件与关联守卫复用同一版本上已有的结论。
    async fn metric_breach(
        &self,
        ctx: &Ctx,
        m: &Metric,
        e: &Entry,
        cur: &HashMap<String, TableVersion>,
        changed: &[String],
        conds: &mut Vec<Value>,
    ) -> Result<Option<Breach>> {
        if let Some(b) = schema_breach(e, &metric::columns(m, &self.cat), cur, changed) {
            return Ok(Some(b));
        }
        let force = self.cfg.metric_maint == Maint::Definition;
        let action = if force { "forced" } else { "checked" };
        let untouched = |tables: Option<Vec<String>>| tables.filter(|ts| !force && !ts.iter().any(|t| changed.contains(t)));
        for (idx, j) in m.joins.iter().enumerate() {
            let label = format!("关联 {}⋈{}", j.left, j.right);
            if let Some(ts) = untouched(self.join_cond(ctx, &j.left, &j.right, &j.on, Some(j.revision), &j.filters)) {
                conds.push(json!({"cond": label, "tables": ts, "action": "skipped"}));
                continue;
            }
            let (r, src) = self.verdict_with(ctx, &j.left, &j.right, &j.on, force).await?;
            let breach = match r {
                Ok(p) if p.left == j.left && p.right == j.right => {
                    if covers(&j.filters, &p.filters) {
                        None
                    } else {
                        let reason = format!("关联 {}⋈{} 的已验证路径现在要求过滤 {:?}", j.left, j.right, p.filters);
                        Some(Breach::Join { idx, path: Some(p), reason })
                    }
                }
                Ok(p) => {
                    Some(Breach::Join { idx, path: None, reason: format!("关联 {}⋈{} 的多侧已变为 {}", j.left, j.right, p.left) })
                }
                Err(x) => {
                    Some(Breach::Join { idx, path: None, reason: format!("关联 {}⋈{} 不再成立：{}", j.left, j.right, x.reason) })
                }
            };
            conds.push(json!({"cond": label, "action": action, "source": src, "pass": breach.is_none()}));
            if breach.is_some() {
                return Ok(breach);
            }
        }
        if let Some(t) = &m.time {
            let on = vec![(t.fact_col.clone(), t.dim_col.clone())];
            let label = format!("时间关联 {}⋈{}", m.fact, t.dim);
            if let Some(ts) = untouched(self.join_cond(ctx, &m.fact, &t.dim, &on, None, &BTreeMap::new())) {
                conds.push(json!({"cond": label, "tables": ts, "action": "skipped"}));
            } else {
                let (r, src) = self.verdict_with(ctx, &m.fact, &t.dim, &on, force).await?;
                conds.push(json!({"cond": label, "action": action, "source": src, "pass": r.is_ok()}));
                if let Err(x) = r {
                    return Ok(Some(Breach::Time(format!("时间关联不再成立：{}", x.reason))));
                }
            }
            // 日期键范围修订：日期键必须仍按月连续，否则范围谓词不再等价于维度连接（不在受限修复范围）
            if t.strategy == TimeStrategy::KeyRange {
                let c = time_contiguity_check(t);
                let label = format!("日期键连续 {}", t.dim);
                if !force && !changed.contains(&t.dim) {
                    conds.push(json!({"cond": label, "tables": [t.dim.clone()], "action": "skipped"}));
                } else {
                    let (o, how) = if self.cfg.cond_reuse && !force {
                        self.cond_check(ctx, &c, QKind::Metric).await?
                    } else {
                        let (o, merged) = self.exec_check(ctx, &c, QKind::Metric).await?;
                        (o, if merged { "merged" } else { "executed" })
                    };
                    let ms = if how == "executed" { o.ms } else { 0.0 };
                    conds.push(json!({"cond": label, "tables": [t.dim.clone()], "action": how, "pass": o.pass, "ms": ms}));
                    if !o.pass {
                        return Ok(Some(Breach::Time(format!("日期键不再按月连续：{}", outcome_text(&c, &o)))));
                    }
                }
            }
            // 覆盖：每条事实都应能归入某个期间。关联不上时间维度的行占比超过准入基线即不成立
            if let Some(c) = coverage_check(m) {
                let label = format!("覆盖 {}⋈{}", m.fact, t.dim);
                if !force && !c.tables().iter().any(|x| changed.contains(x)) {
                    conds.push(json!({"cond": label, "tables": c.tables(), "action": "skipped"}));
                } else {
                    let (o, how) = if self.cfg.cond_reuse && !force {
                        self.cond_check(ctx, &c, QKind::Metric).await?
                    } else {
                        let (o, merged) = self.exec_check(ctx, &c, QKind::Metric).await?;
                        (o, if merged { "merged" } else { "executed" })
                    };
                    let loss = loss_of(&o);
                    let pass = loss <= t.loss_ratio + COVERAGE_TOLERANCE;
                    let ms = if how == "executed" { o.ms } else { 0.0 };
                    conds.push(json!({"cond": label, "tables": c.tables(), "action": how, "pass": pass,
                                      "loss": loss, "baseline": t.loss_ratio, "ms": ms}));
                    if !pass {
                        return Ok(Some(Breach::Coverage(format!(
                            "{} 中关联不上 {} 的行占比从 {:.2}% 升至 {:.2}%，部分事实无法归入期间",
                            m.fact,
                            t.dim,
                            t.loss_ratio * 100.0,
                            loss * 100.0
                        ))));
                    }
                }
            }
        }
        let c = grain_check(m);
        let label = format!("粒度 {}", c.describe());
        if !force && !changed.contains(&m.fact) {
            conds.push(json!({"cond": label, "tables": [m.fact], "action": "skipped"}));
            return Ok(None);
        }
        let (o, how) = if self.cfg.cond_reuse && !force {
            self.cond_check(ctx, &c, QKind::Metric).await?
        } else {
            let (o, merged) = self.exec_check(ctx, &c, QKind::Metric).await?;
            (o, if merged { "merged" } else { "executed" })
        };
        let ms = if how == "executed" { o.ms } else { 0.0 };
        conds.push(json!({"cond": label, "tables": [m.fact], "action": how, "pass": o.pass, "ms": ms}));
        if !o.pass {
            return Ok(Some(Breach::Grain(format!("粒度守卫失败：{}，{}", c.describe(), outcome_text(&c, &o)))));
        }
        Ok(None)
    }

    /// 关联条件读到的表：已验证路径的守卫（唯一侧的键唯一性）涉及的表。关联经验不是有效状态、修订号与引用时不同、
    /// 找不到同方向的同一路径，或路径要求的过滤没有被引用覆盖时返回 None，按待验证处理。只读经验库，不访问数据库。
    fn join_cond(
        &self,
        ctx: &Ctx,
        left: &str,
        right: &str,
        on: &On,
        revision: Option<u32>,
        filters: &BTreeMap<String, String>,
    ) -> Option<Vec<String>> {
        let e = self.store.get(&self.fk(ctx, &join_key(left, right)))?;
        if e.status != Status::Valid || revision.is_some_and(|r| r != e.revision) {
            return None;
        }
        let Content::Join { paths, .. } = &e.content else { return None };
        let p = paths.iter().find(|p| same_on(&p.on, on) && p.left == left && p.right == right)?;
        if !covers(filters, &p.filters) {
            return None;
        }
        let tables: BTreeSet<String> = p.guards().iter().flat_map(|g| g.tables()).collect();
        Some(tables.into_iter().collect())
    }

    /// 修复复用：同一张表、同一组键在当前版本上已由粒度修复找到过滤（经验库里的 grain 条目），直接采用。
    pub(super) async fn known_grain_filter(&self, ctx: &Ctx, table: &str, cols: &[String]) -> Result<Option<String>> {
        let Some(e) = self.store.get(&self.fk(ctx, &format!("grain:{table}"))) else { return Ok(None) };
        let Content::Profile(g) = &e.content else { return Ok(None) };
        let key: BTreeSet<String> = serde_json::from_value(g["key"].clone()).unwrap_or_default();
        let deps = self.deps_for(&[table.to_string()]).await?;
        if e.status != Status::Valid || e.deps != deps || key != cols.iter().cloned().collect::<BTreeSet<_>>() {
            return Ok(None);
        }
        Ok(g["filter"].as_str().map(str::to_string))
    }

    /// 写入通知到达后立即维护全部有效的指标条目（逐写入撤销组在此撤销；其他组默认在首次使用时维护）。
    /// 返回每条的完整键、来源任务与维护后的状态。
    pub async fn sweep_metrics(&self, ctx: &Ctx) -> Result<Vec<Value>> {
        let mut out = vec![];
        for (fk, e, ev) in self.metric_entries() {
            if e.status != Status::Valid {
                continue;
            }
            let after = self.check_view(ctx, &fk).await?;
            out.push(json!({"full_key": fk, "key": e.key, "task": ev.map(|x| x.task), "before": e.revision, "after": after}));
        }
        Ok(out)
    }

    /// 按键使用一条指标经验，与执行端引用检查走同一条守护路径（维护评测用）。返回状态、修订号与口径字段。
    pub async fn use_metric(&self, ctx: &Ctx, key: &str) -> Result<Value> {
        self.check_view(ctx, &self.mfk(ctx, key)).await
    }

    async fn check_view(&self, ctx: &Ctx, fk: &str) -> Result<Value> {
        Ok(match self.metric_check(ctx, fk).await? {
            Checked::Valid(e) => json!({"status": "valid", "revision": e.revision, "metric": metric_of(&e)}),
            Checked::Unavailable(e, r) => json!({"status": "unavailable", "revision": e.revision, "reason": r}),
            Checked::Missing => json!({"status": "missing"}),
        })
    }

    /// 受限修复只处理两种情况：事实表粒度守卫失败且 repair_grain 找到过滤；关联经重验证后只新增了过滤。
    /// 修复结果是新的候选（修订号加一），示例改为由口径字段编译的规范 SQL，当场回归（G3/G4/G5/G8）通过才恢复有效。
    /// 开启条件结论复用时，同一张表、同一组键在当前版本上已有粒度修复结论就直接采用，不再搜索。
    async fn restricted_repair(&self, ctx: &Ctx, fk: &str, old: &Entry, m: &Metric, b: Breach) -> Result<()> {
        let mut m2 = m.clone();
        let change = match b {
            Breach::Grain(_) => {
                let known = if self.cfg.cond_reuse { self.known_grain_filter(ctx, &m.fact, &m.grain).await? } else { None };
                let found = match known {
                    Some(f) => {
                        self.metric_event(
                            json!({"event": "repair_reused", "key": old.key, "revision": old.revision, "table": m.fact, "filter": f}),
                        );
                        Some(f)
                    }
                    None => self.repair_grain(ctx, &m.fact, &m.grain).await?,
                };
                match found {
                    Some(f) => {
                        m2.filters.insert(m.fact.clone(), f.clone());
                        format!("{} 增加粒度过滤 {f}", m.fact)
                    }
                    None => {
                        let reason = match self.ambiguous_repair(&m.fact) {
                            Some(c) => format!("多个过滤都能恢复唯一性，结构上分不出哪个对：{}", c.join("；")),
                            None => "没有找到能恢复唯一性的过滤".into(),
                        };
                        self.metric_event(json!({"event": "repair_failed", "key": old.key, "revision": old.revision, "reason": reason}));
                        return Ok(());
                    }
                }
            }
            Breach::Join { idx, path: Some(p), .. } if covers(&p.filters, &m.joins[idx].filters) => {
                let rev = self.store.get(&self.fk(ctx, &join_key(&p.left, &p.right))).map_or(0, |e| e.revision);
                let j = &mut m2.joins[idx];
                j.filters.extend(p.filters.clone());
                j.cardinality = p.cardinality().to_string();
                j.loss_ratio = p.loss_ratio;
                j.revision = rev;
                format!("关联 {}⋈{} 采用重验证路径的过滤 {:?}", j.left, j.right, p.filters)
            }
            other => {
                self.metric_event(json!({"event": "repair_skipped", "key": old.key, "revision": old.revision,
                                         "reason": format!("不属于受限修复范围：{}", other.reason())}));
                return Ok(());
            }
        };
        let ask = self.metric_evidence.lock().get(fk).map(|x| x.ask);
        if let Some(ask) = ask {
            if let Ok(sql) = metric::compile(&m2, &ask) {
                let question = m2.examples.first().map(|x| x.question.clone()).unwrap_or_default();
                m2.examples = vec![Example { question, sql }];
            }
        }
        let deps = self.deps_for(&m2.tables()).await?;
        let guards = vec![grain_check(&m2)];
        let mut e = self.new_entry(ctx, &old.key, Content::Metric(Box::new(m2)), deps, guards);
        e.revision = old.revision + 1;
        e.status = Status::Candidate("修复待回归验证".into());
        e.created_by = old.created_by.clone();
        e.consumers = old.consumers.clone();
        self.store.put(fk, e);
        if let Some(ev) = self.metric_evidence.lock().get_mut(fk) {
            ev.repaired = true;
        }
        self.metric_event(json!({"event": "repair_candidate", "key": old.key, "revision": old.revision + 1, "change": change}));
        self.regress(ctx, fk).await
    }

    /// 修复候选的回归：G3、G4、G5 与 G8 全部通过才恢复有效，否则保持候选（不可用）。
    async fn regress(&self, ctx: &Ctx, fk: &str) -> Result<()> {
        let (Some(e), Some(ev)) = (self.store.get(fk), self.metric_evidence.lock().get(fk).cloned()) else { return Ok(()) };
        let Some(mut m) = metric_of(&e).cloned() else { return Ok(()) };
        let mut gates = vec![];
        let failed = self.repair_gates(ctx, &mut m, &ev, &mut gates).await?;
        let deps = self.deps_for(&m.tables()).await?;
        let status = match &failed {
            None => Status::Valid,
            Some((gate, r)) => Status::Candidate(format!("{gate}：{r}")),
        };
        self.store.update(fk, |x| {
            x.status = status;
            x.deps = deps;
            x.content = Content::Metric(Box::new(m));
        });
        if let Some(x) = self.metric_evidence.lock().get_mut(fk) {
            x.gates.extend(gates.clone());
        }
        self.metric_event(json!({
            "event": if failed.is_none() { "repair_promoted" } else { "repair_rejected" },
            "key": e.key, "revision": e.revision,
            "failed_gate": failed.as_ref().map(|f| f.0.clone()), "reason": failed.as_ref().map(|f| f.1.clone()), "gates": gates,
        }));
        Ok(())
    }

    /// 工具 run_sql 的执行端检查：声明的指标引用须仍有效且修订号一致。不能证明 SQL 遵循了口径，原有审查照常执行。
    pub(super) async fn check_metric_refs(&self, ctx: &Ctx, refs: &[(String, u32)]) -> Result<Option<Value>> {
        for (key, rev) in refs {
            let fk = self.mfk(ctx, key);
            let problem = match self.metric_check(ctx, &fk).await? {
                Checked::Valid(e) if e.revision == *rev => None,
                // 被等价且更省的修订替代的旧修订：仍然正确，宽限可用，附通知
                Checked::Valid(e) if self.opt_prev.lock().get(&fk) == Some(rev) => {
                    self.notices.lock().entry(ctx.agent.clone()).or_default().push(format!(
                        "指标经验 {key} 已发布等价且更省的修订 r{}（你引用的 r{rev} 仍可用），建议重新调用 find_metric 改用新修订",
                        e.revision
                    ));
                    None
                }
                Checked::Valid(e) => Some(format!("指标经验 {key} 已修订为 r{}（你引用的是 r{rev}），请重新调用 find_metric", e.revision)),
                Checked::Unavailable(_, r) => Some(format!("指标经验 {key} 当前不可用：{r}")),
                Checked::Missing => Some(format!("指标经验 {key} 不存在或无权访问")),
            };
            if let Some(reason) = problem {
                self.metric_event(json!({"event": "ref_rejected", "key": key, "revision": rev, "agent": ctx.agent, "reason": reason}));
                return Ok(Some(json!({"rejected": true, "reason": reason, "metric": key})));
            }
        }
        Ok(None)
    }

    /// 绑定快照执行：在一个可重复读的只读事务里，先读事务性版本，逐条核对所引用修订的条件（同一条件在相同版本上
    /// 已有结论就直接用，否则在该快照上执行检查），全部成立后在同一快照上执行业务 SQL。版本由写入事务内的触发器
    /// 维护，所以快照读到的版本恰好对应它能看到的数据：核对与执行之间提交的写入对本次执行不可见。
    /// 任一条件不成立即放弃快照并拒绝，同时让下一次请求重读版本，后续使用按常规维护处理。
    pub(super) async fn run_bound(&self, ctx: &Ctx, sql: &str, refs: &[(String, u32)]) -> Result<Value> {
        let mut conds: Vec<(Check, Option<f64>)> = vec![];
        for (key, _) in refs {
            let Some(e) = self.store.get(&self.mfk(ctx, key)) else { continue };
            for c in metric_of(&e).map(bound_conditions).unwrap_or_default() {
                if !conds.iter().any(|(k, _)| same_cond(k, &c.0) || k.key() == c.0.key()) {
                    conds.push(c);
                }
            }
        }
        let snap = self.db.snapshot().await?;
        let vers = catalog::tx_versions(&snap.query(QKind::Metric, catalog::TX_VERSIONS_SQL).await?);
        let (mut run, mut reused) = (0u32, 0u32);
        for (c, baseline) in &conds {
            // 同一条件在相同事务性版本上的结论（来自更早的快照，或前后版本一致的维护检查）直接用
            let vkey = snap_key(c, &vers);
            let known = self.snap_verdicts.lock().get(&vkey).cloned();
            let o = match known {
                Some(o) => {
                    reused += 1;
                    inc(&self.stats.snapshot_checks_reused);
                    o
                }
                None => {
                    // 同版本的快照看到的这些表的数据相同，并发的同一检查只在其中一个快照里执行，结果分给其余请求
                    let (o, merged) = self
                        .flight_c
                        .run(self.cfg.singleflight, &format!("snap:{vkey}"), || async {
                            let t = Instant::now();
                            let o = c.eval(&snap.query(QKind::Metric, &c.sql()).await?, t.elapsed().as_secs_f64() * 1000.0);
                            self.snap_verdicts.lock().insert(vkey.clone(), o.clone());
                            Ok(o)
                        })
                        .await?;
                    if merged {
                        reused += 1;
                        inc(&self.stats.snapshot_checks_reused);
                    } else {
                        run += 1;
                        inc(&self.stats.snapshot_checks_run);
                    }
                    o
                }
            };
            let pass = match baseline {
                Some(b) => loss_of(&o) <= *b,
                None => o.pass,
            };
            if !pass {
                drop(snap);
                inc(&self.stats.snapshot_rejections);
                self.invalidate_versions();
                let reason = format!("执行快照上条件不成立：{}", c.describe());
                self.metric_event(
                    json!({"event": "snapshot_rejected", "refs": refs, "agent": ctx.agent, "reason": reason, "versions": vers}),
                );
                return Ok(json!({"rejected": true, "reason": reason, "metric": refs.first().map(|r| r.0.clone())}));
            }
        }
        if self.cfg.exec_pause_ms > 0 {
            tokio::time::sleep(std::time::Duration::from_millis(self.cfg.exec_pause_ms)).await;
        }
        let v = snap.query(QKind::Exec, sql).await?.to_json(self.cfg.max_rows);
        snap.commit().await?;
        Ok(json!({"result": v, "source": "snapshot", "snapshot": {"versions": vers, "checks_run": run, "checks_reused": reused}}))
    }

    async fn repair_gates(
        &self,
        ctx: &Ctx,
        m: &mut Metric,
        ev: &MetricEvidence,
        gates: &mut Vec<Value>,
    ) -> Result<Option<(String, String)>> {
        gate!(gates, "G3", self.static_gate(ctx, m, &ev.ask).await?);
        gate!(gates, "G4", self.grain_gate(ctx, m, self.cfg.cond_reuse).await);
        let example = m.examples.first().map(|x| x.sql.clone()).unwrap_or_default();
        gate!(gates, "G5", self.review_gate(ctx, &example).await?);
        // G8：规范 SQL 按学习题参数执行，与参照查询在同一份数据上的结果比较；数据默认是当前快照，
        // 配置了学习时快照时两者都在学习时快照上执行
        let g8 = match (&ev.judge, metric::compile(m, &ev.ask)) {
            (None, _) => Err("没有学习题判题查询，需业务方确认".into()),
            (_, Err(e)) => Err(format!("{e:#}")),
            (Some(judge), Ok(sql)) => match (&self.learn_db, &self.cfg.g8_snapshot) {
                (Some(ldb), _) => self.learned_snapshot_gate(ldb, None, judge, &sql, ev.decimals).await,
                (None, Some(schema)) => self.learned_snapshot_gate(&self.db, Some(schema), judge, &sql, ev.decimals).await,
                _ if self.cfg.g8_snapshot_db => Err("配置了学习时快照库，但没有连接".into()),
                (None, None) => match self.vquery(QKind::Metric, judge).await {
                    Ok(r) => {
                        let expect = metric::parse_answer(r.cell(0, 0).unwrap_or("NULL"));
                        self.value_gate(&sql, &expect, ev.decimals).await
                    }
                    Err(e) => Err(format!("判题查询失败：{e:#}")),
                },
            },
        };
        gate!(gates, "G8", g8);
        Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ku(table: &str, cols: &[&str], filter: Option<&str>) -> Check {
        Check::KeyUnique { table: table.into(), cols: cols.iter().map(|c| c.to_string()).collect(), filter: filter.map(str::to_string) }
    }

    #[test]
    fn same_condition_ignores_column_order_and_filter_spacing() {
        assert!(same_cond(&ku("t", &["a", "b"], Some("s = '完成'")), &ku("t", &["b", "a"], Some("S='完成'"))));
        assert!(!same_cond(&ku("t", &["a", "b"], None), &ku("t", &["a"], None)));
        assert!(!same_cond(&ku("t", &["a"], None), &ku("u", &["a"], None)));
        assert!(!same_cond(&ku("t", &["a"], None), &ku("t", &["a"], Some("s = '完成'"))));
        assert!(!same_cond(&ku("t", &["a"], Some("s = 'ABC'")), &ku("t", &["a"], Some("s = 'abc'"))));
        assert!(!same_cond(&ku("t", &["a"], Some("s = 'A B'")), &ku("t", &["a"], Some("s = 'AB'"))));
    }

    #[test]
    fn unique_subset_key_implies_unique_superset_key() {
        assert!(implies(&ku("t", &["a", "b"], None), &ku("t", &["c", "a", "b"], None)));
        assert!(!implies(&ku("t", &["a", "b", "c"], None), &ku("t", &["a", "b"], None)));
        assert!(!implies(&ku("t", &["a"], Some("x = 1")), &ku("t", &["a", "b"], None)));
        assert!(!implies(&ku("t", &["a"], None), &ku("u", &["a", "b"], None)));
        assert!(!implies(&ku("t", &["a"], Some("s = 'ABC'")), &ku("t", &["a", "b"], Some("s = 'abc'"))));
        assert!(!implies(&ku("t", &["a"], Some("s = 'A B'")), &ku("t", &["a", "b"], Some("s = 'AB'"))));
    }

    #[test]
    fn schema_dependency_only_covers_referenced_columns() {
        let v = |cols: &str| TableVersion { schema: format!("md5:{cols}"), dml: 0, batch: 1, cols: cols.into() };
        let then = v("sr_item_sk:integer,sr_return_amt:numeric(12,2),sr_status:character varying(8)");
        let e = Entry {
            key: "metric:门店退货金额".into(),
            content: Content::Profile(Value::Null),
            deps: [("store_returns".to_string(), then)].into_iter().collect(),
            guards: vec![],
            status: Status::Valid,
            created_by: "A".into(),
            hits: 0,
            consumers: BTreeSet::new(),
            revision: 0,
        };
        let used: BTreeMap<String, BTreeSet<String>> =
            [("store_returns".to_string(), ["sr_item_sk", "sr_return_amt"].iter().map(|c| c.to_string()).collect())].into_iter().collect();
        let changed = vec!["store_returns".to_string()];
        let cur = |cols: &str| -> HashMap<String, TableVersion> { [("store_returns".to_string(), v(cols))].into_iter().collect() };
        let added = cur("sr_item_sk:integer,sr_return_amt:numeric(12,2),sr_status:character varying(8),sr_reason:character varying(20)");
        assert!(schema_breach(&e, &used, &added, &changed).is_none(), "无关列新增不应使口径失效");
        let unused_dropped = cur("sr_item_sk:integer,sr_return_amt:numeric(12,2)");
        assert!(schema_breach(&e, &used, &unused_dropped, &changed).is_none());
        let retyped = cur("sr_item_sk:integer,sr_return_amt:bigint,sr_status:character varying(8)");
        assert!(schema_breach(&e, &used, &retyped, &changed).is_some(), "引用列改类型必须失效");
        let dropped = cur("sr_item_sk:integer,sr_status:character varying(8)");
        assert!(schema_breach(&e, &used, &dropped, &changed).is_some(), "引用列删除必须失效");
        assert!(schema_breach(&e, &BTreeMap::new(), &added, &changed).is_some(), "没有列信息时按整表判断");
        assert!(schema_breach(&e, &used, &HashMap::new(), &changed).is_some(), "表不存在必须失效");
    }

    #[test]
    fn coverage_loss_reads_join_ratio() {
        let o = |r: f64| Outcome { pass: true, metrics: json!({"join_ratio": r}), ms: 0.0 };
        assert!((loss_of(&o(0.99)) - 0.01).abs() < 1e-12);
        assert_eq!(loss_of(&o(1.2)), 0.0);
    }
}
