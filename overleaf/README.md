# MAVRA Overleaf 工程

论文标题：**MAVRA: Keeping Shared Metric Definitions Valid for Data Agents**。

`main.tex` 是双语入口，`main-en.tex` 是英文入口，两者直接读取同一份 `paper.tex`。修改对应章节即可同时更新两种语言，不再生成或维护正文副本。本次拆分保留原有正文、公式、图表、数值、引用顺序和排版设置。

## 目录与编辑位置

| 路径 | 用途 |
| --- | --- |
| `main.tex` | 双语入口，只设置文档类与语言开关 |
| `main-en.tex` | 英文入口，只设置文档类与语言开关 |
| `paper.tex` | 标题、作者、文档环境与章节顺序 |
| `acmart.cls` | 随包提供的官方 ACM 文档类，不依赖编译环境预装此文件 |
| `latex/preamble.tex` | 宏包、语言宏、颜色、图表样式和数值宏加载 |
| `latex/acmart/acmart.dtx` | 官方文档类的对应源码，保留版权及 LPPL 许可说明 |
| `sections/abstract.tex` | 中英文摘要、关键词与 `\maketitle` |
| `sections/01-*.tex` 至 `10-*.tex` | 原论文的十个章节，编号和顺序不变 |
| `sections/evaluation/` | 实验设置、有效性、并发、修复、维护代价与场景六个小节 |
| `figures/` | 四幅图：`*.tex` 写标题、标签与描述，图本身是 [`tools/figures/build.py`](../tools/figures/README.md) 生成的矢量 PDF（`<名称>.pdf` 用于英文稿，`<名称>-zh.pdf` 用于双语稿），不要手改；另有算法 1 |
| `tables/` | 八张表，包括标题和原有生成数据的加载位置 |
| `references.tex` | 原样保留的 `thebibliography`，引用键与条目顺序不变 |
| `gen/` | 实验统计脚本生成的数值宏、表格数据和绘图坐标；不要手改 |
| `build.sh` | 编译或生成 Overleaf 上传包 |
| `mavra-sigmod-bilingual.zip` | 包含两个入口、论文源码与 ACM 文档类的 Overleaf 源码包；标准宏包和字体由 TeX 环境提供 |

章节中的 `\bi{English}{中文}`、标题与图表中的 `\bt{English}{中文}` 保持原用法。论文的 LaTeX 文件均在本目录内；在安装了所需宏包与字体的 TeX 环境中，编译不依赖父目录、实验数据或实验服务器。

## Overleaf 设置

1. 上传 `mavra-sigmod-bilingual.zip`，保留包内目录结构。
2. 双语稿：Main document 选择 `main.tex`，Compiler 选择 **XeLaTeX**。
3. 英文稿：Main document 选择 `main-en.tex`，Compiler 选择 **pdfLaTeX**，也可使用 XeLaTeX。

Overleaf 的编译器需要在项目设置中选择；源码顶部的 `% !TeX program` 注释不会自动改变这一设置。若使用 pdfLaTeX 编译双语入口 `main.tex`，应先改用 XeLaTeX。[官方编译器设置说明](https://docs.overleaf.com/getting-started/recompiling-your-project/selecting-a-tex-live-version-and-latex-compiler)。

上传包现已包含 `acmart.cls`，应放在与 `main.tex` 相同的项目根目录。模板使用 [CTAN / TeX Live 官方发行版](https://ctan.org/pkg/acmart) **2.20（2026-08-16）**，文件原样保留，随包携带对应的 `acmart.dtx` 源码。

保留 `\documentclass[sigconf,review,anonymous]{acmart}` 和模板原有排版。投稿格式参考 [SIGMOD 2027 Research 官方要求](https://2027.sigmod.org/calls_papers_sigmod_research.shtml)，最终页数应以投稿用编译器生成的 PDF 为准。

## 编译与打包

在本目录执行：

```bash
./build.sh en    # 英文稿 → build/main-en.pdf
./build.sh bi    # 双语稿 → build/main.pdf
./build.sh all   # 两份都编译，默认选项
./build.sh pack  # 更新 mavra-sigmod-bilingual.zip，不需要 LaTeX 环境
```

编译优先使用 `latexmk`：英文调用 pdfLaTeX，双语调用 XeLaTeX；也支持已有的 Tectonic 环境。ACM 文档类已随包提供；环境仍需提供其标准宏包依赖与 colortbl，以及双语模式下的 `ctex` / Fandol 字体。打包只需要 Python 3，包含官方文档类及其源码，并按 `\input` 与 `\includegraphics` 依赖收集论文文件，不包含实验附件、编译缓存或无关生成文件。构建不会改写论文源文件。

### 缺少标准宏包时

`acmart.cls` 成功加载后仍报 `xkeyval.sty` 等文件缺失，说明编译环境未安装对应宏包。类文件不能替代宏包和字体安装。使用 `latexmk` 且存在 `kpsewhich` 时，`build.sh` 会在编译前一次列出缺失的直接依赖和双语字体；这项预检不覆盖所有间接依赖。Overleaf 网页中的直接编译不会执行此脚本。

自建 Overleaf Community Edition 默认只有精简版 TeX Live。按照[官方安装说明](https://docs.overleaf.com/on-premises/installation/upgrading-tex-live)，管理员应在**实际编译容器**内补齐环境；使用 Overleaf Toolkit 时先执行 `bin/shell`，然后运行：

```bash
tlmgr install scheme-full
tlmgr path add
```

安装后可用 `kpsewhich xkeyval.sty`、`kpsewhich ctex.sty` 和 `kpsewhich FandolSong-Regular.otf` 检查是否返回文件路径。容器升级或重建时，应按官方说明保留完整 TeX 安装；Server Pro 的独立编译容器应按[对应镜像配置说明](https://docs.overleaf.com/on-premises/maintenance/extending-tex-live)处理。

如果使用官方 `overleaf.com`，可在项目设置中切换到另一年度 TeX Live 后重新编译；若仍缺少标准宏包，应交由平台排查编译环境。本地 TeX Live 则由其安装管理员通过包管理器补齐。Tectonic 会通过自己的资源包获取宏包，Tectonic 编译成功不能证明其他环境已安装相同依赖。

## 数值与实验存档

实验数据统一保存在仓库的 `exp/`，不再在 Overleaf 工程中保留副本。

| 生成文件 | 来源与生成脚本 |
| --- | --- |
| `gen/numbers.tex`、`gen/scen-heat.tex`、`gen/scen-cost.tex` | `tools/paper-results.py`；原始场景结果在 noctis 的 `results/scen-20261002/`，汇总存档在 `exp/2026-10-02-scenarios-ds/paper-results.json` |
| `gen/numbers-prev.tex` | `tools/paper-results.py --numbers-only`；此前一轮三模型实验，原始结果在 noctis 的 `results/scen-20260930/` |
| `gen/scen-ds.tex` | `tools/scen-stats.py`；汇总存档在 `exp/2026-10-02-scenarios-ds/scen-stats.json` |
| `gen/review.tex`、`gen/snapshot-stress.tex` | `tools/review-results.py`；本地存档在 `exp/2026-10-02-cache-baseline-tpcds/` |
| `gen/session-latency.tex` | `tools/session-latency-stats.py --tex-out`；存档在 `exp/2026-10-03-session-latency/` |
| `figures/*.pdf` | `tools/figures/build.py`；图 3、图 4 直接读取上面的 `cb-1m-share-stats.json` 与 `scen-stats.json` 存档，并与 `gen/` 中正文引用的数值逐一核对 |
| 工作负载表中的数值 | `exp/2026-10-01-workload-characterization/` |

在 noctis 的仓库根目录重新生成（2026-10-06 核对：前四条命令逐字节复现 `gen/` 中对应文件）：

```bash
python3 tools/paper-results.py --scen results/scen-20260930 --prefix PrevScen --numbers-only overleaf/gen/numbers-prev.tex
python3 tools/paper-results.py --scen results/scen-20261002 --models "DeepSeek V4.1 Flash" --out overleaf/gen \
  --json exp/2026-10-02-scenarios-ds/paper-results.json
python3 tools/scen-stats.py --scen results/scen-20261002 --json exp/2026-10-02-scenarios-ds/scen-stats.json --tex-out overleaf/gen
python3 tools/review-results.py --exp exp/2026-10-02-cache-baseline-tpcds --out overleaf/gen
python3 tools/figures/build.py
```

场景生成命令需要服务器上完整的原始结果；正常编辑与编译不需要重新运行实验。研究状态与实现边界见 [docs/research-status.md](../docs/research-status.md)，实验索引见 [exp/README.md](../exp/README.md)，参考文献核对记录见 [docs/citation-audit-2026-10-01.md](../docs/citation-audit-2026-10-01.md)。

`overleaf/` 是主仓库的普通目录。上传包可以手动导入 Overleaf，目前未配置在线项目自动同步。
