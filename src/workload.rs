//! 负载：TPC-DS 99 条标准查询的“探索需求”、退货率类任务的 SQL 与标准答案、给 LLM 的问题集。

use crate::catalog::Catalog;
use crate::checks::On;
use crate::sqlscan;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

// ───────────────────────── TPC-DS 99 条查询 → 每个任务要查明的表与关联 ─────────────────────────

#[derive(Clone, Debug, Serialize)]
pub struct TaskNeeds {
    pub id: u32,
    pub tables: Vec<String>,
    /// (多侧, 一侧, 关联列)；方向按“小表作一侧”的直觉给出，验证时两边都会试
    pub joins: Vec<(String, String, On)>,
}

#[derive(Deserialize)]
struct RawQuery {
    id: u32,
    sql: String,
}

pub fn tpcds_tasks(cat: &Catalog, path: &str) -> Result<Vec<TaskNeeds>> {
    let raw: Vec<RawQuery> = serde_json::from_str(&std::fs::read_to_string(path).with_context(|| format!("读取 {path}"))?)?;
    Ok(raw
        .into_iter()
        .map(|q| {
            let tables: Vec<String> = sqlscan::tables(&q.sql, cat).into_iter().collect();
            let joins = sqlscan::joins(&q.sql, cat)
                .into_iter()
                .map(|j| {
                    if cat.rows(&j.left) >= cat.rows(&j.right) {
                        (j.left, j.right, j.on)
                    } else {
                        (j.right, j.left, crate::checks::flip(&j.on))
                    }
                })
                .collect();
            TaskNeeds { id: q.id, tables, joins }
        })
        .collect())
}

/// (表探查总数, 关联验证总数, 不同表数, 不同关联数)
pub fn needs_summary(tasks: &[TaskNeeds]) -> (usize, usize, usize, usize) {
    let probes: usize = tasks.iter().map(|t| t.tables.len()).sum();
    let joins: usize = tasks.iter().map(|t| t.joins.len()).sum();
    let dt: BTreeSet<&String> = tasks.iter().flat_map(|t| t.tables.iter()).collect();
    let dj: BTreeSet<String> = tasks
        .iter()
        .flat_map(|t| t.joins.iter())
        .map(|(l, r, on)| {
            let mut v: Vec<String> = on.iter().map(|(a, b)| if a < b { format!("{a}={b}") } else { format!("{b}={a}") }).collect();
            v.sort();
            let (x, y) = if l < r { (l, r) } else { (r, l) };
            format!("{x}|{y}|{}", v.join(","))
        })
        .collect();
    (probes, joins, dt.len(), dj.len())
}

// ───────────────────────── 退货率任务 ─────────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Channel {
    Store,
    Catalog,
    Web,
}

impl Channel {
    pub const ALL: [Channel; 3] = [Channel::Store, Channel::Catalog, Channel::Web];

    pub fn name(self) -> &'static str {
        match self {
            Channel::Store => "门店",
            Channel::Catalog => "目录",
            Channel::Web => "网店",
        }
    }
    pub fn returns(self) -> &'static str {
        match self {
            Channel::Store => "store_returns",
            Channel::Catalog => "catalog_returns",
            Channel::Web => "web_returns",
        }
    }
    pub fn sales(self) -> &'static str {
        match self {
            Channel::Store => "store_sales",
            Channel::Catalog => "catalog_sales",
            Channel::Web => "web_sales",
        }
    }
    fn ret_amt(self) -> &'static str {
        match self {
            Channel::Store => "sr_return_amt",
            Channel::Catalog => "cr_return_amount",
            Channel::Web => "wr_return_amt",
        }
    }
    fn net_paid(self) -> &'static str {
        match self {
            Channel::Store => "ss_net_paid",
            Channel::Catalog => "cs_net_paid",
            Channel::Web => "ws_net_paid",
        }
    }
    pub fn sold_date(self) -> &'static str {
        match self {
            Channel::Store => "ss_sold_date_sk",
            Channel::Catalog => "cs_sold_date_sk",
            Channel::Web => "ws_sold_date_sk",
        }
    }
    /// 正确的退货→销售关联：(单号, 商品)
    pub fn correct_on(self) -> On {
        let p = |a: &str, b: &str| (a.to_string(), b.to_string());
        match self {
            Channel::Store => vec![p("sr_ticket_number", "ss_ticket_number"), p("sr_item_sk", "ss_item_sk")],
            Channel::Catalog => vec![p("cr_order_number", "cs_order_number"), p("cr_item_sk", "cs_item_sk")],
            Channel::Web => vec![p("wr_order_number", "ws_order_number"), p("wr_item_sk", "ws_item_sk")],
        }
    }
    /// 常见陷阱：只按单号关联
    pub fn trap_on(self) -> On {
        self.correct_on().into_iter().take(1).collect()
    }
    /// 标准答案需要的粒度过滤（只有门店退货表带状态列）
    pub fn gold_filter(self) -> Option<&'static str> {
        (self == Channel::Store).then_some("sr_status = '完成'")
    }
}

/// 销售期间：年份 + 月份区间。
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct Period {
    pub year: i32,
    pub m1: u32,
    pub m2: u32,
}

impl Period {
    pub fn year(y: i32) -> Period {
        Period { year: y, m1: 1, m2: 12 }
    }
    pub fn month(y: i32, m: u32) -> Period {
        Period { year: y, m1: m, m2: m }
    }
    pub fn label(&self) -> String {
        match (self.m1, self.m2) {
            (1, 12) => format!("{} 年", self.year),
            (a, b) if a == b => format!("{}-{:02}", self.year, a),
            (a, b) => format!("{} 年 {}–{} 月", self.year, a, b),
        }
    }
}

/// 退货率（%）= 这期间售出商品对应的退货金额 / 这期间的净支付额。
/// `ret_on`：(退货表列, 销售表列)；`date_on`：销售表日期键 = date_dim 键。
pub fn return_rate_sql(ch: Channel, p: Period, ret_on: &On, ret_filter: Option<&str>, date_on: &(String, String)) -> String {
    let keys: Vec<String> = ch.correct_on().into_iter().map(|(_, s)| s).collect();
    let jc: Vec<String> = ret_on.iter().map(|(r, s)| format!("r.{r} = s.{s}")).collect();
    let months = if (p.m1, p.m2) == (1, 12) { String::new() } else { format!(" and d_moy between {} and {}", p.m1, p.m2) };
    let filt = ret_filter.map(|f| format!(" where r.{f}")).unwrap_or_default();
    format!(
        "with s as (select {keys}, {paid} as paid from {sales} join date_dim on {dl} = {dr} where d_year = {y}{months}) \
         select round(100.0 * (select sum(r.{amt}) from {ret} r join s on {jc}{filt}) / (select sum(paid) from s), 4) as return_rate_pct",
        keys = keys.join(", "),
        paid = ch.net_paid(),
        sales = ch.sales(),
        dl = date_on.0,
        dr = date_on.1,
        y = p.year,
        amt = ch.ret_amt(),
        ret = ch.returns(),
        jc = jc.join(" and "),
    )
}

pub fn gold_return_rate_sql(ch: Channel, p: Period) -> String {
    return_rate_sql(ch, p, &ch.correct_on(), ch.gold_filter(), &(ch.sold_date().to_string(), "d_date_sk".to_string()))
}

// ───────────────────────── LLM 问题集 ─────────────────────────

#[derive(Clone, Debug, Serialize)]
pub struct Question {
    pub id: &'static str,
    pub text: &'static str,
    pub gold_sql: &'static str,
    /// 数值题按相对误差判分，否则按字符串相等
    pub numeric: bool,
    /// 是否受 v2 改版影响（改版后再问一遍）
    pub affected_by_v2: bool,
}

pub fn questions() -> Vec<Question> {
    vec![
        Question {
            id: "Q1",
            text: "2001 年售出的门店商品，退货率是多少？退货率 = 这些销售行对应的退货金额（sr_return_amt）之和 ÷ 这些销售行的净支付额（ss_net_paid）之和；按销售日期归属年份。用百分数回答，保留两位小数。",
            gold_sql: "with s as (select ss_ticket_number, ss_item_sk, ss_net_paid from store_sales join date_dim on ss_sold_date_sk = d_date_sk where d_year = 2001) \
                       select round(100.0 * (select sum(sr_return_amt) from store_returns r join s on r.sr_ticket_number = s.ss_ticket_number and r.sr_item_sk = s.ss_item_sk where r.sr_status = '完成') / (select sum(ss_net_paid) from s), 2)",
            numeric: true,
            affected_by_v2: false,
        },
        Question {
            id: "Q2",
            text: "2002 年 1–6 月售出的门店商品，退货率是多少？定义同上：对应退货金额（sr_return_amt）之和 ÷ 净支付额（ss_net_paid）之和，按销售日期归属期间。用百分数回答，保留两位小数。",
            gold_sql: "with s as (select ss_ticket_number, ss_item_sk, ss_net_paid from store_sales join date_dim on ss_sold_date_sk = d_date_sk where d_year = 2002 and d_moy between 1 and 6) \
                       select round(100.0 * (select sum(sr_return_amt) from store_returns r join s on r.sr_ticket_number = s.ss_ticket_number and r.sr_item_sk = s.ss_item_sk where r.sr_status = '完成') / (select sum(ss_net_paid) from s), 2)",
            numeric: true,
            affected_by_v2: true,
        },
        Question {
            id: "Q3",
            text: "2000 年售出的目录渠道商品，退货率是多少？退货率 = 对应退货金额（cr_return_amount）之和 ÷ 净支付额（cs_net_paid）之和，按销售日期归属年份。用百分数回答，保留两位小数。",
            gold_sql: "with s as (select cs_order_number, cs_item_sk, cs_net_paid from catalog_sales join date_dim on cs_sold_date_sk = d_date_sk where d_year = 2000) \
                       select round(100.0 * (select sum(cr_return_amount) from catalog_returns r join s on r.cr_order_number = s.cs_order_number and r.cr_item_sk = s.cs_item_sk) / (select sum(cs_net_paid) from s), 2)",
            numeric: true,
            affected_by_v2: false,
        },
        Question {
            id: "Q4",
            text: "2001 年售出的网店商品，退货率是多少？退货率 = 对应退货金额（wr_return_amt）之和 ÷ 净支付额（ws_net_paid）之和，按销售日期归属年份。用百分数回答，保留两位小数。",
            gold_sql: "with s as (select ws_order_number, ws_item_sk, ws_net_paid from web_sales join date_dim on ws_sold_date_sk = d_date_sk where d_year = 2001) \
                       select round(100.0 * (select sum(wr_return_amt) from web_returns r join s on r.wr_order_number = s.ws_order_number and r.wr_item_sk = s.ws_item_sk) / (select sum(ws_net_paid) from s), 2)",
            numeric: true,
            affected_by_v2: false,
        },
        Question {
            id: "Q5",
            text: "2001 年门店渠道哪个月的净支付额（ss_net_paid）合计最高？只回答月份数字（1–12）。",
            gold_sql: "select d_moy from store_sales join date_dim on ss_sold_date_sk = d_date_sk where d_year = 2001 group by d_moy order by sum(ss_net_paid) desc limit 1",
            numeric: true,
            affected_by_v2: false,
        },
        Question {
            id: "Q6",
            text: "2002 年售出的门店商品，扣除对应退货金额后的净销售额是多少？净销售额 = 净支付额（ss_net_paid）之和 − 这些销售行对应的退货金额（sr_return_amt）之和。四舍五入到整数。",
            gold_sql: "with s as (select ss_ticket_number, ss_item_sk, ss_net_paid from store_sales join date_dim on ss_sold_date_sk = d_date_sk where d_year = 2002) \
                       select round((select sum(ss_net_paid) from s) - (select sum(sr_return_amt) from store_returns r join s on r.sr_ticket_number = s.ss_ticket_number and r.sr_item_sk = s.ss_item_sk where r.sr_status = '完成'))",
            numeric: true,
            affected_by_v2: true,
        },
        Question {
            id: "Q7",
            text: "2001 年售出的门店商品中，退货率（对应退货金额 ÷ 净支付额）最高的商品类别（item.i_category）是哪个？只回答类别名。",
            gold_sql: "with s as (select ss_ticket_number, ss_item_sk, ss_net_paid, i_category from store_sales join date_dim on ss_sold_date_sk = d_date_sk join item on ss_item_sk = i_item_sk where d_year = 2001 and i_category is not null), \
                       r as (select s.i_category, sum(sr_return_amt) amt from store_returns r join s on r.sr_ticket_number = s.ss_ticket_number and r.sr_item_sk = s.ss_item_sk where r.sr_status = '完成' group by 1), \
                       t as (select i_category, sum(ss_net_paid) paid from s group by 1) \
                       select t.i_category from t join r using (i_category) order by r.amt / t.paid desc limit 1",
            numeric: false,
            affected_by_v2: false,
        },
        Question {
            id: "Q8",
            text: "2002 年 12 月（按退货日期）门店一共退了多少金额？即这段时间退货行的 sr_return_amt 之和，四舍五入到整数。",
            gold_sql: "select round(sum(sr_return_amt)) from store_returns join date_dim on sr_returned_date_sk = d_date_sk where d_year = 2002 and d_moy = 12 and sr_status = '完成'",
            numeric: true,
            affected_by_v2: true,
        },
    ]
}

/// 判分：数值题相对误差 < 0.5%；文字题忽略大小写与空白。
pub fn grade(answer: &str, gold: &str, numeric: bool) -> bool {
    if numeric {
        let num = |s: &str| -> Option<f64> {
            let cleaned: String = s.chars().filter(|c| c.is_ascii_digit() || *c == '.' || *c == '-').collect();
            cleaned.parse().ok()
        };
        match (num(answer), num(gold)) {
            (Some(a), Some(g)) => (a - g).abs() <= g.abs() * 0.005 + 1e-9,
            _ => false,
        }
    } else {
        answer.trim().to_lowercase().contains(&gold.trim().to_lowercase())
    }
}
