# MAVRA：ICDE 稿件

`main-en.tex` 是英文投稿入口（IEEEtran conference，pdfLaTeX）；`main.tex` 是共用源码的中英对照阅读稿（XeLaTeX）。双语稿不用于投稿。

根据 [ICDE 2027 Research CFP](https://icde2027.github.io/cf-research-papers)，正文最多 12 页，参考文献和 AI 生成内容声明不计入，不能附加附录。作者姓名与单位仍为占位符，投稿前需填写。最终以投稿编译环境生成的 PDF 为准。

## 编译与上传

生成文件统一放在 `overleaf/build/`。在仓库根目录可执行 `bash overleaf/build.sh all` 或 `bash overleaf/build.sh pack`；旧 SIGMOD 上传包不再维护。

在本目录执行：

```bash
bash build.sh en    # build/main-en.pdf
bash build.sh bi    # build/main.pdf
bash build.sh all   # 两份均编译
bash build.sh pack  # build/mavra-icde-bilingual.zip
```

构建优先使用 latexmk，亦支持 Tectonic。TeX 环境须提供 IEEEtran 类与参考文献样式及标准宏包；双语稿还需 ctex 和 Noto Serif CJK SC、Noto Sans CJK SC、Noto Sans Mono CJK SC 字体。`build.sh` 预检直接宏包依赖，字体由 XeLaTeX 检查。

上传 `build/mavra-icde-bilingual.zip` 至 Overleaf 后，英文选择 `main-en.tex` / pdfLaTeX，双语选择 `main.tex` / XeLaTeX。包内按输入与图形依赖收集源码，并包含 `references.bib`；不需要实验服务器或原始数据即可编译。

`references.tex` 调用 `IEEEtran.bst` 与 BibTeX：只输出正文引用的条目，按首次引用排序。正文中的多篇引用统一在一组方括号内逐一列出，逗号后留空格，例如 `[7, 8, 9, 10]`，不压缩为编号区间。英文稿与中英对照稿共用这一设置。`references.bib` 保留原稿全部元数据；未引用条目不占参考文献版面。此次转换未对每条文献重新做出版信息核验。

## 2026-10-31 受检执行与跨智能体多题型 Fig.6（当前）

当前来源为 `exp/2026-10-31-diverse-scenarios/`。保留两库、每库三指标及全部十一类变化；不同计分问题从 6 道增至 12 道，题型从单期扩展到四种，共 208 次计分、48 次学习（256 个正式任务）。六个未变更基线格复用此前有效冻结运行，MAVRA 原题库两格及全部方法的新增题均重新测量。缓存恢复的 72 个源任务不重复计分。

新增三种 M3 题型为期间差值、最高月份、最大月度增幅，新智能体 B 对所有方法都获得相同显式业务定义，反馈仅含自身已答结果。题目数量按预先固定的费用门槛决定；原留出、单位／备份等全部失败均保留，13 个情形等权。Fig.6 展示正常更新、覆盖变化、跨智能体迁移与全部情形，仍为 84.6 × 55 mm 单栏、32 根柱。

两种模式及全部 13 情形等权汇总，MAVRA 84.6%、AWM 81.4%、ACE 73.1%、G-Memory 61.5%；全部题次直接计数为 43/52、41/52、38/52、32/52。联合汇总在实验后增加为描述性统计，原有数据及分库结果均保留，不构成统计显著性结论。合成数据总体 MAVRA 92.3%，最强基线 ACE 76.9%；TPC-H 总体 MAVRA 76.9%，仍低于 AWM 88.5%。六道新增题 MAVRA、AWM、G-Memory 均全对；MAVRA 使用 19 次 API 调用和 76,643 token，AWM 为基线最少的 30 次和 114,985 token，分别减少 36.7% 和 33.3%（含在线记忆更新，各方法均不含原有源学习）。只据此报告完整方法的复用成本，不当作结构化表示的单独消融。

表属过滤编译与直接指标执行已修复；TPC-H 追加误去重、日期键及单位错误如实保留。最初扩展批次因完整轨迹采集丢失而全部归为开发结果，六个基线格与两个中断原生格都不进入分数，费用仍全部保留。新增原始归档 684 文件、旧对照归档 492 文件均已逐一核验。

累计全部 7,090 次官方 API 请求实际扣费 19.72 元，保守计价上界 19.74518594 元，低于累计授权 20 元；新增调用已关闭。正式比较每方法一轮、复用冻结对照，不画置信区间、不声称统计显著。英文正文 12 页（总 15 页），双语稿 23 页；未更改模板字体或页边距。最新本地 PDF 与源码包为 `build/main-en.pdf`、`build/main.pdf`、`build/mavra-icde-bilingual.zip`，论文远端未自动同步。

## 2026-10-31 SQL 审查与语义保留修复后的 Fig.6（历史及当前基线来源）

该阶段 Fig.6 使用 `exp/2026-10-31-corrected-scenarios/`：保留两库、三指标、十一变化；共用 SQL 审查按实际查询输入验证唯一性，失效口径保留业务含义但不授予执行权限。ACE／AWM 发布组件的 SQL 适配、官方 G-Memory 与完整 MAVRA 均获得同一格式的自身近三题结果和二值反馈，各自保留正常更新机制。

完成一轮完整配对，共 232 个正式任务（48 次学习、184 次计分）；图中不画误差棒。合成全部情形 MAVRA 86.1%，高于最强基线 ACE 的 77.8%；覆盖变化 80.0%，与 AWM 并列。TPC-H 覆盖变化为 80.0%，与 G-Memory 并列，总体为 79.2%，低于 AWM 的 87.5%。重复装载与备份来源得到改善，日期键、单位及新键克隆增长的误去重仍有失败，正文保留这些限制。

累计 5,144 次 API 请求包含前批全部调用、调试与失败尝试；最终账户扣费 14.30 元，用量上界 14.3077 元，低于累计授权 20 元，新增调用已关闭。费用／时间门槛没有允许第二轮；未经完成或被旧实现取代的格不进入新图。492 个证据文件已下载并逐一校验。

图仍为单栏 84.6 × 55 mm、32 根柱。英文正文 12 页（含声明和参考文献共 15 页），中英对照稿 23 页，没有更改模板字体或页边距。当前上传包为 `build/mavra-icde-bilingual.zip`。下方记录保留各旧版本当时的来源和数值。

## 2026-10-31 修复前已发表基线比较（历史）

修复前 Fig.6 使用 `exp/2026-10-30-published-scenarios/` 的完整配对结果：ACE／AWM 使用发布组件的 SQL 适配，G-Memory 调用官方核心，MAVRA 使用完整配置。两种模式各固定三指标，评测单期问题及十一类独立变化。Agent A 学习后复用，各变化恢复同一份留出后记忆；已发表记忆方法只接收自身轨迹与二值正确性反馈。图形仍为单栏 84.6 × 55 mm、32 根柱。

两轮完整配对比较已结束，共 464 个正式任务（96 次学习、368 次计分问答），图中为两轮均值及实际范围，不作为置信区间。MAVRA 在两库的留出及正常更新问题上均正确；覆盖变化上，合成数据为 60.0%，低于 ACE 的 66.7%，TPC-H 为 75.0%，高于最强基线 G-Memory 的 65.0%。正文保留这些差异并精简逐项数字复述。

全部 3,378 次 API 调用（包括两次失败学习尝试及内部记忆／提炼／优化调用）账户实际扣费 8.65 元，用量估算 8.70 元，保守上界 17.39 元，均低于用户授权的 20 元，已关闭新增调用。原始记录已归档并逐文件核对，详见该批次 README。最终英文正文为 12 页（含声明与参考文献共 15 页），中英对照稿 23 页，未改模板字体或页边距；当前上传包为 `build/mavra-icde-bilingual.zip`。下方旧日期记录保留当时版本和来源，不能据此重建当前 Fig.6。

## 2026-10-30 实验设置补全

V-A 新增并前置 Experimental Setup，集中说明数据集与任务、基线及其比较目的、机制对照、实现环境与预算、指标计量与重复运行。英文稿和中英对照稿同步更新，保留纵向五截点与官方 API 三截点两个批次各自的协议。

- 分别说明 No memory、ACE、AWM、G-Memory、DeepPrep 和 FeatPilot 为什么适合作为对照，以及各方法保留的机制与必要适配。FeatPilot 明确标为 SQL 适配版本，Table IV 加星号对应说明；表内实验数值未改动。
- 群体实验、验证共享和快照实验说明各对照固定与改变的因素，区分记忆可见性、示例检索、检查结果缓存及快照保留。
- 根据实际实验服务器核实环境：Ubuntu 22.04.5 LTS、48 个 vCPU、Hygon C86 5390、约 98 GiB 内存、PostgreSQL 18.6。论文中的硬件描述使用虚拟机暴露的 vCPU 数，不将其解释为物理核心数。
- 明确 token 包含记忆内部调用及会话后构建，在线延迟列与后台学习耗时分开；同时补充失败回退、质量容差、调用预算和重复运行口径。补入 TPC-DS、TPC-H 及 SSB 原始资料引用。
- 本轮只补充协议与说明，没有运行新实验。英文稿 19 页，中英对照稿 29 页；已检查新增正文、Table IV/V、引用及交叉引用，暂未压缩篇幅。默认上传包为 `build/mavra-icde-bilingual.zip`。

## 2026-10-30 紧凑柱图与篇幅压缩

Fig.6（`two-schemas`）恢复单栏分组柱图，84.6 × 55 mm。合成零售比较无记忆、示例检索、检索加自行核验、整定义重查与 MAVRA；TPC-H 比较实际运行的三种方法。四组汇总合计 32 根柱，继续覆盖留出、正常更新、覆盖变化及全部十二种情形，误差棒为五／三轮运行范围。输入仍为 10-10 合成场景与 10-11 TPC-H 归档，没有新增运行。

实验设置只介绍一次任务、方法与计量口径；结果段落删除逐项复述。策略表的必要定义并入设置，固定库回放与快照对照以正文报告，原图表源码及实验记录保留。共享验证图保留耗时两子图，查询次数在正文说明。系统概览、相关工作和结论进一步精简重复说明；正式定义、算法、证明及 Fig.3/4 保持本轮修改前内容。

本地英文稿为 15 页：正文第 1–12 页，AI 声明与参考文献第 13–15 页；中英文对照阅读稿 23 页。按 2026-10-30 核对的 [ICDE 2027 Research CFP](https://icde2027.github.io/cf-research-papers) 计算正文页数。字体、页边距和 IEEE 模板尺寸保持不变。AI 声明移至 `sections/ai-statement.tex`，在正文分页之后、参考文献之前输出。中英文均已编译并检查图表、交叉引用与相关页面。

当前源码包为 `build/mavra-icde-bilingual.zip`；图形重建入口为 `tools/figures/two_schemas.py` 和 `tools/figures/mechanism.py`。

## 2026-10-30 系统概览与设计重写

III 按 Fig.2 的组件、1--9 步流程及共享示例展开，说明定义修订、表版本、条件结果与执行快照。IV 按共享表示、学习与发布、条件与有效性、查找与维护、快照执行、共享优化及实体级特征复用组织，中英文同步更新。

- 新增 Algorithm 1（带共享维护的查找）和 Algorithm 2（快照绑定的指标执行），源码在 `algorithms/`；正文解释其输入、输出、共享检查、恢复与拒绝分支。
- Fig.2 的种子时间上界改为 `t <= t_i`，与 `src/metric.rs` 的编译边界一致；架构布局与其他元素保持一致。Table III 的快照脚注改为引用新的快照执行小节。
- 本轮按内容完整性扩写，未压缩篇幅。英文稿 17 页，中英对照稿 26 页；已检查两节、算法、公式与 Fig.2 的显示，以及引用和交叉引用。

## 2026-10-30 引言与动机图更新

- 使用新版中英文引言；Fig.1 以 Agent 1、Agent 2、省略号和 Agent N 表现多智能体，不同探索轨迹汇向同一数据库，突出重复探查负载。
- 独立公式采用连续自动编号，中英文共用同一公式；Table I/II 使用简短表题，必要统计口径归入正文。
- 当前英文稿与中英对照稿均已编译，分别为 15 页和 22 页。已检查引言、Fig.1、公式与 Table I/II 的排版。
- 当前上传包为 `build/mavra-icde-bilingual.zip`，按实际依赖收集 70 个源码与图形文件；独立论文仓库同步记录见 `docs/development/paper-sync.json`（主仓库）。

## 2026-10-29 中英文润色与源码同步

按 CCFA 写作清单同步润色 10 个正文源文件，明确配对执行时间差、查询快照、检查结果及连续两次验证未改进的停止规则，并拆分背景、发布检查、优化与回退结果中的密集段落。实验数字、结果宏、公式、引用与原有结论保持不变。润色清单见主仓库的 `ccfa-review-reports/mavra-writing-review.md`。

源码以本目录为准，独立论文仓库接收当前正文及实际依赖的图表、数值宏和编译文件；远端已有历史证据保留。默认上传包为 `build/mavra-icde-bilingual.zip`。论文仓库同步状态见主仓库 `docs/development/paper-sync.json`；Overleaf 仍需通过 GitHub 集成拉取。

以下 15／22 页记录对应机制图合入时的 PDF，不能用来代替本轮润色后的分页检查。

## 2026-10-29 机制图合入与段落重构

经用户确认，图 A/B/C 已纳入共用正文，当前编号为 Fig.5/6/7；原两种模式正确率图顺延为 Fig.8。实验部分按历史与官方 API 比较、程序/定义访问预实验、受控指标研究、验证共享、数据变化、快照绑定组织。相关工作和结论据这些证据同步调整。原 Fig.3/4 的图形文件和图注保持不变。

- Fig.5：八格、每格一次的开发预实验。分别呈现验证 AUC 与含源成本的 token，保留两格无有效 SQL 和全部成本。未将其写成组合器收益、表示优势或测试集非劣性证据；接口中断及补跑范围写入正文。
- Fig.6：固定 16 个定义的三轮共享对照，72 格、9,216 次有效请求。保留 SQL/版本缓存强对照、全量重查的在途合并及异常格；误差棒是最小值到最大值，活跃表集合变化的限制明示。
- Fig.7：30 次同版本源、同守卫的快照生命周期对照；归档读延迟和写吞吐另列子图，不把三批数据解释为同一安全性/吞吐曲线。

新增图为嵌入字体的矢量 PDF，采用现有衬线字体、固定方法配色、空心点/线型及柱纹理。主文页脚说明移入图注，保持 Fig.4 等图的传统数据库论文风格。双语图与中英文正文同步。

从仓库根目录执行 `python3 tools/figures/mechanism.py`，同时生成六份中英文 PDF 和 `gen/mechanism.tex`。输入均为已存档的汇总 JSON，无需连接实验服务器或调用模型。来源和验证记录见 [合入记录](../exp/2026-10-29-mechanism-pilot/paper-integration/README.md)。本次只合入已有结果，没有新实验消费。

本地英文编译为 15 页，正文在第 12 页结束，AI 声明和参考文献从第 13 页起；双语阅读稿 22 页。最终投稿仍以所用编译环境输出为准。当前源码包为 `build/mavra-icde-mechanism-20261029.zip`，默认包 `build/mavra-icde-bilingual.zip` 同步更新；两包都包含中英文入口和图形。独立论文仓库与远端 Overleaf 未自动同步。

## 2026-10-22 修订与计时范围

RelBench 的 14 组运行、210 个会话已恢复完成。表 IV 从记录用量按[官方美元价目](https://api-docs.deepseek.com/quick_start/pricing/?push_animated=1&theme=light&webview_progress_bar=1)重新计价：每百万 token 缓存命中 $0.003、未命中 $0.15、输出 $0.60（闲时价，2026-10-22 查询），不是历史账单金额或汇率换算。原始比较工具默认人民币定价不变，论文生成器显式选用美元价。

在仓库根目录重新生成：

```bash
python3 tools/relbench/paper-stats.py --out overleaf/gen --sessions-json exp/2026-10-20-relbench/paper-sessions.json
python3 tools/figures/relbench_cumulative.py
python3 tools/replay-safety-summary.py
```

现有 RelBench 时间列是共享服务器上的观测值，尚未执行无争用计时，不据此声称隔离加速比。SQL 子集重放不能代表完整系统重放，回放时间与估计 API 延迟之和也不能当作实测端到端时间。

## 数值与实验存档

### 2026-10-23 一致性核对

- 当前稿件的群体实验包含三种作用域配置（无记忆、私有记忆、MAVRA）及共享示例检索，各五轮，共 3,520 会话：初始阶段 `4 × 16 × 7 × 5 = 2,240`，更正后 `4 × 16 × 4 × 5 = 1,280`。`exp/2026-10-12-population/population-stats.json` 中每种方法分别为 560 与 320 个有效会话；正文按阶段报告结果。10-29恢复同批配对的示例检索对照：更正后为 190/320（59.375%），MAVRA 为 318/320（99.375%）。基线检索成功题目、答案 SQL 与算式，数据更新后不维护记录；它属于复用对照，不是仅移除维护组件的消融。其他未采用的旧比较组保留在原始归档中，不计入当前分母。
- 九条优化修订来自端到端优化实验；四条前提失效修订来自独立的系统测试，见 `exp/2026-10-08-optimize/README.md` 与 `premise-report.json`，并非九条中只有四条受月份重编号影响。
- 175 条定义来自全部 99 个 TPC-DS 模板的静态分析，其中 82 个模板含定义；每个 SELECT 块内同一事实表的聚合合算一条。来源为 `tools/tpcds-sharing.py` 与 `exp/2026-10-02-cache-baseline-tpcds/tpcds-sharing.json`，不同于群体实验选取的五个指标。
- Table IV 的 rel-stack 后四个截点：无记忆的缓存输入／未缓存输入／输出分别为 3,696,128／149,925／462,532 token，MAVRA 为 884,736／247,429／196,020（包含学习开销，沿用计价脚本将未记录缓存命中的学习输入按未缓存计价）。token 下降 69.17%；原始重计价金额从 0.311096334 降至 0.157380558 美元，下降 49.41%。表内金额保留两位小数，按 0.31 与 0.16 计算才得到约 48%；正文解释缓存与输入／输出构成，不将舍入后的比值当作原始测量值。
- Table VII 的 unit/backup 组共 267 题次：89 正确、115 错误、63 拒绝；43% 的分母包含拒绝，只计返回答案时为 `115 / 204 ≈ 56%`。正文与未来工作明确量纲及权威来源约束的边界。
- Lemma 1 的覆盖范围依据 `src/catalog.rs`、`src/middle/metrics.rs` 与 PostgreSQL 18 的 [COPY](https://www.postgresql.org/docs/18/sql-copy.html)、[CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html)、[TRUNCATE](https://www.postgresql.org/docs/18/sql-truncate.html) 文档核对。版本递增随事务回滚；ABA 防护要求缓存存续期间不重置或复用计数。非普通 MVCC 操作要求读事务静默，绕过触发器及重置类操作要求清除检查缓存；这些是保证成立的部署前提，不表示原型已自动拦截所有管理操作。代码没有以时间戳为基础的完备兜底机制，模式指纹与 ETL 批次标记不能证明未观测写入的安全性。

[实验索引](../exp/README.md) 列出实验批次。各批次的失败、替换和排除规则以原协议为准。正常编辑与编译直接使用已提交的宏和 PDF，无需运行实验。

| 生成文件 | 当前来源与生成入口 |
| --- | --- |
| `gen/relbench.tex`、`gen/relbench-table.tex` | `tools/relbench/paper-stats.py`；采用 `results/relbench-pilot3/` 与 `results/relbench-main/` 中的最终运行 |
| `gen/population.tex` | `tools/population-stats.py`；TPC-DS 群体实验的采用组见 `exp/2026-10-12-population/README.md`，早期外部记忆基线排除范围见 RelBench 协议 |
| `gen/published-scenarios.tex` | `exp/2026-10-31-diverse-scenarios/analyse-paired-reuse.py`；六个冻结基线对照、两格原生重跑及八格共同新增题，208 次计分，13 情形等权；每方法一轮不画误差棒 |
| `gen/numbers.tex`、`gen/scen-cost.tex`、`gen/scen-ds.tex` | `tools/paper-results.py`、`tools/scen-stats.py`；当前五轮场景汇总在 `exp/2026-10-10-scenarios-q5/` |
| `gen/numbers-prev.tex` | 早期三模型批次，`PrevScen` 前缀；存档在 `exp/2026-10-01-scenarios/` |
| `gen/review.tex`、`gen/snapshot-stress.tex` | `tools/review-results.py`；`exp/2026-10-02-cache-baseline-tpcds/` |
| `gen/generality.tex`、`gen/replay-safety.tex` | `tools/generality-stats.py`、`tools/replay-safety-summary.py`；通用性回放与共同题次审计 |
| `gen/opt.tex`、`gen/premise.tex`、`gen/sharing.tex` | `tools/opt-stats.py`、`tools/premise-stats.py`、`tools/sharing-stats.py`；优化、前提失效与使用成本，具体输入范围见各脚本和实验清单 |
| `gen/external.tex` | `tools/external-reuse-stats.py`；`exp/2026-10-14-external-motivation/` |
| `gen/mechanism.tex` | `tools/figures/mechanism.py`；10-29 开发预实验及共享/快照对照，采用范围见上文 |
| `gen/session-latency.tex`、`gen/lifecycle*.tex` | 补充实验宏，分别由会话耗时和生命周期统计工具生成 |
| `figures/*.pdf` | 脚本、数据和单图入口见 [绘图说明](../tools/figures/README.md)；架构图由 `tools/figures/build.py architecture` 生成，RelBench 图由 `tools/figures/relbench_cumulative.py` 生成 |

重算时先确认输入目录与采用范围，建议先写临时输出目录并比较差异，再更新 `gen/`。旧三轮场景命令不能直接替换当前五轮图表的输入。

## 2026-10-28 官方 API 实验与 10-29 归因复核

官方 API 比较已完成：无记忆、ACE、AWM、G-Memory、MAVRA，两库、三任务、三截点，共90个正式会话。按用户最新要求，删除新增的六任务质量图；Fig.3 恢复 01daa213 的 `relbench-cumulative` 原图、图注与历史五截点数据。昨晚官方API实验仅用于原 Fig.5 的 `reuse-work` 工作量图；删除前一图后，它自动编号为 Fig.4。官方实验的设置、质量边界与来源审计集中在该图对应小节，完整数据仍在工件中。Table III、含旧数据的 Table IV、引言、摘要、结论及 Fig.1 位置均保持本轮修改前状态。历史网关结果与官方API结果分别陈述。

10-29逐会话复核发现：12个MAVRA复用会话中9个首先验证完整旧SQL，6个原样保留旧SQL。查找工具内部也会编译定义，显式组合调用为零不能等同于无编译；但本轮没有分离结构化定义的增量作用。首截点一次直接验证的编译SQL被目标任务审计拒绝。正文、图注、系统概览和实证限制已据此同步，核心表示消融仍待补充。详见主仓库 `exp/2026-10-29-fig5-review/` 的审计与来源记录。

本次发布保留可用结果及其限制，不新增模型调用。工作量图不作为结构化组合有效的独立证明；该阶段尚未执行的组件预实验已在上方 10-29 机制图合入记录中单列更新。英文与双语入口共用修订正文。

项目说明见 [主仓库 README](../README.md)。当前 `references.bib` 是稿件实际编译的来源。

## 独立论文仓库

`overleaf/` 仍是主仓库的普通目录，主仓库远程地址保持不变。独立论文仓库为 [icde-2027-paper](https://github.com/mmmttt000045/icde-2027-paper)，论文源文件放在该仓库根目录，可用 Overleaf 的 GitHub 导入功能创建项目。本目录的修改不会自动同步过去；将当前源码同步到独立论文仓库后，还需在 Overleaf 的 Integrations → GitHub 中手动拉取。Overleaf 中的修改也需先推送回 GitHub，再合入本目录。

工作量图沿用 `exp/2026-10-29-fig45-official/build-figures.py` 已生成的原 Fig.5 PDF，数据和版式本轮不变。此前生成的质量图与官方累计图从正文移除，文件作为历史版本留档，不再参与当前编译。恢复记录与源文件保护哈希见 `exp/2026-10-29-fig3-restore/`。
