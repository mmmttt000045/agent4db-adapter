//! Factorial experiment: cross-agent knowledge sharing × adaptive check ordering.
use crate::benchmark::{self, Options};
use crate::db::{Db, QKind};
use crate::etl;
use crate::middle::{Ctx, GuardMode, Middle, MiddleConfig, Scope};
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

const MODES: [&str; 4] = ["A", "B", "C", "D"];

fn config(mode: &str, seed: u32) -> MiddleConfig {
    MiddleConfig {
        name: mode.into(),
        scope: if matches!(mode, "B" | "D") { Scope::Global } else { Scope::Agent },
        singleflight: false,
        feedback: true,
        trace_checks: true,
        audit_seed: Some(u64::from(seed)),
        ..Default::default()
    }
}

async fn train(mid: &Middle, agent: u32) -> Result<()> {
    let ctx = Ctx::new(&format!("agent-{agent}"), "training", "training");
    for (table, left, right) in
        [("item", "ss_item_sk", "i_item_sk"), ("customer", "ss_customer_sk", "c_customer_sk"), ("date_dim", "ss_sold_date_sk", "d_date_sk")]
    {
        mid.call_tool(&ctx, "check_join", &json!({"left":"store_sales","right":table,"on":[[left,right]]})).await?;
    }
    mid.call_tool(&ctx, "check_join", &benchmark::pair(true)).await?;
    mid.call_tool(&ctx, "check_join", &benchmark::pair(false)).await?;
    Ok(())
}

async fn trial(url: &str, mode: &str, o: &Options, pool: usize, gold: Arc<Vec<f64>>) -> Result<Value> {
    let db = Arc::new(Db::connect(url, pool, true)?);
    let cold_start = Instant::now();
    let shared = matches!(mode, "B" | "D");
    let adaptive = matches!(mode, "C" | "D");
    let mut unique = vec![];
    for _ in 0..if shared { 1 } else { o.agents } {
        let mid = Arc::new(Middle::new(db.clone(), config(mode, o.seed)).await?);
        // Keep collection and the same candidate-level audit in every cell.
        if !adaptive {
            mid.fb.set_priority(Some(vec!["KeyUnique".into(), "RowConservation".into(), "SampleFanout".into()]));
        }
        unique.push(mid);
    }
    let mids = if shared { vec![unique[0].clone(); o.agents as usize] } else { unique.clone() };
    // Identical logical training calls for each agent; shared cells may reuse them.
    for (agent, mid) in mids.iter().enumerate() {
        train(mid, agent as u32).await?;
    }
    let training_wall = cold_start.elapsed().as_secs_f64();
    let training_database = db.meter.snap();
    let training: Vec<_> = unique.iter().map(|m| json!({"stats":m.stats_json(),"checks":m.take_check_traces()})).collect();
    let phase = benchmark::phase_for_agents(mids, o, false, gold).await?;
    let stats: Vec<_> = unique.iter().map(|m| m.stats_json()).collect();
    Ok(json!({"mode":mode,"shared":shared,"adaptive":adaptive,"config":config(mode,o.seed),
        "training_wall_seconds":training_wall,"training_database":training_database,"training":training,
        "phase":phase,"total_database":db.meter.snap(),"cold_total_wall_seconds":cold_start.elapsed().as_secs_f64(),"final_states":stats}))
}

async fn specials(url: &str, admin: &Db, pool: usize) -> Result<Value> {
    let mut sf = vec![];
    let expected =
        admin.query(QKind::Meta, "select sum(ss_net_paid) from store_sales").await?.cell(0, 0).context("empty sales sum")?.to_string();
    for enabled in [false, true] {
        let db = Arc::new(Db::connect(url, pool, true)?);
        let mid = Arc::new(
            Middle::new(db.clone(), MiddleConfig { singleflight: enabled, result_cache: false, validate_sql: false, ..Default::default() })
                .await?,
        );
        let barrier = Arc::new(tokio::sync::Barrier::new(8));
        let started = Instant::now();
        let responses = futures::future::join_all((0..8).map(|i| {
            let mid = mid.clone();
            let barrier = barrier.clone();
            async move {
                barrier.wait().await;
                mid.run_sql(&Ctx::new(&format!("sf-{i}"), "sf", "sf"), "select sum(ss_net_paid) from store_sales").await
            }
        }))
        .await;
        for response in responses {
            ensure!(response?["result"]["rows"][0][0] == expected, "singleflight result mismatch");
        }
        sf.push(json!({"enabled":enabled,"requests":8,"executed":db.meter.snap().kind(QKind::Exec).0,"merged":mid.merged(),"wall_seconds":started.elapsed().as_secs_f64()}));
    }
    let mut guards = vec![];
    let mut mids = vec![];
    for guard in [GuardMode::Off, GuardMode::OnChange] {
        let db = Arc::new(Db::connect(url, pool, true)?);
        let mid = Middle::new(db, MiddleConfig { guard, result_cache: false, version_ttl_ms: 0, ..Default::default() }).await?;
        mid.call_tool(&Ctx::new("guard", "guard", "guard"), "check_join", &benchmark::pair(true)).await?;
        mids.push(mid);
    }
    let gold = admin.query(QKind::Meta, "select sum(sr_return_amt) from store_returns").await?.f64(0, 0).context("empty return sum")?;
    let inserted = etl::apply_v2(admin).await?;
    for mid in &mids {
        mid.invalidate_versions();
        let ctx = Ctx::new("guard", "guard", "guard");
        let join = mid.call_tool(&ctx, "check_join", &benchmark::pair(true)).await?;
        let result = mid.run_sql(&ctx, "select sum(sr_return_amt) from store_returns").await?;
        let amount = result["result"]["rows"][0][0].as_str().and_then(|s| s.parse::<f64>().ok());
        let corrected = if mid.cfg.guard == GuardMode::OnChange {
            Some(mid.run_sql(&ctx, "select sum(sr_return_amt) from store_returns where sr_status = '完成'").await?)
        } else {
            None
        };
        guards.push(json!({"guard":mid.cfg.guard,"join":join,"unfiltered_result":result,"amount":amount,
            "relative_error_percent":amount.map(|v|(v/gold-1.0)*100.0),"corrected":corrected,"stats":mid.stats_json()}));
    }
    ensure!(sf[0]["executed"] == 8 && sf[1]["executed"] == 1, "singleflight did not coalesce exactly 8 requests; see observations");
    ensure!(guards[0]["amount"].as_f64().is_some_and(|v| v > gold), "guard-off should expose inflated amount");
    ensure!(guards[1]["unfiltered_result"]["rejected"] == true, "guard-on should reject unfiltered sum");
    ensure!(
        guards[1]["corrected"]["result"]["rows"][0][0]
            .as_str()
            .and_then(|s| s.parse::<f64>().ok())
            .is_some_and(|v| (v - gold).abs() < 0.01),
        "guard repair amount mismatch"
    );
    Ok(json!({"singleflight":sf,"guard":{"baseline_amount":gold,"inserted_rows":inserted,"cases":guards}}))
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_ablation_{}_{stamp}", std::process::id());
    let directory = format!("{out}/ablation-{stamp}");
    std::fs::create_dir_all(&directory)?;
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await?;
    let result:Result<Value>=async {
        let admin=Db::connect(isolated.as_str(),2,false)?;
        eprintln!("2×2 消融：{} 条销售，{} 个 Agent，{} 轮；主矩阵关闭 singleflight",o.rows,o.agents,o.rounds);
        admin.query(QKind::Meta,&benchmark::fixture(o.rows)).await?;
        benchmark::risk_fixture(&admin).await?;etl::setup(&admin).await?;
        let mut gold=vec![];
        for bucket in 0..8 {gold.push(admin.query(QKind::Meta,&format!("select coalesce(sum(ss_net_paid),0) from store_sales where ss_item_sk % 8={bucket}")).await?.f64(0,0).unwrap_or(0.0));}
        gold.push(admin.query(QKind::Meta,"select sum(sr_return_amt) from store_returns").await?.f64(0,0).unwrap_or(0.0));
        let gold=Arc::new(gold);
        let mut runs=vec![];
        for round in 0..o.rounds {
            for offset in 0..4 {
                let mode=MODES[(round as usize+offset)%4];
                admin.query(QKind::Meta,"select sum(ss_net_paid) from store_sales; select sum(sr_return_amt) from store_returns").await?;
                eprintln!("轮 {} / {}：准备独立状态、相同训练和混合负载",round+1,mode);
                let mut r=trial(isolated.as_str(),mode,&o,pool,gold.clone()).await?;
                r["round"]=json!(round+1);
                eprintln!("  {} 请求，正确率 {:.1}%，SQL {}，P95 {:.2} ms",r["phase"]["requests"],r["phase"]["accuracy"].as_f64().unwrap()*100.0,r["phase"]["database"]["queries"],r["phase"]["p95_ms"].as_f64().unwrap());
                std::fs::write(format!("{directory}/round-{}-{mode}.json",round+1),serde_json::to_string_pretty(&r)?)?;
                runs.push(r);
            }
        }
        eprintln!("运行专项：singleflight 开关、守护开关");
        let special=specials(isolated.as_str(),&admin,pool).await?;
        let mut report=json!({"options":o,"pool":pool,"build":if cfg!(debug_assertions){"debug"}else{"release"},
            "matrix":{"A":{"sharing":false,"feedback":false},"B":{"sharing":true,"feedback":false},"C":{"sharing":false,"feedback":true},"D":{"sharing":true,"feedback":true}},
            "methodology":{"no_sharing":"agent-local state including feedback; local reuse across sessions is retained","sharing":"global knowledge and feedback state","singleflight_main":false,"audit":"seeded candidate-level hash with 20% threshold, same across cells","guard":"OnChange in all cells","order":"rotated Latin order; use rounds multiple of 4 for balanced positions","transport":"in-process scripted agents, no real LLM calls","training":"same logical calls per agent; measured separately and included in cold totals","seed":o.seed,"cache":"new adapter state each cell; PostgreSQL cache warmed, OS cache not flushed"},"runs":runs,"specials":special});
        report["summary"]=summary(&report);
        report["contrasts"]=contrasts(&report);
        Ok(report)
    }.await;
    let cleanup = root.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    match result {
        Ok(mut report) => {
            report["database_cleaned_up"] = json!(cleanup.is_ok());
            std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
            std::fs::write(format!("{directory}/report.md"), markdown(&report))?;
            println!("消融报告：{directory}/report.md");
            cleanup.context("消融数据库清理失败")?;
            ensure!(
                report["runs"].as_array().unwrap().iter().all(|r| r["phase"]["accuracy"] == 1.0),
                "主矩阵存在不符合预期的结果，检查逐请求证据"
            );
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

fn summary(report: &Value) -> Value {
    let mut out = serde_json::Map::new();
    for mode in MODES {
        let runs: Vec<_> = report["runs"].as_array().unwrap().iter().filter(|r| r["mode"] == mode).collect();
        let phases: Vec<_> = runs.iter().map(|r| &r["phase"]).collect();
        let events: Vec<_> = phases.iter().flat_map(|p| p["events"].as_array().unwrap()).collect();
        let times: Vec<_> = events.iter().map(|e| e["latency_ms"].as_f64().unwrap()).collect();
        let sum = |key: &str| phases.iter().map(|p| p["database"][key].as_f64().unwrap()).sum::<f64>();
        let wall: f64 = phases.iter().map(|p| p["wall_seconds"].as_f64().unwrap()).sum();
        out.insert(mode.into(),json!({"requests":events.len(),"correct":events.iter().filter(|e|e["correct"]==true).count(),
            "p95_ms":benchmark::percentile(&times,0.95),"wall_seconds":wall,"throughput":events.len() as f64/wall,
            "sql":sum("queries"),"db_ms":sum("db_ms"),"cold_sql":runs.iter().map(|r|r["total_database"]["queries"].as_u64().unwrap()).sum::<u64>(),
            "cold_db_ms":runs.iter().map(|r|r["total_database"]["db_ms"].as_f64().unwrap()).sum::<f64>()}));
    }
    Value::Object(out)
}

fn contrasts(report: &Value) -> Value {
    let mut output = vec![];
    for (base, target, label) in [
        ("A", "B", "共享收益 B−A"),
        ("A", "C", "反馈收益 C−A"),
        ("B", "D", "共享后的反馈收益 D−B"),
        ("C", "D", "反馈后的共享收益 D−C"),
        ("A", "D", "整体收益 D−A"),
    ] {
        let mut rows = vec![];
        for round in 1..=report["options"]["rounds"].as_u64().unwrap() {
            let find = |m: &str| report["runs"].as_array().unwrap().iter().find(|r| r["mode"] == m && r["round"] == round).unwrap();
            let a = &find(base)["phase"];
            let b = &find(target)["phase"];
            let av = a["database"]["db_ms"].as_f64().unwrap();
            let bv = b["database"]["db_ms"].as_f64().unwrap();
            rows.push(json!({"round":round,"db_ms_delta":bv-av,"db_cost_reduction_percent":(av-bv)/av*100.0,
                "sql_delta":b["database"]["queries"].as_i64().unwrap()-a["database"]["queries"].as_i64().unwrap()}));
        }
        output.push(json!({"label":label,"baseline":base,"target":target,"paired_rounds":rows}));
    }
    let interactions: Vec<_> = (1..=report["options"]["rounds"].as_u64().unwrap())
        .map(|round| {
            let cost = |mode: &str| {
                report["runs"].as_array().unwrap().iter().find(|r| r["mode"] == mode && r["round"] == round).unwrap()["phase"]["database"]
                    ["db_ms"]
                    .as_f64()
                    .unwrap()
            };
            json!({"round":round,"interaction_cost_ms":cost("D")-cost("B")-cost("C")+cost("A")})
        })
        .collect();
    json!({"paired_effects":output,"interaction":interactions,"interpretation":"delta=target-baseline; lower cost is better; negative interaction means extra saving beyond additive effects; rounds are descriptive, not significance tests"})
}

fn markdown(r: &Value) -> String {
    let mut s=format!("# 2×2 消融与专项测试\n\n配置：`{}`，构建：{}。\n\n|组别|跨 Agent 共享|检查顺序|\n|---|---|---|\n|A 基线|否|固定|\n|B 只加共享|是|固定|\n|C 只加反馈|否|自反馈|\n|D 组合方案|是|自反馈|\n\n",r["options"],r["build"]);
    s.push_str("## 指标\n\n主矩阵关闭 singleflight；四组均使用守护、结果缓存与相同的候选级审计规则。A/C 保留每个 Agent 自己的跨会话记忆，经验与反馈不跨 Agent 传播。反馈为内置反馈排序，不调用 LLM。\n\n|组别|请求|符合预期|P95 ms|请求/秒|测量 SQL|测量 DB ms|含训练 SQL|含训练 DB ms|\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n");
    for mode in MODES {
        let v = &r["summary"][mode];
        s.push_str(&format!(
            "|{mode}|{}|{}|{:.2}|{:.2}|{}|{:.2}|{}|{:.2}|\n",
            v["requests"],
            v["correct"],
            v["p95_ms"].as_f64().unwrap(),
            v["throughput"].as_f64().unwrap(),
            v["sql"],
            v["db_ms"].as_f64().unwrap(),
            v["cold_sql"],
            v["cold_db_ms"].as_f64().unwrap()
        ));
    }
    s.push_str("\n## 成对消融\n\nΔ=目标组−基线组，成本指标为负表示减少。降幅=(基线−目标)/基线；正数为节约，负数为退化。报告均值和每轮范围，不作显著性声明。\n\n|对比|平均 DB 成本降幅|最小—最大|平均 SQL Δ|\n|---|---:|---:|---:|\n");
    for c in r["contrasts"]["paired_effects"].as_array().unwrap() {
        let pairs = c["paired_rounds"].as_array().unwrap();
        let values: Vec<_> = pairs.iter().map(|v| v["db_cost_reduction_percent"].as_f64().unwrap()).collect();
        s.push_str(&format!(
            "|{}|{:.2}%|{:.2}% — {:.2}%|{:.2}|\n",
            c["label"].as_str().unwrap(),
            values.iter().sum::<f64>() / values.len() as f64,
            values.iter().copied().fold(f64::INFINITY, f64::min),
            values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
            pairs.iter().map(|v| v["sql_delta"].as_f64().unwrap()).sum::<f64>() / pairs.len() as f64
        ));
    }
    s.push_str("\n## 交互项\n\n成本交互项 = D−B−C+A。负数才表示超出简单相加的额外节约；D 优于 A 本身不能证明协同。\n\n|轮次|成本交互项 ms|\n|---|---:|\n");
    for x in r["contrasts"]["interaction"].as_array().unwrap() {
        s.push_str(&format!("|{}|{:.2}|\n", x["round"], x["interaction_cost_ms"].as_f64().unwrap()));
    }
    s.push_str("\n## 专项 1：并发合并\n\n关闭结果缓存，8 个 Agent 同步执行相同真实汇总；只切换 singleflight。\n\n|启用|请求|实际 SQL 执行|合并|墙钟秒|\n|---|---:|---:|---:|---:|\n");
    for x in r["specials"]["singleflight"].as_array().unwrap() {
        s.push_str(&format!(
            "|{}|{}|{}|{}|{:.3}|\n",
            x["enabled"],
            x["requests"],
            x["executed"],
            x["merged"],
            x["wall_seconds"].as_f64().unwrap()
        ));
    }
    s.push_str(&format!(
        "\n## 专项 2：守护\n\n正确金额为 {}；ETL 增加 {} 条状态行。关闭结果缓存避免旧金额掩盖错误，仅比较守护开关。\n\n```json\n{}\n```\n",
        r["specials"]["guard"]["baseline_amount"],
        r["specials"]["guard"]["inserted_rows"],
        serde_json::to_string_pretty(&r["specials"]["guard"]["cases"]).unwrap()
    ));
    s.push_str("\n## 复现与解释边界\n\n- 四组共用同样大小的数据库池、数据、任务序列；A/C 的每 Agent 状态独立，B/D 全局共享。共享收益包含画像、关联、检查、结果、版本读取及反馈经验的复用。\n- 相同逻辑训练对所有 Agent 执行，测量指标不含训练；含训练成本另列，避免隐藏不共享组的重复学习成本。\n- 主矩阵只用稳定 v1 数据，ETL 和 singleflight 分别做专项，不混入两个主因素。\n- 审计按固定种子与候选签名抽取，阈值20%；同一候选的开关不因模式、先失败检查或并发调度改变。实际有限候选抽中比例不保证恰为20%。\n- 每轮轮换顺序；建议轮数为4的倍数以平衡位置。数据库预热但不清空 OS 缓存。毫秒值仍受调度影响。\n- 使用并发脚本 Agent 直接调用工具层，不包含 HTTP、真实 LLM 或 token 成本。D 是共享+内置反馈，不等同于已证明真实模型收益。\n- 逐轮 JSON 保留请求输入、预期、实际结果与检查轨迹；source 区分执行、复用、合并。正确拒绝也计作符合预期。\n");
    s
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn factorial_cells_hold_other_controls_constant() {
        for mode in MODES {
            let c = config(mode, 42);
            assert!(!c.singleflight);
            assert!(c.feedback);
            assert_eq!(c.guard, GuardMode::OnChange);
            assert_eq!(c.audit_seed, Some(42));
            assert_eq!(c.scope == Scope::Global, matches!(mode, "B" | "D"));
        }
    }

    #[test]
    fn contrast_signs_match_cost_savings_and_interaction() {
        let runs: Vec<_> = [("A", 100), ("B", 60), ("C", 80), ("D", 30)]
            .into_iter()
            .map(|(mode, cost)| json!({"round":1,"mode":mode,"phase":{"database":{"db_ms":cost,"queries":cost}}}))
            .collect();
        let values = contrasts(&json!({"options":{"rounds":1},"runs":runs}));
        assert_eq!(values["paired_effects"][0]["paired_rounds"][0]["db_ms_delta"], -40.0);
        assert_eq!(values["paired_effects"][0]["paired_rounds"][0]["db_cost_reduction_percent"], 40.0);
        assert_eq!(values["interaction"][0]["interaction_cost_ms"], -10.0);
    }
}
