# 实验数据

每次实验一个目录，命名 `日期-内容`。程序默认把原始输出写到 `results/`（不进 Git），整理后放到这里。单文件过大的原始数据只留在服务器，下表注明位置。

环境：noctis（48 核 Hygon、98 GiB），PostgreSQL 18.6，端口 55432，关闭 WAL 与 fsync（见 `/etc/postgresql/18/main/conf.d/agentdb.conf`）。真实模型为 DeepSeek V4.1 Flash（`deepseek-flash`，max 思考），查询 Agent 与提炼器相同。

| 目录 | 代码 | 命令 | 内容 | 主要结果 |
|---|---|---|---|---|
| `2026-09-29-ablation-2x2` | `1da4ac1` | `ablation --rows 1000000 --agents 24 --tasks 48 --rounds 4 --seed 42` | 共享 × 反馈 2×2 消融，脚本 Agent，另含并发合并与守护专项 | 共享使测量 DB 成本降 50.3%（48.1–51.9%）；反馈无收益（−1.3%）；8 个相同请求合并为 1 次执行；守护关闭时金额错 24.7%，开启后撤销、修复并拦下未过滤 SQL |
| `2026-09-29-metric-trial-M2` | `1da4ac1` + 未提交的指标经验实现（两处修复之前） | `metric-bench --rows 100000 --modes middle,metric-global --phrasings defined --metrics M2` | 门店退货金额，带口径题面，普通中间层 vs 共享口径 | 两组 6/6 全对；v2 后共享组输入 token 49.5k vs 203.5k；暴露两个问题（v2 后首题拿不到修复口径；诊断查询被误拦） |
| `2026-09-29-metric-direct-M1M3` | 同上 + 两处修复 | `metric-bench --metrics M1,M3`（全组，跑完直连组两种题面后手动停止） | 直连组，门店营业额与门店退货率，1M 行 | 带口径 15/15；只报指标名 5/15，错误全部是口径选择 |
| `2026-09-29-metric-shared-named-M1M3` | 同上 | `metric-bench --metrics M1,M3 --modes metric-global --phrasings named` | 共享口径组，只报指标名，1M 行 | 15/15；含学习成本输入 token 0.41M vs 直连 3.30M；v2 撤销后同一请求内修复为 r1 |

- 两次指标实验的数据完全由确定性公式生成，同样行数下数据与标准答案相同，可跨目录比较。
- 消融的逐轮数据（`round-*.json`，共 56 MB）与 31 MB 的 `report.json` 在 noctis 的 `/root/agentdb-mid/results/ablation-1790658664143008/`。
- 分析见 `docs/notes/2026-09-29-experiments.md`。
