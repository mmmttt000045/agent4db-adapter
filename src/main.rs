mod catalog;
mod checks;
mod db;
mod etl;
mod feedback;
mod flight;
mod knowledge;
mod llm;
mod middle;
mod server;
mod sim;
mod sqlscan;
mod workload;

use anyhow::Result;
use clap::{Parser, Subcommand};
use db::Db;
use middle::{Middle, MiddleConfig};
use serde_json::Value;
use std::sync::Arc;

#[derive(Parser)]
#[command(name = "agentdb-mid", about = "中间层 Agent 原型：共享 · 守护 · 反馈")]
struct Cli {
    /// PostgreSQL 连接串
    #[arg(long, env = "AGENTDB_URL", default_value = "postgres://postgres@127.0.0.1:55432/tpcds")]
    db: String,
    /// 连接池大小
    #[arg(long, default_value_t = 16)]
    pool: usize,
    /// 结果输出目录
    #[arg(long, default_value = "results")]
    out: String,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// 初始化：状态列与 ETL 批次表（幂等）
    Setup,
    /// 模拟 ETL 改版：apply-v2 / reset / status
    Etl { action: String },
    /// 启动 HTTP 工具接口
    Serve {
        #[arg(long, default_value = "127.0.0.1:8088")]
        addr: String,
    },
    /// 按 PPT 故事线演示一遍
    Demo,
    /// 实验 1：共享与在途合并（数据库负载）
    Exp1 {
        #[arg(long, default_value_t = 3)]
        agents: usize,
        #[arg(long, default_value_t = 3)]
        sessions: usize,
        #[arg(long, default_value_t = 10)]
        tasks: usize,
        #[arg(long, value_delimiter = ',', default_value = "1,8")]
        concurrency: Vec<usize>,
        #[arg(long, value_delimiter = ',', default_value = "session,agent,global,global+sf")]
        modes: Vec<String>,
        #[arg(long, default_value_t = 42)]
        seed: u64,
    },
    /// 实验 2：守护（ETL 改版后的静默错误）
    Exp2 {
        #[arg(long, value_delimiter = ',')]
        modes: Option<Vec<String>>,
        #[arg(long)]
        verbose: bool,
    },
    /// 实验 3：错误关联与反馈排序
    Exp3 {
        #[arg(long, default_value_t = 3)]
        agents: usize,
        #[arg(long, default_value_t = 2)]
        sessions: usize,
        #[arg(long, default_value_t = 6)]
        tasks: usize,
        #[arg(long, default_value_t = 0.5)]
        p_trap: f64,
        #[arg(long, default_value_t = 7)]
        seed: u64,
        #[arg(long, value_delimiter = ',')]
        modes: Option<Vec<String>>,
    },
    /// 真实 LLM Agent：直连 vs 中间层（key 写在 .env）
    Llm {
        /// agent 名=provider，如 claude-agent=claude,gpt-agent=openai；或 mock
        #[arg(long, value_delimiter = ',', default_value = "mock-a=mock,mock-b=mock")]
        agents: Vec<String>,
        #[arg(long, value_delimiter = ',', default_value = "direct,middle")]
        modes: Vec<String>,
        #[arg(long, value_delimiter = ',')]
        questions: Option<Vec<String>>,
        #[arg(long, default_value_t = 20)]
        max_steps: usize,
    },
}

fn save(out: &str, name: &str, v: &Value, md: &str) -> Result<()> {
    std::fs::create_dir_all(out)?;
    std::fs::write(format!("{out}/{name}.json"), serde_json::to_string_pretty(v)?)?;
    std::fs::write(format!("{out}/{name}.md"), md)?;
    println!("{md}");
    eprintln!("结果已写入 {out}/{name}.json 与 {out}/{name}.md");
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let _ = dotenvy::dotenv();
    let cli = Cli::parse();
    let db = Arc::new(Db::connect(&cli.db, cli.pool, true)?);
    let admin = Arc::new(Db::connect(&cli.db, 2, false)?);
    match cli.cmd {
        Cmd::Setup => {
            etl::setup(&admin).await?;
            eprintln!("初始化完成");
        }
        Cmd::Etl { action } => match action.as_str() {
            "apply-v2" => eprintln!("已应用 v2，新增“申请”行 {} 条", etl::apply_v2(&admin).await?),
            "reset" => {
                etl::reset(&admin).await?;
                eprintln!("已回到 v1");
            }
            "status" => eprintln!("当前为 {}", if etl::is_v2(&admin).await? { "v2（状态流水）" } else { "v1" }),
            _ => anyhow::bail!("未知动作 {action}（apply-v2 / reset / status）"),
        },
        Cmd::Serve { addr } => {
            etl::setup(&admin).await?;
            let mid = Arc::new(Middle::new(db, MiddleConfig { verbose: true, ..Default::default() }).await?);
            server::serve(mid, &addr).await?;
        }
        Cmd::Demo => sim::demo(db, admin).await?,
        Cmd::Exp1 { agents, sessions, tasks, concurrency, modes, seed } => {
            etl::setup(&admin).await?;
            let o = sim::E1Opts {
                agents,
                sessions,
                tasks_per_session: tasks,
                concurrency,
                modes,
                seed,
                queries_path: "data/tpcds_queries.json".into(),
            };
            let (v, md) = sim::e1(db, &o).await?;
            save(&cli.out, "exp1", &v, &md)?;
        }
        Cmd::Exp2 { modes, verbose } => {
            let modes = modes.unwrap_or_else(|| sim::e2_modes().into_iter().map(String::from).collect());
            let (v, md) = sim::e2(db, admin, &modes, verbose).await?;
            save(&cli.out, "exp2", &v, &md)?;
        }
        Cmd::Exp3 { agents, sessions, tasks, p_trap, seed, modes } => {
            let modes = modes.unwrap_or_else(|| sim::e3_modes().into_iter().map(String::from).collect());
            let o = sim::E3Opts { agents, sessions, tasks_per_session: tasks, p_trap, seed, modes };
            let (v, md) = sim::e3(db, admin, &o).await?;
            save(&cli.out, "exp3", &v, &md)?;
        }
        Cmd::Llm { agents, modes, questions, max_steps } => {
            let mut list = vec![];
            for a in agents {
                let (name, kind) = a.split_once('=').unwrap_or((a.as_str(), a.as_str()));
                list.push((name.to_string(), llm::Provider::from_env(kind)?));
            }
            let (v, md) = llm::llm_eval(db, admin, list, &modes, questions, max_steps).await?;
            save(&cli.out, "llm", &v, &md)?;
        }
    }
    Ok(())
}
