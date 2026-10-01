# MAVRA：面向数据智能体的共享指标定义维护

English title: **MAVRA: Maintaining Shared Metric Definitions for Data Agents**.

## SIGMOD 模板与双语 / SIGMOD format and languages

已按 [SIGMOD 2027 Research 官方投稿要求](https://2027.sigmodconf.hosting.acm.org/calls_papers_sigmod_research.shtml) 改为 ACM 双栏匿名审稿格式：

```latex
\documentclass[sigconf,review,anonymous]{acmart}
```

SIGMOD research submissions use the ACM two-column proceedings template, Letter paper, double anonymity, and at most 12 pages excluding references. The submission and revision format is `sigconf`; accepted papers are converted to PACMMOD later. The source does not change the template's margins, column spacing, font sizes, or line spacing.

主文件默认是逐段英文、中文对照，摘要、正文、标题、图表说明和表头均有中英文。参考文献保留原出版信息。双语稿供共同写作与核对；英文导出稿供准备投稿，页数需在最终 PDF 中核实。

The default manuscript pairs English and Chinese paragraphs, headings, captions, and table headers. Bibliographic metadata stays in its original language. The bilingual manuscript is for joint editing; the English export uses the same layout and numerical results. Check the final PDF's page count before submission.

## 文件 / Files

| 文件 / File | 用途 / Purpose |
| --- | --- |
| `main.tex` | 中英文双语全文；XeLaTeX。Complete bilingual manuscript; XeLaTeX. |
| `main-en.tex` | 从同一正文生成的英文稿；pdfLaTeX 或 XeLaTeX。English export generated from the same manuscript. |
| `export-english.ps1` | 编辑双语稿后重新生成英文稿。Regenerates the English export. |
| `export-english.sh` | Linux 版英文稿导出，与 `.ps1` 等价。Linux equivalent of the PowerShell export. |
| `build.sh` | 在 noctis 上导出英文稿、编译两份 PDF 到 `build/` 并报告页数：`./build.sh [en\|bi\|all]`。Exports, compiles both PDFs into build/, and reports page counts. |
| `abstract-zh.md` | 当前中文摘要，与正文结果一致。Current Chinese abstract. |
| `RESEARCH_STATUS.md` | 实验证据、边界与未完成机制。Evidence and remaining implementation work. |
| `gen/` | 由 `tools/paper-results.py` 从原始实验输出生成的场景表、图的坐标和正文数值宏，正文用 `\input` 引入，请勿手改。Generated tables, plot coordinates, and number macros; do not edit by hand. |
| `evidence/` | 本轮报告和每组合计的原样副本。Unmodified copies of current reports and cell summaries. |
| `mavra-sigmod-bilingual.zip` | 可直接上传 Overleaf 的源文件包。Source package for Overleaf. |

两个 TeX 文件包含 TikZ 架构图、pgfplots 图和参考文献，编译只依赖本目录的 `gen/`，不依赖父仓库或 `evidence/`。

Both TeX files contain the figures and bibliography and compile with only this directory's `gen/`, independently of the system repository or evidence directory. They use standard packages supplied by Overleaf, including `acmart`, TikZ, pgfplots, colortbl, and, in bilingual mode, `ctex` with Fandol fonts.

## Overleaf 设置 / Overleaf setup

1. 上传 `mavra-sigmod-bilingual.zip`，或将仓库文件上传至已有项目。Upload the ZIP or files to your existing project.
2. 双语稿：Main document 设为 `main.tex`，Compiler 设为 **XeLaTeX**。Bilingual: select main.tex and XeLaTeX.
3. 英文稿：Main document 设为 `main-en.tex`，Compiler 可设为 **pdfLaTeX**。English: select main-en.tex and pdfLaTeX.
4. 在 Overleaf 的项目设置中选择编译器，源码中的编辑器提示不自动改变 Overleaf 设置。Select the compiler in project settings; the source comment does not change that setting automatically.

后续统一修改 `main.tex`，然后在本目录运行：

```powershell
./export-english.ps1
```

You can also change the standalone source's sole `\bilingualtrue` line to `\bilingualfalse` to hide Chinese without duplicating the manuscript. The English file retains Chinese source arguments but does not typeset them or load CJK packages. The system name remains centralized in `\system`.

## 实验与数值来源 / Experiments and number provenance

论文写入四组证据：受控维护实验（80 组）、工作负载刻画（Redset 4.41 亿条查询对 100 个智能体会话）、三模型十种数据变化的端到端场景（43 组），以及早期单模型运行中的准入拒绝。第 2.1 节表格数值直接写在正文；第 7 节场景表、两张图和正文中的场景数值以宏（如 `\ScenAccCond`）引用 `gen/numbers.tex`。场景补跑完成后，在 noctis 仓库根目录运行 `python3 tools/paper-results.py --scen results/scen-20260930 --out overleaf/gen`，再编译即可更新全文数值。口径与边界见 `RESEARCH_STATUS.md`。

The manuscript reports the controlled maintenance sweeps, the workload characterization, the three-model data-change scenarios, and admission rejections from an earlier run. Section 7's scenario table, figures, and in-text scenario numbers come from `gen/`; rerun `tools/paper-results.py` after the remaining repetitions. Definitions and limits are in RESEARCH_STATUS.md.

## 图表风格 / Figure style

图用 TikZ／pgfplots 在 TeX 中绘制，字体与正文一致，轴标签和图例支持双语。每种方法在所有图表中颜色固定（导言 `mCond`、`mDef` 等，表 3 的色块即图例）：\system 为蓝色且蓝色只用于它，定义级为橙色，其余方法按经色觉缺陷校验的顺序取色；准确率表用中性灰阶底纹。方法名全文统一为 No sharing、Unguarded、Schema-only、Revoke-on-write、Definition-level、Scope-only、Condition-level（\system）。全部表格用 `\footnotesize`。

Figures are drawn with TikZ/pgfplots. Each method keeps one color across all figures and tables (Table 3 shows the swatches): MAVRA is blue and blue is reserved for it, definition-level is orange, others follow a CVD-checked order; the accuracy table uses a neutral gray ramp. Method names are uniform across text, tables, and figures, and all tables use `\footnotesize`.

## 编译 / Compilation

2026-10-01 在 noctis 用 `./build.sh all` 编译：英文稿 11 页（正文在第 9 页结束），双语稿 16 页。

Compiled on noctis on 2026-10-01: English 11 pages including references (body ends on page 9), bilingual 16 pages.

## 仓库 / Repositories

主仓库 / Main repository: <https://github.com/mmmttt000045/agent4db-adapter>

论文目录 / Paper directory: <https://github.com/mmmttt000045/agent4db-adapter/tree/main/overleaf>

`overleaf/` 现在是主仓库的普通目录，与系统代码共享 Git 历史、`main` 分支和远程仓库。可以从仓库根目录统一提交代码、论文和实验更新；从本目录执行 Git 命令也会作用于同一主仓库。它不是子模块，编译缓存仍被忽略，Overleaf 上传包纳入版本控制。

This is a regular directory of agent4db-adapter, tracked with the system code on the same main branch. Git commands here resolve to the main repository. It is not a submodule. Build output stays ignored, while the upload ZIP is tracked.

此前的 [独立论文仓库](https://github.com/mmmttt000045/agent-adaper-paper) 保留早期历史，本地 Git 元数据也已备份在主仓库的 `.git/overleaf-repository-backup-10b3fbf/` 中。后续统一在主仓库维护。本目录尚未与在线 Overleaf 项目建立自动同步。

The earlier paper repository preserves its history, and its local metadata has been archived under the main repository's .git directory. Ongoing paper work belongs in the main repository. There is no automatic synchronization with an online Overleaf project.
