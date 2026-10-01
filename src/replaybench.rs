//! 配对回放（机制层，不调用 LLM）：取场景评测里模型学到的指标库（各组的 metric_report），在同一份数据上逐个施加
//! 数据变化。每个库在每种维护方式下各有一个中间层实例，从同一个库、同一个变化、同一批留出题出发，只有维护方式不同。
//! 答案一律用当时提供的修订的规范 SQL（`metric::compile`）在当前数据上计算并与标准答案比较，即“智能体完全按定义作答”
//! 时维护方式本身带来的正确、过期使用与不可用，排除了学习与作答的随机性。
//!
//! G8 参照有两种：judge = 学习题的判题 SQL（本文基准的做法，预先写入了状态与版本过滤）；example = 智能体学习时
//! 自己写的 SQL（部署中真正可得的参照）。只影响修复，因此只对会修复的条件级与定义级各跑两种。

use crate::db::{Db, QKind};
use crate::etl;
use crate::knowledge::Metric;
use crate::metric::{self, parse_answer, same_value, Ask};
use crate::metricbench::{self, Set};
use crate::middle::{Checkpoint, Ctx, Maint, Middle, MiddleConfig};
use crate::scenario::{self, Change};
use anyhow::{ensure, Context, Result};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::Path;
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    /// 场景评测的组文件（cell-*.json），或包含它们的目录（递归查找条件级与定义级组的 cell-*-metric-global[-def]-named.json）
    #[arg(long, value_delimiter = ',', required = true)]
    libs: Vec<String>,
    /// 门店销售行数（目录渠道为其一半）
    #[arg(long, default_value_t = 200_000, value_parser = clap::value_parser!(u32).range(10_000..=20_000_000))]
    rows: u32,
    #[arg(long, value_delimiter = ',', default_value = "condition,definition,definition-cache,schema,revoke",
          value_parser = ["condition", "definition", "definition-cache", "schema", "revoke"])]
    policies: Vec<String>,
    /// G8 参照（只对条件级与定义级区分；其余方式不修复，用 judge 准入）
    #[arg(long, value_delimiter = ',', default_value = "judge,example", value_parser = ["judge", "example"])]
    oracles: Vec<String>,
    #[arg(long, value_delimiter = ',',
          default_value = "append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror",
          value_parser = ["append", "backfill", "correct", "addcol", "status", "revision", "dupload", "dimhist", "latekey", "unit", "mirror"])]
    changes: Vec<String>,
    /// 中间层连接池的单条 SQL 超时
    #[arg(long, default_value_t = 120, value_parser = clap::value_parser!(u64).range(10..=3600))]
    sql_timeout_secs: u64,
}

struct LibEntry {
    /// 库内唯一的名称（同名的第二条带 #2 后缀，与原组一致）
    name: String,
    def: String,
    metric: Metric,
    ask: Ask,
    decimals: u32,
    judge: String,
    example: String,
}

struct Library {
    id: String,
    source: String,
    entries: Vec<LibEntry>,
    skipped: Vec<Value>,
}

struct Run {
    lib: usize,
    policy: String,
    oracle: String,
    mid: Middle,
    cp: Checkpoint,
    /// (库内条目序号, 键, 准入后的修订号)
    seeded: Vec<(usize, String, u32)>,
    seed_failed: Vec<Value>,
}

fn find_cells(path: &Path, out: &mut Vec<String>) -> Result<()> {
    if path.is_dir() {
        let mut items: Vec<_> = std::fs::read_dir(path)?.filter_map(|e| e.ok().map(|e| e.path())).collect();
        items.sort();
        for p in items {
            if p.is_dir() {
                find_cells(&p, out)?;
            } else {
                let n = p.file_name().and_then(|n| n.to_str()).unwrap_or_default();
                if n.starts_with("cell-") && (n.ends_with("-metric-global-named.json") || n.ends_with("-metric-global-def-named.json")) {
                    out.push(p.to_string_lossy().into_owned());
                }
            }
        }
    } else {
        out.push(path.to_string_lossy().into_owned());
    }
    Ok(())
}

fn load(path: &str) -> Result<Library> {
    let v: Value = serde_json::from_str(&std::fs::read_to_string(path)?).with_context(|| format!("读取 {path}"))?;
    let p = Path::new(path);
    let run = p.parent().and_then(Path::parent).and_then(Path::file_name).and_then(|n| n.to_str()).unwrap_or("run");
    let cell = v["cell"].as_str().unwrap_or("cell");
    let (mut entries, mut skipped) = (vec![], vec![]);
    for e in v["metric_report"]["entries"].as_array().into_iter().flatten() {
        let key = e["key"].as_str().unwrap_or_default();
        let parsed = (|| -> Result<LibEntry> {
            ensure!(e["status"] == "Valid", "状态 {}", e["status"]);
            let ev = &e["evidence"];
            let task = ev["task"].as_str().context("缺少来源任务")?;
            let mut metric: Metric = serde_json::from_value(e["metric"].clone())?;
            let name = key.strip_prefix("metric:").unwrap_or(key).to_string();
            metric.name = name.clone();
            let example = metric.examples.first().map(|x| x.sql.clone()).context("缺少学习示例 SQL")?;
            Ok(LibEntry {
                name,
                def: task.split('-').next().unwrap_or_default().to_string(),
                metric,
                ask: serde_json::from_value(ev["ask"].clone())?,
                decimals: ev["decimals"].as_u64().unwrap_or(2) as u32,
                judge: ev["judge"].as_str().context("缺少判题 SQL")?.to_string(),
                example,
            })
        })();
        match parsed {
            Ok(x) => entries.push(x),
            Err(err) => skipped.push(json!({"key": key, "reason": format!("{err:#}")})),
        }
    }
    Ok(Library { id: format!("{run}/{cell}"), source: path.to_string(), entries, skipped })
}

fn config(policy: &str) -> MiddleConfig {
    let base = MiddleConfig { name: policy.into(), ..Default::default() };
    match policy {
        "condition" => MiddleConfig { metric_maint: Maint::Condition, cond_reuse: true, ..base },
        "definition" => MiddleConfig { metric_maint: Maint::Definition, ..base },
        "definition-cache" => MiddleConfig { metric_maint: Maint::Definition, sql_cache: true, ..base },
        "schema" => MiddleConfig { metric_maint: Maint::Schema, ..base },
        _ => MiddleConfig { metric_maint: Maint::Revoke, ..base },
    }
}

fn affected(def: &str, ch: Change) -> bool {
    metricbench::tasks(&[def.to_string()]).first().is_some_and(|t| t.def.tables.iter().any(|x| ch.tables().contains(x)))
}

async fn answer(probe: &Db, sql: &str) -> String {
    match probe.query(QKind::Meta, sql).await {
        Ok(r) => r.cell(0, 0).unwrap_or("NULL").to_string(),
        Err(e) => format!("ERROR: {e:#}"),
    }
}

fn db_ms(mid: &Middle) -> (f64, u64) {
    let d = &mid.stats_json()["db"];
    (d["db_ms"].as_f64().unwrap_or(0.0), d["queries"].as_u64().unwrap_or(0))
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    let changes = o.changes.iter().map(|c| Change::parse(c)).collect::<Result<Vec<_>>>()?;
    let mut files = vec![];
    for l in &o.libs {
        find_cells(Path::new(l), &mut files)?;
    }
    let libs: Vec<Library> = files.iter().map(|f| load(f)).collect::<Result<_>>()?;
    ensure!(!libs.is_empty(), "没有找到指标库");
    eprintln!("指标库 {} 个，条目 {} 条", libs.len(), libs.iter().map(|l| l.entries.len()).sum::<usize>());
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_replay_{}_{stamp}", std::process::id());
    let directory = format!("{out}/replay-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await.context("创建隔离实验库失败（需要 CREATEDB）")?;
    let result: Result<Value> = async {
        let admin = Db::connect(isolated.as_str(), 2, false)?;
        eprintln!("生成合成零售数据：门店销售 {} 行，目录销售 {} 行", o.rows, o.rows / 2);
        admin.query(QKind::Meta, &metricbench::fixture(o.rows)).await?;
        etl::setup(&admin).await?;
        scenario::setup(&admin).await?;
        let v1 = scenario::fingerprint(&admin).await?;
        let probe = Db::connect(isolated.as_str(), 2, true)?;
        let db = Arc::new(Db::connect_timeout(isolated.as_str(), pool, true, o.sql_timeout_secs)?);
        let defs: Vec<String> = ["M1", "M2", "M3", "M4", "M5"].iter().map(|s| s.to_string()).collect();
        let tasks = metricbench::tasks(&defs);

        // 每个库 × 维护方式 × G8 参照一个中间层实例，共用连接池；按顺序评估，数据库耗时按前后差值归属
        let mut runs: Vec<Run> = vec![];
        for (li, lib) in libs.iter().enumerate() {
            for policy in &o.policies {
                let oracles: Vec<&str> = if matches!(policy.as_str(), "condition" | "definition") {
                    o.oracles.iter().map(String::as_str).collect()
                } else {
                    vec!["judge"]
                };
                for oracle in oracles {
                    let mid = Middle::new(db.clone(), config(policy)).await?;
                    let ctx = Ctx::new("A", &lib.id, "seed");
                    let (mut seeded, mut seed_failed) = (vec![], vec![]);
                    for (ei, e) in lib.entries.iter().enumerate() {
                        let reference = if oracle == "judge" { &e.judge } else { &e.example };
                        let v = mid.seed_metric(&ctx, e.metric.clone(), e.ask, e.decimals, reference).await?;
                        if v["promoted"] == true {
                            seeded.push((ei, v["key"].as_str().unwrap_or_default().to_string(), v["revision"].as_u64().unwrap_or(0) as u32));
                        } else {
                            seed_failed.push(json!({"entry": e.name, "gate": v["failed_gate"], "reason": v["reason"]}));
                        }
                    }
                    eprintln!("  {} {policy}/{oracle}：准入 {}，未通过 {}", lib.id, seeded.len(), seed_failed.len());
                    let _ = mid.take_metric_events();
                    runs.push(Run { lib: li, policy: policy.clone(), oracle: oracle.into(), cp: mid.checkpoint(), mid, seeded, seed_failed });
                }
            }
        }

        let (mut outcomes, mut maint) = (vec![], vec![]);
        for (ci, &ch) in changes.iter().enumerate() {
            scenario::ensure_v1(&admin, &v1, "上一个变化").await?;
            let truth = ch.apply_truth(&admin).await?;
            let gold = metricbench::gold_map(&admin, &tasks).await?;
            let hidden = ch.apply_hidden(&admin).await?;
            eprintln!("变化 {}（{}）：写入 {truth} + {hidden} 行", ch.name(), ch.label());
            let held: Vec<_> = tasks.iter().filter(|t| t.set != Set::Learn).collect();
            // 不维护时原定义在变化后的数据上是否仍答对：区分必要与不必要的不可用
            let mut orig: BTreeMap<(usize, usize, String), (String, bool)> = BTreeMap::new();
            for (li, lib) in libs.iter().enumerate() {
                for (ei, e) in lib.entries.iter().enumerate().filter(|(_, e)| affected(&e.def, ch)) {
                    for t in held.iter().filter(|t| t.def.id == e.def) {
                        let value = match metric::compile(&e.metric, &t.ask) {
                            Ok(sql) => answer(&probe, &sql).await,
                            Err(err) => format!("ERROR: {err:#}"),
                        };
                        let ok = same_value(&parse_answer(&value), &parse_answer(&gold[&t.id]), metricbench::decimals(&t.ask));
                        orig.insert((li, ei, t.id.clone()), (value, ok));
                    }
                }
            }
            // 轮换评估顺序，避免总由同一组承担冷缓存
            let n = runs.len();
            for k in 0..n {
                let r = &runs[(k + ci * 7) % n];
                let lib = &libs[r.lib];
                r.mid.invalidate_versions();
                let (ms0, q0) = db_ms(&r.mid);
                let t0 = Instant::now();
                let ctx = Ctx::new("B", ch.name(), "use");
                let mut used = 0;
                for (ei, key, rev) in &r.seeded {
                    let e = &lib.entries[*ei];
                    if !affected(&e.def, ch) {
                        continue;
                    }
                    used += 1;
                    let v = r.mid.use_metric(&ctx, key).await?;
                    let valid = v["status"] == "valid";
                    let served: Option<Metric> = if valid { serde_json::from_value(v["metric"].clone()).ok() } else { None };
                    let revision = v["revision"].as_u64().unwrap_or(0) as u32;
                    for t in held.iter().filter(|t| t.def.id == e.def) {
                        let (orig_value, orig_ok) = orig[&(r.lib, *ei, t.id.clone())].clone();
                        let (value, ok) = match &served {
                            Some(m) => {
                                let value = match metric::compile(m, &t.ask) {
                                    Ok(sql) => answer(&probe, &sql).await,
                                    Err(err) => format!("ERROR: {err:#}"),
                                };
                                let ok = same_value(&parse_answer(&value), &parse_answer(&gold[&t.id]), metricbench::decimals(&t.ask));
                                (Some(value), ok)
                            }
                            None => (None, false),
                        };
                        let class = match (valid, ok, orig_ok) {
                            (true, true, _) => "correct",
                            (true, false, _) => "served_wrong",
                            (false, _, false) => "unavailable_needed",
                            (false, _, true) => "unavailable_unneeded",
                        };
                        outcomes.push(json!({
                            "lib": lib.id, "policy": r.policy, "oracle": r.oracle, "change": ch.name(), "entry": e.name, "def": e.def,
                            "task": t.id, "status": v["status"], "revision": revision, "repaired": valid && revision != *rev,
                            "value": value, "gold": gold[&t.id], "orig_value": orig_value, "orig_ok": orig_ok, "class": class,
                        }));
                    }
                }
                let (ms1, q1) = db_ms(&r.mid);
                maint.push(json!({
                    "lib": lib.id, "policy": r.policy, "oracle": r.oracle, "change": ch.name(), "entries_used": used,
                    "db_ms": ms1 - ms0, "queries": q1 - q0, "wall_ms": t0.elapsed().as_secs_f64() * 1000.0,
                    "events": r.mid.take_metric_events(),
                }));
            }
            ch.reset(&admin).await?;
            scenario::ensure_v1(&admin, &v1, ch.name()).await?;
            for r in &runs {
                r.mid.restore(&r.cp).await?;
            }
            std::fs::write(
                format!("{directory}/partial.json"),
                serde_json::to_string(&json!({"done": ci + 1, "outcomes": outcomes, "maintenance": maint}))?,
            )?;
        }
        let libraries: Vec<Value> = libs
            .iter()
            .map(|l| json!({"id": l.id, "source": l.source, "entries": l.entries.iter().map(|e| json!({"name": e.name, "def": e.def})).collect::<Vec<_>>(),
                            "skipped": l.skipped}))
            .collect();
        let seeds: Vec<Value> = runs
            .iter()
            .map(|r| json!({"lib": libs[r.lib].id, "policy": r.policy, "oracle": r.oracle, "seeded": r.seeded.len(), "failed": r.seed_failed}))
            .collect();
        Ok(json!({
            "options": o, "pool": pool, "libraries": libraries, "seeds": seeds,
            "changes": changes.iter().map(|c| json!({"name": c.name(), "label": c.label(), "class": c.class(), "tables": c.tables(),
                                                     "describe": c.describe()})).collect::<Vec<_>>(),
            "methodology": {
                "pairing": "每个库在各维护方式下各有一个中间层实例，准入、变化、留出题完全相同；每个变化从 v1 施加，结束后回滚并恢复各实例的准入快照",
                "answer": "答案 = 当时提供的修订的规范 SQL 在当前数据上的结果；不提供（撤销或候选）记为不可用",
                "classes": "correct / served_wrong（提供了但答错：过期使用或错误修复）/ unavailable_needed（原定义已答错）/ unavailable_unneeded（原定义仍答对）",
                "oracle": "judge = 学习题判题 SQL；example = 智能体学习时自己写的 SQL；只影响修复的 G8",
                "db_time": "各实例按顺序评估，数据库耗时为评估前后中间层连接池计量的差值（答案查询走独立连接，不计入）",
            },
            "outcomes": outcomes, "maintenance": maint,
        }))
    }
    .await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let report = match &result {
        Ok(v) => v.clone(),
        Err(e) => json!({"status": "failed", "error": format!("{e:#}")}),
    };
    std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
    if let Ok(v) = &result {
        std::fs::write(format!("{directory}/report.md"), markdown(v))?;
    }
    eprintln!("配对回放报告：{directory}/report.json；实验库清理：{}", cleanup.is_ok());
    cleanup.context("实验库清理失败")?;
    result.map(|_| ())
}

fn markdown(v: &Value) -> String {
    let mut by: BTreeMap<(String, String), BTreeMap<String, u64>> = BTreeMap::new();
    for x in v["outcomes"].as_array().into_iter().flatten() {
        let k = (x["policy"].as_str().unwrap_or_default().to_string(), x["oracle"].as_str().unwrap_or_default().to_string());
        *by.entry(k).or_default().entry(x["class"].as_str().unwrap_or_default().to_string()).or_default() += 1;
    }
    let mut ms: BTreeMap<(String, String), f64> = BTreeMap::new();
    for x in v["maintenance"].as_array().into_iter().flatten() {
        let k = (x["policy"].as_str().unwrap_or_default().to_string(), x["oracle"].as_str().unwrap_or_default().to_string());
        *ms.entry(k).or_default() += x["db_ms"].as_f64().unwrap_or(0.0);
    }
    let cols = ["correct", "served_wrong", "unavailable_needed", "unavailable_unneeded"];
    let rows: Vec<Vec<String>> = by
        .iter()
        .map(|((p, o), c)| {
            let total: u64 = c.values().sum();
            let mut row = vec![p.clone(), o.clone(), total.to_string()];
            row.extend(cols.iter().map(|k| c.get(*k).copied().unwrap_or(0).to_string()));
            row.push(format!("{:.1}", ms.get(&(p.clone(), o.clone())).copied().unwrap_or(0.0) / 1000.0));
            row
        })
        .collect();
    format!(
        "# 配对回放\n\n库 {} 个；变化 {} 个。\n\n{}",
        v["libraries"].as_array().map_or(0, Vec::len),
        v["changes"].as_array().map_or(0, Vec::len),
        metricbench::md_table(
            &["维护方式", "G8 参照", "题次", "答对", "提供但答错", "不可用（必要）", "不可用（不必要）", "维护 DB 秒"],
            &rows
        )
    )
}
