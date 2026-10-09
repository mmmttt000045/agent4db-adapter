//! Opt-in PostgreSQL + HTTP integration test.
//! Creates a uniquely named database, never loads fixtures into the supplied database.

use crate::db::{Db, QKind};
use crate::knowledge::{Basis, EmptyRule, JoinKind, JoinRef, Metric, TimeSpec, TimeStrategy};
use crate::metric::{self, Ask, Period};
use crate::middle::{Checkpoint, Ctx, Maint, Middle, MiddleConfig};
use crate::scenario::{self, Change};
use crate::{catalog, etl, metricbench, server};
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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
        let listed: Value = http.get(format!("{base}/v1/tools")).send().await?.json().await?;
        let listed = listed.as_array().context("工具清单应为数组")?;
        ensure!(listed.iter().any(|t| t["name"] == "find_metric"), "工具清单应包含 find_metric");
        ensure!(
            listed.iter().any(|t| t["name"] == "run_sql" && t["schema"]["properties"].get("metrics").is_some()),
            "工具清单里的 run_sql 应带 metrics 声明"
        );
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

async fn orientation_counterexample(url: &str) -> Result<Value> {
    let admin = Arc::new(Db::connect(url, 2, false)?);
    admin
        .query(
            QKind::Meta,
            "create table facts (f_id bigint, f_link bigint, f_amount numeric, f_date bigint, f_scope text);\
             create table details (de_id bigint, de_fact bigint);\
             create table date_dim (d_date_sk bigint, d_year integer, d_moy integer);\
             create table etl_batch_log (table_name text, batch_id integer, note text, applied_at timestamptz default now());\
             insert into facts values (1, 10, 100, 1, 'A B');\
             insert into details values (1, 10);\
             insert into date_dim values (1, 2002, 9)",
        )
        .await?;
    let raw = "select sum(f_amount) from facts join details on f_link = de_fact \
               join date_dim on f_date = d_date_sk where d_year = 2002 and d_moy = 9";
    let before = admin.query(QKind::Meta, raw).await?;
    ensure!(before.cell(0, 0) == Some("100"), "反例初始值应为 100");
    let db = Arc::new(Db::connect(url, 4, true)?);
    let mid = Middle::new(db, MiddleConfig { version_ttl_ms: 0, cond_reuse: true, ..Default::default() }).await?;
    let ctx = Ctx::new("A", "orientation", "seed");
    let on = vec![("de_fact".into(), "f_link".into())];
    let m: Metric = serde_json::from_value(json!({
        "name": "fact_amount", "definition": "每条事实的金额恰好累计一次", "fact": "facts",
        "measure": "sum(f_amount)", "grain": ["f_id"],
        "time": {"role": "event date", "fact_col": "f_date", "dim": "date_dim", "dim_col": "d_date_sk", "grain": "day"},
        "joins": [{"left": "details", "right": "facts", "on": on, "kind": "inner"}],
        "examples": [{"question": "2002-09 amount", "sql": raw}]
    }))?;
    let ask = Ask::Single { period: Period::month(2002, 9) };
    ensure!(metric::compile(&m, &ask).is_err(), "反向引用必须被规范编译拒绝");
    // The seeding harness compiles before its gates; production extraction checks the same
    // orientation in G3 before canonical compilation. Both paths must refuse publication.
    let rejection = mid.seed_metric(&ctx, m, ask, 2, "select sum(f_amount) from facts").await.unwrap_err();
    ensure!(rejection.to_string().contains("反向"), "反向引用必须被拒绝：{rejection}");
    let admission = json!({"rejected": true, "stage": "seed compilation", "reason": rejection.to_string()});
    admin.query(QKind::Meta, "insert into details values (2, 10)").await?;
    mid.invalidate_versions();
    let path = mid.check_join(&ctx, "details", "facts", &on).await?;
    ensure!(path["valid"] == true, "details→facts 的右键仍唯一，关系检查本身应通过：{path}");
    let after = admin.query(QKind::Meta, raw).await?;
    let gold = admin.query(QKind::Meta, "select sum(f_amount) from facts").await?;
    ensure!(after.cell(0, 0) == Some("200") && gold.cell(0, 0) == Some("100"), "反向关系导致事实金额翻倍");
    admin
        .query(
            QKind::Meta,
            "insert into facts values (2,20,100,1,'AB'),(2,21,100,1,'AB'),\
             (3,30,100,1,'ABC'),(4,40,100,1,'abc'),(4,41,100,1,'abc')",
        )
        .await?;
    mid.invalidate_versions();
    let mut filter_identity = vec![];
    for (i, filter, should_promote) in
        [(0, "f_scope = 'A B'", true), (1, "f_scope = 'AB'", false), (2, "f_scope = 'ABC'", true), (3, "f_scope = 'abc'", false)]
    {
        let candidate: Metric = serde_json::from_value(json!({
            "name": format!("literal_{i}"), "definition": "过滤后的事实金额", "fact": "facts",
            "measure": "sum(f_amount)", "grain": ["f_id"], "filters": {"facts": filter},
            "time": {"role": "event date", "fact_col": "f_date", "dim": "date_dim", "dim_col": "d_date_sk", "grain": "day"}
        }))?;
        let v = mid.seed_metric(&ctx, candidate, ask, 2, &format!("select sum(f_amount) from facts where {filter}")).await?;
        ensure!(v["promoted"] == should_promote, "不同字面量不能复用另一总体的唯一性结论：{v}");
        if !should_promote {
            ensure!(v["failed_gate"] == "G4", "重复键必须由 G4 拒绝：{v}");
        }
        filter_identity.push(json!({"filter": filter, "expected_promoted": should_promote, "result": v}));
    }
    Ok(json!({"status": "passed", "before": before.cell(0, 0), "after": after.cell(0, 0),
              "gold": gold.cell(0, 0), "reverse_path": path, "admission": admission, "filter_identity": filter_identity}))
}

#[tokio::test]
#[ignore = "requires AGENTDB_TEST_URL and PostgreSQL 15+ with CREATE DATABASE permission"]
async fn postgres_metric_join_orientation() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("设置 AGENTDB_TEST_URL 为测试服务器连接串")?;
    let admin = Db::connect(&url, 1, false)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_orientation_{}_{unique}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    admin.query(QKind::Meta, &format!("create database {name}")).await?;
    let result = tokio::time::timeout(Duration::from_secs(90), orientation_counterexample(test_url.as_str())).await;
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let report = match &result {
        Ok(Ok(v)) => v.clone(),
        Ok(Err(e)) => json!({"status": "failed", "error": format!("{e:#}")}),
        Err(_) => json!({"status": "failed", "error": "连接方向测试超时"}),
    };
    let out = format!("results/orientation-test-{unique}");
    std::fs::create_dir_all(&out)?;
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("连接方向测试报告：{out}/report.json；测试库清理：{}", cleanup.is_ok());
    cleanup.context("测试库清理失败")?;
    result.context("连接方向测试超时")??;
    Ok(())
}

/// 优化修订：对已发布的门店营业额尝试规则改写（期间谓词改为日期键范围），记录各门槛与配对代价证据；
/// 发布后新修订的示例 SQL 不再连接日期维度，声明旧修订的查询宽限可用并收到通知。
async fn optimization_revision(url: &str) -> Result<Value> {
    let admin = Db::connect(url, 2, false)?;
    let rows = std::env::var("AGENTDB_SCENARIO_ROWS").ok().and_then(|v| v.parse().ok()).unwrap_or(20_000);
    admin.query(QKind::Meta, &metricbench::fixture(rows)).await?;
    etl::setup(&admin).await?;
    scenario::setup(&admin).await?;
    let db = Arc::new(Db::connect(url, 4, true)?);
    let cfg = MiddleConfig {
        name: "optimize".into(),
        version_ttl_ms: 0,
        metric_maint: Maint::Condition,
        cond_reuse: true,
        optimize: true,
        ..Default::default()
    };
    let mid = Middle::new(db, cfg).await?;
    let seed = Ctx::new("A", "seed", "seed");
    let learn = Period::month(2001, 3);
    let (id, m) = seeded_metrics().into_iter().find(|(id, _)| *id == "M1").context("没有 M1")?;
    let v = mid.seed_metric(&seed, m, Ask::Single { period: learn }, 2, &metricbench::gold_period(id, &learn)).await?;
    ensure!(v["promoted"] == true, "M1 未晋升：{v}");
    let key = "metric:门店营业额";
    let user = Ctx::new("B", "use", "use");
    let before = mid.use_metric(&user, key).await?;
    ensure!(before["status"] == "valid" && before["revision"] == 0, "{before}");
    let octx = Ctx::new("O", "optimize", "optimize");
    let rounds = mid.optimize_sweep(&octx, None, 1).await?;
    let round = rounds.iter().find(|r| r["key"] == key).context("没有 M1 的优化轮")?;
    let tried = round["tried"].as_array().context("tried")?;
    let first = tried.first().context("没有候选")?;
    ensure!(first["candidate"].as_str().unwrap_or("").contains("日期键范围"), "{first}");
    let gates = first["gates"].as_array().context("gates")?;
    for g in ["O1", "G3", "G4", "O2", "O3", "G5", "O5"] {
        ensure!(gates.iter().any(|x| x["gate"] == g && x["pass"] == true), "门槛 {g} 未通过：{first}");
    }
    let o6 = gates.iter().find(|x| x["gate"] == "O6").context("没有 O6")?.clone();
    let promoted = first["event"] == "optimize_promoted";
    let after = mid.use_metric(&user, key).await?;
    let mut grace = Value::Null;
    if promoted {
        ensure!(after["revision"] == 1, "{after}");
        let sql = after["metric"]["examples"][0]["sql"].as_str().context("示例 SQL")?.to_string();
        ensure!(!sql.contains("join date_dim"), "新修订的示例 SQL 仍连接 date_dim：{sql}");
        let r = mid.run_sql_with(&user, "select 1 as value", &[(key.to_string(), 0)]).await?;
        ensure!(r.get("rejected").is_none(), "旧修订应宽限可用：{r}");
        let notices = mid.take_notices("B");
        ensure!(notices.iter().any(|n| n.contains("等价且更省")), "缺少通知：{notices:?}");
        grace = json!({"old_revision_accepted": true, "notices": notices});
    } else {
        ensure!(after["revision"] == 0, "{after}");
    }
    Ok(json!({"rows": rows, "promoted": promoted, "candidate": first["candidate"], "o6": o6, "cost": first["cost"],
              "revision_after": after["revision"], "grace": grace, "stats": mid.stats_json()}))
}

#[tokio::test]
#[ignore = "requires AGENTDB_TEST_URL and PostgreSQL 15+ with CREATE DATABASE permission"]
async fn postgres_optimization_revision() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("设置 AGENTDB_TEST_URL 为测试服务器连接串")?;
    let admin = Db::connect(&url, 1, false)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_optimize_{}_{unique}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    admin.query(QKind::Meta, &format!("create database {name}")).await?;
    let result = tokio::time::timeout(Duration::from_secs(900), optimization_revision(test_url.as_str())).await;
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let report = match &result {
        Ok(Ok(v)) => v.clone(),
        Ok(Err(e)) => json!({"status": "failed", "error": format!("{e:#}")}),
        Err(_) => json!({"status": "failed", "error": "优化修订测试超时"}),
    };
    let out = format!("results/optimize-test-{unique}");
    std::fs::create_dir_all(&out)?;
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("优化修订测试报告：{out}/report.json；测试库清理：{}", cleanup.is_ok());
    cleanup.context("测试库清理失败")?;
    result.context("优化修订测试超时")??;
    Ok(())
}

#[tokio::test]
#[ignore = "requires AGENTDB_TEST_URL and PostgreSQL 15+ with CREATE DATABASE permission"]
async fn postgres_premise_break() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("设置 AGENTDB_TEST_URL 为测试服务器连接串")?;
    let admin = Db::connect(&url, 1, false)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_premise_{}_{unique}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    admin.query(QKind::Meta, &format!("create database {name}")).await?;
    let result = tokio::time::timeout(Duration::from_secs(3600), premise_break(test_url.as_str())).await;
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let report = match &result {
        Ok(Ok(v)) => v.clone(),
        Ok(Err(e)) => json!({"status": "failed", "error": format!("{e:#}")}),
        Err(_) => json!({"status": "failed", "error": "优化前提测试超时"}),
    };
    let out = format!("results/premise-test-{unique}");
    std::fs::create_dir_all(&out)?;
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("优化前提测试报告：{out}/report.json；测试库清理：{}", cleanup.is_ok());
    cleanup.context("测试库清理失败")?;
    result.context("优化前提测试超时")??;
    Ok(())
}

/// 规范 SQL 在当前数据上的取值。
async fn value_of(db: &Db, sql: &str) -> Result<metric::Answer> {
    Ok(metric::parse_answer(db.query(QKind::Meta, sql).await?.cell(0, 0).unwrap_or("NULL")))
}

/// 被引用的修订是否被执行端接受（只看引用检查，执行的 SQL 无关紧要）。
async fn accepted(mid: &Middle, ctx: &Ctx, key: &str, rev: u32) -> Result<(bool, Value)> {
    let r = mid.run_sql_with(ctx, "select 1 as value", &[(key.to_string(), rev)]).await?;
    Ok((r.get("rejected").is_none(), r))
}

/// 优化修订的前提被破坏，以及三种被替代的修订。种子定义（M1 / M2 / M3 / M5）经一轮规则优化得到日期键范围修订后：
/// (1) 日期键重编号：2002-02 的日期换成新的代理键并让事实表改指向它。所有日期键仍存在、关联仍唯一、完整性不变，
///     只有日期键按月连续不再成立。预期日期键范围修订失效、前一修订（连接日期维度）恢复为当前修订，按它回答的各期间
///     都正确；不维护这一前提时，日期键范围修订在跨月期间上漏掉被重编号的月份。声明失效修订的查询被拒绝，声明恢复的修订被接受。
/// (2) 另一个实例中，门店退货金额优化后施加状态流水：退货粒度失效并被修复。被修复替代的修订与它的前一修订都被拒绝。
/// (3) 补录的销售中一半的商品键关联不上商品维度：内连接商品维度的电子品类营业额被完整性条件判为失效，不连接商品维度的门店营业额不受影响。
async fn premise_break(url: &str) -> Result<Value> {
    let admin = Db::connect(url, 2, false)?;
    let rows = std::env::var("AGENTDB_SCENARIO_ROWS").ok().and_then(|v| v.parse().ok()).unwrap_or(200_000);
    admin.query(QKind::Meta, &metricbench::fixture(rows)).await?;
    etl::setup(&admin).await?;
    scenario::setup(&admin).await?;
    let v1 = scenario::fingerprint(&admin).await?;
    let db = Arc::new(Db::connect(url, 4, true)?);
    let cfg = MiddleConfig {
        name: "premise".into(),
        version_ttl_ms: 0,
        metric_maint: Maint::Condition,
        cond_reuse: true,
        optimize: true,
        ..Default::default()
    };
    let mid = Middle::new(db, cfg.clone()).await?;
    let seed = Ctx::new("A", "seed", "seed");
    let user = Ctx::new("B", "use", "use");
    let octx = Ctx::new("O", "optimize", "optimize");
    let learn = Period::month(2001, 3);
    let defs = seeded_metrics();
    let key_of = |m: &Metric| format!("metric:{}", m.name);
    for (id, m) in &defs {
        let v = mid.seed_metric(&seed, m.clone(), Ask::Single { period: learn }, 2, &metricbench::gold_period(id, &learn)).await?;
        ensure!(v["promoted"] == true, "{id} 未晋升：{v}");
        let u = mid.use_metric(&user, &key_of(m)).await?;
        ensure!(u["status"] == "valid" && u["revision"] == 0, "{id}：{u}");
    }

    // (1) 一轮规则优化，然后日期键重编号
    let t = Instant::now();
    let rounds = mid.optimize_sweep(&octx, None, 1).await?;
    let sweep_s = t.elapsed().as_secs_f64();
    let mut optimized: BTreeMap<&str, Metric> = BTreeMap::new();
    for (id, m) in &defs {
        let u = mid.use_metric(&user, &key_of(m)).await?;
        if u["revision"] == 1 {
            optimized.insert(*id, serde_json::from_value(u["metric"].clone())?);
        }
    }
    ensure!(!optimized.is_empty(), "没有定义得到优化修订：{rounds:?}");
    // (2) 被修复替代：另一个实例只放门店退货金额，优化后施加状态流水，退货粒度失效并被修复
    let mid2 = Middle::new(Arc::new(Db::connect(url, 4, true)?), cfg.clone()).await?;
    let (m2_id, m2) = defs.iter().find(|(id, _)| *id == "M2").context("没有 M2")?;
    let m2_key = key_of(m2);
    let v = mid2.seed_metric(&seed, m2.clone(), Ask::Single { period: learn }, 2, &metricbench::gold_period(m2_id, &learn)).await?;
    ensure!(v["promoted"] == true, "{m2_id} 未晋升：{v}");
    let rounds2 = mid2.optimize_sweep(&octx, None, 1).await?;
    let before2 = mid2.use_metric(&user, &m2_key).await?;
    let st = Change::Status;
    st.apply_truth(&admin).await?;
    st.apply_hidden(&admin).await?;
    mid2.invalidate_versions();
    let after2 = mid2.use_metric(&user, &m2_key).await?;
    let mut status_refs = json!({"skipped": "门店退货金额没有得到优化修订", "rounds": rounds2, "before": before2});
    if before2["revision"] == 1 {
        ensure!(after2["status"] == "valid" && after2["revision"] == 2, "{m2_id}：状态流水后应修复为 r2：{after2}");
        let mut seen = serde_json::Map::new();
        for rev in [0u32, 1, 2] {
            let (a, r) = accepted(&mid2, &user, &m2_key, rev).await?;
            ensure!(a == (rev == 2), "{m2_id}：r{rev} 的接受情况不对：{r}");
            seen.insert(format!("r{rev}"), json!({"accepted": a, "response": r}));
        }
        // 修复之后不再保留前一修订；此时日期键重编号只破坏日期键连续，回退方式是撤销改写规则：同一结构改回连接日期维度
        let rk = Change::Rekey;
        rk.apply_truth(&admin).await?;
        rk.apply_hidden(&admin).await?;
        mid2.invalidate_versions();
        let undone = mid2.use_metric(&user, &m2_key).await?;
        ensure!(
            undone["status"] == "valid" && undone["revision"] == 3 && undone["metric"]["time"]["strategy"] == "dim_join",
            "{m2_id}：重编号后应撤销日期键范围规则，发布连接日期维度的 r3：{undone}"
        );
        let q1 = Period { year: 2002, m1: 1, m2: 3 };
        let served: Metric = serde_json::from_value(undone["metric"].clone())?;
        let got = value_of(&admin, &metric::compile(&served, &Ask::Single { period: q1 })?).await?;
        let gold = value_of(&admin, &metricbench::gold_period(m2_id, &q1)).await?;
        ensure!(metric::same_value(&got, &gold, 2), "{m2_id}：撤销规则后的 Q1 答案 {got:?}，标准 {gold:?}");
        rk.reset(&admin).await?;
        status_refs = json!({"before": before2["revision"], "after": after2["revision"], "references": seen,
                             "rekey_after_repair": {"revision": undone["revision"], "strategy": undone["metric"]["time"]["strategy"]}});
    }
    st.reset(&admin).await?;
    scenario::ensure_v1(&admin, &v1, "状态流水回滚").await?;
    mid.invalidate_versions();

    let periods = [
        ("2002-02", Period::month(2002, 2)),
        ("2002-Q1", Period { year: 2002, m1: 1, m2: 3 }),
        ("2002-H1", Period { year: 2002, m1: 1, m2: 6 }),
        ("2002", Period { year: 2002, m1: 1, m2: 12 }),
        ("2002-09", Period::month(2002, 9)),
    ];
    let mut gold_before = BTreeMap::new();
    for (id, _) in &defs {
        for (pn, p) in &periods {
            gold_before.insert((*id, *pn), value_of(&admin, &metricbench::gold_period(id, p)).await?);
        }
    }
    mid.take_metric_events();
    let ch = Change::Rekey;
    ch.apply_truth(&admin).await?;
    ch.apply_hidden(&admin).await?;
    mid.invalidate_versions();
    let mut per_def = vec![];
    let (mut served_wrong, mut unmaintained_wrong, mut answers) = (0, 0, 0);
    for (id, m) in &defs {
        let key = key_of(m);
        let u = mid.use_metric(&user, &key).await?;
        ensure!(u["status"] == "valid", "{id} 重编号后不可用：{u}");
        let served: Metric = serde_json::from_value(u["metric"].clone())?;
        let mut rows_out = vec![];
        for (pn, p) in &periods {
            let gold = value_of(&admin, &metricbench::gold_period(id, p)).await?;
            ensure!(metric::same_value(&gold, &gold_before[&(*id, *pn)], 2), "{id} {pn}：重编号改变了业务事实");
            let ask = Ask::Single { period: *p };
            let s = value_of(&admin, &metric::compile(&served, &ask)?).await?;
            let ok = metric::same_value(&s, &gold, 2);
            answers += 1;
            served_wrong += usize::from(!ok);
            let stale = match optimized.get(id) {
                Some(om) => {
                    let v = value_of(&admin, &metric::compile(om, &ask)?).await?;
                    let ok = metric::same_value(&v, &gold, 2);
                    unmaintained_wrong += usize::from(!ok);
                    json!({"value": v, "correct": ok})
                }
                None => Value::Null,
            };
            rows_out.push(json!({"period": pn, "gold": gold, "served": s, "served_correct": ok, "key_range_unmaintained": stale}));
        }
        let mut refs = json!(null);
        if optimized.contains_key(id) {
            ensure!(u["revision"] == 0, "{id}：日期键范围修订失效后应恢复前一修订 r0：{u}");
            let (a1, r1) = accepted(&mid, &user, &key, 1).await?;
            let (a0, r0) = accepted(&mid, &user, &key, 0).await?;
            ensure!(!a1 && r1["reason"].as_str().unwrap_or("").contains("日期键"), "{id}：声明失效的 r1 应被拒绝并说明原因：{r1}");
            ensure!(a0, "{id}：声明恢复的 r0 应被接受：{r0}");
            refs = json!({"r1": r1, "r0_accepted": a0});
        }
        per_def.push(json!({"id": id, "key": key, "optimized": optimized.contains_key(id), "revision_served": u["revision"],
                            "answers": rows_out, "references": refs}));
    }
    ensure!(served_wrong == 0, "恢复前一修订后仍有 {served_wrong} 个错误答案：{per_def:?}");
    ensure!(unmaintained_wrong > 0, "不维护前提时日期键范围修订应在跨月期间上出错：{per_def:?}");
    let rekey_events: Vec<Value> = mid
        .take_metric_events()
        .into_iter()
        .filter(|e| matches!(e["event"].as_str(), Some("maintenance" | "reinstated" | "predecessor_checked" | "revoked")))
        .collect();
    let rekey_notices = mid.take_notices("B");
    ch.reset(&admin).await?;
    scenario::ensure_v1(&admin, &v1, "日期键重编号回滚").await?;
    mid.invalidate_versions();

    // (3) 关联不上商品维度的销售：内连接的完整性条件
    metricbench::apply_growth(&admin).await?;
    let before = catalog::versions(&admin).await?.get("store_sales").map(|v| v.dml).unwrap_or(0);
    let n = admin
        .execute(&format!(
            "update store_sales set ss_item_sk = ss_item_sk + 1000000 \
             where ss_ticket_number > {} and ss_ticket_number % 2 = 0",
            metricbench::GROWTH_OFFSET
        ))
        .await?;
    admin.query(QKind::Meta, "select pg_stat_force_next_flush()").await?;
    metricbench::log_batch(&admin, "store_sales", "补录销售中一半的商品键关联不上商品维度").await?;
    admin.query(QKind::Meta, "analyze store_sales").await?;
    etl::wait_table_stats(&admin, "store_sales", before).await?;
    mid.invalidate_versions();
    let (_, m5) = defs.iter().find(|(id, _)| *id == "M5").context("没有 M5")?;
    let (_, m1) = defs.iter().find(|(id, _)| *id == "M1").context("没有 M1")?;
    let e5 = mid.use_metric(&user, &key_of(m5)).await?;
    let e1 = mid.use_metric(&user, &key_of(m1)).await?;
    ensure!(e5["status"] == "unavailable" && e5["reason"].as_str().unwrap_or("").contains("内连接排除"), "M5 应被完整性条件判为失效：{e5}");
    ensure!(e1["status"] == "valid", "M1 不连接商品维度，应不受影响：{e1}");
    metricbench::reset_growth(&admin).await?;
    scenario::ensure_v1(&admin, &v1, "孤儿商品键回滚").await?;

    Ok(json!({
        "status": "passed", "rows": rows, "sweep_s": sweep_s, "rounds": rounds,
        "rekey": {"definitions": per_def, "answers": answers, "served_wrong": served_wrong,
                  "key_range_unmaintained_wrong": unmaintained_wrong, "events": rekey_events, "notices": rekey_notices},
        "status_change": status_refs,
        "orphan_items": {"rows_updated": n, "m5": e5, "m1": e1},
        "stats": mid.stats_json(),
    }))
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
            strategy: TimeStrategy::DimJoin,
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
        orphan_ratio: 0.0,
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
        // 未优化的定义不依赖日期键连续：各条件都成立
        Change::Rekey => [V0, V0, V0, V0],
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
        _ => unreachable!(),
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
/// 对前两种参照各跑一次条件级维护（修复候选唯一性要求关闭与打开各一次），记录 MAVRA 实际发布的过滤。
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
        _ => unreachable!(),
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
    for ((oracle, use_anticipated), unique) in
        [("unanticipated", false), ("anticipated", true)].into_iter().flat_map(|o| [false, true].map(move |u| (o, u)))
    {
        let db = Arc::new(Db::connect(url, 4, true)?);
        let cfg = MiddleConfig {
            version_ttl_ms: 0,
            metric_maint: Maint::Condition,
            cond_reuse: true,
            repair_unique: unique,
            ..Default::default()
        };
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
        runs.push(json!({"oracle": oracle, "repair_unique": unique, "served": served, "events": events}));
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

// ───────────────────────── 快照绑定：核对与执行之间的并发写入（不调用 LLM） ─────────────────────────

/// 违反 M1 粒度条件的写入：2002-06 至 2002-09 的门店销售整批重复一次（与重复装载场景相同，但不经过 ETL 通知）。
const DUP_INJECT: &str = "insert into store_sales select s.* from store_sales s join date_dim d on s.ss_sold_date_sk = d.d_date_sk \
                          where d.d_date between date '2002-06-01' and date '2002-09-30'";
const DUP_RESET: &str = "delete from store_sales a using store_sales b \
                         where a.ss_ticket_number = b.ss_ticket_number and a.ss_item_sk = b.ss_item_sk and a.ctid > b.ctid";
const SNAP_TABLES: [&str; 4] = ["store_sales", "store_returns", "date_dim", "item"];

/// 一次带指标引用的 run_sql：served = 答案所在的数据满足所引用修订的粒度条件；violation = 不满足
/// （探针在同一语句、同一快照里数出重复键）；rejected = 拒绝或指标不可用；error = 执行出错。
fn classify(r: &Result<Value>) -> &'static str {
    match r {
        Err(_) => "error",
        Ok(v) if v.get("rejected").is_some() => "rejected",
        Ok(v) => match v["result"]["rows"][0][1].as_str().and_then(|d| d.parse::<i64>().ok()) {
            Some(0) => "served",
            Some(_) => "violation",
            None => "error",
        },
    }
}

fn summary(xs: &mut [f64]) -> Value {
    if xs.is_empty() {
        return json!({"n": 0});
    }
    xs.sort_by(|a, b| a.total_cmp(b));
    let q = |p: f64| xs[((xs.len() - 1) as f64 * p).round() as usize];
    json!({"n": xs.len(), "mean": xs.iter().sum::<f64>() / xs.len() as f64, "p50": q(0.5), "p95": q(0.95), "max": q(1.0)})
}

struct SnapBench {
    url: String,
    admin: Db,
    learn: Period,
}

struct SnapMid {
    mid: Middle,
    cp: Checkpoint,
    refs: Vec<(String, u32)>,
    /// 引用修订的规范 SQL（2002-07，落在重复区间内）
    canon: String,
    /// 规范 SQL 加上同一语句里、该月销售行的重复键计数（判定答案所汇总的数据是否满足粒度条件）
    probe: String,
    /// 同样的探针，期间为 2002-06 至 2002-09 各月（都在重复区间内）；随机并发里各读者问不同的月份，查询不会在途合并
    probes: Vec<String>,
}

impl SnapBench {
    async fn middle(&self, snapshot: bool, pause_ms: u64) -> Result<SnapMid> {
        let db = Arc::new(Db::connect(&self.url, 8, true)?);
        let cfg = MiddleConfig {
            name: if snapshot { "snapshot" } else { "precheck" }.into(),
            metric_maint: Maint::Condition,
            cond_reuse: true,
            result_cache: false,
            snapshot_exec: snapshot,
            exec_pause_ms: pause_ms,
            ..Default::default()
        };
        let mid = Middle::new(db, cfg).await?;
        let m1 = seeded_metrics().into_iter().find(|(id, _)| *id == "M1").map(|x| x.1).context("缺少 M1")?;
        let key = format!("metric:{}", m1.name);
        let v = mid
            .seed_metric(
                &Ctx::new("A", "seed", "seed"),
                m1,
                Ask::Single { period: self.learn },
                2,
                &metricbench::gold_period("M1", &self.learn),
            )
            .await?;
        ensure!(v["promoted"] == true, "M1 未晋升：{v}");
        let u = mid.use_metric(&Ctx::new("B", "snapshot", "use"), &key).await?;
        ensure!(u["status"] == "valid", "M1 不可用：{u}");
        let m: Metric = serde_json::from_value(u["metric"].clone())?;
        let canon = metric::compile(&m, &Ask::Single { period: Period::month(2002, 7) })?;
        let wrap = |mo: u32| -> Result<String> {
            let c = metric::compile(&m, &Ask::Single { period: Period::month(2002, mo) })?;
            Ok(format!(
                "select ({}) as v, (select count(*) - count(distinct (s.ss_ticket_number, s.ss_item_sk)) from store_sales s \
                 join date_dim d on s.ss_sold_date_sk = d.d_date_sk where d.d_year = 2002 and d.d_moy = {mo}) as dup",
                c.trim().trim_end_matches(';')
            ))
        };
        let probe = wrap(7)?;
        let probes = (6..=9).map(wrap).collect::<Result<Vec<_>>>()?;
        let refs = vec![(key, u["revision"].as_u64().unwrap_or(0) as u32)];
        Ok(SnapMid { cp: mid.checkpoint(), mid, refs, canon, probe, probes })
    }

    async fn dml(&self) -> Result<i64> {
        Ok(catalog::versions(&self.admin).await?.get("store_sales").map(|v| v.dml).unwrap_or(0))
    }

    /// 写入提交后再通知（ETL 的正常顺序）：登记批次、使中间层重读版本。
    async fn inject_then_notify(&self, mid: &Middle) -> Result<()> {
        self.admin.execute(DUP_INJECT).await?;
        metricbench::log_batch(&self.admin, "store_sales", "重复装载（快照实验）").await?;
        mid.invalidate_versions();
        Ok(())
    }

    /// 去掉重复行，等统计计数稳定后把经验库恢复到写入前（数据内容已回到写入前）。
    async fn reset(&self, s: &SnapMid) -> Result<()> {
        let before = self.dml().await?;
        if self.admin.execute(DUP_RESET).await? > 0 {
            etl::wait_table_stats(&self.admin, "store_sales", before).await?;
        }
        // 回收删掉的重复行，保持各次试验的表状态与计划一致（不改变 DML 计数与模式）
        self.admin.query(QKind::Meta, "vacuum analyze store_sales").await?;
        tokio::time::sleep(Duration::from_millis(1500)).await;
        s.mid.invalidate_versions();
        s.mid.restore(&s.cp).await?;
        // 恢复只改写经验库，不含快照结论；预热一次，让两种模式都从稳态开始下一次试验
        let warm = s.mid.run_sql_with(&Ctx::new("W", "snapshot", "warm"), &s.probe, &s.refs).await;
        ensure!(classify(&warm) == "served", "恢复后预热应在干净数据上执行：{warm:?}");
        Ok(())
    }

    /// 实验 A：确定性交错。write_during_pause = 核对通过后、执行前提交写入（未通知）；write_before_call = 写入刚提交、
    /// 尚未通知时调用；write_notified = 写入提交并通知、统计已刷新后调用。每次先在干净数据上预热一次。
    async fn interleave(&self, snapshot: bool, case: &str, trials: usize) -> Result<Value> {
        let s = self.middle(snapshot, if case == "write_during_pause" { 2000 } else { 0 }).await?;
        let ctx = Ctx::new("B", "snapshot", "use");
        let mut counts: BTreeMap<&str, u32> = BTreeMap::new();
        let (mut samples, mut lat) = (vec![], vec![]);
        for i in 0..trials {
            let warm = s.mid.run_sql_with(&ctx, &s.probe, &s.refs).await;
            ensure!(classify(&warm) == "served", "第 {i} 次预热应在干净数据上执行：{warm:?}");
            let t = Instant::now();
            let r = match case {
                "write_during_pause" => {
                    let (r, w) = tokio::join!(s.mid.run_sql_with(&ctx, &s.probe, &s.refs), async {
                        tokio::time::sleep(Duration::from_millis(700)).await;
                        self.admin.execute(DUP_INJECT).await
                    });
                    w?;
                    r
                }
                "write_before_call" => {
                    self.admin.execute(DUP_INJECT).await?;
                    s.mid.run_sql_with(&ctx, &s.probe, &s.refs).await
                }
                _ => {
                    let before = self.dml().await?;
                    self.inject_then_notify(&s.mid).await?;
                    etl::wait_table_stats(&self.admin, "store_sales", before).await?;
                    s.mid.invalidate_versions();
                    s.mid.run_sql_with(&ctx, &s.probe, &s.refs).await
                }
            };
            lat.push(t.elapsed().as_secs_f64() * 1000.0);
            let c = classify(&r);
            *counts.entry(c).or_default() += 1;
            if i < 2 {
                let resp = match &r {
                    Ok(v) => v.clone(),
                    Err(e) => json!(format!("{e:#}")),
                };
                samples.push(json!({"class": c, "response": resp}));
            }
            self.reset(&s).await?;
        }
        Ok(json!({"mode": if snapshot { "snapshot" } else { "precheck" }, "case": case, "trials": trials, "counts": counts,
                  "latency_ms": summary(&mut lat), "stats": s.mid.stats_json(), "samples": samples}))
    }

    /// 实验 B：随机并发。readers 个读者在窗口内连续调用（每次间隔 think_ms）；写者在随机时刻提交违反粒度的写入。
    /// notify = 提交后立即登记批次并通知（ETL 的正常顺序）；否则不通知，中间层只能从统计计数发现写入。
    /// distinct = 各读者问不同的月份；否则都问同一个月，相同的查询会合并到在途执行。
    #[allow(clippy::too_many_arguments)]
    async fn stress(
        &self,
        snapshot: bool,
        notify: bool,
        distinct: bool,
        trials: usize,
        readers: usize,
        window_ms: u64,
        think_ms: u64,
        seed: u64,
    ) -> Result<Value> {
        use rand::{Rng, SeedableRng};
        let s = self.middle(snapshot, 0).await?;
        let mut rng = rand::rngs::StdRng::seed_from_u64(seed);
        let mut counts: BTreeMap<&str, u32> = BTreeMap::new();
        let (mut lat, mut after_commit, mut per_trial) = (vec![], vec![], vec![]);
        for _ in 0..trials {
            let at = rng.gen_range(300..window_ms - 300);
            let start = Instant::now();
            let reader = |k: usize| {
                let s = &s;
                async move {
                    let ctx = Ctx::new(&format!("R{k}"), "snapshot", "use");
                    let mut out = vec![];
                    while start.elapsed() < Duration::from_millis(window_ms) {
                        let t0 = start.elapsed().as_secs_f64() * 1000.0;
                        let probe = if distinct { &s.probes[k % s.probes.len()] } else { &s.probe };
                        let r = s.mid.run_sql_with(&ctx, probe, &s.refs).await;
                        out.push((classify(&r), t0, start.elapsed().as_secs_f64() * 1000.0));
                        tokio::time::sleep(Duration::from_millis(think_ms)).await;
                    }
                    out
                }
            };
            let writer = async {
                tokio::time::sleep(Duration::from_millis(at)).await;
                self.admin.execute(DUP_INJECT).await?;
                let committed = start.elapsed().as_secs_f64() * 1000.0;
                if notify {
                    metricbench::log_batch(&self.admin, "store_sales", "重复装载（快照实验）").await?;
                    s.mid.invalidate_versions();
                }
                Ok::<_, anyhow::Error>((committed, start.elapsed().as_secs_f64() * 1000.0))
            };
            let (calls, w) = tokio::join!(futures::future::join_all((0..readers).map(reader)), writer);
            let (committed, notified) = w?;
            let mut trial: BTreeMap<&str, u32> = BTreeMap::new();
            for (c, t0, t1) in calls.into_iter().flatten() {
                *counts.entry(c).or_default() += 1;
                *trial.entry(c).or_default() += 1;
                lat.push(t1 - t0);
                if c == "violation" {
                    after_commit.push(t0 - committed);
                }
            }
            per_trial.push(json!({"commit_ms": committed, "notify_ms": notified, "counts": trial}));
            self.reset(&s).await?;
        }
        Ok(
            json!({"mode": if snapshot { "snapshot" } else { "precheck" }, "notify": notify, "distinct": distinct, "trials": trials, "readers": readers,
                  "window_ms": window_ms, "think_ms": think_ms, "counts": counts, "latency_ms": summary(&mut lat),
                  "violation_start_minus_commit_ms": summary(&mut after_commit), "per_trial": per_trial, "stats": s.mid.stats_json()}),
        )
    }

    /// 实验 C1：读者开销。无写入时（版本未变，结论直接用）与良性写入后（版本变了，条件在快照里重查）的调用延迟。
    /// 只执行规范 SQL（不带重复键计数），排除判定探针本身的代价。
    async fn reader_overhead(&self, snapshot: bool, calls: usize, writes: usize) -> Result<Value> {
        self.admin.query(QKind::Meta, "vacuum analyze store_sales").await?;
        let s = self.middle(snapshot, 0).await?;
        let ctx = Ctx::new("B", "snapshot", "use");
        let ok = |r: &Result<Value>| r.as_ref().is_ok_and(|v| v.get("rejected").is_none() && v.get("result").is_some());
        for _ in 0..3 {
            let r = s.mid.run_sql_with(&ctx, &s.canon, &s.refs).await;
            ensure!(ok(&r), "预热失败：{r:?}");
        }
        let mut steady = vec![];
        for _ in 0..calls {
            let t = Instant::now();
            let r = s.mid.run_sql_with(&ctx, &s.canon, &s.refs).await;
            ensure!(ok(&r), "无写入时应正常执行：{r:?}");
            steady.push(t.elapsed().as_secs_f64() * 1000.0);
        }
        let (mut first, mut second) = (vec![], vec![]);
        for _ in 0..writes {
            // 良性写入：内容不变，但版本前进（触发器与统计计数都会变）
            let before = self.dml().await?;
            self.admin
                .execute(
                    "update store_sales set ss_net_paid = ss_net_paid where (ss_ticket_number, ss_item_sk) = \
                     (select ss_ticket_number, ss_item_sk from store_sales order by ss_ticket_number, ss_item_sk limit 1)",
                )
                .await?;
            metricbench::log_batch(&self.admin, "store_sales", "良性写入（快照实验）").await?;
            etl::wait_table_stats(&self.admin, "store_sales", before).await?;
            s.mid.invalidate_versions();
            for out in [&mut first, &mut second] {
                let t = Instant::now();
                let r = s.mid.run_sql_with(&ctx, &s.canon, &s.refs).await;
                ensure!(ok(&r), "良性写入后应正常执行：{r:?}");
                out.push(t.elapsed().as_secs_f64() * 1000.0);
            }
        }
        Ok(json!({"mode": if snapshot { "snapshot" } else { "precheck" }, "steady_ms": summary(&mut steady),
                  "first_after_write_ms": summary(&mut first), "second_after_write_ms": summary(&mut second), "stats": s.mid.stats_json()}))
    }

    /// 实验 C2：写者开销。单行更新的吞吐：顺序、以及 8 个连接并发（各改不同的行，但同表的版本行要排队）；
    /// 以及批量写入（每条语句 1 万行）的耗时。
    async fn writer_overhead(&self, per_worker: usize) -> Result<Value> {
        let pool = Db::connect(&self.url, 32, false)?;
        pool.query(
            QKind::Meta,
            "drop table if exists bench_w; create table bench_w (id int primary key, x int not null default 0); \
                                 insert into bench_w (id) select g from generate_series(0, 31999) g",
        )
        .await?;
        let run = |workers: usize| {
            let pool = &pool;
            async move {
                let t = Instant::now();
                let jobs = (0..workers).map(|w| async move {
                    for i in 0..per_worker {
                        pool.execute(&format!("update bench_w set x = x + 1 where id = {}", w * 1000 + i % 1000)).await?;
                    }
                    Ok::<_, anyhow::Error>(())
                });
                for r in futures::future::join_all(jobs).await {
                    r?;
                }
                Ok::<_, anyhow::Error>((workers * per_worker) as f64 / t.elapsed().as_secs_f64())
            }
        };
        let mut out = vec![];
        for round in 0..3 {
            // 0 = 无触发器；1 = 每表一行版本计数；TX_SHARDS = 分片计数（默认）
            for shards in [0, 1, catalog::TX_SHARDS] {
                let trig = shards > 0;
                if trig {
                    catalog::install_tx_versions_sharded(&pool, &["bench_w"], shards).await?;
                } else {
                    pool.query(QKind::Meta, "drop trigger if exists mavra_bump on bench_w").await?;
                }
                let seq = run(1).await?;
                let conc = run(8).await?;
                let conc32 = run(32).await?;
                let t = Instant::now();
                for b in 0..20 {
                    pool.execute(&format!("update bench_w set x = x + 1 where id between {} and {}", (b % 8) * 1000, (b % 8) * 1000 + 999))
                        .await?;
                    pool.execute(&format!(
                        "insert into bench_w (id) select g from generate_series({lo}, {hi}) g; delete from bench_w where id between {lo} and {hi}",
                        lo = 100_000 + b * 10_000,
                        hi = 100_000 + b * 10_000 + 9_999
                    ))
                    .await?;
                }
                let bulk = t.elapsed().as_secs_f64() * 1000.0 / 60.0;
                out.push(json!({"round": round, "trigger": trig, "shards": shards, "sequential_stmt_per_s": seq,
                                "concurrent8_stmt_per_s": conc, "concurrent32_stmt_per_s": conc32, "bulk_ms_per_stmt": bulk}));
            }
        }
        pool.query(QKind::Meta, "drop table bench_w; delete from mavra_versions where table_name = 'bench_w'").await?;
        Ok(json!(out))
    }
}

async fn snapshot_binding(url: &str) -> Result<Value> {
    let admin = Db::connect(url, 2, false)?;
    let rows = std::env::var("AGENTDB_SCENARIO_ROWS").ok().and_then(|v| v.parse().ok()).unwrap_or(200_000);
    admin.query(QKind::Meta, &metricbench::fixture(rows)).await?;
    etl::setup(&admin).await?;
    scenario::setup(&admin).await?;
    catalog::install_tx_versions(&admin, &SNAP_TABLES).await?;
    admin.query(QKind::Meta, "analyze").await?;
    let b = SnapBench { url: url.to_string(), admin, learn: Period::month(2001, 3) };
    let trials = std::env::var("AGENTDB_SNAP_TRIALS").ok().and_then(|v| v.parse().ok()).unwrap_or(10);
    // AGENTDB_SNAP_PARTS 选择要跑的部分（默认全部）：readers,writers,interleave,stress
    let parts = std::env::var("AGENTDB_SNAP_PARTS").unwrap_or_else(|_| "readers,writers,interleave,stress".into());
    let on = |p: &str| parts.split(',').any(|x| x.trim() == p);
    // 开销先测（表还没有经历重复写入与删除），两种模式交替两轮
    let mut readers = vec![];
    if on("readers") {
        for _ in 0..2 {
            for snapshot in [false, true] {
                readers.push(b.reader_overhead(snapshot, 40, trials).await?);
            }
        }
    }
    let writers = if on("writers") { b.writer_overhead(500).await? } else { json!([]) };
    let mut interleavings = vec![];
    if on("interleave") {
        for case in ["write_during_pause", "write_before_call", "write_notified"] {
            for snapshot in [false, true] {
                interleavings.push(b.interleave(snapshot, case, trials).await?);
            }
        }
    }
    let mut stress = vec![];
    if on("stress") {
        for distinct in [false, true] {
            for notify in [true, false] {
                for snapshot in [false, true] {
                    stress.push(b.stress(snapshot, notify, distinct, 2 * trials, 4, 3000, 10, 20261002).await?);
                }
            }
        }
    }
    Ok(json!({"rows": rows, "trials": trials, "interleavings": interleavings, "stress": stress,
              "reader_overhead": readers, "writer_overhead": writers}))
}

#[tokio::test]
#[ignore = "experiment; requires AGENTDB_TEST_URL and PostgreSQL 15+ with CREATE DATABASE permission"]
async fn postgres_snapshot_binding() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("设置 AGENTDB_TEST_URL 为测试服务器连接串")?;
    let admin = Db::connect(&url, 1, false)?;
    let unique = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_snap_{}_{unique}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    admin.query(QKind::Meta, &format!("create database {name}")).await.context("无法创建独立测试库")?;
    let result = tokio::time::timeout(Duration::from_secs(5400), snapshot_binding(test_url.as_str())).await;
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let out = format!("results/snapshot-binding-{unique}");
    std::fs::create_dir_all(&out)?;
    let report = match &result {
        Ok(Ok(v)) => v.clone(),
        Ok(Err(e)) => json!({"status": "failed", "error": format!("{e:#}")}),
        Err(_) => json!({"status": "failed", "error": "实验超时"}),
    };
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&report)?)?;
    println!("快照绑定实验报告：{out}/report.json；测试库清理：{}", cleanup.is_ok());
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
        _ => unreachable!(),
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
