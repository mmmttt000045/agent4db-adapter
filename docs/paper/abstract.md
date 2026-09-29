# 摘要草稿（SIGMOD）

定位与质疑见 `related-work.md`。方括号是待正式实验填入的数字。

## 两个区别点

1. **服务多个并发客户 Agent**：并发 Agent 共享彼此的探索与验证——相同的关联、探查、SQL 在途合并，验证结果进入共享经验库；数据库工作量随不同问题数增长，而不随 Agent 数增长；数据变化时所有 Agent 看到一致的修订（一次撤销、一次修复）。
2. **面向数据库的经验（experience for DB）**，区别于普通 Agent 记忆：

| | Agent 记忆 | 面向数据库的经验 |
|---|---|---|
| 形态 | 文本：反思、工作流、历史 SQL | 类型化的数据库对象：关联路径、粒度约束、指标口径、结果 |
| 服务对象 | 单个 Agent 的提示词 | 多个 Agent，按范围共享，带权限检查 |
| 验证 | Agent 自认成功 | 在数据库上执行验证 |
| 与数据的关系 | 无 | 绑定表版本（结构指纹、DML 计数、ETL 批次） |
| 数据变化后 | 继续用或整体过期 | 检查依赖的假设：正常新增保持，破坏性变化撤销，修复须经回归 |
| 约束力 | 仅作参考 | 执行端强制（`review_sql`、声明引用检查） |

“数据变化后”一行只区别于不看数据的 Agent 记忆。对面向数据库的合理基线（写入后标脏、首次使用时重验），它不构成区别，见下一节。

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

## 题目候选

- *Learning Once, Answering Consistently: Guarded Sharing of Metric Definitions among LLM Data Agents*
- *[Name]: Verified, Change-Aware Metric Memory for LLM Data Agents*

## 摘要（当前版本）

> Sharing learned metric definitions can reduce repeated exploration by LLM data agents, but database updates can silently invalidate the assumptions behind those definitions. Schema-only invalidation misses data-only failures. A conservative alternative marks affected definitions stale on write and revalidates them on first use; it keeps valid knowledge, but it rechecks every assumption of every stale definition, even assumptions over unchanged tables and assumptions that other definitions have just rechecked. We present [Name], a middleware system that maintains shared metric definitions through executable validity conditions. It separates a metric's declared business meaning from the data assumptions required by its implementation, including filtered key uniqueness, join multiplicity, and coverage. An offline process extracts candidate definitions and supporting conditions from successful task trajectories grounded in explicit business definitions and their recorded exploration checks. Candidates undergo database validation and snapshot replay before publication. Conditions are normalized and shared across definitions: a condition is revalidated only when a table it reads changes, and its verdict at a data version is reused by every definition, agent, and repair that depends on it. An execution protocol binds definition revisions and validation results to query snapshots, admitting explicitly declared uses only when the recorded conditions hold on the execution snapshot. Restricted repairs produce new revisions only after renewed validation and regression testing. We evaluate [Name] on [benchmark] with [models], [K] update classes, and up to [N] concurrent agents, comparing approaches supplied with identical learning evidence, conditions, and repairs. Under tested changes covered by the recorded conditions, [Name] reduces executions using invalid definitions from [S]% to [T]% relative to schema-only invalidation. Relative to definition-level revalidation, it performs [C]% fewer maintenance checks, spends [M]% less database time on maintenance, and reduces agent waiting on first use by [W]%, with no increase in invalid executions; the gains shrink as fewer definitions share conditions, and we report where they vanish. Relative to revocation followed by re-extraction, it avoids [X] re-extractions per update. Across the full workload, it improves answer accuracy by [A] percentage points over shared trajectory retrieval.

### 每句话的支撑状态（对照当前代码）

| 摘要中的说法 | 状态 | 说明 |
|---|---|---|
| 业务含义与数据假设分开 | 部分 | 口径字段与守护检查都有，但条件没有作为独立对象存储，是从口径字段临时推出来的 |
| 条件含过滤后键唯一、关联多重性、覆盖 | 部分 | 过滤后键唯一（KeyUnique）、关联基数与方向有；覆盖只在粒度修复里用，重验证时没单独检查 |
| 离线从轨迹提炼候选与支撑条件 | 有 | 提炼器输入含已验证关联与粒度过滤；条件没有显式列出 |
| 发布前数据库验证与快照回放 | 有 | G2–G7 |
| 标脏后首用重验（定义级） | 有 | 2026-09-29 之前的实现就是它，现为对照组 `Maint::Definition` |
| 条件只在读到的表变化时重查 | 部分（未运行） | `Maint::Condition`：粒度、关联、时间关联按所读表判断是否待验证；关联经验修订号变化也按待验证处理。条件是从口径字段推出的，不是独立存储对象；覆盖条件不检查 |
| 同一版本的条件结论跨定义复用 | 部分（未运行） | `cond_reuse`：粒度条件、关联守卫、修复回归的 G4 复用同一版本上已有结论；同表同键的粒度修复复用已找到的过滤 |
| 合并同一条件、同一数据版本的并发检查 | 部分（未运行） | 底层检查按（条件, 表版本）在途合并；口径维护按（定义, 依赖版本）在途合并，并发时不再重复撤销与修复。两者定义级对照组同样享有 |
| “比写即失效少误撤销” | **撤回** | 定义级重验同样不误撤销，见“论断修正” |
| 执行协议把修订与验证结果绑定到查询快照 | **无** | 现在先检查、后执行，不在同一快照，检查与执行之间数据可能变化 |
| 只放行显式声明的使用 | 有 | `run_sql` 的 `metrics` 参数 |
| 受限修复须重新验证与回归 | 有 | 当场回归 G3/G4/G5/G8 |
| 维护方式基线 | 有（未运行） | 只看结构、逐写入撤销后重新提炼、定义级重验：`metricbench` 三个模式与 `maint-bench` |
| 共享轨迹检索基线 | **无** | AgentSM 式按相似度检索、复用前不验证，尚未实现 |
| [K] 类更新、[N] 个并发 Agent | **无** | 现在只有正常新增与状态行两类，Agent 顺序执行 |

## 贡献（引言用）

1. 问题：共享口径会被只改数据的更新悄悄破坏，按模式失效漏报（动机证据：直连组只报指标名 5/15，错误全部是口径选择；v2 不改表结构却使旧口径答错全部 3 题）。写入即删除再重新提炼能避免错误，但每次写入都要付出提炼成本；标脏后首用重验两者都能避免，本文的问题是它的维护量随“受影响定义数 × 每个定义的条件数”增长。
2. 可执行有效性条件：把口径的业务含义与实现所依赖的数据假设（过滤后键唯一、关联多重性、覆盖）分开记录。
3. 条件级维护：条件规范化后在定义间共享，只在所读表变化时重查，同一版本的结论被各定义、关联守卫与修复复用；相对定义级重验的收益在 `maint-bench` 中按重验范围、跨定义复用、并发合并、可用性四项分别量化，并报告收益消失的条件。
4. 快照绑定的执行协议：声明的口径修订与验证结果绑定到执行快照，条件在该快照上成立才放行。
5. 受限修复：新修订须重新验证并通过回归。
6. 评估：相同学习证据、条件与修复下对比按模式失效、逐写入撤销后重新提炼、定义级重验、共享轨迹检索；覆盖 [K] 类更新与最多 [N] 个并发 Agent。

## 占位符的当前值（初步，不能直接用）

来自 `exp/2026-09-29-*`，单次运行、15 题、合成数据、一个模型：

- 只报指标名：共享口径 15/15，直连 5/15；普通中间层组未跑。
- 输入 token 约少 8 倍，输出约少 4 倍（共享组含学习成本）。
- v2 后：执行引用过期口径的 SQL 0 次；修复后 3/3 正确。
- 正常新增：误撤销 0。定义级重验同样是 0，这一条不能作为优势。
- 正常新增后首次重查的代价（全表 KeyUnique）：M1 约 5.9 s、M3 约 2.7 s。M3 的 2.7 s 里，同一条件 `KeyUnique(store_sales, 小票号+商品)` 执行了两次（1:1 关联的守卫 1374 ms、口径粒度 1293 ms）；M1 的粒度键是“日期 + 小票号 + 商品”，被前者蕴含。条件结论复用与蕴含能省掉这些，定义级不能；量化待 `maint-bench`。
- 失效基线已实现未运行；变化类型分类只有三类正常追加与 v2；并发实验还没有。

## 投稿前审稿人会要的

1. 真实 schema（TPC-DS 原表或企业风格基准），十几个以上指标，含多表与比率指标。
2. 2–3 个模型，每组 3 次以上重复，报置信区间。
3. 基线：直连；同一中间层不共享；历史 SQL 相似度检索（AgentSM 式）；人工写的语义层（上界）；维护方式：只看结构、逐写入撤销后重新提炼（不是永久清空）、定义级重验（与本文同条件、同修复、同在途合并，最强的对照）。
4. 消融：逐个关闭门槛、关闭守护、关闭修复。
5. 开销：误撤销率、请求路径上的守护与修复耗时、学习成本随复用摊销。

## 上一版（2026-09-29，被“论断修正”取代）

被取代的原因：第二句把“写入即失效”当作对照，评估句用“相对 invalidate-on-write 少误撤销、省数据库时间”作结论；对合理的“标脏 + 首用重验”这两点都不成立。

> Sharing learned metric definitions can reduce repeated exploration by LLM data agents, but database updates can silently invalidate the assumptions behind those definitions. Schema-only invalidation misses data-only failures, while invalidating on every write discards knowledge that remains valid. We present [Name], a middleware system that maintains shared metric definitions through executable validity conditions. It separates a metric's declared business meaning from the data assumptions required by its implementation, including filtered key uniqueness, join multiplicity, and coverage. An offline process extracts candidate definitions and supporting conditions from successful task trajectories grounded in explicit business definitions and their recorded exploration checks. Candidates undergo database validation and snapshot replay before publication. A condition-level dependency graph localizes revalidation to affected conditions and coalesces concurrent checks of the same condition and data version. An execution protocol binds definition revisions and validation results to query snapshots, admitting explicitly declared uses only when the recorded conditions hold on the execution snapshot. Restricted repairs produce new revisions only after renewed validation and regression testing. We evaluate [Name] on [benchmark] with [models], [K] update classes, and up to [N] concurrent agents, comparing approaches supplied with identical learning evidence. Under tested changes covered by the recorded conditions, [Name] reduces executions using invalid definitions from [S]% to [T]% relative to schema-only invalidation. Under benign updates, it reduces unnecessary revocations by [R]% relative to invalidate-on-write. Across the full workload, it improves answer accuracy by [A] percentage points over shared trajectory retrieval and reduces cumulative database execution time by [D]% relative to invalidate-on-write, including admission, revalidation, and repair.

## 更早一版（2026-09-29，已被取代）

> LLM data agents increasingly share a database, and the knowledge they learn (what a metric means, which rows are final, how facts join) is worth sharing across agents. Prior work records such knowledge as trajectories or semantic-layer entries and reuses it by retrieval, but does not address when shared knowledge silently becomes wrong. We show that the natural remedy, invalidating on dependency change, fails in both directions. Schema- or lineage-level invalidation misses data-only changes that break a definition's meaning, while data-level invalidation revokes knowledge on every append and erases the benefit of reuse. Our key observation is that a learned definition is correct only under a small set of data assumptions: key uniqueness under its filters, cardinality and coverage of its joins, and the validity of its time role. These are absent from the SQL text but derivable from the exploration that produced it. [Name] records these assumptions as executable constraints when admitting a definition, revalidates them [incrementally] when the underlying tables change, and repairs a definition only through changes that restore the assumptions and pass regression. Definitions are versioned and explicitly referenced by agents' queries, so no query declared against a revoked version executes, and revalidation triggered by concurrent agents is merged. Across [k] change types on [benchmark] with [N] concurrent agents, [Name] serves no stale definitions under data-only breaking changes, where schema-based invalidation serves [X]%, and revokes [Y]% under benign changes, versus [Z]% for data-level invalidation, while retaining [W]% of the reuse benefit.
