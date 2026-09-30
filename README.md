# agent4db-adapter

MAVRA（Maintaining Shared Metric Definitions for Data Agents）的系统原型：一个位于数据智能体与 PostgreSQL 之间的 Rust 中间层。多个 Agent 共享从成功轨迹中提炼的指标定义；每个定义的正确性落到可执行的有效性条件（过滤后的键唯一性、连接多重性、时间角色）上，数据变化后按条件选择性重验，跨定义复用条件结论，失效时撤销并做经过回归的受限修复，执行端核对声明的定义修订。

## 论文

论文源文件与实验依据在 [overleaf/](overleaf/README.md)：

- [中英文双语稿](overleaf/main.tex)：SIGMOD 2027 双栏匿名格式，XeLaTeX；改稿只改这一份。
- [英文稿](overleaf/main-en.tex)：由 `overleaf/export-english.sh`（Linux）或 `export-english.ps1`（Windows）从双语稿生成。
- `overleaf/build.sh`：在 noctis 上编译两份 PDF 并报告页数。
- [研究状态](overleaf/RESEARCH_STATUS.md)：已有证据与尚未实现的机制。

## 目录

| 路径 | 内容 |
| --- | --- |
| `src/` | 中间层与两个评测命令 |
| `exp/` | 论文所用实验的整理结果，索引见 [exp/README.md](exp/README.md) |
| `docs/` | [指标经验设计与评测协议](docs/metric-experience-protocol.md)、[相关工作与审稿质疑](docs/related-work.md) |
| `overleaf/` | 论文 |
| `tools/check-llm.py` | 模型 API 的极小连通性测试 |
| `data/mock_fixture.sql` | PostgreSQL 集成测试的最小数据 |

| 文件 | 职责 |
| --- | --- |
| `src/main.rs` | CLI 入口 |
| `src/middle.rs` | 共享、守护、修复与工具调度 |
| `src/middle/metrics.rs` | 指标定义的准入（G1–G8）、条件维护、撤销与受限修复、执行端修订核对 |
| `src/metric.rs` | 指标定义的纯逻辑：题型、规范 SQL 编译、计算链求值、静态检查、离线提炼 |
| `src/metricbench.rs` | 端到端 LLM 评测（`metric-bench`） |
| `src/maintbench.rs` | 维护方式对照，不调用 LLM（`maint-bench`） |
| `src/knowledge.rs` / `src/flight.rs` | 经验库 / 在途合并 |
| `src/catalog.rs` / `src/checks.rs` | 数据目录、表版本与语义检查 |
| `src/feedback.rs` | 检查顺序的执行反馈与回放采纳 |
| `src/db.rs` / `src/etl.rs` | 数据库访问计量 / ETL 场景 |
| `src/sqlscan.rs` | 轻量 SQL 扫描 |
| `src/llm.rs` | 模型客户端与 Agent 工具循环 |
| `src/server.rs` | HTTP 工具接口 |

## 环境

- Rust stable 与 Cargo。
- PostgreSQL 15 或更高版本，连接账号需要 `CREATEDB`。两个评测命令都会新建独立实验库、生成合成零售数据，结束后删除，不修改连接串所指的数据库。
- 真实模型实验需要模型 API key，写在被 Git 忽略的 `.env`（从 `.env.example` 复制）。

实验在 noctis 上运行：PostgreSQL 18.6，端口 55432，关闭 WAL 与 fsync，代码在 `/root/agentdb-mid`，原始输出写到被 Git 忽略的 `results/`。

```bash
cargo build --release --locked
cp .env.example .env   # 填入 AGENTDB_URL 与模型 key
```

通用参数放在子命令前：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--db` / `AGENTDB_URL` | `postgres://postgres@127.0.0.1:55432/tpcds` | 连接串，评测命令用它创建独立实验库 |
| `--pool` | `16` | Agent 只读连接池大小 |
| `--out` | `results` | 报告输出目录 |

## 实验

### 维护方式对照（`maint-bench`，不调用 LLM）

相同的口径集合与数据变化序列（三次正常追加 + 一次 v2 状态流水破坏）下，比较逐写入撤销（`revoke`）、只看结构（`schema`）、定义级重验（`definition`）、条件级重验但不复用结论（`condition-scope`）与条件级重验加跨定义复用（`condition`）。脚本 Agent 在每次变化后按随机顺序使用全部口径，记录过期使用、误撤销、不可用、维护 DB 时间与等待。

```bash
./target/release/agentdb-mid --pool 16 maint-bench --agents 8 --share 1,2,4,6
# 反序复验，抵消执行顺序与缓存冷热
./target/release/agentdb-mid --pool 16 maint-bench --agents 8 --share 1,2,4,6 --policies condition,condition-scope,definition,schema,revoke
```

`--share k` 控制每个口径族取前 k 个口径（6 为全部 19 个），`--arrivals staggered,burst` 为错峰与同时到达。先用 `--rows 20000 --share 1` 检查环境。

### 端到端 LLM 评测（`metric-bench`）

Agent A 在学习题上探索并由提炼器生成候选口径，经准入后共享；未接触过指标的 Agent B 做留出题，中途应用 v2 数据变化。

```bash
./target/release/agentdb-mid --pool 16 metric-bench --agent deepseek --extractor deepseek \
  --metrics M1,M2,M3 --phrasings named \
  --modes middle,metric-global,metric-global-def,metric-global-schema,metric-global-revoke,metric-global-noguard
```

| 模式 | 含义 |
| --- | --- |
| `direct` | 只有基础工具，无中间层复用与验证 |
| `middle` | 中间层，不共享指标定义 |
| `metric-local` / `metric-global` | 指标定义按 Agent / 全局共享，条件级维护 |
| `metric-global-def` / `-schema` / `-revoke` | 只换维护方式：定义级重验 / 只看结构 / 逐写入撤销后重新提炼 |
| `metric-global-noguard` | 关闭守护 |

`--phrasings named` 只报指标名，`defined` 在题面写出口径。

### 模型服务

内置三个 OpenAI 兼容配置，各读各的环境变量；切换模型只改 provider 名（`metric-bench --agent/--extractor`），不用改 `.env`：

| provider | 环境变量 | 默认 base URL |
| --- | --- | --- |
| `openai` | `OPENAI_API_KEY`、`OPENAI_MODEL`，可选 `OPENAI_BASE_URL`、`OPENAI_REASONING_EFFORT`、`OPENAI_THINKING` | `https://api.openai.com/v1` |
| `deepseek` | `DEEPSEEK_*`（同上） | `https://api.deepseek.com` |
| `zhipu` | `ZHIPU_*`（同上） | `https://open.bigmodel.cn/api/paas/v4` |

另有 `anthropic`（`ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL`，可选 `ANTHROPIC_BASE_URL`）。

```dotenv
DEEPSEEK_API_KEY=替换为自己的密钥
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_REASONING_EFFORT=max
DEEPSEEK_THINKING=enabled
ZHIPU_API_KEY=替换为自己的密钥
ZHIPU_MODEL=glm-5.3
ZHIPU_REASONING_EFFORT=high
ZHIPU_THINKING=enabled
```

```bash
# 极小的真实 API 连通性测试：一次普通回复 + 一次工具调用往返；不发送项目数据，只允许官方地址
python tools/check-llm.py deepseek
python tools/check-llm.py zhipu
```

- DeepSeek：V4.1 Flash 的 API 标识是 `deepseek-flash`（[官方说明](https://api-docs.deepseek.com/news/news260910/)）；工具对话需原样回传 `reasoning_content`（[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)）。
- 智谱 BigModel：API key 直接作 Bearer 鉴权（[HTTP 调用说明](https://docs.bigmodel.cn/cn/guide/develop/http/introduction)）。GLM-5.3 强制思考，工具调用时同样原样回传 `reasoning_content`（[思考模式](https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode)）。智谱用 HTTP 429 同时表示限流、欠费（1113）、内容审核（1301）和额度用尽（1308 / 1310），后几种不重试；`finish_reason` 为 `sensitive` 或 `model_context_window_exceeded` 时按调用失败处理，在 `metric-bench` 中记为“出错”而非答错。
- 只配置了 `*_REASONING_EFFORT` / `*_THINKING` 时才发送对应字段。

## HTTP 工具接口

```bash
./target/release/agentdb-mid setup                       # 状态列与 ETL 批次表（幂等）
./target/release/agentdb-mid serve --addr 127.0.0.1:8088
./target/release/agentdb-mid etl status                  # 也可 apply-v2 / reset
```

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/v1/tools` | 工具列表、描述与 JSON Schema |
| POST | `/v1/tools/{name}` | 调用工具，body：`{"agent": "...", "session": "...", "task": "...", "tables": [...], "args": {...}}` |
| GET | `/v1/stats` | 命中、撤销、修复、拒绝、数据库耗时等统计 |
| GET | `/v1/knowledge` | 当前进程中的经验库 |

工具有 `list_tables`、`describe_table`、`join_path`、`check_join`、`run_sql`，共享指标定义时另有 `find_metric`。`agent` 必填，`session` 默认 `default`；`tables` 是客户端自报的访问范围，不能替代服务端认证。语义审查拒绝的 SQL 返回 HTTP 200 与 `rejected: true`、理由及修复建议；经验撤销通知通过后续响应的 `notices` 返回。

## 开发与测试

在 noctis 上运行（本机只做编码）：

```bash
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
# PostgreSQL + HTTP 集成测试：创建临时库、装载 data/mock_fixture.sql、启动 HTTP 服务，结束后删除
AGENTDB_TEST_URL=postgres://postgres:postgres@127.0.0.1:55432/postgres \
  cargo test --locked postgres_http_mock_lifecycle -- --ignored --nocapture
```

集成测试覆盖只读连接、空结果列名、缓存隔离与命中、并发请求合并、多对一关联，以及 ETL 变更后的守护、粒度修复和未过滤 SQL 的拦截。GitHub Actions 执行同样的检查。

## 已知边界

- SQL 表依赖、关联与过滤识别使用轻量文本扫描，依赖列名前缀；不是完整 SQL 解析，过滤条件的文本匹配不是语义证明。
- 同快照验证与执行、修复进行中的请求等待尚未实现，见 [研究状态](overleaf/RESEARCH_STATUS.md)。
- 版本统计异步刷新，默认缓存 200 ms，不提供事务级一致性；表目录在启动时加载。
- HTTP 接口没有认证、租户隔离或速率限制，默认只监听本机；数据库连接使用 `NoTls`。
- 经验库与反馈状态只在内存中，没有持久化与容量淘汰。
