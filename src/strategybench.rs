//! 对已有反馈排序器的数据库计时回放。全观测采集成本单列，不能冒充实时加速。
use crate::checks::{Check, Outcome};
use crate::db::{Db, QKind};
use crate::feedback::{Feedback, Obs};
use anyhow::{ensure, Context, Result};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    #[arg(long, default_value_t = 100_000, value_parser = clap::value_parser!(u32).range(10_000..=1_000_000))]
    rows: u32,
    #[arg(long, default_value_t = 64, value_parser = clap::value_parser!(u32).range(48..=128))]
    groups: u32,
    #[arg(long, default_value_t = 3, value_parser = clap::value_parser!(u32).range(1..=5))]
    measurements: u32,
}

struct Candidate {
    checks: Vec<Check>,
    outcomes: Vec<Outcome>,
}

fn replay(c: &Candidate, order: &[Check], probe_key: bool) -> (f64, bool) {
    let mut ms = 0.0;
    let mut key_seen = false;
    for check in order {
        let i = c.checks.iter().position(|x| x == check).expect("same candidate");
        let outcome = &c.outcomes[i];
        ms += outcome.ms;
        key_seen |= matches!(check, Check::KeyUnique { .. });
        if !outcome.pass {
            if !key_seen && probe_key {
                ms += c.outcomes[0].ms;
            }
            return (ms, false);
        }
    }
    (ms, true)
}

pub async fn run(url: &str, out: &str, o: Options) -> Result<()> {
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_strategy_{}_{stamp}", std::process::id());
    let directory = format!("{out}/strategy-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await.context("创建隔离实验库失败")?;
    let result: Result<Value> = async {
        let admin = Db::connect(isolated.as_str(), 2, false)?;
        let mut candidates = Vec::new();
        let mut row_counts = HashMap::new();
        let mut raw = Vec::new();
        let mut full_observation_ms = 0.0;
        let start = Instant::now();
        for g in 0..o.groups {
            let left = format!("facts_{g}");
            let right = format!("dimension_{g}");
            let duplicate = g % 4 != 0;
            let keys = if duplicate { o.rows / 2 } else { o.rows };
            let left_rows = 2_000_u32;
            admin.query(QKind::Meta, &format!(
                "create table {right} (r_key integer not null); \
                 insert into {right} select 1 + (x - 1) % {keys} from generate_series(1,{rows}) x; \
                 create index on {right}(r_key); \
                 create table {left} (l_key integer not null); \
                 insert into {left} select 1 + (x * 7919 + {g} * 101) % {keys} from generate_series(1,{left_rows}) x; \
                 analyze {right}; analyze {left}", rows=o.rows)).await?;
            row_counts.insert(left.clone(), left_rows as f64);
            row_counts.insert(right.clone(), o.rows as f64);
            let on = vec![("l_key".into(), "r_key".into())];
            let checks = vec![
                Check::KeyUnique { table: right.clone(), cols: vec!["r_key".into()], filter: None },
                Check::RowConservation { left: left.clone(), right: right.clone(), on: on.clone(), lf: None, rf: None },
                Check::SampleFanout { left: left.clone(), right: right.clone(), on, lf: None, rf: None, n: 1000 },
            ];
            let mut measured: Vec<Vec<Outcome>> = vec![vec![], vec![], vec![]];
            for pass in 0..o.measurements {
                for offset in 0..3 {
                    let i = (g as usize + pass as usize + offset) % 3;
                    let t0 = Instant::now();
                    let rows = admin.query(QKind::Check, &checks[i].sql()).await?;
                    let ms = t0.elapsed().as_secs_f64() * 1000.0;
                    let outcome = checks[i].eval(&rows, ms);
                    full_observation_ms += ms;
                    raw.push(json!({"group":g,"measurement":pass,"check":checks[i],"outcome":outcome}));
                    measured[i].push(outcome);
                }
            }
            let outcomes: Vec<Outcome> = measured.into_iter().map(|mut xs| {
                xs.sort_by(|a,b| a.ms.total_cmp(&b.ms));
                xs[xs.len()/2].clone()
            }).collect();
            ensure!(outcomes.iter().all(|x| x.pass == !duplicate), "实验候选的检查结论不一致");
            candidates.push(Candidate { checks, outcomes });
            std::fs::write(format!("{directory}/observations.json"), serde_json::to_string_pretty(&raw)?)?;
        }
        let rows = |table: &str| row_counts.get(table).copied().unwrap_or_default();
        let training = 24_usize;
        let validation = 16_usize;
        let permutations = [[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]];
        let mut results = Vec::new();
        for setting in ["key-required", "repair-exhausted", "mixed"] {
            let feedback = Feedback::default();
            let probe = |idx:usize| match setting { "key-required"=>true, "repair-exhausted"=>false, _=>idx.is_multiple_of(2) };
            for (i,c) in candidates.iter().take(training).enumerate() {
                for (check,outcome) in c.checks.iter().zip(&c.outcomes) { feedback.record(check,outcome,&rows); }
                feedback.episode(c.checks.iter().zip(&c.outcomes).map(|(check,outcome)|Obs::new(check,outcome,true,&rows)).collect(),true,probe(i));
            }
            // 空候选冻结训练评分器，不把任何采纳候选登记为训练组。
            feedback.order(true,vec![],&rows,&|_|false);
            for (i,c) in candidates.iter().enumerate().skip(training).take(validation) {
                for (check,outcome) in c.checks.iter().zip(&c.outcomes) { feedback.record(check,outcome,&rows); }
                feedback.episode(c.checks.iter().zip(&c.outcomes).map(|(check,outcome)|Obs::new(check,outcome,true,&rows)).collect(),true,probe(i));
            }
            feedback.order(true,vec![],&rows,&|_|false);
            let adoption = feedback.report();
            let mut tests = Vec::new();
            for (i,c) in candidates.iter().enumerate().skip(training+validation) {
                let selected = feedback.order(true,c.checks.clone(),&rows,&|_|false);
                let (adaptive_ms, adaptive_pass) = replay(c,&selected,probe(i));
                let (fixed_ms, fixed_pass) = replay(c,&c.checks,probe(i));
                ensure!(adaptive_pass==fixed_pass,"顺序改变了候选判定");
                let all:Vec<Value> = permutations.iter().map(|p| {
                    let order:Vec<Check>=p.iter().map(|&j|c.checks[j].clone()).collect();
                    let (ms,pass)=replay(c,&order,probe(i));
                    json!({"order":p,"ms":ms,"pass":pass})
                }).collect();
                tests.push(json!({"group":i,"probe_key":probe(i),"pass":fixed_pass,
                    "default_ms":fixed_ms,"selected_ms":adaptive_ms,"selected_order":selected.iter().map(Check::kind).collect::<Vec<_>>(),"permutations":all}));
            }
            results.push(json!({"setting":setting,"adoption":adoption,"tests":tests}));
        }
        Ok(json!({"options":o,"training_groups":training,"validation_groups":validation,
            "test_groups":o.groups as usize-training-validation,"full_observation_ms":full_observation_ms,
            "collection_seconds":start.elapsed().as_secs_f64(),"results":results,
            "methodology":"PostgreSQL measured outcomes; median of three rotated measurements per check; chronological disjoint training/validation/test table pairs; scoring frozen before validation; no test feedback; all permutations replay identical actual costs; required key-diagnostic cost included; full observation acquisition overhead separate. Narrow verifier-strategy evidence, not an agent-planning or live latency experiment."}))
    }.await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    match result {
        Ok(mut report) => {
            report["database_cleaned_up"] = json!(cleanup.is_ok());
            std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
            cleanup.context("实验库清理失败")?;
            println!("策略反馈实验：{directory}");
            Ok(())
        }
        Err(e) => {
            std::fs::write(
                format!("{directory}/error.json"),
                serde_json::to_string_pretty(&json!({"error":format!("{e:#}"),"database_cleaned_up":cleanup.is_ok()}))?,
            )?;
            Err(e)
        }
    }
}
