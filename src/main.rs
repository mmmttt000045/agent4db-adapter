mod ablation;
mod benchmark;
mod catalog;
mod checks;
mod db;
mod etl;
mod feedback;
mod flight;
#[cfg(test)]
mod integration_tests;
mod knowledge;
mod llm;
mod maintbench;
mod metric;
mod metricbench;
mod middle;
mod optimizer;
mod realbench;
mod research;
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
    #[arg(long, default_value_t = 16, value_parser = positive_usize)]
    pool: usize,
    /// 结果输出目录
    #[arg(long, default_value = "results")]
    out: String,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// 官方 NYC TLC 真实数据上的只读脚本评测（先运行 tools/prepare-tlc.py）
    RealBench(realbench::Options),
    /// 多业务域、结构留出、数据漂移的可复现研究评测
    Research(research::Options),
    /// 独立数据库上的规模化多 Agent mock 对照实验
    Bench(benchmark::Options),
    /// 2×2 消融：跨 Agent 共享 × 自反馈排序，另含专项测试
    Ablation(benchmark::Options),
    /// 指标经验评测：提炼、跨 Agent 复用与 ETL 后的失效管理（真实模型，独立数据库）
    MetricBench(metricbench::Options),
    /// 指标经验维护方式对照：相同口径与数据变化序列下比较逐写入撤销、只看结构、定义级与条件级重验（不调用 LLM，独立数据库）
    MaintBench(maintbench::Options),
    /// 初始化：状态列与 ETL 批次表（幂等）
    Setup,
    /// 模拟 ETL 改版：apply-v2 / reset / status
    Etl {
        #[arg(value_parser = ["apply-v2", "reset", "status"])]
        action: String,
    },
    /// 启动 HTTP 工具接口
    Serve {
        #[arg(long, default_value = "127.0.0.1:8088")]
        addr: String,
        /// 管理 adapter 的模型服务（与 llm 实验中的查询 Agent 独立）
        #[arg(long, value_parser = ["mock", "openai", "anthropic", "claude"])]
        optimizer_provider: Option<String>,
        /// 定期生成建议；省略时仅通过 HTTP 手动触发
        #[arg(long, value_parser = positive_usize, requires = "optimizer_provider")]
        optimizer_interval_secs: Option<usize>,
        /// 定期生成的建议通过校验后自动应用；默认只生成建议
        #[arg(long, requires = "optimizer_interval_secs")]
        optimizer_auto_apply: bool,
        /// 策略采纳门槛：improvement 需回放证明更省；no-regression 只拒绝回放显著变差；off 只做格式校验且不自动回滚
        #[arg(long, value_enum, default_value_t = optimizer::Gate::Improvement)]
        optimizer_gate: optimizer::Gate,
    },
    /// 按 PPT 故事线演示一遍
    Demo,
    /// 实验 1：共享与在途合并（数据库负载）
    Exp1 {
        #[arg(long, default_value_t = 3, value_parser = positive_usize)]
        agents: usize,
        #[arg(long, default_value_t = 3, value_parser = positive_usize)]
        sessions: usize,
        #[arg(long, default_value_t = 10, value_parser = positive_usize)]
        tasks: usize,
        #[arg(long, value_delimiter = ',', default_value = "1,8", value_parser = positive_usize)]
        concurrency: Vec<usize>,
        #[arg(long, value_delimiter = ',', default_value = "session,agent,global,global+sf", value_parser = ["task", "session", "session+sf", "agent", "global", "global+sf"])]
        modes: Vec<String>,
        #[arg(long, default_value_t = 42)]
        seed: u64,
    },
    /// 实验 2：守护（ETL 改版后的静默错误）
    Exp2 {
        #[arg(long, value_delimiter = ',', value_parser = ["fresh-session", "agent-memory", "global-noguard", "global-guard", "global-always"])]
        modes: Option<Vec<String>>,
        #[arg(long)]
        verbose: bool,
    },
    /// 实验 3：错误关联与反馈排序
    Exp3 {
        #[arg(long, default_value_t = 3, value_parser = positive_usize)]
        agents: usize,
        #[arg(long, default_value_t = 2, value_parser = positive_usize)]
        sessions: usize,
        #[arg(long, default_value_t = 6, value_parser = positive_usize)]
        tasks: usize,
        #[arg(long, default_value_t = 0.5, value_parser = probability)]
        p_trap: f64,
        #[arg(long, default_value_t = 7)]
        seed: u64,
        #[arg(long, value_delimiter = ',', value_parser = ["direct", "A-session-fixed", "C-session-feedback", "B-global-fixed", "D-global-feedback"])]
        modes: Option<Vec<String>>,
    },
    /// 真实 LLM Agent：直连 vs 中间层（key 写在 .env）
    Llm {
        /// agent 名=provider，如 claude-agent=claude,gpt-agent=openai；或 mock
        #[arg(long, value_delimiter = ',', default_value = "mock-a=mock,mock-b=mock")]
        agents: Vec<String>,
        #[arg(long, value_delimiter = ',', default_value = "direct,middle", value_parser = ["direct", "middle"])]
        modes: Vec<String>,
        #[arg(long, value_delimiter = ',', value_parser = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"])]
        questions: Option<Vec<String>>,
        #[arg(long, default_value_t = 20, value_parser = positive_usize)]
        max_steps: usize,
    },
}

fn positive_usize(s: &str) -> std::result::Result<usize, String> {
    s.parse::<usize>().ok().filter(|n| *n > 0).ok_or_else(|| "必须为大于 0 的整数".into())
}

fn probability(s: &str) -> std::result::Result<f64, String> {
    s.parse::<f64>().ok().filter(|p| p.is_finite() && (0.0..=1.0).contains(p)).ok_or_else(|| "概率必须为 0 到 1 之间的有限数值".into())
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
        Cmd::RealBench(options) => realbench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::Research(options) => research::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::Bench(options) => benchmark::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::Ablation(options) => ablation::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::MetricBench(options) => metricbench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::MaintBench(options) => maintbench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::Setup => {
            etl::setup(&admin).await?;
            eprintln!("初始化完成");
        }
        Cmd::Etl { action } => {
            etl::setup(&admin).await?;
            match action.as_str() {
                "apply-v2" => eprintln!("已应用 v2，新增“申请”行 {} 条", etl::apply_v2(&admin).await?),
                "reset" => {
                    etl::reset(&admin).await?;
                    eprintln!("已回到 v1");
                }
                "status" => eprintln!("当前为 {}", if etl::is_v2(&admin).await? { "v2（状态流水）" } else { "v1" }),
                _ => anyhow::bail!("未知动作 {action}（apply-v2 / reset / status）"),
            }
        }
        Cmd::Serve { addr, optimizer_provider, optimizer_interval_secs, optimizer_auto_apply, optimizer_gate } => {
            let optimizer = optimizer_provider
                .map(|kind| optimizer::Optimizer::with_gate(llm::Provider::from_env(&kind)?, &cli.out, optimizer_gate).map(Arc::new))
                .transpose()?;
            etl::setup(&admin).await?;
            let mid = Arc::new(Middle::new(db, MiddleConfig { verbose: true, ..Default::default() }).await?);
            server::serve(mid, &addr, optimizer, optimizer_interval_secs, optimizer_auto_apply).await?;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invalid_options_fail_before_database_access() {
        for args in [
            vec!["app", "--pool", "0", "serve"],
            vec!["app", "exp1", "--concurrency", "1,0"],
            vec!["app", "exp1", "--agents", "0"],
            vec!["app", "exp2", "--modes", "typo"],
            vec!["app", "exp3", "--p-trap", "NaN"],
            vec!["app", "exp3", "--p-trap", "1.1"],
            vec!["app", "llm", "--questions", "Q9"],
            vec!["app", "llm", "--max-steps", "0"],
            vec!["app", "etl", "typo"],
            vec!["app", "serve", "--optimizer-auto-apply"],
            vec!["app", "serve", "--optimizer-interval-secs", "300"],
            vec!["app", "serve", "--optimizer-provider", "mock", "--optimizer-gate", "typo"],
        ] {
            assert!(Cli::try_parse_from(&args).is_err(), "{args:?}");
        }
    }

    #[test]
    fn defaults_and_probability_boundaries_are_valid() {
        for cmd in ["setup", "serve", "demo", "exp1", "exp2", "exp3", "llm"] {
            assert!(Cli::try_parse_from(["app", cmd]).is_ok());
        }
        for p in ["0", "0.5", "1"] {
            assert!(Cli::try_parse_from(["app", "exp3", "--p-trap", p]).is_ok());
        }
        assert!(Cli::try_parse_from([
            "app",
            "serve",
            "--optimizer-provider",
            "openai",
            "--optimizer-interval-secs",
            "300",
            "--optimizer-auto-apply"
        ])
        .is_ok());
        for gate in ["off", "no-regression", "improvement"] {
            assert!(Cli::try_parse_from(["app", "serve", "--optimizer-provider", "mock", "--optimizer-gate", gate]).is_ok());
        }
    }
}
