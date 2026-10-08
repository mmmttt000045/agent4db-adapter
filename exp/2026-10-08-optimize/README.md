# 优化修订：对已发布定义迭代出等价且更省的写法

2026-10-08。用户提出：常见任务的 SQL 可能有更好的写法，系统应能迭代出更好的写法并发布共享。本目录记录设计、实现与运行。

## 设计

- **候选来源**：规则改写（`metric::rewrite_candidates`）——期间谓词改为日期键范围过滤（`TimeStrategy::KeyRange`，不连接日期维度）、去掉口径没有用到其任何列且不带过滤的关联；模型提议（`metric::propose`，输入当前口径、规范 SQL、执行计划与表的行数/列，输出至多 3 个同格式的候选加 rationale）。候选都是结构化定义，规范 SQL 仍由 `metric::compile` 生成，命题 1 与四类条件继续覆盖。
- **判定**（`Middle::optimize_metric`，`src/middle/optimize.rs`）：
  - O1 结构与当前修订不同；G3 静态合法；G4 粒度成立；
  - O2 日期键范围修订要求日期键按月连续（新增条件 `Check::DateKeysContiguous`：按（年, 月）分组后每组键恰好是 [min, max] 的全部整数，相邻月份首尾相接）；
  - O3 规范 SQL 可编译；G5 通过执行前审查；
  - O4 学习时快照上与当前修订的规范 SQL 结果相同（有学习时快照库或模式时）；
  - O5 在一个可重复读的只读快照里，对样本期间（学习年份 12 个单月、一个季度、一次跨期差值、一次全年排名；编译结果相同的题型不计）逐个比较，结果必须全部相同；
  - O6 同一快照内对每个样本期间各做一次 `EXPLAIN (ANALYZE, BUFFERS)`，先后顺序逐期交替；执行时间的配对差（候选 − 当前）用 `feedback::summarize` 的 Student-t 95% 区间，要求配对数 ≥ 8、区间整体低于 0、平均节省 ≥ `optimize_min_saving`（默认 10%）。
- **发布**：作为同一键的新修订（修订号加一），使用者与命中数沿用；旧修订号记入 `Middle::opt_prev`，执行端对声明旧修订的查询宽限接受并附通知（`check_metric_refs`）；使用者收到 `optimize_promoted` 通知。日期键连续作为新修订的条件进入维护（`metric_breach`）与同快照验证（`bound_conditions`），不成立时该修订失效（不在受限修复范围）。
- **范围**：`MiddleConfig::optimize` 默认关闭，已有实验的行为不变；端到端评测新增模式 `metric-global-opt`（同 `-snap`，学习之后、留出之前执行 `optimize_sweep`：先规则候选再模型提议，每条定义本轮最多发布一个新修订）。

## 单元与集成测试

- `metric::tests::compile_key_range_filters_by_date_key_bounds_without_joining_the_dimension`、`rewrite_candidates_offer_key_range_and_drop_only_unused_joins`。
- `integration_tests::postgres_optimization_revision`（`--ignored`，需要 `AGENTDB_TEST_URL`）：合成数据上准入 M1 门店营业额后做一轮规则优化。noctis，20 万行，`results/optimize-test-1791439403141244/report.json`：
  - 候选“期间谓词改为日期键范围过滤，不连接 date_dim”：O1/G3/G4/O2/O3/G5/O5 全部通过；
  - O6：14 个配对期间，执行时间 4.69 → 4.01 ms（平均 −0.69 ms，−14.6%），95% 区间 [−1.10, −0.28] ms；读到的共享块 19,786 → 17,597；
  - 发布 r1；声明 r0 的 `run_sql` 被接受并附通知“已发布等价且更省的修订 r1（你引用的 r0 仍可用）”；整轮 61 条查询、0.27 秒。

## 端到端运行

- 命令（noctis，2026-10-08）：`agentdb-mid --pool 8 --out results/scen-20261008-opt metric-bench --agent cline --extractor cline --modes metric-global-opt --metrics M1,M2,M3,M4,M5 --phrasings named --changes append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror --repeats 1 --rows 1000000 --sql-timeout-secs 120`，日志 `results/scen-20261008-opt/r1.log`。
- 看什么：`optimizing.rounds`（每条定义的候选、门槛与代价证据、是否发布）、`events.optimize`、留出与各变化阶段的正确率（应与 `-snap` 相同；`latekey` 下日期键范围修订与维度连接同样因覆盖条件失效）、用户智能体 SQL 的 `explain.exec_ms`（是否采用了新修订的示例写法）。
- 结果：待补。
