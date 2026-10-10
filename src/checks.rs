//! 验证检查：每种检查 = 一条 SQL + 一个判定。检查结果本身也作为知识共享。

use crate::db::Rows;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

/// 关联列对：(左表列, 右表列)
pub type On = Vec<(String, String)>;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(tag = "type")]
pub enum Check {
    /// 键唯一性：`table` 在 `cols` 上是否唯一（可带行过滤）。关联时“一侧”必须唯一，否则会膨胀。
    KeyUnique { table: String, cols: Vec<String>, filter: Option<String> },
    /// 抽样扇出：取左表若干行，按键去右表找匹配，看是否一行匹配多行。便宜，适合先查。
    SampleFanout { left: String, right: String, on: On, lf: Option<String>, rf: Option<String>, n: u32 },
    /// 行数守恒：关联后行数与左表行数对比（发现膨胀，并量化丢行）。
    RowConservation { left: String, right: String, on: On, lf: Option<String>, rf: Option<String> },
    /// 日期键连续：日期维度按（年, 月）分组后，每组的键恰好是 [min, max] 内的全部整数，且相邻月份首尾相接。
    /// 成立时任一期间的日期键集合就是一个整数区间，期间谓词可以写成事实表日期键的范围过滤，不必连接维度表。
    DateKeysContiguous { dim: String, key: String, year_col: String, month_col: String },
    /// 日期列完整性：没有日期维度时，日期列为空的行归不到任何期间；返回有日期的行占比，由调用方与准入基线比较。
    DateCoverage { table: String, col: String },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Outcome {
    pub pass: bool,
    pub metrics: Value,
    pub ms: f64,
}

impl Check {
    pub fn kind(&self) -> &'static str {
        match self {
            Check::KeyUnique { .. } => "KeyUnique",
            Check::SampleFanout { .. } => "SampleFanout",
            Check::RowConservation { .. } => "RowConservation",
            Check::DateKeysContiguous { .. } => "DateKeysContiguous",
            Check::DateCoverage { .. } => "DateCoverage",
        }
    }

    pub fn key(&self) -> String {
        serde_json::to_string(self).unwrap_or_default()
    }

    pub fn tables(&self) -> Vec<String> {
        match self {
            Check::KeyUnique { table, .. } => vec![table.clone()],
            Check::DateKeysContiguous { dim, .. } => vec![dim.clone()],
            Check::DateCoverage { table, .. } => vec![table.clone()],
            Check::SampleFanout { left, right, .. } | Check::RowConservation { left, right, .. } => {
                vec![left.clone(), right.clone()]
            }
        }
    }

    /// 反馈统计的上下文：键唯一性看被检查的表，另两种看关联方向（左表>右表）。
    pub fn context(&self) -> String {
        match self {
            Check::KeyUnique { table, cols, .. } => format!("{table}({})", cols.join(",")),
            Check::DateKeysContiguous { dim, key, .. } => format!("{dim}({key})"),
            Check::DateCoverage { table, col } => format!("{table}({col})"),
            Check::SampleFanout { left, right, on, .. } | Check::RowConservation { left, right, on, .. } => {
                format!("{left}>{right}:{}", fmt_on(on))
            }
        }
    }

    /// 本检查大致要扫的行数（给反馈模块估代价用）。
    pub fn rows_touched(&self, rows: &dyn Fn(&str) -> f64) -> f64 {
        match self {
            Check::KeyUnique { table, cols, .. } => rows(table) * (1.0 + 0.5 * (cols.len() as f64 - 1.0)),
            Check::DateKeysContiguous { dim, .. } => rows(dim),
            Check::DateCoverage { table, .. } => rows(table),
            Check::SampleFanout { right, .. } => rows(right),
            Check::RowConservation { left, right, .. } => rows(left) * 2.0 + rows(right),
        }
    }

    pub fn describe(&self) -> String {
        match self {
            Check::KeyUnique { table, cols, filter } => {
                format!("{table}({}) 是否唯一{}", cols.join(", "), filter.as_ref().map(|f| format!(" [过滤 {f}]")).unwrap_or_default())
            }
            Check::DateKeysContiguous { dim, key, .. } => format!("{dim}({key}) 日期键是否按月连续"),
            Check::DateCoverage { table, col } => format!("{table}.{col} 有日期的行占比"),
            Check::SampleFanout { left, right, on, .. } => format!("抽样：{left}→{right} 按 {} 是否一对多", fmt_on(on)),
            Check::RowConservation { left, right, on, .. } => {
                format!("行数守恒：{left}⋈{right} 按 {} 后行数是否超过 {left}", fmt_on(on))
            }
        }
    }

    pub fn sql(&self) -> String {
        match self {
            Check::KeyUnique { table, cols, filter } => {
                let key = if cols.len() == 1 { cols[0].clone() } else { format!("({})", cols.join(", ")) };
                let mut conds: Vec<String> = cols.iter().map(|c| format!("{c} is not null")).collect();
                if let Some(f) = filter {
                    conds.push(format!("({f})"));
                }
                format!("select count(*) as n_rows, count(distinct {key}) as n_keys from {table} where {}", conds.join(" and "))
            }
            Check::DateKeysContiguous { dim, key, year_col, month_col } => format!(
                "with m as (select {year_col} as y, {month_col} as mo, count(*) as c, min({key}) as mn, max({key}) as mx \
                 from {dim} where {key} is not null group by 1, 2), \
                 s as (select c, mn, mx, lag(mx) over (order by y, mo) as prev_mx from m) \
                 select count(*) filter (where c <> mx - mn + 1 or (prev_mx is not null and mn <> prev_mx + 1)) as n_bad, \
                        count(*) as n_months from s"
            ),
            Check::DateCoverage { table, col } => format!("select count(*) as n_rows, count({col}) as n_dated from {table}"),
            Check::SampleFanout { left, right, on, lf, rf, n } => {
                let lcols: Vec<&str> = on.iter().map(|(l, _)| l.as_str()).collect();
                let mut lconds: Vec<String> = lcols.iter().map(|c| format!("{c} is not null")).collect();
                if let Some(f) = lf {
                    lconds.push(format!("({f})"));
                }
                let mut jconds: Vec<String> = on.iter().map(|(l, r)| format!("{right}.{r} = s.{l}")).collect();
                if let Some(f) = rf {
                    jconds.push(format!("({f})"));
                }
                format!(
                    "with s as (select {cols} from {left} where {lc} limit {n}) \
                     select count(*) as n_sample, coalesce(max(m), 0) as max_mult, coalesce(avg(m), 0) as avg_mult, \
                            count(*) filter (where m > 1) as n_fanned \
                     from s cross join lateral (select count(*) as m from {right} where {jc}) t",
                    cols = lcols.join(", "),
                    lc = lconds.join(" and "),
                    jc = jconds.join(" and "),
                )
            }
            Check::RowConservation { left, right, on, lf, rf } => {
                // 过滤在各自表的子查询里求值，过滤可以写成 表.列，也可以引用两表重名的列
                let wl = lf.as_ref().map(|f| format!(" where {f}")).unwrap_or_default();
                let wr = rf.as_ref().map(|f| format!(" where {f}")).unwrap_or_default();
                let side = |t: &str, w: &str| if w.is_empty() { t.to_string() } else { format!("(select * from {t}{w})") };
                let conds: Vec<String> = on.iter().map(|(l, r)| format!("l.{l} = r.{r}")).collect();
                format!(
                    "select (select count(*) from {left}{wl}) as n_left, (select count(*) from {right}{wr}) as n_right, \
                            (select count(*) from {} l join {} r on {}) as n_join",
                    side(left, &wl),
                    side(right, &wr),
                    conds.join(" and ")
                )
            }
        }
    }

    pub fn eval(&self, rows: &Rows, ms: f64) -> Outcome {
        match self {
            Check::KeyUnique { .. } => {
                let (n_rows, n_keys) = (rows.i64(0, 0).unwrap_or(0), rows.i64(0, 1).unwrap_or(0));
                let avg = if n_keys > 0 { n_rows as f64 / n_keys as f64 } else { 0.0 };
                Outcome { pass: n_rows == n_keys, metrics: json!({"n_rows": n_rows, "n_keys": n_keys, "avg_mult": avg}), ms }
            }
            Check::DateKeysContiguous { .. } => {
                let (n_bad, n_months) = (rows.i64(0, 0).unwrap_or(0), rows.i64(0, 1).unwrap_or(0));
                Outcome { pass: n_bad == 0, metrics: json!({"n_bad": n_bad, "n_months": n_months}), ms }
            }
            Check::DateCoverage { .. } => {
                let (n_rows, n_dated) = (rows.i64(0, 0).unwrap_or(0), rows.i64(0, 1).unwrap_or(0));
                let ratio = if n_rows > 0 { n_dated as f64 / n_rows as f64 } else { 1.0 };
                Outcome { pass: true, metrics: json!({"n_rows": n_rows, "n_dated": n_dated, "join_ratio": ratio}), ms }
            }
            Check::SampleFanout { .. } => {
                let max_mult = rows.i64(0, 1).unwrap_or(0);
                Outcome {
                    pass: max_mult <= 1,
                    metrics: json!({
                        "n_sample": rows.i64(0, 0).unwrap_or(0),
                        "max_mult": max_mult,
                        "avg_mult": rows.f64(0, 2).unwrap_or(0.0),
                        "n_fanned": rows.i64(0, 3).unwrap_or(0),
                    }),
                    ms,
                }
            }
            Check::RowConservation { .. } => {
                let (n_left, n_right, n_join) = (rows.i64(0, 0).unwrap_or(0), rows.i64(0, 1).unwrap_or(0), rows.i64(0, 2).unwrap_or(0));
                let ratio = if n_left > 0 { n_join as f64 / n_left as f64 } else { 0.0 };
                Outcome {
                    pass: n_join <= n_left,
                    metrics: json!({"n_left": n_left, "n_right": n_right, "n_join": n_join, "join_ratio": ratio}),
                    ms,
                }
            }
        }
    }
}

pub fn fmt_on(on: &On) -> String {
    let s: Vec<String> = on.iter().map(|(l, r)| format!("{l}={r}")).collect();
    format!("({})", s.join(", "))
}

/// 按列集合（不看顺序与方向）比较两个关联是否相同。
pub fn same_on(a: &On, b: &On) -> bool {
    let norm = |o: &On| {
        let mut v: Vec<(String, String)> =
            o.iter().map(|(l, r)| if l <= r { (l.clone(), r.clone()) } else { (r.clone(), l.clone()) }).collect();
        v.sort();
        v
    };
    norm(a) == norm(b)
}

pub fn flip(on: &On) -> On {
    on.iter().map(|(l, r)| (r.clone(), l.clone())).collect()
}
