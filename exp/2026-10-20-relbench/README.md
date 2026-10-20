# RelBench 主实验：共享记忆省下的 token、调用次数与延迟（2026-10-20 起）

10-20 导师建议主实验改用通用基准 RelBench，体现智能体的工作负载、与纯 Text-to-SQL 区分；用户要求 3–4 个最相关的已发表基线，
核心指标为 token 大幅减少、加速、工具调用次数减少、延迟降低，并要求**充分尊重每个基线的原文**（否则可能直接被拒稿）。
TPC-DS 群体实验（`exp/2026-10-12-population/`）降为受控实验。

## 0. 已停止的运行（10-20）

`results/pop-mem-20261013/` 的 8 组（AWM、ACE、Mem0、共享 ACE）自 10-13 额度用完后一直暂停，10-20 按用户决定终止，
对应的 8 个 `agentdb_metric_*` 数据库已删除，目录里写了 `STOPPED.txt`。原因：10-20 逐篇核对原文与官方代码后，
`src/agentmem.rs` 里的 AWM、ACE、Mem0、ReasoningBank、APC、AgentSM 都与原文有实质出入（自写提示词、用标准答案判对错、
词二元组检索、自创的条数上限与合并规则、APC 缺小模型改写、AgentSM 缺离线合成与两智能体结构）。这些运行（含已完成的
r1-mem-awm 与 `results/pop-mem-20261013-agentsm/`）**一律不报告**。

## 1. 设计（写于看到任何 RelBench 结果之前）

### 1.1 基准

- RelBench v1（NeurIPS 2024 D&B）的数据库、任务定义与官方训练/验证/测试表取自 Hugging Face `stanford-star/relbench-v1`
  （仓库已迁到 `stanford-star/relbench`；noctis 经 hf-mirror.com 下载，原始文件在 noctis `results/relbench-data/`）。
  官方任务、评价指标（分类 ROC-AUC，回归 MAE）与已知问题（如 user-engagement 的 issue #402）一律原样保留。
- 只用实体分类与回归任务（推荐类任务后放）：

  | 库 | 表 | 任务（窗口 Δ） | 截点数 K | 会话数 |
  |---|---|---|---|---|
  | rel-stack | 7 | user-engagement、user-badge、post-votes（91 天） | 5 | 15 |
  | rel-amazon | 3 | user-churn、user-ltv、item-churn、item-ltv（91 天） | 4 | 16 |
  | rel-trial | 15 | study-outcome、study-adverse、site-success（365 天） | 5 | 15 |

- **截点时间线（定期重训）。** 第 k 个截点（k = 1..K）：test_k = 官方 test_timestamp − (K−k)·Δ，
  val_k = 官方 val_timestamp − (K−k)·Δ，训练种子时间从 val_k − Δ 起按 Δ 向前直到库内最早时间（与 RelBench `_get_table` 相同）。
  k = K 即官方划分。标签用任务清单里的 DuckDB SQL（`timestamps` 关系 + `{timedelta}`）在全量数据上生成，
  并按 RelBench 的 `filter_dangling_entities`（以 upto(test_k) 的实体表为准）过滤。**检查：k = K 生成的训练/验证/测试表必须与官方
  parquet 逐行一致，否则不开始实验。**
- **数据变化是真实追加。** 截点 k 的数据库只含时间列 ≤ test_k 的行（与 RelBench 的 `Database.upto` 相同，时间列为空的行不进库）；
  进入截点 k+1 前，把 (test_k, test_{k+1}] 的行追加进去。测试标签不进数据库。
- **智能体身份。** 每个任务由一个智能体负责（如 user-engagement 智能体），每个截点开一个全新会话（不带对话历史）。
  单智能体记忆在它自己的各截点会话之间积累——这是对单智能体记忆最有利的设置。同一截点内各任务的到达顺序按种子随机，
  同一次运行中所有方法顺序相同（配对）。

### 1.2 会话（所有方法相同）

- 模型：river 网关 `deepseek-ai/DeepSeek-V4.1-Flash`，推理强度 high（`RIVER_*`，回报模型名不符的回复丢弃）。
  智能体与各方法的记忆操作用同一模型，除非原文要求不同的模型（APC 的小模型，见 1.3）。
- 工具：`list_tables`、`describe_table`、`join_path`、`check_join`、`run_sql`（中间层 HTTP 接口 `/v1/tools`；
  除 MAVRA 外都用 `middle-alone` 配置，表描述、连接路径与查询结果只在一个会话内有效），`validate_features`、`submit`
  （Python 框架实现），各方法另加自己的记忆工具。提示词与工具说明用英文（各基线的官方提示词都是英文）。
- 特征 SQL 约定：一条 SELECT，以 `{seeds}` 代表种子表（列：实体键、`timestamp`），每个种子恰好返回一行、
  前两列为实体键与 `timestamp`，其余列为数值特征（≤ 100 列）；只能使用时间 ≤ 种子时间的数据。
  `validate_features` 在训练抽样与验证种子上执行 SQL（每次 600 s 超时），训练 LightGBM，返回验证分数、特征重要性与行数检查；
  违反约定时返回错误、不计分。
- 学习器（固定，所有方法与参照相同）：LightGBM 4.6.0，训练种子按 RelBench 默认随机抽 50,000 行（种子 42）；
  分类 objective=binary，回归 objective=l1；n_estimators 300、learning_rate 0.05、num_leaves 63、min_child_samples 20、
  feature_fraction 0.8、bagging_fraction 0.8、bagging_freq 1、seed 42、deterministic、n_jobs 8。
  RelBench 自带的 LightGBM 基线另做 10 轮调参，这里为可重复性不调参，论文写明。
- **参照特征**：实体表本身的列（与 RelBench LightGBM 基线的输入相同），用同一学习器得到每个（任务, 截点）的参照验证分数。
  原文需要“成功”信号的方法，统一用“验证分数优于参照”判定；任何方法都不接触测试标签。
- 停止规则（由框架执行）：智能体提交；或连续 2 次验证没有严格提升（出错的验证不算“没有提升”）；或已验证 8 次（出错的也计入）；或已调用 LLM 40 次
  （不低于各原文的步数上限：ACE 40、APC 10、AWM 10）。未提交时取验证分数最好的一次作为提交。
- 测试评估：会话结束后，用提交的特征 SQL 在测试种子上算特征、同一学习器训练，按官方指标打分。
- 泄漏审计（所有方法）：对每个提交，在最晚的训练种子时间 t* 上，用“只含时间 ≤ t* 的行”的视图重算一次特征并与正常结果比较，
  不一致记为泄漏。

### 1.3 方法（每个基线按原文的记忆归属、内容、构建、检索、反馈与超参数；改动逐条进论文附录的复现说明）

| 方法 | 原文的记忆归属 → 本实验 | 原样保留 | 不得不改 |
|---|---|---|---|
| 无记忆 | — | — | — |
| AgentSM（arXiv 2601.15709，预印本） | 每个库一份，离线一次建好，评估时只读 → 每个库建一次，所有智能体读同一份；离线开销单列 | Algorithm 1 合成探索任务（n = 100，取自其存档代码），合成会话只带 SQL 与读表工具、不检查答案；按探索、构造执行、验证三段存 Markdown，标题由轻量模型生成；MiniLM-L6-v2 + FAISS 取最相似 1 条、只返回相关阶段；规划智能体 + 模式链接智能体（5 步）；组合工具；SQL 自动纠错 | “问题”换成预测任务描述；按本框架的工具重写阶段划分规则；`validate_features`/`submit` 对应原文的输出验证与保存结果；τ = 0.5、组合工具最长 3（原文未给） |
| ACE（ICLR 2026） | 一个智能体一本手册，在线一遍 → 每个智能体一本 | 官方 `REFLECTOR_PROMPT_NO_GT`、`CURATOR_PROMPT_NO_GT` 原文；三个角色同一模型、温度 0；条目格式与计数、只增、80,000 预算；整本手册进提示 | 反馈 = 验证分数记录（原文无标签时用执行反馈）；`submit` 附用到的条目编号；一轮反思；不做多轮 epoch（会泄漏未来标签）；去重默认关（官方 AppWorld 配置同） |
| APC（NeurIPS 2025） | 一个应用一份缓存，服务全部请求 → 所有智能体共用一份（原文如此） | 附录 B.4.3–B.4.5 提示词原文；关键词精确匹配；未命中且成功才写入；命中时由小模型逐轮改写模板；LRU 100；温度 0、max_tokens 4096；关键词与模板生成计入成本 | 搭“计划—执行”两级结构；需要比计划模型便宜约 10 倍的小模型（待定，见第 5 节）；“输出正确”= 验证分数优于参照；另跑 APC 自己的无缓存对照（原文的 Accuracy-Optimal） |
| G-Memory（NeurIPS 2025） | 一个多智能体系统一份，所有智能体共用 → 所有智能体共用（原文如此） | 官方代码 `bingreeky/GMemory` 的记忆模块原样调用（需作者同意，仓库无 LICENSE），阈值与日程照其发布的设置（successful_topk 1、insights_topk 5 等） | 智能体之间不对话，交互图退化为工具调用链（官方运行中该层不被读回、角色定制默认关）；Resolved = 提交且验证分数优于参照；失败的工具调用 reward −1；只改写 ALFWorld 专用文字并公开差异 |
| **MAVRA（本文）** | 所有智能体共用 | — | 共享对象扩展为按实体、相对种子时间窗口的特征定义，新增“不读种子时间之后的数据”条件（开工前另写增补方案） |

附录（只在 rel-stack 上）：AWM（ICML 2025，每个智能体每个库一份，官方 `instruction.txt`）、ReasoningBank（ICLR 2026），
以及敏感性实验“一个 ACE 智能体承担一个库上的全部会话”（仍是原文的单智能体用法）。
原文本来就共享的只有 APC 与 G-Memory；“共享现有记忆仍要探索、会过期”由它们检验，不做任何单智能体方法的共享扩展。

### 1.4 指标与分析方案

1. token：每次 LLM 调用回报的输入 + 输出 token；记忆操作的 token 记在触发它的会话上；AgentSM 离线建库单列。
2. 金额：按公开价格折算（APC 的节省来自换小模型，只看 token 对它不公平）。
3. LLM 调用次数；工具调用次数，按类别：看结构（list/describe/join_path/check_join）、探查（run_sql）、验证、记忆查找、提交。
4. 延迟：会话时间（第一次 LLM 调用到会话结束），拆为 LLM、SQL（探查与特征计算）、训练三部分。
5. 质量：官方指标的测试分数，要求不劣于无记忆（分类 AUC 容差 0.01，回归 MAE 容差 2%，事先写定）；泄漏提交数；成功率（优于参照）。
6. 节省来源：冷启动（库上第一个会话）/ 跨任务（某任务第一个截点、此前已有别的任务的会话）/ 跨截点（同一任务、数据追加之后）。
7. 预先声明的比较：MAVRA 与每个基线在一个库全部会话的累计 token、累计会话时间上的差别；后几个截点每会话的 LLM 调用、
   工具调用、token 与时间；质量不劣。每次运行的值都报告，给出 3 次的范围。

### 1.5 规模

主实验 7 组（无记忆、AgentSM、ACE、APC、APC 无缓存对照、G-Memory、MAVRA）× 3 个库 × 约 15 个会话 × 3 次 ≈ 950 个会话；
AgentSM 离线建库每库 100 个合成会话；rel-stack 附录约 135 个会话。总 token 在 pilot 之后核算。

### 1.6 增补：MAVRA 的 RelBench 扩展（写于 P2 之前，看到任何 MAVRA 结果之前）

- **共享的对象。**
  1. **特征定义**：现有指标定义（事实表、度量、粒度、时间列、经验证的多对一连接、必需过滤）加两个字段——
     实体（经事实表外键或连接到达的实体键，如 votes.postid → posts.id → posts.owneruserid）与回看窗口（天数，或不限）。
     MAVRA 把它编译为对种子表逐行的 LATERAL 聚合：`时间列 <= seed_time`（及窗口下界）写在编译出的 SQL 里，
     所以按定义执行不会读到种子时间之后的数据；每个种子恰好一行（计数类空集取 0，其余按定义的空集规则）。
  2. **任务方案**：一次通过检查的会话为某任务在某截点提交的那组定义（按定义的键与修订引用）及其验证分数。
  3. 中间层原有的表描述、连接路径与检查结果，同 TPC-DS 研究一样由所有智能体共用。
- **从使用中学习。** 会话结束后，若提交的特征在验证集上优于参照（10-20 修订，见运行记录：原先另要求整份提交的审计为 clean），同一模型的提炼器把提交的 SQL
  转为若干特征定义的草稿；发布前检查：字段合法（列存在、表达式只引用涉及的表）、连接在数据上为多对一、事实表粒度键唯一、
  **重现**（编译出的 SQL 在 2,000 个种子上与会话里对应列逐值一致）、**不泄漏**（对编译出的 SQL 跑同一审计）。
  只发布通过的定义；任务方案只引用已发布的定义。提炼与检查的 token 与时间记在触发它的会话上。
- **使用。** 新增工具：`find_features(entity, query)` 返回该实体上已发布的定义（名称、含义、窗口、修订、最近一次使用的增益）；
  `compose_features(ids)` 返回由这些定义编译、可直接交给 `validate_features` 的特征 SQL（含 `{seeds}`）；
  `find_program(task)` 返回该任务最近的已验证方案及其截点与验证分数。智能体仍须自己验证与提交；预算与停止规则不变。
  提示词只说明这些工具，不要求必须使用。
- **维护。** 截点之间追加数据后，定义按现有的条件级维护重查（实体与维度键唯一、连接基数、完整性以发布时为基线）；
  条件不再成立的定义撤下（受限修复的回归以单个答案值为准，特征没有这样的参照，所以特征定义不做受限修复；实现时改定，见运行记录）。
- **P2 门槛不变（第 2 节）。** 若不过，停下分析原因，不调到过为止。

## 2. Pilot 与门槛（先于全量；任何一条不过就停下分析、改设计，不排全量）

- **P1：无记忆，rel-stack，1 次运行，15 个会话**（同一截点的 3 个会话并行，截点依次推进）。
  门槛：(a) ≥ 13/15 个会话正常结束；(b) 每会话 LLM 调用中位数 ≥ 15（否则工作量不足以与 Text-to-SQL 区分）；
  (c) 看结构 + 探查占工具调用 ≥ 30%；(d) ≥ 2/3 的会话验证分数优于参照；(e) 第 2 个起的会话里，看结构的调用
  （同一工具、同一参数）有 ≥ 50% 在同一库更早的会话里出现过（共享的前提）。同时记录每会话 token、时间，用来核算预算。
  k = K 的标签与官方 parquet 一致是 P1 的前置检查。
- **P2：MAVRA，同一抽签**（实现 RelBench 扩展后，另写增补方案再跑）。门槛：从第 2 个截点起每会话 token ≤ 无记忆的 1/3，测试分数不劣。
- **P3：每个基线 4 个会话的忠实性检查**：逐项核对行为与原文一致（ACE 手册按条目增长、APC 命中与未命中路径、
  G-Memory 产生规则、AgentSM 检索返回探索段），记入复现说明。

## 3. 实现

- 数据准备 `tools/relbench/prepare.py`（下载文件 → 截点与标签 → 官方表一致性检查 → PostgreSQL 模板库：主键来自清单，外键列与时间列建 B 树索引并写注释，另有中间层内部的 `etl_batch_log`）。
- 会话框架 `tools/relbench/harness.py`（LLM 循环、工具、`validate_features`、测试评估、泄漏审计、逐次调用记录）。
- 中间层 `serve` 增加 `--mode`（复用 metric-bench 的分组配置）与 `--no-etl`（RelBench 库没有零售表）。
- Python 依赖装在 noctis `.pydeps-relbench`（psycopg 3.2.10、lightgbm 4.6.0；pandas、pyarrow、duckdb 系统已有）。

## 4. 运行记录

（按时间追加）

- 10-20 下午：noctis 的本地代理（127.0.0.1:7890）已停，下载、pip 与网关请求一律去掉代理变量直连（hf-mirror.com、PyPI、api.river.ai 均可达）。
  rel-stack 7 个表与 3 个任务的官方文件经 hf-mirror 下载，大小与 Hugging Face 列表一致；依赖装在 `.pydeps-relbench`
  （relbench 3.0.2 不带依赖、huggingface_hub 2.2.0、psycopg 3.2.10、lightgbm 4.6.0；numpy 与 scipy 用系统的 1.26.4 / 1.15.3）。
- river 试探（Python 客户端）：回报模型 `deepseek-ai/DeepSeek-V4.1-Flash`，“Reply with exactly OK.” 35 个 prompt token（与 Cline 上 35–37 相同，无隐藏提示），工具调用不需回传推理内容。
- `prepare.py`（noctis `results/relbench-data/rel-stack-prep/`）：3 个任务 × 5 个截点的标签由 RelBench 自己的 `_get_table` 生成；
  **k = 5 的训练/验证/测试表与官方 parquet 逐行一致**（post-votes 2,454,038 / 156,230 / 160,903 行，user-badge 3,386,276 / 247,398 / 255,360，
  user-engagement 1,360,850 / 85,838 / 88,137）。截点 test_k：2020-01-03、2020-04-03、2020-07-03、2020-10-02、2021-01-01。
  模板库 `relbench_stack_t1`（截至 2020-01-03，时间列为空的行 0 条）；外键列与时间列 25 个索引，1.6 GB。
- 冒烟（`--smoke`，8 次调用、不计入结果）：第一次所有中间层工具因缺 `etl_batch_log` 报错，补上（模板与追加都记批次）；
  第二次工具正常，智能体 8 次调用里做了 19–23 次工具调用、约 6 万 token，尚未到验证。直接测试验证与审计：
  手写的干净特征验证 AUC 0.813 / 测试 0.809、审计 clean；故意读未来评论的特征验证 0.867 / 测试 0.500、审计判为 leak；
  无索引时按种子的相关子查询 600 s 超时，加索引后 13 s。
- 17:20 启动 P1：`harness.py --arm none --run 1 --parallel 3`，输出 noctis `results/relbench-pilot/none-r1/`。
- **事故（18:30–20:38）**：P1 第 4 个截点上，框架进程把一个特征查询的全部结果取进内存（没有先限行数；按种子连接帖子与投票而不分组的查询会成百万倍放大），
  长到 58.7 GB，noctis 交换约两小时（负载最高约 620，ssh 连不上），20:37:56 被 OOM 终止。这台机器与他人共用，这段时间也拖慢了别人的任务。
  第 1–3 个截点的 9 个会话已写盘，第 4 个截点的 3 个会话丢失。修复（b0c1ef0）：特征查询包一层 `LIMIT 种子数 + 1`（多出的行本来就违反约定，
  数据库读到即停）；追加时按时间范围读文件、不再把全表留在内存；每轮模型调用后写会话检查点；运行一律放进 `systemd-run --scope -p MemoryMax=24G -p MemorySwapMax=0`，
  超限只终止本次运行。复测：故意放大的查询 0.8 s 被拒，进程峰值 3 GB。
- 20:44 续跑第 4–5 个截点（`--cutoffs 4 5`，无记忆的会话与前面的截点无关，库状态 = 模板 + 追加到 test_4），river 返回 503 “No ready deployment”，
  3 个会话 0 次调用即失败，立即停止并移到 `results/relbench-pilot/aborted/`（不计）；river 恢复后重新续跑，输出 `results/relbench-pilot/none-r1-k45/`。
- MAVRA 的 RelBench 扩展（§1.6）实现：7cef189、cefe7cd（特征定义 = 指标定义 + 实体 + 回看窗口，编译为按种子的 LATERAL 聚合；
  `/v1/learn_features` 与 F1–F4；`find_features`、`compose_features`、`find_program`；模式 `relbench-mavra`；特征定义失效即撤下、不做受限修复）。
  noctis 上 50 个单元测试通过（含新加的编译测试）。端到端测试（第 1 个截点，一条手写的干净 user-engagement 特征 SQL）：提炼 15 s、约 3,100 token，
  3 条定义 F1–F4 全部通过并发布；user-badge 的智能体用 `find_features` 查到、`compose_features` 编译成自己种子表上的 SQL，5 万个种子上 2.5 s 算完；
  第一次运行时 3 条都因粒度列带表名前缀（`comments.id`）在 F1 被拒，改为解析时去掉事实表自己的前缀后通过。
- 约 21:00 启动 P2：`harness.py --arm mavra --run 1`（与 P1 同一抽签），输出 `results/relbench-pilot/mavra-r1/`。
- **P2 第一次启动后停止并修订学习条件（21:30，尚未看到任何节省数据）**：第 1 个截点的两个会话（user-badge、user-engagement）提交都有泄漏列，
  按原规则（整份提交审计 clean 才学习）记忆一直为空；P1 中 15 个提交有 4 个泄漏，照原规则 MAVRA 会少学约四分之一的会话，而这不是方法本身的限制：
  每条定义都要过 F3（编译出的 SQL 自带 `<= seed_time` 上界，必须逐值重现提交的列，泄漏列重现不了）与 F4（隐去 t* 之后的行重算，值必须不变）。
  修订：只要提交在验证集上优于参照就学习；审计判为泄漏的列不进提炼器的输入（`columns_by_importance` 中去掉），其余照旧由 F1–F4 逐条把关。
  停掉的部分运行移到 `results/relbench-pilot/aborted/mavra-r1-cleanonly/`（不计）；P2 用同一抽签从头重跑。
- **P1 结果（21:23，`p1-gates.json`，15 个会话 = `none-r1` 9 个 + `none-r1-k45` 6 个；user-engagement k1 的审计经 `reaudit.py` 补做为 clean）：五条门槛全部通过。**
  (a) 15/15 正常结束；(b) 每会话 LLM 调用中位数 16；(c) 看结构 + 探查占工具调用 86%；(d) 15/15 验证分数优于参照；
  (e) 第 2 个起的会话里 97% 的看结构调用在更早的会话中出现过。代价：每会话 token 中位数 19.6 万（均值 27.8 万，合计 416 万），
  会话时间中位数 412 s。**15 个提交中 4 个泄漏**（审计确认，见各会话 `audit`）：没有记忆、各自写特征时，泄漏并不少见。

## 5. 待定

- APC 的小模型（网关上比 Flash 便宜约 10 倍的模型，或计划模型用 V4.1 Pro、小模型用 Flash）。
- 用户发信：向 AgentSM 作者要代码（并问 n）；向 G-Memory 作者确认代码许可。
