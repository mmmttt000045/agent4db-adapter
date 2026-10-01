# 研究状态与证据 / Research status and evidence

更新日期 / Updated: **2026-10-01**（写入工作负载刻画与三模型数据变化场景；论文数值由 `tools/paper-results.py` 生成）。

系统仓库 / System repository: `agent4db-adapter`，场景实验代码 `26c2b48` 起，统计脚本见 `tools/`。
论文仓库原始版本 / Original paper commit: `f33e2b8`。

## 模板与语言 / Format and language

已采用 `\\documentclass[sigconf,review,anonymous]{acmart}`。按照 SIGMOD 2027 Research 的官方要求使用双栏匿名审稿格式，保留模板的默认字体尺寸、页边距、栏距和行距。双语 `main.tex` 使用 XeLaTeX；英文 `main-en.tex` 从相同源稿导出，可使用 pdfLaTeX。双语稿是共同写作版本，不能因已使用模板就视为达到投稿页数要求。

The manuscript uses the SIGMOD 2027 research submission layout with anonymous review. The bilingual working document and English export share text, figures, and results. Template selection does not establish PDF compilation, rendering quality, or compliance with the 12-page main-paper limit.

## 本轮证据 / Current evidence

| 实验 / Experiment | 范围 / Scope | 证据 / Evidence |
| --- | --- | --- |
| 维护正序 / Forward maintenance | 40 组，19 个定义上限，8 个脚本 Agent / 40 cells, up to 19 definitions, 8 scripted agents | `evidence/maint-forward-cells.txt` |
| 维护反序 / Reverse maintenance | 相同 40 组，反转策略顺序 / same 40 cells, reversed policy order | `evidence/maint-reverse-cells.txt` |
| 工作负载：应用侧 / Workload, application | Amazon Redset 全部 400 个集群、4.41 亿条查询 / all 400 Redset clusters, 441M queries | `evidence/redset-stats.json`；脚本与说明在 `exp/2026-10-01-workload-characterization/redset/` |
| 工作负载：智能体侧 / Workload, agents | 100 个 DeepSeek V4.1 Flash 全新会话，521 次调用 / 100 fresh sessions, 521 calls | `evidence/workload-agent-stats.json`；原始轨迹在 `exp/2026-10-01-workload-characterization/` |
| 数据变化场景 / Data-change scenarios | 3 个模型 × 6 种方法 × 10 种变化，分析 43 组、3,701 道计分题 / 3 LLMs × 6 methods × 10 changes; 43 cells, 3,701 scored tasks | `evidence/scenario-results.json`；原始逐组 JSON 在 noctis `results/scen-20260930/` |
| 早期单模型端到端 / Earlier single-model run | 6 组，21 道计分题；论文只引用其准入拒绝与引言中的单期例子 / cited only for admission rejections and the introduction example | `evidence/metric-maint-report.md`、`evidence/metric-summary.txt`、`evidence/verified-results.json` |

论文中第 2.1 节表格的数值直接写在正文里（来自上面两份工作负载证据）；第 7 节的场景表格、两张图和正文数值宏由 `tools/paper-results.py` 从原始输出生成到 `gen/`，场景补跑完成后重跑脚本即可更新：

```bash
# noctis，仓库根目录
python3 tools/paper-results.py --scen results/scen-20260930 --out overleaf/gen --json exp/2026-10-01-scenarios/paper-results.json
```

Section 2.1 values are written in the text from the two workload reports. Section 7's scenario table, both figures, and the in-text number macros are generated into `gen/` from raw outputs; rerun the script after the remaining scenario repetitions.

## 已支撑的结果 / Supported results

- 工作负载：智能体 SQL 只有 24% 复用已出现模板（Redset 读查询 93.4%，SELECT 90.1%）；68% 的调用用于探索；93% 的查找重复此前会话获得的事实；91% 的查找在 60 秒内被其他会话重复（Redset 不同用户同模板 0.61%）；SQL 出错 1.7%，32 个错误答案全部没有任何失败调用。Agent workloads repeat knowledge, not templates.
- 维护扫描错峰时条件级耗时比均值 **12.5%–37.8%**，同时到达 **44.6%–75.5%**；条件级和定义级零过期使用、零误撤销。Means average the two per-order ratios.
- 同时到达、k=6，条件级修复窗口不可用 **43/304**，定义级 **24/304**。Lower DB work does not establish better availability.
- 场景（11 种情形等权、模型宏平均）：不共享 **32%**，无守护 70%，只看结构 62%，撤销重学 63%，定义级 **77%**，条件级 **74%**；留出题 50% → 96%。
- 5 种已建模破坏性变化下，条件级、定义级与撤销重学零过期使用；只看结构 **195** 道、无守护 **201** 道题使用过期定义。状态流水与版本化更正修复成功（条件级 78%、91%）。
- 边界：重复装载与日期键改写被检测并撤销但无法修复（33%、17%，接近不共享）；单位变化未建模，条件级 54 道题中 48 道使用过期定义。
- 场景维护数据库时间：条件级每组 **180 s**，定义级 **367 s**（49%）；撤销重学每组撤销约 24 个修订、重学约 0.55 M token。
- 分模型：DeepSeek 与 GLM-5.3 条件级 82%／82%，定义级 81%／83%；GLM-5.3 Flash 条件级 54%、定义级 65%，区间宽、完整情形少（8 种）。

统计口径（排除用量上限失败的 136 道题、剔除学习阶段被中断的 2 组、场景等权、按题自助法区间）写在 `tools/paper-results.py` 文件头。早期单模型运行的舍入修正（52.96 秒、76.1%）仍记录在 `evidence/verified-results.json`。

## 实现边界 / Implementation boundaries

| 机制 / Mechanism | 状态 / Status |
| --- | --- |
| 成功轨迹提炼、G1–G7 准入 / extraction and admission | 已实现；早期运行 30 次初始提炼中 4 次别名表达式未通过 G3 / implemented |
| 条件级维护及结论复用 / condition maintenance and reuse | 受控实验与三模型场景均有结果 / evaluated in both benchmarks |
| 相同条件的在途合并 / in-flight merging | 各重验证方法相同 / shared by revalidation baselines |
| 修订引用检查与 SQL 审查 / revision checks and SQL review | 已实现，仅覆盖显式声明；维表拉链中 SQL 审查挡住了过期定义的放大连接 / implemented for declared uses |
| 受限修复及 G8 回归 / restricted repair and regression | 已实现；只能加过滤，无法去重或重映射键；2026-10-02 起候选过滤不唯一时不自动修复（`repair_unique`，默认开），本文已有场景运行时尚无此规则 / filter-only repair; unique-candidate rule added after the reported runs |
| 同快照验证与执行 / same-snapshot validation and execution | 已实现，默认关闭（事务性版本 + 可重复读快照内核对并执行）；并发写入实验见 `exp/2026-10-02-cache-baseline-tpcds`；**正文尚未更新**，仍写作设计协议 / implemented (opt-in), paper text not yet updated |
| 取值层面的条件（如单位）/ value-level conditions | **未建模**；单位变化场景为对照 / not modeled |
| 修复进行中的请求等待 / wait for in-progress repair | 2026-10-02 已实现（`wait_repair`，默认开）；20 万行同时到达复测不可用降为 0；本文已报告的不可用数来自此前的运行 / implemented after the reported runs |
| AgentSM 式轨迹检索基线 / matched trajectory retrieval | 已实现（`traj-global`），**尚未运行**（需要 LLM），不填写相对它的正确率优势 / implemented, not yet run |

## 评估边界 / Evaluation limits

只有一个合成表结构。场景实验计划 3 模型 × 6 方法 × 3 次重复共 54 组，因 ClinePass 5 小时与周用量上限，目前分析 43 组（DeepSeek 与 GLM-5.3 较完整，GLM-5.3 Flash 缺得多）；周上限约 2026-10-07 重置后补跑，再重跑 `tools/paper-results.py`。工作负载刻画只用一个模型；两个 GLM 模型的轨迹因 Cline 余额耗尽未完成。维护正反序是顺序控制，不是统计显著性检验；8 个并发 Agent 是脚本 Agent。数据库关闭 WAL 和 fsync。参考 SQL 与任务生成器同源。

Only one synthetic schema is used. The scenario design has 54 cells; usage caps leave 43 analyzed cells, mostly missing GLM-5.3 Flash repetitions. The workload study uses one model. Reference SQL and the task generator share origins.

## 编译验证 / Compilation verification

2026-10-01 在 noctis（TeX Live 2026）用 `./build.sh all` 编译通过：英文稿 11 页（正文在第 9 页结束，其后为参考文献），双语稿 16 页。英文稿无未定义引用，只有一处 3.8pt 的溢出行已改写消除。

Compiled on noctis with TeX Live 2026: English 11 pages including references (body ends on page 9), bilingual 16 pages.
