//! Reproducible synthetic multi-agent workload. No real model calls or business databases are modified.
use crate::db::{Db, QKind};
use crate::llm::Provider;
use crate::middle::{Ctx, Middle, MiddleConfig};
use crate::optimizer::Optimizer;
use crate::{etl, sim};
use anyhow::{ensure, Context, Result};
use futures::{stream, StreamExt};
use serde::Serialize;
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    #[arg(long, default_value_t = 1_000_000, value_parser = clap::value_parser!(u32).range(1000..=5_000_000))]
    pub(crate) rows: u32,
    #[arg(long, default_value_t = 24, value_parser = clap::value_parser!(u32).range(1..=128))]
    pub(crate) agents: u32,
    #[arg(long, default_value_t = 48, value_parser = clap::value_parser!(u32).range(8..=1000))]
    pub(crate) tasks: u32,
    #[arg(long, default_value_t = 3, value_parser = clap::value_parser!(u32).range(1..=10))]
    pub(crate) rounds: u32,
    #[arg(long, default_value_t = 42)]
    pub(crate) seed: u32,
}

pub(crate) fn fixture(n: u32) -> String {
    format!(
        r#"
create table date_dim (d_date_sk int primary key, d_date date);
insert into date_dim select g, date '2001-01-01' + g - 1 from generate_series(1,365) g;
create table item (i_item_sk int primary key, i_category text);
insert into item select g, 'category-' || (g % 20) from generate_series(1,1000) g;
create table customer (c_customer_sk int primary key, c_region int);
insert into customer select g, g % 10 from generate_series(1,10000) g;
create table warehouse (w_warehouse_sk int primary key, w_region int);
insert into warehouse select g, g % 4 from generate_series(1,32) g;
create table store_sales (ss_ticket_number int, ss_item_sk int, ss_customer_sk int,
 ss_warehouse_sk int, ss_sold_date_sk int, ss_net_paid numeric(12,2));
insert into store_sales select (g-1)/5+1, (g-1)%1000+1, (g-1)%10000+1,
 (g-1)%32+1, (g-1)%365+1, 100+(g%97) from generate_series(1,{n}) g;
create index sales_key on store_sales(ss_ticket_number,ss_item_sk);
create index sales_item on store_sales(ss_item_sk);
create index sales_customer on store_sales(ss_customer_sk);
create index sales_date on store_sales(ss_sold_date_sk);
create table store_returns (sr_ticket_number int, sr_item_sk int, sr_returned_date_sk int, sr_return_amt numeric(12,2));
insert into store_returns select ss_ticket_number,ss_item_sk,ss_sold_date_sk,ss_net_paid/10
 from store_sales where (ss_item_sk-1)%5 in (0,1);
create index returns_key on store_returns(sr_ticket_number,sr_item_sk);
analyze date_dim; analyze item; analyze customer; analyze warehouse; analyze store_sales; analyze store_returns;
create table risk_left as select g as rl_row from generate_series(1,20000) g;
create table risk_right as select g as rr_row from generate_series(1,20000) g;
"#
    )
}

#[derive(Serialize)]
struct Event {
    agent: u32,
    session: u32,
    task: u32,
    scenario: String,
    tool: String,
    args: Value,
    expected: Value,
    response: Value,
    correct: bool,
    latency_ms: f64,
}

pub(crate) async fn risk_fixture(db: &Db) -> Result<()> {
    for i in 0..16 {
        db.query(
            QKind::Meta,
            &format!(
                "alter table risk_left add column rl_key{i} int; alter table risk_right add column rr_key{i} int; \
             update risk_left set rl_key{i}=(rl_row-1)/{}; update risk_right set rr_key{i}=(rr_row-1)/{}; \
             create index risk_left_{i} on risk_left(rl_key{i}); create index risk_right_{i} on risk_right(rr_key{i});",
                2 + i % 4,
                2 + i % 4
            ),
        )
        .await?;
    }
    db.query(QKind::Meta, "vacuum analyze risk_left").await?;
    db.query(QKind::Meta, "vacuum analyze risk_right").await?;
    Ok(())
}

struct Scenario {
    name: &'static str,
    tool: &'static str,
    args: Value,
    expected: Value,
}

pub(crate) fn pair(composite: bool) -> Value {
    let mut on = vec![json!(["sr_ticket_number", "ss_ticket_number"])];
    if composite {
        on.push(json!(["sr_item_sk", "ss_item_sk"]));
    }
    json!({"left":"store_returns","right":"store_sales","on":on})
}

fn scenario(kind: u32, bucket: u32, drift: bool, gold: &[f64]) -> Scenario {
    match kind {
        0 => Scenario {
            name: "共享表画像",
            tool: "describe_table",
            args: json!({"table":"store_returns"}),
            expected: json!({"success":true}),
        },
        1 => Scenario {
            name: "分桶金额汇总",
            tool: "run_sql",
            args: json!({"sql":format!("select sum(ss_net_paid) from store_sales where ss_item_sk % 8 = {bucket}")}),
            expected: json!({"scalar":gold[bucket as usize]}),
        },
        2 => Scenario {
            name: "多对一维度关联",
            tool: "check_join",
            args: json!({"left":"store_sales","right":"item","on":[["ss_item_sk","i_item_sk"]]}),
            expected: json!({"valid":true}),
        },
        3 => {
            let key = bucket + if drift { 8 } else { 0 };
            Scenario {
                name: "未见过的多对多陷阱",
                tool: "check_join",
                args: json!({"left":"risk_left","right":"risk_right","on":[[format!("rl_key{key}"),format!("rr_key{key}")]]}),
                expected: json!({"valid":false}),
            }
        }
        4 => Scenario {
            name: "未过滤退货汇总",
            tool: "run_sql",
            args: json!({"sql":"select sum(sr_return_amt) from store_returns"}),
            expected: if drift { json!({"rejected":true}) } else { json!({"scalar":gold[8]}) },
        },
        5 => Scenario { name: "复合键关联", tool: "check_join", args: pair(true), expected: json!({"valid":true}) },
        6 => Scenario {
            name: "正确粒度汇总",
            tool: "run_sql",
            args: json!({"sql":"select sum(sr_return_amt) from store_returns where sr_status = '完成'"}),
            expected: json!({"scalar":gold[8]}),
        },
        _ => Scenario {
            name: "不存在的列",
            tool: "check_join",
            args: json!({"left":"store_returns","right":"store_sales","on":[["missing_column","ss_item_sk"]]}),
            expected: json!({"error":true}),
        },
    }
}

fn correct(expected: &Value, response: &Value) -> bool {
    if expected.get("error").is_some() {
        return response.get("error").is_some();
    }
    if response.get("error").is_some() {
        return false;
    }
    if let Some(value) = expected.get("scalar").and_then(Value::as_f64) {
        return response["result"]["rows"][0][0]
            .as_str()
            .and_then(|s| s.parse::<f64>().ok())
            .is_some_and(|actual| (actual - value).abs() < 0.01);
    }
    for key in ["valid", "rejected"] {
        if let Some(value) = expected.get(key) {
            return response.get(key) == Some(value);
        }
    }
    response.get("rejected").is_none()
}

pub(crate) fn percentile(values: &[f64], p: f64) -> f64 {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    sorted[((sorted.len() as f64 * p).ceil() as usize).saturating_sub(1).min(sorted.len() - 1)]
}

async fn phase(mid: Arc<Middle>, o: &Options, drift: bool, gold: Arc<Vec<f64>>) -> Result<Value> {
    phase_for_agents(vec![mid; o.agents as usize], o, drift, gold).await
}

pub(crate) async fn phase_for_agents(mids: Vec<Arc<Middle>>, o: &Options, drift: bool, gold: Arc<Vec<f64>>) -> Result<Value> {
    let db = mids[0].db.clone();
    let before = db.meter.snap();
    let started = Instant::now();
    let groups = stream::iter(0..o.agents)
        .map(|agent| {
            let mid = mids[agent as usize].clone();
            let gold = gold.clone();
            async move {
                let mut events = Vec::new();
                for task in 0..o.tasks {
                    let s = scenario(((task as u64 + agent as u64 + o.seed as u64) % 8) as u32, agent % 8, drift, &gold);
                    let ctx = Ctx::new(&format!("agent-{agent}"), &format!("session-{}", task / 8), &format!("task-{task}"));
                    let start = Instant::now();
                    let response = match mid.call_tool(&ctx, s.tool, &s.args).await {
                        Ok(v) => v,
                        Err(e) => json!({"error":format!("{e:#}")}),
                    };
                    events.push(Event {
                        agent,
                        session: task / 8,
                        task,
                        scenario: s.name.into(),
                        tool: s.tool.into(),
                        args: s.args,
                        correct: correct(&s.expected, &response),
                        expected: s.expected,
                        response,
                        latency_ms: start.elapsed().as_secs_f64() * 1000.0,
                    });
                }
                events
            }
        })
        .buffer_unordered(o.agents as usize)
        .collect::<Vec<_>>()
        .await;
    let wall = started.elapsed().as_secs_f64();
    let events: Vec<Event> = groups.into_iter().flatten().collect();
    let times: Vec<f64> = events.iter().map(|e| e.latency_ms).collect();
    let successful = events.iter().filter(|e| e.correct).count();
    let mut scenarios = std::collections::BTreeMap::<String, Value>::new();
    for name in events.iter().map(|e| e.scenario.clone()).collect::<std::collections::BTreeSet<_>>() {
        let selected: Vec<_> = events.iter().filter(|e| e.scenario == name).collect();
        scenarios.insert(
            name,
            json!({"requests":selected.len(),"correct":selected.iter().filter(|e|e.correct).count(),
            "example":selected.first(),"failures":selected.iter().filter(|e|!e.correct).collect::<Vec<_>>()}),
        );
    }
    let mut seen = std::collections::BTreeSet::new();
    let traces: Vec<Value> = mids.iter().filter(|m| seen.insert(Arc::as_ptr(m) as usize)).flat_map(|m| m.take_check_traces()).collect();
    Ok(json!({"phase":if drift {"v2"} else {"v1"},"requests":events.len(),"correct":successful,
        "accuracy":successful as f64/events.len() as f64,"wall_seconds":wall,"requests_per_second":events.len() as f64/wall,
        "p50_ms":percentile(&times,0.5),"p95_ms":percentile(&times,0.95),"p99_ms":percentile(&times,0.99),
        "database":sim::diff(&before,&db.meter.snap()),"scenarios":scenarios,"events":events,"check_traces":traces}))
}

async fn trial(url: &str, admin: &Db, o: &Options, pool: usize, mode: &str, output: (&str, u32), gold: Arc<Vec<f64>>) -> Result<Value> {
    let (out, round) = output;
    etl::reset(admin).await?;
    // Equal explicit warmup for every mode; no OS-cache eviction is attempted.
    admin.query(QKind::Meta, "select sum(ss_net_paid) from store_sales; select sum(sr_return_amt) from store_returns").await?;
    let db = Arc::new(Db::connect(url, pool, true)?);
    let mid = Arc::new(Middle::new(db, MiddleConfig { name: mode.into(), trace_checks: true, ..Default::default() }).await?);
    // Keep feedback collection and the same 20% audit active in all groups.
    // Only the scheduling order is fixed in this comparator.
    if mode == "fixed" {
        mid.fb.set_priority(Some(vec!["KeyUnique".into(), "RowConservation".into(), "SampleFanout".into()]));
    }
    let ctx = Ctx::new("training", "training", "training");
    for (table, left, right) in
        [("item", "ss_item_sk", "i_item_sk"), ("customer", "ss_customer_sk", "c_customer_sk"), ("date_dim", "ss_sold_date_sk", "d_date_sk")]
    {
        mid.call_tool(&ctx, "check_join", &json!({"left":"store_sales","right":table,"on":[[left,right]]})).await?;
    }
    mid.call_tool(&ctx, "check_join", &pair(true)).await?;
    mid.call_tool(&ctx, "check_join", &pair(false)).await?;
    let optimizer =
        if mode == "mock-managed" { Some(Optimizer::new(Provider::Mock, &format!("{out}/round-{round}-{mode}"))?) } else { None };
    let mut decisions = vec![];
    if let Some(manager) = &optimizer {
        let p = manager.propose(&mid.fb).await?;
        decisions.push(json!({"phase":"after-training","proposal":p,"apply":manager.apply(p.id,&mid.fb)?}));
    }
    let training = json!({"stats":mid.stats_json(),"check_traces":mid.take_check_traces()});
    let v1 = phase(mid.clone(), o, false, gold.clone()).await?;
    let drift_before = mid.db.meter.snap();
    let drift_start = Instant::now();
    let inserted = etl::apply_v2(admin).await?;
    let unfiltered = admin.query(QKind::Meta, "select sum(sr_return_amt) from store_returns").await?.f64(0, 0).context("无未过滤汇总")?;
    mid.invalidate_versions();
    let repair = mid.call_tool(&ctx, "check_join", &pair(true)).await?;
    let drift = json!({"inserted_rows":inserted,"unfiltered_amount":unfiltered,"inflation_percent":(unfiltered/gold[8]-1.0)*100.0,"repair":repair,"wall_seconds":drift_start.elapsed().as_secs_f64(),"check_traces":mid.take_check_traces(),
        "database":sim::diff(&drift_before,&mid.db.meter.snap()),"etl_notification":true});
    if let Some(manager) = &optimizer {
        let p = manager.propose(&mid.fb).await?;
        decisions.push(json!({"phase":"after-drift","proposal":p,"apply":manager.apply(p.id,&mid.fb)?}));
    }
    let v2 = phase(mid.clone(), o, true, gold).await?;
    Ok(json!({"round":round,"mode":mode,"training":training,"v1":v1,"drift":drift,"v2":v2,
        "decisions":decisions,"final_stats":mid.stats_json()}))
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_bench_{}_{stamp}", std::process::id());
    let directory = format!("{out}/bench-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await.context("创建隔离实验库失败（需要 CREATEDB）")?;
    let result: Result<Value> = async {
        let admin=Db::connect(isolated.as_str(),2,false)?;
        eprintln!("准备 {} 条销售数据，{} 个 Agent，每阶段每 Agent {} 个任务，{} 轮三组对照",o.rows,o.agents,o.tasks,o.rounds);
        admin.query(QKind::Meta,&fixture(o.rows)).await?;
        risk_fixture(&admin).await?;
        etl::setup(&admin).await?;
        let count=admin.query(QKind::Meta,"select count(*) from store_returns").await?.i64(0,0).unwrap_or(0);
        let mut gold=vec![];
        for bucket in 0..8 {gold.push(admin.query(QKind::Meta,&format!("select coalesce(sum(ss_net_paid),0) from store_sales where ss_item_sk % 8 = {bucket}")).await?.f64(0,0).unwrap_or(0.0));}
        gold.push(admin.query(QKind::Meta,"select sum(sr_return_amt) from store_returns").await?.f64(0,0).unwrap_or(0.0));
        let gold=Arc::new(gold);
        let mut runs=vec![];
        let modes=["fixed","feedback","mock-managed"];
        for round in 0..o.rounds {
            for offset in 0..3 {
                let mode=modes[(round as usize+offset)%3];
                eprintln!("第 {} 轮 / {}：训练 → v1 混合负载 → ETL 改版 → v2 混合负载",round+1,mode);
                let r=trial(isolated.as_str(),&admin,&o,pool,mode,(&directory,round+1),gold.clone()).await?;
                std::fs::write(format!("{directory}/round-{}-{mode}.json",round+1),serde_json::to_string_pretty(&r)?)?;
                eprintln!("  v1 正确率 {:.1}%，v2 正确率 {:.1}%",r["v1"]["accuracy"].as_f64().unwrap_or(0.0)*100.0,r["v2"]["accuracy"].as_f64().unwrap_or(0.0)*100.0);
                runs.push(r);
            }
        }
        Ok(json!({"options":o,"pool":pool,"dataset":{"sales":o.rows,"returns_v1":count,"dimension_rows":11397,"heldout_risk_rows":40000,"gold_return_amount":gold[8]},
            "methodology":{"transport":"in-process call_tool; excludes HTTP and real LLM latency","agents":"concurrent scripted agents; sequential tasks per agent","order":"rotated across rounds","version_ttl_ms":200,"audit_rate":0.2,"audit_randomness":"unseeded; run-to-run variation remains","seed_scope":"deterministic scenario rotation only","training_excluded_from_phase_metrics":true,"drift_excluded_from_phase_metrics":true},"runs":runs}))
    }.await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    match result {
        Ok(mut report) => {
            report["database_cleaned_up"] = json!(cleanup.is_ok());
            std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
            std::fs::write(format!("{directory}/report.md"), markdown(&report))?;
            println!("规模实验报告：{directory}/report.md");
            cleanup.context("实验库清理失败")?;
            ensure!(
                report["runs"].as_array().unwrap().iter().all(|r| r["v1"]["accuracy"] == 1.0 && r["v2"]["accuracy"] == 1.0),
                "出现不符合预期的结果，见逐请求日志"
            );
            Ok(())
        }
        Err(error) => {
            std::fs::write(
                format!("{directory}/error.json"),
                serde_json::to_string_pretty(&json!({"error":format!("{error:#}"),"database_cleaned_up":cleanup.is_ok()}))?,
            )?;
            Err(error)
        }
    }
}

fn markdown(report: &Value) -> String {
    let mut text = format!("# 多 Agent 规模实验\n\n配置：`{}`\n\n数据：`{}`\n\n", report["options"], report["dataset"]);
    text.push_str("## 合并指标\n\nP95 按各模式全部请求重新计算；吞吐量为总请求数 / 各阶段墙钟时间之和。\n\n|模式|请求数|正确率|P95 ms|吞吐 请求/秒|SQL 次数|DB 累计 ms|\n|---|---:|---:|---:|---:|---:|---:|\n");
    for mode in ["fixed", "feedback", "mock-managed"] {
        let runs: Vec<_> = report["runs"].as_array().unwrap().iter().filter(|r| r["mode"] == mode).collect();
        let phases: Vec<_> = runs.iter().flat_map(|r| [&r["v1"], &r["v2"]]).collect();
        let events: Vec<_> = phases.iter().flat_map(|p| p["events"].as_array().unwrap()).collect();
        let times: Vec<_> = events.iter().map(|e| e["latency_ms"].as_f64().unwrap()).collect();
        let success = events.iter().filter(|e| e["correct"] == true).count();
        let wall: f64 = phases.iter().map(|p| p["wall_seconds"].as_f64().unwrap()).sum();
        let queries: u64 = phases.iter().map(|p| p["database"]["queries"].as_u64().unwrap()).sum();
        let ms: f64 = phases.iter().map(|p| p["database"]["db_ms"].as_f64().unwrap()).sum();
        text.push_str(&format!(
            "|{mode}|{}|{:.2}%|{:.2}|{:.2}|{queries}|{ms:.2}|\n",
            events.len(),
            success as f64 / events.len() as f64 * 100.0,
            percentile(&times, 0.95),
            events.len() as f64 / wall
        ));
    }
    text.push_str("\n## 分轮结果\n\n");
    text.push_str(
        "|轮次|模式|阶段|请求|正确率|P50 ms|P95 ms|请求/秒|SQL 次数|DB 累计 ms|\n|---|---|---|---:|---:|---:|---:|---:|---:|---:|\n",
    );
    for run in report["runs"].as_array().unwrap() {
        for phase in ["v1", "v2"] {
            let p = &run[phase];
            text.push_str(&format!(
                "|{}|{}|{}|{}|{:.2}%|{:.2}|{:.2}|{:.2}|{}|{:.2}|\n",
                run["round"],
                run["mode"].as_str().unwrap(),
                phase,
                p["requests"],
                p["accuracy"].as_f64().unwrap() * 100.0,
                p["p50_ms"].as_f64().unwrap(),
                p["p95_ms"].as_f64().unwrap(),
                p["requests_per_second"].as_f64().unwrap(),
                p["database"]["queries"],
                p["database"]["db_ms"].as_f64().unwrap()
            ));
        }
    }
    text.push_str("\n## 如何解释\n\n- fixed、feedback、mock-managed 共用缓存、在途合并和守护；仅检查排序策略不同。不能把共享缓存收益归因于模型。\n- Agent 为并发脚本，不是真实推理模型。直接调用与 HTTP 相同的工具调度，不包含 HTTP、模型网络耗时或 token 成本。\n- 所有组使用相同数据与任务序列，轮换执行顺序；没有清空操作系统缓存。反馈审计存在未固定种子的随机性。\n- v1/v2 表格只含混合负载；训练、ETL 通知、重验修复和策略应用独立记录在 JSON 中。\n- JSON 的 scenarios 与 events 记录每次输入、预期、实际结果、耗时与拒绝理由；决策记录含原始反馈。\n- 多数请求可复用经验，因此排序策略可能没有稳定优势。比较多轮分布，不凭单次毫秒差得出提升结论。\n");
    text.push_str("\n## 决策依据（mock 可逐项复算）\n\n分数 = ((失败次数 + 1) / (执行次数 + 2)) / (平均耗时 ms + 1)，按分数降序。平滑概率不等于真实错误率；真实模型的推理也不等于此公式。\n\n");
    for run in report["runs"].as_array().unwrap().iter().filter(|r| r["mode"] == "mock-managed") {
        for decision in run["decisions"].as_array().unwrap() {
            let p = &decision["proposal"];
            text.push_str(&format!(
                "### 第 {} 轮 / {}\n\n排序：`{}`\n\n|检查|样本|失败|平均 ms|平滑失败概率|分数|\n|---|---:|---:|---:|---:|---:|\n",
                run["round"],
                decision["phase"].as_str().unwrap(),
                p["policy"]["check_order"]
            ));
            for (kind, s) in p["heuristic_reference"]["scores"].as_object().unwrap() {
                text.push_str(&format!(
                    "|{kind}|{}|{}|{:.3}|{:.4}|{:.6}|\n",
                    s["runs"],
                    s["fails"],
                    s["mean_ms"].as_f64().unwrap(),
                    s["smoothed_failure_probability"].as_f64().unwrap(),
                    s["score"].as_f64().unwrap()
                ));
            }
        }
    }
    let first = &report["runs"][0];
    text.push_str(&format!("\n## 数据变更的因果链（首轮示例）\n\n1. ETL 新增 {} 条申请状态行，业务退货并未增加。\n2. 之前复合键唯一的经验触发重验，修复响应保留通知与证据。\n3. 修复过滤条件：`{}`。\n4. 未过滤汇总预期被拒绝；正确金额的独立 SQL 基准为 {}。\n\n修复证据：\n```json\n{}\n```\n",first["drift"]["inserted_rows"],first["drift"]["repair"]["path"]["filters"],report["dataset"]["gold_return_amount"],serde_json::to_string_pretty(&first["drift"]["repair"]).unwrap()));
    text.push_str("\n## 场景覆盖（全部模式与轮次）\n\n|场景|请求|符合预期|\n|---|---:|---:|\n");
    let mut totals = std::collections::BTreeMap::<String, (u64, u64)>::new();
    for run in report["runs"].as_array().unwrap() {
        for phase in ["v1", "v2"] {
            for (name, s) in run[phase]["scenarios"].as_object().unwrap() {
                let counts = totals.entry(name.clone()).or_default();
                counts.0 += s["requests"].as_u64().unwrap();
                counts.1 += s["correct"].as_u64().unwrap();
            }
        }
    }
    for (name, (requests, correct)) in totals {
        text.push_str(&format!("|{name}|{requests}|{correct}|\n"));
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn grading_distinguishes_correct_rejection_from_silent_error() {
        assert!(correct(&json!({"valid":false}), &json!({"valid":false})));
        assert!(!correct(&json!({"rejected":true}), &json!({"result":{"rows":[["120.00"]]}})));
        assert!(correct(&json!({"scalar":100.0}), &json!({"result":{"rows":[["100.00"]]}})));
        assert!(!correct(&json!({"scalar":100.0}), &json!({"result":{"rows":[["120.00"]]}})));
        assert!(!correct(&json!({"valid":false}), &json!({"error":"database disconnected"})));
    }
    #[test]
    fn quantiles_use_nearest_rank() {
        assert_eq!(percentile(&[4.0, 1.0, 2.0, 3.0], 0.5), 2.0);
        assert_eq!(percentile(&[4.0, 1.0, 2.0, 3.0], 0.95), 4.0);
    }
}
