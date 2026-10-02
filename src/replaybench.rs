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
use crate::tpcds;
use anyhow::{bail, ensure, Context, Result};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
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
    /// 维护方式；tabletest 为 dbt 式表级测试基线（不经中间层，见 `TABLE_TESTS`）
    #[arg(long, value_delimiter = ',', default_value = "condition,definition,definition-cache,schema,revoke,tabletest",
          value_parser = ["condition", "definition", "definition-cache", "schema", "revoke", "tabletest"])]
    policies: Vec<String>,
    /// G8 参照（只对条件级与定义级区分；其余方式不修复，用 judge 准入）
    #[arg(long, value_delimiter = ',', default_value = "judge,example", value_parser = ["judge", "example"])]
    oracles: Vec<String>,
    /// 负载：synthetic = 合成零售数据（按 --rows 生成）；tpcds = 从模板库复制真实 TPC-DS 数据（tools/tpcds-load.sh 装入），
    /// 变化为 `tpcds::Change`，库为 tools/tpcds-library.py 导出的模板定义库（留出题与标准答案随库给出）
    #[arg(long, default_value = "synthetic", value_parser = ["synthetic", "tpcds"])]
    schema: String,
    /// --schema tpcds 时复制的模板库名
    #[arg(long, default_value = "tpcds_sf1")]
    template_db: String,
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
    /// 计分的留出题（编号, 参数）：合成基准取 `metricbench::tasks`，TPC-DS 库随库给出
    held: Vec<(String, Ask)>,
    /// 标准答案由原定义的规范 SQL 在“业务事实已变、表示未变”的状态上算出（TPC-DS 库）；合成基准用手写判题 SQL
    own_gold: bool,
}

/// 两种负载上的同名变化。
#[derive(Clone, Copy)]
enum Ch {
    Syn(Change),
    Tp(tpcds::Change),
}

impl Ch {
    fn parse(schema: &str, s: &str) -> Result<Ch> {
        Ok(if schema == "tpcds" { Ch::Tp(tpcds::Change::parse(s)?) } else { Ch::Syn(Change::parse(s)?) })
    }
    fn syn(self) -> Change {
        match self {
            Ch::Syn(c) => c,
            Ch::Tp(c) => c.syn(),
        }
    }
    fn name(self) -> &'static str {
        self.syn().name()
    }
    fn tables(self) -> &'static [&'static str] {
        self.syn().tables()
    }
    async fn apply_truth(self, db: &Db) -> Result<i64> {
        match self {
            Ch::Syn(c) => c.apply_truth(db).await,
            Ch::Tp(c) => c.apply_truth(db).await,
        }
    }
    async fn apply_hidden(self, db: &Db) -> Result<i64> {
        match self {
            Ch::Syn(c) => c.apply_hidden(db).await,
            Ch::Tp(c) => c.apply_hidden(db).await,
        }
    }
    async fn reset(self, db: &Db) -> Result<()> {
        match self {
            Ch::Syn(c) => c.reset(db).await,
            Ch::Tp(c) => c.reset(db).await,
        }
    }
}

/// TPC-DS 库的判题查询：规范 SQL 加上基准作者预知的区分列过滤，与合成基准手写判题 SQL 的做法相同。
fn judge_metric(m: &Metric) -> Metric {
    let mut j = m.clone();
    for (t, f) in [("store_returns", "sr_status = '完成'"), ("store_sales", "ss_is_current = 1"), ("item", "i_is_current = 'Y'")] {
        if m.tables().iter().any(|x| x == t) {
            let v = j.filters.entry(t.to_string()).or_default();
            *v = if v.is_empty() { f.to_string() } else { format!("({v}) and {f}") };
        }
    }
    j
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
            let ask: Ask = serde_json::from_value(ev["ask"].clone())?;
            let holdout: Vec<(String, Ask)> = e["holdout"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|h| Ok((h["id"].as_str().context("留出题缺少 id")?.to_string(), serde_json::from_value(h["ask"].clone())?)))
                .collect::<Result<_>>()?;
            let own_gold = !holdout.is_empty();
            let def = if own_gold { name.clone() } else { task.split('-').next().unwrap_or_default().to_string() };
            let held = if own_gold {
                holdout
            } else {
                metricbench::tasks(&[def.clone()]).into_iter().filter(|t| t.set != Set::Learn).map(|t| (t.id, t.ask)).collect()
            };
            let example = match metric.examples.first() {
                Some(x) => x.sql.clone(),
                None if own_gold => metric::compile(&metric, &ask)?,
                None => bail!("缺少学习示例 SQL"),
            };
            let judge = match ev["judge"].as_str() {
                Some(j) => j.to_string(),
                None if own_gold => metric::compile(&judge_metric(&metric), &ask)?,
                None => bail!("缺少判题 SQL"),
            };
            Ok(LibEntry { name, def, metric, ask, decimals: ev["decimals"].as_u64().unwrap_or(2) as u32, judge, example, held, own_gold })
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

/// 条目是否读到了变化的表：合成基准按基准定义的表，TPC-DS 库按结构化实现涉及的表。
fn affected(e: &LibEntry, ch: Ch) -> bool {
    let tables: Vec<String> = match metricbench::tasks(&[e.def.clone()]).first() {
        Some(t) if !e.own_gold => t.def.tables.iter().map(|s| s.to_string()).collect(),
        _ => e.metric.tables(),
    };
    tables.iter().any(|x| ch.tables().contains(&x.as_str()))
}

/// 同一变化状态下相同 SQL 的答案只算一次（各实例提供的修订大多相同）。
async fn answer_memo(probe: &Db, sql: &str, memo: &mut HashMap<String, String>) -> String {
    if let Some(v) = memo.get(sql) {
        return v.clone();
    }
    let v = answer(probe, sql).await;
    memo.insert(sql.to_string(), v.clone());
    v
}

/// dbt 式表级测试基线（配对回放的对照）：每张表上人工声明的 unique / not_null / relationships 测试，按初始快照校准；
/// 每次变化后像 `dbt test` 一样全部跑一遍，某张表有测试失败时读到该表的全部定义一律隔离（不可用），否则照原样提供，不修复。
/// 与条件级维护的区别：测试按表声明而不由定义推出、不带定义自己的过滤、结论只说明表而不说明哪个定义受影响。
const TABLE_TESTS: &[(&str, &str, &str)] = &[
    ("store_sales", "unique(ss_ticket_number, ss_item_sk)",
     "select 1 from store_sales group by ss_ticket_number, ss_item_sk having count(*) > 1 limit 1"),
    ("store_sales", "relationships(ss_sold_date_sk -> date_dim.d_date_sk)",
     "select 1 from store_sales s where s.ss_sold_date_sk is not null and not exists (select 1 from date_dim d where d.d_date_sk = s.ss_sold_date_sk) limit 1"),
    ("store_sales", "relationships(ss_item_sk -> item.i_item_sk)",
     "select 1 from store_sales s where not exists (select 1 from item i where i.i_item_sk = s.ss_item_sk) limit 1"),
    ("store_returns", "unique(sr_ticket_number, sr_item_sk)",
     "select 1 from store_returns group by sr_ticket_number, sr_item_sk having count(*) > 1 limit 1"),
    ("store_returns", "relationships(sr_returned_date_sk -> date_dim.d_date_sk)",
     "select 1 from store_returns r where r.sr_returned_date_sk is not null and not exists (select 1 from date_dim d where d.d_date_sk = r.sr_returned_date_sk) limit 1"),
    ("store_returns", "relationships(sr_item_sk -> item.i_item_sk)",
     "select 1 from store_returns r where not exists (select 1 from item i where i.i_item_sk = r.sr_item_sk) limit 1"),
    ("catalog_sales", "unique(cs_order_number, cs_item_sk)",
     "select 1 from catalog_sales group by cs_order_number, cs_item_sk having count(*) > 1 limit 1"),
    ("catalog_sales", "relationships(cs_sold_date_sk -> date_dim.d_date_sk)",
     "select 1 from catalog_sales c where c.cs_sold_date_sk is not null and not exists (select 1 from date_dim d where d.d_date_sk = c.cs_sold_date_sk) limit 1"),
    ("catalog_sales", "relationships(cs_item_sk -> item.i_item_sk)",
     "select 1 from catalog_sales c where not exists (select 1 from item i where i.i_item_sk = c.cs_item_sk) limit 1"),
    ("item", "unique(i_item_sk)", "select 1 from item group by i_item_sk having count(*) > 1 limit 1"),
    ("item", "not_null(i_item_sk)", "select 1 from item where i_item_sk is null limit 1"),
    ("date_dim", "unique(d_date_sk)", "select 1 from date_dim group by d_date_sk having count(*) > 1 limit 1"),
];

async fn table_tests(db: &Db) -> Result<Vec<Value>> {
    let mut out = vec![];
    for (table, test, sql) in TABLE_TESTS {
        let failed = db.query(QKind::Check, sql).await?.cell(0, 0).is_some();
        out.push(json!({"table": table, "test": test, "failed": failed}));
    }
    Ok(out)
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
    let changes = o.changes.iter().map(|c| Ch::parse(&o.schema, c)).collect::<Result<Vec<_>>>()?;
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
    let create = if o.schema == "tpcds" {
        format!("create database {name} template {}", o.template_db)
    } else {
        format!("create database {name}")
    };
    root.query(QKind::Meta, &create).await.context("创建隔离实验库失败（需要 CREATEDB；tpcds 还需要模板库存在且无人连接）")?;
    let result: Result<Value> = async {
        let admin = Db::connect(isolated.as_str(), 2, false)?;
        if o.schema == "tpcds" {
            eprintln!("从模板库 {} 复制 TPC-DS 数据", o.template_db);
            tpcds::setup(&admin).await?;
        } else {
            eprintln!("生成合成零售数据：门店销售 {} 行，目录销售 {} 行", o.rows, o.rows / 2);
            admin.query(QKind::Meta, &metricbench::fixture(o.rows)).await?;
            etl::setup(&admin).await?;
            scenario::setup(&admin).await?;
        }
        let v1 = scenario::fingerprint(&admin).await?;
        let table_test = o.policies.iter().any(|p| p == "tabletest");
        if table_test {
            let failed: Vec<Value> = table_tests(&admin).await?.into_iter().filter(|x| x["failed"] == true).collect();
            ensure!(failed.is_empty(), "表级测试在初始快照上就失败，无法作为校准过的基线：{failed:?}");
        }
        let probe = Db::connect(isolated.as_str(), 2, true)?;
        let db = Arc::new(Db::connect_timeout(isolated.as_str(), pool, true, o.sql_timeout_secs)?);
        // 合成基准的留出题与手写标准答案；TPC-DS 库的留出题随条目给出，标准答案在每个变化下由原定义算出
        let defs: Vec<String> = ["M1", "M2", "M3", "M4", "M5"].iter().map(|s| s.to_string()).collect();
        let bench = libs.iter().any(|l| l.entries.iter().any(|e| !e.own_gold));
        let tasks = if bench { metricbench::tasks(&defs) } else { vec![] };

        // 每个库 × 维护方式 × G8 参照一个中间层实例，共用连接池；按顺序评估，数据库耗时按前后差值归属
        let mut runs: Vec<Run> = vec![];
        for (li, lib) in libs.iter().enumerate() {
            for policy in &o.policies {
                if policy == "tabletest" {
                    continue; // 不经中间层，见下面的表级测试基线
                }
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
            let mut gold = metricbench::gold_map(&admin, &tasks).await?;
            for lib in &libs {
                for e in lib.entries.iter().filter(|e| e.own_gold && affected(e, ch)) {
                    for (id, ask) in &e.held {
                        let v = match metric::compile(&e.metric, ask) {
                            Ok(sql) => answer(&probe, &sql).await,
                            Err(err) => format!("ERROR: {err:#}"),
                        };
                        gold.insert(id.clone(), v);
                    }
                }
            }
            let hidden = ch.apply_hidden(&admin).await?;
            eprintln!("变化 {}（{}）：写入 {truth} + {hidden} 行", ch.name(), ch.syn().label());
            let mut memo: HashMap<String, String> = HashMap::new();
            // 不维护时原定义在变化后的数据上是否仍答对：区分必要与不必要的不可用
            let mut orig: BTreeMap<(usize, usize, String), (String, bool)> = BTreeMap::new();
            for (li, lib) in libs.iter().enumerate() {
                for (ei, e) in lib.entries.iter().enumerate().filter(|(_, e)| affected(e, ch)) {
                    for (id, ask) in &e.held {
                        let value = match metric::compile(&e.metric, ask) {
                            Ok(sql) => answer_memo(&probe, &sql, &mut memo).await,
                            Err(err) => format!("ERROR: {err:#}"),
                        };
                        let ok = same_value(&parse_answer(&value), &parse_answer(&gold[id]), metricbench::decimals(ask));
                        orig.insert((li, ei, id.clone()), (value, ok));
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
                    if !affected(e, ch) {
                        continue;
                    }
                    used += 1;
                    let v = r.mid.use_metric(&ctx, key).await?;
                    let valid = v["status"] == "valid";
                    let served: Option<Metric> = if valid { serde_json::from_value(v["metric"].clone()).ok() } else { None };
                    let revision = v["revision"].as_u64().unwrap_or(0) as u32;
                    for (tid, ask) in &e.held {
                        let (orig_value, orig_ok) = orig[&(r.lib, *ei, tid.clone())].clone();
                        let (value, ok) = match &served {
                            Some(m) => {
                                let value = match metric::compile(m, ask) {
                                    Ok(sql) => answer_memo(&probe, &sql, &mut memo).await,
                                    Err(err) => format!("ERROR: {err:#}"),
                                };
                                let ok = same_value(&parse_answer(&value), &parse_answer(&gold[tid]), metricbench::decimals(ask));
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
                            "task": tid, "status": v["status"], "revision": revision, "repaired": valid && revision != *rev,
                            "value": value, "gold": gold[tid], "orig_value": orig_value, "orig_ok": orig_ok, "class": class,
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
            // 表级测试基线：每个库视作一个 dbt 项目，变化后跑一遍全部测试，失败的表上的定义全部隔离，其余照原样提供
            if table_test {
                for (li, lib) in libs.iter().enumerate() {
                    let before = db.meter.snap();
                    let t0 = Instant::now();
                    let tests = table_tests(&db).await?;
                    let d = crate::db::diff(&before, &db.meter.snap());
                    let bad: BTreeSet<String> =
                        tests.iter().filter(|x| x["failed"] == true).map(|x| x["table"].as_str().unwrap_or_default().to_string()).collect();
                    let mut used = 0;
                    for (ei, e) in lib.entries.iter().enumerate().filter(|(_, e)| affected(e, ch)) {
                        used += 1;
                        let quarantined = e.metric.tables().iter().any(|t| bad.contains(t));
                        for (tid, _) in &e.held {
                            let (orig_value, orig_ok) = orig[&(li, ei, tid.clone())].clone();
                            let class = match (quarantined, orig_ok) {
                                (false, true) => "correct",
                                (false, false) => "served_wrong",
                                (true, false) => "unavailable_needed",
                                (true, true) => "unavailable_unneeded",
                            };
                            outcomes.push(json!({
                                "lib": lib.id, "policy": "tabletest", "oracle": "judge", "change": ch.name(), "entry": e.name, "def": e.def,
                                "task": tid, "status": if quarantined { "quarantined" } else { "valid" }, "revision": 0, "repaired": false,
                                "value": (!quarantined).then(|| orig_value.clone()), "gold": gold[tid], "orig_value": orig_value,
                                "orig_ok": orig_ok, "class": class,
                            }));
                        }
                    }
                    maint.push(json!({
                        "lib": lib.id, "policy": "tabletest", "oracle": "judge", "change": ch.name(), "entries_used": used,
                        "db_ms": d.db_ms, "queries": d.queries, "wall_ms": t0.elapsed().as_secs_f64() * 1000.0, "events": tests,
                    }));
                }
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
            "changes": changes.iter().map(|c| json!({"name": c.name(), "label": c.syn().label(), "class": c.syn().class(), "tables": c.tables(),
                                                     "describe": c.syn().describe()})).collect::<Vec<_>>(),
            "methodology": {
                "schema": if o.schema == "tpcds" { "真实 TPC-DS 数据（dsdgen）上的同名变化，库为模板导出的定义，标准答案 = 原定义在业务事实变化后、表示变化前的值" } else { "合成零售数据" },
                "pairing": "每个库在各维护方式下各有一个中间层实例，准入、变化、留出题完全相同；每个变化从 v1 施加，结束后回滚并恢复各实例的准入快照",
                "answer": "答案 = 当时提供的修订的规范 SQL 在当前数据上的结果；不提供（撤销或候选）记为不可用",
                "classes": "correct / served_wrong（提供了但答错：过期使用或错误修复）/ unavailable_needed（原定义已答错）/ unavailable_unneeded（原定义仍答对）",
                "oracle": "judge = 学习题判题 SQL；example = 智能体学习时自己写的 SQL；只影响修复的 G8",
                "tabletest": "dbt 式表级测试基线：按初始快照校准的 unique / not_null / relationships 测试，变化后全部重跑，失败的表上的定义全部隔离，不修复",
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
