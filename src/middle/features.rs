//! 特征定义（RelBench，exp/2026-10-20-relbench/README.md §1.6）：从通过验证的会话学习、发布前检查、查找与组合、任务方案。
//! 特征定义就是带实体与回看窗口的指标定义（`Metric::entity`），依赖表有写入后的维护沿用指标定义的条件级维护（`metrics`），
//! 条件不成立时撤下、不做受限修复。

use super::metrics::{grain_check, metric_of, view, Checked};
use super::{join_key, Ctx, Middle, ToolSpec, LOOKUP_NOTE};
use crate::checks::Check;
use crate::db::{QKind, Rows};
use crate::knowledge::{Basis, Content, Entry, Metric, Status};
use crate::llm::Provider;
use crate::metric::{self, Ask, Period};
use crate::sqlscan;
use anyhow::Result;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeSet, HashMap};
use std::time::Instant;

/// 一次学习请求（框架在会话结束后发出）。种子都以子查询给出，中间层只读。
#[derive(Deserialize)]
pub struct LearnReq {
    pub task: String,
    pub description: String,
    pub cutoff: String,
    /// 种子表上的实体列，如 owneruserid
    pub seed_key: String,
    pub entity_table: String,
    pub entity_key: String,
    /// 会话提交的特征 SQL（含 `{seeds}`）
    pub sql: String,
    /// 按增益排序的特征列
    #[serde(default)]
    pub importance: Vec<String>,
    /// 重现检查用的种子子查询，如 `(select * from task.user_badge_train_sample order by userid, seed_time limit 2000)`
    pub seeds: String,
    /// 泄漏检查：只含 t* 及之前行的同名视图所在的模式，与 t* 时刻的种子子查询
    #[serde(default)]
    pub audit_schema: Option<String>,
    #[serde(default)]
    pub audit_seeds: Option<String>,
    pub val_score: f64,
    pub metric: String,
}

/// 结果行按（实体键, seed_time）取某一列的值。
fn by_seed(r: &Rows, col: usize) -> HashMap<(String, String), Option<String>> {
    r.rows
        .iter()
        .map(|row| {
            let k = (row.first().cloned().flatten().unwrap_or_default(), row.get(1).cloned().flatten().unwrap_or_default());
            (k, row.get(col).cloned().flatten())
        })
        .collect()
}

/// 两个特征值是否相同：数值相对误差 1e-6 以内；空值与 0 视为相同（计数类在没有行时一边写空、一边写 0）。
fn same_feature(a: &Option<String>, b: &Option<String>) -> bool {
    let num = |x: &Option<String>| x.as_deref().map(|s| s.trim().parse::<f64>().ok());
    match (num(a), num(b)) {
        (Some(Some(x)), Some(Some(y))) => (x - y).abs() <= 1e-6 * x.abs().max(y.abs()).max(1.0),
        (None, None) => true,
        (None, Some(Some(y))) | (Some(Some(y)), None) => y == 0.0,
        _ => a == b,
    }
}

/// 两组按种子的值逐一比较，返回不一致的个数与比较的个数。
fn compare(a: &HashMap<(String, String), Option<String>>, b: &HashMap<(String, String), Option<String>>) -> (usize, usize) {
    let mut bad = 0;
    for (k, v) in b {
        if !a.get(k).is_some_and(|x| same_feature(x, v)) {
            bad += 1;
        }
    }
    (bad, b.len())
}

type Gate = std::result::Result<(), String>;

fn record(gates: &mut Vec<Value>, name: &str, r: Gate) -> Option<(String, String)> {
    gates.push(json!({"gate": name, "pass": r.is_ok(), "reason": r.as_ref().err()}));
    r.err().map(|e| (name.to_string(), e))
}

impl Middle {
    fn feature_key(m: &Metric) -> String {
        let e = m.entity.as_ref().map(|e| e.table.clone()).unwrap_or_default();
        format!("feature:{}:{}", e.to_lowercase(), metric::feature_ident(&m.name))
    }

    /// 提炼器输入：任务说明、种子实体、提交的 SQL、按增益排序的列、相关表的元数据与已验证关联。不含业务行。
    fn feature_extract_input(&self, ctx: &Ctx, req: &LearnReq) -> Value {
        let mut tables: BTreeSet<String> = sqlscan::tables(&req.sql, &self.cat).into_iter().collect();
        tables.insert(req.entity_table.clone());
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
                        joins.push(
                            json!({"left": p.left, "right": p.right, "on": p.on, "filters": p.filters, "cardinality": p.cardinality()}),
                        );
                    }
                }
            }
        }
        json!({
            "task": req.task, "description": req.description,
            "seed_table": {"entity_column": req.seed_key, "time_column": "seed_time", "entity": format!("{}.{}", req.entity_table, req.entity_key)},
            "submitted_sql": req.sql,
            "columns_by_importance": req.importance.iter().take(20).collect::<Vec<_>>(),
            "tables": meta, "verified_joins": joins,
        })
    }

    /// 会话结束后的学习：提炼特征定义草稿，逐条过发布前检查（F1 字段与关联、F2 粒度、F3 重现、F4 不泄漏），
    /// 通过的发布到共享记忆；有定义通过时记下该任务的方案。提炼与检查的 token 与耗时随结果返回，由框架记到触发它的会话上。
    pub async fn learn_features(&self, ctx: &Ctx, p: &Provider, req: &LearnReq) -> Result<Value> {
        let t0 = Instant::now();
        let before = self.db.meter.snap();
        let input = self.feature_extract_input(ctx, req);
        let ex = metric::extract_features(p, &input, 2).await;
        let n_drafts = ex.drafts.len();
        let agent = self.vquery(QKind::Metric, &req.sql.trim().trim_end_matches(';').replace("{seeds}", &req.seeds)).await;
        let mut results = vec![];
        let mut members = vec![];
        for d in &ex.drafts {
            let mut m = d.metric.clone();
            m.basis = Basis::Confirmed { by: format!("validation:{}@{}", req.task, req.cutoff) };
            let mut gates = vec![];
            let failed = self.feature_gates(ctx, &mut m, &d.column, req, &agent, &mut gates).await?;
            let v = self.publish_feature(ctx, m, failed, gates, req).await?;
            if matches!(v["event"].as_str(), Some("promoted" | "corroborated")) {
                members.push(json!({"key": v["key"], "revision": v["revision"]}));
            }
            results.push(v);
        }
        let program = if members.is_empty() {
            Value::Null
        } else {
            let prog = json!({"task": req.task, "cutoff": req.cutoff, "metric": req.metric, "val_score": req.val_score,
                              "seed_key": req.seed_key, "features": members});
            let key = format!("program:{}", req.task);
            let e = self.new_entry(ctx, &key, Content::Result(prog.clone()), Default::default(), vec![]);
            self.store.put(&self.mfk(ctx, &key), e);
            self.metric_event(json!({"event": "program", "task": req.task, "cutoff": req.cutoff, "features": prog["features"]}));
            prog
        };
        let d = crate::db::diff(&before, &self.db.meter.snap());
        Ok(json!({
            "extraction": ex, "drafts": n_drafts, "features": results, "program": program,
            "seconds": t0.elapsed().as_secs_f64(), "db": {"queries": d.queries, "ms": d.db_ms},
        }))
    }

    async fn feature_gates(
        &self,
        ctx: &Ctx,
        m: &mut Metric,
        column: &str,
        req: &LearnReq,
        agent: &Result<Rows>,
        gates: &mut Vec<Value>,
    ) -> Result<Option<(String, String)>> {
        macro_rules! gate {
            ($name:expr, $r:expr) => {
                if let Some(f) = record(gates, $name, $r) {
                    return Ok(Some(f));
                }
            };
        }
        // F1：字段与关联。指标定义的静态检查（表与列存在、时间列类型、关联为已验证的多对一、过滤不含日期字面量与时间列），
        // 再查实体：实体表与键、via 列可达、实体键唯一
        let ask = Ask::Single { period: Period { year: 0, m1: 1, m2: 12 } };
        let f1 = match self.static_gate(ctx, m, &ask).await? {
            Err(e) => Err(e),
            Ok(()) => self.entity_gate(ctx, m, req).await?,
        };
        gate!("F1", f1);
        gate!("F2", self.grain_gate(ctx, m, false).await);
        let (sql, cols) = match metric::compose_features(&[&*m], &req.seed_key) {
            Ok(x) => x,
            Err(e) => return Ok(record(gates, "F3", Err(format!("编译失败：{e:#}")))),
        };
        // F3：重现。编译出的 SQL 在重现种子上与会话提交的同名列逐值一致
        let f3 = match agent {
            Err(e) => Err(format!("提交的 SQL 在重现种子上执行失败：{e:#}")),
            Ok(a) => match a.cols.iter().position(|c| c.eq_ignore_ascii_case(column)) {
                None => Err(format!("提交的 SQL 没有列 {column}")),
                Some(ci) => match self.vquery(QKind::Metric, &sql.replace("{seeds}", &req.seeds)).await {
                    Err(e) => Err(format!("编译出的 SQL 执行失败：{e:#}")),
                    Ok(c) => {
                        let (bad, n) = compare(&by_seed(a, ci), &by_seed(&c, 2));
                        if n == 0 {
                            Err("重现种子为空".into())
                        } else if bad > 0 {
                            Err(format!("{bad}/{n} 个种子上与提交的列 {column} 不一致"))
                        } else {
                            Ok(())
                        }
                    }
                },
            },
        };
        gate!("F3", f3);
        // F4：不泄漏。时间上界已写进编译出的 SQL；再在“只含 t* 及之前行”的视图上重算 t* 时刻的种子，值必须不变
        let f4 = match (&req.audit_schema, &req.audit_seeds) {
            (Some(schema), Some(seeds)) => {
                let q = sql.replace("{seeds}", seeds);
                let normal = self.vquery(QKind::Metric, &q).await;
                let hidden = async {
                    let snap = self.db.snapshot().await?;
                    snap.query(QKind::Metric, &format!("set local search_path to {schema}, public")).await?;
                    let r = snap.query(QKind::Metric, &q).await;
                    snap.commit().await?;
                    r
                }
                .await;
                match (normal, hidden) {
                    (Ok(a), Ok(b)) => {
                        let (bad, n) = compare(&by_seed(&a, 2), &by_seed(&b, 2));
                        if bad > 0 {
                            Err(format!("隐去 t* 之后的行后 {bad}/{n} 个种子的值改变"))
                        } else {
                            Ok(())
                        }
                    }
                    (Err(e), _) | (_, Err(e)) => Err(format!("泄漏检查执行失败：{e:#}")),
                }
            }
            _ => Ok(()),
        };
        gate!("F4", f4);
        let _ = cols;
        Ok(None)
    }

    /// 实体部分的字段检查：实体表与键存在且键唯一；via 列在事实表或关联到的表上；窗口在 1–3650 天。
    async fn entity_gate(&self, ctx: &Ctx, m: &Metric, req: &LearnReq) -> Result<Gate> {
        let Some(e) = &m.entity else { return Ok(Err("没有 entity".into())) };
        if !e.table.eq_ignore_ascii_case(&req.entity_table) {
            return Ok(Err(format!("实体表 {} 与任务的实体 {} 不同", e.table, req.entity_table)));
        }
        let Some(et) = self.cat.table(&e.table) else { return Ok(Err(format!("实体表 {} 不存在", e.table))) };
        if et.col(&e.key).is_none() {
            return Ok(Err(format!("实体键 {}.{} 不存在", e.table, e.key)));
        }
        let (vt, vc) = e.via_of(&m.fact);
        if vt != m.fact && !m.joins.iter().any(|j| j.right == vt) {
            return Ok(Err(format!("via 所在的表 {vt} 不在定义的关联中")));
        }
        if self.cat.table(&vt).and_then(|t| t.col(&vc)).is_none() {
            return Ok(Err(format!("via 列 {vt}.{vc} 不存在")));
        }
        if let Some(d) = e.window_days {
            if d == 0 || d > 3650 {
                return Ok(Err(format!("回看窗口 {d} 天不在 1–3650")));
            }
        }
        let c = Check::KeyUnique { table: e.table.clone(), cols: vec![e.key.clone()], filter: None };
        let (o, _) = self.cond_check(ctx, &c, QKind::Metric).await?;
        Ok(if o.pass { Ok(()) } else { Err(format!("实体键 {}.{} 不唯一", e.table, e.key)) })
    }

    /// 发布一条特征定义：同结构的有效条目已存在时记为佐证；未通过检查的保持候选（不对外提供）。
    async fn publish_feature(
        &self,
        ctx: &Ctx,
        m: Metric,
        failed: Option<(String, String)>,
        gates: Vec<Value>,
        req: &LearnReq,
    ) -> Result<Value> {
        let base = Self::feature_key(&m);
        let prefix = self.mfk(ctx, &base);
        let existing: Vec<(String, Entry)> =
            self.store.scan(&prefix).into_iter().filter(|(k, _)| *k == prefix || k.starts_with(&format!("{prefix}#"))).collect();
        let same = existing.iter().find(|(_, e)| metric_of(e).is_some_and(|x| metric::same_structure(x, &m))).cloned();
        if let Some((_, e)) = same.as_ref().filter(|(_, e)| e.status == Status::Valid) {
            let v = match &failed {
                None => json!({"event": "corroborated", "key": e.key, "revision": e.revision, "task": req.task, "gates": gates}),
                Some((g, r)) => json!({"event": "candidate", "key": e.key, "task": req.task, "failed_gate": g, "reason": r, "gates": gates,
                                       "note": "同结构的有效条目已存在，未覆盖"}),
            };
            self.metric_event(v.clone());
            return Ok(v);
        }
        let (fk, rev) = match &same {
            Some((k, e)) => (k.clone(), self.next_revision(k, e.revision)),
            None if existing.is_empty() => (prefix.clone(), 0),
            None => (format!("{prefix}#{}", existing.len() + 1), 0),
        };
        let key = fk.split_once('|').map_or_else(|| fk.clone(), |(_, k)| k.to_string());
        let deps = self.deps_for(&m.tables()).await?;
        let guards = vec![grain_check(&m)];
        let name = m.name.clone();
        let mut e = self.new_entry(ctx, &key, Content::Metric(Box::new(m)), deps, guards);
        e.revision = rev;
        e.status = match &failed {
            None => Status::Valid,
            Some((g, r)) => Status::Candidate(format!("{g}：{r}")),
        };
        self.store.put(&fk, e);
        let v = json!({
            "event": if failed.is_none() { "promoted" } else { "candidate" }, "key": key, "revision": rev, "name": name,
            "task": req.task, "cutoff": req.cutoff,
            "failed_gate": failed.as_ref().map(|f| f.0.clone()), "reason": failed.as_ref().map(|f| f.1.clone()), "gates": gates,
        });
        self.metric_event(v.clone());
        Ok(v)
    }

    /// 工具 find_features：某实体上已发布的特征定义，按查询词与名称、含义的重合排序；经守护（依赖表有写入时条件级重验）后返回。
    pub async fn find_features(&self, ctx: &Ctx, entity: &str, query: &str) -> Result<Value> {
        if self.lookup_exhausted(ctx) {
            return Ok(json!({"features": [], "note": LOOKUP_NOTE}));
        }
        let prefix = self.mfk(ctx, &format!("feature:{}:", entity.trim().to_lowercase()));
        let words: Vec<String> =
            query.to_lowercase().split(|c: char| !c.is_alphanumeric()).filter(|w| w.len() > 2).map(String::from).collect();
        let mut cands: Vec<(usize, String, Entry)> = vec![];
        for (fk, e) in self.store.scan(&prefix) {
            let Some(m) = metric_of(&e) else { continue };
            if matches!(e.status, Status::Candidate(_)) {
                continue;
            }
            let text = format!("{} {}", m.name, m.definition).to_lowercase();
            let score = words.iter().filter(|w| text.contains(w.as_str())).count();
            cands.push((score, fk, e));
        }
        cands.sort_by(|a, b| b.0.cmp(&a.0).then(b.2.hits.cmp(&a.2.hits)).then(a.1.cmp(&b.1)));
        let (mut hits, mut unavailable) = (vec![], vec![]);
        for (_, fk, _) in cands.into_iter().take(40) {
            match self.metric_check(ctx, &fk).await? {
                Checked::Valid(e) => {
                    let Some(m) = metric_of(&e) else { continue };
                    let en = m.entity.clone();
                    hits.push(json!({"key": e.key, "revision": e.revision, "name": m.name, "definition": m.definition,
                                     "fact": m.fact, "measure": m.measure, "filters": m.filters,
                                     "via": en.as_ref().map(|x| x.via.clone()), "window_days": en.and_then(|x| x.window_days),
                                     "uses": e.hits}));
                }
                Checked::Unavailable(e, r) => unavailable.push(json!({"key": e.key, "revision": e.revision, "status": r})),
                Checked::Missing => {}
            }
        }
        let mut v = json!({"features": hits});
        if !unavailable.is_empty() {
            v["unavailable"] = json!(unavailable);
        }
        if v["features"].as_array().is_some_and(|a| a.is_empty()) {
            v["note"] = json!("no verified feature definitions for this entity yet; explore the tables directly");
        }
        Ok(v)
    }

    /// 工具 compose_features：把给定的已发布定义（键）编译成一条特征 SQL（含 `{seeds}`），可直接交给 validate_features。
    pub async fn compose_feature_sql(&self, ctx: &Ctx, keys: &[String], seed_key: &str) -> Result<Value> {
        let (mut ms, mut used, mut unavailable) = (vec![], vec![], vec![]);
        for k in keys {
            let fk = self.mfk(ctx, k.trim());
            match self.metric_check(ctx, &fk).await? {
                Checked::Valid(e) => {
                    if let Some(m) = metric_of(&e) {
                        if m.entity.is_some() {
                            ms.push(m.clone());
                            used.push(json!({"key": e.key, "revision": e.revision}));
                            self.store.update(&fk, |x| {
                                x.hits += 1;
                                x.consumers.insert(ctx.agent.clone());
                            });
                        }
                    }
                }
                Checked::Unavailable(e, r) => unavailable.push(json!({"key": e.key, "revision": e.revision, "status": r})),
                Checked::Missing => unavailable.push(json!({"key": k, "status": "no such feature definition"})),
            }
        }
        if ms.is_empty() {
            return Ok(json!({"error": "none of the given keys is a valid feature definition", "unavailable": unavailable}));
        }
        let refs: Vec<&Metric> = ms.iter().collect();
        let (sql, cols) = metric::compose_features(&refs, seed_key)?;
        let columns: Vec<Value> = used
            .into_iter()
            .zip(cols)
            .map(|(mut u, c)| {
                u["column"] = json!(c);
                u
            })
            .collect();
        let mut v = json!({"sql": sql, "columns": columns});
        if !unavailable.is_empty() {
            v["unavailable"] = json!(unavailable);
        }
        Ok(v)
    }

    /// 工具 find_program：该任务最近一次通过检查的方案（截点、验证分数、定义），其中仍然有效的定义编译成特征 SQL。
    pub async fn find_program(&self, ctx: &Ctx, task: &str) -> Result<Value> {
        if self.lookup_exhausted(ctx) {
            return Ok(json!({"program": null, "note": LOOKUP_NOTE}));
        }
        let Some(Entry { content: Content::Result(prog), .. }) = self.store.get(&self.mfk(ctx, &format!("program:{}", task.trim()))) else {
            return Ok(json!({"program": null, "note": "no verified program for this task yet"}));
        };
        let keys: Vec<String> =
            prog["features"].as_array().into_iter().flatten().filter_map(|f| f["key"].as_str().map(String::from)).collect();
        let seed_key = prog["seed_key"].as_str().unwrap_or_default().to_string();
        let composed = self.compose_feature_sql(ctx, &keys, &seed_key).await?;
        Ok(json!({"program": {"task": prog["task"], "cutoff": prog["cutoff"], "metric": prog["metric"], "val_score": prog["val_score"]},
                  "sql": composed["sql"], "columns": composed["columns"], "unavailable": composed["unavailable"]}))
    }

    /// 已发布的特征定义（框架在运行结束时导出）。
    pub fn feature_report(&self) -> Value {
        let entries: Vec<Value> = self
            .store
            .scan("")
            .into_iter()
            .filter(|(_, e)| metric_of(e).is_some_and(|m| m.entity.is_some()))
            .map(|(fk, e)| json!({"full_key": fk, "entry": view(&e), "status": e.status, "hits": e.hits, "consumers": e.consumers}))
            .collect();
        json!({"features": entries})
    }
}

/// 特征记忆的三个工具。
pub fn feature_tool_specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            name: "find_features",
            description: "List verified feature definitions shared by all agents for an entity table (name, meaning, aggregated table, measure, look-back window).",
            schema: json!({"type": "object", "properties": {
                "entity": {"type": "string", "description": "entity table, e.g. users"},
                "query": {"type": "string", "description": "words describing the features you want"}
            }, "required": ["entity"]}),
        },
        ToolSpec {
            name: "compose_features",
            description: "Compile verified feature definitions (keys from find_features) into one feature SQL that uses {seeds}; pass it to validate_features as is or extend it.",
            schema: json!({"type": "object", "properties": {
                "keys": {"type": "array", "items": {"type": "string"}},
                "seed_key": {"type": "string", "description": "entity column of the seed table"}
            }, "required": ["keys", "seed_key"]}),
        },
        ToolSpec {
            name: "find_program",
            description: "The latest verified feature program for a task (cutoff, validation score) with its still-valid definitions compiled into one feature SQL.",
            schema: json!({"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}),
        },
    ]
}
