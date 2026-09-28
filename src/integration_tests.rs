//! Opt-in PostgreSQL + HTTP + mock optimizer integration test.
//! Creates a uniquely named database, never loads fixtures into the supplied database.

use crate::db::{Db, QKind};
use crate::llm::Provider;
use crate::middle::{Middle, MiddleConfig};
use crate::optimizer::Optimizer;
use crate::{etl, server};
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
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

async fn exercise(url: &str, out: &str) -> Result<Value> {
    let admin = Arc::new(Db::connect(url, 2, false)?);
    admin.query(QKind::Meta, include_str!("../data/mock_fixture.sql")).await?;
    etl::setup(&admin).await?;
    let db = Arc::new(Db::connect(url, 4, true)?);
    let mid = Arc::new(Middle::new(db.clone(), MiddleConfig { version_ttl_ms: 0, ..Default::default() }).await?);
    let optimizer = Arc::new(Optimizer::new(Provider::Mock, out)?);
    // Reserve an ephemeral address briefly; report a binding failure through readiness timeout.
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    let addr = listener.local_addr()?;
    drop(listener);
    let server_mid = mid.clone();
    let server_task = tokio::spawn(async move { server::serve(server_mid, &addr.to_string(), Some(optimizer), Some(1), true).await });
    let base = format!("http://{addr}");
    let http = reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(10)).build()?;
    let result = async {
        tokio::time::timeout(Duration::from_secs(10), async {
            loop {
                if http.get(format!("{base}/v1/tools")).send().await.is_ok() { break; }
                tokio::time::sleep(Duration::from_millis(50)).await;
            }
        }).await.context("HTTP 服务未启动")?;
        let response = http.post(format!("{base}/v1/optimizer/propose")).send().await?;
        ensure!(response.status() == 400, "样本不足时应拒绝生成策略");
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
        let applied: Value = tokio::time::timeout(Duration::from_secs(10), async {
            loop {
                let state: Value = http.get(format!("{base}/v1/optimizer")).send().await?.json().await?;
                if state["state"]["active"].is_u64() { return Ok::<Value, anyhow::Error>(state); }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }).await.context("自动应用策略超时")??;
        tokio::time::sleep(Duration::from_millis(1200)).await;
        let idle: Value = http.get(format!("{base}/v1/optimizer")).send().await?.json().await?;
        ensure!(idle["state"]["proposals"] == applied["state"]["proposals"], "没有新增反馈时不应重复生成策略");
        let rollback = http.post(format!("{base}/v1/optimizer/rollback")).send().await?;
        ensure!(rollback.status().is_success(), "回滚应成功");
        let old_id = applied["state"]["active"].as_u64().unwrap();
        let stale = http.post(format!("{base}/v1/optimizer/apply/{old_id}")).send().await?;
        ensure!(stale.status() == 400, "回滚后旧建议必须失效");

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
        Ok(json!({"status":"passed","automatic_policy":applied,"many_to_one":many_to_one,"etl_inserted":inserted,"repaired_join":repaired,"correct_sum":sum,"stats":stats}))
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
    let result = tokio::time::timeout(Duration::from_secs(90), exercise(test_url.as_str(), &out)).await;
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
