# 摘要草稿（SIGMOD）

相关工作、文献简称与审稿质疑见 `related-work.md`。方括号是待正式实验填入的数字。

## 定位（2026-09-29 按已发表工作修订）

> 数据库上多个 Agent 共享由 LLM 学到的指标口径。本文把每个口径的正确性落到可执行的数据条件上（过滤后粒度、关联多重性、时间关联），条件结论按数据版本维护，并在执行端强制。

- **问题不是本文提出的。** Liu26（CIDR'26）提出让多个 Agent 共享 agentic memory store，指出数据或元数据更新会使其过期、“the stale information may lead a new probe to make a mistake”，并把维护留作开放问题。本文是这个问题在指标口径上的具体系统回答。
- **不作为新意的部分**：从轨迹或历史中学业务口径（DataLab、AgentSM，Snowflake、Databricks 产品）；给 Agent 业务口径能提高正确率（Sequeda24、BIRD）；标脏后首次使用时重验（Zhou07 的懒维护）。
- **新意落在交集**：学到的口径 → 可执行数据条件 → 按数据版本维护、跨口径共享结论 → 执行端按声明修订放行 → 失效后受限修复。2026-09-29 的检索没有找到同时做这几件事的论文或产品文档。
- **不突出 multi-agent**：多 Agent 共享已是 Liu26 的框架；我们的指标实验目前 Agent 顺序执行，并发证据只有脚本消融。

## 两个区别点

1. **多个 Agent 共享探索与验证**：相同的关联、探查、SQL 在途合并，验证结果进入共享经验库；数据变化时所有 Agent 看到一致的修订（一次撤销、一次修复）。共享本身不是新意（Liu26 已提出，并测得 BIRD 上 50 次独立尝试中不同子计划常不到 10–20%）；我们的证据是 2×2 消融中共享使数据库成本降 50.3%、8 个同时到达的相同汇总只执行 1 次（脚本 Agent，`exp/2026-09-29-ablation-2x2`）。
2. **面向数据库的经验（experience for DB）**，区别于 Agent 记忆（AWM、ExpeL、ReasoningBank、ACE、A-MEM、Mem0，见 `related-work.md` 第 2 节）：

| | Agent 记忆 | 面向数据库的经验 |
|---|---|---|
| 形态 | 文本：反思、工作流、洞见、历史 SQL | 类型化的数据库对象：关联路径、粒度约束、指标口径、结果 |
| 服务对象 | 单个 Agent 的提示词 | 多个 Agent，按范围共享，带权限检查 |
| 验证 | Agent 自认成功，或 LLM 自评 | 在数据库上执行验证 |
| 与数据的关系 | 无 | 绑定表版本（结构指纹、DML 计数、ETL 批次） |
| 数据变化后 | 继续用；A-MEM、Mem0 只因新记忆或对话修改旧记忆 | 检查依赖的条件：正常新增保持，破坏性变化撤销，修复须经回归 |
| 约束力 | 仅作参考 | 执行端强制（`review_sql`、声明引用检查） |

“数据变化后”一行只区别于不看数据的 Agent 记忆。对面向数据库的合理基线（写入后标脏、首次使用时重验），它不构成区别，见“论断修正”。

## 题目

推荐：***[Name]: Maintaining Shared Metric Definitions for Data Agents***

- 研究对象是 *Shared Metric Definitions*，技术任务是 *Maintaining*，使用者是 *Data Agents*。数据变化、条件级重验、执行端检查在摘要里展开。
- 不加 *Safe*、*Correct*、*Consistency-Preserving*：这些词要求明确的保证边界。
- 名字：MADA 已被 ICML 2024 的优化器论文与 arXiv 2603.11515（Multi-Agent Design Assistant）使用；ADA 与 SIGMOD 2025 的 Adda 相近。MADA 暂作项目名，论文名待定。

旧候选：

- *Learning Once, Answering Consistently: Guarded Sharing of Metric Definitions among LLM Data Agents*
- *[Name]: Verified, Change-Aware Metric Memory for LLM Data Agents*

## 摘要（当前版本，2026-09-29 第三版）

> LLM data agents repeatedly rediscover business semantics, such as which column measures revenue, which rows are final, and how facts join, and agents working independently can settle on different formulas for the same metric. Sharing learned metric definitions across agents avoids this repetition, but it turns each definition into long-lived state over a changing database. A definition is correct only under data conditions that its SQL does not state: one row per business record under its filters, no fan-out through its joins, and a time join on the intended role. Updates can break these conditions without touching the schema, so schema-level invalidation misses them; marking dependent definitions stale and revalidating each on first use catches them, but repeats the same checks for every definition that shares a condition.
>
> We present [Name], a middleware system that maintains shared metric definitions for data agents. [Name] extracts candidate definitions from judged-successful trajectories and publishes them only after database validation and snapshot replay. Each published definition is grounded in executable validity conditions, including filtered key uniqueness, join multiplicity, and time-role joins, which are normalized so that definitions can share them. A condition is revalidated only when a table it reads changes, and its verdict at a data version is reused by every definition, agent, and repair that depends on it. Agents declare the definition revision each query uses, and [Name] executes the query only if that revision's conditions hold on the query's snapshot. When a condition fails, [Name] revokes the definition and publishes a repaired revision only after revalidation and regression. On [benchmark] with [models], [K] update classes ([J] of them data-only breaking changes), and up to [N] concurrent agents, [Name] reduces executions that use invalid definitions from [S]% to [T]% relative to schema-only invalidation. Relative to definition-level revalidation with identical conditions and repairs, it runs [C]% fewer maintenance checks and cuts first-use waiting by [W]%; the gains shrink as fewer definitions share conditions. Shared definitions raise answer accuracy by [A] points over agents without them and by [B] points over shared trajectory retrieval.

相对第二版的改动：

- 第一段按引言的论证顺序写：重复探索与口径不一致 → 共享 → 口径依赖不写在 SQL 里的数据条件 → 只看结构漏报、定义级重验重复检查。每一步的依据见下一节。
- 删去“relative to revocation followed by re-extraction”：它只说明保留比删除好（见“论断修正”），留在正文。
- 删去 “the gains ... and we report where they vanish” 中的承诺式措辞，改为陈述收益随共享度下降。
- 摘要不放引用（SIGMOD 惯例），依据全部放在引言。

## 引言论证链（按段落顺序，每句的依据）

核实标记见 `related-work.md` 开头：**原文**＝读过原文并核对引文；**出处**＝出处已在官方页面核对，内容来自摘要或检索概括，引用具体说法前需读原文。

| # | 引言中的说法 | 依据 | 类型 |
|---|---|---|---|
| 1 | 数据 Agent 正成为数据库的重要负载，探索中有大量重复工作 | Liu26 §2：BIRD 上每题 50 次独立尝试，“the number of distinct sub-plans of each size is often a small fraction of less than 10-20% of the total” | 文献，原文 |
| 2 | 给 LLM 业务口径能大幅提高企业库上的正确率 | Sequeda24：GPT-4 零样本 16% → 54%（在 SQL 之上加知识图谱）；BIRD 为每题附外部知识 | 文献，出处 |
| 3 | 没有共享口径时，Agent 会给同一指标选不同公式 | 我们：只报指标名时直连 5/15、共享口径 15/15，直连组错误全是口径选择；同一 Agent 在 M1-P1 用 `ss_net_paid`、M1-T1 用 `ss_ext_sales_price`（`exp/2026-09-29-metric-*`，15 题单次运行，只作动机）。BIRD-Interact 把缺失或歧义的业务知识作为交互难点 | 我们的实验；文献，出处 |
| 4 | 共享学到的知识已被提出，过期问题没有解决 | Liu26 §6.1：跨 Agent 的 agentic memory store；更新 “necessitating updates to any related information in the agentic memory”；“the stale information may lead a new probe to make a mistake”；“will need to draw inspiration from work on knowledge bases as well as schema evolution”。AgentSM（预印本）把共享记忆的一致性管理留作后续工作 | 文献，原文；预印本 |
| 5 | 现有 Agent 记忆不在数据上验证，也不随数据变化失效 | AWM、ExpeL、ReasoningBank、ACE、A-MEM、Mem0；DataLab 从脚本历史生成的计算逻辑只经 LLM 自评与格式检查 | 文献，出处 |
| 6 | 口径只在一组数据条件下正确，这些条件不在 SQL 文本里 | Lenz97：汇总正确的必要条件是不相交、完备、类型兼容；Mazón09 综述指出违反可汇总性会使分析工具给出错误结果。对应关系（不相交 ↔ 过滤后键唯一、关联不放大；完备 ↔ 覆盖）是我们的解读，正文要写明 | 文献，出处 |
| 7 | 语义层声明这些条件，但运行时不检查 | Databricks metric views 文档：“This property is not validated at runtime. If the join produces a fan-out, measures return incorrect results.”；多对多时 “the engine selects the first matching row”（2026-09-29 核对）。Snowflake Semantic Views 的规则在定义时检查（检索概括，待核） | 产品文档，原文；待核 |
| 8 | 只改数据、不改表结构的更新能破坏这些条件，只看结构的失效看不到 | 我们：v2 不改表结构，只追加状态行，旧口径答错全部 3 题。EvoSchema、Fürst25 只研究表结构变化；检索没有找到“只改数据的变化使已学知识失效”的基准 | 我们的实验；文献，出处 |
| 9 | 标脏后首次使用时重验是成熟、正确的做法，因此是最强对照而非稻草人 | Zhou07：物化视图的懒维护，把维护推迟到视图被使用时 | 文献，出处 |
| 10 | 但定义级重验对共享同一条件的口径重复检查 | 我们：正常新增后 M3-P1 的一次维护里 `KeyUnique(store_sales, 小票号+商品)` 执行两次（1374 ms、1293 ms）；量化待 `maint-bench` | 我们的实验，单次；待测 |
| 11 | 条件检查默认全量，增量检查要测何时划算 | Deequ：全唯一列上增量计算始终慢于批量；低基数列 3–4 批后增量占优 | 文献，出处 |
| 12 | 评估分离“复用的价值”与“选择性维护的价值” | Cache-Craft：完全重算与完全复用为两端，选择性基线控制相同重算比例。对应我们的 `revoke` / `off` 两端与 `definition` / `condition` | 文献，出处 |

快照绑定（摘要“on the query's snapshot”）有技术先例（TxCache 的快照一致读），不作为贡献；实现前摘要不能保留这句，见下表。

## 贡献（引言用）

1. **问题与负载**：把 Liu26 提出的共享记忆过期问题具体化到指标口径——只改数据的更新会悄悄破坏口径依赖的数据条件，只看表结构的失效看不到，语义层运行时也不检查。给出一组只改数据的破坏性变化负载（已有工作只覆盖表结构变化）。现状：只有正常追加与 v2 两类。
2. **可执行有效性条件**：把口径的业务含义与实现依赖的数据条件分开记录；条件对应可汇总性的经典条件（Lenz97），由产生口径的探索证据得到，发布前在数据库上验证。区别于只存文本或轨迹的 Agent 记忆，以及只声明、不检查的语义层。
3. **条件级维护**：条件规范化后在口径间共享，只在所读表变化时重查，同一数据版本的结论被各口径、各 Agent、关联守卫与修复复用。对照是同条件、同修复的定义级懒重验；收益按重验范围、跨定义复用、并发合并、可用性分别量化，并报告收益消失的条件。
4. **执行与修复协议**：Agent 声明所用修订，执行端只放行条件在执行快照上成立的修订（快照绑定待实现）；失效后受限修复，新修订须重新验证与回归。
5. **评估**：相同学习证据、条件与修复下，对比只看结构、写入即撤销后重新提炼、定义级重验、共享轨迹检索（AgentSM 式，未实现）；覆盖 [K] 类更新与最多 [N] 个并发 Agent。

## 每句话的支撑状态（对照当前代码）

| 摘要中的说法 | 状态 | 说明 |
|---|---|---|
| 从判题成功的轨迹提炼候选，经数据库验证与快照回放后发布 | 有 | G1–G7；提炼器输入含已验证关联与粒度过滤，条件没有显式列出 |
| 口径落到可执行条件：过滤后键唯一、关联多重性、时间关联 | 部分 | KeyUnique、关联基数与方向、时间关联都有；条件从口径字段临时推出，不是独立存储对象；覆盖只在粒度修复里用，重验时不单独检查 |
| 条件规范化后可在口径间共享 | 部分（未运行） | `cond_reuse`：同一条件，或被已通过的更弱条件蕴含（同表同过滤、键列更少） |
| 条件只在所读表变化时重查 | 部分（未运行） | `Maint::Condition`：粒度、关联、时间关联按所读表判断；关联经验修订号变化也按待验证处理 |
| 同一版本的结论被各口径、Agent、修复复用 | 部分（未运行） | 粒度条件、关联守卫、修复回归的 G4；同表同键的粒度修复复用已找到的过滤 |
| 合并同一条件、同一数据版本的并发检查 | 部分（未运行） | 底层检查按（条件, 表版本）在途合并；口径维护按（定义, 依赖版本）在途合并。定义级对照组同样享有 |
| Agent 声明所用修订，执行端核对 | 有 | `run_sql` 的 `metrics` 参数；只覆盖声明了引用的 SQL，未声明的使用只靠 `review_sql` |
| 条件在查询快照上成立才执行 | **无** | 现在先检查、后执行，不在同一快照。可把条件检查与 Agent 的 SQL 放进同一个 `REPEATABLE READ` 事务（或 `pg_export_snapshot` 共享快照）；实现前从摘要删去 “on the query's snapshot” |
| 失效撤销，修复后经重验与回归才发布新修订 | 有 | 当场回归 G3/G4/G5/G8 |
| [K] 类更新，其中 [J] 类只改数据 | **无** | 只有正常追加（三张表）与 v2 |
| 最多 [N] 个并发 Agent | **无** | 指标实验 Agent 顺序执行；并发只在脚本消融与 `maint-bench` 的 `burst` |
| 相对只看结构：过期执行 [S]% → [T]% | 有（未运行） | `metric-global-schema` |
| 相对定义级重验：检查数 [C]%、首用等待 [W]% | 有（未运行） | `metric-global-def`、`maint-bench` |
| 相对无共享口径：正确率 +[A] | 有 | 直连 5/15 vs 共享 15/15；普通中间层组（只报指标名）未跑，两因素尚未分开 |
| 相对共享轨迹检索：+[B] | **无** | AgentSM 式按相似度检索、复用前不验证，尚未实现 |
| “比写即失效少误撤销” | **撤回** | 定义级重验同样不误撤销，见“论断修正” |

## 论断修正（2026-09-29）

起因：审稿式质疑指出，合理的保守方案不必在每次写入后删除经验、重新调用 LLM 学习，它可以是“依赖表变化 → 相关定义标为待验证 → 首次使用时重查约束 → 通过后继续使用”。我们当前的实现正是这个流程：查找时发现依赖表版本变化，重查该定义依赖的每项条件，通过后刷新依赖版本。

1. **撤回**“逐写入失效必然抹掉复用收益”。标脏不等于删除，也不等于重新学习。上一版摘要中 “invalidating on every write discards knowledge that remains valid” 只对“写入即删除、且不恢复”成立，这样的基线过弱。
2. 在已建模的变化上，“标脏 + 首用重验”与本文的正确性相同：正常新增保持有效，v2 撤销并可走同样的受限修复。因此“比写即失效少误撤销”只证明“保留定义比删除定义好”，不能作为贡献，也不再作为摘要的评估结论。
3. 比较时区分三种状态，报告各自的次数、持续时间和成本，不只比较状态名：
   - **短暂待验证**：依赖版本已变、尚未重查。不是撤销，不通知使用者，首次使用时付出重查延迟。
   - **正式撤销**：某个条件在当前版本上不成立。通知使用者，进入受限修复，回归通过得到新修订。
   - **重新提炼**：没有可执行条件、或修复不在范围内时，只能从新的、经判题的轨迹重新学习，需要 LLM 与判题。
   即使保留“逐写入撤销”对照，也让它能恢复：撤销后重新学习与提炼（`metricbench` 的 `metric-global-revoke`），成本单列。
4. 能主张的只剩**粒度**：相对“定义级重验”（同样标脏、同样首用重验、同样的条件、修复、回归，同样的定义级与检查级在途合并），条件级维护是否在以下方面有额外收益：
   - **重验范围**：只重查读到了变化表的条件。例：只有退货表写入时，退货率口径不必重扫门店销售表的粒度（1M 行一次约 1.3–5.9 s，视键列与缓存）。
   - **跨定义复用**：同一条件在同一数据版本上的结论被所有依赖它的定义、关联守卫与修复回归复用；粒度修复在同表同键上只搜索一次。
   - **并发合并**：定义级也合并同一定义的并发维护与同时在途的相同检查；条件级另外复用已完成的结论，所以收益应主要出现在错峰到达时，同时到达时可能很小。
   - **可用性**：首次使用的等待次数与时长；修复后恢复有效的时间。
5. 边界要写明：如果定义级方案也把检查结论按“检查 + 所读表的版本”缓存，它会拿回大部分范围与复用收益——那已经就是条件级维护。所以新意不在缓存，而在：定义被分解成可规范化比较、可共享的条件（粒度、关联多重性、时间关联），这是结论能跨定义复用的前提；条件的修订经关联经验等共享对象传播（修订号变化即待验证）；修复在条件层面找到一次，各定义复用；以及快照绑定的执行（未实现）。共享度低（每个条件只被一个定义使用）或写入触及定义的全部条件时，条件级与定义级应当接近，这要如实报告。

对应实现（2026-09-29，均未运行）：`Maint` 五种维护方式与 `cond_reuse`（`src/middle.rs`、`src/middle/metrics.rs`）；`metricbench` 新增 `metric-global-schema`、`metric-global-revoke`（撤销后重新学习与提炼）、`metric-global-def`；新增不调用 LLM 的 `maint-bench`（19 个共享条件的口径、三类正常追加与 v2、错峰与同时到达，另含只看范围不复用结论的 `condition-scope` 消融）。

## 占位符的当前值（初步，不能直接用）

来自 `exp/2026-09-29-*`，单次运行、15 题、合成数据、一个模型：

- 只报指标名：共享口径 15/15，直连 5/15；普通中间层组未跑。
- 输入 token 约少 8 倍，输出约少 4 倍（共享组含学习成本）。
- v2 后：执行引用过期口径的 SQL 0 次；修复后 3/3 正确。
- 正常新增：误撤销 0。定义级重验同样是 0，这一条不能作为优势。
- 正常新增后首次重查的代价（全表 KeyUnique）：M1 约 5.9 s、M3 约 2.7 s。M3 的 2.7 s 里，同一条件 `KeyUnique(store_sales, 小票号+商品)` 执行了两次（1:1 关联的守卫 1374 ms、口径粒度 1293 ms）；M1 的粒度键是“日期 + 小票号 + 商品”，被前者蕴含。条件结论复用与蕴含能省掉这些，定义级不能；量化待 `maint-bench`。
- 失效基线已实现未运行；变化类型分类只有三类正常追加与 v2；并发实验还没有。
- `maint-bench`（`exp/2026-09-29-maint-share`，单次、固定顺序，待 `--repeats 5`）：错峰到达、k = 6 时条件级 DB 时间为定义级的 0.13（180.7 s → 22.6 s，条件检查 63 → 3 次），等待同样 180.7 s → 22.6 s；k = 1 为 0.39，随共享度增加而下降。同时到达时只到 0.48–0.74，等待 527.9 s → 171.8 s（k = 6）。三种重验的过期使用与误撤销都是 0。同时到达时 v2 修复窗口内有不可用使用（k = 6 条件级 22 / 152，定义级 14 / 152），要在可用性里如实报告。

## 投稿前审稿人会要的

1. 真实 schema（TPC-DS 原表或企业风格基准，如 Spider 2.0、BIRD-Interact 的库），十几个以上指标，含多表与比率指标。
2. 2–3 个模型，每组 3 次以上重复，报置信区间。
3. 基线：直连；同一中间层不共享；历史 SQL 相似度检索（AgentSM 式）；人工写的语义层（上界）；维护方式：只看结构、逐写入撤销后重新提炼（不是永久清空）、定义级重验（与本文同条件、同修复、同在途合并，最强的对照）。
4. 消融：逐个关闭门槛、关闭守护、关闭修复。
5. 开销：误撤销率、请求路径上的守护与修复耗时、学习成本随复用摊销。
6. 只改数据的变化类型负载（见 `related-work.md` 第 7 节），这是现有基准没有的。

## 历史版本

### 第二版（2026-09-29，被第三版取代）

被取代的原因：没有接上已有工作（Liu26 已提出共享记忆过期）；“relative to revocation followed by re-extraction” 只说明保留比删除好；第一段的论证顺序与引言不一致。

> Sharing learned metric definitions can reduce repeated exploration by LLM data agents, but database updates can silently invalidate the assumptions behind those definitions. Schema-only invalidation misses data-only failures. A conservative alternative marks affected definitions stale on write and revalidates them on first use; it keeps valid knowledge, but it rechecks every assumption of every stale definition, even assumptions over unchanged tables and assumptions that other definitions have just rechecked. We present [Name], a middleware system that maintains shared metric definitions through executable validity conditions. It separates a metric's declared business meaning from the data assumptions required by its implementation, including filtered key uniqueness, join multiplicity, and coverage. An offline process extracts candidate definitions and supporting conditions from successful task trajectories grounded in explicit business definitions and their recorded exploration checks. Candidates undergo database validation and snapshot replay before publication. Conditions are normalized and shared across definitions: a condition is revalidated only when a table it reads changes, and its verdict at a data version is reused by every definition, agent, and repair that depends on it. An execution protocol binds definition revisions and validation results to query snapshots, admitting explicitly declared uses only when the recorded conditions hold on the execution snapshot. Restricted repairs produce new revisions only after renewed validation and regression testing. We evaluate [Name] on [benchmark] with [models], [K] update classes, and up to [N] concurrent agents, comparing approaches supplied with identical learning evidence, conditions, and repairs. Under tested changes covered by the recorded conditions, [Name] reduces executions using invalid definitions from [S]% to [T]% relative to schema-only invalidation. Relative to definition-level revalidation, it performs [C]% fewer maintenance checks, spends [M]% less database time on maintenance, and reduces agent waiting on first use by [W]%, with no increase in invalid executions; the gains shrink as fewer definitions share conditions, and we report where they vanish. Relative to revocation followed by re-extraction, it avoids [X] re-extractions per update. Across the full workload, it improves answer accuracy by [A] percentage points over shared trajectory retrieval.

### 第一版（2026-09-29，被“论断修正”取代）

被取代的原因：第二句把“写入即失效”当作对照，评估句用“相对 invalidate-on-write 少误撤销、省数据库时间”作结论；对合理的“标脏 + 首用重验”这两点都不成立。

> Sharing learned metric definitions can reduce repeated exploration by LLM data agents, but database updates can silently invalidate the assumptions behind those definitions. Schema-only invalidation misses data-only failures, while invalidating on every write discards knowledge that remains valid. We present [Name], a middleware system that maintains shared metric definitions through executable validity conditions. It separates a metric's declared business meaning from the data assumptions required by its implementation, including filtered key uniqueness, join multiplicity, and coverage. An offline process extracts candidate definitions and supporting conditions from successful task trajectories grounded in explicit business definitions and their recorded exploration checks. Candidates undergo database validation and snapshot replay before publication. A condition-level dependency graph localizes revalidation to affected conditions and coalesces concurrent checks of the same condition and data version. An execution protocol binds definition revisions and validation results to query snapshots, admitting explicitly declared uses only when the recorded conditions hold on the execution snapshot. Restricted repairs produce new revisions only after renewed validation and regression testing. We evaluate [Name] on [benchmark] with [models], [K] update classes, and up to [N] concurrent agents, comparing approaches supplied with identical learning evidence. Under tested changes covered by the recorded conditions, [Name] reduces executions using invalid definitions from [S]% to [T]% relative to schema-only invalidation. Under benign updates, it reduces unnecessary revocations by [R]% relative to invalidate-on-write. Across the full workload, it improves answer accuracy by [A] percentage points over shared trajectory retrieval and reduces cumulative database execution time by [D]% relative to invalidate-on-write, including admission, revalidation, and repair.

### 更早一版（已被取代）

> LLM data agents increasingly share a database, and the knowledge they learn (what a metric means, which rows are final, how facts join) is worth sharing across agents. Prior work records such knowledge as trajectories or semantic-layer entries and reuses it by retrieval, but does not address when shared knowledge silently becomes wrong. We show that the natural remedy, invalidating on dependency change, fails in both directions. Schema- or lineage-level invalidation misses data-only changes that break a definition's meaning, while data-level invalidation revokes knowledge on every append and erases the benefit of reuse. Our key observation is that a learned definition is correct only under a small set of data assumptions: key uniqueness under its filters, cardinality and coverage of its joins, and the validity of its time role. These are absent from the SQL text but derivable from the exploration that produced it. [Name] records these assumptions as executable constraints when admitting a definition, revalidates them [incrementally] when the underlying tables change, and repairs a definition only through changes that restore the assumptions and pass regression. Definitions are versioned and explicitly referenced by agents' queries, so no query declared against a revoked version executes, and revalidation triggered by concurrent agents is merged. Across [k] change types on [benchmark] with [N] concurrent agents, [Name] serves no stale definitions under data-only breaking changes, where schema-based invalidation serves [X]%, and revokes [Y]% under benign changes, versus [Z]% for data-level invalidation, while retaining [W]% of the reuse benefit.
