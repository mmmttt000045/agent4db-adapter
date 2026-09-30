# agent4db-adapter

一个位于 AI Agent 与 PostgreSQL 之间的 Rust 中间层。它共享表探查和关联验证经验，在数据变化后重新验证旧经验，并根据执行反馈优化检查顺序。

项目同时支持 **LLM 管理 adapter**：管理模型读取聚合运行指标，生成受约束的优化策略；adapter 冻结候选后用随后出现的新候选组进行回放评估，达到门槛才应用，应用后持续监测，退化即自动回滚。当前的“自我进化”范围是检查顺序优化，不涉及模型训练、自动修改源码或数据库结构。

> 当前定位：PostgreSQL 上的共享知识与自反馈研究原型。包含自建规模实验和 NYC TLC 真实公开数据验证，不能称为官方 TPC-DS / Spider 成绩。HTTP 接口是工具风格的 REST API，尚未实现 MCP 协议。

此前的 [真实数据验证报告](docs/real-data-validation.md) 使用 NYC TLC 官方两个月的 **5,972,150 条原始行程**，24 个脚本 agent、6 组、6 轮及缓存开/关对照，完成 **552,960 次任务执行**。正常负载的额外反馈收益尚未得到证明；另有真实失败候选专项，明确区分检查执行收益与收集证据的额外成本。数据来源、哈希、完整数值和复现命令都在报告中。

新增 [DeepSeek 真实模型对照](docs/deepseek-real-validation.md)：官方 V4.1 Flash、`max` 思考强度，对照固定规则、统计反馈和 Mock；报告同时记录实际策略采纳、独立验证、模型 token 和全程等待。真实模型接入不保证额外性能收益，专项检查的毛收益不能代替包含观察与模型开销的总收益。

## 论文与 Overleaf

论文源文件与实验依据统一保存在本仓库的 [overleaf/](overleaf/README.md) 目录：

- [中英文双语稿](overleaf/main.tex)：SIGMOD 双栏匿名格式，使用 XeLaTeX。
- [英文稿](overleaf/main-en.tex)：与双语稿共享内容，可使用 pdfLaTeX。
- [Overleaf 上传包](overleaf/mavra-sigmod-bilingual.zip)：包含稿件、使用说明和实验依据。

`overleaf/` 是本仓库的普通目录，随代码一起提交和推送。修改稿件和更新实验时，可在仓库根目录统一管理；使用方法和编译验证状态见 [论文说明](overleaf/README.md)。

## 核心能力

新一轮研究评测使用 `research` 命令。完整设计、计量边界、数据来源和复现方法见 [研究实验协议](docs/research-protocol.md)。它包含 15 张业务表、16 种 SQL 结构、参数/结构/领域留出、数据漂移，以及 A/B/C/D/Mock 五组对照。参数实例数量与独立 SQL 结构数量分别报告。

已完成的 [2026-09-28 实测结果](docs/research-results-2026-09-28.md) 包含 125,000 个主负载任务、24/64 agent 对照、关闭结果缓存的敏感性实验，以及 11.550 GiB / 115,213,824 行容量校验。共享收益明显，反馈与 Mock 未表现出稳定额外收益；语义边界专项发现两类失败，报告完整保留。容量校验不等于十 GB 级完整消融。

```powershell
./tools/research.ps1 -Rows 1000000 -Agents 24 -Variants 16 -Rounds 5
```

默认只运行脚本和 Mock，结果不代表真实大模型收益。报告给出实际存储大小、错误放行/拦截、参考答案、检查轨迹及全程数据库成本；不能预先保证反馈优于固定规则。

| 能力 | 实现 |
| --- | --- |
| 共享经验 | 按任务、会话、Agent 或全局保存表画像、关联路径、检查结果与 SQL 结果 |
| 在途合并 | 合并同一共享范围内的并发重复请求，减少重复数据库访问 |
| 变更守护 | 通过表结构指纹、DML 统计和 ETL 批次感知变化，重新检查经验依赖 |
| 撤销与修复 | 守卫失败时撤销旧经验、通知使用者，并探索保持数据粒度的过滤条件 |
| 反馈排序 | 按表、连接列与方向形成候选排序；冻结候选后用新的不同候选组评估，通过门槛才采纳 |
| LLM 管理 | OpenAI 兼容接口 / Anthropic / mock；生成、校验、回放门槛、应用、退化监测与自动回滚、审计 |
| 实验评估 | 多业务域研究评测、2×2 消融、规模测试，以及查询 Agent 的 direct / middle 对比 |

```text
查询 Agent / HTTP 客户端
          │ 工具调用
          ▼
      Adapter ───────────────► PostgreSQL
          │                        │
          ├─ 共享经验、依赖版本 ◄────┘
          ├─ 守护、撤销、关联修复
          └─ 检查执行反馈
                 │ 聚合统计
                 ▼
            LLM 管理模型
                 │ 受约束的策略 JSON
                 ▼
         校验 → 应用 → 继续观察
                 └─ 审计 / 回滚
```

查询模型负责回答业务问题；管理模型负责优化 adapter 的运行策略。两者复用模型客户端，但执行职责和可用工具不同。

## 环境与数据准备

- Rust stable 工具链，包含 Cargo；Windows 需要可用的 C/C++ 编译与链接工具链。
- PostgreSQL 15 或更高版本。ETL 实验使用 `pg_stat_force_next_flush()`。
- 已导入 TPC-DS 数据的独立实验数据库，表位于 `public` schema，使用标准 TPC-DS 列名。
- 可选：支持 Chat Completions 的模型服务及 API key。

**仓库没有提供完整 TPC-DS 建表脚本和数据生成器。** `data/tpcds_queries.json` 仅包含查询文本，`setup` 也不会创建或导入完整 TPC-DS 数据。完整实验需要使用自己的 TPC-DS 数据生成 / 装载流程准备数据库，并执行 `ANALYZE`。如果只想测试工具和模型管理闭环，可以使用下文的最小 mock 集成测试，无需完整 TPC-DS 数据。

完整实验会访问三类销售与退货表，以及日期、商品、客户等维度表。`setup` 至少要求存在 `store_returns`；ETL 改版还依赖 `date_dim`。ETL 会为同一退货键添加状态流水，因此实验库中的唯一约束不能阻止这种重复键行。

`setup` 和 `serve` 会增加 `store_returns.sr_status` 列并创建 `etl_batch_log`；`demo`、`exp2`、`exp3`、`llm` 及 ETL 命令会修改实验数据。请使用可重建的实验数据库。Agent 查询使用只读连接池，初始化 / ETL 使用同一连接串创建的独立可写连接池，因此当前连接账号需要相应的建表、改表和数据修改权限。

## 快速开始

在项目根目录执行：

```bash
cargo build --locked
```

复制 `.env.example` 为 `.env`。PowerShell：

```powershell
Copy-Item .env.example .env
```

Linux / macOS：

```bash
cp .env.example .env
```

修改 `.env`：

```dotenv
AGENTDB_URL=postgres://postgres:postgres@127.0.0.1:55432/tpcds
```

初始化并启动基础服务：

```bash
cargo run --locked -- setup
cargo run --locked -- serve --addr 127.0.0.1:8088
```

`GET http://127.0.0.1:8088/v1/tools` 返回工具说明。按 Ctrl+C 停止服务。

通用参数放在子命令前，例如：

```bash
cargo run --locked -- --pool 16 --out results serve
cargo run --locked -- --db postgres://postgres@127.0.0.1:55432/tpcds etl status
```

| 通用参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--db` / `AGENTDB_URL` | `postgres://postgres@127.0.0.1:55432/tpcds` | 数据库连接串；命令行优先 |
| `--pool` | `16` | Agent 只读连接池大小，必须大于 0 |
| `--out` | `results` | 实验报告与优化审计目录 |

## 接入管理模型，自动优化

在 `.env` 中配置可用的 OpenAI 兼容服务：

```dotenv
OPENAI_API_KEY=替换为你的密钥
OPENAI_BASE_URL=https://你的服务地址/v1
OPENAI_MODEL=替换为服务支持的模型名称
```

客户端会在 `OPENAI_BASE_URL` 后拼接 `/chat/completions`。不要把完整的 `/chat/completions` 路径写进 base URL。模型需要支持 system 消息及文本 JSON 输出；管理请求不携带工具定义。

按“校验后自动应用”模式运行，每 300 秒检查一次新增反馈：

```bash
cargo run --locked -- serve --optimizer-provider openai --optimizer-interval-secs 300 --optimizer-auto-apply
```

管理行为如下：

1. 三种检查各至少累积 3 次实际执行记录后，才允许生成策略。缓存命中不会自动变成新执行样本。
2. 发送每类检查的执行次数、失败次数、累计耗时、估计处理行数，以及当前策略和应用后的增量统计。不会发送业务行数据、SQL 原文或 API key。
3. 模型只能返回三种既有检查的完整排列及理由：`KeyUnique`、`SampleFanout`、`RowConservation`。
4. 本地拒绝未知字段、重复 / 缺失检查、空理由、工具调用、过期建议和过时版本。一次模型建议最多等待 60 秒。
5. 合法建议还要通过**回放门槛**（见下文）才会应用；未达门槛时写入 `reject` 事件，原策略不变。应用事件先写入审计日志，再影响后续检查排序。检查本身、守护模式、抽样审计规则和数据库权限保持由程序控制。
6. 每个周期先做**退化监测**：只回放应用之后新记录的证据，若当前策略比默认顺序显著更费时，写入 `auto_rollback` 并恢复内置反馈排序。
7. 然后把新反馈再次交给模型。没有新增执行记录时不调用模型；样本不足或调用失败时继续原策略。

#### 回放门槛与退化回滚

默认 `improvement` 使用冻结策略后的新候选组评估：

- 内置反馈冻结上下文评分器；模型建议也记录生成结束时的证据边界。训练期间出现过的完整候选签名不能进入该策略的采纳评估。
- 相同候选的重复观测先组内平均，至少需要 8 个不同候选组。每个完成的验证批次只作一次决策，未通过的模型建议不能继续追加样本反复尝试，需生成新建议。
- 回放累加到首个失败为止，并计入必要的键唯一性补查。采用不可变的当次执行成本；缓存复用观测为零，不再用累计命中次数回溯折扣历史执行。补充观测也使用正常缓存路径。
- 配对差采用保守 Student-t 95% **描述性区间**。窗口最多 2000 条审计失败记录；相同候选分组不等于已经消除了所有相关性，区间不是整个在线流程的置信保证。
- 内置反馈的区间整体低于零才采纳，后续按不重叠新批次重新评估；优势不成立时恢复默认顺序。模型策略在新批次上显著退化时回滚。
- 退化监测独立于提议周期：仅通过 HTTP 手动应用策略时也会每 30 秒监测。配置提议周期时沿用该周期。`off` 明确关闭门槛与自动回滚；`no-regression` 明确允许证据不足时应用。
- 模型候选等待新证据期间自动管理会保留该候选，不在每个周期重新生成并重置验证起点。手动调用 apply 若证据不足可以稍后重试；完整批次已拒绝则需要新候选。

回放没有模拟换序之后的整个缓存生命周期，也未提供事务快照隔离。监测允许观察旧候选在新时间段的表现以发现漂移，重复请求仍按候选分组。模型自动回滚后回到内置反馈，而不是盲目恢复历史模型策略。真实收益必须看包含训练、审计、守护和恢复的总成本，以及策略实际启用次数。

```bash
# 无模型 key，测试相同的建议 / 应用流程；仍需数据库反馈样本
cargo run --locked -- serve --optimizer-provider mock --optimizer-interval-secs 300 --optimizer-auto-apply

# 只开放手动建议、应用和回滚接口
cargo run --locked -- serve --optimizer-provider openai

# 定期生成建议，但不自动应用
cargo run --locked -- serve --optimizer-provider openai --optimizer-interval-secs 300

# 放宽门槛：证据不足也允许应用，但回放显著变差时拒绝，并继续自动回滚
cargo run --locked -- serve --optimizer-provider mock --optimizer-interval-secs 300 --optimizer-auto-apply --optimizer-gate no-regression
```

Anthropic 可使用 `--optimizer-provider anthropic`，并设置 `ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL`，以及可选的 `ANTHROPIC_BASE_URL`。模型名称需由使用者显式指定。

### 多模型服务与一键切换

除通用的 `openai` 配置外，内置两个官方 OpenAI 兼容服务的配置，各读各的环境变量，可同时写在被 Git 忽略的 `.env` 中（密钥不要写进脚本）：

| provider | 环境变量 | 默认 base URL |
| --- | --- | --- |
| `openai` | `OPENAI_API_KEY`、`OPENAI_MODEL`，可选 `OPENAI_BASE_URL`、`OPENAI_REASONING_EFFORT`、`OPENAI_THINKING` | `https://api.openai.com/v1` |
| `deepseek` | `DEEPSEEK_*`（同上） | `https://api.deepseek.com` |
| `zhipu` | `ZHIPU_*`（同上） | `https://open.bigmodel.cn/api/paas/v4` |

```dotenv
DEEPSEEK_API_KEY=替换为自己的密钥
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_REASONING_EFFORT=max
DEEPSEEK_THINKING=enabled
ZHIPU_API_KEY=替换为自己的密钥
ZHIPU_MODEL=glm-5.3
ZHIPU_REASONING_EFFORT=medium
ZHIPU_THINKING=enabled
```

切换模型只改 provider 名，不用改 `.env`：`serve --optimizer-provider`、`metric-bench --agent/--extractor`、`real-bench --provider`（L 模式）、`llm --agents 名=provider` 都接受 `openai` / `deepseek` / `zhipu` / `anthropic`。报告里的模型标识为 `deepseek:deepseek-flash`、`zhipu:glm-5.3`；`openai` 配置仍记为 `openai-compatible:模型名`，与旧报告一致。原来把 DeepSeek 写在 `OPENAI_*` 里的 `.env` 不用改。

```powershell
# 极小的真实 API 连通性测试：一次普通回复 + 一次工具调用往返，会产生少量用量；不发送项目数据，只允许官方地址
python tools/check-llm.py deepseek
python tools/check-llm.py zhipu
# 同一组 metric-bench 对照分别用两种模型跑（查询 Agent 与提炼器保持同一模型）
cargo run --release --locked -- --pool 16 --out results/ds metric-bench --agent deepseek --extractor deepseek
cargo run --release --locked -- --pool 16 --out results/glm metric-bench --agent zhipu --extractor zhipu
# 同一次 llm 评估中并排比较两种模型
cargo run --locked -- llm --agents ds=deepseek,glm=zhipu --modes direct,middle
```

说明：

- DeepSeek：根据 [官方模型说明](https://api-docs.deepseek.com/news/news260910/)，V4.1 Flash 的 API 标识是 `deepseek-flash`；工具对话需保留 `reasoning_content`，见其 [思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)。
- 智谱 BigModel：接口见 [HTTP 调用说明](https://docs.bigmodel.cn/cn/guide/develop/http/introduction)，使用 API key 直接作 Bearer 鉴权。GLM-5.2 及以上支持 `reasoning_effort`；GLM-5.3 强制思考，不能关闭。GLM-5.3 用 max 时，管理 adapter 的一次建议输出 1.1–1.7 万 tokens、耗时 185–300 秒以上，超过优化器 60 秒的等待上限，因此示例用 medium。[思考模式文档](https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode) 要求工具调用时原样回传 `reasoning_content`，项目对 `api.deepseek.com` 与 `open.bigmodel.cn` 都这样处理。
- 智谱用 HTTP 429 同时表示限流和欠费（1113）、内容审核（1301）、额度用尽（1308 / 1310），后几种不重试直接报错；回复 `finish_reason` 为 `sensitive`（输出被审核截断）或 `model_context_window_exceeded` 时按调用失败处理，在 `metric-bench` 中记为“出错”而不是答错。
- 只配置了 `*_REASONING_EFFORT` / `*_THINKING` 时才发送对应字段。用量里的推理 tokens 在两家都位于 `completion_tokens_details.reasoning_tokens`；智谱的缓存命中在 `prompt_tokens_details.cached_tokens`。

修改配置后需重启已运行的服务。此前的 Mock/真实数据实验没有调用 DeepSeek；新增的真实调用、用量和性能比较见 [DeepSeek 对照报告](docs/deepseek-real-validation.md)，与极小连通性测试单独统计。

### 管理 API

只有设置 `--optimizer-provider` 后，下列路由才会开放：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/v1/optimizer` | 当前策略、候选历史、版本和运行统计 |
| POST | `/v1/optimizer/propose` | 手动生成候选；此接口本身不会自动应用 |
| POST | `/v1/optimizer/apply/{id}` | 应用指定候选；一小时内、版本一致且通过回放门槛才可应用 |
| POST | `/v1/optimizer/rollback` | 恢复内置反馈排序，并使旧候选失效 |

PowerShell 示例：

```powershell
$proposal = Invoke-RestMethod -Method Post http://127.0.0.1:8088/v1/optimizer/propose
$proposal
Invoke-RestMethod -Method Post "http://127.0.0.1:8088/v1/optimizer/apply/$($proposal.id)"
Invoke-RestMethod http://127.0.0.1:8088/v1/optimizer
Invoke-RestMethod -Method Post http://127.0.0.1:8088/v1/optimizer/rollback
```

启动、候选生成、门槛拒绝（`reject`）、应用、手动回滚和自动回滚（`auto_rollback`）事件追加写入 `results/optimizer.jsonl`。策略版本和候选编号在当前进程内有效；重启后恢复内置算法并重新积累样本，历史日志保留但不自动加载历史策略。多个服务实例应使用不同的 `--out` 目录。自动模式下，回滚后如果继续产生新样本，下一周期仍可提出并应用新策略；要暂停自动管理，请重启为手动模式。

## Agent 工具 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/v1/tools` | 工具列表、描述与 JSON Schema |
| POST | `/v1/tools/{name}` | 调用工具 |
| GET | `/v1/stats` | 命中、撤销、修复、拒绝、数据库耗时等统计 |
| GET | `/v1/knowledge` | 当前进程中的经验库 |

统一请求体：

```json
{
  "agent": "analyst-a",
  "session": "session-1",
  "task": "task-1",
  "tables": ["store_sales", "store_returns"],
  "args": {"table": "store_returns"}
}
```

`agent` 必填，`session` 默认 `default`，`task` 默认空字符串。`tables` 为可选的工具访问范围，省略表示允许访问目录中的全部表。它由客户端自行声明，不能替代服务器端身份认证和数据库授权。

| 工具 | `args` |
| --- | --- |
| `list_tables` | `{}` |
| `describe_table` | `{"table":"store_returns"}` |
| `join_path` | `{"table_a":"store_returns","table_b":"store_sales"}` |
| `check_join` | `{"left":"store_returns","right":"store_sales","on":[["sr_ticket_number","ss_ticket_number"],["sr_item_sk","ss_item_sk"]]}` |
| `run_sql` | `{"sql":"select count(*) from store_returns"}` |

PowerShell 调用：

```powershell
$body = @{
  agent = "analyst-a"
  session = "session-1"
  args = @{ sql = "select count(*) from store_returns" }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/v1/tools/run_sql -ContentType 'application/json' -Body $body
```

成功的查询响应形如：

```json
{
  "result": {
    "columns": ["count"],
    "rows": [["123"]],
    "row_count": 1,
    "truncated": false
  },
  "source": "executed"
}
```

非空单元格以字符串返回，SQL NULL 返回 JSON `null`。`source` 可表示实际执行、缓存复用或在途合并。工具失败返回 HTTP 400 和 `error`；语义审查拒绝 SQL 则返回 HTTP 200 与 `rejected: true`、理由及修复建议，客户端应检查响应内容。经验撤销通知通过后续工具响应的 `notices` 返回。

## 演示与实验

### 2×2 消融：共享 × 自反馈

```powershell
./tools/ablation.ps1 -Rows 1000000 -Agents 24 -Tasks 48 -Rounds 4
```

等价命令：`cargo run --locked -- --pool 16 ablation --rows 1000000 --agents 24 --tasks 48 --rounds 4 --seed 42`。

| | 固定检查顺序 | 自反馈检查顺序 |
| --- | --- | --- |
| 不跨 Agent 共享 | A 基线 | C 只加反馈 |
| 全局共享 | B 只加共享 | D 共享 + 反馈 |

“不共享”定义为各 Agent 的经验库和反馈状态独立，仍保留该 Agent 自己的跨会话复用；“共享”包含画像、关联、检查、结果、版本读取和反馈经验的跨 Agent 复用。反馈因素使用内置自适应排序（回放门槛通过前保持默认顺序），不调用真实模型；本实验不把模型接入收益混入两个因素。

主矩阵四组均启用守护与结果缓存，**全部关闭 singleflight**，统一连接池大小。固定顺序组仍收集反馈并执行同样的审计，仅固定检查排列。审计按 `seed + 候选签名` 确定20%阈值抽样，不受先失败检查或并发调度影响；有限候选实际抽中比例未必恰为20%。所有 Agent 接收相同逻辑训练，训练成本单列，并同时报告包含训练和初始化的总成本。

主矩阵仅运行稳定数据上的八类混合负载；四轮轮换 A/B/C/D 执行位置，默认共 18,432 个测量请求。报告包含 B−A（共享）、C−A（反馈）、D−B（叠加反馈）、D−C（叠加共享）、D−A（整体）的逐轮配对差异和范围，以及成本交互项 `D−B−C+A`。成本交互项为负才表示超出加法的额外节约，不能仅凭 D 优于 A 宣称协同。

另外自动执行两个专项，避免混入主因素：

1. **singleflight 开/关**：关闭结果缓存，8 个 Agent 同步执行相同汇总，比较实际执行次数和合并数。
2. **守护开/关**：先学习 v1 关联，再应用 ETL；关闭结果缓存避免旧金额掩盖错误，比较静默金额高估、拒绝和修复后的结果。

所有运行均在新建独立数据库中完成并清理。`results/ablation-*/report.md` 为可读报告，`report.json` 和 `round-*.json` 保留配置、训练开销、逐请求预期/实际响应、实际检查轨迹及专项证据。默认开发构建、进程内脚本 Agent；多轮数字为描述性结果，不自动宣称统计显著或真实 LLM 收益。建议轮数为4的倍数，先用 `-Rows 10000 -Agents 4 -Tasks 8 -Rounds 1` 验证环境。

### 百万级多 Agent 对照实验

```bash
cargo run --locked -- --pool 16 bench --rows 1000000 --agents 24 --tasks 48 --rounds 3 --seed 42
```

Windows 也可执行 `./tools/scale-bench.ps1`，脚本会自动寻找 Cargo；例如 `./tools/scale-bench.ps1 -Rows 1000000 -Agents 24 -Tasks 48 -Rounds 3`。

此命令使用 `.env` 的 `AGENTDB_URL` 连接创建独立实验数据库，不修改连接串原数据库。结束后清理实验库，报告保留在 `results/bench-*/`。默认数据包括 100 万销售行、40 万退货行、11,397 条维度数据，以及 4 万行专门构造的关联陷阱数据。

- **并发规模**：24 个并发脚本 Agent，每 Agent 每阶段 48 个任务、6 个会话。两阶段 × 三种模式 × 三轮，总共 20,736 个测量请求。
- **八类负载**：共享表画像、分桶金额汇总、多对一维度关联、未见过的多对多陷阱、未过滤退货汇总、复合键关联、正确粒度汇总、不存在的列。
- **未见过的陷阱**：训练不访问 `risk_left/risk_right`；v1 和 v2 各使用 8 种不同的重复键，确保排序策略有机会在新候选上实际执行检查，而非只命中训练缓存。
- **三组对照**：`fixed` 固定顺序、`feedback` 内置反馈排序、`mock-managed` mock 管理策略。三组均启用共享缓存、在途合并与守护，只改变排序机制。
- **数据漂移**：v1 后应用状态流水 ETL，显式通知 adapter 并重验关联，再运行 v2。训练和漂移处理开销与测量阶段分开记录。
- **公平性与局限**：相同数据和任务序列、各轮轮换模式顺序，统一数据库预热；不清空 OS 缓存。`--seed` 固定任务排列，内部抽样审计仍有随机性。Agent 直接调用工具调度层，结果不包含 HTTP 和真实 LLM 的网络、推理或 token 开销。

以上命令默认使用开发构建，适合功能和相对对照，不代表生产容量。评估发布构建时使用 `cargo run --release --locked -- ...`，并重新运行全部对照组，不混用不同构建的耗时结果。

`report.md` 提供合并指标、逐轮结果、策略评分表、数据漂移证据链与场景覆盖；`report.json` 和 `round-*.json` 提供逐请求输入、预期值、实际响应、正确性与耗时。`check_traces` 可按 Agent / session / task 追踪计划顺序及执行、复用、合并的检查；复用记录中的耗时来自原检查，不应再次当作实际数据库开销累加。每阶段最多保留 20,000 条检查追踪。

模型建议包含 `heuristic_reference`：样本数、失败数、平均耗时、平滑失败概率和参考分数。mock 按 `((fails+1)/(runs+2))/(mean_ms+1)` 排序；真实 LLM 的建议不保证使用这个公式。请求“正确”包含按预期拒绝错误关联或无效输入，不表示每个请求都返回了业务结果。

参数支持最多 500 万销售行、128 个 Agent、每阶段每 Agent 1000 个任务和 10 轮；规模越大，运行时间及逐请求报告体积也会增加。先用 `--rows 10000 --agents 4 --tasks 8 --rounds 1` 检查连接，再运行完整规模。

```bash
cargo run --locked -- demo
cargo run --locked -- etl status
cargo run --locked -- etl apply-v2
cargo run --locked -- etl reset
```

v1 中每条退货只有一行，`sr_status='完成'`。v2 为 2001-10-01 及之后的退货添加一条 `申请` 状态记录，旧的金额汇总可能重复计数。该场景用来验证 adapter 能否发现旧经验失效并补上正确的粒度过滤。

| 实验 | 目标 | 默认模式 |
| --- | --- | --- |
| `exp1` | 比较不同共享范围及在途合并的数据库负载 | `session,agent,global,global+sf` |
| `exp2` | ETL 改版后的静默错误与守护修复 | `fresh-session,agent-memory,global-noguard,global-guard,global-always` |
| `exp3` | 错误关联验证与反馈检查排序 | `direct,A-session-fixed,C-session-feedback,B-global-fixed,D-global-feedback` |

```bash
cargo run --locked -- exp1 --agents 3 --sessions 3 --tasks 10 --concurrency 1,8 --seed 42
cargo run --locked -- exp2 --verbose
cargo run --locked -- exp3 --agents 3 --sessions 2 --tasks 6 --p-trap 0.5 --seed 7
```

`exp1` 还支持 `task` 和 `session+sf`；它从 99 条查询提取探查与关联验证需求，不是运行完整 TPC-DS 性能基准。实验报告输出为 `results/exp1.json` / `.md` 等，同名报告会覆盖。请从仓库根目录运行，以便定位查询文件。

### 查询 Agent 的 LLM 评估

这里的 `llm` 子命令评估“模型查询数据库”，与 `serve --optimizer-provider ...` 的“模型管理 adapter”是独立功能：

```bash
cargo run --locked -- llm
cargo run --locked -- llm --agents analyst=openai --modes direct,middle --questions Q1,Q2 --max-steps 20
cargo run --locked -- llm --agents ds=deepseek,glm=zhipu --modes direct,middle
```

默认使用 `mock-a=mock,mock-b=mock`，无需模型 key，但仍需完整实验数据库。问题编号为 Q1–Q8；报告输出为 `results/llm.json` 和 `.md`。`direct` 是通过基础工具执行的对照组，关闭中间层部分复用和验证能力，并非独立的数据库驱动。

## 开发与测试

```bash
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets
```

单元测试不需要数据库或真实模型 key，覆盖参数校验、SQL 缓存键、关联列校验、并发合并，审计样本回放（首个失败截断、补查代价、历史成本不可变、候选分组与训练隔离）、自适应顺序的采纳与退回，以及管理策略的校验、回放门槛、应用、过期版本拒绝、退化自动回滚、手动回滚和审计。GitHub Actions 在 Linux / Windows 上执行格式、测试和静态检查。

### PostgreSQL + mock 端到端测试

将以下连接配置写入被 Git 忽略的 `.env`，也可设置同名环境变量：

```dotenv
AGENTDB_TEST_URL=postgres://测试账号:密码@127.0.0.1:5432/postgres
```

该账号需要 `LOGIN` 和 `CREATEDB`，不需要超级用户权限。测试创建唯一命名的临时数据库，装载 `data/mock_fixture.sql`，启动真实 HTTP 服务，并在结束后删除临时数据库；不会向连接串所指的原数据库装载数据。

```powershell
# Windows：单元测试 + PG 集成测试 + 静态检查 + 格式检查
./tools/mock-test.ps1
```

也可以单独运行集成测试：

```bash
cargo test --locked postgres_http_mock_lifecycle -- --ignored --nocapture
```

测试覆盖只读连接、空结果列名、缓存隔离和命中、并发请求合并、样本不足拒绝、真实反馈驱动的 mock 策略自动应用（该夹具只有合法关联，没有审计失败样本，因此使用 `no-regression` 门槛）、无新增反馈时跳过模型、回滚及旧策略失效、多对一关联、ETL 变更后的守护和粒度修复。结果与审计日志保存在 `results/mock-*/report.json` 和 `optimizer.jsonl`。

最小数据包含 10 条销售、10 条退货和四张维度表；ETL v2 增加 2 条状态行。正确退货金额合计仍为 `100.00`，未过滤的旧查询应被拦截。此数据用于功能验证，不能替代完整 `demo`、`exp1`–`exp3` 或 `llm` 业务评估所需的 TPC-DS 数据。CI 另有 PostgreSQL 16 服务任务运行该测试。

| 文件 | 职责 |
| --- | --- |
| `src/main.rs` | CLI 参数和命令入口 |
| `src/server.rs` | 工具 API、管理 API、定期优化任务 |
| `src/optimizer.rs` | 模型策略、版本、应用、回滚、审计 |
| `src/middle.rs` | 共享、守护、修复与工具调度 |
| `src/feedback.rs` | 内置反馈排序、审计样本回放评估与采纳判断、模型策略的执行入口 |
| `src/knowledge.rs` / `src/flight.rs` | 经验库 / 在途合并 |
| `src/catalog.rs` / `src/checks.rs` | 数据目录、版本和语义检查 |
| `src/db.rs` / `src/etl.rs` | 数据库访问计量 / ETL 场景 |
| `src/sqlscan.rs` | TPC-DS 场景的轻量 SQL 扫描 |
| `src/llm.rs` | 模型客户端与查询 Agent 评估 |
| `src/sim.rs` / `src/workload.rs` | 脚本实验、查询负载与标准答案 |

## 已知边界与后续方向

- SQL 表依赖、关联及过滤条件识别使用轻量文本扫描，依赖 TPC-DS 的列名前缀；尚不能对任意 SQL、视图、函数、复杂子查询提供完整解析和权限隔离。过滤条件的文本匹配不是语义证明。
- HTTP 接口没有认证、租户隔离或速率限制；默认只监听本机。正式部署前需要补齐服务端认证授权，管理 API 和经验库接口尤其需要限制访问。
- 数据库连接当前使用 `NoTls`；默认只读会话参数不等于面向恶意 SQL 的安全沙箱。
- 版本统计异步刷新，默认缓存 200 ms，不提供事务级一致性；表目录加载于启动阶段，结构变化后可能需要重启。查询结果缓存也未区分随机函数、时间函数等易变表达式。
- 查询结果在内存中完整收集后截取最多 50 行，因此返回行数限制不是数据库执行成本或内存限制。默认单条 SQL 超时为 300 秒；`metric-bench` 的 Agent 连接池默认 60 秒（`--sql-timeout-secs`）。
- 经验库、反馈与策略状态保存在内存中，没有容量淘汰；优化事件日志持久保存，但尚未实现策略跨重启恢复。
- 当前模型策略是全局检查类型排序；内置反馈已按表 / 表对统计，并用审计样本回放决定是否采纳。回放是离线估计，不等于线上灰度实验；后续可增加线上灰度评估、更大的策略空间（守卫强度、结果缓存准入、漂移后主动重验）、持久经验库与完整 SQL 解析。

常见问题：缺少 `store_returns` 表说明还未完成数据装载；模型提示样本不足时，先通过业务工具产生实际关联检查；模型响应被拒绝时查看错误信息，现有策略不会被替换；实验中断后，可执行 `etl reset` 恢复本项目模拟的 v1 状态。
