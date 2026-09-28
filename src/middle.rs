//! 中间层 Agent：位于用户 Agent 与数据库之间，对外提供工具级 API。
//!
//! 三个机制：
//! - 共享：探查 / 检查 / 关联知识存进经验库，按作用域（任务 / 会话 / Agent / 全局）复用；并发相同请求在途合并。
//! - 守护：每条经验绑定依赖表的版本；依赖变化时先重跑守卫（验证时成立的不变量），失败即撤销、通知使用者并修复。
//! - 反馈：检查顺序按“发现问题的概率 / 共享摊销后的代价”调整，回放证据显示更省才采纳，且重排不改变验证结论；
//!   被证伪的关联写法不再重试，Agent 提交的 SQL 用到时直接拦下。

use crate::catalog::{self, Catalog, TableVersion};
use crate::checks::{flip, fmt_on, same_on, Check, On, Outcome};
use crate::db::{lit, Db, QKind};
use crate::feedback::{Feedback, Obs, AUDIT_RATE};
use crate::flight::Flight;
use crate::knowledge::{BadPath, Content, Entry, JoinPath, Status, Store};
use crate::sqlscan;
use anyhow::{anyhow, bail, Result};
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// 经验的共享范围。
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
pub enum Scope {
    /// 每个任务从头来（不复用）
    Task,
    /// 会话内复用（上下文里记得）
    Session,
    /// 同一个 Agent 跨会话复用（各家 Agent 自带的记忆）
    Agent,
    /// 中间层全局共享（跨会话、跨 Agent）
    Global,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, clap::ValueEnum)]
pub enum GuardMode {
    /// 不守护：记住了就直接用
    Off,
    /// 依赖变化时重跑守卫
    OnChange,
    /// 每次复用都重跑守卫
    Always,
}

#[derive(Clone, Debug, Serialize)]
pub struct MiddleConfig {
    pub name: String,
    pub scope: Scope,
    pub singleflight: bool,
    pub guard: GuardMode,
    pub feedback: bool,
    /// 执行前检查 Agent SQL 里的关联与粒度过滤
    pub validate_sql: bool,
    /// 相同 SQL、依赖未变时复用结果
    pub result_cache: bool,
    pub version_ttl_ms: u64,
    pub max_rows: usize,
    pub verbose: bool,
    pub trace_checks: bool,
    /// 实验可固定候选级审计抽样；None 保持逐次随机审计。
    pub audit_seed: Option<u64>,
}

impl Default for MiddleConfig {
    fn default() -> Self {
        MiddleConfig {
            name: "middle".into(),
            scope: Scope::Global,
            singleflight: true,
            guard: GuardMode::OnChange,
            feedback: true,
            validate_sql: true,
            result_cache: true,
            version_ttl_ms: 200,
            max_rows: 50,
            verbose: false,
            trace_checks: false,
            audit_seed: None,
        }
    }
}

/// 权限：角色可访问的表（None = 全部）。
#[derive(Clone, Debug)]
pub struct Role {
    pub name: String,
    pub tables: Option<BTreeSet<String>>,
}

impl Role {
    pub fn all() -> Role {
        Role { name: "analyst".into(), tables: None }
    }
    pub fn allows(&self, t: &str) -> bool {
        self.tables.as_ref().is_none_or(|s| s.contains(t))
    }
}

#[derive(Clone, Debug)]
pub struct Ctx {
    pub agent: String,
    pub session: String,
    pub task: String,
    pub role: Role,
}

impl Ctx {
    pub fn new(agent: &str, session: &str, task: &str) -> Ctx {
        Ctx { agent: agent.into(), session: session.into(), task: task.into(), role: Role::all() }
    }
}

#[derive(Default)]
pub struct Stats {
    pub hits: AtomicU64,
    pub misses: AtomicU64,
    pub guard_runs: AtomicU64,
    pub guard_fails: AtomicU64,
    pub revocations: AtomicU64,
    pub repairs: AtomicU64,
    pub rejections: AtomicU64,
    pub notices: AtomicU64,
}

fn inc(a: &AtomicU64) {
    a.fetch_add(1, Ordering::Relaxed);
}

enum Lookup {
    Hit(Entry),
    Miss,
    /// 守卫失败：经验已撤销，附带失败的守卫
    Violated {
        entry: Entry,
        failed: Check,
    },
}

type Versions = Arc<HashMap<String, TableVersion>>;

pub struct Middle {
    pub db: Arc<Db>,
    pub cat: Catalog,
    pub cfg: MiddleConfig,
    store: Store,
    flight_v: Flight<Value>,
    flight_c: Flight<Outcome>,
    flight_ver: Flight<Versions>,
    pub fb: Feedback,
    versions: Mutex<Option<(Instant, Versions)>>,
    notices: Mutex<HashMap<String, Vec<String>>>,
    pub stats: Stats,
    traces: Mutex<Vec<Value>>,
}

fn join_key(a: &str, b: &str) -> String {
    if a <= b {
        format!("join:{a}|{b}")
    } else {
        format!("join:{b}|{a}")
    }
}

/// Stable FNV-style hash, sampled by candidate rather than scheduling order.
fn audit_candidate(seed: u64, candidate: &str) -> bool {
    let mut hash = 14695981039346656037u64 ^ seed;
    for byte in candidate.as_bytes() {
        hash = (hash ^ u64::from(*byte)).wrapping_mul(1099511628211);
    }
    hash % 10_000 < (AUDIT_RATE * 10_000.0) as u64
}

fn ver_sig(deps: &BTreeMap<String, TableVersion>) -> String {
    deps.iter().map(|(t, v)| format!("{t}:{}:{}:{}", v.batch, v.dml, &v.schema[..v.schema.len().min(8)])).collect::<Vec<_>>().join(",")
}

fn metric(o: &Outcome, k: &str) -> f64 {
    o.metrics.get(k).and_then(Value::as_f64).unwrap_or(0.0)
}

fn fanout_of(c: &Check, o: &Outcome) -> f64 {
    match c {
        Check::RowConservation { .. } => metric(o, "join_ratio"),
        _ => metric(o, "avg_mult"),
    }
}

fn outcome_text(c: &Check, o: &Outcome) -> String {
    match c {
        Check::KeyUnique { .. } => {
            format!("{} 行只有 {} 个不同键（平均每键 {:.2} 行）", o.metrics["n_rows"], o.metrics["n_keys"], metric(o, "avg_mult"))
        }
        Check::SampleFanout { .. } => format!(
            "抽样 {} 行中 {} 行匹配多行（最多 {}，平均 {:.2}）",
            o.metrics["n_sample"],
            o.metrics["n_fanned"],
            o.metrics["max_mult"],
            metric(o, "avg_mult")
        ),
        Check::RowConservation { .. } => {
            format!("左表 {} 行，关联后 {} 行（{:.1} 倍）", o.metrics["n_left"], o.metrics["n_join"], metric(o, "join_ratio"))
        }
    }
}

impl Middle {
    pub async fn new(db: Arc<Db>, cfg: MiddleConfig) -> Result<Middle> {
        let cat = Catalog::load(&db).await?;
        Ok(Middle {
            db,
            cat,
            cfg,
            store: Store::default(),
            flight_v: Flight::default(),
            flight_c: Flight::default(),
            flight_ver: Flight::default(),
            fb: Feedback::default(),
            versions: Mutex::new(None),
            notices: Mutex::new(HashMap::new()),
            stats: Stats::default(),
            traces: Mutex::new(Vec::new()),
        })
    }

    fn log(&self, ctx: &Ctx, msg: impl AsRef<str>) {
        if self.cfg.verbose {
            eprintln!("    · [{}] {}", ctx.agent, msg.as_ref());
        }
    }

    fn trace(&self, ctx: &Ctx, detail: Value) {
        if self.cfg.trace_checks {
            let mut traces = self.traces.lock();
            if traces.len() < 20_000 {
                let sequence = traces.len() + 1;
                traces.push(json!({"sequence":sequence,"agent":ctx.agent,"session":ctx.session,"task":ctx.task,"detail":detail}));
            }
        }
    }

    pub fn take_check_traces(&self) -> Vec<Value> {
        std::mem::take(&mut *self.traces.lock())
    }

    fn scope_key(&self, ctx: &Ctx) -> String {
        match self.cfg.scope {
            Scope::Global => "G".into(),
            Scope::Agent => format!("A:{}", ctx.agent),
            Scope::Session => format!("S:{}/{}", ctx.agent, ctx.session),
            Scope::Task => format!("T:{}/{}/{}", ctx.agent, ctx.session, ctx.task),
        }
    }

    fn fk(&self, ctx: &Ctx, key: &str) -> String {
        format!("{}|{}", self.scope_key(ctx), key)
    }

    fn rows(&self) -> impl Fn(&str) -> f64 + '_ {
        move |t| self.cat.rows(t)
    }

    pub fn merged(&self) -> u64 {
        self.flight_v.merged.load(Ordering::Relaxed) + self.flight_c.merged.load(Ordering::Relaxed)
    }

    pub fn stats_json(&self) -> Value {
        let s = &self.stats;
        let g = |a: &AtomicU64| a.load(Ordering::Relaxed);
        json!({
            "knowledge_hits": g(&s.hits), "knowledge_misses": g(&s.misses), "inflight_merged": self.merged(),
            "guard_runs": g(&s.guard_runs), "guard_fails": g(&s.guard_fails), "revocations": g(&s.revocations),
            "repairs": g(&s.repairs), "sql_rejections": g(&s.rejections), "notices": g(&s.notices),
            "entries": self.store.len(), "feedback": self.fb.report(), "db": self.db.meter.snap(),
        })
    }

    pub fn knowledge(&self) -> Vec<Entry> {
        self.store.dump()
    }

    // ───────────────────────── 版本与依赖 ─────────────────────────

    async fn versions(&self) -> Result<Versions> {
        if let Some((t, v)) = &*self.versions.lock() {
            if t.elapsed() < Duration::from_millis(self.cfg.version_ttl_ms) {
                return Ok(v.clone());
            }
        }
        let (v, _) = self.flight_ver.run(true, "versions", || async { Ok(Arc::new(catalog::versions(&self.db).await?)) }).await?;
        *self.versions.lock() = Some((Instant::now(), v.clone()));
        Ok(v)
    }

    /// 让下一次请求重新读取版本（ETL 通知钩子；实验里也用来消除轮询间隔的影响）。
    pub fn invalidate_versions(&self) {
        *self.versions.lock() = None;
    }

    async fn deps_for(&self, tables: &[String]) -> Result<BTreeMap<String, TableVersion>> {
        let v = self.versions().await?;
        Ok(tables.iter().filter_map(|t| v.get(t).map(|x| (t.clone(), x.clone()))).collect())
    }

    fn allowed(&self, ctx: &Ctx, tables: &[&str]) -> Result<()> {
        for t in tables {
            if self.cat.table(t).is_none() {
                bail!("表不存在：{t}");
            }
            if !ctx.role.allows(t) {
                bail!("权限不足：角色 {} 不能访问表 {t}", ctx.role.name);
            }
        }
        Ok(())
    }

    // ───────────────────────── 经验库：查、守卫、撤销 ─────────────────────────

    async fn lookup(&self, ctx: &Ctx, key: &str) -> Result<Lookup> {
        let fk = self.fk(ctx, key);
        let Some(e) = self.store.get(&fk) else {
            inc(&self.stats.misses);
            return Ok(Lookup::Miss);
        };
        if e.status != Status::Valid || !e.deps.keys().all(|t| ctx.role.allows(t)) {
            inc(&self.stats.misses);
            return Ok(Lookup::Miss);
        }
        if self.cfg.guard == GuardMode::Off {
            return Ok(self.hit(ctx, &fk, e));
        }
        let cur = self.versions().await?;
        let changed: Vec<String> = e.deps.iter().filter(|(t, v)| cur.get(*t) != Some(*v)).map(|(t, _)| t.clone()).collect();
        if changed.is_empty() && self.cfg.guard == GuardMode::OnChange {
            return Ok(self.hit(ctx, &fk, e));
        }
        if e.guards.is_empty() {
            if changed.is_empty() {
                return Ok(self.hit(ctx, &fk, e));
            }
            // 没有可重验的不变量（如表画像、查询结果）：依赖一变就作废，下次重新探查
            self.revoke(&fk, &e, format!("依赖的表 {} 已变化", changed.join("、")), false);
            inc(&self.stats.misses);
            return Ok(Lookup::Miss);
        }
        let always = self.cfg.guard == GuardMode::Always;
        let to_run: Vec<Check> = e.guards.iter().filter(|g| always || g.tables().iter().any(|t| changed.contains(t))).cloned().collect();
        for g in &to_run {
            inc(&self.stats.guard_runs);
            let o = self.exec_check(ctx, g, QKind::Guard).await?.0;
            self.log(ctx, format!("守卫「{}」→ {}", g.describe(), if o.pass { "通过" } else { "失败" }));
            if !o.pass {
                inc(&self.stats.guard_fails);
                self.revoke(&fk, &e, format!("守卫失败：{}，{}", g.describe(), outcome_text(g, &o)), true);
                return Ok(Lookup::Violated { entry: e, failed: g.clone() });
            }
        }
        let new_deps: BTreeMap<String, TableVersion> = e.deps.keys().filter_map(|t| cur.get(t).map(|v| (t.clone(), v.clone()))).collect();
        self.store.update(&fk, |x| x.deps = new_deps);
        Ok(self.hit(ctx, &fk, e))
    }

    fn hit(&self, ctx: &Ctx, fk: &str, e: Entry) -> Lookup {
        inc(&self.stats.hits);
        self.store.update(fk, |x| {
            x.hits += 1;
            x.consumers.insert(ctx.agent.clone());
        });
        Lookup::Hit(e)
    }

    fn revoke(&self, fk: &str, e: &Entry, reason: String, notify: bool) {
        inc(&self.stats.revocations);
        self.store.update(fk, |x| x.status = Status::Revoked(reason.clone()));
        if notify {
            let mut n = self.notices.lock();
            for a in &e.consumers {
                n.entry(a.clone())
                    .or_default()
                    .push(format!("你用过的经验「{}」已撤销（{}）。此前基于它得到的结果建议复核。", e.key, reason));
                inc(&self.stats.notices);
            }
        }
    }

    pub fn take_notices(&self, agent: &str) -> Vec<String> {
        self.notices.lock().remove(agent).unwrap_or_default()
    }

    fn new_entry(&self, ctx: &Ctx, key: &str, content: Content, deps: BTreeMap<String, TableVersion>, guards: Vec<Check>) -> Entry {
        Entry {
            key: key.to_string(),
            content,
            deps,
            guards,
            status: Status::Valid,
            created_by: ctx.agent.clone(),
            hits: 0,
            consumers: [ctx.agent.clone()].into_iter().collect(),
            revision: 0,
        }
    }

    // ───────────────────────── 检查 ─────────────────────────

    /// 执行一个检查（不看经验库），在途合并，并把结果写进经验库。
    async fn exec_check(&self, ctx: &Ctx, c: &Check, kind: QKind) -> Result<(Outcome, bool)> {
        let deps = self.deps_for(&c.tables()).await?;
        let fkey = self.fk(ctx, &format!("{}@{}", c.key(), ver_sig(&deps)));
        let sql = c.sql();
        let (o, merged) = self
            .flight_c
            .run(self.cfg.singleflight, &fkey, || async {
                let t = Instant::now();
                let rows = self.db.query(kind, &sql).await?;
                let o = c.eval(&rows, t.elapsed().as_secs_f64() * 1000.0);
                if kind == QKind::Check {
                    self.fb.record(c, &o, &self.rows());
                }
                Ok(o)
            })
            .await?;
        let key = format!("check:{}", c.key());
        let content = Content::CheckResult { check: c.clone(), outcome: o.clone() };
        self.trace(
            ctx,
            json!({"event":"check","check":c,"purpose":kind.name(),"source":if merged {"merged"} else {"executed"},"outcome":o}),
        );
        self.store.put(&self.fk(ctx, &key), self.new_entry(ctx, &key, content, deps, vec![]));
        Ok((o, merged))
    }

    /// 经验库里是否已有该检查的有效结果。只读探测，不跑守卫；排序时把它视为零代价，真正使用仍经过 `lookup`。
    fn cached(&self, ctx: &Ctx, c: &Check) -> bool {
        self.store.get(&self.fk(ctx, &format!("check:{}", c.key()))).is_some_and(|e| e.status == Status::Valid)
    }

    /// 先查经验库里的检查结果，没有再执行。返回结果，以及本次是否实际访问了数据库（复用与合并都不算）。
    async fn run_check(&self, ctx: &Ctx, c: &Check) -> Result<(Outcome, bool)> {
        if let Lookup::Hit(e) = self.lookup(ctx, &format!("check:{}", c.key())).await? {
            if let Content::CheckResult { outcome, .. } = e.content {
                self.fb.record_reuse(c);
                self.trace(ctx, json!({"event":"check","check":c,"source":"reused","outcome":outcome}));
                self.log(ctx, format!("复用检查「{}」", c.describe()));
                return Ok((outcome, false));
            }
        }
        let (o, merged) = self.exec_check(ctx, c, QKind::Check).await?;
        if merged {
            self.fb.record_reuse(c);
        }
        self.log(
            ctx,
            format!(
                "{}检查「{}」→ {}（{:.0} ms）",
                if merged { "合并" } else { "执行" },
                c.describe(),
                if o.pass { "通过" } else { "失败" },
                o.ms
            ),
        );
        Ok((o, !merged))
    }

    // ───────────────────────── 工具：表 ─────────────────────────

    pub fn list_tables(&self, ctx: &Ctx) -> Value {
        let t: Vec<Value> = self
            .cat
            .tables
            .values()
            .filter(|t| ctx.role.allows(&t.name))
            .map(|t| json!({"table": t.name, "rows_est": t.rows_est as i64, "columns": t.cols.len(), "comment": t.comment}))
            .collect();
        json!({ "tables": t })
    }

    pub async fn describe_table(&self, ctx: &Ctx, table: &str) -> Result<Value> {
        self.allowed(ctx, &[table])?;
        let key = format!("profile:{table}");
        if let Lookup::Hit(e) = self.lookup(ctx, &key).await? {
            if let Content::Profile(v) = e.content {
                self.log(ctx, format!("复用表画像 {table}"));
                return Ok(json!({"profile": v, "source": "reused"}));
            }
        }
        let deps = self.deps_for(&[table.to_string()]).await?;
        let (v, merged) = self
            .flight_v
            .run(self.cfg.singleflight, &self.fk(ctx, &format!("profile:{table}@{}", ver_sig(&deps))), || self.probe_table(table))
            .await?;
        self.log(ctx, format!("{}探查表 {table}", if merged { "合并" } else { "执行" }));
        self.store.put(&self.fk(ctx, &key), self.new_entry(ctx, &key, Content::Profile(v.clone()), deps, vec![]));
        Ok(json!({"profile": v, "source": if merged { "merged" } else { "explored" }}))
    }

    async fn probe_table(&self, table: &str) -> Result<Value> {
        let t = self.cat.table(table).ok_or_else(|| anyhow!("表不存在：{table}"))?;
        let cnts: Vec<String> = t.cols.iter().map(|c| format!("count({})", c.name)).collect();
        let r = self.db.query(QKind::Probe, &format!("select count(*), {} from {table}", cnts.join(", "))).await?;
        let n = r.i64(0, 0).unwrap_or(0);
        let sample = self.db.query(QKind::Probe, &format!("select * from {table} limit 3")).await?;
        let st = self
            .db
            .query(
                QKind::Meta,
                &format!(
                    "select attname, n_distinct, most_common_vals::text from pg_stats \
                     where schemaname = 'public' and tablename = {}",
                    lit(table)
                ),
            )
            .await?;
        let mut stats: HashMap<String, (f64, Option<String>)> = HashMap::new();
        for i in 0..st.rows.len() {
            if let Some(c) = st.cell(i, 0) {
                stats.insert(c.to_string(), (st.f64(i, 1).unwrap_or(0.0), st.cell(i, 2).map(str::to_string)));
            }
        }
        let cols: Vec<Value> = t
            .cols
            .iter()
            .enumerate()
            .map(|(i, c)| {
                let nn = r.i64(0, i + 1).unwrap_or(0);
                let (nd, mcv) = stats.get(&c.name).cloned().unwrap_or((0.0, None));
                let nd_abs = if nd < 0.0 { -nd * n as f64 } else { nd };
                let mut v = json!({
                    "name": c.name, "type": c.dtype,
                    "null_ratio": if n > 0 { 1.0 - nn as f64 / n as f64 } else { 0.0 },
                    "distinct_est": nd_abs.round() as i64,
                });
                if let Some(cm) = &c.comment {
                    v["comment"] = json!(cm);
                }
                if (1.0..=20.0).contains(&nd_abs) {
                    v["common_values"] = json!(mcv);
                }
                v
            })
            .collect();
        Ok(json!({"table": table, "comment": t.comment, "row_count": n, "columns": cols, "sample_rows": sample.to_json(3)}))
    }

    // ───────────────────────── 工具：关联 ─────────────────────────

    /// 读取（必要时重验）某表对的关联经验。
    async fn join_entry(&self, ctx: &Ctx, a: &str, b: &str) -> Result<(Vec<JoinPath>, Vec<BadPath>, &'static str)> {
        let key = join_key(a, b);
        match self.lookup(ctx, &key).await? {
            Lookup::Hit(e) => match e.content {
                Content::Join { paths, bad } => Ok((paths, bad, "reused")),
                _ => Ok((vec![], vec![], "none")),
            },
            Lookup::Miss => Ok((vec![], vec![], "none")),
            Lookup::Violated { entry, failed } => {
                let Content::Join { paths, bad } = entry.content else { return Ok((vec![], vec![], "none")) };
                let hint = match &failed {
                    Check::KeyUnique { table, cols, .. } => Some((table.clone(), cols.clone())),
                    _ => None,
                };
                self.log(ctx, format!("关联经验 {key} 失效，重新验证并尝试修复粒度"));
                let mut new_paths = vec![];
                let mut new_bad = bad;
                for p in paths {
                    let mut filters = p.filters.clone();
                    if let Some((t, _)) = &hint {
                        filters.remove(t);
                    }
                    match self.validate(ctx, &p.left, &p.right, &p.on, filters, hint.clone()).await? {
                        Ok(np) => new_paths.push(np),
                        Err(x) => new_bad.push(x),
                    }
                }
                self.save_join(ctx, a, b, new_paths.clone(), new_bad.clone(), entry.revision + 1).await?;
                Ok((new_paths, new_bad, "revalidated"))
            }
        }
    }

    async fn save_join(&self, ctx: &Ctx, a: &str, b: &str, paths: Vec<JoinPath>, bad: Vec<BadPath>, rev: u32) -> Result<()> {
        let key = join_key(a, b);
        let deps = self.deps_for(&[a.to_string(), b.to_string()]).await?;
        let guards: Vec<Check> = paths.iter().flat_map(|p| p.guards()).collect();
        let mut e = self.new_entry(ctx, &key, Content::Join { paths, bad }, deps, guards);
        e.revision = rev;
        self.store.put(&self.fk(ctx, &key), e);
        Ok(())
    }

    /// 把一次验证结论并入表对的关联经验。
    async fn merge_join(&self, ctx: &Ctx, a: &str, b: &str, verdict: &std::result::Result<JoinPath, BadPath>) -> Result<()> {
        let fk = self.fk(ctx, &join_key(a, b));
        let (mut paths, mut bad, rev) = match self.store.get(&fk) {
            Some(Entry { content: Content::Join { paths, bad }, status: Status::Valid, revision, .. }) => (paths, bad, revision),
            _ => (vec![], vec![], 0),
        };
        match verdict {
            Ok(p) if !paths.iter().any(|x| same_on(&x.on, &p.on)) => paths.push(p.clone()),
            Err(x) if !bad.iter().any(|y| same_on(&y.on, &x.on)) => bad.push(x.clone()),
            _ => {}
        }
        self.save_join(ctx, a, b, paths, bad, rev).await
    }

    /// 验证一个具体写法：left 为“多”侧，right 为“一”侧。
    /// 返回 Ok(路径) 或 Err(反例)。遇到“几乎唯一”的键会尝试修复粒度（找一个能恢复唯一性的行过滤）。
    async fn validate(
        &self,
        ctx: &Ctx,
        left: &str,
        right: &str,
        on: &On,
        mut filters: BTreeMap<String, String>,
        hint: Option<(String, Vec<String>)>,
    ) -> Result<std::result::Result<JoinPath, BadPath>> {
        let mut tried_repair: BTreeSet<String> = BTreeSet::new();
        if let Some((t, cols)) = hint {
            tried_repair.insert(t.clone());
            if let Some(f) = self.repair_grain(ctx, &t, &cols).await? {
                filters.insert(t, f);
            }
        }
        let lcols: Vec<String> = on.iter().map(|(l, _)| l.clone()).collect();
        let rcols: Vec<String> = on.iter().map(|(_, r)| r.clone()).collect();
        'retry: loop {
            let lf = filters.get(left).cloned();
            let rf = filters.get(right).cloned();
            let key_check = Check::KeyUnique { table: right.into(), cols: rcols.clone(), filter: rf.clone() };
            let checks = vec![
                key_check.clone(),
                Check::RowConservation { left: left.into(), right: right.into(), on: on.clone(), lf: lf.clone(), rf: rf.clone() },
                Check::SampleFanout { left: left.into(), right: right.into(), on: on.clone(), lf: lf.clone(), rf: rf.clone(), n: 1000 },
            ];
            let rows = self.rows();
            let ordered = self.fb.order(self.cfg.feedback, checks, &rows, &|c: &Check| self.cached(ctx, c));
            self.trace(
                ctx,
                json!({"event":"planned_order","left":left,"right":right,"checks":ordered.iter().map(Check::kind).collect::<Vec<_>>()}),
            );
            let mut seen: Vec<Obs> = vec![];
            let mut key_outcome: Option<Outcome> = None;
            let mut rc: Option<Outcome> = None;
            let mut failed: Option<(Check, Outcome)> = None;
            let mut audited = false;
            for (idx, c) in ordered.iter().enumerate() {
                let (o, executed) = self.run_check(ctx, c).await?;
                seen.push(Obs::new(c, &o, executed, &rows));
                if *c == key_check {
                    key_outcome = Some(o.clone());
                }
                if o.pass {
                    if matches!(c, Check::RowConservation { .. }) {
                        rc = Some(o);
                    }
                    continue;
                }
                // 反馈的无偏性：排在后面的检查只见过“前面都通过”的候选，永远学不到它们也能发现问题。
                // 以小概率把剩余检查也跑完（审计），代价照常计入。是否审计只取决于候选，与顺序和结果无关，
                // 所以被审计的失败候选是回放其他顺序的无偏样本。
                let audit = match self.cfg.audit_seed {
                    Some(seed) => audit_candidate(seed, &serde_json::to_string(&(left, right, on, &filters))?),
                    None => rand::random::<f64>() < AUDIT_RATE,
                };
                if self.cfg.feedback && audit {
                    audited = true;
                    for rest in &ordered[idx + 1..] {
                        let (ro, merged) = self.exec_check(ctx, rest, QKind::Check).await?;
                        seen.push(Obs::new(rest, &ro, !merged, &rows));
                        if *rest == key_check {
                            key_outcome = Some(ro);
                        }
                    }
                }
                failed = Some((c.clone(), o));
                break;
            }
            if let Some((c, o)) = failed {
                // 重排不改变结论：抽样扇出、行数守恒失败都蕴含右侧键不唯一，但是否修复粒度要看键唯一性的平均倍数。
                // 其他检查先失败时补查键唯一性（常可复用），因此修复与判定和默认顺序一致。
                let probe_key = !tried_repair.contains(right);
                let probed = key_outcome.is_none() && probe_key;
                if probed {
                    key_outcome = Some(self.run_check(ctx, &key_check).await?.0);
                }
                self.trace(
                    ctx,
                    json!({"event":"validation_failed","left":left,"right":right,"first_failed":c.kind(),"audited":audited,"key_probe":probed}),
                );
                self.fb.episode(seen, audited, probe_key);
                if let Some(ko) = key_outcome.as_ref().filter(|ko| !ko.pass) {
                    let avg = metric(ko, "avg_mult");
                    if avg > 1.0 && avg < 1.5 && tried_repair.insert(right.to_string()) {
                        if let Some(f) = self.repair_grain(ctx, right, &rcols).await? {
                            filters.insert(right.to_string(), f);
                            continue 'retry;
                        }
                    }
                }
                // 反例说明优先取键唯一性的结果，不同顺序给出同样的诊断
                let (c, o) = match key_outcome {
                    Some(ko) if !ko.pass => (key_check, ko),
                    _ => (c, o),
                };
                return Ok(Err(BadPath {
                    left: left.into(),
                    right: right.into(),
                    on: on.clone(),
                    reason: format!("{}：{}", c.describe(), outcome_text(&c, &o)),
                    fanout: fanout_of(&c, &o),
                }));
            }
            self.fb.episode(seen, audited, false);
            let rc = rc.ok_or_else(|| anyhow!("缺少行数守恒检查"))?;
            let (n_left, n_right, n_join) = (metric(&rc, "n_left") as i64, metric(&rc, "n_right") as i64, metric(&rc, "n_join") as i64);
            // 基数：若关联行数不超过右表行数，左侧也可能唯一（1:1），需要确认——它会成为守卫
            let mut left_unique = false;
            if n_join <= n_right {
                let c = Check::KeyUnique { table: left.into(), cols: lcols.clone(), filter: lf.clone() };
                let (o, _) = self.run_check(ctx, &c).await?;
                left_unique = o.pass;
                let avg = metric(&o, "avg_mult");
                if !o.pass && avg > 1.0 && avg < 1.5 && tried_repair.insert(left.to_string()) {
                    if let Some(f) = self.repair_grain(ctx, left, &lcols).await? {
                        filters.insert(left.to_string(), f);
                        continue 'retry;
                    }
                }
            }
            let loss = if n_left > 0 { 1.0 - n_join as f64 / n_left as f64 } else { 0.0 };
            let mut evidence = vec![format!("{left} {n_left} 行中 {n_join} 行关联得上（{:.1}% 关联不上）", loss.max(0.0) * 100.0)];
            for (t, f) in &filters {
                evidence.push(format!("{t} 需过滤 {f} 才能保持每键一行"));
            }
            let p = JoinPath {
                left: left.into(),
                right: right.into(),
                on: on.clone(),
                filters: filters.clone(),
                left_unique,
                right_unique: true,
                n_left,
                n_join,
                loss_ratio: loss.max(0.0),
                evidence,
            };
            self.log(ctx, format!("验证通过 {left}⋈{right} {} 基数 {}", fmt_on(on), p.cardinality()));
            return Ok(Ok(p));
        }
    }

    /// 两个方向都试（小表先作“一”侧）。
    async fn validate_pair(&self, ctx: &Ctx, a: &str, b: &str, on: &On) -> Result<std::result::Result<JoinPath, BadPath>> {
        let orients = if self.cat.rows(a) >= self.cat.rows(b) {
            [(a, b, on.clone()), (b, a, flip(on))]
        } else {
            [(b, a, flip(on)), (a, b, on.clone())]
        };
        let mut worst: Option<BadPath> = None;
        for (l, r, o) in orients {
            match self.validate(ctx, l, r, &o, BTreeMap::new(), None).await? {
                Ok(p) => return Ok(Ok(p)),
                Err(x) => {
                    if worst.as_ref().is_none_or(|w| x.fanout > w.fanout) {
                        worst = Some(x);
                    }
                }
            }
        }
        let mut w = worst.ok_or_else(|| anyhow!("无验证结果"))?;
        w.reason = format!("两侧键都不唯一（多对多，会膨胀）。{}", w.reason);
        Ok(Err(w))
    }

    /// 粒度修复：`table` 在 `cols` 上几乎唯一时，找一个低基数列上的取值，
    /// 使过滤后键唯一且不丢任何键（例如状态流水表只取“完成”状态）。
    async fn repair_grain(&self, ctx: &Ctx, table: &str, cols: &[String]) -> Result<Option<String>> {
        let st = self
            .db
            .query(
                QKind::Meta,
                &format!(
                    "select s.attname, case when s.n_distinct < 0 then -s.n_distinct * c.reltuples else s.n_distinct end \
                     from pg_stats s join pg_namespace n on n.nspname = s.schemaname \
                     join pg_class c on c.relnamespace = n.oid and c.relname = s.tablename \
                     where s.schemaname = 'public' and s.tablename = {}",
                    lit(table)
                ),
            )
            .await?;
        let mut cands: Vec<(f64, String)> = (0..st.rows.len())
            .filter_map(|i| Some((st.f64(i, 1)?, st.cell(i, 0)?.to_string())))
            .filter(|(nd, c)| (1.0..=20.0).contains(nd) && !cols.contains(c))
            .collect();
        cands.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
        let key = if cols.len() == 1 { cols[0].clone() } else { format!("({})", cols.join(", ")) };
        let nn: Vec<String> = cols.iter().map(|c| format!("{c} is not null")).collect();
        let total = self
            .db
            .query(QKind::Repair, &format!("select count(distinct {key}) from {table} where {}", nn.join(" and ")))
            .await?
            .i64(0, 0)
            .unwrap_or(0);
        for (_, c) in cands {
            let r = self
                .db
                .query(
                    QKind::Repair,
                    &format!("select {c}::text, count(*), count(distinct {key}) from {table} where {} group by {c}", nn.join(" and ")),
                )
                .await?;
            for i in 0..r.rows.len() {
                let (Some(v), Some(n), Some(k)) = (r.cell(i, 0), r.i64(i, 1), r.i64(i, 2)) else { continue };
                if n == k && k == total {
                    let f = format!("{c} = {}", lit(v));
                    inc(&self.stats.repairs);
                    self.log(ctx, format!("粒度修复：{table} 取 {f} 后每个键恰好一行"));
                    self.save_grain(ctx, table, cols, &f).await?;
                    return Ok(Some(f));
                }
            }
        }
        self.log(ctx, format!("粒度修复：{table} 没找到能恢复唯一性的过滤"));
        Ok(None)
    }

    async fn save_grain(&self, ctx: &Ctx, table: &str, cols: &[String], filter: &str) -> Result<()> {
        let key = format!("grain:{table}");
        let deps = self.deps_for(&[table.to_string()]).await?;
        let guard = Check::KeyUnique { table: table.into(), cols: cols.to_vec(), filter: Some(filter.into()) };
        let content = Content::Profile(json!({"table": table, "key": cols, "filter": filter}));
        self.store.put(&self.fk(ctx, &key), self.new_entry(ctx, &key, content, deps, vec![guard]));
        Ok(())
    }

    /// 工具 join_path：两表怎么关联？已知就复用，未知就探索（先单列、再补第二列）。
    pub async fn join_path(&self, ctx: &Ctx, a: &str, b: &str) -> Result<Value> {
        self.allowed(ctx, &[a, b])?;
        let (paths, bad, src) = self.join_entry(ctx, a, b).await?;
        if !paths.is_empty() {
            self.log(ctx, format!("复用关联经验 {a}⋈{b}（{src}）"));
            return Ok(json!({"paths": paths, "known_bad": bad, "source": src}));
        }
        let fkey = format!("explore:{}@{}", join_key(a, b), self.scope_key(ctx));
        let (v, merged) = self.flight_v.run(self.cfg.singleflight, &fkey, || self.explore_join(ctx, a, b, bad.clone())).await?;
        let paths: Vec<JoinPath> = serde_json::from_value(v["paths"].clone()).unwrap_or_default();
        let bad: Vec<BadPath> = serde_json::from_value(v["bad"].clone()).unwrap_or_default();
        self.save_join(ctx, a, b, paths.clone(), bad.clone(), 0).await?;
        let note = if paths.is_empty() { Some("没有找到可靠的关联路径") } else { None };
        Ok(json!({"paths": paths, "known_bad": bad, "source": if merged { "merged" } else { "explored" }, "note": note}))
    }

    async fn explore_join(&self, ctx: &Ctx, a: &str, b: &str, mut bad: Vec<BadPath>) -> Result<Value> {
        let mut pairs = self.cat.match_pairs(a, b);
        if pairs.is_empty() {
            return Ok(json!({"paths": [], "bad": bad}));
        }
        let (ta, tb) = (self.cat.table(a).unwrap(), self.cat.table(b).unwrap());
        let dist = |p: &(String, String, bool)| ta.distinct_est(&p.0).min(tb.distinct_est(&p.1));
        pairs.sort_by(|x, y| y.2.cmp(&x.2).then(dist(y).partial_cmp(&dist(x)).unwrap_or(std::cmp::Ordering::Equal)));
        let top = pairs[0].clone();
        let mut cands: Vec<On> = vec![vec![(top.0.clone(), top.1.clone())]];
        for p in self.complement_rank(a, b, &top, &pairs[1..]).await?.into_iter().take(2) {
            cands.push(vec![(top.0.clone(), top.1.clone()), (p.0, p.1)]);
        }
        let mut paths = vec![];
        for on in cands {
            if bad.iter().any(|x| same_on(&x.on, &on)) {
                self.log(ctx, format!("跳过已证伪的写法 {}", fmt_on(&on)));
                continue;
            }
            match self.validate_pair(ctx, a, b, &on).await? {
                Ok(p) => {
                    paths.push(p);
                    break;
                }
                Err(x) => {
                    self.log(ctx, format!("写法 {} 被证伪：{}", fmt_on(&on), x.reason));
                    bad.push(x);
                }
            }
        }
        Ok(json!({"paths": paths, "bad": bad}))
    }

    /// 复合键探索：在大表上抽样若干个首列取值，看哪一列能把首列“补全”成唯一键。
    async fn complement_rank(
        &self,
        a: &str,
        b: &str,
        top: &(String, String, bool),
        rest: &[(String, String, bool)],
    ) -> Result<Vec<(String, String, bool)>> {
        if rest.is_empty() {
            return Ok(vec![]);
        }
        let a_big = self.cat.rows(a) >= self.cat.rows(b);
        let (big, base) = if a_big { (a, &top.0) } else { (b, &top.1) };
        let side = |p: &(String, String, bool)| if a_big { p.0.clone() } else { p.1.clone() };
        let cnts: Vec<String> = rest.iter().map(|p| format!("count(distinct ({base}, {}))", side(p))).collect();
        let r = self
            .db
            .query(
                QKind::Probe,
                &format!(
                    "with k as (select distinct {base} from {big} where {base} is not null limit 200) \
                     select count(*), {} from {big} t join k using ({base})",
                    cnts.join(", ")
                ),
            )
            .await?;
        let mut ranked: Vec<(i64, (String, String, bool))> =
            rest.iter().enumerate().map(|(i, p)| (r.i64(0, i + 1).unwrap_or(0), p.clone())).collect();
        ranked.sort_by_key(|x| std::cmp::Reverse(x.0));
        Ok(ranked.into_iter().map(|(_, p)| p).collect())
    }

    /// 某个具体写法是否成立（先查经验，未知才验证）。
    async fn verdict(&self, ctx: &Ctx, a: &str, b: &str, on: &On) -> Result<(std::result::Result<JoinPath, BadPath>, &'static str)> {
        let (paths, bad, src) = self.join_entry(ctx, a, b).await?;
        if let Some(p) = paths.iter().find(|p| same_on(&p.on, on)) {
            return Ok((Ok(p.clone()), src));
        }
        if let Some(x) = bad.iter().find(|x| same_on(&x.on, on)) {
            return Ok((Err(x.clone()), src));
        }
        let fkey = format!("verdict:{}:{}@{}", join_key(a, b), fmt_on(on), self.scope_key(ctx));
        let (v, merged) = self
            .flight_v
            .run(self.cfg.singleflight, &fkey, || async {
                let r = self.validate_pair(ctx, a, b, on).await?;
                Ok(match r {
                    Ok(p) => json!({"ok": p}),
                    Err(x) => json!({"bad": x}),
                })
            })
            .await?;
        let r = match v.get("ok") {
            Some(p) => Ok(serde_json::from_value::<JoinPath>(p.clone())?),
            None => Err(serde_json::from_value::<BadPath>(v["bad"].clone())?),
        };
        self.merge_join(ctx, a, b, &r).await?;
        Ok((r, if merged { "merged" } else { "explored" }))
    }

    /// 工具 check_join：验证 Agent 给出的关联写法。
    pub async fn check_join(&self, ctx: &Ctx, a: &str, b: &str, on: &On) -> Result<Value> {
        self.allowed(ctx, &[a, b])?;
        self.cat.validate_join(a, b, on)?;
        let (r, src) = self.verdict(ctx, a, b, on).await?;
        Ok(match r {
            Ok(p) => json!({"valid": true, "path": p, "source": src}),
            Err(x) => json!({"valid": false, "bad": x, "source": src}),
        })
    }

    // ───────────────────────── 工具：执行 ─────────────────────────

    pub async fn run_sql(&self, ctx: &Ctx, sql: &str) -> Result<Value> {
        let s = sql.trim().trim_end_matches(';').trim();
        let low = s.to_lowercase();
        if !(low.starts_with("select") || low.starts_with("with")) || s.contains(';') {
            bail!("只允许单条只读查询（SELECT / WITH）");
        }
        let tables: Vec<String> = sqlscan::tables(s, &self.cat).into_iter().collect();
        self.allowed(ctx, &tables.iter().map(String::as_str).collect::<Vec<_>>())?;
        if self.cfg.validate_sql {
            if let Some(rej) = self.review_sql(ctx, s, &tables).await? {
                inc(&self.stats.rejections);
                self.log(ctx, format!("拦下 SQL：{}", rej["reason"].as_str().unwrap_or("")));
                return Ok(rej);
            }
        }
        let norm = sqlscan::normalize(s);
        let key = format!("result:{norm}");
        if self.cfg.result_cache {
            if let Lookup::Hit(e) = self.lookup(ctx, &key).await? {
                if let Content::Result(v) = e.content {
                    self.log(ctx, "复用相同查询的结果");
                    return Ok(json!({"result": v, "source": "reused"}));
                }
            }
        }
        let deps = self.deps_for(&tables).await?;
        let max_rows = self.cfg.max_rows;
        let (v, merged) = self
            .flight_v
            .run(self.cfg.singleflight, &self.fk(ctx, &format!("sql:{norm}@{}", ver_sig(&deps))), || async {
                Ok(self.db.query(QKind::Exec, s).await?.to_json(max_rows))
            })
            .await?;
        if self.cfg.result_cache {
            self.store.put(&self.fk(ctx, &key), self.new_entry(ctx, &key, Content::Result(v.clone()), deps, vec![]));
        }
        Ok(json!({"result": v, "source": if merged { "merged" } else { "executed" }}))
    }

    /// 执行前审查：关联写法是否已被证伪 / 验证不通过；用到的表是否需要粒度过滤。
    async fn review_sql(&self, ctx: &Ctx, sql: &str, tables: &[String]) -> Result<Option<Value>> {
        for j in sqlscan::joins(sql, &self.cat) {
            let (r, _) = self.verdict(ctx, &j.left, &j.right, &j.on).await?;
            if let Err(bad) = r {
                let sugg = self.join_path(ctx, &j.left, &j.right).await?;
                return Ok(Some(json!({
                    "rejected": true,
                    "reason": format!("关联 {}⋈{} 按 {} 不可靠：{}", j.left, j.right, fmt_on(&j.on), bad.reason),
                    "fanout": bad.fanout,
                    "suggestion": sugg["paths"],
                })));
            }
        }
        for t in tables {
            let key = format!("grain:{t}");
            if self.store.get(&self.fk(ctx, &key)).is_none() {
                continue;
            }
            if let Lookup::Hit(e) = self.lookup(ctx, &key).await? {
                if let Content::Profile(g) = e.content {
                    let f = g["filter"].as_str().unwrap_or_default();
                    if !sqlscan::contains_filter(sql, f) {
                        return Ok(Some(json!({
                            "rejected": true,
                            "reason": format!("表 {t} 现在每个键有多行（状态流水）；统计前需要加过滤 {f}，否则会重复计算"),
                            "required_filter": {"table": t, "filter": f},
                        })));
                    }
                }
            }
        }
        Ok(None)
    }

    // ───────────────────────── 工具调度（HTTP 与 LLM 共用） ─────────────────────────

    pub async fn call_tool(&self, ctx: &Ctx, name: &str, args: &Value) -> Result<Value> {
        let s = |k: &str| args.get(k).and_then(Value::as_str).ok_or_else(|| anyhow!("缺少参数 {k}"));
        let mut v = match name {
            "list_tables" => self.list_tables(ctx),
            "describe_table" => self.describe_table(ctx, s("table")?).await?,
            "join_path" => self.join_path(ctx, s("table_a")?, s("table_b")?).await?,
            "check_join" => {
                let on: On = serde_json::from_value(args.get("on").cloned().unwrap_or_default())
                    .map_err(|_| anyhow!("参数 on 应为 [[左列, 右列], ...]"))?;
                self.check_join(ctx, s("left")?, s("right")?, &on).await?
            }
            "run_sql" => self.run_sql(ctx, s("sql")?).await?,
            _ => bail!("未知工具：{name}"),
        };
        let notes = self.take_notices(&ctx.agent);
        if !notes.is_empty() {
            v["notices"] = json!(notes);
        }
        Ok(v)
    }
}

/// 工具说明（JSON Schema），供 LLM 与 HTTP 客户端使用。
#[derive(Clone, Debug, Serialize)]
pub struct ToolSpec {
    pub name: &'static str,
    pub description: &'static str,
    pub schema: Value,
}

pub fn tool_specs(middle_tools: bool) -> Vec<ToolSpec> {
    let mut v = vec![
        ToolSpec {
            name: "list_tables",
            description: "列出可访问的表（估计行数、列数、注释）。",
            schema: json!({"type": "object", "properties": {}}),
        },
        ToolSpec {
            name: "describe_table",
            description: "查看一张表：列名、类型、注释、空值比例、不同值个数估计、低基数列的常见取值、3 行样例。",
            schema: json!({"type": "object", "properties": {"table": {"type": "string"}}, "required": ["table"]}),
        },
        ToolSpec {
            name: "run_sql",
            description: "执行一条只读 SQL（PostgreSQL 方言），返回最多 50 行。",
            schema: json!({"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}),
        },
    ];
    if middle_tools {
        v.push(ToolSpec {
            name: "join_path",
            description: "询问两张表应该怎样关联：返回验证过的关联列、基数（1:1 / N:1）、需要的行过滤、关联不上的比例，以及已被证伪的写法。",
            schema: json!({"type": "object", "properties": {"table_a": {"type": "string"}, "table_b": {"type": "string"}}, "required": ["table_a", "table_b"]}),
        });
        v.push(ToolSpec {
            name: "check_join",
            description: "验证一个具体的关联写法（left 为多侧、right 为一侧），on 形如 [[\"left_col\", \"right_col\"], ...]。",
            schema: json!({"type": "object", "properties": {
                "left": {"type": "string"}, "right": {"type": "string"},
                "on": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}
            }, "required": ["left", "right", "on"]}),
        });
    }
    v
}
