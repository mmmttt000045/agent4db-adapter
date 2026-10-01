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
        Change::Mirror => [V0, V1, V1, V0],
    }
}

/// M2 / M3 换上指定的退货表过滤（M2 在事实表上，M3 在与退货的关联上），用于逐个评估修复候选。
fn with_returns_filter(id: &str, m: &Metric, f: &str) -> Metric {
    let mut m = m.clone();
    if id == "M2" {
        m.filters.insert("store_returns".into(), f.into());
    } else if let Some(j) = m.joins.iter_mut().find(|j| j.right == "store_returns") {
        j.filters.insert("store_returns".into(), f.into());
    }
    m
}

/// 受限修复的语义歧义（实验，只记录不断言答对）。备份副本场景下 sr_source = 'primary' 与 'backup' 都能恢复
/// 退货粒度且不丢键，学习期（2001-03）不受更正影响，两者都能通过 G8；只有 2002 年的新问题能分出对错。
/// 记录 MAVRA 两种维护方式实际选出的过滤与回答，以及两个候选在修复判定、G8 与新问题上的逐项结果。
async fn repair_ambiguity(url: &str) -> Result<Value> {
    let admin = Db::connect(url, 2, false)?;
    let rows = std::env::var("AGENTDB_SCENARIO_ROWS").ok().and_then(|v| v.parse().ok()).unwrap_or(200_000);
    admin.query(QKind::Meta, &metricbench::fixture(rows)).await?;
    etl::setup(&admin).await?;
    scenario::setup(&admin).await?;
    let v1 = scenario::fingerprint(&admin).await?;
    let ch = Change::Mirror;
    let learn = Period::month(2001, 3);
    let asks = [
        Ask::Single { period: Period::month(2002, 9) },
        Ask::Single { period: Period::month(2002, 5) },
        Ask::RankMonth { year: 2002 },
        Ask::Single { period: Period::month(2001, 6) },
    ];
    let gold = |id: &str, a: &Ask| match a {
        Ask::Single { period } => metricbench::gold_period(id, period),
        Ask::RankMonth { year } => metricbench::gold_rank(id, *year),
        Ask::Diff { .. } => unreachable!(),
    };
    let returns: Vec<(&str, Metric)> = seeded_metrics().into_iter().filter(|(id, _)| matches!(*id, "M2" | "M3")).collect();
    let answer = |sql: String| {
        let admin = &admin;
        async move { Ok::<_, anyhow::Error>(admin.query(QKind::Meta, &sql).await?.cell(0, 0).unwrap_or("NULL").to_string()) }
    };
    let same = |a: &Ask, x: &str, y: &str| {
        let dec = if matches!(a, Ask::RankMonth { .. }) { 0 } else { 2 };
        metric::same_value(&metric::parse_answer(x), &metric::parse_answer(y), dec)
    };
    let mut runs = vec![];
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
        for (id, m) in &returns {
            let v = mid.seed_metric(&seed, m.clone(), Ask::Single { period: learn }, 2, &metricbench::gold_period(id, &learn)).await?;
            ensure!(v["promoted"] == true, "{id} 未晋升：{v}");
        }
        ch.apply_truth(&admin).await?;
        let mut expect = BTreeMap::new();
        for (id, _) in &returns {
            for (i, a) in asks.iter().enumerate() {
                expect.insert((*id, i), answer(gold(id, a)).await?);
            }
        }
        ch.apply_hidden(&admin).await?;
        mid.invalidate_versions();
        let ctx = Ctx::new("B", ch.name(), "use");
        let mut served = vec![];
        for (id, m) in &returns {
            let v = mid.use_metric(&ctx, &format!("metric:{}", m.name)).await?;
            let mut answers = vec![];
            if v["status"] == "valid" {
                let got: Metric = serde_json::from_value(v["metric"].clone())?;
                for (i, a) in asks.iter().enumerate() {
                    let value = answer(metric::compile(&got, a)?).await?;
                    answers.push(json!({"ask": a, "value": value, "gold": expect[&(*id, i)], "ok": same(a, &value, &expect[&(*id, i)])}));
                }
                served.push(json!({"metric": id, "status": "valid", "revision": v["revision"], "filters": got.filters,
                                   "join_filters": got.joins.iter().map(|j| &j.filters).collect::<Vec<_>>(), "answers": answers}));
            } else {
                served.push(json!({"metric": id, "status": v["status"]}));
            }
        }
        runs.push(json!({"maint": maint.name(), "served": served, "events": mid.take_metric_events()}));
        ch.reset(&admin).await?;
        scenario::ensure_v1(&admin, &v1, ch.name()).await?;
    }
    // 两个候选逐项评估：修复判定（每键恰一行、不丢键）、G8（学习期规范 SQL 与判题查询一致）、新问题是否答对
    ch.apply_truth(&admin).await?;
    let mut expect = BTreeMap::new();
    for (id, _) in &returns {
        for (i, a) in asks.iter().enumerate() {
            expect.insert((*id, i), answer(gold(id, a)).await?);
        }
    }
    ch.apply_hidden(&admin).await?;
    let total = answer("select count(distinct (sr_ticket_number, sr_item_sk)) from store_returns".into()).await?;
    let mut candidates = vec![];
    for v in ["primary", "backup"] {
        let f = format!("sr_source = '{v}'");
        let r = admin
            .query(QKind::Meta, &format!("select count(*), count(distinct (sr_ticket_number, sr_item_sk)) from store_returns where {f}"))
            .await?;
        let (n, k) = (r.cell(0, 0).unwrap_or("0").to_string(), r.cell(0, 1).unwrap_or("0").to_string());
        let mut per_metric = vec![];
        for (id, m) in &returns {
            let mm = with_returns_filter(id, m, &f);
            let g8_expect = answer(metricbench::gold_period(id, &learn)).await?;
            let g8_got = answer(metric::compile(&mm, &Ask::Single { period: learn })?).await?;
            let learn_ask = Ask::Single { period: learn };
            let mut new_asks = vec![];
            for (i, a) in asks.iter().enumerate() {
                let value = answer(metric::compile(&mm, a)?).await?;
                new_asks.push(json!({"ask": a, "value": value, "gold": expect[&(*id, i)], "ok": same(a, &value, &expect[&(*id, i)])}));
            }
            per_metric
                .push(json!({"metric": id, "g8": {"value": g8_got, "judge": g8_expect, "pass": same(&learn_ask, &g8_got, &g8_expect)},
                                   "asks": new_asks}));
        }
        candidates.push(json!({"filter": f, "rows": n, "keys": k, "total_keys": total, "repair_test_passes": n == k && k == total,
                               "metrics": per_metric}));
    }
    ch.reset(&admin).await?;
    scenario::ensure_v1(&admin, &v1, ch.name()).await?;
    let variant = repair_ambiguity_precolumn(url, &admin, &returns, learn, &asks).await?;
    Ok(json!({"rows": rows, "change": ch.describe(), "learn": learn, "runs": runs, "candidates": candidates,
              "precolumn_variant": variant}))
}

/// 变体：来源列 sr_source 在学习前就存在（全为 primary），排除目录未刷新带来的偶然拦截。
/// 比较三种 G8 参照：未预见（学习参照 SQL 不含 sr_source，在当前数据上重算）、已预见（参照含 sr_source = 'primary'，
/// 相当于本文基准中预先写入 sr_status / ss_is_current 的判题 SQL）、存档答案（学习时的答案值）。
/// 对前两种参照各跑一次条件级维护，记录 MAVRA 实际发布的过滤。
async fn repair_ambiguity_precolumn(url: &str, admin: &Db, returns: &[(&str, Metric)], learn: Period, asks: &[Ask]) -> Result<Value> {
    let answer =
        |sql: String| async move { Ok::<_, anyhow::Error>(admin.query(QKind::Meta, &sql).await?.cell(0, 0).unwrap_or("NULL").to_string()) };
    let same = |a: &Ask, x: &str, y: &str| {
        let dec = if matches!(a, Ask::RankMonth { .. }) { 0 } else { 2 };
        metric::same_value(&metric::parse_answer(x), &metric::parse_answer(y), dec)
    };
    let gold = |id: &str, a: &Ask| match a {
        Ask::Single { period } => metricbench::gold_period(id, period),
        Ask::RankMonth { year } => metricbench::gold_rank(id, *year),
        Ask::Diff { .. } => unreachable!(),
    };
    // 预见来源列的参照：在退货表上多一个 sr_source = 'primary'
    let anticipated = |sql: String| sql.replace("r.sr_status = '完成'", "r.sr_status = '完成' and r.sr_source = 'primary'");
    admin
        .query(QKind::Meta, "alter table store_returns add column sr_source varchar(10) not null default 'primary'; analyze store_returns")
        .await?;
    let stored: BTreeMap<&str, String> = {
        let mut m = BTreeMap::new();
        for (id, _) in returns {
            m.insert(*id, answer(metricbench::gold_period(id, &learn)).await?);
        }
        m
    };
    // 每次写入后等 DML 计数上报，保证版本变化能被维护感知
    let before =
        || async { Ok::<_, anyhow::Error>(crate::catalog::versions(admin).await?.get("store_returns").map(|v| v.dml).unwrap_or(0)) };
    let settle = |b: i64| async move {
        admin.query(QKind::Meta, "select pg_stat_force_next_flush(); analyze store_returns").await?;
        etl::wait_table_stats(admin, "store_returns", b).await
    };
    let apply = || async {
        let b = before().await?;
        admin
            .execute(
                "update store_returns set sr_return_amt = sr_return_amt - 1 where sr_ticket_number % 10 = 3 and sr_returned_date_sk >= 732",
            )
            .await?;
        settle(b).await
    };
    let hide = || async {
        let b = before().await?;
        admin
            .execute(
                "insert into store_returns (sr_returned_date_sk, sr_item_sk, sr_ticket_number, sr_return_quantity, sr_return_amt, \
                 sr_return_tax, sr_fee, sr_net_loss, sr_status, sr_source) \
                 select sr_returned_date_sk, sr_item_sk, sr_ticket_number, sr_return_quantity, \
                        sr_return_amt + case when sr_ticket_number % 10 = 3 and sr_returned_date_sk >= 732 then 1 else 0 end, \
                        sr_return_tax, sr_fee, sr_net_loss, sr_status, 'backup' from store_returns where sr_source = 'primary'",
            )
            .await?;
        settle(b).await
    };
    let undo = || async {
        let b = before().await?;
        admin.execute("delete from store_returns where sr_source = 'backup'").await?;
        admin
            .execute(
                "update store_returns set sr_return_amt = sr_return_amt + 1 where sr_ticket_number % 10 = 3 and sr_returned_date_sk >= 732",
            )
            .await?;
        settle(b).await
    };
    let mut runs = vec![];
    for (oracle, use_anticipated) in [("unanticipated", false), ("anticipated", true)] {
        let db = Arc::new(Db::connect(url, 4, true)?);
        let cfg = MiddleConfig { version_ttl_ms: 0, metric_maint: Maint::Condition, cond_reuse: true, ..Default::default() };
        let mid = Middle::new(db, cfg).await?;
        let seed = Ctx::new("A", "seed", "seed");
        for (id, m) in returns {
            let judge = metricbench::gold_period(id, &learn);
            let judge = if use_anticipated { anticipated(judge) } else { judge };
            let v = mid.seed_metric(&seed, m.clone(), Ask::Single { period: learn }, 2, &judge).await?;
            ensure!(v["promoted"] == true, "{id} 未晋升：{v}");
        }
        apply().await?;
        let mut expect = BTreeMap::new();
        for (id, _) in returns {
            for (i, a) in asks.iter().enumerate() {
                expect.insert((*id, i), answer(gold(id, a)).await?);
            }
        }
        hide().await?;
        mid.invalidate_versions();
        let ctx = Ctx::new("B", "mirror-pre", "use");
        let mut served = vec![];
        for (id, m) in returns {
            let v = mid.use_metric(&ctx, &format!("metric:{}", m.name)).await?;
            if v["status"] == "valid" {
                let got: Metric = serde_json::from_value(v["metric"].clone())?;
                let mut oks = vec![];
                for (i, a) in asks.iter().enumerate() {
                    let value = answer(metric::compile(&got, a)?).await?;
                    oks.push(same(a, &value, &expect[&(*id, i)]));
                }
                served.push(json!({"metric": id, "status": "valid", "revision": v["revision"], "filters": got.filters,
                                   "join_filters": got.joins.iter().map(|j| &j.filters).collect::<Vec<_>>(), "asks_ok": oks}));
            } else {
                served.push(json!({"metric": id, "status": v["status"]}));
            }
        }
        let events: Vec<Value> = mid.take_metric_events().into_iter().filter(|e| e["event"] != "maintenance").collect();
        runs.push(json!({"oracle": oracle, "served": served, "events": events}));
        undo().await?;
    }
    // 三种 G8 参照下两个候选各自是否通过
    apply().await?;
    hide().await?;
    let mut candidates = vec![];
    for v in ["primary", "backup"] {
        let f = format!("sr_source = '{v}'");
        let mut per = vec![];
        for (id, m) in returns {
            let got = answer(metric::compile(&with_returns_filter(id, m, &f), &Ask::Single { period: learn })?).await?;
            let rerun = answer(metricbench::gold_period(id, &learn)).await?;
            let rerun_anticipated = answer(anticipated(metricbench::gold_period(id, &learn))).await?;
            let la = Ask::Single { period: learn };
            per.push(json!({"metric": id, "canonical": got,
                            "g8_unanticipated": same(&la, &got, &rerun), "g8_anticipated": same(&la, &got, &rerun_anticipated),
                            "g8_stored_answer": same(&la, &got, &stored[id])}));
        }
        candidates.push(json!({"filter": f, "metrics": per}));
    }
    undo().await?;
    admin.query(QKind::Meta, "alter table store_returns drop column sr_source; analyze store_returns").await?;
    Ok(json!({"runs": runs, "candidates": candidates}))
}

#[tokio::test]
#[ignore = "experiment; requires AGENTDB_TEST_URL and PostgreSQL 15+ with CREATE DATABASE permission"]
async fn postgres_repair_ambiguity() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("设置 AGENTDB_TEST_URL 为测试服务器连接串")?;
    let admin = Db::connect(&url, 1, false)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_repair_{}_{unique}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    admin.query(QKind::Meta, &format!("create database {name}")).await.context("无法创建独立测试库")?;
    let result = tokio::time::timeout(Duration::from_secs(3600), repair_ambiguity(test_url.as_str())).await;
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let out = format!("results/repair-ambiguity-{unique}");
    std::fs::create_dir_all(&out)?;
    let report = match &result {
        Ok(Ok(v)) => v.clone(),
        Ok(Err(e)) => json!({"status": "failed", "error": format!("{e:#}")}),
        Err(_) => json!({"status": "failed", "error": "实验超时"}),
    };
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("修复歧义实验报告：{out}/report.json；测试库清理：{}", cleanup.is_ok());
    cleanup.context("测试库清理失败")?;
    result.context("实验超时")??;
    Ok(())
}

async fn scenarios(url: &str) -> Result<Value> {
    let admin = Db::connect(url, 2, false)?;
    // 默认 2 万行；AGENTDB_SCENARIO_ROWS 可改为评测规模（如 1000000）检查阈值、回滚与耗时
    let rows = std::env::var("AGENTDB_SCENARIO_ROWS").ok().and_then(|v| v.parse().ok()).unwrap_or(20_000);
    admin.query(QKind::Meta, &metricbench::fixture(rows)).await?;
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
            let events = mid.take_metric_events();
            let t = std::time::Instant::now();
            ch.reset(&admin).await?;
            scenario::ensure_v1(&admin, &v1, ch.name()).await?;
            mid.restore(&checkpoint).await?;
            out.push(json!({"maint": maint.name(), "change": ch.name(), "rows": [truth, hidden], "got": got, "want": want,
                            "served": served, "events": events, "reset_seconds": t.elapsed().as_secs_f64()}));
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
    let result = tokio::time::timeout(Duration::from_secs(3600), scenarios(test_url.as_str())).await;
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
