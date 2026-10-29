// Included only in an isolated experiment checkout's integration_tests module.
// No LLM calls. Reuses the real middleware and its ordinary admission path.

#[test]
#[ignore = "export frozen source subsets with the unchanged Rust compiler; no database or model calls"]
fn mechanism_compile_frozen_source() -> Result<()> {
    let source = std::env::var("MECHANISM_SOURCE")?;
    let out = std::env::var("MECHANISM_COMPILED_OUT")?;
    let data: Value = serde_json::from_str(&std::fs::read_to_string(format!("{source}/source-features.json"))?)?;
    let frozen: Value = serde_json::from_str(&std::fs::read_to_string(format!("{source}/frozen-definitions.json"))?)?;
    let mut defs = data["features"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|x| x["status"] == "Valid")
        .map(|x| Ok((x["entry"]["key"].as_str().unwrap().to_string(), serde_json::from_value::<Metric>(x["entry"].clone())?)))
        .collect::<Result<Vec<_>>>()?;
    defs.sort_by(|a, b| a.0.cmp(&b.0));
    ensure!(defs.len() == 7, "source changed: expected seven frozen definitions");
    let mut entries = serde_json::Map::new();
    for mask in 1..(1 << defs.len()) {
        let chosen = defs.iter().enumerate().filter(|(i, _)| mask & (1 << i) != 0).map(|(_, d)| d).collect::<Vec<_>>();
        let metrics = chosen.iter().map(|d| &d.1).collect::<Vec<_>>();
        let (sql, cols) = metric::compose_features(&metrics, "userid")?;
        let keys = chosen.iter().map(|d| d.0.clone()).collect::<Vec<_>>();
        let columns = keys.iter().zip(cols).map(|(k, c)| json!({"key":k,"revision":0,"column":c})).collect::<Vec<_>>();
        if mask == (1 << defs.len()) - 1 {
            ensure!(sql == frozen["sql"].as_str().unwrap(), "full-source compiler equivalence failed");
        }
        entries.insert(keys.join("|"), json!({"sql":sql,"columns":columns}));
    }
    std::fs::write(out, serde_json::to_string_pretty(&json!({"subsets":entries,"full_sql_exact_match":true}))?)?;
    Ok(())
}

async fn mech_c_middle(b: &SnapBench, detach: bool) -> Result<SnapMid> {
    let cfg = MiddleConfig {
        name: if detach { "tx-precheck" } else { "tx-bound" }.into(),
        metric_maint: Maint::Condition,
        cond_reuse: true,
        result_cache: false,
        snapshot_exec: true,
        experiment_detach: detach,
        experiment_barrier: Some(Arc::new((
            std::sync::atomic::AtomicBool::new(false),
            tokio::sync::Notify::new(),
            tokio::sync::Notify::new(),
        ))),
        ..Default::default()
    };
    let mid = Middle::new(Arc::new(Db::connect(&b.url, 8, true)?), cfg).await?;
    let m = seeded_metrics().into_iter().find(|(id, _)| *id == "M1").unwrap().1;
    let key = format!("metric:{}", m.name);
    let seeded = mid
        .seed_metric(&Ctx::new("A", "seed", "seed"), m, Ask::Single { period: b.learn }, 2, &metricbench::gold_period("M1", &b.learn))
        .await?;
    ensure!(seeded["promoted"] == true, "matched-C admission failed: {seeded}");
    let u = mid.use_metric(&Ctx::new("B", "matched", "use"), &key).await?;
    let m: Metric = serde_json::from_value(u["metric"].clone())?;
    let canon = metric::compile(&m, &Ask::Single { period: Period::month(2002, 7) })?;
    let probe = format!(
        "select ({}) as v, (select count(*)-count(distinct (s.ss_ticket_number,s.ss_item_sk)) \
        from store_sales s join date_dim d on s.ss_sold_date_sk=d.d_date_sk \
        where d.d_year=2002 and d.d_moy=7) as dup",
        canon.trim().trim_end_matches(';')
    );
    let refs = vec![(key, u["revision"].as_u64().unwrap() as u32)];
    Ok(SnapMid { cp: mid.checkpoint(), mid, refs, canon, probe, probes: vec![] })
}

async fn mechanism_c(url: &str, out: &str) -> Result<Value> {
    let admin = Db::connect(url, 2, false)?;
    admin.query(QKind::Meta, &metricbench::fixture(200_000)).await?;
    etl::setup(&admin).await?;
    scenario::setup(&admin).await?;
    catalog::install_tx_versions(&admin, &SNAP_TABLES).await?;
    admin.query(QKind::Meta, "analyze").await?;
    let b = SnapBench { url: url.into(), admin, learn: Period::month(2001, 3) };
    let mut rows = vec![];
    for trial in 0..5 {
        for case in ["benign_after_check", "violation_after_check", "violation_before_call"] {
            // Counterbalance mode order across trial blocks.
            for index in 0..2 {
                let detach = (index + trial) % 2 == 0;
                let s = mech_c_middle(&b, detach).await?;
                let ctx = Ctx::new("B", "matched", "execute");
                let warm = s.mid.run_sql_with(&ctx, &s.probe, &s.refs).await;
                ensure!(classify(&warm) == "served", "matched-C warm failed");
                let barrier = s.mid.cfg.experiment_barrier.as_ref().unwrap().clone();
                let r = if case == "violation_before_call" {
                    b.admin.execute(DUP_INJECT).await?;
                    s.mid.run_sql_with(&ctx, &s.probe, &s.refs).await
                } else {
                    barrier.0.store(true, std::sync::atomic::Ordering::SeqCst);
                    let writer = async {
                        tokio::time::timeout(Duration::from_secs(60), barrier.1.notified())
                            .await
                            .context("validation barrier was not reached")?;
                        let w = if case == "benign_after_check" {
                            b.admin
                                .execute(
                                    "update store_sales set ss_net_paid=ss_net_paid \
                                where ctid=(select ctid from store_sales limit 1)",
                                )
                                .await
                        } else {
                            b.admin.execute(DUP_INJECT).await
                        };
                        barrier.2.notify_one();
                        w
                    };
                    let (r, w) = tokio::join!(s.mid.run_sql_with(&ctx, &s.probe, &s.refs), writer);
                    w?;
                    barrier.0.store(false, std::sync::atomic::Ordering::SeqCst);
                    r
                };
                let row = json!({"trial":trial, "case":case, "mode":if detach {"tx-precheck"} else {"tx-bound"},
                    "outcome":classify(&r), "response":match r { Ok(v)=>v, Err(e)=>json!({"error":format!("{e:#}")}) },
                    "stats":s.mid.stats_json(), "artificial_interleaving":case!="violation_before_call"});
                eprintln!("matched-C: {} {} trial {} -> {}", row["mode"], case, trial, row["outcome"]);
                rows.push(row);
                std::fs::write(format!("{out}/c-progress.json"), serde_json::to_string_pretty(&rows)?)?;
                b.reset(&s).await?;
            }
        }
    }
    Ok(json!({"rows":rows,"version_source":"transactional in both modes", "performance_measurement":false}))
}

async fn mech_b_uses(mid: &Middle, keys: &[String], agent: usize, seed: u64) -> Result<Vec<Value>> {
    use rand::{seq::SliceRandom, SeedableRng};
    let mut order = keys.to_vec();
    order.shuffle(&mut rand::rngs::StdRng::seed_from_u64(seed + agent as u64));
    let ctx = Ctx::new(&format!("R{agent}"), "fixed-sharing", "use");
    let mut out = vec![];
    for key in order {
        let start = Instant::now();
        let r = mid.use_metric(&ctx, &key).await?;
        out.push(json!({"key":key,"status":r["status"],"ms":start.elapsed().as_secs_f64()*1000.0}));
    }
    Ok(out)
}

async fn mechanism_b(url: &str, out: &str) -> Result<Value> {
    use rand::{seq::SliceRandom, SeedableRng};
    let admin = Db::connect(url, 2, false)?;
    admin.query(QKind::Meta, &metricbench::fixture(100_000)).await?;
    etl::setup(&admin).await?;
    scenario::setup(&admin).await?;
    for i in 0..16 {
        admin
            .query(
                QKind::Meta,
                &format!(
                    "create table mb_fact{i} as table store_sales; \
            create table mb_date{i} as table date_dim; analyze mb_fact{i}; analyze mb_date{i}"
                ),
            )
            .await?;
    }
    let base = seeded_metrics().into_iter().find(|(id, _)| *id == "M1").unwrap().1;
    let mut cells = vec![];
    let mut order = vec![];
    for rep in 0..3 {
        let mut block = vec![];
        for reuse in [1, 2, 4, 8] {
            for policy in ["definition", "definition-cache", "condition"] {
                for arrival in ["staggered", "burst"] {
                    block.push((rep, reuse, policy, arrival));
                }
            }
        }
        block.shuffle(&mut rand::rngs::StdRng::seed_from_u64(20261029 + rep as u64));
        order.extend(block);
    }
    std::fs::write(format!("{out}/b-order.json"), serde_json::to_string_pretty(&order)?)?;
    for (rep, reuse, policy, arrival) in order {
        let db = Arc::new(Db::connect(url, 8, true)?);
        let cfg = MiddleConfig {
            name: policy.into(),
            metric_maint: if policy == "condition" { Maint::Condition } else { Maint::Definition },
            cond_reuse: policy == "condition",
            sql_cache: policy == "definition-cache",
            result_cache: false,
            version_ttl_ms: 0,
            ..Default::default()
        };
        let mid = Middle::new(db.clone(), cfg).await?;
        let ctx = Ctx::new("admin", "fixed-sharing", "seed");
        let mut keys = vec![];
        let mut definitions = vec![];
        for i in 0..16 {
            let mut m = base.clone();
            m.name = format!("unit_conversion_{i}");
            m.definition = m.name.clone();
            m.fact = format!("mb_fact{}", i / reuse);
            m.time.as_mut().unwrap().dim = format!("mb_date{}", i / reuse);
            m.measure = format!("sum(ss_net_paid) * {}", i + 1);
            // Independent SQL oracle: the existing base oracle on the same tables,
            // with the constant unit conversion applied outside the subquery.
            let base_gold = metricbench::gold_period("M1", &Period::month(2001, 3))
                .replace("store_sales", &m.fact)
                .replace("date_dim", &m.time.as_ref().unwrap().dim);
            let gold = format!("select ({}) * {}", base_gold.trim().trim_end_matches(';'), i + 1);
            let r = mid.seed_metric(&ctx, m.clone(), Ask::Single { period: Period::month(2001, 3) }, 2, &gold).await?;
            ensure!(r["promoted"] == true, "B admission failed: {r}");
            keys.push(r["key"].as_str().unwrap().to_string());
            definitions.push(m);
        }
        mech_b_uses(&mid, &keys, 0, 0).await?;
        // Warm the same physical dataset and apply equal writes to every pair.
        for i in 0..16 {
            admin.query(QKind::Meta, &format!("select sum(ss_net_paid) from mb_fact{i}; select count(*) from mb_date{i}")).await?;
            admin
                .execute(&format!("update mb_fact{i} set ss_net_paid=ss_net_paid where ctid=(select ctid from mb_fact{i} limit 1)"))
                .await?;
            metricbench::log_batch(&admin, &format!("mb_fact{i}"), "fixed-sharing benign write").await?;
            admin.execute(&format!("update mb_date{i} set d_date_sk=d_date_sk where ctid=(select ctid from mb_date{i} limit 1)")).await?;
            metricbench::log_batch(&admin, &format!("mb_date{i}"), "fixed-sharing benign write").await?;
        }
        mid.invalidate_versions();
        mid.take_metric_events();
        let start = Instant::now();
        let before = db.meter.snap();
        let mut uses = vec![];
        if arrival == "burst" {
            for r in futures::future::join_all((0..8).map(|agent| mech_b_uses(&mid, &keys, agent, rep as u64 * 1000))).await {
                uses.extend(r?);
            }
        } else {
            for agent in 0..8 {
                uses.extend(mech_b_uses(&mid, &keys, agent, rep as u64 * 1000).await?);
            }
        }
        let elapsed = start.elapsed().as_secs_f64();
        let meter = crate::db::diff(&before, &db.meter.snap());
        let events = mid.take_metric_events();
        let unavailable = uses.iter().filter(|u| u["status"] != "valid").count();
        let mut actions: BTreeMap<String, u64> = BTreeMap::new();
        for c in events.iter().filter(|e| e["event"] == "maintenance").flat_map(|e| e["conditions"].as_array().into_iter().flatten()) {
            *actions.entry(c["action"].as_str().unwrap_or("unknown").into()).or_default() += 1;
        }
        let row = json!({"repeat":rep,"reuse_factor":reuse,"policy":policy,"arrival":arrival,"definitions":16,
            "groups":16/reuse,"rows_per_fact":100000,"agents":8,"wall_seconds":elapsed,"db":meter,
            "unavailable":unavailable,"uses":uses,"condition_actions":actions,"events":events,
            "definition_inputs":definitions});
        eprintln!("fixed-B: r{rep} reuse{reuse} {policy} {arrival}: {} ms, unavailable {unavailable}", row["db"]["db_ms"]);
        std::fs::write(format!("{out}/b-r{rep}-k{reuse}-{policy}-{arrival}.json"), serde_json::to_string_pretty(&row)?)?;
        cells.push(row);
    }
    Ok(json!({"cells":cells,"design":"fixed 16 definitions, exact shared conditions, warmed fixed physical dataset"}))
}

#[tokio::test]
#[ignore = "isolated mechanism supplement; no LLM calls"]
async fn postgres_mechanism_supplement() -> Result<()> {
    let _ = dotenvy::dotenv();
    let url = std::env::var("AGENTDB_TEST_URL").context("AGENTDB_TEST_URL required")?;
    let part = std::env::var("MECHANISM_PART").unwrap_or("C".into());
    ensure!(part == "B" || part == "C", "unknown supplement");
    let admin = Db::connect(&url, 1, false)?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let name = format!("agentdb_mech_{}_{stamp}", std::process::id());
    let mut test_url = reqwest::Url::parse(&url)?;
    test_url.set_path(&format!("/{name}"));
    let out = format!("results/mechanism-systems-20261029/{part}-{stamp}");
    std::fs::create_dir_all(&out)?;
    admin.query(QKind::Meta, &format!("create database {name}")).await?;
    let result = tokio::time::timeout(Duration::from_secs(3600), async {
        if part == "B" {
            mechanism_b(test_url.as_str(), &out).await
        } else {
            mechanism_c(test_url.as_str(), &out).await
        }
    })
    .await;
    let cleanup = admin.query(QKind::Meta, &format!("drop database {name} with (force)")).await;
    let report = match &result {
        Ok(Ok(r)) => r.clone(),
        Ok(Err(e)) => json!({"error":format!("{e:#}")}),
        Err(_) => json!({"error":"timeout"}),
    };
    std::fs::write(format!("{out}/report.json"), serde_json::to_string_pretty(&json!({"report":report,"cleaned_up":cleanup.is_ok()}))?)?;
    eprintln!("saved {out}/report.json");
    cleanup?;
    result.context("supplement timeout")??;
    Ok(())
}
