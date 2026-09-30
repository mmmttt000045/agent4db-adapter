//! 维护方式对照（不调用 LLM）：同一批已晋升口径、同一串数据变化、同样的使用方式下，对比四种维护方式：
//! 逐写入撤销（撤销后重新提交，代替重新学习与提炼）、只看结构、定义级重验（依赖表有写入即待验证，首次使用时重跑该定义的全部条件）
//! 与条件级重验。要回答的是：条件级维护相对定义级重验，在重验范围、跨定义复用、并发合并与可用性上有没有额外收益，
//! 而不只是“保留定义比删除定义好”。
//!
//! 口径按族生成，同族定义共享同一批条件（事实表粒度、时间关联；比率口径另外共享门店销售与退货的关联）。
//! 共享度越低、写入涉及的条件越多，两种重验越接近。协议见 docs/metric-experience-protocol.md“维护方式对照”。

use crate::catalog;
use crate::db::{diff, Db, QKind};
use crate::etl;
use crate::knowledge::{Basis, Content, EmptyRule, JoinKind, JoinRef, Metric, Status, TimeSpec};
use crate::metric::{self, parse_answer, same_value, Ask, Period};
use crate::metricbench::{self, md_table, GROWTH_OFFSET};
use crate::middle::{Ctx, Maint, Middle, MiddleConfig};
use anyhow::{Context, Result};
use rand::{rngs::StdRng, seq::SliceRandom, SeedableRng};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    /// 门店销售行数（目录渠道为其一半）
    #[arg(long, default_value_t = 1_000_000, value_parser = clap::value_parser!(u32).range(10_000..=20_000_000))]
    rows: u32,
    /// condition-scope：条件级重验但不复用条件结论（只看重验范围）；condition：再加上同一版本条件结论的跨定义复用
    #[arg(long, value_delimiter = ',', default_value = "revoke,schema,definition,condition-scope,condition",
          value_parser = ["revoke", "schema", "definition", "condition-scope", "condition"])]
    policies: Vec<String>,
    /// 每次变化后使用口径的 Agent 数；每个 Agent 按各自的随机顺序把全部口径各用一次
    #[arg(long, default_value_t = 8, value_parser = clap::value_parser!(u32).range(1..=64))]
    agents: u32,
    /// staggered：Agent 依次到达，前一个用完全部口径后下一个才开始；burst：变化后全部 Agent 同时开始
    #[arg(long, value_delimiter = ',', default_value = "staggered,burst", value_parser = ["staggered", "burst"])]
    arrivals: Vec<String>,
    /// 共享度：每个口径族取前 k 个口径（族不足 k 个时取全部），可给多个值做扫描，如 1,2,4,6；6 为全部 19 个
    #[arg(long, value_delimiter = ',', default_value = "6", value_parser = clap::value_parser!(u32).range(1..=6))]
    share: Vec<u32>,
    #[arg(long, default_value_t = 1, value_parser = clap::value_parser!(u32).range(1..=10))]
    repeats: u32,
    #[arg(long, default_value_t = 42)]
    seed: u64,
}

// ───────────────────────── 口径族 ─────────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum Family {
    /// 门店销售单表：条件为 store_sales 粒度、store_sales⋈date_dim
    Store,
    /// 门店退货单表（按退货日）：条件为 store_returns 粒度、store_returns⋈date_dim
    Returns,
    /// 门店退货比率（按销售日）：门店销售的两个条件，外加 store_sales⋈store_returns
    Ratio,
    /// 目录渠道单表：条件为 catalog_sales 粒度、catalog_sales⋈date_dim
    Catalog,
}

impl Family {
    /// (事实表, 粒度键, 时间键)
    fn fact(self) -> (&'static str, [&'static str; 2], &'static str) {
        match self {
            Family::Store | Family::Ratio => ("store_sales", ["ss_ticket_number", "ss_item_sk"], "ss_sold_date_sk"),
            Family::Returns => ("store_returns", ["sr_ticket_number", "sr_item_sk"], "sr_returned_date_sk"),
            Family::Catalog => ("catalog_sales", ["cs_order_number", "cs_item_sk"], "cs_sold_date_sk"),
        }
    }
}

struct Spec {
    name: &'static str,
    family: Family,
    /// 单表口径的求和列；比率口径的分子列（门店退货表）
    num: &'static str,
    /// 比率口径的分母列（门店销售表）
    den: Option<&'static str>,
}

static SPECS: [Spec; 19] = [
    Spec { name: "门店营业额", family: Family::Store, num: "ss_net_paid", den: None },
    Spec { name: "门店销售额", family: Family::Store, num: "ss_ext_sales_price", den: None },
    Spec { name: "门店含税营业额", family: Family::Store, num: "ss_net_paid_inc_tax", den: None },
    Spec { name: "门店净利润", family: Family::Store, num: "ss_net_profit", den: None },
    Spec { name: "门店折扣额", family: Family::Store, num: "ss_ext_discount_amt", den: None },
    Spec { name: "门店销量", family: Family::Store, num: "ss_quantity", den: None },
    Spec { name: "门店退货金额", family: Family::Returns, num: "sr_return_amt", den: None },
    Spec { name: "门店退货税额", family: Family::Returns, num: "sr_return_tax", den: None },
    Spec { name: "门店退货手续费", family: Family::Returns, num: "sr_fee", den: None },
    Spec { name: "门店退货净损失", family: Family::Returns, num: "sr_net_loss", den: None },
    Spec { name: "门店退货数量", family: Family::Returns, num: "sr_return_quantity", den: None },
    Spec { name: "门店退货率", family: Family::Ratio, num: "sr_return_amt", den: Some("ss_net_paid") },
    Spec { name: "门店退货数量占比", family: Family::Ratio, num: "sr_return_quantity", den: Some("ss_quantity") },
    Spec { name: "门店退货损失率", family: Family::Ratio, num: "sr_net_loss", den: Some("ss_net_paid") },
    Spec { name: "目录渠道营业额", family: Family::Catalog, num: "cs_net_paid", den: None },
    Spec { name: "目录渠道销售额", family: Family::Catalog, num: "cs_ext_sales_price", den: None },
    Spec { name: "目录渠道含税营业额", family: Family::Catalog, num: "cs_net_paid_inc_tax", den: None },
    Spec { name: "目录渠道运费", family: Family::Catalog, num: "cs_ext_ship_cost", den: None },
    Spec { name: "目录渠道销量", family: Family::Catalog, num: "cs_quantity", den: None },
];

/// 共享度 k：每个族取前 k 个。k 越小，共享同一条件的口径越少（门店销售族与比率族之间仍共享门店销售的条件）。
fn specs(share: u32) -> Vec<&'static Spec> {
    SPECS
        .iter()
        .enumerate()
        .filter(|(i, s)| SPECS[..*i].iter().filter(|x| x.family == s.family).count() < share as usize)
        .map(|(_, s)| s)
        .collect()
}

fn spec_of(key: &str) -> Option<&'static Spec> {
    let name = key.strip_prefix("metric:")?;
    SPECS.iter().find(|s| s.name == name)
}

/// 提交的口径与 metricbench 提炼出的同类口径结构相同：单表求和，或按小票号与商品左关联退货的比率。
fn metric(s: &Spec) -> Metric {
    let (fact, grain, date_col) = s.family.fact();
    let (measure, definition) = match s.den {
        Some(den) => (
            format!("100.0 * sum({}) / sum({den})", s.num),
            format!("{} = 期间内售出的门店销售行对应的退货 {} 之和 ÷ 这些销售行的 {den} 之和 × 100，每笔退货只计一次", s.name, s.num),
        ),
        None => (format!("sum({})", s.num), format!("{} = {fact}.{} 之和", s.name, s.num)),
    };
    let role = if s.family == Family::Returns { "退货日" } else { "销售日" };
    let joins = if s.family == Family::Ratio {
        vec![JoinRef {
            key: String::new(),
            left: "store_sales".into(),
            right: "store_returns".into(),
            on: vec![("ss_ticket_number".into(), "sr_ticket_number".into()), ("ss_item_sk".into(), "sr_item_sk".into())],
            kind: JoinKind::Left,
            filters: BTreeMap::new(),
            cardinality: String::new(),
            loss_ratio: 0.0,
            revision: 0,
        }]
    } else {
        vec![]
    };
    Metric {
        name: s.name.into(),
        aliases: vec![],
        definition,
        fact: fact.into(),
        measure,
        grain: grain.iter().map(|c| c.to_string()).collect(),
        time: Some(TimeSpec {
            role: role.into(),
            fact_col: date_col.into(),
            dim: "date_dim".into(),
            dim_col: "d_date_sk".into(),
            grain: "month".into(),
        }),
        joins,
        filters: BTreeMap::new(),
        empty: EmptyRule::Unspecified,
        caveats: vec![],
        examples: vec![],
        basis: Basis::None,
    }
}

/// 判题查询：独立于 metric::compile 手写；门店退货只计“完成”行（每笔退货一次）。
fn gold(s: &Spec, p: &Period) -> String {
    let when = format!("d.d_year = {} and d.d_moy between {} and {}", p.year, p.m1, p.m2);
    match (s.family, s.den) {
        (Family::Ratio, Some(den)) => format!(
            "with s as (select ss_ticket_number as t, ss_item_sk as i, {den} as v from store_sales \
                        join date_dim d on ss_sold_date_sk = d.d_date_sk where {when}) \
             select 100.0 * (select sum(r.{num}) from store_returns r join s on r.sr_ticket_number = s.t and r.sr_item_sk = s.i \
                             where r.sr_status = '完成') / (select sum(v) from s)",
            num = s.num
        ),
        (Family::Returns, _) => format!(
            "select sum(r.{}) from store_returns r join date_dim d on r.sr_returned_date_sk = d.d_date_sk \
             where r.sr_status = '完成' and {when}",
            s.num
        ),
        _ => {
            let (fact, _, date_col) = s.family.fact();
            format!("select sum(f.{}) from {fact} f join date_dim d on f.{date_col} = d.d_date_sk where {when}", s.num)
        }
    }
}

/// 提交与回归（G7、G8）所用的学习参数；v2 影响这个月的退货。
fn learn_period() -> Period {
    Period::month(2002, 3)
}

/// 判定过期与误撤销的探测参数：四次变化都会改变这个月的某些答案。
fn probe_period() -> Period {
    Period::month(2002, 9)
}

/// 口径的规范 SQL 在当前快照上是否答对探测题。
async fn correct(probe: &Db, key: &str, m: &Metric) -> bool {
    let Some(s) = spec_of(key) else { return false };
    let p = probe_period();
    let Ok(sql) = metric::compile(m, &Ask::Single { period: p }) else { return false };
    match (probe.query(QKind::Meta, &sql).await, probe.query(QKind::Meta, &gold(s, &p)).await) {
        (Ok(a), Ok(b)) => same_value(&parse_answer(a.cell(0, 0).unwrap_or("NULL")), &parse_answer(b.cell(0, 0).unwrap_or("NULL")), 2),
        _ => false,
    }
}

// ───────────────────────── 数据变化 ─────────────────────────

/// 变化序列：三次正常追加分别落在不同的表上，最后一次是只改数据的破坏性变化。
const EVENTS: [(&str, &str); 4] = [
    ("sales-append", "门店销售追加（正常）"),
    ("returns-append", "门店退货追加（正常）"),
    ("catalog-append", "目录销售追加（正常）"),
    ("v2", "门店退货改为状态流水（破坏性，只改数据）"),
];

async fn exists(db: &Db, sql: &str) -> Result<bool> {
    Ok(db.query(QKind::Meta, &format!("select exists ({sql})")).await?.cell(0, 0) == Some("t"))
}

async fn count(db: &Db, sql: &str) -> Result<i64> {
    Ok(db.query(QKind::Meta, sql).await?.i64(0, 0).unwrap_or(0))
}

/// 执行一次写入，记 ETL 批次，并等 pg_stat 的 DML 计数刷新（否则同一次变化可能被感知两次）。
async fn write(db: &Db, table: &str, sql: &str, note: &str) -> Result<()> {
    let before = catalog::versions(db).await?.get(table).map(|v| v.dml).unwrap_or(0);
    db.query(QKind::Meta, &format!("{sql}; select pg_stat_force_next_flush()")).await?;
    metricbench::log_batch(db, table, note).await?;
    db.query(QKind::Meta, &format!("analyze {table}")).await?;
    etl::wait_table_stats(db, table, before).await
}

/// 返回新增或改动的行数。
async fn apply(db: &Db, event: &str) -> Result<i64> {
    match event {
        "sales-append" => metricbench::apply_growth(db).await,
        "returns-append" => {
            let q = format!("select 1 from store_returns where sr_ticket_number > {GROWTH_OFFSET}");
            if !exists(db, &q).await? {
                // 为补录的门店销售生成退货，规则与初始数据相同；新小票号不与已有键冲突
                let sql = format!(
                    "insert into store_returns (sr_returned_date_sk, sr_item_sk, sr_ticket_number, sr_return_quantity, sr_return_amt, \
                                                sr_return_tax, sr_fee, sr_net_loss) \
                     select least(1096, ss_sold_date_sk + 1 + ss_ticket_number % 30), ss_item_sk, ss_ticket_number, ss_quantity, a, \
                            round(a * 0.08, 2), f, round(a * 0.5 + f, 2) \
                     from store_sales \
                     cross join lateral (select round(ss_net_paid * (0.3 + (ss_ticket_number % 7) * 0.1), 2) as a, \
                                                (2 + ss_ticket_number % 5)::numeric(12,2) as f) x \
                     where ss_ticket_number > {GROWTH_OFFSET} and ss_sold_date_sk is not null and (ss_item_sk + ss_ticket_number) % 5 in (0, 1)"
                );
                write(db, "store_returns", &sql, "补录 2002-09 门店销售对应的退货").await?;
            }
            count(db, &format!("select count(*) from store_returns where sr_ticket_number > {GROWTH_OFFSET}")).await
        }
        "catalog-append" => {
            let q = format!("select 1 from catalog_sales where cs_order_number > {GROWTH_OFFSET}");
            if !exists(db, &q).await? {
                let sql = format!(
                    "insert into catalog_sales select c.cs_sold_date_sk, c.cs_item_sk, c.cs_order_number + {GROWTH_OFFSET}, c.cs_quantity, \
                            c.cs_ext_sales_price, c.cs_ext_discount_amt, c.cs_net_paid, c.cs_net_paid_inc_tax, c.cs_ext_ship_cost \
                     from catalog_sales c join date_dim d on c.cs_sold_date_sk = d.d_date_sk where d.d_year = 2002 and d.d_moy = 9"
                );
                write(db, "catalog_sales", &sql, "补录 2002-09 目录销售").await?;
            }
            count(db, &format!("select count(*) from catalog_sales where cs_order_number > {GROWTH_OFFSET}")).await
        }
        _ => etl::apply_v2(db).await,
    }
}

/// 回到初始数据：删掉“申请”行与三次补录。
async fn reset(db: &Db) -> Result<()> {
    etl::reset(db).await?;
    if exists(db, &format!("select 1 from store_returns where sr_ticket_number > {GROWTH_OFFSET}")).await? {
        write(db, "store_returns", &format!("delete from store_returns where sr_ticket_number > {GROWTH_OFFSET}"), "撤回补录退货").await?;
    }
    metricbench::reset_growth(db).await?;
    if exists(db, &format!("select 1 from catalog_sales where cs_order_number > {GROWTH_OFFSET}")).await? {
        write(db, "catalog_sales", &format!("delete from catalog_sales where cs_order_number > {GROWTH_OFFSET}"), "撤回补录目录销售")
            .await?;
    }
    Ok(())
}

/// 各组在相近的缓存状态下开始。
async fn warm(db: &Db) -> Result<()> {
    for t in ["store_sales", "store_returns", "catalog_sales", "date_dim"] {
        db.query(QKind::Meta, &format!("select count(*) from {t}")).await?;
    }
    Ok(())
}

// ───────────────────────── 运行 ─────────────────────────

struct Env<'a> {
    o: &'a Options,
    url: &'a str,
    pool: usize,
    admin: &'a Db,
    /// 只读连接：判定过期与误撤销，不计入中间层计量
    probe: &'a Db,
}

fn policy_of(p: &str) -> Maint {
    match p {
        "revoke" => Maint::Revoke,
        "schema" => Maint::Schema,
        "definition" => Maint::Definition,
        _ => Maint::Condition,
    }
}

fn s(v: &Value) -> String {
    v.as_str().unwrap_or_default().to_string()
}

fn f(v: &Value) -> f64 {
    v.as_f64().unwrap_or(0.0)
}

/// 当前有效的口径：键 → (修订号, 口径)。
fn snapshot(mid: &Middle) -> BTreeMap<String, (u64, Metric)> {
    mid.metric_entries()
        .into_iter()
        .filter(|(_, e, _)| e.status == Status::Valid)
        .filter_map(|(_, e, _)| match e.content {
            Content::Metric(m) => Some((e.key, (u64::from(e.revision), *m))),
            _ => None,
        })
        .collect()
}

/// 一个 Agent 按自己的随机顺序把全部口径各用一次（与执行端引用检查同一条守护路径）。
async fn agent_uses(mid: &Middle, agent: u32, event: &str, keys: &[String], seed: u64) -> Result<Vec<Value>> {
    let mut order = keys.to_vec();
    order.shuffle(&mut StdRng::seed_from_u64(seed.wrapping_mul(1_000_003).wrapping_add(u64::from(agent))));
    let name = format!("U{agent}");
    let ctx = Ctx::new(&name, event, "use");
    let mut out = vec![];
    for k in order {
        let t = Instant::now();
        let v = mid.use_metric(&ctx, &k).await?;
        out.push(json!({"agent": name, "key": k, "ms": t.elapsed().as_secs_f64() * 1000.0,
                        "status": v["status"], "revision": v["revision"], "metric": v["metric"]}));
    }
    Ok(out)
}

struct Run<'a> {
    env: &'a Env<'a>,
    mid: &'a Middle,
    db: &'a Db,
    arrival: &'a str,
    policy: Maint,
    keys: &'a [String],
}

impl Run<'_> {
    /// 一次变化之后的全部使用。`pre`：变化前有效的口径，用于判定误撤销（变化前的修订在变化后的快照上仍然正确，却被撤销）。
    async fn event(&self, event: &str, label: &str, seed: u64, pre: &BTreeMap<String, (u64, Metric)>) -> Result<Value> {
        let (mid, probe) = (self.mid, self.env.probe);
        let m0 = self.db.meter.snap();
        let t0 = Instant::now();
        let mut uses = vec![];
        if self.arrival == "burst" {
            let runs = futures::future::join_all((0..self.env.o.agents).map(|a| agent_uses(mid, a, event, self.keys, seed))).await;
            for r in runs {
                uses.extend(r?);
            }
        } else {
            for a in 0..self.env.o.agents {
                uses.extend(agent_uses(mid, a, event, self.keys, seed).await?);
            }
        }
        let wall = t0.elapsed().as_secs_f64();
        let d = diff(&m0, &self.db.meter.snap());
        let evs = mid.take_metric_events();

        let kind = |k: &str| evs.iter().filter(|e| e["event"] == k).count();
        let maint: Vec<&Value> = evs.iter().filter(|e| e["event"] == "maintenance").collect();
        let outcome = |o: &str| maint.iter().filter(|e| e["outcome"] == o).count();
        let mut conds: BTreeMap<String, u64> = BTreeMap::new();
        for x in maint.iter().flat_map(|e| e["conditions"].as_array().into_iter().flatten()) {
            *conds.entry(s(&x["action"])).or_default() += 1;
        }
        // 等待维护的使用：本次使用执行了维护，或合并进了别人正在做的维护
        let waited: BTreeSet<(String, String)> = evs
            .iter()
            .filter(|e| matches!(e["event"].as_str(), Some("maintenance" | "maintenance_merged")))
            .map(|e| (s(&e["agent"]), s(&e["key"])))
            .collect();
        let is_waited = |u: &Value| waited.contains(&(s(&u["agent"]), s(&u["key"])));

        // 过期使用：返回为有效的修订在当前快照上答错探测题
        let mut served: BTreeMap<(String, u64), bool> = BTreeMap::new();
        for u in uses.iter().filter(|u| u["status"] == "valid") {
            let k = (s(&u["key"]), u["revision"].as_u64().unwrap_or(0));
            if let std::collections::btree_map::Entry::Vacant(slot) = served.entry(k) {
                let ok = match serde_json::from_value::<Metric>(u["metric"].clone()) {
                    Ok(m) => correct(probe, &slot.key().0, &m).await,
                    Err(_) => false,
                };
                slot.insert(ok);
            }
        }
        let stale = uses
            .iter()
            .filter(|u| u["status"] == "valid" && served.get(&(s(&u["key"]), u["revision"].as_u64().unwrap_or(0))) == Some(&false))
            .count();
        // 变化后答错的变化前修订（应当被阻断的口径）
        let mut broken = vec![];
        for (k, (_, m)) in pre {
            if !correct(probe, k, m).await {
                broken.push(k.clone());
            }
        }
        let revoked: Vec<&Value> = evs.iter().filter(|e| e["event"] == "revoked").collect();
        let (mut false_rev, mut true_rev) = (0, 0);
        for e in &revoked {
            let key = s(&e["key"]);
            if pre.get(&key).is_some_and(|(rev, _)| e["revision"].as_u64() == Some(*rev)) {
                if broken.contains(&key) {
                    true_rev += 1;
                } else {
                    false_rev += 1;
                }
            }
        }
        let mut lat: Vec<f64> = uses.iter().map(|u| f(&u["ms"])).collect();
        lat.sort_by(|a, b| a.total_cmp(b));
        let q = |p: f64| if lat.is_empty() { 0.0 } else { lat[((lat.len() - 1) as f64 * p).round() as usize] };
        let n = |st: &str| uses.iter().filter(|u| u["status"] == st).count();

        // 逐写入撤销组的恢复：重新提交被撤销的口径，代替重新学习与提炼。LLM 成本不在本评测中（见 metricbench 的 *-relearn）；
        // 恢复之前的使用都记为不可用。
        let mut recovery = Value::Null;
        if self.policy == Maint::Revoke {
            let r0 = self.db.meter.snap();
            let t1 = Instant::now();
            let ctx = Ctx::new("admin", event, "reextract");
            let (mut tried, mut promoted, mut rejected) = (0, 0, vec![]);
            for e in revoked.iter().filter(|e| e["reextract"] == true) {
                let key = s(&e["key"]);
                let Some(sp) = spec_of(&key) else { continue };
                tried += 1;
                let v = mid.seed_metric(&ctx, metric(sp), Ask::Single { period: learn_period() }, 2, &gold(sp, &learn_period())).await?;
                if v["promoted"] == true {
                    promoted += 1;
                } else {
                    rejected.push(json!({"key": key, "failed_gate": v["failed_gate"], "reason": v["reason"]}));
                }
            }
            let rd = diff(&r0, &self.db.meter.snap());
            recovery = json!({"reextracted": tried, "promoted": promoted, "rejected": rejected, "seconds": t1.elapsed().as_secs_f64(),
                              "db": {"queries": rd.queries, "ms": rd.db_ms, "by_kind": rd.by_kind}});
            mid.take_metric_events();
        }

        let uses_out: Vec<Value> = uses
            .iter()
            .map(|u| {
                json!({"agent": u["agent"], "key": u["key"], "ms": u["ms"], "status": u["status"], "revision": u["revision"],
                            "waited": is_waited(u)})
            })
            .collect();
        let served_out: Vec<Value> = served.iter().map(|((k, r), ok)| json!({"key": k, "revision": r, "correct": ok})).collect();
        Ok(json!({
            "event": event, "label": label, "arrival": self.arrival, "wall_seconds": wall,
            "uses": uses.len(), "valid_uses": n("valid"), "unavailable_uses": n("unavailable"), "missing_uses": n("missing"),
            "stale_uses": stale,
            "waited_uses": uses.iter().filter(|&u| is_waited(u)).count(),
            "wait_ms": uses.iter().filter(|&u| is_waited(u)).map(|u| f(&u["ms"])).sum::<f64>(),
            "latency_ms": {"p50": q(0.5), "p95": q(0.95), "max": q(1.0), "sum": lat.iter().sum::<f64>()},
            "maintenance": {
                "episodes": maint.len(), "refreshed": outcome("refreshed"), "repaired": outcome("repaired"), "revoked": outcome("revoked"),
                "revoked_on_write": outcome("revoked_on_write"), "merged": kind("maintenance_merged"), "superseded": kind("maintenance_superseded"),
                "repair_reused": kind("repair_reused"), "repair_candidates": kind("repair_candidate"), "conditions": conds,
            },
            "revocations": revoked.len(), "true_revocations": true_rev, "false_revocations": false_rev, "broken_before": broken,
            "db": {"queries": d.queries, "ms": d.db_ms, "by_kind": d.by_kind},
            "served": served_out, "recovery": recovery, "uses_detail": uses_out, "events": evs,
        }))
    }
}

async fn cell(env: &Env<'_>, policy_name: &str, arrival: &str, repeat: u32, share: u32) -> Result<Value> {
    let policy = policy_of(policy_name);
    let id = format!("r{repeat}-k{share}-{policy_name}-{arrival}");
    eprintln!("== {id}");
    reset(env.admin).await?;
    warm(env.admin).await?;
    let db = Arc::new(Db::connect(env.url, env.pool, true)?);
    let cfg = MiddleConfig {
        name: format!("maint-{policy_name}"),
        metric_maint: policy,
        cond_reuse: policy_name == "condition",
        ..Default::default()
    };
    let mid = Middle::new(db.clone(), cfg).await?;

    // 准入：各组相同的口径、相同的门槛
    let ctx = Ctx::new("admin", "seed", "seed");
    let m0 = db.meter.snap();
    let t0 = Instant::now();
    let mut seeded = vec![];
    let chosen = specs(share);
    for sp in &chosen {
        seeded.push(mid.seed_metric(&ctx, metric(sp), Ask::Single { period: learn_period() }, 2, &gold(sp, &learn_period())).await?);
    }
    let ad = diff(&m0, &db.meter.snap());
    let keys: Vec<String> = seeded.iter().filter(|x| x["promoted"] == true).map(|x| s(&x["key"])).collect();
    eprintln!("  准入：{}/{} 条口径晋升", keys.len(), chosen.len());
    mid.take_metric_events();

    let run = Run { env, mid: &mid, db: db.as_ref(), arrival, policy, keys: &keys };
    let base = env.o.seed.wrapping_add(u64::from(repeat) * 1000);
    let mut events = vec![run.event("none", "无变化", base, &snapshot(&mid)).await?];
    for (i, (ev, label)) in EVENTS.iter().enumerate() {
        let pre = snapshot(&mid);
        let rows = apply(env.admin, ev).await?;
        mid.invalidate_versions();
        let mut v = run.event(ev, label, base + i as u64 + 1, &pre).await?;
        v["rows_changed"] = json!(rows);
        eprintln!(
            "  {:<15} 维护 {:>2} 次 | DB {:>4} 条 {:>8.0} ms | 等待 {:>3} 次 {:>7.1} s | 过期使用 {} | 误撤销 {} | 不可用 {}",
            ev,
            v["maintenance"]["episodes"],
            v["db"]["queries"],
            f(&v["db"]["ms"]),
            v["waited_uses"],
            f(&v["wait_ms"]) / 1000.0,
            v["stale_uses"],
            v["false_revocations"],
            v["unavailable_uses"]
        );
        events.push(v);
    }
    Ok(json!({
        "cell": id, "policy": policy_name, "arrival": arrival, "repeat": repeat, "share": share, "specs": chosen.len(), "agents": env.o.agents,
        "admission": {"seconds": t0.elapsed().as_secs_f64(), "promoted": keys.len(), "db": {"queries": ad.queries, "ms": ad.db_ms}, "entries": seeded},
        "events": events, "stats": mid.stats_json(),
    }))
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_maint_{}_{stamp}", std::process::id());
    let directory = format!("{out}/maint-{stamp}");
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
        let probe = Db::connect(isolated.as_str(), 2, true)?;
        let env = Env { o: &o, url: isolated.as_str(), pool, admin: &admin, probe: &probe };
        let mut cells = vec![];
        for r in 1..=o.repeats {
            for &share in &o.share {
                // 每轮轮换组的执行顺序
                for k in 0..o.policies.len() {
                    let p = &o.policies[(k + r as usize - 1) % o.policies.len()];
                    for a in &o.arrivals {
                        let c = cell(&env, p, a, r, share).await?;
                        std::fs::write(format!("{directory}/cell-{}.json", s(&c["cell"])), serde_json::to_string_pretty(&c)?)?;
                        cells.push(c);
                    }
                }
            }
        }
        let specs: Vec<Value> = SPECS
            .iter()
            .map(|sp| json!({"name": sp.name, "family": sp.family, "measure": metric(sp).measure, "fact": sp.family.fact().0}))
            .collect();
        Ok(json!({
            "options": o, "pool": pool, "specs": specs,
            "events": EVENTS.iter().map(|(e, l)| json!({"event": e, "label": l})).collect::<Vec<_>>(),
            "methodology": {
                "admission": "各组以相同的口径与判题查询走 G3、G4、G5、G7，不经提炼",
                "share": "共享度 k：每个口径族取前 k 个口径，族内口径共享同一批条件；门店销售族与比率族之间另外共享门店销售的粒度与时间关联",
                "use": "每次变化后 agents 个 Agent 各按随机顺序把全部口径用一次，走执行端引用检查同一条守护路径（use_metric）",
                "revoke": "逐写入撤销：依赖表有写入即撤销；本次变化的使用结束后重新提交（代替重新学习与提炼，LLM 成本不计），恢复前的使用记为不可用",
                "schema": "只看表结构：结构指纹不变就继续用",
                "definition": "定义级重验：依赖表有写入即待验证，首次使用时重跑全部条件（关联守卫强制重跑）；同一定义的并发维护合并，相同检查 SQL 在途合并",
                "condition_scope": "条件级重验：只重查读到了变化表的条件，关联经验在别处修订后按待验证处理；不复用条件结论",
                "condition": "condition-scope 之外，同一条件在同一版本上的结论跨定义复用（关联守卫、修复回归与粒度修复也复用）",
                "stale": "返回为有效的修订，其规范 SQL 在当前快照上答错探测题（2002-09）",
                "false_revocation": "变化前的修订在变化后的快照上仍答对探测题，却被撤销",
                "db": "中间层连接池的全部查询（含版本读取），按变化事件整体计量；判定过期用的只读连接不计入",
            },
            "cells": cells,
        }))
    }
    .await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    match result {
        Ok(mut report) => {
            report["database_cleaned_up"] = json!(cleanup.is_ok());
            std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
            std::fs::write(format!("{directory}/report.md"), markdown(&report))?;
            println!("维护方式对照报告：{directory}/report.md");
            cleanup.context("实验库清理失败")?;
            Ok(())
        }
        Err(error) => {
            std::fs::write(
                format!("{directory}/error.json"),
                serde_json::to_string_pretty(&json!({"error": format!("{error:#}"), "database_cleaned_up": cleanup.is_ok()}))?,
            )?;
            Err(error)
        }
    }
}

// ───────────────────────── 报告 ─────────────────────────

/// 一个组四次变化合计：[条件执行次数（含在途合并与定义级强制重跑）, 中间层 DB ms, 等待维护的总时长 s]。
fn totals(c: &Value) -> [f64; 3] {
    let mut t = [0.0; 3];
    for e in c["events"].as_array().into_iter().flatten().filter(|e| e["event"] != "none") {
        let cnt = |k: &str| e["maintenance"]["conditions"][k].as_f64().unwrap_or(0.0);
        t[0] += cnt("executed") + cnt("merged") + cnt("forced");
        t[1] += f(&e["db"]["ms"]);
        t[2] += f(&e["wait_ms"]) / 1000.0;
    }
    t
}

fn markdown(report: &Value) -> String {
    let cells: Vec<&Value> = report["cells"].as_array().into_iter().flatten().collect();
    let mut out = format!(
        "# 维护方式对照（不调用 LLM）\n\n口径数随共享度 k 变化（k = 6 为全部 {} 条），{} 个 Agent；每次变化后每个 Agent 把全部口径各用一次。\
         组名 r轮次-k共享度-维护方式-到达方式。本报告是描述性结果，不作显著性声明。协议见 docs/metric-experience-protocol.md。\n",
        SPECS.len(),
        report["options"]["agents"]
    );

    out.push_str("\n## 1. 准入（各组相同）\n\n");
    let rows: Vec<Vec<String>> = cells
        .iter()
        .map(|c| {
            vec![
                s(&c["cell"]),
                c["admission"]["promoted"].to_string(),
                format!("{:.1}", f(&c["admission"]["seconds"])),
                c["admission"]["db"]["queries"].to_string(),
                format!("{:.0}", f(&c["admission"]["db"]["ms"])),
            ]
        })
        .collect();
    out.push_str(&md_table(&["组", "晋升", "耗时 s", "DB 查询", "DB ms"], &rows));

    out.push_str(
        "\n## 2. 每次变化后的维护、可用性与正确性\n\n\
         维护结果：刷新＝待验证后重查通过；修复＝条件不成立、正式撤销后受限修复并通过回归；未恢复＝撤销后修复失败或不在修复范围；\
         重提＝逐写入撤销，只能重新提炼。条件（跳过/复用/执行/强制/交给关联经验）：跳过＝读到的表未变化；复用＝同一版本上已有同一条件或蕴含它的结论；\
         执行＝本次访问数据库（含在途合并）；强制＝定义级重跑关联守卫；交给关联经验＝由关联经验按其守卫涉及的表决定是否重跑。\
         DB 为中间层在该次变化后全部使用期间的查询（维护之外只有版本读取）。等待＝本次使用执行了维护或合并进了别人的维护。\
         过期使用＝返回为有效但答错探测题；误撤销＝变化前的修订仍然正确却被撤销；不可用＝返回撤销或候选状态。\n",
    );
    let arrivals: BTreeSet<String> = cells.iter().map(|c| s(&c["arrival"])).collect();
    for a in &arrivals {
        let mut rows = vec![];
        for c in cells.iter().filter(|c| s(&c["arrival"]) == *a) {
            for e in c["events"].as_array().into_iter().flatten().filter(|e| e["event"] != "none") {
                let m = &e["maintenance"];
                let cnt = |k: &str| m["conditions"][k].as_u64().unwrap_or(0);
                let kind = |k: &str| e["db"]["by_kind"][k][1].as_f64().unwrap_or(0.0);
                rows.push(vec![
                    s(&c["cell"]),
                    s(&e["event"]),
                    m["episodes"].to_string(),
                    format!("{}/{}/{}/{}", m["refreshed"], m["repaired"], m["revoked"], m["revoked_on_write"]),
                    m["merged"].to_string(),
                    format!(
                        "{}/{}/{}/{}/{}",
                        cnt("skipped"),
                        cnt("reused") + cnt("implied"),
                        cnt("executed") + cnt("merged"),
                        cnt("forced"),
                        cnt("checked")
                    ),
                    m["repair_reused"].to_string(),
                    e["db"]["queries"].to_string(),
                    format!("{:.0}", f(&e["db"]["ms"])),
                    format!("{:.0}/{:.0}/{:.0}", kind("guard") + kind("check"), kind("metric"), kind("repair")),
                    e["waited_uses"].to_string(),
                    format!("{:.1}", f(&e["wait_ms"]) / 1000.0),
                    format!("{:.0}", f(&e["latency_ms"]["p95"])),
                    format!("{:.0}", f(&e["latency_ms"]["max"])),
                    e["stale_uses"].to_string(),
                    e["false_revocations"].to_string(),
                    e["unavailable_uses"].to_string(),
                ]);
            }
        }
        out.push_str(&format!("\n### 到达方式：{a}\n\n"));
        out.push_str(&md_table(
            &[
                "组",
                "变化",
                "维护次数",
                "刷新/修复/未恢复/重提",
                "合并的并发维护",
                "条件：跳过/复用/执行/强制/交给关联经验",
                "修复复用",
                "DB 查询",
                "DB ms",
                "其中 守卫与关联检查/指标检查/修复 ms",
                "等待维护的使用",
                "等待总时长 s",
                "p95 ms",
                "最大 ms",
                "过期使用",
                "误撤销",
                "不可用",
            ],
            &rows,
        ));
    }

    out.push_str("\n## 3. 逐写入撤销组的恢复（重新提交）\n\n重新提交代替重新学习与提炼，不含 LLM 成本；真实的重新提炼成本见 metricbench 的 *-relearn 阶段。\n\n");
    let mut rows = vec![];
    for c in cells.iter().filter(|c| c["policy"] == "revoke") {
        for e in c["events"].as_array().into_iter().flatten().filter(|e| !e["recovery"].is_null()) {
            let r = &e["recovery"];
            rows.push(vec![
                s(&c["cell"]),
                s(&e["event"]),
                r["reextracted"].to_string(),
                r["promoted"].to_string(),
                format!("{:.1}", f(&r["seconds"])),
                format!("{:.0}", f(&r["db"]["ms"])),
            ]);
        }
    }
    out.push_str(&md_table(&["组", "变化", "重新提交", "通过门槛", "耗时 s", "DB ms"], &rows));

    out.push_str(
        "\n## 4. 按共享度汇总\n\n四次变化合计，多轮取平均。条件执行＝访问数据库的条件检查（含在途合并与定义级强制重跑的关联守卫，不含交给关联经验的）；DB ms 为中间层全部查询；\
         相对 definition＝同一共享度、同一到达方式下 DB ms 之比。共享度越低，condition 与 definition 应越接近。\n",
    );
    let shares: BTreeSet<u64> = cells.iter().filter_map(|c| c["share"].as_u64()).collect();
    for a in &arrivals {
        let mut rows = vec![];
        for k in &shares {
            let group: Vec<&&Value> = cells.iter().filter(|c| s(&c["arrival"]) == *a && c["share"].as_u64() == Some(*k)).collect();
            let mean = |p: &str| -> Option<[f64; 3]> {
                let g: Vec<[f64; 3]> = group.iter().filter(|c| c["policy"] == p).map(|c| totals(c)).collect();
                (!g.is_empty()).then(|| [0usize, 1, 2].map(|i| g.iter().map(|t| t[i]).sum::<f64>() / g.len() as f64))
            };
            let base = mean("definition");
            for p in ["revoke", "schema", "definition", "condition-scope", "condition"] {
                let Some(t) = mean(p) else { continue };
                rows.push(vec![
                    k.to_string(),
                    group.first().map(|c| c["specs"].to_string()).unwrap_or_default(),
                    p.to_string(),
                    format!("{:.0}", t[0]),
                    format!("{:.0}", t[1]),
                    format!("{:.1}", t[2]),
                    base.filter(|b| b[1] > 0.0).map_or("—".into(), |b| format!("{:.2}", t[1] / b[1])),
                ]);
            }
        }
        out.push_str(&format!("\n### 到达方式：{a}\n\n"));
        out.push_str(&md_table(&["共享度 k", "口径数", "组", "条件执行", "DB ms", "等待 s", "相对 definition"], &rows));
    }

    out.push_str(
        "\n## 说明\n\n\
         - 各组的条件、受限修复、回归与门槛相同；定义级组同样享有同一定义的维护合并与相同检查 SQL 的在途合并。\n\
         - 条件级的收益来自三处：读到的表未变化的条件不查（condition-scope 只有这一项）；同一条件在同一版本上的结论跨定义复用\
           （含关联守卫与修复回归，以及键列更少的已通过键唯一性蕴含的条件）；同表同键的粒度修复复用。definition 与 condition-scope 之差是重验范围，\
           condition-scope 与 condition 之差是跨定义复用。单个定义、条件不共享、或写入涉及定义的全部条件时，几种重验应当接近。\n\
         - burst 下定义级组的相同检查可能恰好同时在途而被合并，收益会小于 staggered。\n\
         - 判题器与数据、口径同源；探测题只有一个月份，过期与误撤销按这一题判定。\n\
         - 各组在同一数据库上顺序运行，不清空 OS/PG 缓存，执行顺序按轮换。\n",
    );
    out
}
