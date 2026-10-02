# 实验数据

每次实验一个目录，命名 `日期-内容`。程序默认把原始输出写到 `results/`（不进 Git），整理后放到这里。单文件过大的原始数据只留在服务器，下表注明位置。

环境：noctis（48 核 Hygon、98 GiB），PostgreSQL 18.6，端口 55432，关闭 WAL 与 fsync（见 `/etc/postgresql/18/main/conf.d/agentdb.conf`）。真实模型为 DeepSeek V4.1 Flash（`deepseek-flash`，max 思考），查询 Agent 与提炼器相同。

| 目录 | 代码 | 命令 | 内容 | 主要结果 |
|---|---|---|---|---|
| `2026-09-29-maint-share` | `5e82e37` | `maint-bench --agents 8 --share 1,2,4,6`（1M 行） | 维护方式对照 + 共享度扫描，不调用 LLM，4 共享度 × 5 维护方式 × 2 到达方式 = 40 组 | 错峰到达时条件级 DB 时间为定义级的 0.39 / 0.23 / 0.15 / 0.13（k = 1 / 2 / 4 / 6），同时到达 0.64 / 0.74 / 0.59 / 0.48；三种重验的过期使用与误撤销均为 0 |
| `2026-09-30-metric-maint-named` | `5e82e37` + 计算链与 G3 修复 | `metric-bench --metrics M1,M2,M3 --phrasings named --modes metric-global,metric-global-def,metric-global-schema,metric-global-revoke,metric-global-noguard`；普通中间层取 9-29 22:06 一轮（`cell-r1-middle-named.json`） | 端到端 LLM 维护对照，只报指标名，21 道计分题 | 条件级、定义级、写入即撤销 21/21；只看结构 18/21（v2 后 M2 三题答案翻倍）；无守护 12/21（其中 6 个因 M3 未学到）；普通中间层 11/21；维护 DB 条件级 22.4 s、定义级 52.9 s |
| `2026-09-30-maint-share-rev` | `5e82e37` + 计算链与 G3 修复（`maint-bench` 不涉及） | `maint-bench --agents 8 --share 1,2,4,6 --policies condition,condition-scope,definition,schema,revoke` | 同 `2026-09-29-maint-share`，维护方式反序执行（条件级最先），抵消顺序与缓存冷热 | 错峰 0.36 / 0.20 / 0.16 / 0.13，同时 0.73 / 0.77 / 0.59 / 0.41（k = 1 / 2 / 4 / 6），与正序一致；过期使用与误撤销仍为 0 |
| `2026-10-01-workload-characterization` | `9b98bc9` | `workload-bench --agent cline --repeats 2 --concurrency 3`（`CLINE_MODEL=deepseek/deepseek-v4.1-flash`，按量计费）；`python3 tools/workload-stats.py`；Redset 分析脚本在 noctis `results/workload-baselines/redset/` | Agent 负载与应用负载对照：100 个互不共享的 Agent 会话（25 题 × 两种题面 × 2 次，并发 3）对 Amazon Redset 全部 400 个集群（4.41 亿条查询） | Agent 的 176 条 SQL 有 133 个模板（Redset 读查询 93.4% 复用已有模板）；67.9% 的调用是探查（Redset 系统表查询 7.6%）；92.9% 的知识性调用重复其他会话已获得的事实，90.8% 在 60 秒内有其他会话做同一事实（Redset 不同用户同模板 0.61%）；SQL 出错仅 1.7%，但 32 个答错会话全部没有任何报错 |
| `2026-10-01-scenarios` | `26c2b48` 起（场景）；`tools/paper-results.py` | 12 个 `metric-bench` 任务（`results/queue-scen.sh`：3 模型 × 6 方法 × 3 次，`--changes` 十种）；`python3 tools/paper-results.py --scen results/scen-20260930 --out overleaf/gen` | 三模型十种数据变化的端到端对照，论文第 7.6 节与 `gen/` 的来源 | 分析 43 组、3,701 道计分题：不共享 32%、条件级 74%、定义级 77%（11 种情形等权）；已建模破坏性变化下条件级零过期使用（只看结构 195、无守护 201 道）；维护 DB 条件级 180 s／组、定义级 367 s／组；重复装载与日期键改写检测但无法修复，单位变化未建模 |

- 两个评测命令的数据完全由确定性公式生成，同样行数下数据与标准答案相同，可跨目录比较。
- 维护方式对照的 `report.json`（7 MB）与各组 `cell-*.json` 在 noctis 的 `/root/agentdb-mid/results/maint-1790686347212630/`；反序复验在 `/root/agentdb-mid/results/maint-1790707404365821/`；两个目录里的 `cells.txt` 是从中提取的每组合计（过期使用、误撤销、不可用、维护结果、条件处理计数、DB 时间、等待时长）。
- 端到端实验的原始输出在 noctis 的 `/root/agentdb-mid/results/metric-1790700840466648/`（5 组共享口径）与 `results/metric-1790690815978959/`（其中只有 `cell-r1-middle-named.json` 被采用，其余组来自有提炼缺陷的一轮，已弃用）。
- 早期维护与单模型实验的历史分析见 `2026-09-30-metric-maint-named/analysis.md`，原有核对数据保存在同目录的 `verified-results.json`。更早的试跑（2×2 消融、M1–M3 试跑）已从仓库移除，需要时从 Git 历史 `d15e4af` 取回。
- 工作负载刻画：`deepseek-v4.1-flash/` 为原始轨迹，`workload-stats.*` 为统计结果，`audit-sample.jsonl` 为人工核对样本，`redset/` 为 Redset 统计与说明（原始 parquet 17 GB 只在 noctis 的 `results/workload-baselines/redset/data/`）。GLM-5.3 与 GLM-5.3 Flash 两组因 Cline 余额耗尽（HTTP 402）只完成 16 / 0 个会话，未纳入。
- 数据变化场景：原始逐组 JSON 在 noctis 的 `results/scen-20260930/<任务>/metric-*/`（约 45 个 cell，每个 100–200 KB），这里只放 `paper-results.json`（使用了哪些组、剔除原因、逐模型逐场景计数）。ClinePass 周用量上限使 12 组含失败题、9 组未完成，约 2026-10-07 重置后补跑。
