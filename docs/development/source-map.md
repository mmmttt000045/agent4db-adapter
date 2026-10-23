# 源码导览

所有路径相对仓库根目录。

| 文件 | 职责 |
| --- | --- |
| `src/main.rs` | CLI 入口、服务与评测命令分发 |
| `src/middle.rs` | 中间层配置、共享、守护与工具调度 |
| `src/middle/metrics.rs` | 定义准入、条件维护、撤销、受限修复与执行修订核对 |
| `src/middle/features.rs` | 共享特征的发布、验证与使用 |
| `src/middle/optimize.rs` | 优化候选验证与修订发布 |
| `src/metric.rs` | 定义结构、SQL 编译、静态检查与提炼 |
| `src/catalog.rs`、`src/checks.rs` | 目录、表版本与语义条件检查 |
| `src/knowledge.rs`、`src/flight.rs` | 经验库与在途请求合并 |
| `src/db.rs`、`src/etl.rs`、`src/sqlscan.rs` | 数据库访问、ETL 与 SQL 扫描 |
| `src/llm.rs`、`src/server.rs` | 模型客户端与 HTTP 工具接口 |
| `src/feedback.rs`、`src/timing.rs` | 检查反馈与请求局部计时 |
| `src/*bench.rs` | 端到端、维护、回放、会话、群体等评测入口 |
| `src/scenario.rs`、`src/specchange.rs`、`src/tpcds.rs` | 场景、模式变化与基准支持 |
| `src/agentmem.rs` | 早期记忆方法适配；论文采用范围见 RelBench 协议 |
| `src/integration_tests.rs`、`data/mock_fixture.sql` | 数据库与 HTTP 集成测试及最小输入 |

当前评测模块共享 `metricbench.rs` 中的配置和辅助函数。后续模块整理应先抽出这些公共职责，再迁移到评测子模块；目录迁移与行为变更分别审查。
