# 已完成的旧 SQL-only 单元：描述性核对

这不是本次同批配对实验的结果。10-22 的 SQL-only／rel-stack 已完成 3 个任务各 5 个截点；对应的新批次 MAVRA 未完成。作为诊断，将它与论文已采用的历史 MAVRA／rel-stack 单独列在一起：前者经 happycoding，后者经 DeepSeek 官方 API；运行日期、代码版本及调用条件并非完全一致。每条都是一条连续序列，各组也使用自己的上一期方案设置目标。两者不构成严格配对，不能作为结构化定义增量收益的结论。

| 指标 | 旧 SQL-only | 历史 MAVRA |
| --- | ---: | ---: |
| 五个截点 token，含学习 | 1,951,358 | 1,985,300 |
| 截点 2–5 token，含学习 | 881,889 | 1,328,185 |
| post-votes 五截点平均 MAE（越低越好） | 0.064422 | 0.064832 |
| user-badge 五截点平均 AUC（越高越好） | 0.860431 | 0.857473 |
| user-engagement 五截点平均 AUC（越高越好） | 0.885703 | 0.883356 |

旧 SQL-only 在 12 个复用会话中，有 11 个首次验证使用上一期完整 SQL，也有 11 个首次验证达到该组目标。其后四个截点的 token 比上述历史 MAVRA 少 33.6%；这提示完整 SQL 复用可能解释大量节省，也提示本次新实验可能得出不利于 MAVRA 的结果，但跨批次差异及单序列波动无法排除。

核对方式：已将旧 SQL-only 原始单元复制到本机 `results/sql-only-20261022/sql-only-rel-stack-r1/`，并用 [audit-legacy.py](audit-legacy.py) 对照 [10-22 状态记录](../2026-10-22-sql-only/status.json) 中的 16 个 SHA-256，全部一致。历史 MAVRA 的逐会话 token 与测试值来自 [paper-sessions.json](../2026-10-20-relbench/paper-sessions.json)。在仓库根目录使用 `python -X utf8 exp/2026-10-27-sql-only/audit-legacy.py` 可重新计算。`results/` 不受版本管理，若本机没有该单元，需从实验索引记录的远端位置取回原始文件。
