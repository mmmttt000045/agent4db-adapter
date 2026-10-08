//! 反馈：根据执行记录调整关联检查的顺序，并用回放证据决定是否采纳。
//!
//! 目标是“出问题时尽早停下”：按 P(发现问题) / 预计代价 从大到小排（顺序检验的经典规则）。
//! 三种检查在同一候选上是蕴含关系：抽样扇出或行数守恒失败，右侧键必然不唯一。调用方据此
//! 保证重排不改变验证结论（见 `Middle::validate`），这里只决定为同一结论花多少数据库代价。
//!
//! 自适应顺序不会直接生效。被审计的失败候选（三项检查结果全知，抽样与顺序无关）可以离线
//! 回放任意顺序的代价；只有回放显示比默认顺序显著更省时才采纳，证据增加后重新评估。

use crate::checks::{Check, Outcome};
use parking_lot::Mutex;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Clone, Debug, Default, Serialize)]
pub struct KindStats {
    pub runs: u64,
    pub fails: u64,
    pub ms: f64,
    pub mrows: f64,
    /// 已执行的结果被后续请求直接复用的次数
    pub hits: u64,
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
    fn mean_ms(&self) -> Option<f64> {
        if self.runs > 0 {
            Some(self.ms / self.runs as f64)
        } else {
            None
        }
    }
    /// 每次执行平均被复用几次；用于把执行代价摊到所有使用者身上。
    fn reuse_rate(&self) -> f64 {
        if self.runs > 0 {
            self.hits as f64 / self.runs as f64
        } else {
            0.0
        }
    }
}

/// 发现问题后，以此概率把剩余检查也跑完，给反馈提供补充观测（不是无偏因果估计）。
pub const AUDIT_RATE: f64 = 0.2;

/// 有足够样本之前沿用固定顺序。
const MIN_RUNS: u64 = 3;

/// 默认顺序：与固定顺序对照组一致，也是回放比较的基线。
pub const DEFAULT_ORDER: [&str; 3] = ["KeyUnique", "RowConservation", "SampleFanout"];

/// 上下文失败概率向该检查种类整体收缩的先验强度（相当于多少次虚拟观测）。
const PRIOR_WEIGHT: f64 = 4.0;

/// 作出采纳 / 回滚判断至少需要的被审计失败候选数。
pub const MIN_EVIDENCE: usize = 8;

/// 回放窗口：只保留最近的被审计失败候选，跟随负载变化。
const WINDOW: usize = 2000;

/// Frozen boundary: only later, previously unseen candidate groups may validate a policy.
#[derive(Clone, Debug, Default, Serialize)]
pub struct Checkpoint {
    cursor: u64,
    groups: BTreeSet<String>,
}

fn signature(obs: &[Obs]) -> String {
    let mut keys: Vec<&str> = obs.iter().map(|o| o.key.as_str()).collect();
    keys.sort_unstable();
    keys.join("\n")
}

/// 一次验证尝试中某项检查的观测。
#[derive(Clone, Debug)]
pub struct Obs {
    kind: String,
    context: String,
    key: String,
    rows: f64,
    pass: bool,
    /// 本次实际花费的数据库毫秒；复用或合并为 0
    ms: f64,
    executed: bool,
}

impl Obs {
    /// `executed=false` 表示结果来自经验库复用或在途合并，本次不产生数据库代价。
    pub fn new(c: &Check, o: &Outcome, executed: bool, rows: &dyn Fn(&str) -> f64) -> Obs {
        Obs {
            kind: c.kind().to_string(),
            context: c.context(),
            key: c.key(),
            rows: c.rows_touched(rows),
            pass: o.pass,
            ms: if executed { o.ms } else { 0.0 },
            executed,
        }
    }
}

#[derive(Clone, Debug)]
struct Episode {
    obs: Vec<Obs>,
    /// 首个失败的不是键唯一性时，是否还要补查它来决定粒度修复（与顺序无关，取决于修复进度）
    probe_key: bool,
    sequence: u64,
}

/// 可回放的排序策略。
#[derive(Clone, Debug)]
pub enum Order {
    /// 按检查种类的固定排列（回放基线用默认顺序）
    Fixed(Vec<String>),
    /// 内置自适应评分
    Adaptive,
}

impl Order {
    pub fn default_order() -> Order {
        Order::Fixed(DEFAULT_ORDER.map(String::from).to_vec())
    }
}

/// 候选策略与默认顺序在同一批被审计失败候选上的配对回放结果。
#[derive(Clone, Debug, Default, Serialize)]
pub struct Evidence {
    /// 不同候选签名组数，重复请求先组内平均
    pub episodes: usize,
    /// 候选策略的平均观测执行代价（ms / 候选组）
    pub policy_ms: f64,
    /// 默认顺序的平均观测执行代价（ms / 候选组）
    pub baseline_ms: f64,
    /// 候选 − 默认 的平均配对差；负数表示更省
    pub mean_delta_ms: f64,
    /// 候选组平均配对差的保守 Student-t 95% 描述性区间
    pub ci95: [f64; 2],
}

impl Evidence {
    /// 证据足够，且区间整体低于 0。
    pub fn improves(&self) -> bool {
        self.episodes >= MIN_EVIDENCE && self.ci95[1] < 0.0
    }
}

#[derive(Clone, Debug, Serialize)]
struct Decision {
    /// 作出判断时累计的证据条数
    at: u64,
    adopted: bool,
    evidence: Evidence,
}

#[derive(Default)]
struct State {
    kinds: BTreeMap<String, KindStats>,
    /// 键：`种类|上下文`
    contexts: BTreeMap<String, KindStats>,
    /// Frozen scorer; never updated with its evaluation batch.
    frozen: Option<Box<State>>,
    boundary: Checkpoint,
    seen_groups: BTreeSet<String>,
    adaptive_uses: u64,
    order_calls: u64,
    episodes: VecDeque<Episode>,
    /// 被审计失败候选的累计数（含已滑出窗口的）
    evidence_total: u64,
    passed: u64,
    unaudited_failures: u64,
    adaptive: Option<Decision>,
}

fn ctx_key(kind: &str, context: &str) -> String {
    format!("{kind}|{context}")
}

fn rank(priority: &[String], kind: &str) -> usize {
    priority.iter().position(|k| k == kind).unwrap_or(usize::MAX)
}

pub(crate) fn summarize(pairs: &[(f64, f64)]) -> Evidence {
    let n = pairs.len();
    if n == 0 {
        return Evidence::default();
    }
    let nf = n as f64;
    let policy_ms = pairs.iter().map(|p| p.0).sum::<f64>() / nf;
    let baseline_ms = pairs.iter().map(|p| p.1).sum::<f64>() / nf;
    let mean = policy_ms - baseline_ms;
    let half = if n > 1 {
        let var = pairs.iter().map(|(p, b)| (p - b - mean).powi(2)).sum::<f64>() / (nf - 1.0);
        // Student-t critical values; this remains a descriptive interval, not a sequential guarantee.
        let critical = match n {
            2 => 12.706,
            3 => 4.303,
            4 => 3.182,
            5 => 2.776,
            6 => 2.571,
            7 => 2.447,
            8 => 2.365,
            9 => 2.306,
            10 => 2.262,
            11..=16 => 2.228,
            17..=31 => 2.120,
            _ => 2.042,
        };
        critical * (var / nf).sqrt()
    } else {
        0.0
    };
    Evidence { episodes: n, policy_ms, baseline_ms, mean_delta_ms: mean, ci95: [mean - half, mean + half] }
}

impl State {
    /// 排序分数，越大越先执行。
    /// - 失败概率：上下文（具体表 / 表对方向）的观测向该种类整体收缩，少量样本不会大幅摆动；
    /// - 代价：优先用该上下文的实测均值，没有时才按行数线性外推；
    /// - 共享摊销：执行一次、被复用 h 次的检查，每次使用平均只花 1/(1+h)；已缓存的视为零代价。
    fn score(&self, kind: &str, context: &str, rows: f64, cached: bool) -> f64 {
        let k = self.kinds.get(kind).cloned().unwrap_or_default();
        let x = self.contexts.get(&ctx_key(kind, context));
        let prior = k.p_fail();
        let p = x.map_or(prior, |x| (x.fails as f64 + PRIOR_WEIGHT * prior) / (x.runs as f64 + PRIOR_WEIGHT));
        let cost = if cached {
            0.0
        } else {
            let exec = x.and_then(KindStats::mean_ms).unwrap_or_else(|| k.ms_per_mrow() * rows / 1e6);
            exec / (1.0 + x.map_or_else(|| k.reuse_rate(), KindStats::reuse_rate))
        };
        p / (cost + 1.0)
    }

    fn observed_cost(&self, o: &Obs) -> f64 {
        // Immutable actual incremental cost. Future hits cannot rewrite old evidence.
        // Reuse is already represented by zero-cost observations; do not discount twice.
        o.ms
    }

    /// 按某策略重放一个被审计的失败候选：累加到第一个失败为止的代价；
    /// 若第一个失败的不是键唯一性且需要补查，再加上它的代价。审计本身的开销不计入任何策略。
    fn replay(&self, e: &Episode, policy: &Order) -> f64 {
        let mut idx: Vec<usize> = (0..e.obs.len()).collect();
        let default = DEFAULT_ORDER.map(String::from);
        idx.sort_by_key(|&i| rank(&default, &e.obs[i].kind));
        match policy {
            Order::Fixed(priority) => idx.sort_by_key(|&i| rank(priority, &e.obs[i].kind)),
            Order::Adaptive => {
                let keys: Vec<f64> = e.obs.iter().map(|o| self.score(&o.kind, &o.context, o.rows, !o.executed)).collect();
                idx.sort_by(|&a, &b| keys[b].total_cmp(&keys[a]));
            }
        }
        let mut cost = 0.0;
        let mut key_seen = false;
        for i in idx {
            let o = &e.obs[i];
            cost += self.observed_cost(o);
            key_seen |= o.kind == "KeyUnique";
            if !o.pass {
                if !key_seen && e.probe_key {
                    cost += e.obs.iter().find(|x| x.kind == "KeyUnique").map_or(0.0, |x| self.observed_cost(x));
                }
                break;
            }
        }
        cost
    }

    fn checkpoint(&self) -> Checkpoint {
        Checkpoint { cursor: self.evidence_total, groups: self.seen_groups.clone() }
    }

    fn evaluate_batch(&self, policy: &Order, boundary: Option<&Checkpoint>, scorer: &State) -> Evidence {
        let baseline = Order::default_order();
        let mut groups: BTreeMap<String, Vec<(f64, f64)>> = BTreeMap::new();
        for e in &self.episodes {
            let key = signature(&e.obs);
            if boundary.is_some_and(|b| e.sequence <= b.cursor || b.groups.contains(&key)) {
                continue;
            }
            groups.entry(key).or_default().push((scorer.replay(e, policy), scorer.replay(e, &baseline)));
        }
        let pairs: Vec<_> = groups
            .values()
            .map(|g| {
                let n = g.len() as f64;
                (g.iter().map(|p| p.0).sum::<f64>() / n, g.iter().map(|p| p.1).sum::<f64>() / n)
            })
            .collect();
        summarize(&pairs)
    }

    /// Freeze a scorer, then decide once per fresh batch of distinct candidates.
    fn adaptive_adopted(&mut self) -> bool {
        if self.frozen.is_none() {
            self.frozen = Some(Box::new(State { kinds: self.kinds.clone(), contexts: self.contexts.clone(), ..Default::default() }));
            self.boundary = self.checkpoint();
            self.adaptive = Some(Decision { at: self.evidence_total, adopted: false, evidence: Evidence::default() });
            return false;
        }
        let evidence = self.evaluate_batch(&Order::Adaptive, Some(&self.boundary), self.frozen.as_ref().unwrap());
        if evidence.episodes >= MIN_EVIDENCE {
            let adopted = evidence.improves();
            self.adaptive = Some(Decision { at: self.evidence_total, adopted, evidence });
            self.boundary.cursor = self.evidence_total;
            if !adopted {
                self.frozen = None;
            }
        }
        self.adaptive.as_ref().is_some_and(|d| d.adopted)
    }
}

#[derive(Default)]
pub struct Feedback {
    state: Mutex<State>,
}

impl Feedback {
    /// 一次实际执行（种类整体与具体上下文各记一份）。
    pub fn record(&self, c: &Check, o: &Outcome, rows: &dyn Fn(&str) -> f64) {
        let mrows = c.rows_touched(rows) / 1e6;
        let mut guard = self.state.lock();
        let s = &mut *guard;
        let kind = s.kinds.entry(c.kind().to_string()).or_default();
        let context = s.contexts.entry(ctx_key(c.kind(), &c.context())).or_default();
        for e in [kind, context] {
            e.runs += 1;
            if !o.pass {
                e.fails += 1;
            }
            e.ms += o.ms;
            e.mrows += mrows;
        }
    }

    /// 检查结果被直接复用（未访问数据库）。
    pub fn record_reuse(&self, c: &Check) {
        let mut s = self.state.lock();
        s.kinds.entry(c.kind().to_string()).or_default().hits += 1;
        s.contexts.entry(ctx_key(c.kind(), &c.context())).or_default().hits += 1;
    }

    /// 记录一次验证尝试。只有被审计的失败候选能回放其他顺序；通过的候选所有顺序代价相同，只计数。
    pub fn episode(&self, obs: Vec<Obs>, audited: bool, probe_key: bool) {
        let mut s = self.state.lock();
        s.seen_groups.insert(signature(&obs));
        if obs.iter().all(|o| o.pass) {
            s.passed += 1;
            return;
        }
        if !audited {
            s.unaudited_failures += 1;
            return;
        }
        let sequence = s.evidence_total + 1;
        s.episodes.push_back(Episode { obs, probe_key, sequence });
        while s.episodes.len() > WINDOW {
            s.episodes.pop_front();
        }
        s.evidence_total += 1;
    }

    /// `enabled=false` 时保持调用方给出的固定顺序（调用方按 `DEFAULT_ORDER` 构造）。
    /// `cached` 报告某检查的结果当前是否已在经验库中，它会被视为零代价。
    pub fn order(&self, enabled: bool, checks: Vec<Check>, rows: &dyn Fn(&str) -> f64, cached: &dyn Fn(&Check) -> bool) -> Vec<Check> {
        if !enabled {
            return checks;
        }
        let mut s = self.state.lock();
        s.order_calls += 1;
        let mut candidate_keys: Vec<String> = checks.iter().map(Check::key).collect();
        candidate_keys.sort();
        s.seen_groups.insert(candidate_keys.join("\n"));
        if checks.iter().any(|c| s.kinds.get(c.kind()).is_none_or(|k| k.runs < MIN_RUNS)) || !s.adaptive_adopted() {
            return checks;
        }
        s.adaptive_uses += 1;
        let scorer = s.frozen.as_ref().expect("adopted scorer");
        let keys: Vec<f64> = checks.iter().map(|c| scorer.score(c.kind(), &c.context(), c.rows_touched(rows), cached(c))).collect();
        let mut idx: Vec<usize> = (0..checks.len()).collect();
        idx.sort_by(|&a, &b| keys[b].total_cmp(&keys[a]));
        idx.into_iter().map(|i| checks[i].clone()).collect()
    }

    /// 统计、证据与自适应采纳状态，供 `/v1/stats` 与实验报告使用。
    pub fn report(&self) -> Value {
        let s = self.state.lock();
        let pending = s.frozen.as_ref().map(|scorer| s.evaluate_batch(&Order::Adaptive, Some(&s.boundary), scorer));
        json!({
            "kinds": s.kinds,
            "contexts": s.contexts,
            "evidence": {"audited_failures_in_window": s.episodes.len(), "audited_failures_total": s.evidence_total,
                "passed": s.passed, "unaudited_failures": s.unaudited_failures, "min_evidence": MIN_EVIDENCE},
            "adaptive": s.adaptive,
            "pending_validation": pending,
            "order_calls": s.order_calls, "adaptive_uses": s.adaptive_uses,
            "evaluation": "frozen scorer; future distinct candidate groups; observed incremental costs",
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn checks() -> Vec<Check> {
        vec![
            Check::KeyUnique { table: "u".into(), cols: vec!["id".into()], filter: None },
            Check::RowConservation { left: "t".into(), right: "u".into(), on: vec![], lf: None, rf: None },
            Check::SampleFanout { left: "t".into(), right: "u".into(), on: vec![], lf: None, rf: None, n: 10 },
        ]
    }

    fn outcome(pass: bool, ms: f64) -> Outcome {
        Outcome { pass, metrics: json!({}), ms }
    }

    /// 键唯一性、行数守恒各自的耗时与结果；抽样扇出 1 ms 且通过（样本没碰到重复键）。
    fn audited(fb: &Feedback, key: (bool, f64), rc: (bool, f64), probe_key: bool) {
        let mut c = checks();
        if let Check::KeyUnique { filter, .. } = &mut c[0] {
            *filter = Some(format!("id > {}", fb.state.lock().evidence_total));
        }
        let obs = vec![
            Obs::new(&c[0], &outcome(key.0, key.1), true, &|_| 100.0),
            Obs::new(&c[1], &outcome(rc.0, rc.1), true, &|_| 100.0),
            Obs::new(&c[2], &outcome(true, 1.0), true, &|_| 100.0),
        ];
        fb.episode(obs, true, probe_key);
    }

    fn evaluate(fb: &Feedback, policy: &Order, boundary: Option<&Checkpoint>) -> Evidence {
        let s = fb.state.lock();
        s.evaluate_batch(policy, boundary, &s)
    }

    /// 证据足够，且区间整体高于 0。
    fn regresses(e: &Evidence) -> bool {
        e.episodes >= MIN_EVIDENCE && e.ci95[0] > 0.0
    }

    fn rc_first() -> Order {
        Order::Fixed(vec!["RowConservation".into(), "KeyUnique".into(), "SampleFanout".into()])
    }

    #[test]
    fn replay_counts_cost_until_first_failure_plus_needed_key_probe() {
        let fb = Feedback::default();
        for _ in 0..MIN_EVIDENCE {
            audited(&fb, (false, 50.0), (false, 5.0), false);
        }
        let e = evaluate(&fb, &rc_first(), None);
        assert_eq!(e.episodes, MIN_EVIDENCE);
        assert!((e.policy_ms - 5.0).abs() < 1e-9 && (e.baseline_ms - 50.0).abs() < 1e-9);
        assert!(e.improves() && !regresses(&e));
        // 需要补查键唯一性时，先跑行数守恒反而多花一次检查。
        let fb = Feedback::default();
        for _ in 0..MIN_EVIDENCE {
            audited(&fb, (false, 50.0), (false, 5.0), true);
        }
        let e = evaluate(&fb, &rc_first(), None);
        assert!((e.policy_ms - 55.0).abs() < 1e-9);
        assert!(regresses(&e) && !e.improves());
    }

    #[test]
    fn passing_and_unaudited_candidates_are_not_replay_evidence() {
        let fb = Feedback::default();
        let c = checks();
        for _ in 0..MIN_EVIDENCE * 2 {
            fb.episode(c.iter().map(|x| Obs::new(x, &outcome(true, 3.0), true, &|_| 1.0)).collect(), false, true);
            fb.episode(vec![Obs::new(&c[0], &outcome(false, 3.0), true, &|_| 1.0)], false, true);
        }
        let e = evaluate(&fb, &rc_first(), None);
        assert_eq!(e.episodes, 0);
        assert!(!e.improves() && !regresses(&e));
        let r = fb.report();
        assert_eq!(r["evidence"]["passed"], MIN_EVIDENCE as u64 * 2);
        assert_eq!(r["evidence"]["unaudited_failures"], MIN_EVIDENCE as u64 * 2);
    }

    #[test]
    fn future_reuse_cannot_rewrite_past_execution_costs() {
        let fb = Feedback::default();
        for _ in 0..MIN_EVIDENCE {
            audited(&fb, (false, 50.0), (false, 5.0), false);
        }
        // 后续复用不能回溯降低已经发生的执行成本。
        for _ in 0..9 {
            fb.record_reuse(&checks()[0]);
        }
        let e = evaluate(&fb, &rc_first(), None);
        assert!((e.baseline_ms - 50.0).abs() < 1e-9);
        assert!(e.improves() && !regresses(&e));
    }

    #[test]
    fn adaptive_order_needs_replay_evidence_and_reverts_when_it_fades() {
        let fb = Feedback::default();
        let c = checks();
        for _ in 0..10 {
            fb.record(&c[0], &outcome(false, 50.0), &|_| 100.0);
            fb.record(&c[1], &outcome(false, 5.0), &|_| 100.0);
            fb.record(&c[2], &outcome(true, 1.0), &|_| 100.0);
        }
        let none = |_: &Check| false;
        // 统计已偏向先跑行数守恒，但没有回放证据前保持默认顺序。
        assert_eq!(fb.order(true, c.clone(), &|_| 100.0, &none), c);
        for _ in 0..MIN_EVIDENCE {
            audited(&fb, (false, 50.0), (false, 5.0), false);
        }
        assert_eq!(fb.order(true, c.clone(), &|_| 100.0, &none)[0].kind(), "RowConservation");
        assert_eq!(fb.order(false, c.clone(), &|_| 100.0, &none), c);
        // 新证据表明要补查键唯一性：窗口内优势消失后退回默认顺序。
        for _ in 0..MIN_EVIDENCE * 4 {
            audited(&fb, (false, 50.0), (false, 5.0), true);
        }
        assert_eq!(fb.order(true, c.clone(), &|_| 100.0, &none), c);
        assert_eq!(fb.report()["adaptive"]["adopted"], false);
    }

    #[test]
    fn cached_checks_are_treated_as_free() {
        let fb = Feedback::default();
        let c = checks();
        for _ in 0..10 {
            fb.record(&c[0], &outcome(false, 50.0), &|_| 100.0);
            fb.record(&c[1], &outcome(false, 5.0), &|_| 100.0);
            fb.record(&c[2], &outcome(true, 1.0), &|_| 100.0);
        }
        fb.order(true, c.clone(), &|_| 100.0, &|_| false);
        for _ in 0..MIN_EVIDENCE {
            audited(&fb, (false, 50.0), (false, 5.0), false);
        }
        let key_cached = |x: &Check| x.kind() == "KeyUnique";
        assert_eq!(fb.order(true, c.clone(), &|_| 100.0, &key_cached)[0].kind(), "KeyUnique");
    }

    #[test]
    fn repeated_candidates_do_not_inflate_evidence_and_training_groups_are_excluded() {
        let fb = Feedback::default();
        let c = checks();
        let observations = || {
            vec![
                Obs::new(&c[0], &outcome(false, 50.0), true, &|_| 100.0),
                Obs::new(&c[1], &outcome(false, 5.0), true, &|_| 100.0),
                Obs::new(&c[2], &outcome(true, 1.0), true, &|_| 100.0),
            ]
        };
        fb.episode(observations(), true, false);
        let boundary = fb.state.lock().checkpoint();
        for _ in 0..100 {
            fb.episode(observations(), true, false);
        }
        assert_eq!(evaluate(&fb, &rc_first(), None).episodes, 1);
        assert_eq!(evaluate(&fb, &rc_first(), Some(&boundary)).episodes, 0);
        assert!(!evaluate(&fb, &rc_first(), None).improves());
    }

    #[test]
    fn replay_does_not_charge_an_already_executed_key_probe_twice() {
        let fb = Feedback::default();
        audited(&fb, (true, 50.0), (false, 5.0), true);
        // Inconsistent observations can occur without a shared transaction snapshot.
        let e = evaluate(&fb, &Order::default_order(), None);
        assert_eq!(e.baseline_ms, 55.0);
        assert_eq!(e.policy_ms, 55.0);
    }

    #[test]
    fn scorer_is_frozen_until_fresh_validation_completes() {
        let fb = Feedback::default();
        let c = checks();
        for _ in 0..3 {
            for (check, ms) in c.iter().zip([50.0, 5.0, 1.0]) {
                fb.record(check, &outcome(check.kind() == "SampleFanout", ms), &|_| 100.0);
            }
        }
        fb.order(true, c.clone(), &|_| 100.0, &|_| false);
        // New telemetry strongly favors the opposite ranking. The evaluated scorer stays frozen.
        for _ in 0..100 {
            fb.record(&c[1], &outcome(false, 10000.0), &|_| 100.0);
        }
        for _ in 0..MIN_EVIDENCE {
            audited(&fb, (false, 50.0), (false, 5.0), false);
        }
        assert_eq!(fb.order(true, c, &|_| 100.0, &|_| false)[0].kind(), "RowConservation");
    }
}
