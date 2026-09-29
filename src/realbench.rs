//! Real NYC TLC records, scripted tasks. No generated or replicated business rows.
use crate::db::{Db, QKind};
use crate::feedback::DEFAULT_ORDER;
use crate::llm::Provider;
use crate::middle::{Ctx, Middle, MiddleConfig, Scope};
use crate::optimizer::Optimizer;
use anyhow::{ensure, Result};
use futures::{stream, StreamExt};
use rand::{rngs::StdRng, seq::SliceRandom, SeedableRng};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::Instant;

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    #[arg(long, default_value = "D", value_parser = ["A", "B", "C", "D", "M", "L"])]
    mode: String,
    #[arg(long, default_value_t = 24, value_parser = clap::value_parser!(u32).range(1..=128))]
    agents: u32,
    #[arg(long, default_value_t = 16, value_parser = clap::value_parser!(u32).range(1..=64))]
    variants: u32,
    #[arg(long, default_value_t = 42)]
    seed: u64,
    #[arg(long)]
    no_result_cache: bool,
    /// Read precomputed direct-SQL oracle results; generated with --oracle-only.
    #[arg(long)]
    oracle: String,
    #[arg(long)]
    oracle_only: bool,
    /// Real PostgreSQL check measurements with chronological holdout; separate from end-to-end tasks.
    #[arg(long)]
    check_study: bool,
}

#[derive(Clone, Serialize, Deserialize)]
struct Task {
    family: usize,
    month: u32,
    sql: String,
    expected: Value,
}

fn queries(variants: u32) -> Vec<Task> {
    let mut tasks = vec![];
    for month in [1, 2] {
        for v in 0..variants {
            // Include busy areas as well as coverage zones; do not let empty results dominate.
            let busy = [161, 237, 236, 230, 132, 138, 142, 234, 162, 170, 48, 79, 68, 163, 164, 186];
            let zone = busy[v as usize % busy.len()];
            let day = 1 + (v * 7) % 24;
            let predicate = format!(
                "t_pu={zone} and t_pickup >= timestamp '2024-{month:02}-{day:02}' and t_pickup < timestamp '2024-{month:02}-{:02}'",
                day + 2
            );
            let base = format!("select * from trips where {predicate}");
            let sqls = vec![
                format!("select count(*) as n,sum(t_total) as total from trips where {predicate}"),
                format!("select t_payment,count(*) as n,sum(t_tip) as tips from trips where {predicate} group by t_payment order by t_payment"),
                format!("select z_borough,count(*) as n,sum(t_total) as total from trips join zones on t_pu=z_id where {predicate} group by z_borough order by z_borough"),
                format!("select t_id,t_total from trips where {predicate} order by t_total desc nulls last,t_id limit 10"),
                format!("with q as ({base}) select t_vendor,count(*) as n,avg(t_distance)::numeric(18,4) as distance from q group by t_vendor order by t_vendor"),
                format!("select t_id,t_total,rank() over(order by t_total desc nulls last) as r from ({base}) q order by t_total desc nulls last,t_id limit 10"),
                format!("select count(*) filter(where t_total<0) as negative,count(*) filter(where t_passengers is null) as missing from trips where {predicate}"),
                format!("select t_do,count(*) as n from trips where {predicate} group by t_do having count(*)>1 order by n desc,t_do limit 10"),
                format!("select count(distinct t_do) as destinations,min(t_pickup) as first_pickup,max(t_dropoff) as last_dropoff from trips where {predicate}"),
                format!("select a_day,sum(a_trips) as n,sum(a_total) as total from zone_day join zones on a_zone=z_id where a_zone={zone} and a_day >= date '2024-{month:02}-01' and a_day < date '2024-{month:02}-28' group by a_day order by a_day"),
            ];
            for (family, sql) in sqls.into_iter().enumerate() {
                tasks.push(Task { family, month, sql, expected: Value::Null });
            }
        }
    }
    tasks
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    std::fs::create_dir_all(out)?;
    if o.check_study {
        return check_study(url, out, &o.mode).await;
    }
    if o.oracle_only {
        let db = Db::connect(url, pool, true)?;
        let mut tasks = queries(o.variants);
        for t in &mut tasks {
            t.expected = db.query(QKind::Exec, &t.sql).await?.to_json(1000);
        }
        std::fs::write(&o.oracle, serde_json::to_string_pretty(&tasks)?)?;
        println!("Oracle: {} actual PostgreSQL query results", tasks.len());
        return Ok(());
    }
    let tasks: Vec<Task> = serde_json::from_str(&std::fs::read_to_string(&o.oracle)?)?;
    let generated = queries(o.variants);
    ensure!(tasks.len() == generated.len() && tasks.iter().zip(&generated).all(|(a, b)| a.sql == b.sql), "Oracle workload mismatch");
    let tasks = Arc::new(tasks);
    let db = Arc::new(Db::connect(url, pool, true)?);
    let start = Instant::now();
    let shared = o.mode != "A" && o.mode != "C";
    let config = MiddleConfig {
        name: format!("real-{}", o.mode),
        scope: if shared { Scope::Global } else { Scope::Agent },
        singleflight: false,
        feedback: true,
        trace_checks: true,
        audit_seed: Some(o.seed),
        max_rows: 1000,
        result_cache: !o.no_result_cache,
        ..Default::default()
    };
    let mut mids = vec![];
    for _ in 0..if shared { 1 } else { o.agents } {
        let mid = Arc::new(Middle::new(db.clone(), config.clone()).await?);
        if o.mode == "A" || o.mode == "B" {
            mid.fb.set_priority(Some(DEFAULT_ORDER.map(String::from).to_vec()));
        }
        mids.push(mid);
    }
    let manager = match o.mode.as_str() {
        "M" => Some(Optimizer::new(Provider::Mock, out)?),
        "L" => Some(Optimizer::new(Provider::from_env("openai")?, out)?),
        _ => None,
    };
    let mut decisions = vec![];
    let mut proposal_id = None;
    let mut phases = vec![];
    for month in [1, 2] {
        let before = db.meter.snap();
        let phase_start = Instant::now();
        let results = stream::iter(0..o.agents)
            .map(|agent| {
                let mid = mids[if shared { 0 } else { agent as usize }].clone();
                let tasks = tasks.clone();
                let seed = o.seed;
                async move {
                    let mut indices: Vec<usize> = tasks.iter().enumerate().filter(|(_, t)| t.month == month).map(|(i, _)| i).collect();
                    indices.shuffle(&mut StdRng::seed_from_u64(seed + u64::from(agent)));
                    let mut events = vec![];
                    for i in indices {
                        let t = &tasks[i];
                        let ctx = Ctx::new(&format!("agent-{agent}"), &format!("month-{month}"), &format!("task-{i}"));
                        let t0 = Instant::now();
                        let response = mid.run_sql(&ctx, &t.sql).await.unwrap_or_else(|e| json!({"error":format!("{e:#}")}));
                        let r = &response["result"];
                        let correct = r.is_object()
                            && r["rows"] == t.expected["rows"]
                            && r["row_count"] == t.expected["row_count"]
                            && r["truncated"] == false;
                        events.push(json!({"task":i,"agent":agent,"family":t.family,"correct":correct,
                        "latency_ms":t0.elapsed().as_secs_f64()*1000.0,"source":response["source"],
                        "failure":if correct {Value::Null}else{response}}));
                    }
                    events
                }
            })
            .buffer_unordered(o.agents as usize)
            .collect::<Vec<_>>()
            .await;
        let events: Vec<Value> = results.into_iter().flatten().collect();
        let times: Vec<f64> = events.iter().filter_map(|e| e["latency_ms"].as_f64()).collect();
        phases.push(json!({"month":month,"tasks":events.len(),"correct":events.iter().filter(|e|e["correct"]==true).count(),
            "wall_seconds":phase_start.elapsed().as_secs_f64(),"p95_ms":crate::benchmark::percentile(&times,0.95),
            "database":crate::sim::diff(&before,&db.meter.snap()),"events":events}));
        if let Some(manager) = &manager {
            if let Some(id) = proposal_id {
                decisions.push(json!({"stage":month,"apply":manager.apply(id,&mids[0].fb).map_err(|e|e.to_string())}));
            } else {
                match manager.propose(&mids[0].fb).await {
                    Ok(p) => {
                        proposal_id = Some(p.id);
                        decisions.push(json!({"stage":month,"proposal":p}));
                    }
                    Err(e) => decisions.push(json!({"stage":month,"error":e.to_string()})),
                }
            }
        }
    }
    let report = json!({"options":o,"source":"NYC TLC Jan/Feb 2024 real data; scripted read-only workload",
        "wall_seconds":start.elapsed().as_secs_f64(),"total_database":db.meter.snap(),"phases":phases,"decisions":decisions,
        "states":mids.iter().map(|m|m.stats_json()).collect::<Vec<_>>(),"traces":mids.iter().map(|m|m.take_check_traces()).collect::<Vec<_>>()});
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("{}: {} ms DB, {:.2} seconds wall", o.mode, report["total_database"]["db_ms"], start.elapsed().as_secs_f64());
    Ok(())
}

/// This is a check-order microbenchmark, not an end-to-end adapter speedup claim.
async fn check_study(url: &str, out: &str, mode: &str) -> Result<()> {
    use crate::checks::{Check, Outcome};
    use crate::feedback::{Feedback, Obs};
    let db = Db::connect(url, 1, true)?;
    let mut experiments = vec![];
    for probe_key in [true, false] {
        let fb = Feedback::default();
        // Same train/validation/deployment boundaries for Mock and the real model.
        let manager = match mode {
            "M" => Some(Optimizer::new(Provider::Mock, &format!("{out}/manager-{probe_key}"))?),
            "L" => Some(Optimizer::new(Provider::from_env("openai")?, &format!("{out}/manager-{probe_key}"))?),
            _ => None,
        };
        let mut decisions = vec![];
        let mut proposal_id = None;
        if manager.is_some() || mode == "B" {
            fb.set_priority(Some(DEFAULT_ORDER.map(String::from).to_vec()));
        }
        let mut events = vec![];
        for index in 0..48 {
            let month = if index < 24 { 1 } else { 2 };
            let day = index % 24 + 1;
            let rf = Some(format!("t_pu between 132 and 170 and t_pickup >= timestamp '2024-{month:02}-{day:02}' and t_pickup < timestamp '2024-{month:02}-{:02}'",day+1));
            let lf = Some("z_id between 132 and 170".to_string());
            let checks = vec![
                Check::KeyUnique { table: "trips".into(), cols: vec!["t_pu".into()], filter: rf.clone() },
                Check::RowConservation {
                    left: "zones".into(),
                    right: "trips".into(),
                    on: vec![("z_id".into(), "t_pu".into())],
                    lf: lf.clone(),
                    rf: rf.clone(),
                },
                Check::SampleFanout {
                    left: "zones".into(),
                    right: "trips".into(),
                    on: vec![("z_id".into(), "t_pu".into())],
                    lf,
                    rf,
                    n: 1000,
                },
            ];
            let estimate = |table: &str| if table == "trips" { 5_972_150.0 } else { 265.0 };
            let order = fb.order(true, checks.clone(), &estimate, &|_| false);
            let was_adopted = if let Some(manager) = &manager {
                manager.snapshot(&fb)["state"]["active"].is_u64()
            } else {
                fb.report()["adaptive"]["adopted"] == true
            };
            // Paired actual executions, alternating order. Every measured trial is followed by
            // separately charged full observation; observations only affect subsequent candidates.
            let mut pair = vec![];
            for n in 0..2 {
                let candidate = (index + n) % 2 == 0;
                let sequence = if candidate { &order } else { &checks };
                let before = db.meter.snap();
                let mut ran_key = false;
                let mut verdict = true;
                for c in sequence {
                    let start = Instant::now();
                    let rows = db.query(QKind::Check, &c.sql()).await?;
                    let o = c.eval(&rows, start.elapsed().as_secs_f64() * 1000.0);
                    ran_key |= c.kind() == "KeyUnique";
                    if !o.pass {
                        verdict = false;
                        if probe_key && !ran_key {
                            db.query(QKind::Check, &checks[0].sql()).await?;
                        }
                        break;
                    }
                }
                pair.push(json!({"candidate":candidate,"pass":verdict,"db_ms":db.meter.snap().db_ms-before.db_ms}));
            }
            let audit_start = db.meter.snap();
            let mut obs = vec![];
            for offset in 0..3 {
                let c = &checks[(index as usize + offset) % 3];
                let start = Instant::now();
                let rows = db.query(QKind::Check, &c.sql()).await?;
                let o: Outcome = c.eval(&rows, start.elapsed().as_secs_f64() * 1000.0);
                fb.record(c, &o, &estimate);
                obs.push(Obs::new(c, &o, true, &estimate));
            }
            fb.episode(obs, true, probe_key);
            if let Some(manager) = &manager {
                if index == 7 {
                    match manager.propose(&fb).await {
                        Ok(p) => {
                            proposal_id = Some(p.id);
                            decisions.push(json!({"after_index":index,"proposal":p}));
                        }
                        Err(e) => decisions.push(json!({"after_index":index,"error":format!("{e:#}")})),
                    }
                }
                if index == 15 {
                    if let Some(id) = proposal_id {
                        decisions.push(json!({"after_index":index,"apply":manager.apply(id,&fb).map_err(|e|e.to_string())}));
                    }
                }
                if index >= 23 && (index + 1) % 8 == 0 {
                    decisions.push(json!({"after_index":index,"watch":manager.watch(&fb).map_err(|e|e.to_string())}));
                }
            }
            events.push(json!({"index":index,"month":month,"day":day,"adopted_before_execution":was_adopted,
                "order":order.iter().map(Check::kind).collect::<Vec<_>>(),"paired_execution":pair,
                "full_observation_db_ms":db.meter.snap().db_ms-audit_start.db_ms}));
        }
        experiments.push(json!({"key_probe_required":probe_key,"events":events,"feedback":fb.report(),"decisions":decisions}));
    }
    std::fs::write(
        format!("{out}/check-study.json"),
        serde_json::to_string_pretty(&json!({
        "description":"Real-record check-order microbenchmark; 100% full observation cost separately reported; no cache; single worker; fixed scorer with future candidate groups; two repair states, not end-to-end speedup",
        "mode":mode,"experiments":experiments,"all_database_cost":db.meter.snap()}))?,
    )?;
    println!("Real-data check study complete");
    Ok(())
}
