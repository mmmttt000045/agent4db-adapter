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
| `abstract-zh.md` | 当前中文摘要，与正文结果一致。Current Chinese abstract. |
| `RESEARCH_STATUS.md` | 实验证据、边界与未完成机制。Evidence and remaining implementation work. |
| `evidence/` | 本轮报告和每组合计的原样副本。Unmodified copies of current reports and cell summaries. |
| `mavra-sigmod-bilingual.zip` | 可直接上传 Overleaf 的源文件包。Source package for Overleaf. |

两个 TeX 文件都独立包含 TikZ 架构图和参考文献，编译不依赖父仓库或 `evidence/`。

Both TeX files contain the architecture figure and bibliography and compile independently of the system repository or evidence directory. They use standard packages supplied by Overleaf, including `acmart`, TikZ, and, in bilingual mode, `ctex` with Fandol fonts.

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

## 新实验 / New experiments

系统仓库已快进至 `743041f`，实验为 2026-09-29 至 2026-09-30 的单模型、合成数据结果。论文写入 80 组维护配置、19 个定义、8 个脚本智能体，以及 6 组模型端到端对照。

The system repository is synchronized to `743041f`. The manuscript uses the September 29–30 maintenance sweeps and end-to-end experiment. It distinguishes maintenance DB time from whole-workload DB time, scripted concurrency from LLM concurrency, and measured behavior from the proposed snapshot protocol. See RESEARCH_STATUS.md for provenance and limits.

## 本地验证 / Local validation

Codex 内置 LaTeX 编译器返回运行环境错误 `Unable to find standard directories for platform`，未进入 TeX 源码诊断。当前环境也没有可用的终端 TeX 编译器，因此本次没有确认 PDF 编译成功、页数或实际页面效果。源文件已经打开在内置编辑器，并完成语言开关、LaTeX 结构、结果数值及打包检查。

The built-in compiler fails at environment initialization, before source diagnostics. No terminal TeX compiler is available, so PDF compilation, page count, and rendered layout remain unverified. Sources are preserved and opened in the built-in editor; structural, language-export, result, and packaging checks are recorded separately from compilation.

## 仓库 / Repositories

主仓库 / Main repository: <https://github.com/mmmttt000045/agent4db-adapter>

论文目录 / Paper directory: <https://github.com/mmmttt000045/agent4db-adapter/tree/main/overleaf>

`overleaf/` 现在是主仓库的普通目录，与系统代码共享 Git 历史、`main` 分支和远程仓库。可以从仓库根目录统一提交代码、论文和实验更新；从本目录执行 Git 命令也会作用于同一主仓库。它不是子模块，编译缓存仍被忽略，Overleaf 上传包纳入版本控制。

This is a regular directory of agent4db-adapter, tracked with the system code on the same main branch. Git commands here resolve to the main repository. It is not a submodule. Build output stays ignored, while the upload ZIP is tracked.

此前的 [独立论文仓库](https://github.com/mmmttt000045/agent-adaper-paper) 保留早期历史，本地 Git 元数据也已备份在主仓库的 `.git/overleaf-repository-backup-10b3fbf/` 中。后续统一在主仓库维护。本目录尚未与在线 Overleaf 项目建立自动同步。

The earlier paper repository preserves its history, and its local metadata has been archived under the main repository's .git directory. Ongoing paper work belongs in the main repository. There is no automatic synchronization with an online Overleaf project.
