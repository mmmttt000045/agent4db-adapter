//! Reproducible synthetic research workload; never claims to be a public benchmark.
use crate::benchmark::percentile;
use crate::db::{Db, QKind};
use crate::llm::Provider;
use crate::middle::{Ctx, Middle, MiddleConfig, Scope};
use crate::optimizer::Optimizer;
use crate::sim::diff;
use anyhow::{ensure, Context, Result};
use futures::{stream, StreamExt};
use rand::{rngs::StdRng, seq::SliceRandom, Rng, SeedableRng};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

const DOMAINS: [&str; 3] = ["retail", "billing", "delivery"];
const MODES: [&str; 5] = ["A", "B", "C", "D", "M"];
const STRUCTURES: [&str; 16] = [
    "range_sum",
    "group_having",
    "dimension_join",
    "conditional_aggregate",
    "cte_preaggregate",
    "window_rank",
    "correlated_exists",
    "anti_join",
    "union_all",
    "left_join_missing",
    "nested_aggregate",
    "window_lag",
    "status_grain",
    "null_semantics",
    "grouping_sets",
    "many_to_many_trap",
];

#[derive(Clone, Debug, clap::Args, Serialize)]
pub struct Options {
    /// 每个业务域事实行数；实际大小由 PostgreSQL 测量，不按行数宣称 GB。
    #[arg(long, default_value_t = 100_000, value_parser = clap::value_parser!(u32).range(1000..=50_000_000))]
    rows: u32,
    #[arg(long, default_value_t = 24, value_parser = clap::value_parser!(u32).range(1..=128))]
    agents: u32,
    #[arg(long, default_value_t = 16, value_parser = clap::value_parser!(u32).range(1..=1024))]
    variants: u32,
    #[arg(long, default_value_t = 2, value_parser = clap::value_parser!(u32).range(1..=16))]
    repeats: u32,
    /// 五组轮换，5 的倍数平衡运行位置。
    #[arg(long, default_value_t = 5, value_parser = clap::value_parser!(u32).range(1..=40))]
    rounds: u32,
    #[arg(long, default_value_t = 42)]
    seed: u64,
    /// 去掉结果缓存的敏感性实验，五组统一设置。
    #[arg(long)]
    no_result_cache: bool,
    /// 额外的、适配到本实验 schema 的公开任务清单；与自建负载分开计数。
    #[arg(long)]
    corpus: Option<String>,
    /// 只做大数据容量与只读查询校验，不运行消融，不产生策略收益结论。
    #[arg(long)]
    capacity_only: bool,
    /// 从已有逐轮文件恢复，完整单元不重跑；使用相同实验参数。
    #[arg(long, conflicts_with = "capacity_only")]
    #[serde(skip_serializing)]
    resume: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct Task {
    id: String,
    family: String,
    split: String,
    domain: String,
    sql: String,
    oracle_sql: String,
    /// Deliberately unsafe business query; rejection is the correct outcome.
    unsafe_query: bool,
    source: String,
    #[serde(default)]
    adaptation: Option<String>,
}

fn fixture(domain: &str, n: u32) -> String {
    let p = domain;
    format!(
        r#"
create table {p}_label ({p}_l_id int primary key, {p}_l_region int, {p}_l_name text);
insert into {p}_label select g,g%64,'segment-'||g from generate_series(1,512) g;
create table {p}_entity ({p}_e_id int primary key, {p}_e_region int, {p}_e_label int, {p}_e_name text);
insert into {p}_entity select g,g%64,(g-1)%512+1,'account-'||g from generate_series(1,4096) g;
create table {p}_fact ({p}_f_id bigint primary key, {p}_f_entity int, {p}_f_amount bigint,
 {p}_f_day int, {p}_f_channel int, {p}_f_discount int, {p}_f_reference text);
insert into {p}_fact select g,(g-1)%4096+1,100+g%997,g%365,g%8,
 case when g%7=0 then null else g%11 end,md5(g::text) from generate_series(1,{n}) g;
create index on {p}_fact({p}_f_entity);
create table {p}_detail ({p}_d_id bigint primary key,{p}_d_fact bigint,{p}_d_amount bigint,{p}_d_kind int);
insert into {p}_detail select (g-1)*3+k,g,10+g%97,k from generate_series(1,{n}) g cross join generate_series(1,3) k;
create index on {p}_detail({p}_d_fact);
create table {p}_history ({p}_h_fact bigint,{p}_h_amount bigint,{p}_h_state text);
insert into {p}_history select {p}_f_id,{p}_f_amount,'complete' from {p}_fact where {p}_f_id%5<>0;
create index on {p}_history({p}_h_fact);
analyze {p}_label; analyze {p}_entity; analyze {p}_fact; analyze {p}_detail; analyze {p}_history;
"#
    )
}

fn task(p: &str, kind: usize, variant: u32, rows: u32, seed: u64, drift: bool) -> Task {
    // Held-out ranges start beyond training's first 100 rows. Keep queries bounded at all scales.
    let lo = 101 + ((u64::from(variant) * 7919).wrapping_add(seed.wrapping_mul(31)) % u64::from(rows - 400)) as u32;
    let hi = (lo + 255).min(rows);
    let f = format!("{p}_fact");
    let id = format!("{p}_f_id");
    let amount = format!("{p}_f_amount");
    let range = format!("{id} between {lo} and {hi}");
    let base = format!("select {id} as id,{amount} as amount,{p}_f_channel as channel from {f} where {range}");
    let (sql, oracle_sql) = match kind {
        0 => (format!("select sum({amount})::bigint as v from {f} where {range}"), format!("select sum(amount)::bigint as v from ({base}) q")),
        1 => (format!("select {p}_f_channel as k,sum({amount})::bigint as v from {f} where {range} group by {p}_f_channel having count(*)>1 order by k"),
            format!("select channel as k,sum(amount)::bigint as v from ({base}) q group by channel having count(*)>1 order by k")),
        2 => (format!("select {p}_e_region as k,sum({amount})::bigint as v from {f} join {p}_entity on {p}_f_entity={p}_e_id where {range} group by {p}_e_region order by k"),
            format!("select (select {p}_e_region from {p}_entity where {p}_e_id={p}_f_entity) as k,sum({amount})::bigint as v from {f} where {range} group by k order by k")),
        3 => (format!("select sum(case when {p}_f_channel<4 then {amount} else 0 end)::bigint as v from {f} where {range}"),
            format!("select coalesce(sum({amount}) filter(where {p}_f_channel<4),0)::bigint as v from {f} where {range}")),
        4 => (format!("with a as (select {p}_d_fact as fk,sum({p}_d_amount)::bigint as v from {p}_detail where {p}_d_fact between {lo} and {hi} group by {p}_d_fact) select sum(v)::bigint as v from a"),
            format!("select sum({p}_d_amount)::bigint as v from {p}_detail where {p}_d_fact between {lo} and {hi}")),
        5 => (format!("select id as k,amount as v from (select id,amount,row_number() over(order by amount desc,id) as rn from ({base}) b) w where rn<=10 order by v desc,k"),
            format!("select {id} as k,{amount} as v from {f} where {range} order by v desc,k limit 10")),
        6 => (format!("select count(*) as v from {f} where {range} and exists(select 1 from {p}_history where {p}_h_fact={id} and {p}_h_state = 'complete')"),
            format!("select count(*) as v from {f} where {range} and {id} in(select {p}_h_fact from {p}_history where {p}_h_state = 'complete')")),
        7 => (format!("select count(*) as v from {f} where {range} and not exists(select 1 from {p}_history where {p}_h_fact={id} and {p}_h_state = 'complete')"),
            format!("select count(*) as v from generate_series({lo},{hi}) g where g%5=0")),
        8 => (format!("select sum(v)::bigint as v from (select {amount} as v from {f} where {range} and {p}_f_channel<4 union all select {amount} as v from {f} where {range} and {p}_f_channel>=4) u"),
            format!("select sum({amount})::bigint as v from {f} where {range}")),
        9 => (format!("select count(*) as v from {f} left join {p}_history on {id}={p}_h_fact and {p}_h_state = 'complete' where {range} and {p}_h_fact is null"),
            format!("select count(*) as v from {f} where {range} and {id}%5=0")),
        10 => (format!("select count(*) as v from {f} where {range} and {amount}>(select avg({amount}) from {f} where {range})"),
            format!("with b as ({base}),a as(select avg(amount) as v from b) select count(*) as v from b,a where amount>v")),
        11 => (format!("select coalesce(sum(delta),0)::bigint as v from(select amount-lag(amount) over(order by id) as delta from ({base}) b) w"),
            format!("select ((select {amount} from {f} where {id}={hi})-(select {amount} from {f} where {id}={lo}))::bigint as v")),
        12 => (format!("select sum({p}_h_amount)::bigint as v from {p}_history where {p}_h_fact between {lo} and {hi} and {p}_h_state = 'complete'"),
            format!("select sum(100+g%997)::bigint as v from generate_series({lo},{hi}) g where g%5<>0")),
        13 => (format!("select count(*)-count({p}_f_discount) as v from {f} where {range}"),
            format!("select count(*) as v from {f} where {range} and {p}_f_discount is null")),
        14 => (format!("select {p}_f_channel as k,sum({amount})::bigint as v from {f} where {range} group by grouping sets(({p}_f_channel),()) order by k nulls last"),
            format!("select * from(select {p}_f_channel as k,sum({amount})::bigint as v from {f} where {range} group by {p}_f_channel union all select null::int as k,sum({amount})::bigint as v from {f} where {range}) u order by k nulls last")),
        _ => (format!("select sum({p}_e_id)::bigint as v from {p}_entity join {p}_label on {p}_e_region={p}_l_region where {p}_e_id between {} and {}",variant%32+1,variant%32+32),
            format!("select sum({p}_e_id)::bigint as v from {p}_entity where {p}_e_id between {} and {}",variant%32+1,variant%32+32)),
    };
    Task {
        id: format!("{p}-k{kind}-v{variant}"),
        family: STRUCTURES[kind].into(),
        split: if p == "delivery" {
            "domain_holdout"
        } else if kind >= 4 {
            "structure_holdout"
        } else {
            "parameter_holdout"
        }
        .into(),
        domain: p.into(),
        sql,
        oracle_sql,
        unsafe_query: kind == 15,
        source: format!("synthetic-v1; phase={}", if drift { "shifted" } else { "stable" }),
        adaptation: None,
    }
}

fn tasks(o: &Options, seed: u64, drift: bool) -> Result<Vec<Task>> {
    let mut all = vec![];
    for p in DOMAINS {
        for k in 0..16 {
            for v in 0..o.variants {
                all.push(task(p, k, v, o.rows, seed, drift));
            }
        }
    }
    if let Some(path) = &o.corpus {
        let imported: Vec<Task> = serde_json::from_str(&std::fs::read_to_string(path)?)?;
        for t in &imported {
            ensure!(t.source.starts_with("https://"), "外部任务必须提供 https 来源");
            ensure!(t.adaptation.as_ref().is_some_and(|s| !s.trim().is_empty()), "外部任务必须解释适配范围");
            ensure!(DOMAINS.contains(&t.domain.as_str()), "外部任务 domain 必须对应本实验业务域");
            ensure!(t.split == "external_holdout", "外部任务 split 必须为 external_holdout");
            ensure!(!t.sql.contains(';') && !t.oracle_sql.contains(';'), "外部任务只能是单条查询");
        }
        all.extend(imported);
    }
    ensure!(all.iter().map(|t| &t.id).collect::<BTreeSet<_>>().len() == all.len(), "任务 ID 重复");
    Ok(all)
}

async fn gold(db: &Db, tasks: &[Task]) -> Result<Vec<Value>> {
    let mut out = vec![];
    for task in tasks {
        let reference = db.query(QKind::Exec, &task.oracle_sql).await.with_context(|| format!("oracle {}", task.id))?.to_json(1000);
        if !task.unsafe_query {
            let actual = db.query(QKind::Exec, &task.sql).await.with_context(|| format!("candidate {}", task.id))?.to_json(1000);
            ensure!(equivalent(&actual, &reference), "候选 SQL 与独立参考不一致: {}", task.id);
        }
        ensure!(reference["truncated"] == false, "参考结果被截断");
        out.push(reference);
    }
    Ok(out)
}

fn equivalent(a: &Value, b: &Value) -> bool {
    a["truncated"] == false && b["truncated"] == false && a["rows"].is_array() && a["rows"] == b["rows"] && a["row_count"] == b["row_count"]
}

fn config(mode: &str, o: &Options, seed: u64) -> MiddleConfig {
    MiddleConfig {
        name: mode.into(),
        scope: if matches!(mode, "A" | "C") { Scope::Agent } else { Scope::Global },
        singleflight: false,
        feedback: true,
        trace_checks: true,
        audit_seed: Some(seed),
        max_rows: 1000,
        result_cache: !o.no_result_cache,
        ..Default::default()
    }
}

fn join(p: &str, a: &str, b: &str, ac: &str, bc: &str) -> Value {
    json!({"left":format!("{p}_{a}"),"right":format!("{p}_{b}"),"on":[[format!("{p}_{ac}"),format!("{p}_{bc}")]]})
}

async fn train(mid: &Middle, agent: usize) -> Result<Value> {
    let ctx = Ctx::new(&format!("agent-{agent}"), "training", "training");
    let mut evidence = vec![];
    for args in [
        join("retail", "fact", "entity", "f_entity", "e_id"),
        join("retail", "entity", "label", "e_label", "l_id"),
        join("retail", "detail", "fact", "d_fact", "f_id"),
    ] {
        evidence.push(mid.call_tool(&ctx, "check_join", &args).await?);
    }
    for k in 0..4 {
        let mut t = task("retail", k, 0, 1000, 0, false);
        // Training occupies only [1,100]; evaluation ranges start at 101.
        t.sql = t.sql.replace("101 and 356", "1 and 100");
        evidence.push(mid.run_sql(&ctx, &t.sql).await?);
    }
    Ok(json!({"agent":agent,"evidence":evidence}))
}

async fn phase(mids: &[Arc<Middle>], o: &Options, tasks: Arc<Vec<Task>>, gold: Arc<Vec<Value>>, seed: u64) -> Result<Value> {
    let db = &mids[0].db;
    let before = db.meter.snap();
    let mut schedule = vec![];
    for repeat in 0..o.repeats {
        for index in 0..tasks.len() {
            schedule.push((index, repeat));
        }
    }
    schedule.shuffle(&mut StdRng::seed_from_u64(seed));
    let mut lanes = vec![vec![]; o.agents as usize];
    for (i, item) in schedule.into_iter().enumerate() {
        lanes[i % o.agents as usize].push(item);
    }
    let start = Instant::now();
    let groups=stream::iter(lanes.into_iter().enumerate()).map(|(agent,lane)| {
        let mid=mids[agent].clone(); let tasks=tasks.clone(); let gold=gold.clone();
        async move {
            let mut events=vec![];
            for (position,(index,repeat)) in lane.into_iter().enumerate() {
                let t=&tasks[index];
                let ctx=Ctx::new(&format!("agent-{agent}"),&format!("session-{}",position/8),&t.id);
                let start=Instant::now();
                // Explicit exploration is part of the measured task, not free pretraining.
                let profile=mid.call_tool(&ctx,"describe_table",&json!({"table":format!("{}_fact",t.domain)})).await;
                let response=mid.run_sql(&ctx,&t.sql).await.unwrap_or_else(|e|json!({"error":format!("{e:#}")}));
                let rejected=response["rejected"]==true;
                let correct=profile.is_ok() && if t.unsafe_query {rejected} else {equivalent(&response["result"],&gold[index])};
                events.push(json!({"agent":agent,"task":t.id,"family":t.family,"split":t.split,"source":t.source,
                    "repeat":repeat,"correct":correct,"false_accept":t.unsafe_query && response.get("result").is_some(),
                    "false_reject":!t.unsafe_query && rejected,"error":response.get("error").is_some() || profile.is_err(),
                    "latency_ms":start.elapsed().as_secs_f64()*1000.0,"response":response,
                    "profile":profile.unwrap_or_else(|e|json!({"error":format!("{e:#}")})),"expected":if t.unsafe_query {json!({"rejected":true})} else {gold[index].clone()}}));
            }
            events
        }
    }).buffer_unordered(o.agents as usize).collect::<Vec<_>>().await;
    let wall = start.elapsed().as_secs_f64();
    let events: Vec<_> = groups.into_iter().flatten().collect();
    let times: Vec<_> = events.iter().filter_map(|e| e["latency_ms"].as_f64()).collect();
    let mut breakdown = serde_json::Map::new();
    for field in ["family", "split"] {
        let mut by = serde_json::Map::new();
        for key in events.iter().filter_map(|e| e[field].as_str()).collect::<BTreeSet<_>>() {
            let selected: Vec<_> = events.iter().filter(|e| e[field] == key).collect();
            by.insert(key.into(), json!({"tasks":selected.len(),"correct":selected.iter().filter(|e|e["correct"]==true).count()}));
        }
        breakdown.insert(field.into(), Value::Object(by));
    }
    Ok(json!({"tasks":events.len(),"safe_tasks":tasks.iter().filter(|t| !t.unsafe_query).count()*o.repeats as usize,
        "unsafe_tasks":tasks.iter().filter(|t| t.unsafe_query).count()*o.repeats as usize,"correct":events.iter().filter(|e|e["correct"]==true).count(),
        "false_accept":events.iter().filter(|e|e["false_accept"]==true).count(),"false_reject":events.iter().filter(|e|e["false_reject"]==true).count(),
        "errors":events.iter().filter(|e|e["error"]==true).count(),"p95_ms":percentile(&times,0.95),"wall_seconds":wall,
        "database":diff(&before,&db.meter.snap()),"breakdown":breakdown,"events":events}))
}

async fn change(admin: &Db, shifted: bool) -> Result<()> {
    for p in DOMAINS {
        let sql = if shifted {
            format!("insert into {p}_history select {p}_h_fact,{p}_h_amount,'pending' from {p}_history where {p}_h_fact%4=0 and {p}_h_state='complete'; update {p}_fact set {p}_f_amount={p}_f_amount*3 where {p}_f_id%8=0;")
        } else {
            format!("delete from {p}_history where {p}_h_state='pending'; update {p}_fact set {p}_f_amount=100+{p}_f_id%997 where {p}_f_id%8=0;")
        };
        admin.query(QKind::Meta, &sql).await?;
        for table in [format!("{p}_fact"), format!("{p}_history")] {
            admin
                .query(
                    QKind::Meta,
                    &format!(
                        "insert into etl_batch_log(table_name,batch_id) select '{table}',coalesce(max(batch_id),0)+1 from etl_batch_log;"
                    ),
                )
                .await?;
            admin.query(QKind::Meta, &format!("vacuum analyze {table}")).await?;
        }
    }
    Ok(())
}

async fn manage(manager: &Option<Optimizer>, mid: &Middle, stage: &str) -> Value {
    if let Some(manager) = manager {
        let start = Instant::now();
        // Regression check on evidence recorded since the last apply comes before a new proposal.
        let watch = manager.watch(&mid.fb).map_err(|e| format!("{e:#}"));
        match manager.propose(&mid.fb).await {
            Ok(p) => {
                json!({"stage":stage,"watch":watch,"proposal":p,"apply":manager.apply(p.id,&mid.fb).map_err(|e|e.to_string()),"wall_ms":start.elapsed().as_secs_f64()*1000.0})
            }
            Err(e) => json!({"stage":stage,"watch":watch,"error":format!("{e:#}"),"wall_ms":start.elapsed().as_secs_f64()*1000.0}),
        }
    } else {
        Value::Null
    }
}

struct Corpus {
    stable: Arc<Vec<Task>>,
    shifted: Arc<Vec<Task>>,
    gold_stable: Arc<Vec<Value>>,
    gold_shifted: Arc<Vec<Value>>,
}

// Deliberate hard cases, kept outside the factorial timing totals. These expose
// the limits of the current string-based SQL reviewer rather than hiding them.
async fn robustness(mid: &Middle, reference: &Db) -> Result<Value> {
    let ctx = Ctx::new("agent-0", "robustness", "semantic-boundaries");
    let cases = [
        ("legal_many_to_many_distinct", false,
         "select count(distinct retail_e_id) as v from retail_entity join retail_label on retail_e_region=retail_l_region where retail_e_id between 1 and 32",
         "select count(*) as v from retail_entity where retail_e_id between 1 and 32"),
        ("grain_predicate_or_bypass", true,
         "select sum(retail_h_amount)::bigint as v from retail_history where retail_h_fact between 101 and 1000 and (retail_h_state = 'complete' or retail_h_fact > 0)",
         "select sum(retail_h_amount)::bigint as v from retail_history where retail_h_fact between 101 and 1000 and retail_h_state = 'complete'"),
    ];
    let mut events = vec![];
    for (name, unsafe_query, sql, oracle) in cases {
        let expected = reference.query(QKind::Exec, oracle).await?.to_json(1000);
        let raw = reference.query(QKind::Exec, sql).await?.to_json(1000);
        ensure!(equivalent(&raw, &expected) != unsafe_query, "边界案例缺少有效判据: {name}");
        let response = mid.run_sql(&ctx, sql).await.unwrap_or_else(|e| json!({"error":e.to_string()}));
        let correct = if unsafe_query { response["rejected"] == true } else { equivalent(&response["result"], &expected) };
        events.push(json!({"case":name,"sql":sql,"oracle_sql":oracle,"business_expected":expected,"raw_result":raw,
            "response":response,"correct":correct,"unsafe_query":unsafe_query}));
    }
    Ok(json!({"events":events,"scope":"semantic boundary tests; excluded from factorial costs"}))
}

async fn trial(url: &str, admin: &Db, o: &Options, pool: usize, cell: (&str, u64), corpus: &Corpus, out: &str) -> Result<Value> {
    let (mode, seed) = cell;
    change(admin, false).await?;
    // Equal warmup. This is a warm-storage experiment; no OS-cache eviction claim.
    for p in DOMAINS {
        admin.query(QKind::Meta, &format!("select sum({p}_f_amount) from {p}_fact")).await?;
    }
    let db = Arc::new(Db::connect(url, pool, true)?);
    let start = Instant::now();
    let mut unique = vec![];
    for _ in 0..if matches!(mode, "A" | "C") { o.agents } else { 1 } {
        let mid = Arc::new(Middle::new(db.clone(), config(mode, o, seed)).await?);
        if matches!(mode, "A" | "B") {
            mid.fb.set_priority(Some(vec!["KeyUnique".into(), "RowConservation".into(), "SampleFanout".into()]));
        }
        unique.push(mid);
    }
    let mids = if unique.len() == 1 { vec![unique[0].clone(); o.agents as usize] } else { unique.clone() };
    let mut training = vec![];
    for (i, mid) in mids.iter().enumerate() {
        training.push(train(mid, i).await?);
    }
    let manager = if mode == "M" { Some(Optimizer::new(Provider::Mock, out)?) } else { None };
    let first_decision = manage(&manager, &unique[0], "after_training").await;
    let training_cost = json!({"wall_seconds":start.elapsed().as_secs_f64(),"database":db.meter.snap(),"events":training,
        "traces":unique.iter().flat_map(|m|m.take_check_traces()).collect::<Vec<_>>()});
    let stable = phase(&mids, o, corpus.stable.clone(), corpus.gold_stable.clone(), seed).await?;
    let stable_traces: Vec<_> = unique.iter().flat_map(|m| m.take_check_traces()).collect();
    change(admin, true).await?;
    let recovery_start = Instant::now();
    let before = db.meter.snap();
    let mut recovery = vec![];
    // Explicit ETL notification is equal in every cell. Recovery costs are included.
    for mid in &unique {
        mid.invalidate_versions();
    }
    for (i, mid) in mids.iter().enumerate() {
        for p in DOMAINS {
            let ctx = Ctx::new(&format!("agent-{i}"), "drift", "grain-recovery");
            let args = join(p, "history", "fact", "h_fact", "f_id");
            let response = mid.call_tool(&ctx, "check_join", &args).await.unwrap_or_else(|e| json!({"error":format!("{e:#}")}));
            let invalid = mid
                .run_sql(&ctx, &format!("select sum({p}_h_amount)::bigint from {p}_history"))
                .await
                .unwrap_or_else(|e| json!({"error":e.to_string()}));
            recovery.push(json!({"agent":i,"domain":p,"join":response,"unsafe_sum":invalid,"correct":invalid["rejected"]==true}));
        }
    }
    let recovery = json!({"events":recovery,"wall_seconds":recovery_start.elapsed().as_secs_f64(),"database":diff(&before,&db.meter.snap()),
        "traces":unique.iter().flat_map(|m|m.take_check_traces()).collect::<Vec<_>>(),"notification":"explicit ETL batch + invalidate_versions"});
    let second_decision = manage(&manager, &unique[0], "after_drift").await;
    let shifted = phase(&mids, o, corpus.shifted.clone(), corpus.gold_shifted.clone(), seed).await?;
    let shifted_traces: Vec<_> = unique.iter().flat_map(|m| m.take_check_traces()).collect();
    let total_database = db.meter.snap();
    let total_wall_seconds = start.elapsed().as_secs_f64();
    let boundary = robustness(&unique[0], admin).await?;
    Ok(json!({"mode":mode,"seed":seed,"config":config(mode,o,seed),"training":training_cost,"stable":stable,"shifted":shifted,
        "recovery":recovery,"decisions":[first_decision,second_decision],"stable_traces":stable_traces,"shifted_traces":shifted_traces,
        "total_database":total_database,"total_wall_seconds":total_wall_seconds,"robustness":boundary,
        "final_states":unique.iter().map(|m|json!({"stats":m.stats_json(),"knowledge":m.knowledge()})).collect::<Vec<_>>()}))
}

fn contrasts(runs: &[Value], rounds: u32, seed: u64) -> Value {
    let mut result = vec![];
    for (base, target) in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("A", "D"), ("B", "M"), ("D", "M")] {
        for metric in ["db_ms", "queries"] {
            let mut delta = vec![];
            let mut reduction = vec![];
            for round in 0..rounds {
                let cost = |mode: &str| {
                    runs.iter().find(|r| r["round"] == round && r["mode"] == mode).unwrap()["total_database"][metric].as_f64().unwrap()
                };
                let a = cost(base);
                let b = cost(target);
                delta.push(b - a);
                reduction.push((a - b) / a * 100.0);
            }
            let mean = |v: &[f64]| v.iter().sum::<f64>() / v.len() as f64;
            let mut rng = StdRng::seed_from_u64(seed);
            let mut bootstrap = vec![];
            for _ in 0..2000 {
                bootstrap.push((0..delta.len()).map(|_| delta[rng.gen_range(0..delta.len())]).sum::<f64>() / delta.len() as f64);
            }
            result.push(json!({"baseline":base,"target":target,"metric":metric,"paired_deltas":delta,"mean_delta":mean(&delta),
                "mean_reduction_percent":mean(&reduction),"bootstrap_interval_95":[percentile(&bootstrap,0.025),percentile(&bootstrap,0.975)],
                "interpretation":"descriptive paired-round bootstrap; small sample, one machine; not a significance claim"}));
        }
    }
    let interactions: Vec<_> = (0..rounds)
        .map(|round| {
            let cost = |mode: &str| {
                runs.iter().find(|r| r["round"] == round && r["mode"] == mode).unwrap()["total_database"]["db_ms"].as_f64().unwrap()
            };
            cost("D") - cost("B") - cost("C") + cost("A")
        })
        .collect();
    json!({"paired":result,"interaction_db_ms":interactions})
}

fn markdown(report: &Value) -> String {
    if report["capacity_only"] == true {
        return format!("# 大数据容量校验\n\n实际表及索引大小：{:.3} GiB；基线数据 {} 行。\n\n{} 个范围查询与独立参考结果一致。\n\n此运行只验证装载和范围查询，不包含 A/B/C/D/Mock 消融，不能用于声称大规模策略收益，也不能代表全表分析吞吐。\n\n配置：`{}`\n",
            report["dataset"]["relation_bytes"].as_f64().unwrap()/1073741824.0,report["dataset"]["rows"],
            report["capacity_checks"],report["options"]);
    }
    let mut s=format!("# 多业务域 adapter 研究实验\n\n自建 synthetic-v1；不是 TPC / Spider / 生产轨迹。真实 LLM 未运行。\n\n配置：`{}`\n\n实际基线表及索引大小：{:.3} GiB；数据行数：{}。构建：{}。\n\n16 种结构 × 3 个同构业务域 = 48 个领域查询族；不是 48 种独立 SQL 结构。\n\n|组|任务|正确|错误放行|错误拦截|执行错误|全程 DB 秒|全程 SQL|任务 P95 ms|\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n",
        report["options"],report["dataset"]["relation_bytes"].as_f64().unwrap_or(0.0)/1073741824.0,report["dataset"]["rows"],report["build"]);
    for mode in MODES {
        let runs: Vec<_> = report["runs"].as_array().unwrap().iter().filter(|r| r["mode"] == mode).collect();
        let phases: Vec<_> = runs.iter().flat_map(|r| [&r["stable"], &r["shifted"]]).collect();
        let sum = |key: &str| phases.iter().map(|p| p[key].as_u64().unwrap_or(0)).sum::<u64>();
        let times: Vec<_> = phases.iter().flat_map(|p| p["events"].as_array().unwrap()).filter_map(|e| e["latency_ms"].as_f64()).collect();
        s.push_str(&format!(
            "|{mode}|{}|{}|{}|{}|{}|{:.2}|{}|{:.2}|\n",
            sum("tasks"),
            sum("correct"),
            sum("false_accept"),
            sum("false_reject"),
            sum("errors"),
            runs.iter().map(|r| r["total_database"]["db_ms"].as_f64().unwrap()).sum::<f64>() / 1000.0,
            runs.iter().map(|r| r["total_database"]["queries"].as_u64().unwrap()).sum::<u64>(),
            percentile(&times, 0.95)
        ));
    }
    s.push_str("\nA=本地固定，B=共享固定，C=本地统计反馈，D=共享统计反馈，M=共享 Mock 管理器。全程成本含训练、检查、恢复与测量；不含 fixture、参考答案生成、ETL 注入和等量预热。DB 时间是各 SQL 耗时之和，不是墙钟时间。\n\n## 配对成本比较\n\n正降幅表示节约。小样本区间仅供描述，正确性有退化时不能只按速度宣称获益。\n\n|对比|全程 DB 成本平均降幅|平均差 ms|配对 bootstrap 95% 区间 ms|\n|---|---:|---:|---|\n");
    for c in report["contrasts"]["paired"].as_array().unwrap().iter().filter(|c| c["metric"] == "db_ms") {
        s.push_str(&format!(
            "|{}→{}|{:.2}%|{:.2}|{}|\n",
            c["baseline"],
            c["target"],
            c["mean_reduction_percent"].as_f64().unwrap(),
            c["mean_delta"].as_f64().unwrap(),
            c["bootstrap_interval_95"]
        ));
    }
    s.push_str("\n## 反馈闭环\n\n自适应顺序只在被审计失败候选的配对回放显著更省时采纳（否则保持默认顺序）；M 的模型策略按 improvement 门槛应用，之后新证据显著变差则自动回滚。重排不改变验证结论，只影响代价。\n\n|组|adapter 数|结束时采纳自适应|被审计失败候选|未审计失败|通过的验证|\n|---|---:|---:|---:|---:|---:|\n");
    for mode in ["C", "D", "M"] {
        let states: Vec<&Value> = report["runs"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|r| r["mode"] == mode)
            .flat_map(|r| r["final_states"].as_array().into_iter().flatten())
            .collect();
        let adopted = states.iter().filter(|st| st["stats"]["feedback"]["adaptive"]["adopted"] == true).count();
        let sum = |key: &str| states.iter().map(|st| st["stats"]["feedback"]["evidence"][key].as_u64().unwrap_or(0)).sum::<u64>();
        s.push_str(&format!(
            "|{mode}|{}|{adopted}|{}|{}|{}|\n",
            states.len(),
            sum("audited_failures_total"),
            sum("unaudited_failures"),
            sum("passed")
        ));
    }
    let decisions: Vec<&Value> = report["runs"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["mode"] == "M")
        .flat_map(|r| r["decisions"].as_array().into_iter().flatten())
        .filter(|d| d.is_object())
        .collect();
    s.push_str(&format!(
        "\nM 组模型决策：生成 {} 次，应用 {} 次，未应用 {} 次（门槛或版本），自动回滚 {} 次。\n",
        decisions.iter().filter(|d| d["proposal"].is_object()).count(),
        decisions.iter().filter(|d| d["apply"]["Ok"].is_object()).count(),
        decisions.iter().filter(|d| d["apply"]["Err"].is_string()).count(),
        decisions.iter().filter(|d| d["watch"]["Ok"].is_object()).count()
    ));
    let boundary: Vec<_> =
        report["runs"].as_array().unwrap().iter().flat_map(|r| r["robustness"]["events"].as_array().into_iter().flatten()).collect();
    if !boundary.is_empty() {
        s.push_str("\n## 语义边界专项（不计入主矩阵耗时）\n\n这些专项会暴露轻量文本审查的误拦截或误放行。主负载正确率不能代替这些结果。\n\n|用例|符合预期/总数|\n|---|---:|\n");
        for name in ["legal_many_to_many_distinct", "grain_predicate_or_bypass"] {
            let selected: Vec<_> = boundary.iter().filter(|e| e["case"] == name).collect();
            s.push_str(&format!("|{name}|{}/{}|\n", selected.iter().filter(|e| e["correct"] == true).count(), selected.len()));
        }
    }
    s.push_str("\n## 边界和证据\n\n- 训练仅 retail 的简单结构与前 100 行；其余结构、delivery 域和新参数分别标注留出。评测期间允许在线反馈；属于 prequential 在线评测，不是冻结模型测试。三个域同构，跨域结论有限。\n- 每个参数实例先比较候选 SQL 与等价参考 SQL；参考通过只读直连执行，绕过 adapter。该校验验证执行一致性，不代表已经证明业务规格完全正确。所有参考成本独立记录。\n- 主矩阵关闭 singleflight，审计候选种子一致，组间全新 adapter 状态，同一连接池上限。五轮轮换平衡位置；不清空 OS 缓存。\n- 漂移同时包含事实金额热点变化和状态流水重复行。显式通知后运行恢复检查，记录错误放行与修复耗时；不是自动发现延迟。\n- describe_table 与 run_sql 构成脚本任务链；不包含真实模型规划和 token 成本。Mock 只排序检查，模型费用为零。\n- 每轮 JSON 有预期/实际结果、来源、检查顺序、执行/复用证据、知识创建者和依赖版本。任务 SQL 与参考 SQL 存在 corpus 文件。错误不被丢弃。\n- 公开任务仅在提供带来源的外部清单时纳入，单独标记 external_holdout；默认外部任务为零。\n");
    s
}

pub async fn run(url: &str, pool: usize, out: &str, o: Options) -> Result<()> {
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros();
    let directory = o.resume.clone().unwrap_or_else(|| format!("{out}/research-{stamp}"));
    std::fs::create_dir_all(&directory)?;
    // Capture build-time source, not the potentially edited working tree at run time.
    let mut fingerprint = 0xcbf29ce484222325u64;
    for source in [
        include_str!("research.rs"),
        include_str!("middle.rs"),
        include_str!("checks.rs"),
        include_str!("feedback.rs"),
        include_str!("sqlscan.rs"),
        include_str!("optimizer.rs"),
    ] {
        for b in source.bytes() {
            fingerprint = (fingerprint ^ u64::from(b)).wrapping_mul(0x100000001b3);
        }
    }
    if o.resume.is_some() {
        let previous: Value = serde_json::from_str(&std::fs::read_to_string(format!("{directory}/manifest.json"))?)?;
        ensure!(previous["options"] == serde_json::to_value(&o)? && previous["pool"] == pool, "恢复参数必须与原始 manifest 一致");
    }
    std::fs::write(
        if o.resume.is_some() { format!("{directory}/resume-{stamp}.json") } else { format!("{directory}/manifest.json") },
        serde_json::to_string_pretty(&json!({
            "options":o,"pool":pool,"source_fingerprint_fnv1a64":format!("{fingerprint:016x}"),
            "build":if cfg!(debug_assertions){"debug"}else{"release"},"balanced_positions":o.rounds.is_multiple_of(5),
            "source":"synthetic-v1; external adaptations only when explicitly provided","model_calls":0,"model_tokens":0
        }))?,
    )?;
    let name = format!("agentdb_research_{}_{stamp}", std::process::id());
    let root = Db::connect(url, 1, false)?;
    let mut isolated = reqwest::Url::parse(url)?;
    isolated.set_path(&format!("/{name}"));
    root.query(QKind::Meta, &format!("create database {name}")).await?;
    let result:Result<Value>=async {
        let admin=Db::connect(isolated.as_str(),2,false)?;
        let reference=Db::connect(isolated.as_str(),2,true)?;
        let setup=Instant::now();
        admin.query(QKind::Meta,"create table etl_batch_log(table_name text,batch_id int)").await?;
        for p in DOMAINS {eprintln!("装载 {p}: {} 事实行",o.rows);admin.query(QKind::Meta,&fixture(p,o.rows)).await?;}
        let relation_bytes=admin.query(QKind::Meta,"select sum(pg_total_relation_size(relid))::bigint from pg_stat_user_tables").await?.i64(0,0).unwrap_or(0);
        let row_count=3*(u64::from(o.rows)*4+u64::from(o.rows)-u64::from(o.rows/5)+4096+512);
        let dataset=json!({"relation_bytes":relation_bytes,"rows":row_count,"setup_wall_seconds":setup.elapsed().as_secs_f64(),
            "tables":15,"domains":DOMAINS,"structures":STRUCTURES,"public_tasks_executed_by_default":0,
            "postgres":admin.query(QKind::Meta,"select version()").await?.cell(0,0)});
        if o.capacity_only {
            let mut probes=vec![];
            for p in DOMAINS {for k in [0,2,4,5,11,14] {probes.push(task(p,k,0,o.rows,o.seed,false));}}
            let expected=gold(&reference,&probes).await?;
            std::fs::write(format!("{directory}/capacity-queries.json"),serde_json::to_string_pretty(&json!({"tasks":probes,"expected":expected}))?)?;
            return Ok(json!({"options":o,"dataset":dataset,"capacity_only":true,"capacity_checks":probes.len(),
                "reference_database":reference.meter.snap(),"build":if cfg!(debug_assertions){"debug"}else{"release"}}));
        }
        let mut runs=vec![];
        for round in 0..o.rounds {
            let seed=o.seed.wrapping_add(u64::from(round)*1009);
            let mut completed=std::collections::BTreeMap::new();
            if o.resume.is_some() {
                for mode in MODES {
                    let path=format!("{directory}/round-{round}-{mode}.json");
                    if std::path::Path::new(&path).exists() {
                        let r:Value=serde_json::from_str(&std::fs::read_to_string(path)?)?;
                        ensure!(r["round"]==round && r["mode"]==mode && r["seed"]==seed && r["config"]==serde_json::to_value(config(mode,&o,seed))?, "检查点配置不一致");
                        completed.insert(mode,r);
                    }
                }
            }
            if completed.len()==MODES.len() {eprintln!("轮 {} 已完成，保留原始结果",round+1);runs.extend(completed.into_values());continue;}
            change(&admin,false).await?;
            let stable=Arc::new(tasks(&o,seed,false)?);let shifted=Arc::new(tasks(&o,seed,true)?);
            let corpus_path=format!("{directory}/corpus-{round}.json");
            let corpus=if o.resume.is_some() && std::path::Path::new(&corpus_path).exists() {
                let saved:Value=serde_json::from_str(&std::fs::read_to_string(&corpus_path)?)?;
                let old:Vec<Task>=serde_json::from_value(saved["stable"].clone())?;
                ensure!(old.len()==stable.len() && old.iter().zip(stable.iter()).all(|(a,b)|a.id==b.id && a.sql==b.sql && a.unsafe_query==b.unsafe_query), "恢复时任务 SQL 已变化");
                Corpus{stable,shifted,gold_stable:Arc::new(serde_json::from_value(saved["gold_stable"].clone())?),gold_shifted:Arc::new(serde_json::from_value(saved["gold_shifted"].clone())?)}
            } else {
            eprintln!("轮 {}: 校验 {} 参数实例的独立参考答案",round+1,stable.len());
            let oracle_start=Instant::now();let before=reference.meter.snap();
            let gold_stable=Arc::new(gold(&reference,&stable).await?);
            change(&admin,true).await?;
            let gold_shifted=Arc::new(gold(&reference,&shifted).await?);
            std::fs::write(&corpus_path,serde_json::to_string_pretty(&json!({"stable":*stable,"shifted":*shifted,
                "gold_stable":*gold_stable,"gold_shifted":*gold_shifted,"oracle_wall_seconds":oracle_start.elapsed().as_secs_f64(),"oracle_database":diff(&before,&reference.meter.snap())}))?)?;
            Corpus{stable,shifted,gold_stable,gold_shifted}
            };
            for offset in 0..MODES.len() {
                let mode=MODES[(round as usize+offset)%MODES.len()];
                if let Some(r)=completed.remove(mode) {runs.push(r);continue;}
                eprintln!("轮 {} / {mode}: 训练、稳定阶段、漂移恢复、变化后阶段",round+1);
                let mut r=trial(isolated.as_str(),&admin,&o,pool,(mode,seed),&corpus,&format!("{directory}/optimizer-{round}-{mode}")).await?;
                r["round"]=json!(round);
                r["execution_epoch"]=json!(stamp);
                eprintln!("  稳定 {}/{}，变化后 {}/{}，全程 SQL {}",r["stable"]["correct"],r["stable"]["tasks"],r["shifted"]["correct"],r["shifted"]["tasks"],r["total_database"]["queries"]);
                std::fs::write(format!("{directory}/round-{round}-{mode}.json"),serde_json::to_string_pretty(&r)?)?;runs.push(r);
            }
        }
        Ok(json!({"options":o,"pool":pool,"dataset":dataset,"resumed":o.resume.is_some(),"build":if cfg!(debug_assertions){"debug"}else{"release"},
            "real_llm":"not run: user selected scripted and Mock evaluation","contrasts":contrasts(&runs,o.rounds,o.seed),"runs":runs}))
    }.await;
    // FORCE checks permission to terminate every backend, including autovacuum
    // workers that a CREATEDB-only owner cannot signal. Normal DROP handles
    // autovacuum; briefly retry while this process's pools finish disconnecting.
    let mut cleanup = root.query(QKind::Meta, &format!("drop database {name}")).await;
    for _ in 0..3 {
        if cleanup.is_ok() {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(250)).await;
        cleanup = root.query(QKind::Meta, &format!("drop database {name}")).await;
    }
    match result {
        Ok(mut report) => {
            report["database_cleaned_up"] = json!(cleanup.is_ok());
            std::fs::write(format!("{directory}/report.md"), markdown(&report))?;
            std::fs::write(format!("{directory}/report.json"), serde_json::to_string_pretty(&report)?)?;
            println!("研究实验报告: {directory}/report.md");
            cleanup.context("实验数据库清理失败")?;
            Ok(())
        }
        Err(e) => {
            std::fs::write(
                format!("{directory}/failure.json"),
                serde_json::to_string_pretty(&json!({"error":format!("{e:#}"),"database_cleaned_up":cleanup.is_ok()}))?,
            )?;
            Err(e)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn heldout_tasks_have_distinct_identity_and_bounded_ranges() {
        let mut ids = BTreeSet::new();
        for p in DOMAINS {
            for k in 0..16 {
                for v in 0..16 {
                    let t = task(p, k, v, 1000, 42, false);
                    assert!(ids.insert(t.id));
                    assert!(!t.sql.contains(';'));
                    assert_eq!(t.unsafe_query, k == 15);
                    assert_eq!(t.split == "domain_holdout", p == "delivery");
                }
            }
        }
        assert_eq!(ids.len(), 768);
    }
    #[test]
    fn oracle_comparison_rejects_truncation_null_and_duplicate_changes() {
        let a = json!({"rows":[["1"],[null]],"row_count":2,"truncated":false});
        assert!(equivalent(&a, &a));
        for b in [
            json!({"rows":[["1"],[null]],"row_count":2,"truncated":true}),
            json!({"rows":[["1"],[""]],"row_count":2,"truncated":false}),
            json!({"rows":[["1"]],"row_count":1,"truncated":false}),
        ] {
            assert!(!equivalent(&a, &b));
        }
        assert!(!equivalent(&Value::Null, &Value::Null));
    }

    #[tokio::test]
    #[ignore = "requires AGENTDB_TEST_URL with CREATEDB; creates and drops isolated research database"]
    async fn research_postgres_oracles_and_drift() -> Result<()> {
        let _ = dotenvy::dotenv();
        let url = std::env::var("AGENTDB_TEST_URL").context("missing AGENTDB_TEST_URL")?;
        let output = format!("results/research-test-{}", SystemTime::now().duration_since(UNIX_EPOCH)?.as_micros());
        run(
            &url,
            4,
            &output,
            Options {
                rows: 1000,
                agents: 2,
                variants: 1,
                repeats: 1,
                rounds: 1,
                seed: 42,
                no_result_cache: false,
                corpus: Some("data/research_public_adaptations.json".into()),
                capacity_only: false,
                resume: None,
            },
        )
        .await?;
        let directory = std::fs::read_dir(&output)?.next().context("missing report")??.path();
        let report: Value = serde_json::from_str(&std::fs::read_to_string(directory.join("report.json"))?)?;
        ensure!(report["database_cleaned_up"] == true, "test database not cleaned up");
        for r in report["runs"].as_array().unwrap() {
            for stage in ["stable", "shifted"] {
                ensure!(r[stage]["correct"] == r[stage]["tasks"], "main workload failure: {} {stage}", r["mode"]);
                ensure!(r[stage]["breakdown"]["split"]["external_holdout"]["tasks"] == 2, "public adaptations not executed");
            }
            ensure!(r["recovery"]["events"].as_array().unwrap().iter().all(|e| e["correct"] == true), "grain recovery failed");
            // Do not lock in known bugs; verify that both boundary cases were evaluated.
            ensure!(r["robustness"]["events"].as_array().unwrap().len() == 2, "missing boundary cases");
        }
        Ok(())
    }
}
