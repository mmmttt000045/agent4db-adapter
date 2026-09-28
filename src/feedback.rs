//! 反馈：根据历史执行记录调整检查顺序。
//! 目标是“出问题时尽早停下”：按 P(发现问题) / 预计代价 从大到小排（顺序检验的经典最优规则）。
//! 正常数据上所有检查一项不少，所以只省失败路径上的代价，不降低正确性要求。

use crate::checks::{Check, Outcome};
use parking_lot::Mutex;
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Default, Serialize)]
pub struct KindStats {
    pub runs: u64,
    pub fails: u64,
    pub ms: f64,
    pub mrows: f64,
}

impl KindStats {
    fn p_fail(&self) -> f64 {
        (self.fails as f64 + 1.0) / (self.runs as f64 + 2.0)
    }
    fn ms_per_mrow(&self) -> f64 {
        if self.mrows > 0.0 {
            self.ms / self.mrows
        } else {
            300.0
        }
    }
}

/// 发现问题后，以此概率把剩余检查也跑完，给反馈提供无偏样本。
pub const AUDIT_RATE: f64 = 0.2;

/// 有足够样本之前沿用固定顺序。
const MIN_RUNS: u64 = 3;

#[derive(Default)]
pub struct Feedback {
    stats: Mutex<BTreeMap<String, KindStats>>,
    priority: Mutex<Option<Vec<String>>>,
}

impl Feedback {
    pub fn set_priority(&self, priority: Option<Vec<String>>) {
        *self.priority.lock() = priority;
    }

    pub fn record(&self, c: &Check, o: &Outcome, rows: &dyn Fn(&str) -> f64) {
        let mut s = self.stats.lock();
        let e = s.entry(c.kind().to_string()).or_default();
        e.runs += 1;
        if !o.pass {
            e.fails += 1;
        }
        e.ms += o.ms;
        e.mrows += c.rows_touched(rows) / 1e6;
    }

    /// `enabled=false` 时保持调用方给出的固定顺序。
    pub fn order(&self, enabled: bool, mut checks: Vec<Check>, rows: &dyn Fn(&str) -> f64) -> Vec<Check> {
        if !enabled {
            return checks;
        }
        if let Some(priority) = &*self.priority.lock() {
            checks.sort_by_key(|c| priority.iter().position(|k| k == c.kind()).unwrap_or(usize::MAX));
            return checks;
        }
        let s = self.stats.lock();
        if checks.iter().any(|c| s.get(c.kind()).is_none_or(|k| k.runs < MIN_RUNS)) {
            return checks;
        }
        let score = |c: &Check| {
            let k = &s[c.kind()];
            let cost = k.ms_per_mrow() * c.rows_touched(rows) / 1e6 + 1.0;
            k.p_fail() / cost
        };
        checks.sort_by(|a, b| score(b).partial_cmp(&score(a)).unwrap_or(std::cmp::Ordering::Equal));
        checks
    }

    pub fn snapshot(&self) -> BTreeMap<String, KindStats> {
        self.stats.lock().clone()
    }
}
