# 研究状态与证据 / Research status and evidence

更新日期 / Updated: **2026-09-30**（Asia/Shanghai）。

系统仓库 / System repository: `agent4db-adapter@743041f`。
论文仓库原始版本 / Original paper commit: `f33e2b8`。

## 模板与语言 / Format and language

已采用 `\\documentclass[sigconf,review,anonymous]{acmart}`。按照 SIGMOD 2027 Research 的官方要求使用双栏匿名审稿格式，保留模板的默认字体尺寸、页边距、栏距和行距。双语 `main.tex` 使用 XeLaTeX；英文 `main-en.tex` 从相同源稿导出，可使用 pdfLaTeX。双语稿是共同写作版本，不能因已使用模板就视为达到投稿页数要求。

The manuscript uses the SIGMOD 2027 research submission layout with anonymous review. The bilingual working document and English export share text, figures, and results. Template selection does not establish PDF compilation, rendering quality, or compliance with the 12-page main-paper limit.

## 本轮证据 / Current evidence

| 实验 / Experiment | 范围 / Scope | 证据 / Evidence |
| --- | --- | --- |
| 维护正序 / Forward maintenance | 40 组，19 个定义上限，8 个脚本 Agent / 40 cells, up to 19 definitions, 8 scripted agents | `evidence/maint-forward-cells.txt` |
| 维护反序 / Reverse maintenance | 相同 40 组，反转策略顺序 / same 40 cells, reversed policy order | `evidence/maint-reverse-cells.txt` |
| 端到端 / End-to-end | 6 组，每组 6 道学习题及 21 道计分题 / 6 cells, 6 learning and 21 scored tasks each | `evidence/metric-maint-report.md`、`evidence/metric-summary.txt` |
| 原始分析 / Analysis | 2026-09-29 至 09-30 的实验说明 / September 29–30 report | `evidence/metric-maintenance-report-2026-09-30.md` |
| 数值复核 / Recomputed values | 逐任务 JSON 与维护每组合计 / raw task JSON and cell totals | `evidence/verified-results.json` |

原始逐任务记录在父仓库 `exp/2026-09-30-metric-maint-named/cell-*.json`；论文包保留轻量报告和重新汇总值，不依赖这些文件来编译。原报告指出实验在 `5e82e37` 基础上增加了计算链和列名前缀修复；这些修复随后随 `743041f` 归档。维护报告的计数修正亦已归档。普通中间层来自较早一轮且不进行提炼；不能称所有实验来自完全相同的二进制。

Raw task records remain in the system repository. The experiment report identifies the baseline code and fixes applied before final sharing runs, now archived by 743041f. The ordinary middleware cell comes from an earlier run and performs no extraction; future repeats should align code and prompts. Discarded extraction-bug runs are excluded.

## 已支撑的结果 / Supported results

- 条件级、定义级、撤销重学均为 **21/21**；无共享中间层 **11/21**，只看结构 **18/21**，无守护 **12/21**。The scored-task denominator excludes initial learning and additional relearning.
- 端到端条件级维护数据库时间 **22.362609 s**，定义级 **52.960153 s**，描述性下降 **57.775%**。These values are event-accounted maintenance DB time, not whole-workload time.
- 维护扫描错峰时条件级耗时比均值 **12.5%–37.8%**，同时到达 **44.6%–75.5%**。Means average the two per-order ratios; they are not ratios of averaged times.
- 条件级和定义级在已建模更新中均未出现过期使用或误撤销。Both revalidation methods have the same observed correctness.
- 同时到达、k=6，条件级修复窗口不可用 **43/304**，定义级 **24/304**。Lower DB work does not establish better availability.
- 只看结构在模型实验 v2 后执行 **6 次过期引用**，M2 的 **3 题答错**；单期例子为 **6,588,699.86** 对 **3,294,349.93**。Stale references and wrong answers are separate measures.

统一舍入后论文表中 52.960153 秒写作 52.96 秒，而非旧报告的 52.9 秒；错峰 k=2 的范围组均值从原始每组合计重算为 76.1%，原分析表写作 76.2%。原样证据副本未覆盖，复核文件记录差异。

The manuscript corrects two rounding discrepancies without altering archived reports: 52.960153 seconds is displayed as 52.96, and the staggered k=2 scope-only mean recomputes to 76.1% from cell totals.

## 实现边界 / Implementation boundaries

| 机制 / Mechanism | 状态 / Status |
| --- | --- |
| 成功轨迹提炼、G1–G7 准入 / extraction and admission | 已实现；30 次初始提炼中 4 次别名表达式未通过 G3 / implemented, 4 of 30 initial extractions rejected for aliases |
| 条件级维护及结论复用 / condition maintenance and reuse | 已有专项结果 / evaluated in controlled benchmark |
| 相同条件的在途合并 / in-flight merging | 各重验证方法相同 / shared by revalidation baselines |
| 修订引用检查 / revision checks | 已实现，仅覆盖显式声明 / implemented for declared uses |
| 受限修复及 G8 回归 / restricted repair and regression | 已实现；学习集参考查询同源 / implemented with workload-derived evidence |
| 同快照验证与执行 / same-snapshot validation and execution | **未实现**；正文明确标为设计协议 / not implemented; described as proposed protocol |
| 完整独立覆盖条件 / complete coverage maintenance | **未完成** / incomplete |
| 修复进行中的请求等待 / wait for in-progress repair | **未完成**，不可用数如上 / incomplete; availability gap measured |
| AgentSM 式轨迹检索基线 / matched trajectory retrieval | **未实现**，不填写相对它的正确率优势 / not implemented; no claimed gain over it |

## 评估边界 / Evaluation limits

单模型、合成数据、端到端每组仅一轮。维护正反序是顺序控制，不是统计显著性检验。8 个并发 Agent 是脚本 Agent；模型问答按顺序执行。k=1 仍有跨族共享，不能代表无共享负载。四次更新是三次正常追加及一次 v2 破坏，不是四类独立故障。数据库关闭 WAL 和 fsync；结果不能直接代表持久化生产部署的绝对耗时。

The reference SQL and task generator share origins, not an external business gold standard. Undeclared uses and SQL that does not implement its declared formula are outside the revision guarantee. Initial learning, extraction, unsuccessful runs, and restoration must remain separate from scored-task costs and be included in future whole-workload analyses.

下一步是并发修复等待、同快照执行、更多变化类型、第二模型、至少三次重复、更接近真实的 schema，以及匹配的轨迹检索基线；这些尚未完成，不作为本稿实测结论。

## 编译验证 / Compilation verification

内置编译器对双语稿和英文稿均返回 `Unable to find standard directories for platform`，未进入 TeX 处理。当前没有终端 TeX 编译器。不报告编译成功或 PDF 页数；编辑器保留打开。已核对 LaTeX 括号、环境、标签、引用、语言导出一致性、80 组汇总及 6 组逐任务数值。

Both native compilation attempts fail during environment initialization. PDF rendering and page count remain unverified. Structural and numerical checks passed; these are not a substitute for a successful TeX compilation.
