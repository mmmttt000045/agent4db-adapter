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
        }
    }

    pub fn key(&self) -> String {
        serde_json::to_string(self).unwrap_or_default()
    }

    pub fn tables(&self) -> Vec<String> {
        match self {
            Check::KeyUnique { table, .. } => vec![table.clone()],
            Check::SampleFanout { left, right, .. } | Check::RowConservation { left, right, .. } => {
                vec![left.clone(), right.clone()]
            }
        }
    }

    /// 反馈统计的上下文：键唯一性看被检查的表，另两种看关联方向（左表>右表）。
    pub fn context(&self) -> String {
        match self {
            Check::KeyUnique { table, .. } => table.clone(),
            Check::SampleFanout { left, right, .. } | Check::RowConservation { left, right, .. } => format!("{left}>{right}"),
        }
    }

    /// 本检查大致要扫的行数（给反馈模块估代价用）。
    pub fn rows_touched(&self, rows: &dyn Fn(&str) -> f64) -> f64 {
        match self {
            Check::KeyUnique { table, cols, .. } => rows(table) * (1.0 + 0.5 * (cols.len() as f64 - 1.0)),
            Check::SampleFanout { right, .. } => rows(right),
            Check::RowConservation { left, right, .. } => rows(left) * 2.0 + rows(right),
        }
    }

    pub fn describe(&self) -> String {
        match self {
            Check::KeyUnique { table, cols, filter } => {
                format!("{table}({}) 是否唯一{}", cols.join(", "), filter.as_ref().map(|f| format!(" [过滤 {f}]")).unwrap_or_default())
            }
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
            Check::SampleFanout { left, right, on, lf, rf, n } => {
                let lcols: Vec<&str> = on.iter().map(|(l, _)| l.as_str()).collect();
                let mut lconds: Vec<String> = lcols.iter().map(|c| format!("{c} is not null")).collect();
                if let Some(f) = lf {
                    lconds.push(format!("({f})"));
                }
                let mut jconds: Vec<String> = on.iter().map(|(l, r)| format!("r.{r} = s.{l}")).collect();
                if let Some(f) = rf {
                    jconds.push(format!("({f})"));
                }
                format!(
                    "with s as (select {cols} from {left} where {lc} limit {n}) \
                     select count(*) as n_sample, coalesce(max(m), 0) as max_mult, coalesce(avg(m), 0) as avg_mult, \
                            count(*) filter (where m > 1) as n_fanned \
                     from s cross join lateral (select count(*) as m from {right} r where {jc}) t",
                    cols = lcols.join(", "),
                    lc = lconds.join(" and "),
                    jc = jconds.join(" and "),
                )
            }
            Check::RowConservation { left, right, on, lf, rf } => {
                let wl = lf.as_ref().map(|f| format!(" where {f}")).unwrap_or_default();
                let wr = rf.as_ref().map(|f| format!(" where {f}")).unwrap_or_default();
                let mut conds: Vec<String> = on.iter().map(|(l, r)| format!("l.{l} = r.{r}")).collect();
                if let Some(f) = lf {
                    conds.push(format!("({})", qualify(f, "l")));
                }
                if let Some(f) = rf {
                    conds.push(format!("({})", qualify(f, "r")));
                }
                format!(
                    "select (select count(*) from {left}{wl}) as n_left, (select count(*) from {right}{wr}) as n_right, \
                            (select count(*) from {left} l join {right} r on {}) as n_join",
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

/// 把形如 `col = 'v'` 的简单过滤条件加上表别名（TPC-DS 列名唯一，只需给开头的列名加前缀）。
fn qualify(filter: &str, alias: &str) -> String {
    format!("{alias}.{}", filter.trim())
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
