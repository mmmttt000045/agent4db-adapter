# 工具索引

所有命令从仓库根目录执行。工具与实验输入的对应关系见 [实验索引](../exp/README.md)；脚本文件头和 `--help`（如支持）记录具体参数。

## 常用入口

| 工作 | 工具 |
| --- | --- |
| 论文、PPT、检查 | 根目录 [Makefile](../Makefile) |
| 更新或检查实验索引 | [experiment-index.py](experiment-index.py)；`--check` 只检查文件与目录 |
| 论文和 PPT 绘图 | [figures/README.md](figures/README.md) |
| PPT 生成与版本 | [slides/README.md](../slides/README.md) |
| RelBench SQL 复用对照 | [协议](../exp/2026-10-22-sql-only/README.md)、`relbench/sql-only-stats.py`、`relbench/test_sql_only.py` |
| RelBench 主实验 | [实验协议](../exp/2026-10-20-relbench/README.md)、[基线复现说明](../exp/2026-10-20-relbench/reproduction-notes.md)、`relbench/` |
| 机制预实验与论文图 | [10-29 证据与合入记录](../exp/2026-10-29-mechanism-pilot/paper-integration/README.md)；`figures/mechanism.py` 从已存档 JSON 生成 A/B/C 图与数值宏，无模型调用 |
| 官方 API 实验与图表重构 | [10-28 协议、队列与分析](../exp/2026-10-28-official/README.md)；费用闸门、完整配对核对、独立机制图 |
| 最新场景比较与离线复核 | [10-30 已发表基线](../exp/2026-10-30-published-scenarios/README.md)、[10-31 修复比较](../exp/2026-10-31-corrected-scenarios/README.md)、[10-31 跨智能体题型迁移](../exp/2026-10-31-diverse-scenarios/README.md)；各批次保留运行脚本、冻结源码和 `test-budget.py`，最终聚合入口为 `analyse-paired-reuse.py` |

## 统计与论文数值

| 用途 | 脚本 |
| --- | --- |
| 场景、逐模型与历史汇总 | `paper-results.py`、`scen-stats.py`、`aggregate-metric.py` |
| 维护、回放、并发与快照 | `review-results.py`、`cache-baseline-stats.py`、`replay-stats.py`、`replay-safety-summary.py`、`snapshot-stats.py`、`merge-replay.py`、`declared-use.py` |
| 使用成本、优化与前提 | `sharing-stats.py`、`opt-stats.py`、`premise-stats.py`、`trace-stats.py` |
| 群体、生命周期、工作负载 | `population-stats.py`、`lifecycle-stats.py`、`workload-stats.py` |
| 通用性、外部动机与 ReFoRCE | `generality-stats.py`、`external-reuse-stats.py`、`reforce-stats.py`、`tpcds-sharing.py` |
| 补充会话与共享记忆研究 | `session-latency-stats.py`、`memory-study-stats.py` |

## 启动、数据准备与适配

| 用途 | 脚本 |
| --- | --- |
| 模型连通性 | `check-llm.py`；会调用模型 API |
| 通用基准定义与数据加载 | `bench-library.py`、`bench-support.py`、`bench-load.sh` |
| TPC-DS 数据与定义库 | `tpcds-load.sh`、`tpcds-library.py` |
| 补充实验启动与诊断 | `run-session-latency.py`、`run-memory-study.py`、`run-strategy-study.py`、`metadata-audit.py` |
| RelBench | `relbench/prepare.py`、`relbench/harness.py`、`relbench/run-queue.py`；统计、审计和恢复工具同目录 |
| ReFoRCE | `reforce/mavra_reforce.py` |

旧实验目录中的 `queue-*.sh`、`script-as-run.py` 等保留当时的执行版本。启动、加载、恢复工具可能访问数据库或模型服务；它们不属于常规构建入口。绘图依赖独立声明在 [figures/requirements.txt](figures/requirements.txt)，外部实验依赖按对应协议配置。
