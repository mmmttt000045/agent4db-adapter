//! 脚本模拟 Agent 与三组实验，外加一个按 PPT 故事线走的演示。
//! 模拟 Agent 的行为参数（陷阱概率等）是设定值，结果中的数据库负载、正确率均为本机实测。

use crate::catalog::Catalog;
use crate::checks::{flip, On};
use crate::db::{Db, MeterSnap, QKind};
use crate::etl;
use crate::knowledge::{Content, JoinPath};
use crate::middle::{Ctx, GuardMode, Middle, MiddleConfig, Scope};
use crate::workload::{self, gold_return_rate_sql, return_rate_sql, Channel, Period};
use anyhow::{anyhow, bail, Result};
use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::Semaphore;

// ───────────────────────── 公共工具 ─────────────────────────

pub fn diff(a: &MeterSnap, b: &MeterSnap) -> MeterSnap {
    let mut d = MeterSnap { queries: b.queries - a.queries, db_ms: b.db_ms - a.db_ms, by_kind: BTreeMap::new() };
    for (k, (n, ms)) in &b.by_kind {
        let (n0, ms0) = a.by_kind.get(k).copied().unwrap_or((0, 0.0));
        d.by_kind.insert(k.clone(), (n - n0, ms - ms0));
    }
    d
}

fn pct(v: &[f64], p: f64) -> f64 {
    if v.is_empty() {
        return 0.0;
    }
    let mut s = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    s[((s.len() as f64 - 1.0) * p).round() as usize]
}

fn kinds_json(d: &MeterSnap) -> Value {
    let mut m = serde_json::Map::new();
    for (k, (n, ms)) in &d.by_kind {
        if *n > 0 {
            m.insert(k.clone(), json!({"queries": n, "seconds": (ms / 10.0).round() / 100.0}));
        }
    }
    Value::Object(m)
}

/// 把主要大表读一遍，让各组实验在相近的缓存状态下开始。
pub async fn warmup(db: &Db) -> Result<()> {
    for t in [
        "store_sales",
        "store_returns",
        "catalog_sales",
        "catalog_returns",
        "web_sales",
        "web_returns",
        "date_dim",
        "item",
        "customer",
        "customer_address",
        "customer_demographics",
    ] {
        db.query(QKind::Meta, &format!("select count(*) from {t}")).await?;
    }
    Ok(())
}

pub fn md_table(headers: &[&str], rows: &[Vec<String>]) -> String {
    let mut s = format!("| {} |\n|{}|\n", headers.join(" | "), headers.iter().map(|_| "---").collect::<Vec<_>>().join("|"));
    for r in rows {
        s.push_str(&format!("| {} |\n", r.join(" | ")));
    }
    s
}

fn f1(x: f64) -> String {
    format!("{x:.1}")
}

fn base_cfg(name: &str) -> MiddleConfig {
    MiddleConfig {
        name: name.into(),
        scope: Scope::Session,
        singleflight: false,
        guard: GuardMode::OnChange,
        feedback: false,
        validate_sql: false,
        result_cache: false,
        ..Default::default()
    }
}

/// 把关联路径的列方向摆成 (表 a 的列, 表 b 的列)。
fn orient(p: &JoinPath, a: &str) -> On {
    if p.left == a {
        p.on.clone()
    } else {
        flip(&p.on)
    }
}

// ───────────────────────── 实验 1：共享 + 在途合并（数据库负载） ─────────────────────────

pub struct E1Opts {
    pub agents: usize,
    pub sessions: usize,
    pub tasks_per_session: usize,
    pub concurrency: Vec<usize>,
    pub modes: Vec<String>,
    pub seed: u64,
    pub queries_path: String,
}

fn e1_cfg(mode: &str) -> Result<MiddleConfig> {
    let mut c = base_cfg(mode);
    match mode {
        "task" => c.scope = Scope::Task,
        "session" => c.scope = Scope::Session,
        "session+sf" => {
            c.scope = Scope::Session;
            c.singleflight = true
        }
        "agent" => c.scope = Scope::Agent,
        "global" => c.scope = Scope::Global,
        "global+sf" => {
            c.scope = Scope::Global;
            c.singleflight = true
        }
        _ => bail!("未知模式 {mode}（可选 task/session/session+sf/agent/global/global+sf）"),
    }
    Ok(c)
}

pub fn e1_mode_label(m: &str) -> &'static str {
    match m {
        "task" => "每个任务从头查",
        "session" => "会话内复用",
        "session+sf" => "会话内复用 + 在途合并",
        "agent" => "各 Agent 自带记忆",
        "global" => "中间层共享",
        "global+sf" => "中间层共享 + 在途合并",
        _ => "?",
    }
}

type Assign = Vec<(String, String, Vec<usize>)>;

pub async fn e1(db: Arc<Db>, o: &E1Opts) -> Result<(Value, String)> {
    let cat = Catalog::load(&db).await?;
    let tasks = Arc::new(workload::tpcds_tasks(&cat, &o.queries_path)?);
    let (p_all, j_all, dt_all, dj_all) = workload::needs_summary(&tasks);
    let mut rng = StdRng::seed_from_u64(o.seed);
    let mut assign: Assign = vec![];
    for a in 0..o.agents {
        for s in 0..o.sessions {
            let idx = rand::seq::index::sample(&mut rng, tasks.len(), o.tasks_per_session.min(tasks.len())).into_vec();
            assign.push((format!("agent{}", a + 1), format!("s{}", s + 1), idx));
        }
    }
    let picked: Vec<workload::TaskNeeds> = assign.iter().flat_map(|(_, _, v)| v.iter().map(|&i| tasks[i].clone())).collect();
    let (p_req, j_req, dt_req, dj_req) = workload::needs_summary(&picked);
    eprintln!("E1：TPC-DS 99 条查询共需表探查 {p_all} 次、关联验证 {j_all} 次（不同表 {dt_all} 张、不同关联 {dj_all} 种）");
    eprintln!(
        "E1：{} 个 Agent × {} 个会话 × 每会话 {} 个任务 = {} 个任务；需求 {} 次表探查 + {} 次关联验证，去重后 {} + {}",
        o.agents,
        o.sessions,
        o.tasks_per_session,
        picked.len(),
        p_req,
        j_req,
        dt_req,
        dj_req
    );
    warmup(&db).await?;
    let assign = Arc::new(assign);
    let mut results = vec![];
    let mut rows = vec![];
    for &c in &o.concurrency {
        for m in &o.modes {
            let r = e1_run(db.clone(), e1_cfg(m)?, tasks.clone(), assign.clone(), c).await?;
            eprintln!(
                "  并发 {c:>2} | {:<24} | 数据库查询 {:>5} 条 | 数据库耗时 {:>7.1} s | 总耗时 {:>6.1} s | 任务 p95 {:>6.1} s",
                e1_mode_label(m),
                r["db_queries"],
                r["db_seconds"].as_f64().unwrap_or(0.0),
                r["wall_seconds"].as_f64().unwrap_or(0.0),
                r["task_latency_p95_s"].as_f64().unwrap_or(0.0)
            );
            rows.push(vec![
                c.to_string(),
                e1_mode_label(m).to_string(),
                r["db_queries"].to_string(),
                f1(r["db_seconds"].as_f64().unwrap_or(0.0)),
                f1(r["wall_seconds"].as_f64().unwrap_or(0.0)),
                f1(r["task_latency_p50_s"].as_f64().unwrap_or(0.0)),
                f1(r["task_latency_p95_s"].as_f64().unwrap_or(0.0)),
                r["middle"]["knowledge_hits"].to_string(),
                r["middle"]["inflight_merged"].to_string(),
            ]);
            results.push(r);
        }
    }
    let md = format!(
        "### 实验 1：共享与在途合并对数据库负载的影响（实测）\n\n\
         负载：TPC-DS 99 条标准查询各自需要的表探查与关联验证。{} 个 Agent × {} 个会话 × 每会话 {} 个任务（随机抽取，种子 {}），\
         共需 {} 次表探查 + {} 次关联验证；去重后只有 {} 张表 + {} 种关联。\n\n{}",
        o.agents,
        o.sessions,
        o.tasks_per_session,
        o.seed,
        p_req,
        j_req,
        dt_req,
        dj_req,
        md_table(&["并发", "模式", "数据库查询数", "数据库耗时 s", "总耗时 s", "任务 p50 s", "任务 p95 s", "经验命中", "在途合并"], &rows)
    );
    Ok((
        json!({"experiment": "e1", "needs_all": {"probes": p_all, "joins": j_all, "distinct_tables": dt_all, "distinct_joins": dj_all},
               "needs_assigned": {"tasks": picked.len(), "probes": p_req, "joins": j_req, "distinct_tables": dt_req, "distinct_joins": dj_req},
               "runs": results}),
        md,
    ))
}

async fn e1_run(db: Arc<Db>, cfg: MiddleConfig, tasks: Arc<Vec<workload::TaskNeeds>>, assign: Arc<Assign>, conc: usize) -> Result<Value> {
    let mode = cfg.name.clone();
    let mid = Arc::new(Middle::new(db.clone(), cfg).await?);
    let before = db.meter.snap();
    let t0 = Instant::now();
    let sem = Arc::new(Semaphore::new(conc));
    let mut hs = vec![];
    for (agent, sess, idxs) in assign.iter().cloned() {
        let (mid, tasks, sem) = (mid.clone(), tasks.clone(), sem.clone());
        hs.push(tokio::spawn(async move {
            let _p = sem.acquire_owned().await?;
            let mut lats = vec![];
            let mut errors = 0u32;
            for i in idxs {
                let t = &tasks[i];
                let ctx = Ctx::new(&agent, &sess, &format!("q{}", t.id));
                let s = Instant::now();
                for tb in &t.tables {
                    if mid.describe_table(&ctx, tb).await.is_err() {
                        errors += 1;
                    }
                }
                for (l, r, on) in &t.joins {
                    if let Err(e) = mid.check_join(&ctx, l, r, on).await {
                        eprintln!("    check_join 出错：{e:#}");
                        errors += 1;
                    }
                }
                lats.push(s.elapsed().as_secs_f64());
            }
            anyhow::Ok((lats, errors))
        }));
    }
    let mut lats = vec![];
    let mut errors = 0;
    for h in hs {
        let (l, e) = h.await??;
        lats.extend(l);
        errors += e;
    }
    let wall = t0.elapsed().as_secs_f64();
    let d = diff(&before, &db.meter.snap());
    Ok(json!({
        "mode": mode, "concurrency": conc, "wall_seconds": wall,
        "db_queries": d.queries, "db_seconds": d.db_ms / 1000.0, "by_kind": kinds_json(&d),
        "task_latency_p50_s": pct(&lats, 0.5), "task_latency_p95_s": pct(&lats, 0.95),
        "task_latency_mean_s": lats.iter().sum::<f64>() / lats.len().max(1) as f64,
        "tasks": lats.len(), "errors": errors, "middle": mid.stats_json(),
    }))
}

// ───────────────────────── 退货率类任务：模拟 Agent 的做法 ─────────────────────────

#[derive(Debug, Default)]
pub struct Answer {
    pub value: Option<f64>,
    pub sql: String,
    pub rejections: u32,
    pub reasons: Vec<String>,
}

/// 通过中间层问“怎么关联”，拼 SQL，执行；被拦下就按中间层给的原因修改后重试。
async fn ask_via_paths(mid: &Middle, ctx: &Ctx, ch: Channel, p: Period) -> Result<Answer> {
    let rs = mid.join_path(ctx, ch.returns(), ch.sales()).await?;
    let path: JoinPath = serde_json::from_value(rs["paths"][0].clone()).map_err(|_| anyhow!("没有找到退货与销售的关联"))?;
    let on = orient(&path, ch.returns());
    let filter = path.filters.get(ch.returns()).cloned();
    let sd = mid.join_path(ctx, ch.sales(), "date_dim").await?;
    let sdp: JoinPath = serde_json::from_value(sd["paths"][0].clone()).map_err(|_| anyhow!("没有找到销售与日期的关联"))?;
    let d_on = orient(&sdp, ch.sales());
    run_with_retries(mid, ctx, ch, p, on, filter, (d_on[0].0.clone(), d_on[0].1.clone())).await
}

async fn run_with_retries(
    mid: &Middle,
    ctx: &Ctx,
    ch: Channel,
    p: Period,
    mut on: On,
    mut filter: Option<String>,
    date_on: (String, String),
) -> Result<Answer> {
    let mut ans = Answer::default();
    for _ in 0..3 {
        let sql = return_rate_sql(ch, p, &on, filter.as_deref(), &date_on);
        let res = mid.run_sql(ctx, &sql).await?;
        ans.sql = sql;
        if res["rejected"].as_bool() == Some(true) {
            ans.rejections += 1;
            ans.reasons.push(res["reason"].as_str().unwrap_or_default().to_string());
            if let Some(f) = res["required_filter"]["filter"].as_str() {
                filter = Some(f.to_string());
            }
            if let Ok(sp) = serde_json::from_value::<JoinPath>(res["suggestion"][0].clone()) {
                on = orient(&sp, ch.returns());
                filter = sp.filters.get(ch.returns()).cloned().or(filter);
            }
            continue;
        }
        ans.value = res["result"]["rows"][0][0].as_str().and_then(|s| s.parse().ok());
        return Ok(ans);
    }
    Ok(ans)
}

async fn gold_rates(db: &Db, keys: &[(Channel, Period)]) -> Result<HashMap<String, f64>> {
    let mut g = HashMap::new();
    for (ch, p) in keys {
        let k = format!("{ch:?}{p:?}");
        if g.contains_key(&k) {
            continue;
        }
        let v = db.query(QKind::Meta, &gold_return_rate_sql(*ch, *p)).await?.f64(0, 0).unwrap_or(f64::NAN);
        g.insert(k, v);
    }
    Ok(g)
}

fn is_right(v: Option<f64>, gold: f64) -> bool {
    v.is_some_and(|x| (x - gold).abs() <= gold.abs() * 1e-4 + 1e-6)
}

// ───────────────────────── 实验 2：守护（ETL 改版后的静默错误） ─────────────────────────

pub fn e2_modes() -> Vec<&'static str> {
    vec!["fresh-session", "agent-memory", "global-noguard", "global-guard", "global-always"]
}

fn e2_cfg(mode: &str) -> Result<MiddleConfig> {
    let mut c = base_cfg(mode);
    c.validate_sql = true;
    c.singleflight = true;
    match mode {
        "fresh-session" => c.scope = Scope::Session,
        "agent-memory" => {
            c.scope = Scope::Agent;
            c.guard = GuardMode::Off
        }
        "global-noguard" => {
            c.scope = Scope::Global;
            c.guard = GuardMode::Off
        }
        "global-guard" => c.scope = Scope::Global,
        "global-always" => {
            c.scope = Scope::Global;
            c.guard = GuardMode::Always
        }
        _ => bail!("未知模式 {mode}"),
    }
    Ok(c)
}

fn e2_label(m: &str) -> &'static str {
    match m {
        "fresh-session" => "每个会话重新探索",
        "agent-memory" => "各 Agent 自带记忆（不守护）",
        "global-noguard" => "中间层共享（不守护）",
        "global-guard" => "中间层共享 + 守护（变更时）",
        "global-always" => "中间层共享 + 守护（每次）",
        _ => "?",
    }
}

fn months(y: i32, a: u32, b: u32) -> Vec<Period> {
    (a..=b).map(|m| Period::month(y, m)).collect()
}

pub async fn e2(db: Arc<Db>, admin: Arc<Db>, modes: &[String], verbose: bool) -> Result<(Value, String)> {
    etl::setup(&admin).await?;
    etl::reset(&admin).await?;
    let h1 = Period { year: 2002, m1: 1, m2: 6 };
    let plan1: Vec<(&str, Vec<Period>)> =
        vec![("fin-gpt", months(2001, 1, 3)), ("store-claude", months(2001, 4, 6)), ("merch-inhouse", months(2001, 7, 9))];
    let mut plan2: Vec<(&str, Vec<Period>)> = vec![
        ("fin-gpt", months(2001, 10, 12)),
        ("store-claude", months(2002, 1, 3)),
        ("merch-inhouse", months(2002, 4, 6)),
        ("audit-new", months(2001, 7, 9)),
    ];
    for (_, v) in plan2.iter_mut() {
        v.push(h1);
    }
    let keys: Vec<(Channel, Period)> = plan1.iter().chain(plan2.iter()).flat_map(|(_, v)| v.iter().map(|p| (Channel::Store, *p))).collect();
    let gold = gold_rates(&admin, &keys).await?;
    warmup(&db).await?;
    let mut results = vec![];
    let mut rows = vec![];
    for m in modes {
        etl::reset(&admin).await?;
        let mut cfg = e2_cfg(m)?;
        cfg.verbose = verbose;
        let mid = Middle::new(db.clone(), cfg).await?;
        let mut wrong1 = 0;
        for (agent, ps) in &plan1 {
            let ctx = Ctx::new(agent, "s1", "rr");
            for p in ps {
                let a = ask_via_paths(&mid, &ctx, Channel::Store, *p).await?;
                if !is_right(a.value, gold[&format!("{:?}{p:?}", Channel::Store)]) {
                    wrong1 += 1;
                }
            }
        }
        let n_v2 = etl::apply_v2(&admin).await?;
        mid.invalidate_versions();
        let s0 = mid.stats_json();
        let before = db.meter.snap();
        let t0 = Instant::now();
        let (mut wrong2, mut total2, mut notices, mut rejections) = (0, 0, 0, 0);
        let mut h1_answers = vec![];
        let mut first_wrong: Vec<String> = vec![];
        for (agent, ps) in &plan2 {
            let ctx = Ctx::new(agent, "s2", "rr");
            for p in ps {
                let a = ask_via_paths(&mid, &ctx, Channel::Store, *p).await?;
                let g = gold[&format!("{:?}{p:?}", Channel::Store)];
                total2 += 1;
                rejections += a.rejections;
                if !is_right(a.value, g) {
                    wrong2 += 1;
                    if first_wrong.len() < 3 {
                        first_wrong.push(format!("{agent} 问 {}：答 {:.2}%，应为 {:.2}%", p.label(), a.value.unwrap_or(f64::NAN), g));
                    }
                }
                if *p == h1 {
                    h1_answers.push(json!({"agent": agent, "answer": a.value, "gold": g}));
                }
            }
            notices += mid.take_notices(agent).len();
        }
        for (agent, _) in &plan1 {
            notices += mid.take_notices(agent).len();
        }
        let d = diff(&before, &db.meter.snap());
        let s1 = mid.stats_json();
        let delta = |k: &str| s1[k].as_u64().unwrap_or(0) - s0[k].as_u64().unwrap_or(0);
        eprintln!(
            "  {:<28} | 改版前答错 {wrong1} | 改版后答错 {wrong2:>2}/{total2} | 守卫 {} 次（失败 {}）| 修复 {} | 通知 {notices} | 改版后数据库 {:.1} s",
            e2_label(m), delta("guard_runs"), delta("guard_fails"), delta("repairs"), d.db_ms / 1000.0
        );
        rows.push(vec![
            e2_label(m).to_string(),
            format!("{wrong1}"),
            format!("{wrong2}/{total2}"),
            format!("{}/{}", delta("guard_runs"), delta("guard_fails")),
            delta("repairs").to_string(),
            notices.to_string(),
            d.queries.to_string(),
            f1(d.db_ms / 1000.0),
        ]);
        results.push(json!({
            "mode": m, "v2_rows_added": n_v2, "phase1_wrong": wrong1, "phase2_wrong": wrong2, "phase2_total": total2,
            "phase2_rejections": rejections, "notices": notices, "phase2_db_queries": d.queries, "phase2_db_seconds": d.db_ms / 1000.0,
            "phase2_by_kind": kinds_json(&d), "phase2_wall_seconds": t0.elapsed().as_secs_f64(), "h1_2002": h1_answers,
            "examples_wrong": first_wrong, "middle": mid.stats_json(),
        }));
    }
    etl::reset(&admin).await?;
    let md = format!(
        "### 实验 2：ETL 改版后的“静默错误”（实测，改版为模拟场景）\n\n\
         场景：3 个 Agent 先在 v1 上问 2001 年 1–9 月各月门店退货率；随后 ETL 改版（2001-10 起退货改为“申请/完成”两行，表名列名不变）；\
         再由这 3 个 Agent 和 1 个新 Agent 共问 16 个期间（含 2002 上半年）。每个 Agent 先问中间层“怎么关联”，再执行 SQL。\n\n{}",
        md_table(&["模式", "改版前答错", "改版后答错", "守卫 次/失败", "粒度修复", "撤销通知", "改版后查询数", "改版后数据库 s"], &rows)
    );
    Ok((json!({"experiment": "e2", "runs": results}), md))
}

// ───────────────────────── 实验 3：反馈（错误关联 + 检查顺序） ─────────────────────────

pub struct E3Opts {
    pub agents: usize,
    pub sessions: usize,
    pub tasks_per_session: usize,
    pub p_trap: f64,
    pub seed: u64,
    pub modes: Vec<String>,
}

pub fn e3_modes() -> Vec<&'static str> {
    vec!["direct", "A-session-fixed", "C-session-feedback", "B-global-fixed", "D-global-feedback"]
}

fn e3_cfg(mode: &str) -> Result<MiddleConfig> {
    let mut c = base_cfg(mode);
    c.singleflight = true;
    match mode {
        "direct" => {}
        "A-session-fixed" => c.validate_sql = true,
        "C-session-feedback" => {
            c.validate_sql = true;
            c.feedback = true
        }
        "B-global-fixed" => {
            c.validate_sql = true;
            c.scope = Scope::Global
        }
        "D-global-feedback" => {
            c.validate_sql = true;
            c.scope = Scope::Global;
            c.feedback = true
        }
        _ => bail!("未知模式 {mode}"),
    }
    Ok(c)
}

fn e3_label(m: &str) -> &'static str {
    match m {
        "direct" => "直连（不验证）",
        "A-session-fixed" => "A 不共享 · 固定顺序",
        "C-session-feedback" => "C 不共享 · 反馈排序",
        "B-global-fixed" => "B 共享 · 固定顺序",
        "D-global-feedback" => "D 共享 · 反馈排序",
        _ => "?",
    }
}

pub async fn e3(db: Arc<Db>, admin: Arc<Db>, o: &E3Opts) -> Result<(Value, String)> {
    etl::setup(&admin).await?;
    etl::reset(&admin).await?;
    let years = [1999, 2000, 2001, 2002];
    let kinds: Vec<(Channel, Period)> = Channel::ALL.iter().flat_map(|c| years.iter().map(move |y| (*c, Period::year(*y)))).collect();
    let mut rng = StdRng::seed_from_u64(o.seed);
    // 预先抽好每个会话的任务与“是否掉进陷阱”，所有模式看到同样的 Agent 行为
    type SessionPlan = (String, String, Vec<(Channel, Period, bool)>);
    let mut plan: Vec<SessionPlan> = vec![];
    for a in 0..o.agents {
        for s in 0..o.sessions {
            let v = (0..o.tasks_per_session)
                .map(|_| {
                    let (c, p) = kinds[rng.gen_range(0..kinds.len())];
                    (c, p, rng.gen_bool(o.p_trap))
                })
                .collect();
            plan.push((format!("agent{}", a + 1), format!("s{}", s + 1), v));
        }
    }
    let n_tasks: usize = plan.iter().map(|x| x.2.len()).sum();
    let n_traps: usize = plan.iter().flat_map(|x| x.2.iter()).filter(|t| t.2).count();
    let gold = gold_rates(&admin, &kinds).await?;
    warmup(&db).await?;
    let mut results = vec![];
    let mut rows = vec![];
    for m in &o.modes {
        let mid = Middle::new(db.clone(), e3_cfg(m)?).await?;
        let before = db.meter.snap();
        let t0 = Instant::now();
        let (mut wrong, mut rejections) = (0, 0);
        for (agent, sess, tasks) in &plan {
            let ctx = Ctx::new(agent, sess, "rr");
            for (ch, p, trap) in tasks {
                let on = if *trap { ch.trap_on() } else { ch.correct_on() };
                let a = run_with_retries(&mid, &ctx, *ch, *p, on, None, (ch.sold_date().to_string(), "d_date_sk".to_string())).await?;
                rejections += a.rejections;
                if !is_right(a.value, gold[&format!("{ch:?}{p:?}")]) {
                    wrong += 1;
                }
            }
        }
        let d = diff(&before, &db.meter.snap());
        let (nc, cms) = d.kind(QKind::Check);
        let (ne, ems) = d.kind(QKind::Exec);
        eprintln!(
            "  {:<22} | 答错 {wrong:>2}/{n_tasks} | 拦下 {rejections:>2} | 检查 {nc:>3} 条 {:>6.1} s | 执行 {ne:>3} 条 {:>6.1} s | 总 {:>6.1} s",
            e3_label(m), cms / 1000.0, ems / 1000.0, d.db_ms / 1000.0
        );
        rows.push(vec![
            e3_label(m).to_string(),
            format!("{wrong}/{n_tasks}"),
            rejections.to_string(),
            format!("{nc}"),
            f1(cms / 1000.0),
            f1(ems / 1000.0),
            f1(d.db_ms / 1000.0),
        ]);
        results.push(json!({
            "mode": m, "wrong": wrong, "tasks": n_tasks, "traps": n_traps, "rejections": rejections,
            "db_queries": d.queries, "db_seconds": d.db_ms / 1000.0, "by_kind": kinds_json(&d),
            "wall_seconds": t0.elapsed().as_secs_f64(), "middle": mid.stats_json(),
        }));
    }
    let md = format!(
        "### 实验 3：错误关联与反馈排序（实测；Agent 犯错概率为设定值）\n\n\
         {} 个 Agent × {} 个会话 × 每会话 {} 个任务（三个渠道 × 1999–2002 年的退货率），每个任务以 {:.0}% 概率只按单号关联退货与销售（共 {} 次陷阱）。\
         中间层拦下后，Agent 按建议改写重试。\n\n{}",
        o.agents, o.sessions, o.tasks_per_session, o.p_trap * 100.0, n_traps,
        md_table(&["模式", "答错", "拦下", "检查条数", "检查耗时 s", "执行耗时 s", "数据库总耗时 s"], &rows)
    );
    Ok((json!({"experiment": "e3", "tasks": n_tasks, "traps": n_traps, "p_trap": o.p_trap, "runs": results}), md))
}

// ───────────────────────── 演示：按 PPT 的故事线走一遍 ─────────────────────────

fn step(title: &str) {
    eprintln!("\n━━ {title}");
}

fn show_join(mid: &Middle, a: &str, b: &str) {
    let key = if a <= b { format!("join:{a}|{b}") } else { format!("join:{b}|{a}") };
    for e in mid.knowledge().iter().filter(|e| e.key == key) {
        if let Content::Join { paths, bad } = &e.content {
            for p in paths {
                eprintln!("    ✓ {}⋈{} 按 {:?}，基数 {}；{}", p.left, p.right, p.on, p.cardinality(), p.evidence.join("；"));
            }
            for x in bad {
                eprintln!("    ✗ 按 {:?}：{}", x.on, x.reason);
            }
        }
    }
}

pub async fn demo(db: Arc<Db>, admin: Arc<Db>) -> Result<()> {
    etl::setup(&admin).await?;
    etl::reset(&admin).await?;
    let cfg = MiddleConfig { verbose: true, ..Default::default() };
    let mid = Middle::new(db.clone(), cfg).await?;
    let y2001 = Period::year(2001);
    let h1 = Period { year: 2002, m1: 1, m2: 6 };
    let g2001 = db.query(QKind::Meta, &gold_return_rate_sql(Channel::Store, y2001)).await?.f64(0, 0).unwrap_or(0.0);

    step("① 周一 · 财务 Agent（GPT 系）第一次问：2001 年门店退货率");
    let fin = Ctx::new("fin-gpt", "mon", "q1");
    let s = db.meter.snap();
    let a = ask_via_paths(&mid, &fin, Channel::Store, y2001).await?;
    let d = diff(&s, &db.meter.snap());
    eprintln!(
        "  → 答 {:.2}%（标准答案 {g2001:.2}%）；这次打到数据库 {} 条查询，{:.1} s",
        a.value.unwrap_or(f64::NAN),
        d.queries,
        d.db_ms / 1000.0
    );
    eprintln!("  中间层记下的关联经验：");
    show_join(&mid, "store_returns", "store_sales");
    show_join(&mid, "store_sales", "date_dim");

    step("② 周二 · 另一家厂商的门店运营 Agent（Claude 系）自己写 SQL，只按小票号关联");
    let ops = Ctx::new("store-claude", "tue", "q2");
    let s = db.meter.snap();
    let a =
        run_with_retries(&mid, &ops, Channel::Store, y2001, Channel::Store.trap_on(), None, ("ss_sold_date_sk".into(), "d_date_sk".into()))
            .await?;
    let d = diff(&s, &db.meter.snap());
    for r in &a.reasons {
        eprintln!("  中间层拦下：{r}");
    }
    eprintln!(
        "  → 按建议改写后答 {:.2}%；验证类查询 {} 条（经验直接复用），执行 {} 条",
        a.value.unwrap_or(f64::NAN),
        d.kind(QKind::Check).0 + d.kind(QKind::Guard).0,
        d.kind(QKind::Exec).0
    );

    step("③ 月初高峰 · 8 个 Agent 同时验证同一个新关联（网店退货 ⋈ 网店销售）");
    let s = db.meter.snap();
    let mid = Arc::new(mid);
    let mut hs = vec![];
    for i in 0..8 {
        let m = mid.clone();
        hs.push(tokio::spawn(async move {
            let ctx = Ctx::new(&format!("peak{i}"), "peak", "q");
            m.check_join(&ctx, "web_returns", "web_sales", &Channel::Web.correct_on()).await
        }));
    }
    for h in hs {
        h.await??;
    }
    let d = diff(&s, &db.meter.snap());
    eprintln!("  → 8 个请求，数据库只收到 {} 条检查查询（{:.1} s）", d.kind(QKind::Check).0, d.kind(QKind::Check).1 / 1000.0);

    step("④ 周五之前 · ETL 改版：2001-10 起退货改为“申请 / 完成”各一行（表名、列名不变）");
    // 对照：一个“自带记忆、不守护”的 Agent，周一学会了同样的写法
    let local = Middle::new(db.clone(), MiddleConfig { scope: Scope::Agent, guard: GuardMode::Off, ..Default::default() }).await?;
    let merch = Ctx::new("merch-inhouse", "mon", "q0");
    ask_via_paths(&local, &merch, Channel::Store, y2001).await?;
    let n = etl::apply_v2(&admin).await?;
    mid.invalidate_versions();
    eprintln!("  ETL 写入 {n} 行“申请”记录");
    let gh1 = db.query(QKind::Meta, &gold_return_rate_sql(Channel::Store, h1)).await?.f64(0, 0).unwrap_or(0.0);

    step("⑤ 周五 · 商品 Agent（企业自研）问：2002 年上半年门店退货率");
    let merch = Ctx::new("merch-inhouse", "fri", "q5");
    let a0 = ask_via_paths(&local, &merch, Channel::Store, h1).await?;
    eprintln!("  靠本地记忆（不守护）：答 {:.2}% —— SQL 照常执行、没有报错（真实 {gh1:.2}%）", a0.value.unwrap_or(f64::NAN));
    let s = db.meter.snap();
    let a1 = ask_via_paths(&mid, &merch, Channel::Store, h1).await?;
    let d = diff(&s, &db.meter.snap());
    eprintln!(
        "  经中间层（守护）：答 {:.2}%；守卫 {} 条、修复 {} 条、重验 {} 条查询",
        a1.value.unwrap_or(f64::NAN),
        d.kind(QKind::Guard).0,
        d.kind(QKind::Repair).0,
        d.kind(QKind::Check).0
    );
    show_join(&mid, "store_returns", "store_sales");
    for agent in ["fin-gpt", "store-claude"] {
        for n in mid.take_notices(agent) {
            eprintln!("  通知 {agent}：{n}");
        }
    }
    etl::reset(&admin).await?;
    eprintln!("\n中间层统计：{}", serde_json::to_string_pretty(&mid.stats_json())?);
    Ok(())
}
