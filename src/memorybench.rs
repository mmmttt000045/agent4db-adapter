//! 时序共享记忆实验。生产者的轨迹只生成一次，各方法获得同一个时间前缀；
//! 消费者为全新会话，留出答案不进入提炼或发布。协议见 docs/shared-memory-study.md。

use crate::db::{diff, Db, QKind};
use crate::etl;
use crate::knowledge::{Basis, Content, Status};
use crate::llm::{self, AgentRun, Provider, Trace};
use crate::metric::{self, parse_answer, same_value, Trajectory};
use crate::metricbench::{self, Set, Task};
use crate::middle::{tool_specs_with, trajectory_tool_spec, Checkpoint, Ctx, Middle, Scope, TrajMemo};
use crate::scenario;
use anyhow::{ensure, Context, Result};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    #[arg(long, default_value_t = 100_000, value_parser = clap::value_parser!(u32).range(10_000..=20_000_000))]
    rows: u32,
    #[arg(long, default_value = "cline", value_parser = ["openai", "deepseek", "zhipu", "cline", "kunyou", "anthropic", "claude"])]
    agent: String,
    #[arg(long, default_value = "cline", value_parser = ["openai", "deepseek", "zhipu", "cline", "kunyou", "anthropic", "claude"])]
    extractor: String,
    #[arg(long, value_delimiter = ',', default_value = "M1,M2,M3,M5", value_parser = ["M1", "M2", "M3", "M4", "M5"])]
    metrics: Vec<String>,
    #[arg(long, default_value_t = 1, value_parser = clap::value_parser!(u32).range(1..=10))]
    repeat: u32,
    #[arg(long, default_value_t = 20, value_parser = clap::value_parser!(u32).range(1..=100))]
    max_steps: u32,
    #[arg(long, default_value_t = 2, value_parser = clap::value_parser!(u32).range(1..=5))]
    extract_attempts: u32,
    /// 主分析给所有方法同样的完整业务定义；另在最终前缀运行只报指标名的题面。
    #[arg(long)]
    skip_named: bool,
}

struct LearnedPrefix {
    checkpoint: Checkpoint,
    trajectories: Vec<TrajMemo>,
    summary: Value,
}

fn contents(mid: &Middle) -> Value {
    let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
    for e in mid.knowledge() {
        let kind = match e.content {
            Content::Profile(_) => "profile",
            Content::Join { .. } => "join",
            Content::CheckResult { .. } => "condition",
            Content::Result(_) => "answer",
            Content::Metric(_) => "metric",
        };
        *counts.entry(kind).or_default() += 1;
    }
    json!(counts)
}

struct Learning<'a> {
    o: &'a Options,
    agent: &'a Provider,
    extractor: &'a Provider,
    admin: &'a Db,
    mid: &'a Middle,
}

impl Learning<'_> {
    async fn task(&self, t: &Task, wave: usize) -> Result<(Value, Option<TrajMemo>)> {
        let question = metricbench::text(t, true);
        let ctx = Ctx::new(&format!("producer-{}-{wave}", self.o.repeat), "learn", &t.id);
        let mut tools = tool_specs_with(true, true);
        tools.push(llm::final_answer_spec(true));
        tools.push(llm::clarification_spec());
        let gold = self.admin.query(QKind::Meta, &metricbench::gold_sql(t)).await?.cell(0, 0).unwrap_or("NULL").to_string();
        let before = self.mid.db.meter.snap();
        let start = Instant::now();
        let answer =
            llm::run_agent_with(self.agent, self.mid, &ctx, &question, &metricbench::system(true, true), &tools, self.o.max_steps as usize)
                .await;
        let seconds = start.elapsed().as_secs_f64();
        let log = self.mid.take_task_log(&ctx);
        let (run, error) = match answer {
            Ok(r) => (r, None),
            Err(e) => (AgentRun::default(), Some(format!("{e:#}"))),
        };
        let correct =
            run.answer.as_deref().is_some_and(|a| same_value(&parse_answer(a), &parse_answer(&gold), metricbench::decimals(&t.ask)));
        let traj = Trajectory {
            task: t.id.clone(),
            question: question.clone(),
            ask: t.ask,
            basis: Basis::ExplicitQuestion { task: t.id.clone() },
            judged: correct,
            decimals: metricbench::decimals(&t.ask),
            answer: run.answer.clone().unwrap_or_default(),
            used: run.used.clone(),
            derivation: run.derivation.clone(),
            judge: Some(metricbench::gold_sql(t)),
        };
        let mut extraction = Value::Null;
        let mut extracted_draft = Value::Null;
        let mut publication = Value::Null;
        let mut memory = None;
        let mut chain_error = None;
        if correct {
            match log.verify(&traj) {
                Ok(_) => {
                    let used = metricbench::used_refs(&run);
                    memory = Some(TrajMemo {
                        task: t.id.clone(),
                        agent: ctx.agent.clone(),
                        question: question.clone(),
                        sqls: log.calls.iter().filter(|c| used.contains(&c.index)).map(|c| c.sql.clone()).collect(),
                        derivation: run.derivation.clone(),
                        answer: traj.answer.clone(),
                    });
                    let input = self.mid.extract_input(&ctx, &traj, &log);
                    let mut ex = metric::extract(self.extractor, &input, self.o.extract_attempts).await;
                    if let Some(draft) = ex.draft.take() {
                        extracted_draft = json!({"metric": &draft.metric, "example_sql": &draft.example_sql});
                        publication = self.mid.submit_metric(&ctx, draft, &traj, &log).await?;
                    }
                    extraction = serde_json::to_value(ex)?;
                }
                Err(e) => chain_error = Some(e),
            }
        }
        let total_seconds = start.elapsed().as_secs_f64();
        let d = diff(&before, &self.mid.db.meter.snap());
        eprintln!("producer wave {wave} {} correct={correct} publication={}", t.id, publication["event"]);
        Ok((
            json!({"wave": wave, "task": t.id, "metric": t.def.id, "question": question, "gold": gold,
            "correct": correct, "error": error, "chain_error": chain_error, "run": run,
            "agent_seconds": seconds, "total_seconds": total_seconds, "extraction": extraction, "extracted_draft": extracted_draft,
            "publication": publication, "db": {"queries": d.queries, "ms": d.db_ms}, "memory": contents(self.mid)}),
            memory,
        ))
    }
}

struct Consumer<'a> {
    o: &'a Options,
    agent: &'a Provider,
    mid: &'a Middle,
    policy: &'a str,
    sessions: &'a Trace,
}

impl Consumer<'_> {
    async fn task(&self, t: &Task, wave: usize, phase: &str, defined: bool, gold: &str) -> Result<Value> {
        let question = metricbench::text(t, defined);
        let ctx = Ctx::new(&format!("consumer-{}-{}-{wave}-{phase}-{}", self.o.repeat, self.policy, t.id), "fresh", &t.id);
        let trajectory = self.policy == "trajectory";
        let mut tools = tool_specs_with(true, !trajectory);
        let mut system = metricbench::system(true, !trajectory);
        if trajectory {
            tools.push(trajectory_tool_spec());
            system
                .push_str("\nfind_trajectory 返回已判定成功的历史任务、参与答案的 SQL 与算式，可作为参考。复用前先在当前数据上核对前提。");
        }
        tools.push(llm::final_answer_spec(true));
        tools.push(llm::clarification_spec());
        let before = self.mid.db.meter.snap();
        let start = Instant::now();
        let answer = llm::run_agent_with(self.agent, self.mid, &ctx, &question, &system, &tools, self.o.max_steps as usize).await;
        let seconds = start.elapsed().as_secs_f64();
        let log = self.mid.take_task_log(&ctx);
        let d = diff(&before, &self.mid.db.meter.snap());
        let (run, error) = match answer {
            Ok(r) => (r, None),
            Err(e) => (AgentRun::default(), Some(format!("{e:#}"))),
        };
        let correct =
            run.answer.as_deref().is_some_and(|a| same_value(&parse_answer(a), &parse_answer(gold), metricbench::decimals(&t.ask)));
        let outcome = if error.is_some() {
            "error"
        } else if run.clarification.is_some() {
            "clarify"
        } else if correct {
            "correct"
        } else {
            "wrong"
        };
        let record = json!({"policy": self.policy, "repeat": self.o.repeat, "wave": wave, "phase": phase,
            "agent": ctx.agent, "session": ctx.session, "task": t.id, "metric": t.def.id,
            "defined": defined, "question": question, "outcome": outcome, "error": error, "gold": gold, "answer": run.answer,
            "seconds": seconds, "run": run, "sql_calls": log.calls.len(), "finds": log.finds,
            "found": log.found, "rejections": log.rejections,
            "db": {"queries": d.queries, "ms": d.db_ms, "by_kind": d.by_kind}});
        self.sessions.write(&record);
        eprintln!("{} wave {wave} {phase} {} {outcome} {:.2}s", self.policy, t.id, seconds);
        Ok(record)
    }
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    ensure!(!o.metrics.is_empty(), "metrics 不能为空");
    let agent = Provider::from_env(&o.agent)?;
    let extractor = Provider::from_env(&o.extractor)?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_memory_{}_{stamp}", std::process::id());
    let directory = format!("{out}/memory-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await.context("创建隔离实验库失败")?;
    let result: Result<Value> = async {
        let admin = Db::connect(isolated.as_str(), 2, false)?;
        admin.query(QKind::Meta, &metricbench::fixture(o.rows)).await?;
        etl::setup(&admin).await?;
        scenario::setup(&admin).await?;
        let tasks = metricbench::tasks(&o.metrics);
        let gold = metricbench::gold_map(&admin, &tasks).await?;
        let db = Arc::new(Db::connect_timeout(isolated.as_str(), pool, true, 60)?);
        let (mut source_cfg, _, _) = metricbench::config("metric-global-exref");
        source_cfg.feedback = false;
        source_cfg.result_cache = false;
        let mut source = Middle::new(db.clone(), source_cfg).await?;
        source.trace = Some(Trace::create(&format!("{directory}/producer-trace.jsonl"))?);
        let learning = Learning { o: &o, agent: &agent, extractor: &extractor, admin: &admin, mid: &source };
        let mut order = o.metrics.clone();
        let rotate = (o.repeat as usize - 1) % order.len();
        order.rotate_left(rotate);
        let mut prefixes = Vec::new();
        let mut training = Vec::new();
        let mut trajectories = Vec::new();
        for (wave, id) in order.iter().enumerate() {
            for t in tasks.iter().filter(|t| t.def.id == id && t.set == Set::Learn) {
                let (rec, memo) = learning.task(t, wave + 1).await?;
                if let Some(memo) = memo { trajectories.push(memo); }
                let promoted = rec["publication"]["event"] == "promoted";
                training.push(rec);
                std::fs::write(format!("{directory}/training.json"), serde_json::to_string_pretty(&training)?)?;
                if promoted { break; }
            }
            let summary = json!({"wave": wave + 1, "introduced_metric": id, "memory": contents(&source),
                "valid_metrics": source.metric_entries().iter().filter(|(_, e, _)| matches!(e.status, Status::Valid)).count(),
                "training_tasks": training.len()});
            let checkpoint = source.checkpoint();
            std::fs::write(format!("{directory}/prefix-{}.json", wave + 1), serde_json::to_string_pretty(
                &json!({"summary": &summary, "checkpoint": &checkpoint, "trajectories": &trajectories}))?)?;
            prefixes.push(LearnedPrefix { checkpoint, trajectories: trajectories.clone(), summary });
        }
        let policies = ["isolated", "frozen", "accumulating", "trajectory"];
        let mut records = Vec::new();
        let sessions = Trace::create(&format!("{directory}/sessions.jsonl"))?;
        for wave in 1..=prefixes.len() {
            let introduced = &order[..wave];
            let mut methods = policies.to_vec();
            let len = methods.len();
            methods.rotate_left((o.repeat as usize + wave - 2) % len);
            for policy in methods {
                let (mut cfg, _, _) = metricbench::config("metric-global-exref");
                cfg.name = policy.into();
                cfg.feedback = false;
                cfg.result_cache = false;
                cfg.traj_memory = policy == "trajectory";
                if policy == "isolated" { cfg.scope = Scope::Session; cfg.metric_scope = Scope::Session; }
                let mut mid = Middle::new(db.clone(), cfg).await?;
                mid.trace = Some(Trace::create(&format!("{directory}/trace-w{wave}-{policy}.jsonl"))?);
                let prefix = if policy == "frozen" { &prefixes[0] } else { &prefixes[wave - 1] };
                if policy == "trajectory" {
                    for memo in &prefix.trajectories { mid.remember_trajectory(memo.clone()); }
                }
                let consumer = Consumer { o: &o, agent: &agent, mid: &mid, policy, sessions: &sessions };
                let mut probes: Vec<(&Task, &str, bool)> = tasks.iter()
                    .filter(|t| introduced.iter().any(|id| id == t.def.id) && t.set == Set::Param)
                    .map(|t| (t, "prefix-param", true)).collect();
                if wave == prefixes.len() {
                    probes.extend(tasks.iter().filter(|t| t.set == Set::Type).map(|t| (t, "final-type", true)));
                    if !o.skip_named {
                        probes.extend(tasks.iter().filter(|t| t.set == Set::Param).map(|t| (t, "final-named", false)));
                    }
                }
                for (t, phase, defined) in probes {
                    // 数据从学习开始未改变；恢复仅隔离消费者的写回，使每个方法得到完全相同的生产者前缀。
                    mid.restore(&prefix.checkpoint).await?;
                    let rec = consumer.task(t, wave, phase, defined, gold.get(&t.id).map(String::as_str).unwrap_or("NULL")).await?;
                    records.push(rec);
                    std::fs::write(format!("{directory}/partial.json"), serde_json::to_string_pretty(&records)?)?;
                }
            }
        }
        Ok(json!({"options": o, "agent": agent.config(), "extractor": extractor.config(),
            "order": order, "prefixes": prefixes.iter().map(|p| &p.summary).collect::<Vec<_>>(),
            "training": training, "records": records,
            "methodology": "Same real producer trajectories and exact knowledge prefix across policies; consumer task/agent/session fresh; primary questions fully defined; held-out results never published; consumer writeback reset between probes; no answer cache or strategy adaptation. Frozen gets only prefix one. Trajectory gets current structural knowledge and raw judged trajectories through its own retrieval tool. Isolated cannot read producer-scoped entries."}))
    }.await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    match result {
        Ok(mut report) => {
            report["database_cleaned_up"] = json!(cleanup.is_ok());
            std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
            cleanup.context("实验库清理失败")?;
            println!("共享记忆实验：{directory}");
            Ok(())
        }
        Err(e) => {
            std::fs::write(
                format!("{directory}/error.json"),
                serde_json::to_string_pretty(&json!({"error": format!("{e:#}"), "database_cleaned_up": cleanup.is_ok()}))?,
            )?;
            Err(e)
        }
    }
}
