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

#[derive(Clone, Debug, Serialize)]
pub enum Content {
    Profile(Value),
    Join { paths: Vec<JoinPath>, bad: Vec<BadPath> },
    CheckResult { check: Check, outcome: Outcome },
    Result(Value),
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub enum Status {
    Valid,
    Revoked(String),
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

    pub fn dump(&self) -> Vec<Entry> {
        let mut v: Vec<Entry> = self.map.read().values().cloned().collect();
        v.sort_by(|a, b| a.key.cmp(&b.key));
        v
    }
}
