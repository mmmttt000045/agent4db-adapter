//! Paired end-to-end sessions over fixed learned libraries. No learning or extraction during measurement.

use crate::db::{diff, Db, QKind};
use crate::etl;
use crate::llm::{self, AgentRun, Provider, Trace};
use crate::metric::{parse_answer, same_value};
use crate::metricbench::{self, Set, Task};
use crate::middle::{tool_specs_with, Ctx, Maint, Middle, MiddleConfig, ToolSpec};
use crate::replaybench::{self, Library};
use crate::scenario::{self, Change};
use crate::timing;
use anyhow::{ensure, Context, Result};
use futures::StreamExt;
use rand::{rngs::StdRng, seq::SliceRandom, SeedableRng};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    /// Explicit cell JSON files from completed, non-replaced scenario runs. Each library is paired across all policies.
    #[arg(long, value_delimiter = ',', required = true)]
    libs: Vec<String>,
    #[arg(long, default_value_t = 1_000_000, value_parser = clap::value_parser!(u32).range(10_000..=20_000_000))]
    rows: u32,
    #[arg(long, default_value = "cline", value_parser = ["openai", "deepseek", "zhipu", "cline", "kunyou", "anthropic", "claude"])]
    agent: String,
    #[arg(long, value_delimiter = ',', default_value = "no-share,definition,definition-cache,condition",
          value_parser = ["no-share", "definition", "definition-cache", "condition"])]
    policies: Vec<String>,
    #[arg(long, value_delimiter = ',', default_value = "cold,warm,after-append,after-status,burst-status",
          value_parser = ["cold", "warm", "after-append", "after-status", "burst-status"])]
    phases: Vec<String>,
    /// One parameter-holdout question (P1) per metric; no measured question is a learning question.
    #[arg(long, value_delimiter = ',', default_value = "M1,M2,M3", value_parser = ["M1", "M2", "M3", "M4", "M5"])]
    metrics: Vec<String>,
    /// Model sessions admitted concurrently in the burst; requests beyond this limit wait in the measured queue.
    #[arg(long, default_value_t = 3, value_parser = clap::value_parser!(u32).range(1..=6))]
    concurrency: u32,
    #[arg(long, default_value_t = 2, value_parser = clap::value_parser!(u32).range(1..=10))]
    burst_copies: u32,
    /// example uses the saved agent's own SQL as the repair reference; judge uses the benchmark oracle.
    #[arg(long, default_value = "example", value_parser = ["example", "judge"])]
    oracle: String,
    #[arg(long, default_value_t = 20, value_parser = clap::value_parser!(u32).range(1..=100))]
    max_steps: u32,
    #[arg(long, default_value_t = 120, value_parser = clap::value_parser!(u64).range(10..=3600))]
    sql_timeout_secs: u64,
    #[arg(long, default_value_t = 20261003)]
    seed: u64,
    /// Counterbalance policy order across independent library processes.
    #[arg(long, default_value_t = 0)]
    order_offset: usize,
}

fn config(policy: &str, seed: u64) -> MiddleConfig {
    let base = MiddleConfig { name: policy.into(), record: true, result_cache: false, audit_seed: Some(seed), ..Default::default() };
    match policy {
        "condition" => MiddleConfig { metric_maint: Maint::Condition, cond_reuse: true, ..base },
        "definition-cache" => MiddleConfig { metric_maint: Maint::Definition, sql_cache: true, ..base },
        "definition" => MiddleConfig { metric_maint: Maint::Definition, ..base },
        _ => MiddleConfig { metric_maint: Maint::Off, ..base },
    }
}

struct Env<'a> {
    o: &'a Options,
    mid: &'a Middle,
    agent: &'a Provider,
    policy: &'a str,
    library: &'a str,
    system: String,
    tools: Vec<ToolSpec>,
    sessions: &'a Trace,
}

struct Phase<'a> {
    name: &'a str,
    gold: HashMap<String, String>,
    start: Instant,
    unix_ms: f64,
    burst: bool,
}

async fn session(env: &Env<'_>, phase: &Phase<'_>, idx: usize, copy: u32, task: &Task) -> Value {
    let id = format!("{}-{}-{}-s{idx}", env.library, env.policy, phase.name);
    let ctx = Ctx::new(&id, &id, &task.id);
    let question = metricbench::text(task, false);
    let started_ms = llm::unix_ms();
    let queue_ms = if phase.burst { phase.start.elapsed().as_secs_f64() * 1000.0 } else { 0.0 };
    let (result, profile) =
        timing::capture(llm::run_agent_with(env.agent, env.mid, &ctx, &question, &env.system, &env.tools, env.o.max_steps as usize)).await;
    let (run, error) = match result {
        Ok(run) => (run, None),
        Err(e) => (AgentRun::default(), Some(format!("{e:#}"))),
    };
    let log = env.mid.take_task_log(&ctx);
    let gold = &phase.gold[&task.id];
    let correct =
        run.answer.as_deref().is_some_and(|a| same_value(&parse_answer(a), &parse_answer(gold), metricbench::decimals(&task.ask)));
    let outcome = if error.is_some() {
        "error"
    } else if run.clarification.is_some() {
        "clarify"
    } else if correct {
        "correct"
    } else {
        "wrong"
    };
    let record = json!({
        "library": env.library, "policy": env.policy, "phase": phase.name, "index": idx, "copy": copy,
        "agent": ctx.agent, "session": ctx.session, "task": task.id, "metric": task.def.id, "question": question,
        "gold": gold, "outcome": outcome, "error": error, "run": run,
        "offered_ms": if phase.burst { phase.unix_ms } else { started_ms }, "started_ms": started_ms,
        "queue_ms": queue_ms, "completion_ms": queue_ms + profile.wall_ms, "profile": profile,
        "found": log.found, "rejections": log.rejections, "sql_calls": log.calls,
    });
    env.sessions.write(&record);
    eprintln!(
        "  {} {} {:<16} {:<6} c{copy} {outcome:<7} {:.2}s",
        env.library,
        env.policy,
        phase.name,
        task.id,
        record["completion_ms"].as_f64().unwrap_or_default() / 1000.0
    );
    record
}

async fn phases(env: &Env<'_>, admin: &Db, tasks: &[Task], v1: &std::collections::BTreeMap<String, String>) -> Result<Vec<Value>> {
    let cp = env.mid.checkpoint();
    let mut previous = None;
    let mut reports = vec![];
    for (pi, name) in env.o.phases.iter().enumerate() {
        if name != "warm" {
            if let Some(change) = previous.take() {
                Change::reset(change, admin).await?;
            }
            scenario::ensure_v1(admin, v1, "会话阶段恢复").await?;
            env.mid.restore(&cp).await?;
        }
        let change = match name.as_str() {
            "after-append" => Some(Change::parse("append")?),
            "after-status" | "burst-status" => Some(Change::parse("status")?),
            _ => None,
        };
        if let Some(c) = change {
            c.apply_truth(admin).await?;
            c.apply_hidden(admin).await?;
            previous = Some(c);
        }
        // Gold and ETL are outside all measured sessions. All writers finish before the phase begins.
        let gold = metricbench::gold_map(admin, tasks).await?;
        env.mid.invalidate_versions();
        let _ = env.mid.take_metric_events();
        let burst = name == "burst-status";
        let copies = if burst { env.o.burst_copies } else { 1 };
        let mut plan: Vec<_> = (1..=copies).flat_map(|copy| tasks.iter().map(move |task| (copy, task))).collect();
        plan.shuffle(&mut StdRng::seed_from_u64(env.o.seed + pi as u64));
        let before = env.mid.db.meter.snap();
        let phase = Phase { name, gold, start: Instant::now(), unix_ms: llm::unix_ms(), burst };
        let records: Vec<Value> = futures::stream::iter(plan.iter().enumerate())
            .map(|(idx, (copy, task))| session(env, &phase, idx, *copy, task))
            .buffer_unordered(if burst { env.o.concurrency as usize } else { 1 })
            .collect()
            .await;
        let wall_ms = phase.start.elapsed().as_secs_f64() * 1000.0;
        let db = diff(&before, &env.mid.db.meter.snap());
        let attributed: u64 = records.iter().map(|r| r["profile"]["db"]["queries"].as_u64().unwrap_or_default()).sum();
        let attributed_ms: f64 = records.iter().map(|r| r["profile"]["db"]["db_ms"].as_f64().unwrap_or_default()).sum();
        ensure!(attributed == db.queries && (attributed_ms - db.db_ms).abs() < 0.001, "请求局部计量与阶段总计不一致");
        reports.push(json!({
            "library": env.library, "policy": env.policy, "phase": name, "sessions": records.len(),
            "wall_ms": wall_ms, "db": db, "attributed_queries": attributed, "attributed_db_ms": attributed_ms,
            "events": env.mid.take_metric_events(), "stats": env.mid.stats_json(),
        }));
    }
    if let Some(c) = previous {
        c.reset(admin).await?;
    }
    scenario::ensure_v1(admin, v1, "会话单元结束").await?;
    Ok(reports)
}

struct Runner<'a> {
    isolated: &'a str,
    pool: usize,
    directory: &'a str,
    admin: &'a Db,
    agent: &'a Provider,
    o: &'a Options,
    tasks: &'a [Task],
    sessions: &'a Trace,
    v1: &'a std::collections::BTreeMap<String, String>,
}

async fn cell(r: &Runner<'_>, library: &Library, policy: &str) -> Result<Value> {
    let (isolated, pool, directory, admin, agent) = (r.isolated, r.pool, r.directory, r.admin, r.agent);
    let (o, tasks, sessions, v1) = (r.o, r.tasks, r.sessions, r.v1);
    let db = Arc::new(Db::connect_timeout(isolated, pool, true, o.sql_timeout_secs)?);
    let (startup_result, startup) = timing::capture(async {
        let mid = Middle::new(db, config(policy, o.seed)).await?;
        let ctx = Ctx::new("import", "fixed-library", "seed");
        let mut seeds = vec![];
        if policy != "no-share" {
            for entry in &library.entries {
                let reference = if o.oracle == "example" { &entry.example } else { &entry.judge };
                let seed = mid.seed_metric(&ctx, entry.metric.clone(), entry.ask, entry.decimals, reference).await?;
                ensure!(seed["promoted"] == true, "固定库条目 {} 准入失败：{seed}", entry.name);
                seeds.push(seed);
            }
        }
        Ok::<_, anyhow::Error>((mid, seeds))
    })
    .await;
    let (mut mid, seeds) = startup_result?;
    mid.trace = Some(Trace::create(&format!("{directory}/trace-{}-{policy}.jsonl", library.id.replace('/', "_")))?);
    let initial = mid.metric_report();
    let _ = mid.take_metric_events();
    let mut tools = tool_specs_with(true, policy != "no-share");
    tools.push(llm::final_answer_spec(true));
    tools.push(llm::clarification_spec());
    let env =
        Env { o, mid: &mid, agent, policy, library: &library.id, system: metricbench::system(true, policy != "no-share"), tools, sessions };
    let phase_reports = phases(&env, admin, tasks, v1).await?;
    Ok(json!({"library": library.id, "policy": policy, "startup": startup, "seeds": seeds,
              "initial_library": initial, "phases": phase_reports}))
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    ensure!(!o.libs.is_empty() && !o.policies.is_empty() && !o.phases.is_empty(), "libs、policies 与 phases 不能为空");
    ensure!(o.phases.iter().enumerate().all(|(i, p)| p != "warm" || i > 0 && o.phases[i - 1] == "cold"), "warm 必须紧跟 cold");
    let mut libraries = o.libs.iter().map(|p| replaybench::load(p)).collect::<Result<Vec<_>>>()?;
    // Preserve all variants of the measured metrics; unrelated definitions do not participate in this workload.
    for library in &mut libraries {
        library.entries.retain(|entry| o.metrics.contains(&entry.def));
    }
    let tasks: Vec<Task> = metricbench::tasks(&o.metrics).into_iter().filter(|t| t.set == Set::Param).collect();
    ensure!(!tasks.is_empty(), "没有计分题");
    for library in &libraries {
        for t in &tasks {
            ensure!(library.entries.iter().any(|e| e.def == t.def.id), "库 {} 没有 {} 的有效定义", library.id, t.def.id);
        }
    }
    let agent = Provider::from_env(&o.agent)?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_session_{}_{stamp}", std::process::id());
    let directory = format!("{out}/session-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let manifest = json!({
        "options": o, "pool": pool, "agent": agent.label(), "agent_config": agent.config(),
        "libraries": libraries.iter().map(|l| json!({"id": l.id, "source": l.source,
            "entries": l.entries.iter().map(|e| json!({"name": e.name, "metric": e.metric, "def": e.def})).collect::<Vec<_>>(),
            "skipped": l.skipped})).collect::<Vec<_>>(),
        "tasks": tasks.iter().map(|t| json!({"task": t.id, "question": metricbench::text(t, false), "ask": t.ask})).collect::<Vec<_>>(),
        "methodology": "同一已学库与参数留出题配对；不重新学习；新 Agent 会话；关闭答案结果缓存；固定候选审计种子；阶段间写入完成后才发请求；\
            cold 是固定库加载/准入后的首次 Agent 使用，库启动成本单列，非 OS/数据库冷缓存；warm 重用同一个中间层；\
            append/status 各从内容核对过的 v1 恢复，首次使用触发维护；burst-status 同时提交全部请求，模型并发限制之外的排队计入完成时间；\
            request-local SQL 只归属执行者，合并等待由 shared_wait 记录；嵌套 span 不直接相加；失败的耗时和已完成 token 仍保留",
    });
    std::fs::write(format!("{directory}/manifest.json"), serde_json::to_string_pretty(&manifest)?)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await.context("创建隔离实验库失败（需要 CREATEDB）")?;
    let result: Result<Vec<Value>> = async {
        let admin = Db::connect(isolated.as_str(), 2, false)?;
        eprintln!("生成 {} 行合成零售数据；输出 {directory}", o.rows);
        admin.query(QKind::Meta, &metricbench::fixture(o.rows)).await?;
        etl::setup(&admin).await?;
        scenario::setup(&admin).await?;
        let v1 = scenario::fingerprint(&admin).await?;
        let sessions = Trace::create(&format!("{directory}/sessions.jsonl"))?;
        let runner = Runner {
            isolated: isolated.as_str(),
            pool,
            directory: &directory,
            admin: &admin,
            agent: &agent,
            o: &o,
            tasks: &tasks,
            sessions: &sessions,
            v1: &v1,
        };
        let mut cells = vec![];
        for (li, library) in libraries.iter().enumerate() {
            for k in 0..o.policies.len() {
                let policy = &o.policies[(k + li + o.order_offset) % o.policies.len()];
                cells.push(cell(&runner, library, policy).await?);
                std::fs::write(format!("{directory}/partial.json"), serde_json::to_string_pretty(&cells)?)?;
            }
        }
        Ok(cells)
    }
    .await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    match result {
        Ok(cells) => {
            std::fs::write(
                format!("{directory}/report.json"),
                serde_json::to_string_pretty(&json!({
                    "manifest": manifest, "cells": cells, "database_cleaned_up": cleanup.is_ok(),
                }))?,
            )?;
            println!("固定库会话实验：{directory}");
            cleanup.context("实验库清理失败")?;
            Ok(())
        }
        Err(error) => {
            std::fs::write(
                format!("{directory}/error.json"),
                serde_json::to_string_pretty(&json!({
                    "error": format!("{error:#}"), "database_cleaned_up": cleanup.is_ok(),
                }))?,
            )?;
            Err(error)
        }
    }
}
