//! 指标经验评测：学习 → 参数 / 题型留出 → 正常新增 → 已建模的破坏性 ETL（v2）。
//! 在独立数据库上生成合成零售数据；查询 Agent 与提炼器都调用真实模型。协议见 docs/metric-experience-protocol.md。

use crate::catalog;
use crate::db::{diff, lit, Db, QKind};
use crate::etl;
use crate::knowledge::{Basis, Content, Status};
use crate::llm::{self, AgentRun, Provider};
use crate::metric::{self, parse_answer, same_value, Ask, Period, Trajectory};
use crate::middle::{tool_specs_with, Ctx, GuardMode, Maint, Middle, MiddleConfig, Scope, SqlCall, TaskLog, ToolSpec};
use anyhow::{ensure, Context, Result};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    /// 门店销售行数（目录渠道为其一半）
    #[arg(long, default_value_t = 1_000_000, value_parser = clap::value_parser!(u32).range(10_000..=20_000_000))]
    rows: u32,
    /// 查询 Agent 的模型服务（配置写在 .env，如 deepseek 读 DEEPSEEK_*，zhipu 读 ZHIPU_*，cline 读 CLINE_*）
    #[arg(long, default_value = "openai", value_parser = ["openai", "deepseek", "zhipu", "cline", "anthropic", "claude"])]
    agent: String,
    /// 提炼器的模型服务
    #[arg(long, default_value = "openai", value_parser = ["openai", "deepseek", "zhipu", "cline", "anthropic", "claude"])]
    extractor: String,
    /// metric-global 为条件级维护；-schema / -revoke / -def 只改变维护方式（只看结构、逐写入撤销后重新提炼、定义级重验）
    #[arg(long, value_delimiter = ',', default_value = "direct,middle,metric-local,metric-global,metric-global-noguard",
          value_parser = ["direct", "middle", "metric-local", "metric-global", "metric-global-noguard",
                          "metric-global-schema", "metric-global-revoke", "metric-global-def"])]
    modes: Vec<String>,
    #[arg(long, value_delimiter = ',', default_value = "defined,named", value_parser = ["defined", "named"])]
    phrasings: Vec<String>,
    #[arg(long, value_delimiter = ',', default_value = "M1,M2,M3,M4", value_parser = ["M1", "M2", "M3", "M4"])]
    metrics: Vec<String>,
    /// 做留出题的 Agent；学习只由 A 完成，默认由未接触过指标的 B 做留出
    #[arg(long, value_delimiter = ',', default_value = "B")]
    holdout_agents: Vec<String>,
    #[arg(long, default_value_t = 1, value_parser = clap::value_parser!(u32).range(1..=10))]
    repeats: u32,
    #[arg(long, default_value_t = 20, value_parser = clap::value_parser!(u32).range(1..=100))]
    max_steps: u32,
    #[arg(long, default_value_t = 2, value_parser = clap::value_parser!(u32).range(1..=5))]
    extract_attempts: u32,
    /// Agent 连接池（含中间层检查）的单条 SQL 超时，各组相同；行数很大时调高，避免粒度检查超时
    #[arg(long, default_value_t = 60, value_parser = clap::value_parser!(u64).range(10..=3600))]
    sql_timeout_secs: u64,
    /// 不对参与答案的 SQL 执行 EXPLAIN (ANALYZE, BUFFERS)
    #[arg(long)]
    no_explain: bool,
}

// ───────────────────────── 指标与题目 ─────────────────────────

struct Def {
    id: &'static str,
    name: &'static str,
    definition: &'static str,
    /// 受“正常新增”（补录 2002-09 门店销售）影响
    growth: bool,
    /// 受 v2（门店退货改为状态流水）影响
    v2: bool,
}

static DEFS: [Def; 4] = [
    Def {
        id: "M1",
        name: "门店营业额",
        definition: "门店营业额 = 门店销售行的净支付额（store_sales.ss_net_paid）之和，按销售日期归属期间",
        growth: true,
        v2: false,
    },
    Def {
        id: "M2",
        name: "门店退货金额",
        definition: "门店退货金额 = 门店退货的退货金额（store_returns.sr_return_amt）之和，按退货日期归属期间；每笔退货只计一次",
        growth: false,
        v2: true,
    },
    Def {
        id: "M3",
        name: "门店退货率",
        definition:
            "门店退货率（%）= 期间内售出的门店销售行所对应的退货金额（sr_return_amt）之和 ÷ 这些销售行的净支付额（ss_net_paid）之和 × 100；\
                     按销售日期归属期间，退货按小票号和商品与销售行对应，每笔退货只计一次",
        growth: true,
        v2: true,
    },
    Def {
        id: "M4",
        name: "目录渠道营业额",
        definition: "目录渠道营业额 = 目录销售行的净支付额（catalog_sales.cs_net_paid）之和，按销售日期归属期间",
        growth: false,
        v2: false,
    },
];

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum Set {
    Learn,
    /// 同题型换参数
    Param,
    /// 学习阶段未出现的题型
    Type,
}

struct Task {
    id: String,
    def: &'static Def,
    ask: Ask,
    set: Set,
}

fn tasks(ids: &[String]) -> Vec<Task> {
    let p = Period::month;
    let single = |y, m| Ask::Single { period: p(y, m) };
    let diff = |a: (i32, u32), b: (i32, u32)| Ask::Diff { a: p(a.0, a.1), b: p(b.0, b.1) };
    let plan = |id: &str| -> Vec<(Set, Ask)> {
        match id {
            "M1" => vec![
                (Set::Learn, single(2001, 3)),
                (Set::Learn, single(2000, 11)),
                (Set::Param, single(2002, 9)),
                (Set::Type, diff((2002, 9), (2001, 6))),
                (Set::Type, Ask::RankMonth { year: 2002 }),
            ],
            "M2" => vec![
                (Set::Learn, single(2001, 4)),
                (Set::Learn, single(2000, 8)),
                (Set::Param, single(2002, 5)),
                (Set::Type, diff((2002, 3), (2001, 3))),
                (Set::Type, Ask::RankMonth { year: 2001 }),
            ],
            "M3" => vec![
                (Set::Learn, single(2001, 2)),
                (Set::Learn, single(2000, 7)),
                (Set::Param, single(2002, 9)),
                (Set::Type, diff((2002, 6), (2001, 6))),
                (Set::Type, Ask::RankMonth { year: 2001 }),
            ],
            _ => vec![
                (Set::Learn, single(2001, 5)),
                (Set::Learn, single(2000, 12)),
                (Set::Param, single(2002, 2)),
                (Set::Type, diff((2002, 2), (2001, 2))),
                (Set::Type, Ask::RankMonth { year: 2000 }),
            ],
        }
    };
    let mut out = vec![];
    for def in DEFS.iter().filter(|d| ids.iter().any(|x| x == d.id)) {
        let mut n: HashMap<&str, u32> = HashMap::new();
        for (set, ask) in plan(def.id) {
            let tag = match set {
                Set::Learn => "L",
                Set::Param => "P",
                Set::Type => "T",
            };
            let k = n.entry(tag).or_insert(0);
            *k += 1;
            out.push(Task { id: format!("{}-{tag}{k}", def.id), def, ask, set });
        }
    }
    out
}

fn cn(p: &Period) -> String {
    match (p.m1, p.m2) {
        (1, 12) => format!("{} 年", p.year),
        (a, b) if a == b => format!("{} 年 {a} 月", p.year),
        (a, b) => format!("{} 年 {a}–{b} 月", p.year),
    }
}

fn text(t: &Task, defined: bool) -> String {
    let n = t.def.name;
    let body = match &t.ask {
        Ask::Single { period } => format!("{}的{n}是多少？", cn(period)),
        Ask::Diff { a, b } => format!("{}的{n}比{}高多少？（用前者减去后者，结果可以为负数）", cn(a), cn(b)),
        Ask::RankMonth { year } => format!("{year} 年哪个月的{n}最高？"),
    };
    let fmt = if matches!(t.ask, Ask::RankMonth { .. }) { "只回答月份数字（1–12）。" } else { "保留两位小数。" };
    if defined {
        format!("{body}口径：{}。{fmt}", t.def.definition)
    } else {
        format!("{body}{fmt}")
    }
}

fn decimals(ask: &Ask) -> u32 {
    if matches!(ask, Ask::RankMonth { .. }) {
        0
    } else {
        2
    }
}

// ───────────────────────── 判题器（独立于 metric::compile 手写） ─────────────────────────

fn gold_period(def: &str, p: &Period) -> String {
    let when = format!("d_year = {} and d_moy between {} and {}", p.year, p.m1, p.m2);
    match def {
        "M1" => format!("select sum(s.ss_net_paid) from store_sales s join date_dim d on s.ss_sold_date_sk = d.d_date_sk where {when}"),
        "M2" => format!(
            "select sum(r.sr_return_amt) from store_returns r join date_dim d on r.sr_returned_date_sk = d.d_date_sk \
             where r.sr_status = '完成' and {when}"
        ),
        "M3" => format!(
            "with s as (select ss_ticket_number as t, ss_item_sk as i, ss_net_paid as paid from store_sales \
                        join date_dim on ss_sold_date_sk = d_date_sk where {when}) \
             select 100.0 * (select sum(r.sr_return_amt) from store_returns r join s on r.sr_ticket_number = s.t and r.sr_item_sk = s.i \
                             where r.sr_status = '完成') / (select sum(paid) from s)"
        ),
        _ => format!("select sum(c.cs_net_paid) from catalog_sales c join date_dim d on c.cs_sold_date_sk = d.d_date_sk where {when}"),
    }
}

fn gold_rank(def: &str, year: i32) -> String {
    match def {
        "M1" => format!(
            "select d_moy from store_sales join date_dim on ss_sold_date_sk = d_date_sk where d_year = {year} \
             group by d_moy order by sum(ss_net_paid) desc, d_moy limit 1"
        ),
        "M2" => format!(
            "select d_moy from store_returns join date_dim on sr_returned_date_sk = d_date_sk where d_year = {year} and sr_status = '完成' \
             group by d_moy order by sum(sr_return_amt) desc, d_moy limit 1"
        ),
        "M3" => format!(
            "with s as (select ss_ticket_number as t, ss_item_sk as i, ss_net_paid as paid, d_moy as mo from store_sales \
                        join date_dim on ss_sold_date_sk = d_date_sk where d_year = {year}), \
                  r as (select s.mo, sum(r.sr_return_amt) as amt from store_returns r join s on r.sr_ticket_number = s.t and r.sr_item_sk = s.i \
                        where r.sr_status = '完成' group by s.mo), \
                  p as (select mo, sum(paid) as paid from s group by mo) \
             select p.mo from p left join r using (mo) order by coalesce(r.amt, 0) / p.paid desc, p.mo limit 1"
        ),
        _ => format!(
            "select d_moy from catalog_sales join date_dim on cs_sold_date_sk = d_date_sk where d_year = {year} \
             group by d_moy order by sum(cs_net_paid) desc, d_moy limit 1"
        ),
    }
}

fn gold_sql(t: &Task) -> String {
    match &t.ask {
        Ask::Single { period } => gold_period(t.def.id, period),
        Ask::Diff { a, b } => format!("select ({}) - ({})", gold_period(t.def.id, a), gold_period(t.def.id, b)),
        Ask::RankMonth { year } => gold_rank(t.def.id, *year),
    }
}

/// 当前快照上全部题目的标准答案（task → 首个单元格）。
async fn gold_map(admin: &Db, tasks: &[Task]) -> Result<HashMap<String, String>> {
    let mut out = HashMap::new();
    for t in tasks {
        let v = admin.query(QKind::Meta, &gold_sql(t)).await?.cell(0, 0).unwrap_or("NULL").to_string();
        out.insert(t.id.clone(), v);
    }
    Ok(out)
}

// ───────────────────────── 数据 ─────────────────────────

pub(crate) fn fixture(n: u32) -> String {
    let half = n / 2;
    format!(
        r#"
create table date_dim (d_date_sk int primary key, d_date date not null, d_year int not null, d_moy int not null, d_dom int not null);
insert into date_dim select g, d, extract(year from d)::int, extract(month from d)::int, extract(day from d)::int
  from generate_series(1, 1096) g cross join lateral (select date '2000-01-01' + g - 1 as d) x;
comment on table date_dim is '日期维度：2000-01-01 至 2002-12-31';
comment on column date_dim.d_date_sk is '日期键';
comment on column date_dim.d_date is '日期';
comment on column date_dim.d_year is '年份';
comment on column date_dim.d_moy is '月份（1–12）';
comment on column date_dim.d_dom is '日（1–31）';
create table item (i_item_sk int primary key, i_category varchar(20), i_current_price numeric(7,2));
insert into item select g, (array['家居','服装','电子','食品','运动'])[1 + g % 5], 5 + g % 50 from generate_series(1, 1000) g;
comment on table item is '商品维度';
comment on column item.i_item_sk is '商品键';
comment on column item.i_category is '商品类别';
comment on column item.i_current_price is '当前标价';
create table store_sales (ss_sold_date_sk int, ss_item_sk int not null, ss_ticket_number int not null, ss_quantity int not null,
  ss_sales_price numeric(7,2) not null, ss_ext_sales_price numeric(12,2) not null, ss_ext_discount_amt numeric(12,2) not null,
  ss_net_paid numeric(12,2) not null, ss_net_paid_inc_tax numeric(12,2) not null, ss_net_profit numeric(12,2) not null);
insert into store_sales
select case when t % 97 = 0 then null else 1 + (t::bigint * 7919) % 1096 end, 1 + (g - 1) % 1000, t, q, p,
       q * p, round(q * p * disc, 2), q * p - round(q * p * disc, 2),
       round((q * p - round(q * p * disc, 2)) * 1.08, 2), round(q * p - round(q * p * disc, 2) - q * p * 0.6, 2)
from generate_series(1, {n}) g
cross join lateral (select (g - 1) / 5 + 1 as t, 1 + g % 9 as q, (5 + (g * 37) % 200)::numeric(7,2) as p, (g % 4) * 0.05 as disc) x;
comment on table store_sales is '门店销售明细：一行 = 一张小票中的一种商品';
comment on column store_sales.ss_sold_date_sk is '销售日期键（关联 date_dim.d_date_sk）';
comment on column store_sales.ss_item_sk is '商品键';
comment on column store_sales.ss_ticket_number is '小票号';
comment on column store_sales.ss_quantity is '数量';
comment on column store_sales.ss_sales_price is '单价';
comment on column store_sales.ss_ext_sales_price is '销售额（数量 × 单价，未扣折扣）';
comment on column store_sales.ss_ext_discount_amt is '折扣金额';
comment on column store_sales.ss_net_paid is '净支付额（销售额 − 折扣，不含税）';
comment on column store_sales.ss_net_paid_inc_tax is '含税净支付额';
comment on column store_sales.ss_net_profit is '净利润';
create table store_returns (sr_returned_date_sk int, sr_item_sk int not null, sr_ticket_number int not null, sr_return_quantity int not null,
  sr_return_amt numeric(12,2) not null, sr_return_tax numeric(12,2) not null, sr_fee numeric(12,2) not null, sr_net_loss numeric(12,2) not null);
insert into store_returns
select least(1096, ss_sold_date_sk + 1 + ss_ticket_number % 30), ss_item_sk, ss_ticket_number, ss_quantity, a, round(a * 0.08, 2), f, round(a * 0.5 + f, 2)
from store_sales
cross join lateral (select round(ss_net_paid * (0.3 + (ss_ticket_number % 7) * 0.1), 2) as a, (2 + ss_ticket_number % 5)::numeric(12,2) as f) x
where ss_sold_date_sk is not null and (ss_item_sk + ss_ticket_number) % 5 in (0, 1);
comment on table store_returns is '门店退货明细';
comment on column store_returns.sr_returned_date_sk is '退货日期键（关联 date_dim.d_date_sk）';
comment on column store_returns.sr_item_sk is '商品键';
comment on column store_returns.sr_ticket_number is '原小票号';
comment on column store_returns.sr_return_quantity is '退货数量';
comment on column store_returns.sr_return_amt is '退货金额（不含税）';
comment on column store_returns.sr_return_tax is '退货税额';
comment on column store_returns.sr_fee is '退货手续费';
comment on column store_returns.sr_net_loss is '退货净损失';
create table catalog_sales (cs_sold_date_sk int, cs_item_sk int not null, cs_order_number int not null, cs_quantity int not null,
  cs_ext_sales_price numeric(12,2) not null, cs_ext_discount_amt numeric(12,2) not null, cs_net_paid numeric(12,2) not null,
  cs_net_paid_inc_tax numeric(12,2) not null, cs_ext_ship_cost numeric(12,2) not null);
insert into catalog_sales
select case when o % 89 = 0 then null else 1 + (o::bigint * 6007) % 1096 end, 1 + (g * 7 - 1) % 1000, o, q,
       q * p, round(q * p * disc, 2), q * p - round(q * p * disc, 2), round((q * p - round(q * p * disc, 2)) * 1.08, 2), round(q * 1.5, 2)
from generate_series(1, {half}) g
cross join lateral (select (g - 1) / 4 + 1 as o, 1 + g % 7 as q, (8 + (g * 53) % 300)::numeric(7,2) as p, (g % 3) * 0.05 as disc) x;
comment on table catalog_sales is '目录渠道销售明细：一行 = 一个订单中的一种商品';
comment on column catalog_sales.cs_sold_date_sk is '销售日期键（关联 date_dim.d_date_sk）';
comment on column catalog_sales.cs_item_sk is '商品键';
comment on column catalog_sales.cs_order_number is '订单号';
comment on column catalog_sales.cs_quantity is '数量';
comment on column catalog_sales.cs_ext_sales_price is '销售额（数量 × 单价，未扣折扣）';
comment on column catalog_sales.cs_ext_discount_amt is '折扣金额';
comment on column catalog_sales.cs_net_paid is '净支付额（销售额 − 折扣，不含税）';
comment on column catalog_sales.cs_net_paid_inc_tax is '含税净支付额';
comment on column catalog_sales.cs_ext_ship_cost is '运费';
create index ss_key on store_sales (ss_ticket_number, ss_item_sk);
create index ss_date on store_sales (ss_sold_date_sk);
create index sr_key on store_returns (sr_ticket_number, sr_item_sk);
create index sr_date on store_returns (sr_returned_date_sk);
create index cs_date on catalog_sales (cs_sold_date_sk);
analyze date_dim; analyze item; analyze store_sales; analyze store_returns; analyze catalog_sales;
"#
    )
}

/// 补录的小票号偏移；原始小票号远小于它。
pub(crate) const GROWTH_OFFSET: i64 = 1_000_000_000;

async fn sales_dml(db: &Db) -> Result<i64> {
    Ok(catalog::versions(db).await?.get("store_sales").map(|v| v.dml).unwrap_or(0))
}

async fn has_growth(db: &Db) -> Result<bool> {
    let q = format!("select exists (select 1 from store_sales where ss_ticket_number > {GROWTH_OFFSET})");
    Ok(db.query(QKind::Meta, &q).await?.cell(0, 0) == Some("t"))
}

pub(crate) async fn log_batch(db: &Db, table: &str, note: &str) -> Result<()> {
    let q = format!(
        "insert into etl_batch_log select {t}, coalesce(max(batch_id), 0) + 1, {n}, now() from etl_batch_log where table_name = {t}",
        t = lit(table),
        n = lit(note)
    );
    db.query(QKind::Meta, &q).await?;
    Ok(())
}

/// 正常新增：复制 2002-09 的门店销售行并换新小票号，模拟补录。表结构、粒度与关联约束都不变，只有业务数值变化。
pub(crate) async fn apply_growth(db: &Db) -> Result<i64> {
    if has_growth(db).await? {
        return Ok(0);
    }
    let before = sales_dml(db).await?;
    db.query(
        QKind::Meta,
        &format!(
            "insert into store_sales select s.ss_sold_date_sk, s.ss_item_sk, s.ss_ticket_number + {GROWTH_OFFSET}, s.ss_quantity, \
             s.ss_sales_price, s.ss_ext_sales_price, s.ss_ext_discount_amt, s.ss_net_paid, s.ss_net_paid_inc_tax, s.ss_net_profit \
             from store_sales s join date_dim d on s.ss_sold_date_sk = d.d_date_sk where d.d_year = 2002 and d.d_moy = 9; \
             select pg_stat_force_next_flush()"
        ),
    )
    .await?;
    log_batch(db, "store_sales", "补录 2002-09 门店销售").await?;
    db.query(QKind::Meta, "analyze store_sales").await?;
    etl::wait_table_stats(db, "store_sales", before).await?;
    let q = format!("select count(*) from store_sales where ss_ticket_number > {GROWTH_OFFSET}");
    Ok(db.query(QKind::Meta, &q).await?.i64(0, 0).unwrap_or(0))
}

pub(crate) async fn reset_growth(db: &Db) -> Result<()> {
    if !has_growth(db).await? {
        return Ok(());
    }
    let before = sales_dml(db).await?;
    db.query(QKind::Meta, &format!("delete from store_sales where ss_ticket_number > {GROWTH_OFFSET}; select pg_stat_force_next_flush()"))
        .await?;
    log_batch(db, "store_sales", "撤回补录").await?;
    db.query(QKind::Meta, "vacuum analyze store_sales").await?;
    etl::wait_table_stats(db, "store_sales", before).await
}

// ───────────────────────── 分组配置 ─────────────────────────

/// (中间层配置, 是否提供中间层工具, 是否提供指标经验工具)。metric-local 与 metric-global 只改变指标经验的可见范围；
/// metric-global-* 只改变维护方式，条件、受限修复与回归相同。
fn config(mode: &str) -> (MiddleConfig, bool, bool) {
    let base = MiddleConfig { name: mode.into(), record: true, ..Default::default() };
    match mode {
        "direct" => (
            MiddleConfig {
                scope: Scope::Session,
                singleflight: false,
                guard: GuardMode::Off,
                feedback: false,
                validate_sql: false,
                result_cache: false,
                ..base
            },
            false,
            false,
        ),
        "middle" => (base, true, false),
        "metric-local" => {
            (MiddleConfig { metric_scope: Scope::Agent, metric_maint: Maint::Condition, cond_reuse: true, ..base }, true, true)
        }
        "metric-global" => (MiddleConfig { metric_maint: Maint::Condition, cond_reuse: true, ..base }, true, true),
        "metric-global-schema" => (MiddleConfig { metric_maint: Maint::Schema, ..base }, true, true),
        "metric-global-revoke" => (MiddleConfig { metric_maint: Maint::Revoke, ..base }, true, true),
        "metric-global-def" => (MiddleConfig { metric_maint: Maint::Definition, ..base }, true, true),
        _ => (MiddleConfig { metric_maint: Maint::Off, ..base }, true, true),
    }
}

const SYSTEM: &str = "你是一个数据分析 Agent，通过工具查询 PostgreSQL 上的零售数据（门店、目录两个渠道）。先弄清表结构与关联方式，再写 SQL；不要猜测列的含义。\
得到结果后调用 final_answer：answer 只写最终值（数字或月份数字，不带单位与说明）；used 写参与计算最终答案的查询编号（run_sql 返回的 ref，如 [\"r2\", \"r3\"]）；\
derivation 用这些编号写出最终答案的算式（如 \"r2 - r3\"；答案直接来自一条查询时写 \"r2\"）。\
如果题目的业务口径不明确，且无法从数据或工具得到可靠的定义，可以调用 ask_clarification 说明需要澄清的内容；调用后任务结束。";

const SYSTEM_METRIC: &str = "find_metric 返回中间层已验证的业务指标口径（含示例 SQL），可以作为参考。用某个口径写的 SQL，\
请在 run_sql 的 metrics 参数中声明 [{\"key\": ..., \"revision\": ...}]；中间层会在执行前核对该口径是否仍然有效。";

fn system(middle_tools: bool, metric_tools: bool) -> String {
    let mut s = SYSTEM.to_string();
    if middle_tools {
        s.push('\n');
        s.push_str(llm::SYSTEM_MIDDLE);
    }
    if metric_tools {
        s.push('\n');
        s.push_str(SYSTEM_METRIC);
    }
    s
}

// ───────────────────────── 运行 ─────────────────────────

struct Env<'a> {
    o: &'a Options,
    admin: &'a Db,
    /// 只读连接：EXPLAIN 与审计用，不计入中间层的数据库计量
    probe: &'a Db,
    agent: &'a Provider,
    extractor: &'a Provider,
    tasks: &'a [Task],
}

struct Cell<'a> {
    id: String,
    mode: &'a str,
    phrasing: &'a str,
    repeat: u32,
    system: String,
    tools: Vec<ToolSpec>,
}

struct Phase<'a> {
    env: &'a Env<'a>,
    mid: &'a Middle,
    cell: &'a Cell<'a>,
    name: &'a str,
    gold: &'a HashMap<String, String>,
    /// 阶段开始时在当前快照上给出错误答案的指标条目 (key, revision)
    bad: &'a HashSet<(String, u32)>,
}

struct TaskRec {
    json: Value,
    run: AgentRun,
    log: TaskLog,
    ctx: Ctx,
    question: String,
    correct: bool,
}

const FACTS: [&str; 3] = ["store_sales", "store_returns", "catalog_sales"];

/// (事实表扫描节点数, 按 Actual Loops 计的扫描次数)。并行扫描的 loops 含 worker，节点数更接近逻辑扫描次数。
fn fact_scans(plan: &Value) -> (f64, f64) {
    let is_fact = plan["Node Type"].as_str().is_some_and(|t| t.ends_with("Scan"))
        && plan["Relation Name"].as_str().is_some_and(|r| FACTS.contains(&r));
    let mut acc = if is_fact { (1.0, plan["Actual Loops"].as_f64().unwrap_or(1.0)) } else { (0.0, 0.0) };
    for p in plan["Plans"].as_array().into_iter().flatten() {
        let (n, l) = fact_scans(p);
        acc.0 += n;
        acc.1 += l;
    }
    acc
}

fn used_refs(run: &AgentRun) -> HashSet<usize> {
    let mut used: HashSet<usize> = run.used.iter().filter_map(|r| metric::ref_index(r)).collect();
    if let Some(d) = &run.derivation {
        used.extend(metric::refs_in(d).unwrap_or_default());
    }
    used
}

/// 任务结束后在只读连接上对参与答案的 SQL 执行 EXPLAIN (ANALYZE, BUFFERS)；没有声明时取最后一条。
async fn explain(probe: &Db, run: &AgentRun, log: &TaskLog) -> Value {
    let used = used_refs(run);
    let calls: Vec<&SqlCall> = if used.is_empty() {
        log.calls.last().into_iter().collect()
    } else {
        log.calls.iter().filter(|c| used.contains(&c.index)).collect()
    };
    let (mut ms, mut hit, mut read, mut nodes, mut loops, mut errors) = (0.0, 0.0, 0.0, 0.0, 0.0, 0);
    for c in &calls {
        match probe.query(QKind::Meta, &format!("explain (analyze, buffers, format json) {}", c.sql)).await {
            Ok(r) => {
                let v: Value = r.cell(0, 0).and_then(|s| serde_json::from_str(s).ok()).unwrap_or_default();
                ms += v[0]["Execution Time"].as_f64().unwrap_or(0.0);
                let plan = &v[0]["Plan"];
                hit += plan["Shared Hit Blocks"].as_f64().unwrap_or(0.0);
                read += plan["Shared Read Blocks"].as_f64().unwrap_or(0.0);
                let (n, l) = fact_scans(plan);
                nodes += n;
                loops += l;
            }
            Err(_) => errors += 1,
        }
    }
    json!({"sql": calls.len(), "exec_ms": ms, "shared_hit": hit, "shared_read": read, "fact_scan_nodes": nodes,
           "fact_scan_loops": loops, "errors": errors})
}

async fn run_task(ph: &Phase<'_>, agent: &str, t: &Task, defined: bool) -> Result<TaskRec> {
    let (env, mid, cell) = (ph.env, ph.mid, ph.cell);
    let question = text(t, defined);
    let ctx = Ctx::new(agent, &format!("{}-{}", cell.id, ph.name), &t.id);
    let gold = ph.gold.get(&t.id).cloned().unwrap_or_default();
    let before = mid.db.meter.snap();
    let r = llm::run_agent_with(env.agent, mid, &ctx, &question, &cell.system, &cell.tools, env.o.max_steps as usize).await;
    let d = diff(&before, &mid.db.meter.snap());
    let log = mid.take_task_log(&ctx);
    let (run, error) = match r {
        Ok(run) => (run, None),
        Err(e) => (AgentRun::default(), Some(format!("{e:#}"))),
    };
    let correct = run.answer.as_deref().is_some_and(|a| same_value(&parse_answer(a), &parse_answer(&gold), decimals(&t.ask)));
    let outcome = if error.is_some() {
        "error"
    } else if run.clarification.is_some() {
        "clarify"
    } else if correct {
        "correct"
    } else {
        "wrong"
    };
    let plan = if env.o.no_explain { Value::Null } else { explain(env.probe, &run, &log).await };
    let rejected_refs =
        log.rejections.iter().flat_map(|r| serde_json::from_value::<Vec<(String, u32)>>(r["metrics"].clone()).unwrap_or_default());
    let declared: Vec<(String, u32)> = log.calls.iter().flat_map(|c| c.metrics.iter().cloned()).chain(rejected_refs).collect();
    let bad = |x: &(String, u32)| ph.bad.contains(x);
    let usage = json!({
        "finds": log.finds,
        "found": log.found,
        "declared": declared,
        "bad_found": log.found.iter().filter(|x| bad(x)).count(),
        "bad_declared": declared.iter().filter(|x| bad(x)).count(),
        "bad_executed": log.calls.iter().filter(|c| c.metrics.iter().any(bad)).count(),
        "repaired_found": log.found.iter().filter(|x| x.1 > 0).count(),
    });
    eprintln!(
        "  {:<22} {:<8} {agent} {:<6} {:<8} 轮 {:>2} 工具 {:>2} 拦下 {} | 答 {} / 标准 {}",
        cell.id,
        ph.name,
        t.id,
        outcome,
        run.steps,
        run.tool_calls,
        log.rejections.len(),
        run.answer.clone().unwrap_or_default().chars().take(16).collect::<String>(),
        gold.chars().take(16).collect::<String>()
    );
    let json = json!({
        "cell": cell.id, "mode": cell.mode, "phrasing": cell.phrasing, "repeat": cell.repeat, "phase": ph.name, "agent": agent,
        "task": t.id, "metric": t.def.id, "set": t.set, "ask": t.ask, "defined": defined, "question": question,
        "gold": gold, "answer": run.answer, "outcome": outcome, "error": error, "run": run,
        "db": {"queries": d.queries, "ms": d.db_ms, "by_kind": d.by_kind}, "explain": plan, "metric_use": usage,
        "sql_calls": log.calls.len(), "rejections": log.rejections,
    });
    Ok(TaskRec { json, run, log, ctx, question, correct })
}

/// 学习任务的后续：判题成功且计算链通过后，离线提炼并提交晋升门槛。
async fn learn_step(env: &Env<'_>, mid: &Middle, rec: &TaskRec, t: &Task) -> Result<Value> {
    let traj = Trajectory {
        task: t.id.clone(),
        question: rec.question.clone(),
        ask: t.ask,
        basis: Basis::ExplicitQuestion { task: t.id.clone() },
        judged: rec.correct,
        decimals: decimals(&t.ask),
        answer: rec.run.answer.clone().unwrap_or_default(),
        used: rec.run.used.clone(),
        derivation: rec.run.derivation.clone(),
        judge: Some(gold_sql(t)),
    };
    if !traj.judged {
        return Ok(json!({"task": t.id, "stage": "judge", "reason": "来源任务未被判定为成功"}));
    }
    if let Err(e) = rec.log.verify(&traj) {
        return Ok(json!({"task": t.id, "stage": "chain", "reason": e}));
    }
    let input = mid.extract_input(&rec.ctx, &traj, &rec.log);
    let mut ex = metric::extract(env.extractor, &input, env.o.extract_attempts).await;
    let Some(draft) = ex.draft.take() else { return Ok(json!({"task": t.id, "stage": "extract", "extraction": ex})) };
    let before = mid.db.meter.snap();
    let t0 = Instant::now();
    let submit = mid.submit_metric(&rec.ctx, draft, &traj, &rec.log).await?;
    let d = diff(&before, &mid.db.meter.snap());
    eprintln!("  提炼 {} → {} {}", t.id, submit["event"].as_str().unwrap_or_default(), submit["failed_gate"].as_str().unwrap_or_default());
    Ok(json!({"task": t.id, "stage": "submitted", "extraction": ex, "submit": submit,
              "gate_db": {"queries": d.queries, "ms": d.db_ms}, "gate_seconds": t0.elapsed().as_secs_f64()}))
}

/// 评估用：已晋升（含撤销、修复）的口径在当前快照上是否答对其所属指标的全部留出题。
/// 使用留出题标准答案，但只进入报告，不进入提炼、晋升或修复。
async fn audit(env: &Env<'_>, mid: &Middle, gold: &HashMap<String, String>) -> Result<(Vec<Value>, HashSet<(String, u32)>)> {
    let mut rows = vec![];
    let mut bad = HashSet::new();
    for (fk, e, ev) in mid.metric_entries() {
        let Content::Metric(m) = &e.content else { continue };
        let repaired = ev.as_ref().is_some_and(|x| x.repaired);
        if matches!(e.status, Status::Candidate(_)) && !repaired {
            continue;
        }
        let def = ev.as_ref().and_then(|x| x.task.split('-').next().map(str::to_string)).unwrap_or_default();
        let mut wrong = vec![];
        let mut checked = 0;
        for t in env.tasks.iter().filter(|t| t.set != Set::Learn && t.def.id == def) {
            checked += 1;
            let expect = gold.get(&t.id).map(|g| parse_answer(g));
            let ok = match (metric::compile(m, &t.ask), expect) {
                (Ok(sql), Some(expect)) => match env.probe.query(QKind::Meta, &sql).await {
                    Ok(r) => r.cell(0, 0).is_some_and(|c| same_value(&parse_answer(c), &expect, decimals(&t.ask))),
                    Err(_) => false,
                },
                _ => false,
            };
            if !ok {
                wrong.push(t.id.clone());
            }
        }
        let ok = checked > 0 && wrong.is_empty();
        if !ok {
            bad.insert((e.key.clone(), e.revision));
        }
        let status_filter = m.filters.values().chain(m.joins.iter().flat_map(|j| j.filters.values())).any(|f| f.contains("sr_status"));
        rows.push(json!({"full_key": fk, "key": e.key, "revision": e.revision, "status": e.status, "metric_def": def,
                         "ok": ok, "wrong_on": wrong, "has_status_filter": status_filter, "repaired": repaired}));
    }
    Ok((rows, bad))
}

async fn cell(env: &Env<'_>, db: Arc<Db>, mode: &str, phrasing: &str, repeat: u32) -> Result<Value> {
    let (cfg, middle_tools, metric_tools) = config(mode);
    let mut tools = tool_specs_with(middle_tools, metric_tools);
    tools.push(llm::final_answer_spec(true));
    tools.push(llm::clarification_spec());
    let cell =
        Cell { id: format!("r{repeat}-{mode}-{phrasing}"), mode, phrasing, repeat, system: system(middle_tools, metric_tools), tools };
    eprintln!("== {}", cell.id);
    etl::reset(env.admin).await?;
    reset_growth(env.admin).await?;
    let mid = Middle::new(db, cfg).await?;
    let defined = phrasing == "defined";
    let mut records = vec![];
    let mut learning = vec![];
    let mut relearning = vec![];
    let mut audits = serde_json::Map::new();
    let mut events = serde_json::Map::new();
    let t0 = Instant::now();

    // 学习：A 用带口径的题面完成；直连组没有跨任务状态，跳过
    if mode != "direct" {
        let gold = gold_map(env.admin, env.tasks).await?;
        let none = HashSet::new();
        let ph = Phase { env, mid: &mid, cell: &cell, name: "learn", gold: &gold, bad: &none };
        for t in env.tasks.iter().filter(|t| t.set == Set::Learn) {
            let rec = run_task(&ph, "A", t, true).await?;
            if metric_tools {
                learning.push(learn_step(env, &mid, &rec, t).await?);
            }
            records.push(rec.json);
        }
    }
    events.insert("learn".into(), json!(mid.take_metric_events()));

    for phase in ["holdout", "growth", "v2"] {
        match phase {
            "growth" => eprintln!("  正常新增：补录 {} 行", apply_growth(env.admin).await?),
            "v2" => eprintln!("  ETL v2：新增“申请”行 {} 条", etl::apply_v2(env.admin).await?),
            _ => {}
        }
        mid.invalidate_versions();
        let gold = gold_map(env.admin, env.tasks).await?;
        let (rows, bad) = audit(env, &mid, &gold).await?;
        audits.insert(phase.into(), json!(rows));
        // 逐写入撤销组的恢复：写入通知到达即撤销依赖有写入的口径，再由 A 用带口径题面在新快照上重新学习与提炼。
        // 重新学习的任务记为 *-relearn 阶段，成本单列，不计入答案统计。
        if phase != "holdout" && mid.cfg.metric_maint == Maint::Revoke {
            let sweeper = Ctx::new("A", &format!("{}-{phase}-sweep", cell.id), "sweep");
            let swept = mid.sweep_metrics(&sweeper).await?;
            let defs: HashSet<String> = swept
                .iter()
                .filter(|x| x["after"]["status"] != "valid")
                .filter_map(|x| x["task"].as_str().and_then(|t| t.split('-').next()).map(str::to_string))
                .collect();
            let name = if phase == "growth" { "growth-relearn" } else { "v2-relearn" };
            let ph = Phase { env, mid: &mid, cell: &cell, name, gold: &gold, bad: &bad };
            let t1 = Instant::now();
            for t in env.tasks.iter().filter(|t| t.set == Set::Learn && defs.contains(t.def.id)) {
                let rec = run_task(&ph, "A", t, true).await?;
                let step = learn_step(env, &mid, &rec, t).await?;
                relearning.push(json!({"phase": phase, "step": step}));
                records.push(rec.json);
            }
            relearning.push(json!({"phase": phase, "swept": swept, "seconds": t1.elapsed().as_secs_f64()}));
        }
        let ph = Phase { env, mid: &mid, cell: &cell, name: phase, gold: &gold, bad: &bad };
        let set: Vec<&Task> = env
            .tasks
            .iter()
            .filter(|t| t.set != Set::Learn)
            .filter(|t| match phase {
                "growth" => t.def.growth,
                "v2" => t.def.v2,
                _ => true,
            })
            .collect();
        for agent in &env.o.holdout_agents {
            for t in &set {
                records.push(run_task(&ph, agent, t, defined).await?.json);
            }
        }
        events.insert(phase.into(), json!(mid.take_metric_events()));
        if phase == "v2" {
            audits.insert("v2_end".into(), json!(audit(env, &mid, &gold).await?.0));
        }
    }
    Ok(json!({
        "cell": cell.id, "mode": mode, "phrasing": phrasing, "repeat": repeat, "seconds": t0.elapsed().as_secs_f64(),
        "learning": learning, "relearning": relearning, "audits": audits, "events": events,
        "metric_report": mid.metric_report(), "stats": mid.stats_json(), "records": records,
    }))
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    ensure!(
        !o.holdout_agents.is_empty() && o.holdout_agents.iter().all(|a| !a.trim().is_empty() && !a.contains(['/', '|'])),
        "holdout-agents 不能为空，名称不能含 / 或 |"
    );
    let agent = Provider::from_env(&o.agent)?;
    let extractor = Provider::from_env(&o.extractor)?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_metric_{}_{stamp}", std::process::id());
    let directory = format!("{out}/metric-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await.context("创建隔离实验库失败（需要 CREATEDB）")?;
    let result: Result<Value> = async {
        let admin = Db::connect(isolated.as_str(), 2, false)?;
        eprintln!("生成合成零售数据：门店销售 {} 行，目录销售 {} 行", o.rows, o.rows / 2);
        admin.query(QKind::Meta, &fixture(o.rows)).await?;
        etl::setup(&admin).await?;
        let mut dataset = serde_json::Map::new();
        for t in ["store_sales", "store_returns", "catalog_sales", "date_dim", "item"] {
            let n = admin.query(QKind::Meta, &format!("select count(*) from {t}")).await?.i64(0, 0).unwrap_or(0);
            dataset.insert(t.into(), json!(n));
        }
        let probe = Db::connect(isolated.as_str(), 2, true)?;
        let db = Arc::new(Db::connect_timeout(isolated.as_str(), pool, true, o.sql_timeout_secs)?);
        let tasks = tasks(&o.metrics);
        let env = Env { o: &o, admin: &admin, probe: &probe, agent: &agent, extractor: &extractor, tasks: &tasks };
        let mut cells = vec![];
        for r in 1..=o.repeats {
            // 每轮轮换组的执行顺序
            for k in 0..o.modes.len() {
                let mode = &o.modes[(k + r as usize - 1) % o.modes.len()];
                for phrasing in &o.phrasings {
                    let c = cell(&env, db.clone(), mode, phrasing, r).await?;
                    std::fs::write(format!("{directory}/cell-{}.json", c["cell"].as_str().unwrap_or("cell")), serde_json::to_string_pretty(&c)?)?;
                    cells.push(c);
                }
            }
        }
        Ok(json!({
            "options": o, "pool": pool,
            "providers": {"agent": agent.label(), "extractor": extractor.label(), "temperature": "未设置（服务端默认）",
                          "agent_config": agent.config(), "extractor_config": extractor.config()},
            "dataset": dataset,
            "tasks": tasks.iter().map(|t| json!({"id": t.id, "metric": t.def.id, "set": t.set, "ask": t.ask, "growth": t.def.growth, "v2": t.def.v2})).collect::<Vec<_>>(),
            "methodology": {
                "learning": "学习题由 A 用带口径题面完成；直连组没有跨任务状态，不跑学习",
                "holdout": "留出题由 holdout_agents 完成；参数留出与题型留出分开统计",
                "judge": "手写参考 SQL 在同一快照上执行，按答案精度比较；学习题判题结果用于 G2 与 G8，留出题只用于评分与审计",
                "growth": "复制 2002-09 门店销售行并换新小票号；结构、粒度与关联约束不变",
                "v2": "etl::apply_v2：2001-10-01 起的门店退货增加“申请”行",
                "audit": "阶段开始时按留出题检查每条已晋升口径的规范 SQL；答错者记为不正确口径，用于统计过期使用与误撤销",
                "explain": "任务结束后在只读连接上执行 EXPLAIN (ANALYZE, BUFFERS)，不计入中间层计量，但会影响后续缓存状态",
                "order": "组的执行顺序按轮换；同一数据库顺序运行，不清空 OS/PG 缓存",
                "maintenance": "metric-local / metric-global 条件级重验并复用同一版本上的条件结论（关联守卫与粒度修复也复用）；\
                                -def 定义级重验（首次使用时重跑全部条件）；-schema 只看表结构；\
                                -revoke 写入通知后撤销，再由 A 在新快照上重新学习与提炼（记为 *-relearn）。条件、受限修复与回归相同；\
                                middle 组不复用条件结论",

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
            println!("指标经验评测报告：{directory}/report.md");
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

fn f(v: &Value) -> f64 {
    v.as_f64().unwrap_or(0.0)
}

fn mean(rs: &[&Value], g: impl Fn(&Value) -> f64) -> String {
    if rs.is_empty() {
        return "—".into();
    }
    format!("{:.1}", rs.iter().map(|r| g(r)).sum::<f64>() / rs.len() as f64)
}

fn events<'a>(cell: &'a Value, phase: &str, kind: &str) -> Vec<&'a Value> {
    cell["events"][phase].as_array().into_iter().flatten().filter(|e| e["event"] == kind).collect()
}

/// 评分阶段的任务（不含学习与逐写入撤销组的重新学习）。
fn is_eval(r: &Value) -> bool {
    matches!(r["phase"].as_str(), Some("holdout" | "growth" | "v2"))
}

/// 维护方式对照：待验证后通过、正式撤销与修复、逐写入撤销后重新提炼分开计数，条件按处理方式计数。
fn maintenance_section(metric_cells: &[&Value], recs: &[&Value]) -> String {
    let mut s = String::from(
        "\n## 6. 依赖表有写入后的维护\n\n\
         各组的条件、受限修复与回归相同，只有维护方式不同。刷新：待验证，重查通过后继续使用；撤销后修复 / 撤销未恢复：条件不成立而正式撤销，\
         随后受限修复，回归通过与否；需重新提炼：逐写入撤销，只能由 A 重新学习。\
         条件处理（跳过/复用/执行/强制/交给关联经验）：跳过＝读到的表未变化；复用＝同一版本上已有同一条件或蕴含它的结论；执行＝本次访问数据库（含在途合并）；\
         强制＝定义级重验重跑关联守卫；交给关联经验＝由关联经验按其守卫涉及的表决定是否重跑。维护 DB 按事件内计量，本评测顺序执行，不混入其他请求。\n\n",
    );
    let mut rows = vec![];
    for c in metric_cells {
        for (phase, pl) in [("growth", "正常新增后"), ("v2", "ETL v2 后")] {
            let ms = events(c, phase, "maintenance");
            let out = |o: &str| ms.iter().filter(|e| e["outcome"] == o).count().to_string();
            let mut acts: BTreeMap<String, usize> = BTreeMap::new();
            for x in ms.iter().flat_map(|e| e["conditions"].as_array().into_iter().flatten()) {
                *acts.entry(x["action"].as_str().unwrap_or("?").to_string()).or_default() += 1;
            }
            let act = |a: &str| acts.get(a).copied().unwrap_or(0);
            let relearn = format!("{phase}-relearn");
            let rel: Vec<&Value> = recs.iter().copied().filter(|r| r["cell"] == c["cell"] && r["phase"] == relearn.as_str()).collect();
            let steps: Vec<&Value> =
                c["relearning"].as_array().into_iter().flatten().filter(|x| x["phase"] == phase && x.get("step").is_some()).collect();
            let promoted =
                steps.iter().filter(|x| matches!(x["step"]["submit"]["event"].as_str(), Some("promoted" | "corroborated"))).count();
            let tokens: f64 = rel.iter().map(|r| f(&r["run"]["input_tokens"]) + f(&r["run"]["output_tokens"])).sum::<f64>()
                + steps
                    .iter()
                    .map(|x| f(&x["step"]["extraction"]["input_tokens"]) + f(&x["step"]["extraction"]["output_tokens"]))
                    .sum::<f64>();
            let secs: f64 = rel.iter().map(|r| f(&r["run"]["seconds"])).sum::<f64>()
                + steps.iter().map(|x| f(&x["step"]["extraction"]["seconds"]) + f(&x["step"]["gate_seconds"])).sum::<f64>();
            rows.push(vec![
                c["cell"].as_str().unwrap_or_default().into(),
                pl.into(),
                ms.len().to_string(),
                out("refreshed"),
                out("repaired"),
                out("revoked"),
                out("revoked_on_write"),
                events(c, phase, "maintenance_merged").len().to_string(),
                format!(
                    "{}/{}/{}/{}/{}",
                    act("skipped"),
                    act("reused") + act("implied"),
                    act("executed") + act("merged"),
                    act("forced"),
                    act("checked")
                ),
                events(c, phase, "repair_reused").len().to_string(),
                format!("{:.1}", ms.iter().map(|e| f(&e["wall_ms"])).sum::<f64>() / 1000.0),
                format!("{:.0}", ms.iter().map(|e| f(&e["db"]["ms"])).sum::<f64>()),
                if rel.is_empty() { "—".into() } else { format!("{promoted}/{}", rel.len()) },
                if rel.is_empty() { "—".into() } else { format!("{tokens:.0}") },
                if rel.is_empty() { "—".into() } else { format!("{secs:.0}") },
            ]);
        }
    }
    s.push_str(&md_table(
        &[
            "组",
            "阶段",
            "维护次数",
            "刷新",
            "撤销后修复",
            "撤销未恢复",
            "需重新提炼",
            "合并的并发维护",
            "条件：跳过/复用/执行/强制/交给关联经验",
            "修复复用",
            "维护墙钟 s",
            "维护 DB ms",
            "重新学习：晋升/任务",
            "重新学习 token",
            "重新学习 s",
        ],
        &rows,
    ));
    s
}

fn phrasing_label(p: &str) -> &'static str {
    if p == "defined" {
        "带口径"
    } else {
        "不带口径"
    }
}

fn markdown(report: &Value) -> String {
    let cells: Vec<&Value> = report["cells"].as_array().into_iter().flatten().collect();
    let recs: Vec<&Value> = cells.iter().flat_map(|c| c["records"].as_array().into_iter().flatten()).collect();
    let strs = |v: &Value| -> Vec<String> { v.as_array().into_iter().flatten().filter_map(|x| x.as_str().map(str::to_string)).collect() };
    let modes = strs(&report["options"]["modes"]);
    let phrasings = strs(&report["options"]["phrasings"]);
    let phases = [("holdout", "留出"), ("growth", "正常新增后"), ("v2", "ETL v2 后")];
    let mut s = format!(
        "# 指标经验评测\n\n查询 Agent：`{}`；提炼器：`{}`；温度：{}。数据：`{}`。\n\n\
         本报告是单次运行的描述性结果，不作显著性声明。协议见 docs/metric-experience-protocol.md。\n",
        report["providers"]["agent"].as_str().unwrap_or_default(),
        report["providers"]["extractor"].as_str().unwrap_or_default(),
        report["providers"]["temperature"].as_str().unwrap_or_default(),
        report["dataset"]
    );

    s.push_str("\n## 1. 答案\n\n两种题面分开报告。请求澄清单独计数，不算正确也不算错误；出错指模型或网络调用失败。\n");
    for ph in &phrasings {
        let mut rows = vec![];
        for mode in &modes {
            for (phase, pl) in phases {
                for (set, sl) in [("param", "参数留出"), ("type", "题型留出")] {
                    let rs: Vec<&Value> = recs
                        .iter()
                        .copied()
                        .filter(|r| r["phrasing"] == ph.as_str() && r["mode"] == mode.as_str() && r["phase"] == phase && r["set"] == set)
                        .collect();
                    if rs.is_empty() {
                        continue;
                    }
                    let n = |o: &str| rs.iter().filter(|r| r["outcome"] == o).count().to_string();
                    rows.push(vec![
                        mode.clone(),
                        pl.into(),
                        sl.into(),
                        rs.len().to_string(),
                        n("correct"),
                        n("wrong"),
                        n("clarify"),
                        n("error"),
                    ]);
                }
            }
        }
        s.push_str(&format!("\n### 题面：{}\n\n", phrasing_label(ph)));
        s.push_str(&md_table(&["组", "阶段", "题集", "题数", "正确", "错误", "请求澄清", "出错"], &rows));
    }

    s.push_str("\n## 2. 效率（留出阶段，出错除外）\n\n数据库一栏是任务期间中间层的全部查询；最终 SQL 一栏是参与答案的 SQL 的 EXPLAIN 结果，事后执行。\n\n");
    let mut rows = vec![];
    for ph in &phrasings {
        for mode in &modes {
            let rs: Vec<&Value> = recs
                .iter()
                .copied()
                .filter(|r| {
                    r["phrasing"] == ph.as_str() && r["mode"] == mode.as_str() && r["phase"] == "holdout" && r["outcome"] != "error"
                })
                .collect();
            if rs.is_empty() {
                continue;
            }
            rows.push(vec![
                phrasing_label(ph).into(),
                mode.clone(),
                rs.len().to_string(),
                mean(&rs, |r| f(&r["run"]["steps"])),
                mean(&rs, |r| f(&r["run"]["tool_calls"])),
                mean(&rs, |r| f(&r["run"]["input_tokens"])),
                mean(&rs, |r| f(&r["run"]["output_tokens"])),
                mean(&rs, |r| f(&r["run"]["seconds"])),
                mean(&rs, |r| f(&r["db"]["queries"])),
                mean(&rs, |r| f(&r["db"]["ms"])),
                mean(&rs, |r| f(&r["explain"]["exec_ms"])),
                mean(&rs, |r| f(&r["explain"]["shared_hit"]) + f(&r["explain"]["shared_read"])),
                mean(&rs, |r| f(&r["explain"]["fact_scan_nodes"])),
            ]);
        }
    }
    s.push_str(&md_table(
        &[
            "题面",
            "组",
            "题数",
            "LLM 轮数",
            "工具调用",
            "输入 token",
            "输出 token",
            "墙钟 s",
            "DB 查询",
            "DB ms",
            "最终 SQL ms",
            "最终 SQL 缓冲块",
            "事实表扫描节点",
        ],
        &rows,
    ));

    let metric_cells: Vec<&Value> = cells.iter().copied().filter(|c| c["mode"].as_str().is_some_and(|m| m.starts_with("metric"))).collect();

    s.push_str("\n## 3. 指标经验的产生\n\n“错误口径晋升”按 v1 留出题审计：已晋升口径的规范 SQL 答错任一留出题即计入。\n\n");
    let mut rows = vec![];
    for c in &metric_cells {
        let l: Vec<&Value> = c["learning"].as_array().into_iter().flatten().collect();
        let stage = |st: &str| l.iter().filter(|x| x["stage"] == st).count();
        let submitted: Vec<&Value> = l.iter().copied().filter(|x| x["stage"] == "submitted").collect();
        let promoted = submitted.iter().filter(|x| matches!(x["submit"]["event"].as_str(), Some("promoted" | "corroborated"))).count();
        let mut gates: BTreeMap<String, u32> = BTreeMap::new();
        for x in &submitted {
            if let Some(g) = x["submit"]["failed_gate"].as_str() {
                *gates.entry(g.to_string()).or_default() += 1;
            }
        }
        let gates = if gates.is_empty() {
            "—".to_string()
        } else {
            gates.iter().map(|(g, n)| format!("{g}×{n}")).collect::<Vec<_>>().join("，")
        };
        let tok = |k: &str| l.iter().map(|x| f(&x["extraction"][k])).sum::<f64>();
        let v1: Vec<&Value> = c["audits"]["holdout"].as_array().into_iter().flatten().collect();
        let wrong = v1.iter().filter(|x| x["ok"] == false).count();
        let filt = v1.iter().filter(|x| matches!(x["metric_def"].as_str(), Some("M2" | "M3")) && x["has_status_filter"] == true).count();
        let m23 = v1.iter().filter(|x| matches!(x["metric_def"].as_str(), Some("M2" | "M3"))).count();
        rows.push(vec![
            c["cell"].as_str().unwrap_or_default().into(),
            l.len().to_string(),
            (l.len() - stage("judge")).to_string(),
            (l.len() - stage("judge") - stage("chain")).to_string(),
            submitted.len().to_string(),
            promoted.to_string(),
            gates,
            format!("{:.0}/{:.0}", tok("input_tokens"), tok("output_tokens")),
            format!("{:.1}", tok("seconds")),
            format!("{:.0}", l.iter().map(|x| f(&x["gate_db"]["ms"])).sum::<f64>()),
            format!("{wrong}/{}", v1.len()),
            format!("{filt}/{m23}"),
        ]);
    }
    s.push_str(&md_table(
        &[
            "组",
            "学习题",
            "判定成功",
            "计算链通过",
            "提炼成功",
            "晋升",
            "候选（首个未过门槛）",
            "提炼 token 入/出",
            "提炼 s",
            "门槛 DB ms",
            "错误口径晋升",
            "M2/M3 口径含状态过滤",
        ],
        &rows,
    ));

    s.push_str("\n## 4. 检索与声明（留出、正常新增、v2 合计）\n\n");
    let mut rows = vec![];
    for c in &metric_cells {
        let rs: Vec<&Value> = recs.iter().copied().filter(|r| r["cell"] == c["cell"] && is_eval(r)).collect();
        let hit: Vec<&Value> = rs.iter().copied().filter(|r| r["metric_use"]["found"].as_array().is_some_and(|a| !a.is_empty())).collect();
        let declared = hit.iter().filter(|r| r["metric_use"]["declared"].as_array().is_some_and(|a| !a.is_empty())).count();
        let rejected: usize = ["holdout", "growth", "v2"].iter().map(|p| events(c, p, "ref_rejected").len()).sum();
        rows.push(vec![
            c["cell"].as_str().unwrap_or_default().into(),
            rs.len().to_string(),
            rs.iter().filter(|r| f(&r["metric_use"]["finds"]) > 0.0).count().to_string(),
            hit.len().to_string(),
            declared.to_string(),
            rejected.to_string(),
        ]);
    }
    s.push_str(&md_table(&["组", "任务", "调用 find_metric", "命中有效口径", "命中后声明引用", "引用被执行端拒绝"], &rows));

    s.push_str(
        "\n## 5. 过期与撤销\n\n“不正确口径”指阶段开始时审计答错留出题的口径。误撤销：被撤销的条目在该阶段审计中并无错误。\
         使用修复口径：find_metric 返回了修订号大于 0 的条目。\n\n",
    );
    let mut rows = vec![];
    for c in &metric_cells {
        for (phase, pl) in phases {
            let rs: Vec<&Value> = recs.iter().copied().filter(|r| r["cell"] == c["cell"] && r["phase"] == phase).collect();
            let cnt = |k: &str| rs.iter().filter(|r| f(&r["metric_use"][k]) > 0.0).count().to_string();
            let bad: HashSet<(String, u64)> = c["audits"][phase]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|x| x["ok"] == false)
                .map(|x| (x["key"].as_str().unwrap_or_default().to_string(), x["revision"].as_u64().unwrap_or(0)))
                .collect();
            let revoked = events(c, phase, "revoked");
            let false_rev = revoked
                .iter()
                .filter(|e| !bad.contains(&(e["key"].as_str().unwrap_or_default().to_string(), e["revision"].as_u64().unwrap_or(0))))
                .count();
            let repaired: Vec<&Value> = rs.iter().copied().filter(|r| f(&r["metric_use"]["repaired_found"]) > 0.0).collect();
            let failed = events(c, phase, "repair_rejected").len()
                + events(c, phase, "repair_failed").len()
                + events(c, phase, "repair_skipped").len();
            rows.push(vec![
                c["cell"].as_str().unwrap_or_default().into(),
                pl.into(),
                cnt("bad_found"),
                cnt("bad_declared"),
                cnt("bad_executed"),
                revoked.len().to_string(),
                false_rev.to_string(),
                events(c, phase, "repair_candidate").len().to_string(),
                events(c, phase, "repair_promoted").len().to_string(),
                failed.to_string(),
                format!("{}/{}", repaired.iter().filter(|r| r["outcome"] == "correct").count(), repaired.len()),
            ]);
        }
    }
    s.push_str(&md_table(
        &[
            "组",
            "阶段",
            "检索到不正确口径",
            "声明引用不正确口径",
            "执行了引用不正确口径的 SQL",
            "撤销",
            "误撤销",
            "修复候选",
            "修复恢复有效",
            "修复被拒 / 失败 / 跳过",
            "使用修复口径的任务（正确/总数）",
        ],
        &rows,
    ));
    let mut rows = vec![];
    for c in &metric_cells {
        let end: Vec<&Value> =
            c["audits"]["v2_end"].as_array().into_iter().flatten().filter(|x| x["repaired"] == true && x["status"] == "Valid").collect();
        rows.push(vec![
            c["cell"].as_str().unwrap_or_default().into(),
            end.len().to_string(),
            end.iter().filter(|x| x["ok"] == false).count().to_string(),
        ]);
    }
    s.push_str("\n修复后恢复有效的口径，在 v2 结束时的审计：\n\n");
    s.push_str(&md_table(&["组", "修复后有效的口径", "其中答错留出题"], &rows));

    s.push_str(&maintenance_section(&metric_cells, &recs));

    s.push_str(
        "\n## 7. 成本\n\n提炼与晋升门槛不在请求路径上；守卫、守护、受限修复与 G8 回归在 find_metric 与 run_sql 的请求路径上。\
         离开请求路径不代表成本消失。逐写入撤销组的重新学习与提炼见第 6 节，不计入本表。\n\n",
    );
    let mut rows = vec![];
    for c in &metric_cells {
        let l: Vec<&Value> = c["learning"].as_array().into_iter().flatten().collect();
        let tokens: f64 = l.iter().map(|x| f(&x["extraction"]["input_tokens"]) + f(&x["extraction"]["output_tokens"])).sum();
        let gate_ms: f64 = l.iter().map(|x| f(&x["gate_db"]["ms"])).sum();
        let rs: Vec<&Value> = recs.iter().copied().filter(|r| r["cell"] == c["cell"] && is_eval(r)).collect();
        let guard_ms: f64 = rs
            .iter()
            .map(|r| f(&r["db"]["by_kind"]["guard"][1]) + f(&r["db"]["by_kind"]["metric"][1]) + f(&r["db"]["by_kind"]["repair"][1]))
            .sum();
        let hits = rs.iter().filter(|r| r["metric_use"]["found"].as_array().is_some_and(|a| !a.is_empty())).count();
        rows.push(vec![
            c["cell"].as_str().unwrap_or_default().into(),
            format!("{tokens:.0}"),
            format!("{gate_ms:.0}"),
            format!("{guard_ms:.0}"),
            hits.to_string(),
            if hits > 0 { format!("{:.0}", tokens / hits as f64) } else { "—".into() },
        ]);
    }
    s.push_str(&md_table(
        &["组", "提炼 token", "门槛 DB ms", "请求路径守卫、守护与修复 DB ms", "命中任务", "每个命中任务分摊的提炼 token"],
        &rows,
    ));

    s.push_str(
        "\n## 说明\n\n\
         - 判题器与数据、任务生成器同源，不是外部确认的业务金标准。\n\
         - 直连组不跑学习；带口径题面下所有组得到相同的业务定义。\n\
         - 指标守护的结果依赖任务顺序：关联重验证和粒度修复会写入经验库，影响后续 run_sql 审查。顺序固定，见逐任务记录。\n\
         - 受限修复与 G8 使用学习集判题器，实验之外需要业务方确认。\n\
         - EXPLAIN 在任务结束后执行，会改变后续任务的缓存状态。\n",
    );
    s
}

pub fn md_table(headers: &[&str], rows: &[Vec<String>]) -> String {
    let mut s = format!("| {} |\n|{}|\n", headers.join(" | "), headers.iter().map(|_| "---").collect::<Vec<_>>().join("|"));
    for r in rows {
        s.push_str(&format!("| {} |\n", r.join(" | ")));
    }
    s
}
