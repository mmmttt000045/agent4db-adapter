# 实验数据

每次实验一个目录，命名 `日期-内容`。程序默认把原始输出写到 `results/`（不进 Git），整理后放到这里。单文件过大的原始数据只留在服务器，下表注明位置。

环境：noctis（48 核 Hygon、98 GiB），PostgreSQL 18.6，端口 55432，关闭 WAL 与 fsync（见 `/etc/postgresql/18/main/conf.d/agentdb.conf`）。真实模型为 DeepSeek V4.1 Flash（`deepseek-flash`，max 思考），查询 Agent 与提炼器相同。

| 目录 | 代码 | 命令 | 内容 | 主要结果 |
|---|---|---|---|---|
| `2026-09-29-ablation-2x2` | `1da4ac1` | `ablation --rows 1000000 --agents 24 --tasks 48 --rounds 4 --seed 42` | 共享 × 反馈 2×2 消融，脚本 Agent，另含并发合并与守护专项 | 共享使测量 DB 成本降 50.3%（48.1–51.9%）；反馈无收益（−1.3%）；8 个相同请求合并为 1 次执行；守护关闭时金额错 24.7%，开启后撤销、修复并拦下未过滤 SQL |
| `2026-09-29-metric-trial-M2` | `1da4ac1` + 未提交的指标经验实现（两处修复之前） | `metric-bench --rows 100000 --modes middle,metric-global --phrasings defined --metrics M2` | 门店退货金额，带口径题面，普通中间层 vs 共享口径 | 两组 6/6 全对；v2 后共享组输入 token 49.5k vs 203.5k；暴露两个问题（v2 后首题拿不到修复口径；诊断查询被误拦） |
| `2026-09-29-metric-direct-M1M3` | 同上 + 两处修复 | `metric-bench --metrics M1,M3`（全组，跑完直连组两种题面后手动停止） | 直连组，门店营业额与门店退货率，1M 行 | 带口径 15/15；只报指标名 5/15，错误全部是口径选择 |
| `2026-09-29-metric-shared-named-M1M3` | 同上 | `metric-bench --metrics M1,M3 --modes metric-global --phrasings named` | 共享口径组，只报指标名，1M 行 | 15/15；含学习成本输入 token 0.41M vs 直连 3.30M；v2 撤销后同一请求内修复为 r1 |
| `2026-09-29-maint-share` | `5e82e37` | `maint-bench --agents 8 --share 1,2,4,6`（1M 行） | 维护方式对照 + 共享度扫描，不调用 LLM，4 共享度 × 5 维护方式 × 2 到达方式 = 40 组 | 错峰到达时条件级 DB 时间为定义级的 0.39 / 0.23 / 0.15 / 0.13（k = 1 / 2 / 4 / 6），同时到达 0.64 / 0.74 / 0.59 / 0.48；三种重验的过期使用与误撤销均为 0 |
| `2026-09-30-metric-maint-named` | `5e82e37` + 计算链与 G3 修复 | `metric-bench --metrics M1,M2,M3 --phrasings named --modes metric-global,metric-global-def,metric-global-schema,metric-global-revoke,metric-global-noguard`；普通中间层取 9-29 22:06 一轮（`cell-r1-middle-named.json`） | 端到端 LLM 维护对照，只报指标名，21 道计分题 | 条件级、定义级、写入即撤销 21/21；只看结构 18/21（v2 后 M2 三题答案翻倍）；无守护 12/21（其中 6 个因 M3 未学到）；普通中间层 11/21；维护 DB 条件级 22.4 s、定义级 52.9 s |
| `2026-09-30-maint-share-rev` | `5e82e37` + 计算链与 G3 修复（`maint-bench` 不涉及） | `maint-bench --agents 8 --share 1,2,4,6 --policies condition,condition-scope,definition,schema,revoke` | 同 `2026-09-29-maint-share`，维护方式反序执行（条件级最先），抵消顺序与缓存冷热 | 错峰 0.36 / 0.20 / 0.16 / 0.13，同时 0.73 / 0.77 / 0.59 / 0.41（k = 1 / 2 / 4 / 6），与正序一致；过期使用与误撤销仍为 0 |

- 两次指标实验的数据完全由确定性公式生成，同样行数下数据与标准答案相同，可跨目录比较。
- 消融的逐轮数据（`round-*.json`，共 56 MB）与 31 MB 的 `report.json` 在 noctis 的 `/root/agentdb-mid/results/ablation-1790658664143008/`。
- 维护方式对照的 `report.json`（7 MB）与各组 `cell-*.json` 在 noctis 的 `/root/agentdb-mid/results/maint-1790686347212630/`；反序复验在 `/root/agentdb-mid/results/maint-1790707404365821/`；两个目录里的 `cells.txt` 是从中提取的每组合计（过期使用、误撤销、不可用、维护结果、条件处理计数、DB 时间、等待时长）。
- 分析见 `docs/notes/2026-09-29-experiments.md`。
