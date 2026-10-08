# 相关工作与审稿质疑

目标会议：SIGMOD。本页按“支撑我们哪句话、与我们区别在哪”记录已核实的相关工作，以及审稿人最可能的质疑和我们的回答。定位与摘要见 `abstract.md`；简称对应的完整条目见第 10 节。

检索日期 2026-09-29。核实标记：

- **原文**：读过原文，引文逐字核对。
- **出处**：会议、期刊或文档出处已在官方页面核对；内容来自摘要或检索概括，引用具体说法前需读原文。
- **预印本**：只有 arXiv，不能写成已发表。

## 1. 问题：智能体优先的数据系统与共享记忆

| 简称 | 出处 | 核实 | 支撑我们的说法 | 与我们的区别 |
|---|---|---|---|---|
| Liu26 | CIDR 2026 | 原文 | ① 数据 Agent 的探索高度重复：BIRD 上每题 50 次独立尝试，“the number of distinct sub-plans of each size is often a small fraction of less than 10-20% of the total”（§2）。② 提出跨 Agent 的 agentic memory store，数据或元数据更新 “necessitating updates to any related information in the agentic memory”；让记忆与数据不一致、等新探查发现过期，缺点是 “the stale information may lead a new probe to make a mistake”（§6.1）。 | 愿景论文，没有系统与有效性模型；举例是表结构更新和新增表，没有讨论只改数据的变化；建议 “draw inspiration from work on knowledge bases as well as schema evolution”。**我们是这个开放问题在指标口径上的具体回答，不主张问题是新的。** |
| Luo26 | SIGMOD 2026 教程 | 出处 | 数据 Agent 的分级与开放问题，引言定位用 | 综述 |
| Li26 | PVLDB 19(12) 2026 教程 | 出处（作者主页的定稿 PDF，未在 vldb.org 交叉核对） | 把多 Agent 协作记忆列为开放问题 | 综述 |
| AgentSM | arXiv 2601.15709 | 预印本 | 执行轨迹组织成结构化语义记忆，目标是减少重复探索、提高一致性；原文把共享记忆留作后续工作：“shared memory introduces nontrivial challenges in retrieval efficiency, consistency management, and error propagation, which we leave as future work.” | 按问题相似度检索，复用前不在数据库上验证，不讨论数据变化。是“共享轨迹检索”基线的原型 |

## 2. Agent 经验与记忆

| 简称 | 出处 | 核实 | 做了什么 |
|---|---|---|---|
| AWM | ICML 2025 | 出处 | 从 Web Agent 轨迹归纳可复用工作流 |
| ExpeL | AAAI 2024 | 出处 | 从经验中提炼自然语言洞见，增删改投票维护 |
| ReasoningBank | ICLR 2026 | 出处 | 从自评的成功与失败中提炼策略 |
| ACE | ICLR 2026 | 出处 | 以增量编辑演化的 “playbook” 上下文 |
| A-MEM | NeurIPS 2025 | 出处 | 互相链接的笔记，新笔记到来时更新旧笔记 |
| Mem0 | ECAI 2025 | 出处 | 对话事实，冲突时更新或删除 |
| CollabMem | ICML 2025 workshop（不是主会） | 出处 | 多用户记忆共享，带随时间变化的访问控制与来源 |

共同点（支撑 `abstract.md` “区别于 Agent 记忆”一表）：记忆是文本、工作流或洞见；成功由 Agent 自认或 LLM 自评；不在外部数据上验证；只有 A-MEM、Mem0 会修改旧记忆，触发条件是新记忆或对话，不是数据变化。CollabMem 管“谁能看”，不管“是否仍然成立”。

## 3. 从历史学业务知识、语义层与基准

### 论文

| 简称 | 出处 | 核实 | 支撑我们的说法 | 与我们的区别 |
|---|---|---|---|---|
| Sequeda24 | GRADES-NDA 2024（SIGMOD workshop） | 出处 | 业务语义显著提高 LLM 在企业库上的正确率：GPT-4 零样本 16% → 54% | 知识图谱人工构建，静态 |
| BIRD | NeurIPS 2023 D&B | 出处 | 每题附外部知识（业务定义），说明口径是 Text-to-SQL 的独立难点 | 知识随题给出，不学、不维护 |
| BIRD-Interact | ICLR 2026 | 出处 | 删去或打断知识库条目制造歧义，把缺失的业务知识作为交互难点 | 是否在修改后的数据上继续提问未确认 |
| Spider 2.0 | ICLR 2025 | 出处 | 企业级工作流，需要文档与代码库；可作真实 schema 来源 | 数据静态 |
| DataLab | ICDE 2025 | 出处 | 从脚本历史与血缘中用 LLM 生成领域知识，含派生列的计算逻辑——“从历史学口径”不是新意 | 只经 LLM 自评与 JSON Schema 检查，不在数据上验证，不维护 |
| EvoSchema | PVLDB 18(10) 2025 | 出处 | 表结构演化会降低 Text-to-SQL 正确率 | 只覆盖表结构变化（列、表的增删改名），不涉及只改数据的变化 |
| Fürst25 | EDBT 2025 | 出处 | 同一问题在不同数据模型上结果不同 | 同上，只看表结构 |

### 产品

只有 Databricks 一行是本人核对的原文，其余为检索概括，写进论文前逐条打开官方文档核对。

| 产品 | 自动学口径 | 在数据上检查粒度/关联 | 只改数据后 | 查询绑定口径修订 |
|---|---|---|---|---|
| Databricks metric views | 否（Genie 可辅助） | **否**。文档原文：“This property is not validated at runtime. If the join produces a fan-out, measures return incorrect results.” 多对多时 “the engine selects the first matching row.”（Model star schemas 一节，2026-09-29 核对） | 无处理 | 否 |
| Databricks Genie knowledge mining | 是：从被点赞或下载的回答中建议度量、过滤、关联，作者确认 | 否 | 基准需手动运行 | 否 |
| Snowflake Semantic Views + Autopilot | 是：从查询历史、示例 SQL、BI 工具学语义视图 | 验证规则在定义时检查，基于声明的键 | 按使用情况“保持更新”，不按数据条件 | 否 |
| Cortex Analyst verified queries | 是：从已验证 SQL 提取过滤与指标 | 只检查能否执行 | 已验证查询只有时间戳 | 否 |
| dbt Semantic Layer / MetricFlow | 辅助生成，人工确认 | 只检查对象存在、SQL 能执行（代码变化时的 CI）；`unique` 测试存在但不与指标绑定 | 无处理 | 否（MCP 工具不带修订） |
| Looker | 辅助生成 LookML | 部分：对称聚合求和时主键不唯一会在查询时报错 | 每次查询报错，不撤销定义 | 否 |

能写的说法：“我们查看的产品文档都没有记载在提供口径前对当前数据检查键唯一或关联多重性，也没有记载在只改数据的更新后撤销口径。”不能写“语义层不做任何验证”。

## 4. 口径的数据条件与维护方式

只收能支撑具体说法的几篇。

| 简称 | 出处 | 核实 | 支撑我们的说法 |
|---|---|---|---|
| Lenz97 | SSDBM 1997 | 出处 | 汇总结果正确的必要条件：不相交、完备、类型兼容。对应我们的条件：不相交 ↔ 过滤后键唯一、关联不放大；完备 ↔ 覆盖（“申请”行不覆盖全部键，所以不能作为修复过滤）。对应关系是我们的解读，正文写明 |
| Mazón09 | DKE 68(12) 2009 | 出处 | 综述：违反可汇总性会使分析工具给出错误结果。综述讨论的是多维建模阶段的处理；我们在运行时对学到的口径检查这些条件，这一区别是我们的说法，引用时不要算到综述头上 |
| Zhou07 | VLDB 2007 | 出处 | 物化视图的懒维护：推迟到视图被使用时再维护。说明“标脏 + 首次使用时重验”是成熟做法，因此定义级重验是最强对照，不是稻草人 |
| Deequ | PVLDB 11(12) 2018 | 出处 | 声明式数据检查；全唯一列上增量计算始终慢于批量（直方图开销），低基数列 3–4 批后增量占优。支撑“默认全量检查，增量检查要测何时划算” |
| TxCache | OSDI 2010 | 出处 | 缓存结果带有效区间、快照一致读。快照绑定执行的技术先例，不作为贡献 |
| Cache-Craft | SIGMOD 2025 | 出处 | 实验归因：完全重算、完全复用为两端，选择性重算基线控制相同重算比例。对应我们的 `revoke` / `off` 与 `definition` / `condition` |

## 5. 同期预印本（2026，写相关工作前需读全文）

都是检索代理找到并核对过 arXiv 元数据的，本人未读全文。投稿时按同期工作引用。

| 预印本 | 重叠 | 区别（据摘要） |
|---|---|---|
| Tk-Boost，arXiv 2602.13521（2026-02） | 从 Agent 错误中学可复用知识，带适用条件，执行 SQL 验证，可接任意 Agent | 知识是文本，适用条件是表、列、关键词；不绑数据版本，无撤销与修复 |
| Invalidation Contracts for Cross-Episode Agent Memory，2609.00243（2026-08）**已读全文，已引用（10-08，见第 12 节）** | 用服务端版本戳在数据漂移后驱逐 Agent 缓存的修正；讨论失效粒度（行级可行、表级抹掉收益） | 只驱逐，不重验、不修复；键值 API 而非 SQL；单 Agent |
| Fresh Memory, Stale Plans，2609.03340（2026-09）**已读全文，已引用（10-08，见第 12 节）** | 存储的 Agent 计划链接到带版本的输入，执行前重查 | 不感知数据库，没有数据条件检查 |
| EvoOntology，2609.15779（2026-09） | 面向数据 Agent 的类型化、带版本的本体，从轨迹演化，编辑经任务评估门槛 | 门槛是任务正确率，不是键或关联条件；不处理数据变化 |
| GATE，2606.05634（2026-06） | 用执行结果验证语义层条目，存为记忆 | 只在学习时验证，无失效 |
| GROUND，2608.26157（2026-08） | 按指标、关联、粒度、过滤规则检查生成的 SQL | 规则人工编写，无版本与数据变化处理 |
| Patel et al.，2609.03141（2026-09） | 研究议程：“persistent semantic context”（含规范口径）在团队或企业范围共享，更新会使其失效 | 只是议程；不是 CIDR 论文 |
| Revoked but Still Authoritative，2609.08258（2026-09） | 五个记忆系统在撤销后仍返回旧事实，提出检索端拦截 | 拦在检索端；我们拦在执行端 |
| Automatic Metadata Extraction，2505.19988 | 从查询日志挖掘关联约束与业务公式 | 不在数据上验证，不处理数据变化 |

## 6. 最可能导致拒稿的质疑

### 质疑一

> 相比“已有语义层自动填充 + 历史查询检索 + 依赖变化后失效”，本文究竟增加了哪项非平凡能力？

回答：前两项都有先例（Snowflake Autopilot、Genie knowledge mining、DataLab；AgentSM），不作为新意；“给 Agent 口径能提高正确率”也有先例（Sequeda24）。增加的是：口径依赖的数据条件被显式记录并在数据上检查（语义层只声明，Databricks 文档明言运行时不验证）；只改数据的变化被发现（按表结构失效看不到，EvoSchema 等只研究表结构）；执行端按声明修订放行；失效后受限修复。Liu26 把共享记忆的过期列为开放问题，我们给出指标口径上的具体机制。

### 质疑二（2026-09-29）

> 合理的保守方案是“依赖表变化 → 相关定义标为待验证 → 首次使用时重查约束 → 通过后继续使用”，并不需要删除经验、重新调用 LLM。你们报告里的流程正是如此。条件级维护相对它多了什么？

回答：这个方案就是 Zhou07 的懒维护用在口径上，我们把它作为最强对照（同条件、同修复、同在途合并）。在目前的实现层面两者几乎相同（2026-09-29 之前的代码就是定义级重验）。“保留定义比删除定义好”不是贡献。要主张的是粒度带来的额外收益——重验范围、跨定义复用、并发合并、可用性——并且必须给出数据，也要说明收益何时消失。见 `abstract.md` 的“论断修正”。

### 我们的回答：失效方式的阶梯

| 维护方式 | 正常新增（追加行） | 只改数据的破坏性变化（ETL v2） | 维护代价 |
|---|---|---|---|
| 按模式或血缘 | 保持 ✓ | 继续用旧口径 ✗（v2 不改表结构：`sr_status` 列本来就有，只追加“申请”行） | 无 |
| 写入即删除，不恢复 | 撤销 ✗ | 撤销 ✓，不修复 | 永久失去复用。过弱，不作对照 |
| 写入即撤销，重新提炼 | 撤销后需重新学习 | 撤销 ✓；重新学习能否得到正确口径取决于提炼 | 每次写入 × 受影响定义数次提炼（LLM、判题），恢复前不可用 |
| 标脏，首次使用时定义级重验（Zhou07 式懒维护） | 保持 ✓ | 撤销 ✓，同样的受限修复 | 每个受影响定义重跑自己的全部条件，含未变化表上的条件；相同条件在不同定义里各查一次 |
| 本文：条件级重验 | 保持 ✓（0 撤销，6/6 正确） | 撤销 ✓ 并修复（3/3 正确；旧口径答错全部 3 题） | 每个受影响的条件查一次，结论被各定义、关联守卫与修复复用 |
| 按结果数值变化 | 分不清 | 分不清 | — |

后两行正确性相同，区别只在维护代价与可用性。表中“本文”一行的正确率来自 2026-09-29 的实验；那时的代码实际上是定义级重验，所以这些数字同样适用于定义级那一行。

目前能从记录里直接看到的一处差别（早期试跑 `exp/2026-09-29-metric-shared-named-M1M3`，已移出仓库、见 Git 历史 `d15e4af`；正常新增后的 M3-P1）：退货率口径的关联是 1:1，关联守卫里有 `KeyUnique(store_sales, 小票号+商品)`，口径自己的粒度条件也是它。一次维护里同一条件执行了两次（守卫 1374 ms、粒度 1293 ms）。同一次运行里 M1 学到的粒度键是“日期 + 小票号 + 商品”，与 M3 的键不是同一个条件；但“小票号 + 商品”唯一蕴含它唯一，M3 先维护时 M1 这次 5.9 s 的检查可以省掉（那次是 M1 先维护，省不掉）。这只是单次观察，量化要看 `maint-bench`。

核心观察：学到的口径只在几条数据性质成立时正确——过滤后的键唯一（粒度）、关联的基数与覆盖及必需过滤、时间角色的关联。这些是可汇总性条件（Lenz97）在具体口径上的实例，不在 SQL 文本里（`SUM(sr_return_amt)` 不说“每笔退货一行”），但能从产生口径的探索里得到。

难做对的维护决策：

1. 表结构不变、只改数据时，判断是正常还是破坏性。
2. 修复要恢复含义，而不只是恢复约束。例：只取“申请”也能让退货表每键一行，但“申请”行只在变更日之后存在、不覆盖全部键，按覆盖条件（Lenz97 的完备性）排除，只有 `sr_status = '完成'` 成立；再经学习题回归确认。
3. 什么时候不修：模式变化、关联不再成立时保持不可用。

并发一致性（AgentSM 留作后续工作，Liu26 列为开放问题）可写成可检验的不变量：

- 安全：声明引用了已撤销修订的 SQL 不会执行。
- 可用：满足假设的正常变化不撤销。定义级重验同样满足，不能作为区别。
- 工作量：每次变化的维护量与受影响的不同条件数成正比（定义级为受影响定义数 × 每个定义的条件数），与 Agent 数无关（两者都合并同一定义的并发维护）。

条件级只有在“多个定义共享条件”且“写入只触及部分条件”时才有优势。每个条件只被一个定义使用、或每次写入都触及全部条件时，两者应当接近，这要在实验里如实报告。

## 7. 支撑这套回答还缺什么

1. 变化类型负载：正常（追加、迟到数据、旧期间回填）；只改数据的破坏（状态行、ETL 重跑重复加载、软删除标记、维度键复用）；模式变化（改名、改类型）；明确不在范围内的（单位变化、编码含义变化）。检索没有找到“只改数据的变化使已学知识失效”的基准（EvoSchema、Fürst25 只看表结构），做出来可以作为一条贡献。`maint-bench` 目前只有三张表上的正常追加与 v2。
2. 失效基线：只看结构、逐写入撤销后重新提炼、定义级重验已实现（2026-09-29），未运行；只按相似度检索不验证（AgentSM 式）尚未实现。
3. 检查成本：当前粒度检查是全表扫描，1M 行首次重查约 5.9 s。只检查变化批次（增量检查）尚未实现；做的话写成集成，并按 Deequ 的做法报告何时划算，不作为新意。
4. 并发：口径维护已按（定义, 依赖版本）在途合并，但定义级对照组同样享有；安全不变量只覆盖声明了引用的 SQL，未声明的使用只靠 `review_sql`。
5. 快照绑定：检查与执行仍不在同一快照上。PostgreSQL 上可把条件检查与 Agent 的 SQL 放进同一个 `REPEATABLE READ` 事务；技术先例是 TxCache，不作为贡献。

## 8. 不能写的话

- “首次提出共享 Agent 记忆会随数据变化过期”（Liu26）。
- “首次从 Agent 轨迹或查询历史学业务口径”（DataLab、AgentSM、Snowflake、Databricks）。
- “首次在数据库上执行验证学到的知识”（Tk-Boost、GATE 等预印本，Cortex Analyst）。
- “首次对 LLM 生成的 SQL 做指标、粒度、关联检查”（GROUND 预印本、语义层产品）。
- “首次用数据版本使 Agent 记忆失效”（Invalidation Contracts 预印本）。能写的是：在 SQL 数据库上，把学到的口径落到可执行数据条件、按数据版本共享结论、执行端按修订强制、失效后受限修复，检索没有找到把这些合在一起的工作。
- “语义层不做验证”；“增量检查是新意”；“快照绑定是新意”。
- 把 AgentSM、Tk-Boost、EvoOntology、GATE 等写成已发表；把 CollabMem 写成 ICML 主会；把 Patel et al. 写成 CIDR 论文。
- 把 5/15 vs 15/15 写成超出“15 题的动机例子”的结论。

## 9. 合作者引用核对记录（2026-09-29）

另一份建议中用到的引用，逐条核对结果：

- 准确：Adda（PACMMOD 3(3), 2025，SIGMOD 2025）；SafeQL（PVLDB 19(9):2210–2223, 2026）；DBToaster（PVLDB 5(10), 2012）；Deequ（PVLDB 11(12):1781–1794, 2018）；MAC-SQL（COLING 2025, pp. 540–557）；MADA 优化器（ICML 2024, PMLR 235）；MADA 多 Agent 设计助手（arXiv 2603.11515，预印本）。
- 需更正：Cache-Craft 的实验并非所有基线都控制相同重算比例。完全重算与完全复用是两端；只有选择性重算基线（Random-Recomp、Prefill-H2O）控制与 Cache-Craft 相同的平均重算比例。
- 需补充：Deequ 的“增量始终更慢”只针对全唯一列（图 8，唯一性与熵一起计算）；低基数列上增量在 3–4 批后占优。

## 10. 参考文献

| 简称 | 条目 |
|---|---|
| Liu26 | Shu Liu, Soujanya Ponnapalli, Shreya Shankar, Sepanta Zeighami, Alan Zhu, Shubham Agarwal, Ruiqi Chen, Samion Suwito, Shuo Yuan, Ion Stoica, Matei Zaharia, Alvin Cheung, Natacha Crooks, Joseph E. Gonzalez, Aditya G. Parameswaran. Supporting Our AI Overlords: Redesigning Data Systems to be Agent-First. CIDR 2026. https://www.vldb.org/cidrdb/papers/2026/p32-liu.pdf |
| Luo26 | Yuyu Luo et al. Data Agents: Levels, State of the Art, and Open Problems. SIGMOD 2026 Companion（教程）. arXiv 2602.04261 |
| Li26 | Guoliang Li et al. 智能体记忆的数据管理（教程，英文标题待核）. PVLDB 19(12), 2026. https://dbgroup.cs.tsinghua.edu.cn/ligl/papers/VLDB2026-AMem-Paper.pdf |
| AgentSM | Asim Biswal et al. AgentSM. arXiv 2601.15709, 2026（预印本） |
| AWM | Zora Zhiruo Wang et al. Agent Workflow Memory. ICML 2025 (PMLR 267) |
| ExpeL | Andrew Zhao et al. ExpeL: LLM Agents Are Experiential Learners. AAAI 2024 |
| ReasoningBank | ReasoningBank. ICLR 2026（作者与完整标题待核） |
| ACE | Agentic Context Engineering. ICLR 2026（作者与完整标题待核） |
| A-MEM | Wujiang Xu et al. A-MEM: Agentic Memory for LLM Agents. NeurIPS 2025 |
| Mem0 | Prateek Chhikara et al. Mem0. ECAI 2025 (FAIA 413) |
| CollabMem | Alireza Rezazadeh et al. Collaborative Memory: Multi-User Memory Sharing in LLM Agents with Dynamic Access Control. ICML 2025 Workshop on Multi-Agent Systems |
| Sequeda24 | Juan Sequeda, Dean Allemang, Bryon Jacob. A Benchmark to Understand the Role of Knowledge Graphs on Large Language Model's Accuracy for Question Answering on Enterprise SQL Databases. GRADES-NDA 2024. doi:10.1145/3661304.3661901 |
| BIRD | Jinyang Li et al. Can LLM Already Serve as a Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs. NeurIPS 2023 Datasets and Benchmarks |
| BIRD-Interact | Nan Huo et al. BIRD-Interact. ICLR 2026 |
| Spider 2.0 | Fangyu Lei et al. Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows. ICLR 2025 |
| DataLab | Luoxuan Weng et al. DataLab: A Unified Platform for LLM-Powered Business Intelligence. ICDE 2025 |
| EvoSchema | Zhang et al. EvoSchema. PVLDB 18(10), 2025. https://www.vldb.org/pvldb/vol18/p3655-zhang.pdf |
| Fürst25 | Fürst et al. 基于真实用户问题的 Text-to-SQL 数据模型鲁棒性评估. EDBT 2025. https://openproceedings.org/2025/conf/edbt/paper-18.pdf |
| Lenz97 | Hans-J. Lenz, Arie Shoshani. Summarizability in OLAP and Statistical Data Bases. SSDBM 1997, pp. 132–143 |
| Mazón09 | Jose-Norberto Mazón, Jens Lechtenbörger, Juan Trujillo. A Survey on Summarizability Issues in Multidimensional Modeling. Data & Knowledge Engineering 68(12):1452–1469, 2009 |
| Zhou07 | Jingren Zhou, Per-Åke Larson, Hicham G. Elmongui. Lazy Maintenance of Materialized Views. VLDB 2007, pp. 231–242 |
| Deequ | Sebastian Schelter et al. Automating Large-Scale Data Quality Verification. PVLDB 11(12):1781–1794, 2018 |
| TxCache | Dan R. K. Ports et al. Transactional Consistency and Automatic Management in an Application Data Cache. OSDI 2010 |
| Cache-Craft | Shubham Agarwal et al. Cache-Craft: Managing Chunk-Caches for Efficient Retrieval-Augmented Generation. PACMMOD 3(3), 2025 (SIGMOD 2025). doi:10.1145/3725273 |
| Databricks | Databricks 文档，Unity Catalog metric views，“Model star schemas”. https://docs.databricks.com/aws/en/uc-semantics/metric-views/basic-modeling（2026-09-29 访问） |

标“待核”的条目写进 bib 前补全作者与标题。

## 11. 2026-09-30 补充核对（论文参考文献即 `overleaf/references.tex` 的 58 条）

出处均在官方页面或 Crossref 记录核对；引文来自出版方 PDF，标 [作者版] 的来自作者自存版本。以下是正文用到的关键说法及原文依据。

| 说法 | 依据 |
|---|---|
| 探索高度重复 | Liu26 §2：“Across queries, the number of distinct sub-plans of each size is often a small fraction of less than 10-20% of the total”（图 2：BIRD 每题 GPT-4o-mini 50 次尝试）。原文说的是“persistent, queryable agentic memory store”，不是“shared memory store” |
| 过期记忆是开放问题 | Liu26 §6.1 “Updates to the Store”；Luo26（SIGMOD'26 教程，pp. 571–579）§2.4.4 “difficulty adapting to dynamic environments with changing data”；Li26（PVLDB 19(12):4888–4892，题为 Data Management for Agentic Memory）§2.1 “redundant, outdated, or conflicting information” |
| 业务知识决定正确率 | BIRD 表 2：GPT-4 无证据 34.88 → 有证据 54.89；Spider 2.0：o1-preview 智能体只完成 21.3%；Sequeda24 §5.1：SQL 16.7% → 知识图谱 54.2%（43 题，GPT-4 零样本）；Floratou24 §2：632 张表、4000 多列，“custom terminology” |
| 纯数据变化静默出错 | Auto-Validate（SIGMOD'21）摘要：“upstream data feeds can change in unexpected ways, causing downstream applications to break silently”；Breck19 例 1.1：“the data looks perfectly fine for the training code” |
| 可汇总性条件 | Lenz97：不相交、完备、类型相容是必要条件，可在数据实例上检查 [作者版]；Mazón09 §4.1：实例级检查“must be incorporated and executed for every update” [作者版] |
| 软约束需随更新维护 | Godfrey01 摘要：“future updates may undermine it”；§3：发现、选择、维护三阶段 [作者版]。讨论的是优化器使用，不是汇总正确性 |
| 发现的唯一性只对某一时刻的实例成立 | Abedjan15 §5.1 [作者版]；动态数据上维护：Swan（**ICDE 2014**，不是 EDBT）、DynFD（EDBT 2019） |
| 选择性检查早有先例 | Nicolas82（按更新类型简化约束）、Ceri & Widom VLDB'90（invalidating operations）、Blakeley89 TODS（irrelevant updates）；Zhou07 §3.5 已提出不影响被访问部分的待处理更新可以不立即维护 |
| 共享检查 | Deequ §4：一次运行内各约束共享扫描（scan-sharing）；我们的区别是结论按依赖版本跨定义、跨时间复用 |
| 在途合并先例 | Memcache（NSDI'13）租约 §3.2.1，原文不用 “coalesce” 一词 |
| 智能体记忆不在外部数据上验证 | AWM、ExpeL、ReasoningBank（ICLR'26）、ACE（ICLR'26）、A-Mem、Mem0、MemGPT（仅 arXiv）逐篇核对：都不在外部数据库上检查记忆，也不因数据变化失效 |
| 半导/无同行评审 | AgentSM、MemGPT 只有 arXiv；Gupta & Mumick 1995 是 Data Eng. Bull. 邀稿；“fan trap / chasm trap” 找不到同行评审出处（可改引 Mazón09 §2.3 或 Hyde & Fremlin, SIGMOD-Companion'24） |

作者顺序以论文 PDF 为准：Breck19（Breck, Polyzotis, Roy, Whang, Zinkevich）、DynFD（第五作者 Torben Meyer）、DataLab（按 IEEE/PDF）。

## 12. 2026-10-04 全文引用核对

按“观点混用、相关写成因果、少数写成共识、可能写成证明、引用对不上原文”五类逐句查了正文 38 处带引用的句子、4 句直接引语和全部 63 条被引条目（2025–2026 年的 10 条在 Crossref 或会议官网核过；Fürst25 的 DOI 10.48786/EDBT.2025.13 由 DataCite 注册，Crossref 查不到属正常）。

新核实的原文依据：

| 说法 | 依据 |
|---|---|
| 粒度是“binding contract” | Kimball & Ross 3rd ed. 第 1 章：“The grain declaration becomes a binding contract on the design” |
| 一半集群 80% 查询完全重复 | van Renen et al. VLDB 2024（PDF 文件名 p3694-saxena.pdf）：“in 50% of database clusters 80% of queries are 1-to-1 repetitions of previously seen queries” |
| 指纹高估重复 | Redset README：feature_fingerprint “A proxy for query-likeness, though not based on text. Will overestimate repetition” |
| 只有领域专家懂的术语 | Floratou24 §2：“columns with abbreviated names and custom terminology that only domain experts can understand”；632 张表、4000 多列 |
| 百万查询归并为千级模板 | Ma18 §4：“reduce the number of queries from millions to at most thousands of templates” |
| BI 平台维护术语定义 | SiriusBI §3：知识库含 table、column、value、term、udf、alias 六类知识 |
| 汇总约束类比完整性约束 | Horner04 摘要：“summary constraints could be integrated into data warehouses, just as integrity constraints are integrated into OLTP systems” |
| 度量不随连接重复计数 | Hyde & Fremlin 2024：measure 锁定在定义表的粒度，连接不引入 bottom-up 计算常见的重复计数 |
| BIRD-Interact | **没有**“有/无知识”的正确率对比，只是删除知识条目制造歧义；不能引作“业务语义提高正确率” |

当天改掉的问题：Lenz97 被引作“每次更新都要重查”（应为 Mazón09 §4.1）；BIRD-Interact 被引作提高正确率；Breck19 的 “looks perfectly fine” 挂了两篇且写成普遍规律；引言里“becoming the norm”“every agent”“instances of”“defeat the safeguards”四处措辞收紧；状态流水混粒度的例子注明是我们的例子、Kimball 只禁止混粒度；Adapton 不是构建系统也不用哈希；参考文献里未被引用的 Cache-Craft 条目删除。

## 12. 2026-10-08 全文核对（论文改为“共享记忆层”定位后补引）

检索代理读了 PDF 全文；引文逐字取自 PDF。五篇都已进 `overleaf/references.tex` 与第 8 节“智能体记忆与经验复用”段。

| 条目 | 状态 | 做了什么 | 与 MAVRA 的区别（论文中的说法） |
|---|---|---|---|
| Michael Wu, Arquimedes Canedo. Invalidation Contracts for Cross-Episode Agent Memory. arXiv:2609.00243（2026-08-31，v1，预印本） | 预印本 | 单个 Agent 跨回合缓存 REST API 服务端给的修正建议；服务端附表级版本戳、数据重载时给行级差异（再高一级给依赖图），客户端据此驱逐或重新打戳。§6.5：“validity is asserted, not verified … the client has no independent evidence a table moved” | 只比较版本并驱逐；不对照数据检查、不绑定快照、不修复；没有数据库/SQL；单 Agent |
| Evan Chen, Shiqiang Wang, Christopher G. Brinton. Fresh Memory, Stale Plans: Derivation Currency for Distributed LLM-Agent Memory. arXiv:2609.03340（v2，2026-09-27；v1 副标题为 Dependency-Scoped Validation for Distributed LLM-Agent Memory） | 预印本 | PlanFence：共享记忆中的计划记录其输入的精确版本；受保护动作前向各输入的所有者读当前版本，有变化则刷新、允许一次重规划，否则阻止。§6.2：“derivation currency does not imply semantic correctness”；§7：“owner reads provide neither a common snapshot nor atomicity with the effect” | 只比较版本；不对照数据检查；明确不提供共同快照；SQLite 只用作记忆存储 |
| Joseph Fioresi, Parth Parag Kulkarni, Ashmal Vayani, Song Wang, Mubarak Shah. Learning to Share: Selective Memory for Efficient Parallel Agentic Systems. ICML 2026, PMLR 306:31146–31160 | 已发表 | 并行 Agent 团队共享一个任务内的全局记忆库；Qwen3-0.6B 控制器（强化学习训练）逐步决定是否把中间步骤加入记忆。§4.4：“instantiated per task and does not persist across problem instances”；不处理删除或修订 | 准入是学到的有用性判断，不是正确性检查；记忆不跨任务；不处理数据变化。论文里自称“verified shared memory”，不要沿用这个词 |
| Xiaoyang Li, Yiqi Wang, Haohui Lu, Zhi Chen, Mo Li, Pingan Song, Mingkai Zheng, Taotao Cai. MemTX: Transactional Belief Commit for Stateful Agent Memory. arXiv:2607.23929（v2，2026-07-28；v1 少 Mingkai Zheng） | 预印本（“Under review”） | 智能体与共享记忆之间的中间件：写观测与提交信念分开；记录带证据、权限、派生链接、逻辑时钟上的有效区间和置信度，八状态生命周期；写入在快照隔离事务中暂存，经四项提交检查（置信度/权威阈值、有效区间含当前逻辑时间、同一实体属性槽的规则冲突、祖先无待撤销）；撤销沿派生图传播（信念撤销、视图隔离、工具动作补偿或记为泄漏）。§3.5：不变式是存在性的，“not that the action's own inputs did”；§3.4：“Repair covers only recorded provenance” | 四项检查都不查询信念所描述的数据；失效只由显式撤销或中止触发，不发现数据变化；快照只覆盖记忆记录；重建交给规划器、不检查；没有优化修订；没有 SQL |
| Yang Zhao, Chengxiao Dai, Mengying Kou, Yue Xiu. MEMOREPAIR: Barrier-First Cascade Repair in Agentic Memory. arXiv:2605.07242（v1，2026-05-08） | 预印本 | 记忆是派生产物的溯源图；修复事件（删除、更正、迁移）先撤下所有可达后继，再用最小割按代价选择修复哪些，只有通过验证（重算的重放一致、重生成的模式与任务回归、沙箱、遗忘检查）的后继才重新发布。§5：“A successor that passes the implemented checks is not guaranteed to be semantically correct” | 修复事件是输入，不检测是否过期；验收不要求唯一、不要求按学习时刻复现；无事务、无快照、无多智能体；无 SQL。它把自己与视图维护对比（§4），评审可能对 MAVRA 提同样的对比 |

AgentSM（2601.15709）10-08 仍只有 v1，无同行评审版本，继续按预印本引用。

Orogat & Mansour, Is Agent Memory a Database? Rethinking Data Foundations for Long-Term AI Agent Memory（arXiv:2605.26252，v1，2026-05-25，cs.AI/cs.DB，预印本，7 页愿景论文）**10-08 已读全文**：
- 做了什么：单个长期运行的个人助理式智能体的记忆（例子是用户告诉它的项目截止日期 3 月 15 日改成 4 月 20 日、午餐偏好）。把记忆形式化为状态 M_t = (D_t, S_t, P_t)，用摄入、修订、遗忘、检索四个状态级算子代替记录级 CRUD，给出六条正确性条件（C1 查询返回“most recent non-archived value”；C2 迁移满足策略；C3 依赖一致；C4 保留溯源；C5 活跃状态有界；C6 检索改变显著度）。原型 MemState 建在 Kùzu 上，只是“feasibility sketch”，没有实验数字。研究议程第三项才提共享记忆（多租户隐私）。
- 与 MAVRA 的关系：只在论点层面相通——智能体记忆是数据管理问题，需要有版本历史、溯源、依赖传播和提交时检查的策略。实质不重叠：①它的记忆内容是用户提供的事实，只有新输入到来时才会变（修订由记忆内部的证据 Δ 触发：重复、冲突、依赖不一致），从不对照外部世界检查；MAVRA 的记忆描述外部数据库，没有任何新输入也会因数据变化而失效。②它的正确性是“返回最新值”（C1），恰恰是 MAVRA 场景里不成立的：最新修订本身可能已经失效，正确性取决于查询所读快照上条件是否成立。③单智能体、生产者即使用者；没有使用时的强制、快照绑定、受验证的修复或优化修订；没有 SQL、没有评估。
- 结论：不构成抢先，反而支持我们的动机（数据库社区认为记忆需要数据管理语义）。如引用，用一句话放在“智能体记忆”段：它把长期记忆的正确性定义为状态轨迹上的性质、以最新值为当前值；我们的记忆描述外部数据库，最新修订也可能失效，正确性要在使用时对照数据判定。

其余只核对了元数据、未读全文：Cordon（2606.17573）；TOKI（2606.06240）；Governed Shared Memory for Multi-Agent LLM Systems（2606.24535）；STALE（2605.06527）；Dependency-Guided Rollback Repair for Memory-Augmented Agents（2608.10502，未核）。第 5 节表中的 Revoked but Still Authoritative（2609.08258）、Patel et al.（2609.03141）在新定位下也更相关，同样待读。
