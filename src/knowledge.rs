//! 经验库：每条经验 = 知识内容 + 依赖（表版本）+ 守卫（复用前要重跑的不变量）+ 使用者。

use crate::catalog::TableVersion;
use crate::checks::{Check, On, Outcome};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// 一条验证过的关联路径。
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct JoinPath {
    pub left: String,
    pub right: String,
    pub on: On,
    /// 保持粒度所需的行过滤（表 → 条件），例如 store_returns → sr_status = '完成'
    pub filters: BTreeMap<String, String>,
    pub left_unique: bool,
    pub right_unique: bool,
    pub n_left: i64,
    pub n_join: i64,
    /// 左表有多少比例的行关联不上（空值或孤儿），例如日期键为空的销售行
    pub loss_ratio: f64,
    pub evidence: Vec<String>,
}

impl JoinPath {
    pub fn cardinality(&self) -> &'static str {
        match (self.left_unique, self.right_unique) {
            (true, true) => "1:1",
            (false, true) => "N:1",
            (true, false) => "1:N",
            (false, false) => "M:N",
        }
    }

    /// 复用前要重跑的不变量：验证时成立的唯一性。
    pub fn guards(&self) -> Vec<Check> {
        let mut g = vec![];
        if self.right_unique {
            g.push(Check::KeyUnique {
                table: self.right.clone(),
                cols: self.on.iter().map(|(_, r)| r.clone()).collect(),
                filter: self.filters.get(&self.right).cloned(),
            });
        }
        if self.left_unique {
            g.push(Check::KeyUnique {
                table: self.left.clone(),
                cols: self.on.iter().map(|(l, _)| l.clone()).collect(),
                filter: self.filters.get(&self.left).cloned(),
            });
        }
        g
    }
}

/// 被证伪的关联写法（反例）。
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BadPath {
    pub left: String,
    pub right: String,
    pub on: On,
    pub reason: String,
    /// 膨胀倍数（关联后行数 / 左表行数，或抽样平均匹配数）
    pub fanout: f64,
}

/// 指标经验：业务含义到数据的映射。示例只存题面与 SQL，不存结果值。
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Metric {
    pub name: String,
    #[serde(default)]
    pub aliases: Vec<String>,
    pub definition: String,
    pub fact: String,
    /// 聚合表达式，只能引用 fact 与 joins 涉及表的列
    pub measure: String,
    /// fact 上“一行一条业务记录”的键
    pub grain: Vec<String>,
    pub time: Option<TimeSpec>,
    #[serde(default)]
    pub joins: Vec<JoinRef>,
    /// 仅口径必需条件（表 → 条件），不含题目参数
    #[serde(default)]
    pub filters: BTreeMap<String, String>,
    #[serde(default)]
    pub empty: EmptyRule,
    #[serde(default)]
    pub caveats: Vec<String>,
    #[serde(default)]
    pub examples: Vec<Example>,
    #[serde(default)]
    pub basis: Basis,
}

impl Metric {
    /// 口径涉及的全部表（事实表、关联表、时间维度表）。
    pub fn tables(&self) -> Vec<String> {
        let mut t: BTreeSet<String> = [self.fact.clone()].into_iter().collect();
        for j in &self.joins {
            t.insert(j.left.clone());
            t.insert(j.right.clone());
        }
        if let Some(tm) = &self.time {
            t.insert(tm.dim.clone());
        }
        t.into_iter().collect()
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct TimeSpec {
    /// 时间角色，如“销售日”“退货日”
    pub role: String,
    pub fact_col: String,
    pub dim: String,
    pub dim_col: String,
    /// day / month / year
    pub grain: String,
}

/// 指标引用的已验证关联：方向、基数、过滤与丢行比例都记下，关联能执行不等于不放大聚合。
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct JoinRef {
    #[serde(default)]
    pub key: String,
    /// 多侧
    pub left: String,
    /// 一侧
    pub right: String,
    pub on: On,
    #[serde(default)]
    pub kind: JoinKind,
    #[serde(default)]
    pub filters: BTreeMap<String, String>,
    #[serde(default)]
    pub cardinality: String,
    #[serde(default)]
    pub loss_ratio: f64,
    /// 引用时关联条目的修订号
    #[serde(default)]
    pub revision: u32,
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum JoinKind {
    #[default]
    Inner,
    Left,
}

/// 无输入行时的取值。PostgreSQL 的 SUM 此时返回 NULL，口径未说明时不默认当作零。
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum EmptyRule {
    Null,
    Zero,
    #[default]
    Unspecified,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Example {
    pub question: String,
    pub sql: String,
}

/// 口径依据。
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Basis {
    ExplicitQuestion {
        task: String,
    },
    Glossary {
        source: String,
    },
    Confirmed {
        by: String,
    },
    #[default]
    None,
}

#[derive(Clone, Debug, Serialize)]
pub enum Content {
    Profile(Value),
    Join { paths: Vec<JoinPath>, bad: Vec<BadPath> },
    CheckResult { check: Check, outcome: Outcome },
    Result(Value),
    Metric(Box<Metric>),
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub enum Status {
    Valid,
    Revoked(String),
    /// 未通过晋升门槛或修复待验证；查找时按未命中处理
    Candidate(String),
}

#[derive(Clone, Debug, Serialize)]
pub struct Entry {
    pub key: String,
    pub content: Content,
    pub deps: BTreeMap<String, TableVersion>,
    pub guards: Vec<Check>,
    pub status: Status,
    pub created_by: String,
    pub hits: u64,
    pub consumers: BTreeSet<String>,
    pub revision: u32,
}

#[derive(Default)]
pub struct Store {
    map: RwLock<HashMap<String, Entry>>,
}

impl Store {
    pub fn get(&self, k: &str) -> Option<Entry> {
        self.map.read().get(k).cloned()
    }

    pub fn put(&self, k: &str, e: Entry) {
        self.map.write().insert(k.to_string(), e);
    }

    pub fn update(&self, k: &str, f: impl FnOnce(&mut Entry)) {
        if let Some(e) = self.map.write().get_mut(k) {
            f(e);
        }
    }

    pub fn len(&self) -> usize {
        self.map.read().len()
    }

    /// 按键前缀取出条目（含完整键），按键排序。
    pub fn scan(&self, prefix: &str) -> Vec<(String, Entry)> {
        let mut v: Vec<(String, Entry)> =
            self.map.read().iter().filter(|(k, _)| k.starts_with(prefix)).map(|(k, e)| (k.clone(), e.clone())).collect();
        v.sort_by(|a, b| a.0.cmp(&b.0));
        v
    }

    pub fn dump(&self) -> Vec<Entry> {
        let mut v: Vec<Entry> = self.map.read().values().cloned().collect();
        v.sort_by(|a, b| a.key.cmp(&b.key));
        v
    }
}
