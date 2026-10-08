//! 优化修订：对已发布的指标口径尝试保持语义的改写（规则改写，或模型提议），逐一验证——结构不同（O1）、静态合法（G3）、
//! 粒度（G4）、范围谓词所需的日期键连续（O2）、规范 SQL 可编译（O3）与可审查（G5）、学习时快照上与当前修订结果相同（O4）、
//! 当前快照上逐期间结果相同（O5）、配对测量的执行代价显著更低（O6）。全部通过才作为同一键的新修订发布；旧修订仍然正确，
//! 执行端宽限接受并附通知。等价与代价都在同一个快照里按期间配对比较，不跨表版本。

use super::metrics::{grain_check, metric_of, record, time_contiguity_check, Gate, MetricEvidence};
use super::{inc, outcome_text, scope_prefix, Ctx, Middle};
use crate::db::{QKind, Rows};
use crate::feedback::{summarize, Evidence};
use crate::knowledge::{Content, Example, Metric, Status, TimeSpec, TimeStrategy};
use crate::llm::Provider;
use crate::metric::{self, Ask, Period};
use anyhow::Result;
use serde_json::{json, Value};
use std::time::Instant;

/// 代价证据至少需要的配对期间数；与“配对差的 95% 区间整体低于 0”和最小节省比例一起构成采纳门槛。
pub const OPT_MIN_PAIRS: usize = 8;

macro_rules! gate {
    ($gates:expr, $name:expr, $r:expr) => {
        if let Some(f) = record($gates, $name, $r) {
            return Ok(Some(f));
        }
    };
}

/// 等价与代价比较用的期间样本：学习题所在年份的 12 个单月、一个季度、一次跨期差值、一次全年排名。
fn sample_asks(ask: &Ask) -> Vec<Ask> {
    let year = ask.years().first().copied().unwrap_or(2001);
    let mut v: Vec<Ask> = (1..=12).map(|m| Ask::Single { period: Period::month(year, m) }).collect();
    v.push(Ask::Single { period: Period { year, m1: 1, m2: 3 } });
    v.push(Ask::Diff { a: Period::month(year, 9), b: Period::month(year, 6) });
    v.push(Ask::RankMonth { year });
    v
}

/// EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) 的执行时间（ms）与读到的共享块数。
fn plan_cost(rows: &Rows) -> Option<(f64, f64)> {
    let text: String = rows.rows.iter().filter_map(|r| r.first().cloned().flatten()).collect::<Vec<_>>().join("\n");
    let v: Value = serde_json::from_str(&text).ok()?;
    let top = v.get(0)?;
    let ms = top["Execution Time"].as_f64()?;
    let plan = &top["Plan"];
    Some((ms, plan["Shared Hit Blocks"].as_f64().unwrap_or(0.0) + plan["Shared Read Blocks"].as_f64().unwrap_or(0.0)))
}

impl Middle {
    /// 对一条已发布定义尝试一个候选改写。返回事件：optimize_promoted / optimize_rejected / optimize_skipped。
    pub async fn optimize_metric(&self, ctx: &Ctx, key: &str, mut cand: Metric, label: &str, source: &str) -> Result<Value> {
        let fk = self.mfk(ctx, key);
        let skipped = |reason: &str| json!({"event": "optimize_skipped", "key": key, "candidate": label, "reason": reason});
        let Some(old) = self.store.get(&fk) else { return Ok(skipped("定义不存在")) };
        let Some(m) = metric_of(&old).cloned() else { return Ok(skipped("不是指标定义")) };
        if old.status != Status::Valid {
            return Ok(skipped("当前修订不可用"));
        }
        let Some(ev) = self.metric_evidence.lock().get(&fk).cloned() else { return Ok(skipped("没有学习证据")) };
        // 候选继承名称、别名与业务依据；结构必须与当前修订不同
        cand.name = m.name.clone();
        cand.aliases = m.aliases.clone();
        cand.basis = m.basis.clone();
        if cand.definition.trim().is_empty() {
            cand.definition = m.definition.clone();
        }
        let t0 = Instant::now();
        let before = self.db.meter.snap();
        let mut gates = vec![];
        let failed = self.optimize_gates(ctx, &m, &mut cand, &ev, &mut gates).await?;
        let d = crate::db::diff(&before, &self.db.meter.snap());
        let cost = json!({"queries": d.queries, "ms": d.db_ms, "wall_ms": t0.elapsed().as_secs_f64() * 1000.0});
        if let Some((gate, reason)) = failed {
            let v = json!({"event": "optimize_rejected", "key": key, "revision": old.revision, "candidate": label, "source": source,
                           "gate": gate, "reason": reason, "gates": gates, "cost": cost});
            self.metric_event(v.clone());
            return Ok(v);
        }
        if cand.time.as_ref().is_some_and(|t| t.strategy == TimeStrategy::KeyRange) && !cand.caveats.iter().any(|c| c.contains("日期键范围")) {
            cand.caveats.push("期间谓词按日期键范围过滤，不连接日期维度；前提是日期键按月连续，由中间层作为该修订的条件维护".into());
        }
        // 发布：同一键的新修订，使用者与命中数沿用；旧修订号记为宽限可用
        let deps = self.deps_for(&cand.tables()).await?;
        let guards = vec![grain_check(&cand)];
        let mut e = self.new_entry(ctx, &old.key, Content::Metric(Box::new(cand)), deps, guards);
        e.revision = old.revision + 1;
        e.status = Status::Valid;
        e.created_by = source.to_string();
        e.consumers = old.consumers.clone();
        e.hits = old.hits;
        self.store.put(&fk, e);
        self.opt_prev.lock().insert(fk.clone(), old.revision);
        if let Some(x) = self.metric_evidence.lock().get_mut(&fk) {
            x.gates.extend(gates.clone());
            x.optimized += 1;
        }
        inc(&self.stats.optimizations);
        let saving = gates.iter().rev().find_map(|g| g["saving"].as_f64()).unwrap_or(0.0);
        {
            let mut n = self.notices.lock();
            for a in &old.consumers {
                n.entry(a.clone()).or_default().push(format!(
                    "指标经验 {} 已发布等价且更省的修订 r{}（{label}；样本期间执行时间约省 {:.0}%）。旧修订 r{} 仍可用，建议重新调用 find_metric 改用新修订。",
                    old.key,
                    old.revision + 1,
                    saving * 100.0,
                    old.revision
                ));
                inc(&self.stats.notices);
            }
        }
        let v = json!({"event": "optimize_promoted", "key": key, "revision": old.revision + 1, "from": old.revision, "candidate": label,
                       "source": source, "saving": saving, "gates": gates, "cost": cost});
        self.metric_event(v.clone());
        Ok(v)
    }

    async fn optimize_gates(
        &self,
        ctx: &Ctx,
        old: &Metric,
        cand: &mut Metric,
        ev: &MetricEvidence,
        gates: &mut Vec<Value>,
    ) -> Result<Option<(String, String)>> {
        gate!(gates, "O1", if metric::same_structure(old, cand) { Err("与当前修订结构相同".into()) } else { Ok(()) });
        gate!(gates, "G3", self.static_gate(ctx, cand, &ev.ask).await?);
        gate!(gates, "G4", self.grain_gate(ctx, cand, self.cfg.cond_reuse).await);
        if let Some(t) = cand.time.clone() {
            if t.strategy == TimeStrategy::KeyRange {
                gate!(gates, "O2", self.contiguity_gate(ctx, &t).await);
            }
        }
        let sql = match metric::compile(cand, &ev.ask) {
            Ok(s) => s,
            Err(e) => return Ok(record(gates, "O3", Err(format!("{e:#}")))),
        };
        record(gates, "O3", Ok(()));
        let question = old.examples.first().map(|x| x.question.clone()).unwrap_or_default();
        cand.examples = vec![Example { question, sql: sql.clone() }];
        gate!(gates, "G5", self.review_gate(ctx, &sql).await?);
        // O4：学习时快照上与当前修订的规范 SQL 结果相同（配置了学习时快照时）
        let reference = match metric::compile(old, &ev.ask) {
            Ok(s) => s,
            Err(e) => return Ok(record(gates, "O4", Err(format!("当前修订无法编译：{e:#}")))),
        };
        let o4 = match (&self.learn_db, &self.cfg.g8_snapshot) {
            (Some(ldb), _) => self.learned_snapshot_gate(ldb, None, &reference, &sql, ev.decimals).await,
            (None, Some(schema)) => self.learned_snapshot_gate(&self.db, Some(schema), &reference, &sql, ev.decimals).await,
            (None, None) => Ok(()),
        };
        gate!(gates, "O4", o4);
        // O5 / O6：当前快照上逐期间比较结果与执行代价
        let (equiv, evidence, blocks) = self.compare_on_snapshot(old, cand, ev.decimals, &ev.ask).await?;
        gate!(gates, "O5", equiv);
        let saving = if evidence.baseline_ms > 0.0 { (evidence.baseline_ms - evidence.policy_ms) / evidence.baseline_ms } else { 0.0 };
        let o6: Gate = if evidence.episodes < OPT_MIN_PAIRS {
            Err(format!("可比较的期间只有 {} 个，少于 {OPT_MIN_PAIRS}", evidence.episodes))
        } else if evidence.ci95[1] >= 0.0 {
            Err(format!("执行时间配对差的 95% 区间 [{:.1}, {:.1}] ms 未整体低于 0", evidence.ci95[0], evidence.ci95[1]))
        } else if saving < self.cfg.optimize_min_saving {
            Err(format!("平均只省 {:.1}%，低于 {:.0}%", saving * 100.0, self.cfg.optimize_min_saving * 100.0))
        } else {
            Ok(())
        };
        gates.push(json!({"gate": "O6", "pass": o6.is_ok(), "reason": o6.as_ref().err(), "evidence": evidence, "saving": saving,
                          "blocks": {"old": blocks.0, "new": blocks.1}}));
        Ok(o6.err().map(|r| ("O6".to_string(), r)))
    }

    /// O2：日期键按月连续（复用同一表版本上的结论）。
    async fn contiguity_gate(&self, ctx: &Ctx, t: &TimeSpec) -> Gate {
        let c = time_contiguity_check(t);
        match self.cond_check(ctx, &c, QKind::Metric).await {
            Ok((o, _)) if o.pass => Ok(()),
            Ok((o, _)) => Err(format!("{}：{}", c.describe(), outcome_text(&c, &o))),
            Err(e) => Err(format!("执行失败：{e:#}")),
        }
    }

    /// 在一个可重复读的只读快照里，对样本期间逐个执行当前修订与候选的规范 SQL：结果须相同；再各做一次
    /// EXPLAIN (ANALYZE, BUFFERS)，先后顺序逐期交替以减轻缓存偏向。返回等价判定、执行时间的配对证据（候选 − 当前）
    /// 与两者读到的共享块数。编译结果相同的题型（按月排名）不计。
    async fn compare_on_snapshot(&self, old: &Metric, cand: &Metric, decimals: u32, learn_ask: &Ask) -> Result<(Gate, Evidence, (f64, f64))> {
        let snap = self.db.snapshot().await?;
        let mut pairs: Vec<(f64, f64)> = vec![];
        let mut blocks = (0.0, 0.0);
        let mut mismatch: Option<String> = None;
        for (i, ask) in sample_asks(learn_ask).iter().enumerate() {
            let (Ok(a), Ok(b)) = (metric::compile(old, ask), metric::compile(cand, ask)) else { continue };
            if a == b {
                continue;
            }
            match (snap.query(QKind::Metric, &a).await, snap.query(QKind::Metric, &b).await) {
                (Ok(ra), Ok(rb)) => {
                    let va = metric::parse_answer(ra.cell(0, 0).unwrap_or("NULL"));
                    let vb = metric::parse_answer(rb.cell(0, 0).unwrap_or("NULL"));
                    if !metric::same_value(&va, &vb, decimals) {
                        mismatch = Some(format!("{ask:?}：当前修订 {va:?}，候选 {vb:?}"));
                        break;
                    }
                }
                (Err(e), _) | (_, Err(e)) => {
                    mismatch = Some(format!("{ask:?}：执行失败：{e:#}"));
                    break;
                }
            }
            let explain = |s: &str| format!("explain (analyze, buffers, format json) {s}");
            let (first, second) = if i % 2 == 0 { (&a, &b) } else { (&b, &a) };
            let c1 = plan_cost(&snap.query(QKind::Metric, &explain(first)).await?);
            let c2 = plan_cost(&snap.query(QKind::Metric, &explain(second)).await?);
            if let (Some(c1), Some(c2)) = (c1, c2) {
                let (co, cn) = if i % 2 == 0 { (c1, c2) } else { (c2, c1) };
                pairs.push((cn.0, co.0));
                blocks.0 += co.1;
                blocks.1 += cn.1;
            }
        }
        snap.commit().await?;
        let evidence = summarize(&pairs);
        let equiv = match mismatch {
            Some(r) => Err(r),
            None if pairs.is_empty() => Err("没有可比较的期间".into()),
            None => Ok(()),
        };
        Ok((equiv, evidence, blocks))
    }

    /// 对本范围内每条有效定义做一轮优化：先规则改写，再（有模型时）模型提议；每条定义本轮最多发布一个新修订。
    /// 返回每条定义尝试的候选与结果。
    pub async fn optimize_sweep(&self, ctx: &Ctx, llm: Option<&Provider>, attempts: u32) -> Result<Vec<Value>> {
        let prefix = format!("{}|metric:", scope_prefix(self.cfg.metric_scope, ctx));
        let mut out = vec![];
        for (fk, e) in self.store.scan(&prefix) {
            let Some(m) = metric_of(&e).cloned() else { continue };
            if e.status != Status::Valid {
                continue;
            }
            let Some(ev) = self.metric_evidence.lock().get(&fk).cloned() else { continue };
            let mut cands: Vec<(String, Metric, &str)> =
                metric::rewrite_candidates(&m, &self.cat).into_iter().map(|(l, c)| (l, c, "rule")).collect();
            let mut proposals = Value::Null;
            if let Some(p) = llm {
                let input = self.optimize_input(&m, &ev).await;
                let pr = metric::propose(p, &input, attempts).await;
                proposals = json!({"attempts": pr.attempts, "input_tokens": pr.input_tokens, "output_tokens": pr.output_tokens,
                                   "seconds": pr.seconds, "errors": pr.errors, "proposed": pr.drafts.len()});
                cands.extend(pr.drafts.into_iter().map(|(l, c)| (l, c, "llm")));
            }
            let mut tried = vec![];
            let mut published = None;
            for (label, cand, source) in cands {
                let r = self.optimize_metric(ctx, &e.key, cand, &label, source).await?;
                let ok = r["event"] == "optimize_promoted";
                tried.push(r);
                if ok {
                    published = Some(label);
                    break;
                }
            }
            out.push(json!({"key": e.key, "revision_before": e.revision, "published": published, "tried": tried, "proposals": proposals}));
        }
        Ok(out)
    }

    /// 模型提议的输入：当前口径、它的规范 SQL 与执行计划、涉及表的行数与列。不含业务行与结果值。
    async fn optimize_input(&self, m: &Metric, ev: &MetricEvidence) -> Value {
        let sql = metric::compile(m, &ev.ask).unwrap_or_default();
        let plan = match self.vquery(QKind::Metric, &format!("explain {sql}")).await {
            Ok(r) => r.rows.iter().filter_map(|x| x.first().cloned().flatten()).collect::<Vec<_>>().join("\n"),
            Err(e) => format!("（执行计划不可用：{e:#}）"),
        };
        let tables: Vec<Value> = m
            .tables()
            .iter()
            .filter_map(|t| self.cat.table(t))
            .map(|t| {
                json!({"name": t.name, "rows_est": t.rows_est,
                       "columns": t.cols.iter().map(|c| json!({"name": c.name, "type": c.dtype})).collect::<Vec<_>>()})
            })
            .collect();
        json!({
            "metric": m, "canonical_sql": sql, "plan": plan, "tables": tables,
            "rules": [
                "time.strategy 可取 dim_join（连接日期维度）或 key_range（事实表按日期键范围过滤，不连接维度表；要求日期键按月连续）",
                "只能去掉结果不依赖的关联；度量、过滤与粒度的业务含义不得改变，不得加入题目参数",
            ],
        })
    }
}
