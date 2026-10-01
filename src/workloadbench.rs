//! 工作负载刻画：互不相识的 Agent 会话各自从零开始回答同一批分析题（直连工具，会话之间不共享任何状态），
//! 多个会话同时访问同一数据库。逐次记录工具调用（trace.jsonl）与每个会话的结果（sessions.jsonl），
//! 并给出应用把同样的题写成参数化 SQL 时的查询（app.json），供 tools/workload-stats.py 对照统计。

use crate::db::{Db, QKind};
use crate::etl;
use crate::llm::{self, unix_ms, AgentRun, Provider, Trace};
use crate::metric::{parse_answer, same_value};
use crate::metricbench::{self, Task};
use crate::middle::{tool_specs_with, Ctx, Middle, ToolSpec};
use crate::scenario;
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
    /// 门店销售行数（目录渠道为其一半）
    #[arg(long, default_value_t = 1_000_000, value_parser = clap::value_parser!(u32).range(10_000..=20_000_000))]
    rows: u32,
    /// 查询 Agent 的模型服务（配置写在 .env）
    #[arg(long, default_value = "cline", value_parser = ["openai", "deepseek", "zhipu", "cline", "kunyou", "anthropic", "claude"])]
    agent: String,
    #[arg(long, value_delimiter = ',', default_value = "M1,M2,M3,M4,M5", value_parser = ["M1", "M2", "M3", "M4", "M5"])]
    metrics: Vec<String>,
    /// named 只报指标名，defined 在题面写出口径
    #[arg(long, value_delimiter = ',', default_value = "named,defined", value_parser = ["defined", "named"])]
    phrasings: Vec<String>,
    /// 每道题、每种题面各有几个独立会话
    #[arg(long, default_value_t = 2, value_parser = clap::value_parser!(u32).range(1..=10))]
    repeats: u32,
    /// 同时进行的会话数（共享同一数据库）
    #[arg(long, default_value_t = 3, value_parser = clap::value_parser!(u32).range(1..=32))]
    concurrency: u32,
    #[arg(long, default_value_t = 20, value_parser = clap::value_parser!(u32).range(1..=100))]
    max_steps: u32,
    #[arg(long, default_value_t = 60, value_parser = clap::value_parser!(u64).range(10..=3600))]
    sql_timeout_secs: u64,
    /// 会话顺序的随机种子
    #[arg(long, default_value_t = 1)]
    seed: u64,
}

struct Env<'a> {
    o: &'a Options,
    mid: &'a Middle,
    agent: &'a Provider,
    system: String,
    tools: Vec<ToolSpec>,
    gold: HashMap<String, String>,
    sessions: Trace,
}

/// 一个全新会话：Agent 名即会话编号，中间层按会话隔离，拿不到其他会话的任何探查结果。
async fn session(env: &Env<'_>, idx: usize, repeat: u32, phrasing: &str, t: &Task) -> Value {
    let question = metricbench::text(t, phrasing == "defined");
    let ctx = Ctx::new(&format!("s{idx:03}"), &format!("{phrasing}-r{repeat}"), &t.id);
    let t0 = unix_ms();
    let r = llm::run_agent_with(env.agent, env.mid, &ctx, &question, &env.system, &env.tools, env.o.max_steps as usize).await;
    let t1 = unix_ms();
    let log = env.mid.take_task_log(&ctx);
    let (run, error) = match r {
        Ok(run) => (run, None),
        Err(e) => (AgentRun::default(), Some(format!("{e:#}"))),
    };
    let gold = env.gold.get(&t.id).cloned().unwrap_or_default();
    let correct = run.answer.as_deref().is_some_and(|a| same_value(&parse_answer(a), &parse_answer(&gold), metricbench::decimals(&t.ask)));
    let outcome = match (&error, &run.clarification) {
        (Some(_), _) => "error",
        (None, Some(_)) => "clarify",
        _ if correct => "correct",
        _ => "wrong",
    };
    let used = metricbench::used_refs(&run);
    let final_sql: Vec<&str> = log.calls.iter().filter(|c| used.contains(&c.index)).map(|c| c.sql.as_str()).collect();
    eprintln!(
        "  {:<5} {:<12} {:<6} {:<8} 轮 {:>2} 工具 {:>2} 出错 {} | 答 {} / 标准 {}",
        ctx.agent,
        ctx.session,
        t.id,
        outcome,
        run.steps,
        run.tool_calls,
        run.tool_errors,
        run.answer.clone().unwrap_or_default().chars().take(16).collect::<String>(),
        gold.chars().take(16).collect::<String>()
    );
    let rec = json!({
        "agent": ctx.agent, "session": ctx.session, "task": t.id, "metric": t.def.id, "set": t.set, "ask": t.ask,
        "phrasing": phrasing, "repeat": repeat, "question": question, "gold": gold, "answer": run.answer, "outcome": outcome,
        "error": error, "t0_ms": t0, "t1_ms": t1, "run": run, "final_sql": final_sql, "sql_calls": log.calls.len(),
    });
    env.sessions.write(&rec);
    rec
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    ensure!(!o.phrasings.is_empty() && !o.metrics.is_empty(), "metrics 与 phrasings 不能为空");
    let agent = Provider::from_env(&o.agent)?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_workload_{}_{stamp}", std::process::id());
    let directory = format!("{out}/workload-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await.context("创建隔离实验库失败（需要 CREATEDB）")?;
    let result: Result<Value> = async {
        let admin = Db::connect(isolated.as_str(), 2, false)?;
        eprintln!("生成合成零售数据：门店销售 {} 行，目录销售 {} 行", o.rows, o.rows / 2);
        admin.query(QKind::Meta, &metricbench::fixture(o.rows)).await?;
        etl::setup(&admin).await?;
        scenario::setup(&admin).await?;
        let tasks = metricbench::tasks(&o.metrics);
        // 应用的做法：每类问题一条参数化 SQL，与判题的参考 SQL 相同
        let app: Vec<Value> = tasks
            .iter()
            .map(|t| json!({"task": t.id, "metric": t.def.id, "set": t.set, "ask": t.ask, "sql": metricbench::gold_sql(t)}))
            .collect();
        std::fs::write(format!("{directory}/app.json"), serde_json::to_string_pretty(&app)?)?;
        let db = Arc::new(Db::connect_timeout(isolated.as_str(), pool, true, o.sql_timeout_secs)?);
        let (cfg, middle_tools, metric_tools) = metricbench::config("direct");
        let mut mid = Middle::new(db, cfg).await?;
        mid.trace = Some(Trace::create(&format!("{directory}/trace.jsonl"))?);
        let mut tools = tool_specs_with(middle_tools, metric_tools);
        tools.push(llm::final_answer_spec(true));
        tools.push(llm::clarification_spec());
        let env = Env {
            o: &o,
            mid: &mid,
            agent: &agent,
            system: metricbench::system(middle_tools, metric_tools),
            tools,
            gold: metricbench::gold_map(&admin, &tasks).await?,
            sessions: Trace::create(&format!("{directory}/sessions.jsonl"))?,
        };
        let mut plan: Vec<(u32, &str, &Task)> = vec![];
        for r in 1..=o.repeats {
            for p in &o.phrasings {
                plan.extend(tasks.iter().map(|t| (r, p.as_str(), t)));
            }
        }
        // 打乱顺序：同时进行的会话问的是不同指标、不同题型
        plan.shuffle(&mut StdRng::seed_from_u64(o.seed));
        eprintln!("{} 个会话，并发 {}，模型 {}", plan.len(), o.concurrency, agent.label());
        let t0 = Instant::now();
        let recs: Vec<Value> = futures::stream::iter(plan.iter().enumerate())
            .map(|(i, (r, p, t))| session(&env, i, *r, p, t))
            .buffer_unordered(o.concurrency as usize)
            .collect()
            .await;
        let count = |k: &str| recs.iter().filter(|r| r["outcome"] == k).count();
        Ok(json!({
            "options": o, "pool": pool, "agent": agent.label(), "agent_config": agent.config(),
            "seconds": t0.elapsed().as_secs_f64(), "sessions": recs.len(),
            "outcomes": {"correct": count("correct"), "wrong": count("wrong"), "clarify": count("clarify"), "error": count("error")},
            "methodology": "直连工具（list_tables / describe_table / run_sql），中间层不复用、不合并、不审查；每个会话独立的 Agent 名与会话名；\
                            会话顺序按种子打乱后以固定并发执行；trace.jsonl 为逐次工具调用，sessions.jsonl 为逐会话结果，app.json 为应用的参数化 SQL",
        }))
    }
    .await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    match result {
        Ok(mut report) => {
            report["database_cleaned_up"] = json!(cleanup.is_ok());
            std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
            println!("工作负载轨迹：{directory}");
            cleanup.context("实验库清理失败")?;
            Ok(())
        }
        Err(error) => {
            std::fs::write(
                format!("{directory}/error.json"),
                serde_json::to_string_pretty(&json!({"error": format!("{error:#}"), "database_cleaned_up": cleanup.is_ok()}))?,
            )?;
            Err(error)
        }
    }
}
