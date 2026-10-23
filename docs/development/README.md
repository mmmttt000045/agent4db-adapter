# 开发、运行与测试

本文命令均从仓库根目录执行。各批实验的模型、数据库参数和排除规则以 [实验协议](../../exp/README.md) 为准；下述 noctis 环境是历史运行配置。当前工作入口见 [项目首页](../../README.md)。

## 环境

- Rust stable 与 Cargo。
- PostgreSQL 15 或更高版本，连接账号需要 `CREATEDB`。评测命令都会新建独立实验库、生成合成零售数据，结束后删除，不修改连接串所指的数据库。
- 真实模型实验需要模型 API key，写在被 Git 忽略的 `.env`（从 `.env.example` 复制）。

实验在 noctis 上运行：PostgreSQL 18.6，端口 55432，WAL 级别为 minimal，关闭 fsync、full-page writes 及同步提交。代码在 `/root/agentdb-mid`，原始输出写到被 Git 忽略的 `results/`；10-03 补充实验的原始输出所在的服务器目录见 [exp/README.md](../../exp/README.md)。

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

### 工作负载刻画（`workload-bench`）

刻画 Agent 负载与应用负载的差别。每个会话是一个全新的 Agent，只有直连工具（`list_tables`、`describe_table`、`run_sql`），会话之间不共享任何状态；多个会话以固定并发同时访问同一数据库。题目与 `metric-bench` 相同（5 个指标 × 5 道题 × 两种题面 × `--repeats` 次），顺序按种子打乱。

```bash
CLINE_MODEL=cline-pass/glm-5.3 ./target/release/agentdb-mid --pool 16 workload-bench --agent cline --repeats 2 --concurrency 3
python3 tools/workload-stats.py results/workload-*/
```

输出目录里 `trace.jsonl` 逐次记录工具调用（参数、状态、耗时、返回摘要、调用前的思考末尾），`sessions.jsonl` 逐会话记录答案与判题，`app.json` 是应用把同样的题写成参数化 SQL 时的查询。

### 固定定义库的会话耗时（`session-bench`）

重用已完成场景实验的定义库，固定题目与更新序列，只改变共享和维护方式。每道题都由全新 Agent 会话回答；记录首次使用、热复用、正常追加后首用、状态流水破坏后首用和突发到达。定义库加载/准入单列，任务记录 LLM、工具、验证、修复、在途合并等待和突发入场排队。SQL 工作按实际执行请求归属，嵌套耗时由分析脚本切成互斥区间。

```bash
./target/release/agentdb-mid --pool 16 --out results/session-latency session-bench \
  --libs results/scen-20261002/dsv41flash-r1-b/metric-1790916886275999/cell-r1-metric-global-named.json
python3 tools/session-latency-stats.py results/session-latency/session-*/ --out results/session-latency/analysis --plot
```

三份固定库、四种方法的完整矩阵由 `tools/run-session-latency.py` 运行，设计与证据见 [实验协议](../../exp/2026-10-03-session-latency/README.md) 和 [216 会话的结果](../../exp/2026-10-03-session-latency/report.md)。默认沿用 `.env` 中的 Cline 模型，修复参照使用原 Agent 的示例 SQL；不重新学习定义。此处的首次使用不代表操作系统或数据库冷缓存。

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

## 共享记忆补充实验

所有主分析消费者题面包含相同业务定义。四组复用相同生产者轨迹前缀，关闭答案缓存、消费者跨题写回和策略适应；命名题另行分析。正式运行使用固定模型和三个独立生产者流，保留失败和未采纳结果。

```bash
CLINE_MODEL=cline-pass/deepseek-v4.1-flash \
CLINE_REQUIRE_MODEL=deepseek/deepseek-v4.1-flash \
CLINE_REASONING_EFFORT=high CLINE_HEDGE=1 \
  python3 tools/run-memory-study.py --jobs 3 --out results/shared-memory-new
python3 tools/run-strategy-study.py
python3 tools/metadata-audit.py
python3 tools/memory-study-stats.py \
  --memory results/shared-memory-new \
  --strategy results/strategy-main \
  --metadata results/metadata-audit/report.json \
  --out exp/2026-10-03-shared-memory/analysis
```

元数据诊断是探索性检查：它区分画像的跨智能体复用、带 ETL 通知的数据更新，以及目录刷新尚未实现的边界。生产者学习与完整策略审计成本单列，不能把回放节省写成包含建库成本的完整会话加速。

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

运行全套数据库集成测试时，调试构建使用 `RUST_MIN_STACK=33554432`，并设置私有的 `AGENTDB_TEST_URL`；建议 `--test-threads=1`。

集成测试覆盖只读连接、空结果列名、缓存隔离与命中、并发请求合并、多对一关联，以及 ETL 变更后的守护、粒度修复和未过滤 SQL 的拦截；新增连接方向反例验证事实金额不会因反向引用被重复累计。GitHub Actions 执行同样的检查。

## 已知边界

- SQL 表依赖、关联与过滤识别使用轻量文本扫描，依赖列名前缀；不是完整 SQL 解析，过滤条件的文本匹配不是语义证明。
- 同快照验证与执行已实现但默认关闭（`MiddleConfig::snapshot_exec`，需先 `catalog::install_tx_versions` 安装版本触发器）；修复进行中到达的使用会等待那次维护结束（`MiddleConfig::wait_repair`，默认打开），见 [研究状态](../research/README.md)。
- 默认的版本来源是异步刷新的统计计数（缓存 200 ms），不提供事务级一致性；打开快照绑定执行后改用事务性版本。表目录在启动时加载。
- HTTP 接口没有认证、租户隔离或速率限制，默认只监听本机；数据库连接使用 `NoTls`。
- 经验库与反馈状态只在内存中，没有持久化与容量淘汰。
