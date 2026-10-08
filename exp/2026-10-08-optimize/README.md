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
- 结果（`results/scen-20261008-opt/metric-1791439498065570/`，本目录 `opt-stats.md`、`report.md`；对照 `dsv41flash-r1-g3fix--snap`）：
  - 优化轮 474 秒：9 条已发布定义（5 个指标各两条结构不同的定义，退货金额 `#2` 之外都有）全部由规则候选“期间谓词改为日期键范围过滤，不连接 date_dim”发布为 r1；每条 14 个配对期间，学习时快照与当前快照结果全部一致。
  - 执行时间（EXPLAIN ANALYZE，当前 → 候选，配对差 95% 区间）：门店营业额 29.1 → 23.3 ms（−19.8%，[−9.1, −2.5]）；电子品类 29.4 → 24.8（−15.6%）；目录渠道 14.8 → 12.1（−18.4%）；退货金额 14.6 → 10.7（−26.7%）；退货率 173.1 → 110.5（−36.1%，[−74.4, −50.6]；读块反而从 146 万增到 167 万，采纳只看执行时间）。9 条定义省 15.6%–36.1%。
  - 模型提议：每条定义调用一次（27–75 秒，各得 1 个候选），但规则候选已发布，本轮未评估——已改为规则候选都没发布时才请模型（提交 7648784）。
  - 之后的留出与 11 种更新：78/96 答对，对照 77/96；逐阶段差异（mirror 5/6 对 3/6、dupload 5/9 对 6/9、latekey 1/9 对 2/9）在运行间波动范围内。`latekey` 下日期键范围修订与维度连接一样因覆盖条件失效（关联不上 date_dim 的行占比 1.03% → 3.64%），`dimhist` 下电子品类的连接路径修复照常进行。
  - 留出题 15 条用户智能体查询中 9 条采用了新修订示例里的日期键范围写法（按月排名题还自己写出了按月 min/max 的变体）；智能体 SQL 的 EXPLAIN 均值 122 ms 对 100 ms 不是受控比较（两次运行写的 SQL 不同，含排名题的大查询），受控比较是优化轮的配对测量。

## 带 --trace 的小规模运行（PPT 第 7、8、15 页的调用序列）

- 命令：`agentdb-mid --pool 8 --out results/scen-20261008-trace metric-bench --agent cline --extractor cline --modes metric-global-opt --metrics M1 --phrasings named --changes revision --repeats 1 --rows 1000000 --sql-timeout-secs 120 --trace`（`--trace` 为本次新增：每个 cell 写 `trace-<cell>.jsonl`，逐次记录工具名、参数、结果摘要与耗时）。本目录 `trace/` 有 trace、`trace-calls.md`（`tools/trace-stats.py` 的逐任务调用序列）、`opt-stats.md`、`run.log`。
- 学习 M1-L1：5 轮 7 次调用（list_tables + find_metric 空 → describe_table ×2 → join_path → run_sql r1 → final_answer）；抽取 12.7 秒，准入检查 5.6 秒，发布 r0。优化轮：两条定义都改为日期键范围（39.7 → 33.3 ms，−16.1%，95% 区间 [−12.2, −0.5]；#2 −16.8%），4.3 秒（规则候选先发布，未调用模型）。
- 留出 M1-P1：4 轮 6 次调用，find_metric 返回两条 r1（示例已是日期键范围写法），B 照样写出范围写法并在 run_sql 的 metrics 里声明 revision 1，答对。
- 数据更正后 M1-P1：find_metric 这一次调用里完成了两条定义的维护与修复（r1 失效 → 唯一谓词 ss_is_current = '1' → 回归通过 → r2；31.6 秒与 22.9 秒，共 54.5 秒）并附两条通知；B 之后两条无过滤的探查被执行前审查拦下（required_filter），加过滤后通过，最终答案 12,932,888.04 正确。这一条 run_sql 没有声明 metrics；同阶段 M1-T1 声明了 revision 2。

## 2026-10-08（晚）：外部评审后的三处修正与前提破坏实验

评审指出：(1) 命题 4.1 声称遗漏只来自日期键匹配不到，但非日期内连接同样会排除关联不上的事实行，而“去掉未用关联”规则在 `loss_ratio == 0` 时允许去掉内连接——一条新事实引用不存在的商品时，原 SQL 排除它、改写后的 SQL 计入它，任何条件都不报；(2) 优化取代的旧修订（仍有效）与修复取代的旧修订（已失效）语义没有区分，§6.1 笼统地说拒绝被替代的修订；(3) 新增前提被破坏时的行为没有实验。代码（提交 `a19493a`）：

- **连接完整性**：每个内连接新增条件——左表关联不上右表任何行（两侧都不带过滤）的行占比不超过准入时的比例（`JoinRef.orphan_ratio`，`COVERAGE_TOLERANCE` 0.001），在 `metric_breach` 中维护、在 `bound_conditions` 中同快照核对；日期键完整性是它在日期连接上的特例。准入时在 `static_gate` 里测基线。
- **去掉关联只限左连接**（`metric::rewrite_candidates`）：右侧在连接键上唯一（连接基数条件）时，左连接保留每个左表行恰好一次，去掉它结果不变；内连接不再作为规则候选。
- **修订状态**：`opt_prev` 存前一修订的整个条目；声明它的查询先按它自己的条件检查（`prev_breach`），成立才接受并附通知。维护把优化新增的前提（日期键连续）放在最后检查，只有它不成立时记为 `Breach::Premise`：其余条件刚确认成立，于是恢复前一修订（`reinstate`，修订号不变），而不是搜索修复。其他条件失败时前一修订一并失效。失效的修订记入 `retired`（拒绝时说明原因；新修订号大于所有失效修订号，恢复之后也不复用）。同快照执行核对所声明修订自己的条件。
- **场景 `rekey`**（不在 ALL 中，需显式指定）：2002-02 的日期键加 10000（接在最大键之后），三张事实表的日期键同步改指向新键；所有键仍存在、连接仍唯一、完整性不变，只有日期键连续不成立。
- 测试：`postgres_premise_break`（新增）；`postgres_change_scenarios`、`postgres_optimization_revision`、`postgres_http_mock_lifecycle`、`postgres_metric_join_orientation`、`postgres_repair_ambiguity` 在新代码上全部通过（noctis，20 万行）；单元测试 42 个通过，clippy 无警告。

前提破坏实验（论文 §7.8 “Breaking the added premise”，宏 `gen/premise.tex`，`tools/premise-stats.py premise-report.json --tex-out overleaf/gen`）：

- 命令（noctis）：`AGENTDB_TEST_URL=$AGENTDB_URL AGENTDB_SCENARIO_ROWS=1000000 cargo test --release -- --ignored postgres_premise_break --nocapture`。报告 `results/premise-test-1791464506964743/report.json`，本目录 `premise-report.json`。
- 同一命令的第一次 100 万行运行（`results/premise-test-1791464335472666`）中，代价测试只让 2 个定义得到日期键范围修订（门店营业额平均只省 9.1%，电子品类区间未整体低于 0；当时 noctis 负载约 39）；回退与答案结论相同。重跑一次 4 个定义都得到修订（省 19.9%–39.5%），论文用这一次。20 万行运行：`results/premise-test-1791463831078349`。
- 结果：重编号后 4 个日期键范围修订都因日期键连续失效，恢复连接日期维度的 r0（每个定义维护 48–8,037 ms，第一个定义的覆盖与粒度检查实际执行，其余复用）；之后 20 个答案（2002-02、Q1、H1、全年、2002-09）全对。不维护这一前提时，日期键范围 SQL 在每个定义的 Q1 与 H1 上答错（金额类多算 102%–324%，退货率差 0.02–0.03 个百分点），因为这两个期间的键区间跨到了之后的月份；2002-02 本身与全年碰巧仍对。声明 r1 被拒绝（“r1 已失效（日期键不再按月连续：36 个月份中 2 个月的日期键不连续），当前修订为 r0”），声明 r0 被接受。
- 另一个实例：门店退货金额优化为 r1 后施加状态流水，粒度失效、修复为 r2；声明 r0、r1 都被拒绝（原因为粒度守卫失败），r2 被接受。
- 孤儿商品键：补录 2002-09 销售并让其中一半的商品键加 1,000,000，关联不上商品维度的行占比 0.00% → 1.32%；电子品类营业额（内连接商品维度）因连接完整性失效，门店营业额不受影响。

系统层回放在新代码上重跑（连接完整性会给含内连接的定义增加条件）：命令同 `exp/2026-10-02-cache-baseline-tpcds/README.md` 10-06（晚）一节，TPC-DS 这次三种参照一起跑；结果见该目录。端到端实验未重跑：其中各场景都不产生关联不上商品维度的销售（回放在同一合成数据与同一组变化上核对），连接完整性检查不会失败，只多出每次变化一次连接检查的时间。
