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

`references.tex` 调用 `IEEEtran.bst` 与 BibTeX：只输出正文引用的条目，按首次引用排序。`references.bib` 保留原稿全部元数据；未引用条目不占参考文献版面。此次转换未对每条文献重新做出版信息核验。

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

- 当前稿件的群体实验为三种作用域消融（无记忆、私有记忆、MAVRA）各五轮，共 2,640 会话：初始阶段 `3 × 16 × 7 × 5 = 1,680`，更正后 `3 × 16 × 4 × 5 = 960`。`exp/2026-10-12-population/population-stats.json` 中每种方法分别为 560 与 320 个有效会话；正文按阶段报告结果。10-28移除的旧比较组仍保存在原始归档中，不再计入稿件分母。
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
| `gen/numbers.tex`、`gen/scen-cost.tex`、`gen/scen-ds.tex` | `tools/paper-results.py`、`tools/scen-stats.py`；当前五轮场景汇总在 `exp/2026-10-10-scenarios-q5/` |
| `gen/numbers-prev.tex` | 早期三模型批次，`PrevScen` 前缀；存档在 `exp/2026-10-01-scenarios/` |
| `gen/review.tex`、`gen/snapshot-stress.tex` | `tools/review-results.py`；`exp/2026-10-02-cache-baseline-tpcds/` |
| `gen/generality.tex`、`gen/replay-safety.tex` | `tools/generality-stats.py`、`tools/replay-safety-summary.py`；通用性回放与共同题次审计 |
| `gen/opt.tex`、`gen/premise.tex`、`gen/sharing.tex` | `tools/opt-stats.py`、`tools/premise-stats.py`、`tools/sharing-stats.py`；优化、前提失效与使用成本，具体输入范围见各脚本和实验清单 |
| `gen/external.tex` | `tools/external-reuse-stats.py`；`exp/2026-10-14-external-motivation/` |
| `gen/session-latency.tex`、`gen/lifecycle*.tex` | 补充实验宏，分别由会话耗时和生命周期统计工具生成 |
| `figures/*.pdf` | 脚本、数据和单图入口见 [绘图说明](../tools/figures/README.md)；架构图由 `tools/figures/build.py architecture` 生成，RelBench 图由 `tools/figures/relbench_cumulative.py` 生成 |

重算时先确认输入目录与采用范围，建议先写临时输出目录并比较差异，再更新 `gen/`。旧三轮场景命令不能直接替换当前五轮图表的输入。

## 2026-10-28 官方 API 实验与 10-29 归因复核

官方 API 比较已完成：无记忆、ACE、AWM、G-Memory、MAVRA，两库、三任务、三截点，共90个正式会话。按用户最新要求，删除新增的六任务质量图；Fig.3 恢复 01daa213 的 `relbench-cumulative` 原图、图注与历史五截点数据。昨晚官方API实验仅用于原 Fig.5 的 `reuse-work` 工作量图；删除前一图后，它自动编号为 Fig.4。官方实验的设置、质量边界与来源审计集中在该图对应小节，完整数据仍在工件中。Table III、含旧数据的 Table IV、引言、摘要、结论及 Fig.1 位置均保持本轮修改前状态。历史网关结果与官方API结果分别陈述。

10-29逐会话复核发现：12个MAVRA复用会话中9个首先验证完整旧SQL，6个原样保留旧SQL。查找工具内部也会编译定义，显式组合调用为零不能等同于无编译；但本轮没有分离结构化定义的增量作用。首截点一次直接验证的编译SQL被目标任务审计拒绝。正文、图注、系统概览和实证限制已据此同步，核心表示消融仍待补充。详见主仓库 `exp/2026-10-29-fig5-review/` 的审计与来源记录。

本次发布保留可用结果及其限制，不新增模型调用。工作量图不作为结构化组合有效的独立证明；新的组件实验尚未执行。英文与双语入口共用修订正文。

项目说明见 [主仓库 README](../README.md)。当前 `references.bib` 是稿件实际编译的来源。

## 独立论文仓库

`overleaf/` 仍是主仓库的普通目录，主仓库远程地址保持不变。独立论文仓库为 [icde-2027-paper](https://github.com/mmmttt000045/icde-2027-paper)，论文源文件放在该仓库根目录，可用 Overleaf 的 GitHub 导入功能创建项目。本地独立工作副本位于同级目录 `../icde-2027-paper/`；本目录的修改不会自动同步过去，需先更新独立工作副本并推送，再在 Overleaf 的 Integrations → GitHub 中手动拉取。Overleaf 中的修改也需先推送回 GitHub，再拉取至本地工作副本。

工作量图沿用 `exp/2026-10-29-fig45-official/build-figures.py` 已生成的原 Fig.5 PDF，数据和版式本轮不变。此前生成的质量图与官方累计图从正文移除，文件作为历史版本留档，不再参与当前编译。恢复记录与源文件保护哈希见 `exp/2026-10-29-fig3-restore/`。
