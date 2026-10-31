# 当前研究状态与证据

整理日期：2026-10-22。本文依据当前仓库中的实现、实验协议与稿件维护导航；具体数值及统计范围以各实验记录和生成文件为准。

## 当前稿件

当前论文使用 ICDE 模板，英文投稿入口是 [main.tex](../../overleaf/main.tex)，双语阅读入口是 [main-bilingual.tex](../../overleaf/main-bilingual.tex)。构建、投稿包和独立论文仓库的同步方式见 [论文说明](../../overleaf/README.md)。

研究围绕跨智能体共享经过检查的数据库知识，以及数据变化后的维护与使用。当前评估以 RelBench 为主，TPC-DS 群体实验与指标维护实验提供受控证据。实现入口见 [源码导览](../development/source-map.md)。

## 证据入口

| 问题 | 主要依据 | 稿件入口 |
| --- | --- | --- |
| 真实关系基准上共享记忆的使用、token 与工具调用 | [RelBench](../../exp/2026-10-20-relbench/README.md) | `sections/05-evaluation.tex`（RelBench 小节） |
| 智能体陆续到来时，共享与私有记忆的成本 | [群体实验](../../exp/2026-10-12-population/README.md) | `sections/05-evaluation.tex`（群体实验小节） |
| 已有定义对新使用者的帮助 | [场景题集 v2](../../exp/2026-10-10-scenarios-q5/README.md)、[通用性实验](../../exp/2026-10-11-generality/README.md) | `sections/05-evaluation.tex`（共享使用小节） |
| 更新后的维护成本、优化收益 | [验证缓存与 TPC-DS](../../exp/2026-10-02-cache-baseline-tpcds/README.md)、[优化修订](../../exp/2026-10-08-optimize/README.md) | `sections/05-evaluation.tex`（维护与优化小节） |
| 数据变化下的正确服务、错误服务与拒绝 | [通用性回放及审计](../../exp/2026-10-11-generality/replay-safety-summary.json)、[场景题集 v2](../../exp/2026-10-10-scenarios-q5/README.md) | `sections/05-evaluation.tex`（数据变化小节） |
| 不同任务重复需要数据库知识的动机 | [外部基准统计](../../exp/2026-10-14-external-motivation/README.md) | `gen/external.tex` |

表中的稿件路径均相对 `overleaf/`。完整目录、原始数据位置、统计脚本和历史批次见 [实验索引](../../exp/README.md)。

## 解释结果时的范围

- RelBench 的恢复记录见 [recovery-audit.json](../../exp/2026-10-20-relbench/recovery-audit.json)，论文使用的逐会话序列见 [paper-sessions.json](../../exp/2026-10-20-relbench/paper-sessions.json)。当前计时来自共享服务器；[timing-replay-plan.json](../../exp/2026-10-20-relbench/timing-replay-plan.json) 是准备好的重放方案，尚不代表无争用计时已完成。
- TPC-DS 群体实验采用的无记忆、私有记忆与 MAVRA 结果，和早期外部记忆基线尝试分开解释。RelBench 协议开头明确排除了不忠实的早期基线实现及相关运行，不能从旧汇总中重新纳入论文。
- 更新实验覆盖已建模的条件和指定变化；回放审计同时保留错误服务与拒绝的情况。不能把局部检查扩大为任意业务语义正确性的保证。
- 学习、发布、维护、消费者使用和完整任务时间有不同计量范围；已有定义库上的节省不能直接当作包含建库成本的整体收益。

## 实现边界

- 指标定义的准入、条件维护、撤销、受限修复和执行修订核对在 `src/middle/metrics.rs`；特征相关逻辑在 `src/middle/features.rs`，优化修订在 `src/middle/optimize.rs`。
- 同快照验证与执行、表版本与修复等待的具体开关由 `MiddleConfig` 和实验模式决定；比较结果时需要核对运行配置。
- SQL 识别使用轻量文本扫描；单位含义等业务变化不能仅靠结构条件保证。
- 当前 HTTP 接口没有认证、租户隔离或速率限制，经验库在内存中；运行与测试前提见 [开发指南](../development/README.md)。

## 研究记录

[TABLE III 原文核对](table-iii-audit-2026-10-28.md) 逐项说明能力符号、论文页码、官方文档与配置前提。

[中英文润色清单](../../ccfa-review-reports/mavra-writing-review.md) 记录 2026-10-29 的用词、句式与段落调整及核查结果；[论文同步记录](../development/paper-sync.json) 保存独立论文仓库的已核验版本。

[相关工作笔记](related-work.md) 保留检索时的论证；当前引用与基线实现说明分别在论文源码和 RelBench 实验目录。2026-10-07 的状态、10-03 已回退的稿件重构与早期实验协议见 [历史目录](../history/README.md)。
