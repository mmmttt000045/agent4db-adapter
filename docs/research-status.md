# 研究状态与证据 / Research status and evidence

更新日期 / Updated: **2026-10-07**（10-07：准入 G3 改写提炼器照抄的表别名，所有需要准入的方法端到端各重跑 3 次；端到端 MAVRA 改为 G8 在学习时快照上比较（`metric-global-snap`）：全部 81%、已建模破坏 73%，对轨迹检索 +16（11–19），与 G8 用当前数据无可分辨差别（+1），每次运行修复 10.3 对 4.7；定义级 82% / 74%，与 MAVRA 正确率相同。10-06 晚：G8 改在学习时快照上比较（`g8_snapshot`，回放参照 `snapshot`），定义库回放重跑：MAVRA 不需要标准答案即达到标准答案 SQL 的修复结果；端到端未重跑，其中 G8 在当前数据上比较。10-06：论文以部署可得的配置为 MAVRA——G8 以智能体自己的学习 SQL 为对照（`metric-global-exref`、回放参照 `example`）；原判题参照配置改称 MAVRA (gold SQL)；定义库回放在各方法共用的智能体 SQL 参照下重跑；全文术语改为数据库通用词汇（失效、检查结果、同快照验证、先检查后执行、请求合并、连接基数、缓慢变化维等，一个概念一个名字）。下文 10-03 及更早的条目保留当时的方法名与数值。10-03：补充命题 1、引理 1、算法 1；新增 dbt 式表级测试基线、真实 TPC-DS 数据上的配对回放、两种增补方法（智能体参照的 G8、轨迹检索 + 自验证）。10-02：按外部评审改写主线：有效性模型、使用时的强制保证（含绑定快照执行）与有界修复；效率作为实现结论。新增机制层证据：配对回放、并发写入、通用缓存基线、TPC-DS 自然共享、规模扩展。数值由 `tools/paper-results.py` 与 `tools/review-results.py` 生成）。

系统仓库 / System repository: `agent4db-adapter`，场景实验代码 `26c2b48` 起，统计脚本见 `tools/`。
论文仓库原始版本 / Original paper commit: `f33e2b8`。

## 模板与语言 / Format and language

已采用 `\\documentclass[sigconf,review,anonymous]{acmart}`。按照 SIGMOD 2027 Research 的官方要求使用双栏匿名审稿格式，保留模板的默认字体尺寸、页边距、栏距和行距。双语入口 `overleaf/main.tex` 使用 XeLaTeX；英文入口 `overleaf/main-en.tex` 可使用 pdfLaTeX。两者直接读取共享的 `overleaf/paper.tex` 与 `sections/`，不再需要导出。双语稿是共同写作版本，不能因已使用模板就视为达到投稿页数要求。

The manuscript uses the SIGMOD 2027 research submission layout with anonymous review. The bilingual and English entry points share text, figures, and results. Template selection does not establish PDF compilation, rendering quality, or compliance with the 12-page main-paper limit.

## 本轮证据 / Current evidence

| 实验 / Experiment | 范围 / Scope | 证据 / Evidence |
| --- | --- | --- |
| 维护正序 / Forward maintenance | 40 组，19 个定义上限，8 个脚本 Agent / 40 cells, up to 19 definitions, 8 scripted agents | `exp/2026-09-29-maint-share/cells.txt` |
| 维护反序 / Reverse maintenance | 相同 40 组，反转策略顺序 / same 40 cells, reversed policy order | `exp/2026-09-30-maint-share-rev/cells.txt` |
| 工作负载：应用侧 / Workload, application | Amazon Redset 全部 400 个集群、4.41 亿条查询 / all 400 Redset clusters, 441M queries | `exp/2026-10-01-workload-characterization/redset/redset_stats.json`；脚本与说明在 `exp/2026-10-01-workload-characterization/redset/` |
| 工作负载：智能体侧 / Workload, agents | 100 个 DeepSeek V4.1 Flash 全新会话，521 次调用 / 100 fresh sessions, 521 calls | `exp/2026-10-01-workload-characterization/workload-stats.json`；原始轨迹在 `exp/2026-10-01-workload-characterization/` |
| 数据变化场景（此前一轮）/ Earlier data-change scenarios | 3 个模型 × 6 种方法 × 10 种变化，分析 43 组、3,701 道计分题 / 3 LLMs × 6 methods × 10 changes; 43 cells, 3,701 scored tasks | `exp/2026-10-01-scenarios/paper-results.json`；原始逐组 JSON 在 noctis `results/scen-20260930/` |
| 数据变化场景（当前设计）/ Data-change scenarios, current design | DeepSeek V4.1 Flash × 7 种方法（含轨迹检索基线）× 11 种变化（含备份副本）× 3 次独立运行，21 次有效运行（3 次因学习阶段服务失败按预定规则重跑）、2,010 道计分题 / DeepSeek × 7 methods × 11 changes × 3 runs | `exp/2026-10-02-scenarios-ds/`（分析方案、运行记录、`scen-stats.json`、`paper-results.json`）；原始逐组 JSON 在 noctis `results/scen-20261002/` |
| 配对回放 / Paired replay | 15 个学到的定义库（97 个定义）× 5 种方法与 2 种 G8 参照 × 11 种变化，20 万行 / 15 learned libraries × 5 methods, 2 G8 references × 11 changes | `exp/2026-10-02-cache-baseline-tpcds/replay-stats.json`、同目录的 `replay-outcomes.json.gz` |
| 并发写入 / Concurrent writes | 3 种确定性交错 × 2 种模式 × 10 次；4 种随机设置 × 2 种模式 × 20 次；写者代价（1/8/32 写者，16 分片） | `exp/2026-10-02-cache-baseline-tpcds/snapshot-binding-*.json` |
| 维护代价 / Maintenance cost | 1M 行共享度 1/2/4/6 × 4 种方法 × 2 种到达；零共享对照；4M 行 8 与 32 个 Agent；1M–16M 规模 | `exp/2026-10-02-cache-baseline-tpcds/cb-*.json`、同目录的 `e1b-4m-a32-stats.json`、`e1-scaling-stats.json` |
| 自然共享 / Natural sharing | TPC-DS 官方 99 个查询模板 | `exp/2026-10-02-cache-baseline-tpcds/tpcds-sharing.json` |
| 修复边界与可用性 / Repair boundary, availability | 备份副本反例（唯一性规则开关）；同时到达下等待修复开关 | `exp/2026-10-02-cache-baseline-tpcds/repair-ambiguity-unique-report.json`、同目录的 `wait-repair-stats.json` |
| 声明使用 / Declared use | 场景实验条件级与定义级 15 组的 1,289 条答案 | `exp/2026-10-02-cache-baseline-tpcds/declared-use.json` |
| 表级测试基线 / Table-test baseline | 与配对回放同一次重跑：15 个库 × 6 种方法（含 tabletest）× 11 种变化 / same rerun of the paired replay with the dbt-style baseline | `exp/2026-10-02-cache-baseline-tpcds/replay-stats.json`（`tabletest/judge` 组）、`replay-outcomes.json.gz` |
| TPC-DS 配对回放 / Paired replay on TPC-DS SF1 | 模板导出的 93 个定义 × 5 种方法（条件级两种参照）× 11 种变化，290 万行门店销售 / 93 template-derived definitions, real dsdgen data | `exp/2026-10-02-cache-baseline-tpcds/tpcds-replay-stats.json`、`tpcds-replay-outcomes.json.gz`、`tpcds-library.json` |
| 增补方法 / Added end-to-end methods | DeepSeek V4.1 Flash × {MAVRA 智能体参照, 轨迹检索 + 自验证} × 3 次 / two added methods, three runs each | `results/scen-20261002/dsv41flash-r{1,2,3}-{exref,trajv}`（noctis），分析方案增补见 `exp/2026-10-02-scenarios-ds/README.md` |
| 早期单模型端到端 / Earlier single-model run | 6 组，21 道计分题；论文只引用其准入拒绝与引言中的单期例子 / cited only for admission rejections and the introduction example | `exp/2026-09-30-metric-maint-named/report.md`、同目录的 `summary.txt`、`verified-results.json` |

论文中第 2.1 节表格的数值直接写在正文里（来自上面两份工作负载证据）；第 7.6 节的场景代价表和场景数值宏由 `tools/paper-results.py` 从原始输出生成到 `gen/`；机制层（第 7.2–7.5 节）的数值宏 `\Rp* \Sn* \Cb* \Eone* \Tp* \Wr* \Du*`与随机并发表由 `tools/review-results.py` 从 `exp/2026-10-02-cache-baseline-tpcds` 的存档生成（实验数据统一保留在 `exp/`，Overleaf 工程只加载 `gen/` 的生成文件）；论文的六幅图是 `tools/figures/build.py` 生成的矢量 PDF，图 3–6 直接读取 `exp/` 中的存档并与 `gen/` 的数值核对：

```bash
# noctis，仓库根目录
python3 tools/paper-results.py --scen results/scen-20260930 --prefix PrevScen --numbers-only overleaf/gen/numbers-prev.tex   # 此前一轮三模型（\PrevScen*）
python3 tools/paper-results.py --scen results/scen-20261002 --models "DeepSeek V4.1 Flash" --out overleaf/gen --json exp/2026-10-02-scenarios-ds/paper-results.json
python3 tools/scen-stats.py --scen results/scen-20261002 --json exp/2026-10-02-scenarios-ds/scen-stats.json --tex-out overleaf/gen   # 预定分析方案：整群自助法区间与预先声明的比较（\Ds*）
python3 tools/review-results.py --exp exp/2026-10-02-cache-baseline-tpcds --out overleaf/gen
python3 tools/figures/build.py   # 四幅图：overleaf/figures/<名称>.pdf 与 <名称>-zh.pdf
```

Section 2.1 values are written in the text from the two workload reports. Section 7's scenario cost table and the in-text number macros are generated into `gen/` from raw outputs; the six figures are vector PDFs drawn by `tools/figures/build.py`, which reads the archived results and checks them against `gen/`.

## 已支撑的结果 / Supported results

- **2026-10-06 现行数值**（论文正文、`overleaf/gen/`）：端到端已建模破坏 MAVRA **74%**（73–76），轨迹检索 57%，定义级 64%，自检 63%；MAVRA − 轨迹检索 **+17**（15–18，预先写定的 d1），MAVRA (gold SQL) 73%（−1–3）；每次运行发布修复 4.7（gold SQL 8.0）。定义库回放（1,470 道共同题，各方法同一参照，G8 在学习时快照上）：MAVRA 答对 **933**、条件覆盖的变化下零错误（与标准答案 SQL 相同；G8 在当前数据上为 780），按模式变更失效 629 个错误，表级测试 603；TPC-DS 981 道：MAVRA **630**（标准答案 630，当前数据 360），按模式变更失效 437 个错误。详见 `exp/2026-10-02-cache-baseline-tpcds/README.md` 与 `exp/2026-10-02-scenarios-ds/README.md` 的 10-06 小节。

- 工作负载：智能体 SQL 只有 24% 复用已出现模板（Redset 读查询 93.4%）；68% 的调用用于探索；93% 的查找重复此前会话获得的事实，其中大部分是表结构事实，SQL 查找中 38% 重复事实且没有一条 SQL 文本重复；32 个错误答案全部来自执行成功的 SQL。
- 配对回放（固定学到的定义库，只换维护方式）：在已建模的变化下各重验证方法零错误答案，只看结构 **645** 个；各重验证方法只在单位变化下答错（101）。条件级、定义级、通用缓存逐题结果 **100%** 相同——场景中的正确率差来自学到的库。维护 DB 时间：条件级 583 s，通用缓存 613 s（1.05×），定义级 1,058 s（1.82×）。
- G8 参照：同一批 1,470 题上，判题学习查询为参照答对 933，智能体自己的学习 SQL 为参照答对 780（−10.4 个百分点，95% 区间 9.4–11.8）；差别全部变为不可用，没有一题变错。
- 修复唯一性：备份副本反例中，没有唯一性规则且参照预见来源列时发布错误修复（4 道新题答错 2 道）；有规则时在两种参照下都撤下定义；规则不改变 3,000 道配对题的任何结果。
- 绑定快照执行：核对与执行之间提交写入时预检查 10/10 违规、快照 0/10；未通知的写入刚提交时预检查 7/10 违规、快照全部拒绝；随机并发下预检查 3.8–4.6%（不通知）与 0.07–0.28%（通知）的作答违规，快照 0/11,297；读者中位延迟相同，写者单行语句吞吐约 0.7×，32 并发写者 0.97×（不分片 0.36×），批量语句 1.05×。
- 维护代价：19 个定义错峰时条件级 14.0%、通用缓存 16.7%（相对定义级），仅范围 83–94%；只有共享最少时条件级明显更省（42.5% 对 56.8%，来自条件身份与写法无关）；同时到达 50–84%；零共享时各方法 95–102%；4M 行 13.7% / 16.6%；32 个 Agent 错峰 13.6% / 16.6%、同时 91.6% / 90.4%；1M–16M 行比例稳定在 12.0–13.0%。TPC-DS：175 个定义、65 个不同条件，更新 store_sales 影响 101 个定义、310 次检查、12 个不同条件。
- 修复期间等待：同时到达下不可用从定义级 30、条件级 63 降为 0，等待与 DB 工作不变。
- 声明使用：26% 的答案没有声明定义；声明了正确修订仍答错 11/834（1.3%）。
- 场景（当前设计，DeepSeek V4.1 Flash，3 次独立运行，按运行整群自助法 95% 区间）：全部情形 不共享 32%、轨迹检索 76%、无守护 75%、只看结构 75%、撤销重学 67%、定义级 69%、MAVRA **81%**（80–81）。留出题 MAVRA 与轨迹检索都是 100%。5 种已建模破坏性变化：MAVRA 73%（71–76）、定义级 64%、轨迹检索 57%；预先声明的比较 MAVRA − 轨迹检索 **+16**（14–18），MAVRA − 定义级 +9（0–15，配对回放表明维护相同、差别来自学习）。无守护与只看结构在已建模变化下提供过期定义 98、99 道。备份副本：轨迹检索 72% 高于 MAVRA 61%（MAVRA 撤下退货定义：退货金额 8/9 对 4/9 有利，退货率 0/6 对 6/6 不利）。端到端维护 DB 时间条件级为定义级的 90%（修复搜索为主）。此前一轮三模型（旧二进制、无轨迹基线）：不共享 32%，定义级 77%，条件级 74%，各模型共享提升一致。

统计口径（排除用量上限失败的 136 道题、剔除学习阶段被中断的 2 组、场景等权、按题自助法区间）写在 `tools/paper-results.py` 文件头。早期单模型运行的舍入修正（52.96 秒、76.1%）仍记录在 `exp/2026-09-30-metric-maint-named/verified-results.json`。

- 表级测试基线（dbt 式，按初始快照校准的 unique / relationships 测试，失败即隔离读该表的定义）：同一批 1,530 题次上答对 **631**（MAVRA 973），已建模变化下同样零错误答案；少答对的 342 题是 MAVRA 修复（状态流水 105、版本化更正 174、维表拉链 57）或因定义自带过滤而保留（6）的题；不必要的不可用 153 对 111。配对差 22.4 个百分点（整群自助 95% 区间 21.8–22.8）。
- 论文形式化（10-03）：命题 1（四类条件在业务前提 B1/B2 下充分；边界：取值含义、同构总体、合法但错误的日期键）、引理 1（事务性版本相同 ⇒ 结论可复用，依赖快照嵌套与写入—计数同事务）、算法 1（有界修复：不丢键、唯一、G3–G5 与 G8）。

- 增补方法（10-03，DeepSeek V4.1 Flash × 3 次，预先写定比较）：MAVRA 以智能体提炼的学习查询为 G8 参照时，全部情形 81%、已建模破坏 **74%**（判题参照 73%，差 +1，区间 −1–3）；每次运行发布的修复从 8.0 降到 4.7，被拒绝的修复撤下定义后智能体自行重推过滤，正确率不变。轨迹检索 + 自验证提示：已建模破坏 **63%**（轨迹检索 57%，+5，区间 1–10），每题轮数 5.0 → 5.8；MAVRA 仍领先 11（6–15）。
- TPC-DS SF1 上的配对回放（10-03）：93 个模板导出的定义（91 个通过准入），每种方法 981 道计分题。MAVRA 答对 **630**，已建模变化下零错误答案（72 个错误全部来自单位变化），状态流水、版本化更正、维表拉链下 279 道题经修复后作答，重复装载、日期键改写、备份副本下撤下定义；只看结构在已建模变化下 437 个错误答案；表级测试隔离 437 道必要 + 145 道不必要，少答对的 279 题正是 MAVRA 修复的题；智能体参照答对 360（拒绝触及学习期的修复，0 题变错）。维护 DB 时间 2,602 秒中 2,381 秒是重复装载下的修复搜索。定义级未在 TPC-DS 上运行（逐定义修复搜索在 300 万行上超过 90 分钟）。
## 实现边界 / Implementation boundaries

| 机制 / Mechanism | 状态 / Status |
| --- | --- |
| 成功轨迹提炼、G1–G7 准入 / extraction and admission | 已实现；早期运行 30 次初始提炼中 4 次别名表达式未通过 G3 / implemented |
| 条件级维护及结论复用 / condition maintenance and reuse | 受控实验、配对回放与三模型场景均有结果；节省可由通用版本缓存几乎全部获得，正文不再作为贡献 / evaluated; savings matched by a generic version-keyed cache |
| 相同条件的在途合并 / in-flight merging | 各重验证方法相同 / shared by revalidation baselines |
| 修订引用检查与 SQL 审查 / revision checks and SQL review | 已实现，仅覆盖显式声明；维表拉链中 SQL 审查挡住了过期定义的放大连接 / implemented for declared uses |
| 受限修复及 G8 回归 / restricted repair and regression | 已实现；只能加过滤，无法去重或重映射键；2026-10-02 起候选过滤不唯一时不自动修复（`repair_unique`，默认开），正文已写入；场景运行早于此规则，配对回放复核结果不变 / filter-only repair; unique-candidate rule described in the paper |
| 同快照验证与执行 / same-snapshot validation and execution | 已实现，默认关闭（事务性版本由语句级触发器维护、16 片；可重复读快照内核对并执行），正文第 6.2、7.3 节；不作为新意（技术先例 TxCache）/ implemented (opt-in), in the paper; TxCache is the precedent |
| 取值层面的条件（如单位）/ value-level conditions | **未建模**；单位变化场景为对照 / not modeled |
| 修复进行中的请求等待 / wait for in-progress repair | 2026-10-02 已实现（`wait_repair`，默认开），正文第 5.3、7.4 节；场景运行早于此机制 / implemented, in the paper |
| AgentSM 式轨迹检索基线 / matched trajectory retrieval | 已实现并运行（`traj-global`，DeepSeek V4.1 Flash × 3 次）；自验证变体 `traj-verify` 与智能体参照的 `metric-global-exref` 同样各 3 次（10-03）；其他模型待补 / implemented and evaluated on DeepSeek |

## 评估边界 / Evaluation limits

合成表结构之外增加了 TPC-DS SF1（模板导出的定义库），两者的变化都由我们注入；机制层回放用 20 万行（场景用 100 万行），结果类别与规模无关、耗时有关；场景运行早于唯一性规则、修复等待与绑定快照执行。场景实验计划 3 模型 × 6 方法 × 3 次重复共 54 组，因 ClinePass 5 小时与周用量上限，目前分析 43 组（DeepSeek 与 GLM-5.3 较完整，GLM-5.3 Flash 缺得多）；周上限约 2026-10-07 重置后补跑，再重跑 `tools/paper-results.py`。工作负载刻画只用一个模型；两个 GLM 模型的轨迹因 Cline 余额耗尽未完成。维护正反序是顺序控制，不是统计显著性检验；8 个并发 Agent 是脚本 Agent。数据库关闭 WAL 和 fsync。参考 SQL 与任务生成器同源。

Only one synthetic schema is used. The scenario design has 54 cells; usage caps leave 43 analyzed cells, mostly missing GLM-5.3 Flash repetitions. The workload study uses one model. Reference SQL and the task generator share origins.

## 重构前的编译记录 / Compilation before restructuring

2026-10-02 在 noctis（TeX Live 2026）用 `./build.sh all` 编译通过：英文稿 13 页（正文在第 12 页结束，其后为参考文献，未超过 12 页正文上限），双语稿 20 页。

Compiled on noctis with TeX Live 2026: English 13 pages including references (body ends on page 12), bilingual 20 pages.

2026-10-04（摘要与引言重写、引用核对后）在 noctis 用 `./build.sh all` 编译：英文稿 15 页，正文在第 13 页右栏约四分之一处结束，超出 12 页正文上限约 0.6 页；双语稿 23 页（CJK 字体改用 Noto，浏览器可正常显示）。

Compiled on noctis on 2026-10-04 after the abstract/introduction rewrite and the citation audit: English 15 pages with the body ending about a quarter down the right column of page 13 (roughly 0.6 page over the 12-page body limit); bilingual 23 pages.

2026-10-07 图表整理后（表 3、表 4 删除，表 2 增加“实验”列；原图 1 定义共享与原图 6 按类别点图删除，点图的区间并入热力图末行；回放图增加 TPC-DS 面板；摘要精简；浮动体与正文间距 14pt）在 noctis 编译：英文稿 14 页，正文在第 13 页左栏约三分之二处结束，超出 12 页正文上限约 0.3 页；双语稿 22 页。

Compiled on noctis on 2026-10-07 after consolidating the figures and tables (Tables 3 and 4 removed and Table 2 given a studies column; the sharing figure and the by-group dot plot removed, the dot plot's intervals folded into the heatmap's last row; a TPC-DS panel added to the replay figure; abstract shortened; float separation 14pt): English 14 pages with the body ending about two thirds down the left column of page 13 (roughly 0.3 page over the 12-page body limit); bilingual 22 pages.

## 10-03 补充实验与已回退的重构 / Supplementary experiments and the reverted restructure

2026-10-03 晚曾把论文主线改写为“共享数据库知识与经验证的经验层”（标题 *Shared Database Knowledge and Verified Experience for Data Agents*）。2026-10-04 决定回退：该主线把贡献放宽到已有大量先例的共享记忆领域，而模型、命题、引理、算法和最强证据都只覆盖指标定义；新增主实验四组正确率相同，只在 token 与秒数上有差别。论文回到 `60d0783` 的主线（有效性模型、使用时的强制保证、有界修复）。重构稿 47 个源文件归档在 `exp/2026-10-03-shared-memory/overleaf-restructure-2026-10-03.tar.gz`，其验收记录见 [refactor-acceptance.md](refactor-acceptance.md)。

On the evening of 2026-10-03 the paper was rewritten around a shared-memory layer; on 2026-10-04 this was reverted to the validity-maintenance main line of `60d0783`. The rewritten sources are archived, not deleted.

10-03 运行的实验保留为补充证据，尚未进入正文；数值宏可用各自脚本的 `--tex-out overleaf/gen` 重新生成：

| 实验 | 证据 | 结果 | 可能的用处 |
| --- | --- | --- | --- |
| 固定库会话耗时 | `exp/2026-10-03-session-latency/` | 三种维护方法 54/54、不共享 16/54；MAVRA 更新后首用更快，但全矩阵平均 37.68 s 对通用缓存 31.97 s，LLM 占共享方法服务时间约 99% | 已进入正文（10-04）：摘要、引言和 §7 的“代价与声明使用”段引用 `\Sl*` 宏（`gen/session-latency.tex` 从归档恢复），作为相对不共享的完成时间、轮数与 token 节省；对定义级与通用缓存的完成时间如实写出 |
| 匹配生产者前缀的积累（S1） | `exp/2026-10-03-shared-memory/analysis/results.md` | 相同显式定义下四组均 54/54；积累比隔离输入 token 低 24.4%、结构调用低 27.7%；仅报指标名时隔离 3/12、冻结 6/12、积累与轨迹检索 12/12 | 已进入正文（10-04）：§7 “代价与声明使用”段以文字引用相同定义下的结构查找、SQL 探查和完成时间节省（3.5→2.5、0.20→0.06、13.4→9.5 s）；不能区分 MAVRA 与轨迹检索 |
| 验证排序（S2） | 同上 `raw/results/strategy-main/` | 只排三项检查；采纳 0/3、3/3、3/3，回放代价低 0%、61.9%、37.9%，与回顾最优固定顺序相同 | 不进正文 |
| 元数据诊断 | 同上 `raw/results/metadata-audit/` | 新智能体复用画像零探查；仅改注释与新增列在进程内不刷新，重启后更新 | 目录刷新的实现边界 |

实验后代码修正（随 2026-10-04 的提交进入 main）：G3 与规范 SQL 编译要求每个非时间连接从事实表指向至多一行的另一侧，拒绝反向、自连接与多跳引用；条件身份与过滤去重改为保留字面量的保守 token 比较。两轮 S1 前缀的 25 个指标条目均满足新约束；实验时源码按原样归档。
