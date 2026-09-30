//! Opt-in PostgreSQL + HTTP integration test.
//! Creates a uniquely named database, never loads fixtures into the supplied database.

use crate::db::{Db, QKind};
use crate::knowledge::{Basis, EmptyRule, JoinKind, JoinRef, Metric, TimeSpec};
use crate::metric::{self, Ask, Period};
use crate::middle::{Ctx, Maint, Middle, MiddleConfig};
use crate::scenario::{self, Change};
use crate::{etl, metricbench, server};
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

async fn tool(http: &reqwest::Client, base: &str, name: &str, args: Value) -> Result<Value> {
    let response = http
        .post(format!("{base}/v1/tools/{name}"))
        .json(&json!({"agent": "mock-integration", "session": "test", "args": args}))
        .send()
        .await?;
    let status = response.status();
    let body: Value = response.json().await?;
    ensure!(status.is_success(), "{name}: {status}: {body}");
    Ok(body)
}

async fn exercise(url: &str) -> Result<Value> {
    let admin = Arc::new(Db::connect(url, 2, false)?);
    admin.query(QKind::Meta, include_str!("../data/mock_fixture.sql")).await?;
    etl::setup(&admin).await?;
    let db = Arc::new(Db::connect(url, 4, true)?);
    let mid = Arc::new(Middle::new(db.clone(), MiddleConfig { version_ttl_ms: 0, ..Default::default() }).await?);
    // Reserve an ephemeral address briefly; report a binding failure through readiness timeout.
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    let addr = listener.local_addr()?;
    drop(listener);
    let server_mid = mid.clone();
    let server_task = tokio::spawn(async move { server::serve(server_mid, &addr.to_string()).await });
    let base = format!("http://{addr}");
    let http = reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(10)).build()?;
    let result = async {
        tokio::time::timeout(Duration::from_secs(10), async {
            loop {
                if http.get(format!("{base}/v1/tools")).send().await.is_ok() { break; }
                tokio::time::sleep(Duration::from_millis(50)).await;
            }
        }).await.context("HTTP 服务未启动")?;
        ensure!(db.query(QKind::Meta, "show default_transaction_read_only").await?.cell(0, 0) == Some("on"), "查询池应只读");

        let empty = tool(&http, &base, "run_sql", json!({"sql":"select ss_item_sk from store_sales where false"})).await?;
        ensure!(empty["result"]["columns"] == json!(["ss_item_sk"]), "空结果必须保留列名");
        let upper = tool(&http, &base, "run_sql", json!({"sql":"select 'ABC' as value"})).await?;
        let lower = tool(&http, &base, "run_sql", json!({"sql":"select 'abc' as value"})).await?;
        ensure!(upper["result"]["rows"] != lower["result"]["rows"], "不同字面量不能混用缓存");
        let repeated = tool(&http, &base, "run_sql", json!({"sql":"select 'abc' as value"})).await?;
        ensure!(repeated["source"] == "reused", "相同查询应复用缓存");
        let concurrent = futures::future::join_all((0..8).map(|_| tool(
            &http, &base, "run_sql", json!({"sql":"select pg_sleep(0.1), 'concurrent' as marker"})
        ))).await;
        for response in concurrent { ensure!(response?["result"]["rows"][0][1] == "concurrent", "并发查询结果错误"); }
        ensure!(mid.stats_json()["inflight_merged"].as_u64().unwrap_or(0) > 0, "并发请求应合并");

        for (table, left_col, right_col) in [
            ("item", "ss_item_sk", "i_item_sk"),
            ("customer", "ss_customer_sk", "c_customer_sk"),
            ("warehouse", "ss_warehouse_sk", "w_warehouse_sk"),
        ] {
            let v = tool(&http, &base, "check_join", json!({"left":"store_sales","right":table,"on":[[left_col,right_col]]})).await?;
            ensure!(v["valid"] == true, "合法关联失败：{v}");
        }
        let many_to_one = tool(&http, &base, "check_join", json!({"left":"store_sales","right":"date_dim","on":[["ss_sold_date_sk","d_date_sk"]]})).await?;
        ensure!(many_to_one["valid"] == true, "重复左键的一对多侧关联不应被误判：{many_to_one}");

        let pair = json!({"left":"store_returns","right":"store_sales","on":[["sr_ticket_number","ss_ticket_number"],["sr_item_sk","ss_item_sk"]]});
        let before = tool(&http, &base, "check_join", pair.clone()).await?;
        ensure!(before["valid"] == true, "v1 复合键关联应通过");
        let inserted = etl::apply_v2(&admin).await?;
        ensure!(inserted == 2, "ETL 应新增两条状态行，实际 {inserted}");
        mid.invalidate_versions();
        let repaired = tool(&http, &base, "check_join", pair).await?;
        ensure!(repaired["valid"] == true, "v2 应修复关联粒度：{repaired}");
        ensure!(repaired["path"]["filters"]["store_returns"].as_str().is_some_and(|f| f.contains("完成")), "应恢复完成状态粒度：{repaired}");
        let rejected = tool(&http, &base, "run_sql", json!({"sql":"select sum(sr_return_amt) from store_returns"})).await?;
        ensure!(rejected["rejected"] == true, "缺少状态过滤的汇总必须被拦截");
        let sum = tool(&http, &base, "run_sql", json!({"sql":"select sum(sr_return_amt) from store_returns where sr_status = '完成'"})).await?;
        ensure!(sum["result"]["rows"][0][0] == "100.00", "修复后的汇总应为 100：{sum}");
        let stats = mid.stats_json();
        ensure!(stats["guard_fails"].as_u64().unwrap_or(0) >= 1, "应观测到守卫失败");
        ensure!(stats["repairs"].as_u64().unwrap_or(0) >= 1, "应观测到粒度修复");
        Ok(json!({"status":"passed","many_to_one":many_to_one,"etl_inserted":inserted,"repaired_join":repaired,"correct_sum":sum,"stats":stats}))
    }.await;
    server_task.abort();
    let _ = server_task.await;
    result
}

#[tokio::test]
#[ignore = "requires AGENTDB_TEST_URL and PostgreSQL 15+ with CREATE DATABASE permission"]
async fn postgres_http_mock_lifecycle() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("设置 AGENTDB_TEST_URL 为测试服务器连接串")?;
    let admin = Db::connect(&url, 1, false)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_mock_{}_{unique}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    let out = format!("results/mock-{unique}");
    admin.query(QKind::Meta, &format!("create database {name}")).await.context("无法创建独立测试库")?;
    let result = tokio::time::timeout(Duration::from_secs(90), async { exercise(test_url.as_str()).await }).await;
    // The generated identifier contains only ASCII letters, digits and underscores.
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let report = match &result {
        Ok(Ok(v)) => v.clone(),
        Ok(Err(e)) => json!({"status":"failed","error":format!("{e:#}")}),
        Err(_) => json!({"status":"failed","error":"integration test timed out"}),
    };
    std::fs::create_dir_all(&out)?;
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("Mock integration report: {out}/report.json; database cleanup: {}", cleanup.is_ok());
    cleanup.context("测试库清理失败")?;
    result.context("集成测试超时")??;
    Ok(())
}

// ───────────────────────── 数据变化场景：不调用 LLM 的维护预期 ─────────────────────────

fn seeded_metrics() -> Vec<(&'static str, Metric)> {
    let time = |col: &str, role: &str| {
        Some(TimeSpec {
            role: role.into(),
            fact_col: col.into(),
            dim: "date_dim".into(),
            dim_col: "d_date_sk".into(),
            grain: "month".into(),
            loss_ratio: 0.0,
        })
    };
    let join = |right: &str, on: &[(&str, &str)], kind: JoinKind| JoinRef {
        key: String::new(),
        left: "store_sales".into(),
        right: right.into(),
        on: on.iter().map(|(l, r)| (l.to_string(), r.to_string())).collect(),
        kind,
        filters: BTreeMap::new(),
        cardinality: String::new(),
        loss_ratio: 0.0,
        revision: 0,
    };
    let base = |name: &str, fact: &str, measure: &str, grain: &[&str]| Metric {
        name: name.into(),
        aliases: vec![],
        definition: name.into(),
        fact: fact.into(),
        measure: measure.into(),
        grain: grain.iter().map(|c| c.to_string()).collect(),
        time: None,
        joins: vec![],
        filters: BTreeMap::new(),
        empty: EmptyRule::Unspecified,
        caveats: vec![],
        examples: vec![],
        basis: Basis::None,
    };
    let sales = ["ss_ticket_number", "ss_item_sk"];
    let mut m1 = base("门店营业额", "store_sales", "sum(ss_net_paid)", &sales);
    m1.time = time("ss_sold_date_sk", "销售日");
    let mut m2 = base("门店退货金额", "store_returns", "sum(sr_return_amt)", &["sr_ticket_number", "sr_item_sk"]);
    m2.time = time("sr_returned_date_sk", "退货日");
    let mut m3 = base("门店退货率", "store_sales", "100.0 * sum(sr_return_amt) / sum(ss_net_paid)", &sales);
    m3.time = time("ss_sold_date_sk", "销售日");
    m3.joins = vec![join("store_returns", &[("ss_ticket_number", "sr_ticket_number"), ("ss_item_sk", "sr_item_sk")], JoinKind::Left)];
    let mut m5 = base("电子品类门店营业额", "store_sales", "sum(ss_net_paid)", &sales);
    m5.time = time("ss_sold_date_sk", "销售日");
    m5.joins = vec![join("item", &[("ss_item_sk", "i_item_sk")], JoinKind::Inner)];
    m5.filters.insert("item".into(), "i_category = '电子'".into());
    vec![("M1", m1), ("M2", m2), ("M3", m3), ("M5", m5)]
}

/// 条件级与定义级维护下，每个场景对 M1 / M2 / M3 / M5 的预期：valid0 = 刷新后原修订可用，valid1 = 修复后新修订可用，
/// unavailable = 撤销且不在修复范围或修复失败。金额单位变化不被任何条件覆盖（漏检边界）。
fn expected(c: Change) -> [&'static str; 4] {
    const V0: &str = "valid0";
    const V1: &str = "valid1";
    const NA: &str = "unavailable";
    match c {
        Change::Append | Change::Backfill | Change::Correct | Change::AddColumn | Change::Unit => [V0, V0, V0, V0],
        Change::Status => [V0, V1, V1, V0],
        Change::Revision => [V1, V0, V1, V1],
        Change::Duplicate | Change::LateKey => [NA, V0, NA, NA],
        Change::DimHistory => [V0, V0, V0, V1],
    }
}

async fn scenarios(url: &str) -> Result<Value> {
    let admin = Db::connect(url, 2, false)?;
    admin.query(QKind::Meta, &metricbench::fixture(20_000)).await?;
    etl::setup(&admin).await?;
    scenario::setup(&admin).await?;
    let v1 = scenario::fingerprint(&admin).await?;
    let learn = Period::month(2001, 3);
    let asks = [Ask::Single { period: Period::month(2002, 9) }, Ask::RankMonth { year: 2002 }];
    let gold = |id: &str, a: &Ask| match a {
        Ask::Single { period } => metricbench::gold_period(id, period),
        Ask::RankMonth { year } => metricbench::gold_rank(id, *year),
        Ask::Diff { .. } => unreachable!(),
    };
    let mut out = vec![];
    let mut problems = vec![];
    for maint in [Maint::Condition, Maint::Definition] {
        let db = Arc::new(Db::connect(url, 4, true)?);
        let cfg = MiddleConfig {
            name: maint.name().into(),
            version_ttl_ms: 0,
            metric_maint: maint,
            cond_reuse: maint == Maint::Condition,
            ..Default::default()
        };
        let mid = Middle::new(db, cfg).await?;
        let seed = Ctx::new("A", "seed", "seed");
        for (id, m) in seeded_metrics() {
            let v = mid.seed_metric(&seed, m, Ask::Single { period: learn }, 2, &metricbench::gold_period(id, &learn)).await?;
            ensure!(v["promoted"] == true, "{} 下 {id} 未晋升：{v}", maint.name());
        }
        let checkpoint = mid.checkpoint();
        for ch in scenario::ALL {
            let truth = ch.apply_truth(&admin).await?;
            // 标准答案在只改变数据表示的部分之前计算
            let mut expect = BTreeMap::new();
            for (id, _) in seeded_metrics() {
                for (i, a) in asks.iter().enumerate() {
                    expect.insert((id, i), admin.query(QKind::Meta, &gold(id, a)).await?.cell(0, 0).unwrap_or("NULL").to_string());
                }
            }
            let hidden = ch.apply_hidden(&admin).await?;
            mid.invalidate_versions();
            let ctx = Ctx::new("B", ch.name(), "use");
            let mut got = vec![];
            let mut served = vec![];
            for (id, m) in seeded_metrics() {
                let v = mid.use_metric(&ctx, &format!("metric:{}", m.name)).await?;
                let status = match v["status"].as_str() {
                    Some("valid") => format!("valid{}", v["revision"]),
                    Some(s) => s.to_string(),
                    None => "?".into(),
                };
                if status.starts_with("valid") {
                    let m: Metric = serde_json::from_value(v["metric"].clone())?;
                    for (i, a) in asks.iter().enumerate() {
                        let sql = metric::compile(&m, a)?;
                        let value = admin.query(QKind::Meta, &sql).await?.cell(0, 0).unwrap_or("NULL").to_string();
                        let dec = if matches!(a, Ask::RankMonth { .. }) { 0 } else { 2 };
                        let ok = metric::same_value(&metric::parse_answer(&value), &metric::parse_answer(&expect[&(id, i)]), dec);
                        served.push(json!({"metric": id, "ask": i, "value": value, "gold": expect[&(id, i)], "ok": ok}));
                        // 金额单位变化是漏检边界：此时口径仍被提供且答错是预期结果
                        if !ok && ch != Change::Unit {
                            problems.push(format!("{} {} {id}：提供的口径答错 {value} ≠ {}", maint.name(), ch.name(), expect[&(id, i)]));
                        }
                    }
                }
                got.push(status);
            }
            let want = expected(ch);
            if got != want {
                problems.push(format!("{} {}：维护结果 {got:?}，预期 {want:?}", maint.name(), ch.name()));
            }
            out.push(json!({"maint": maint.name(), "change": ch.name(), "rows": [truth, hidden], "got": got, "want": want,
                            "served": served, "events": mid.take_metric_events()}));
            ch.reset(&admin).await?;
            scenario::ensure_v1(&admin, &v1, ch.name()).await?;
            mid.restore(&checkpoint).await?;
        }
    }
    let report = json!({"status": if problems.is_empty() { "passed" } else { "failed" }, "problems": problems, "runs": out});
    ensure!(problems.is_empty(), "场景预期不符：{problems:#?}\n{}", serde_json::to_string_pretty(&report)?);
    Ok(report)
}

#[tokio::test]
#[ignore = "requires AGENTDB_TEST_URL and PostgreSQL 15+ with CREATE DATABASE permission"]
async fn postgres_change_scenarios() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("设置 AGENTDB_TEST_URL 为测试服务器连接串")?;
    let admin = Db::connect(&url, 1, false)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_scenario_{}_{unique}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    admin.query(QKind::Meta, &format!("create database {name}")).await.context("无法创建独立测试库")?;
    let result = tokio::time::timeout(Duration::from_secs(600), scenarios(test_url.as_str())).await;
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let out = format!("results/scenario-test-{unique}");
    std::fs::create_dir_all(&out)?;
    let report = match &result {
        Ok(Ok(v)) => v.clone(),
        Ok(Err(e)) => json!({"status": "failed", "error": format!("{e:#}")}),
        Err(_) => json!({"status": "failed", "error": "场景测试超时"}),
    };
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("场景测试报告：{out}/report.json；测试库清理：{}", cleanup.is_ok());
    cleanup.context("测试库清理失败")?;
    result.context("场景测试超时")??;
    Ok(())
}
