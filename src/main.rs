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
mod memorybench;
mod metric;
mod metricbench;
mod middle;
mod replaybench;
mod scenario;
mod server;
mod sessionbench;
mod specchange;
mod sqlscan;
mod strategybench;
mod timing;
mod tpcds;
mod workloadbench;

use anyhow::Result;
use clap::{Parser, Subcommand};
use db::Db;
use middle::{Middle, MiddleConfig};
use std::sync::Arc;

#[derive(Parser)]
#[command(name = "agentdb-mid", about = "MAVRA：为数据智能体共享并维护数据库知识与经验证的经验")]
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
    /// 指标经验评测：提炼、跨 Agent 复用与 ETL 后的失效管理（真实模型，独立数据库）
    MetricBench(metricbench::Options),
    /// 指标经验维护方式对照：相同口径与数据变化序列下比较逐写入撤销、只看结构、定义级与条件级重验（不调用 LLM，独立数据库）
    MaintBench(maintbench::Options),
    /// 配对回放：场景评测中学到的指标库，在相同变化与留出题上比较各维护方式（不调用 LLM，独立数据库）
    ReplayBench(replaybench::Options),
    /// 工作负载刻画：互不共享的 Agent 会话并发回答同一批分析题，逐次记录工具调用（真实模型，独立数据库）
    WorkloadBench(workloadbench::Options),
    /// 固定已学定义库的会话耗时分解：首次使用、热复用、更新后首次使用与突发并发（真实模型，独立数据库）
    SessionBench(sessionbench::Options),
    /// 共享记忆的时序积累：同一生产者轨迹前缀下，比较隔离、冻结、持续积累和轨迹检索（真实模型，独立数据库）
    MemoryBench(memorybench::Options),
    /// 用数据库实测检查结果检验反馈排序：训练、采纳证据与未见候选测试分离（不调用 LLM）
    StrategyBench(strategybench::Options),
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
    },
}

fn positive_usize(s: &str) -> std::result::Result<usize, String> {
    s.parse::<usize>().ok().filter(|n| *n > 0).ok_or_else(|| "必须为大于 0 的整数".into())
}

#[tokio::main]
async fn main() -> Result<()> {
    let _ = dotenvy::dotenv();
    let cli = Cli::parse();
    let db = Arc::new(Db::connect(&cli.db, cli.pool, true)?);
    let admin = Arc::new(Db::connect(&cli.db, 2, false)?);
    match cli.cmd {
        Cmd::MetricBench(options) => metricbench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::MaintBench(options) => maintbench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::ReplayBench(options) => replaybench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::WorkloadBench(options) => workloadbench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::SessionBench(options) => sessionbench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::MemoryBench(options) => memorybench::run(&cli.db, cli.pool, &cli.out, options).await?,
        Cmd::StrategyBench(options) => strategybench::run(&cli.db, &cli.out, options).await?,
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
        Cmd::Serve { addr } => {
            etl::setup(&admin).await?;
            let mid = Arc::new(Middle::new(db, MiddleConfig { verbose: true, ..Default::default() }).await?);
            server::serve(mid, &addr).await?;
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
            vec!["app", "etl", "typo"],
            vec!["app", "maint-bench", "--agents", "0"],
            vec!["app", "llm"],
        ] {
            assert!(Cli::try_parse_from(&args).is_err(), "{args:?}");
        }
    }

    #[test]
    fn defaults_are_valid() {
        for cmd in ["setup", "serve", "metric-bench", "maint-bench", "workload-bench"] {
            assert!(Cli::try_parse_from(["app", cmd]).is_ok(), "{cmd}");
        }
    }
}
