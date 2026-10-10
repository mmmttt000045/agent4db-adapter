# 论文矢量图生成器

论文的五幅图都由这里的 Python 脚本画成矢量 PDF，不经过 TikZ、pgfplots、Visio 或 PPT。两张示意图用 `vecfig.py` 的 ReportLab 绘图套件（示意图需要毫米级的手工布局；贯穿示例沿用汇报图的 `parts.py`，按 300 mm 画、由 LaTeX 缩到版宽），三张数据图自 2026-10-07 起用 matplotlib（`mplstyle.py` 统一样式）：

| 图 | 脚本 | 输出（`overleaf/figures/`） | 数据 |
| --- | --- | --- | --- |
| 图 1 贯穿示例：门店营业额从学习、优化、使用到修复（通栏） | `example.py` | `running-example.pdf` | 数值写在脚本里，来源见脚本顶部说明（`exp/2026-10-08-optimize/trace`、`exp/2026-10-08-optimize/README.md`、noctis `results/scen-20261002`） |
| 图 2 系统架构 | `architecture.py` | `architecture.pdf` | 无 |
| 图 3 定义库回放（三个面板：学到的定义库、TPC-DS、另外三种模式合并） | `replay_outcomes.py` | `replay-outcomes.pdf` | `exp/2026-10-02-cache-baseline-tpcds/replay-stats.json`、`tpcds-replay-stats.json`、`tpcds-library.json`（定义数）；`exp/2026-10-11-generality/generality-stats.json` 的 `pooled`（TPC-H、SSB、BIRD financial，与 `generality.tex` 的 `\Gn*` 核对） |
| 图 4 维护代价 | `maintenance_cost.py` | `maintenance-cost.pdf` | `exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json` |
| 图 5 逐情形正确率分组柱状图（通栏；每组一种情形、每柱一种方法，柱为 3 次运行合并的正确率，竖线为按运行重抽样的 95% 区间，斜线为过期定义，底色组为合并的同类情形，“全部覆盖的破坏”组加宽并印出数值；只画 6 种方法，自行核验与两个回归测试变体在正文） | `scenario_changes.py` | `scenario-changes.pdf` | `exp/2026-10-10-scenarios-q5/scen-stats.json`（每种方法 `runs` 里逐次运行的计数、各组的 95% 区间），与 `paper-results.json` 交叉核对；情形顺序取自 `tools/paper-results.py` 的 `PHASES` |

每幅图生成两份：`<名称>.pdf` 用于英文稿（`main-en.tex`），`<名称>-zh.pdf` 用于双语稿（`main.tex`），标签为中文。`overleaf/figures/<名称>.tex` 按 `\ifbilingual` 选用其中一份，标题、标签和 `\Description` 仍写在 tex 文件里。

```bash
python3 tools/figures/build.py                  # 全部，写入 overleaf/figures/
python3 tools/figures/build.py architecture     # 只生成某几幅
python3 tools/figures/build.py --out /tmp/x     # 写到别处预览
pdftoppm -r 400 -png /tmp/x/architecture.pdf /tmp/x/architecture
```

依赖：`reportlab`、`matplotlib`、`fonttools`、Ghostscript（`gs`），以及带 `kpsewhich` 的 TeX Live（libertine、inconsolata、fandol 字体）；架构图的中文版另需 Noto Sans CJK SC。noctis 上都已具备，本机没有装 reportlab。生成的 PDF 是论文源文件，要提交到仓库，Overleaf 不运行 Python。

## 汇报用的三张图

`structure.py`、`definition.py`、`process.py` 是汇报 PPT 的三张核心图，不进论文，从三个视角讲同一个方法：图 1 系统架构（MAVRA 在 agent 与数据库之间，共享记忆与发布、使用、维护与优化三项职责），图 2 数据模型（指标定义 = 口径 + SQL + 从 SQL 结构推导的前提条件 + 版本号；三种日常写入下前提条件怎样识别有害的写入），图 3 生命周期（指标定义随数据变化的状态图：学习、发布前校验、有效、待校验、执行前校验、自动修复、回归测试、新版本、优化、指标失效）。用词用数据库、数仓行业的常用说法。每张图先用黑色文字讲机制本身，再用棕色“例”（`parts.example`）标出贯穿全场的门店营业额，数值取自实验记录（来源写在各脚本开头）。它们按幻灯片尺寸画（300 mm 宽，12–15 pt 字，共用部件在 `parts.py`，状态框用 `parts.state`），只出中文版（`LANGS = ('zh',)`），用标准的数据库术语，不用论文符号，也不写年份。`python3 tools/figures/build.py --deck` 写到 `tools/deck/figures/`，PPT 的生成见 `tools/deck/README.md`。

## 数据核对

- 图 2–4 直接读取 `exp/` 中的存档，不经过 `gen/` 的中间文件。图里每个数值按正文的格式化方式，与 `overleaf/gen/` 中正文引用的宏比较，不一致就报错停止：图 2 对 `review.tex` 的 `\Rp*` 与 `\Tr*`，图 3 对 `\Cb*`，图 4 对 `numbers.tex` 的 `\ScenAcc*`（各方法平均值与正文引用的情形）以及 `scen-ds.tex` 的 `\Ds*Modeled*`、`\Ds*Revoked`、`\Ds*Repaired`；图 4 每个（方法，情形）的合并正确率还要与 `paper-results.json` 里 `tools/paper-results.py` 算出的一致，保证两份存档说的是同一批运行。
- 图 4 的前身是逐情形热力图（2026-10-06 由表 7 改成），2026-10-07 改为每次运行一个小点的点图：热力图只有均值，看不出三次独立运行和离散程度；右面板的失效／修复数原来在表 4 里。
- 原图 1（定义共享条件）于 2026-10-07 删去：它说明的共享不是本文的贡献，§2.4 的正文保留其计数；脚本在 git 历史中（`tools/figures/sharing.py`）。
- 方法颜色从 `overleaf/latex/preamble.tex` 的 `\definecolor` 读取，与表格里的色块是同一组定义；方法名称与表 2 一致（`style.py` 的 `METHODS`）。

## 怎么画出来的

**底层函数**（`vecfig.py` 的 `Sheet`）：坐标单位是毫米，原点在图的左上角，按印刷尺寸画（单栏 84.6 mm，通栏 178 mm）。

```python
rect(x, y, w, h, fill, stroke, sw, r, dash)   # 矩形，r 为圆角
poly(points, fill, stroke, sw)                 # 多边形或折线，立体面用它画
line(x1, y1, x2, y2, stroke, sw, dash)         # 直线
curve(p0, p1, p2, p3, stroke, sw)              # 三次贝塞尔曲线
route(points, stroke, sw, heads, dash)         # 直角折线，拐角为圆角，heads='end'/'both'/None
marker(x, y, kind, size, fill, stroke)         # 数据点：circle / square / triangle / diamond
text(x, y, '文字 $数学$ `代码`', size, fill, style, align, width)
Scale(d0, d1, p0, p1)                          # 数据值到毫米的线性映射
```

**文字全部转成轮廓**，PDF 不嵌入字体，pdfLaTeX、XeLaTeX 和各种阅读器里显示都一样，也不会出现投稿系统拒收的 Type 3 字体：

- 普通文字用 fontTools 排版，字体与论文一致：Linux Biolinum（标签）、Inconsolata zi4（反引号里的代码，同 `\code`），按 GPOS 表做字距调整；中文落到 Noto Sans CJK SC。中文标签里不要用“……”（会取到西文省略号），写“等”。
- `$...$` 里的数学用 matplotlib 的 MathText 排版，字母用 Libertine（与正文的 newtxmath 一致），缺的符号用 STIX。数学和普通文字共用基线，一个标签里可以混排。
- `text(..., width=...)` 给出可用宽度时，标签超宽会直接报错，改布局不会悄悄把字挤出框。

**共享设置**（`style.py`）：颜色、方法名称、`gen/` 宏的读取与核对，以及 `build()`（每幅图写英文和中文两份）。架构图脚本提供 `NAME`、`W`、`H` 和 `draw(sheet, lang)`。

**数据图**（`mplstyle.py`）：数据图脚本提供 `NAME`、`W`、`H`（毫米）和 `figure(lang)`，返回一个 matplotlib Figure；`mplstyle.setup(lang)` 设置字体与 rcParams（标签 Linux Biolinum，中文回退到 FandolHei，字号下限同上），`mplstyle.save()` 先让 matplotlib 以 Type 3 轮廓写出 PDF，再用 Ghostscript `-dNoOutputFonts` 把所有字形转成路径，最终 PDF 同样不含字体。中文标签不能走 mathtext（其字体没有 CJK 字形），脚注角标用 `mplstyle.label_with_mark()` 单独画。

## 想改的话

| 想改什么 | 改哪里 |
| --- | --- |
| 某个标签的文字 | 各脚本里的 `LABELS` / `TEXT` 字典，`en` 与 `zh` 各一份 |
| 方法名称或颜色 | 名称在 `style.py` 的 `METHODS`；颜色改 `preamble.tex` 的 `\definecolor`，图和表一起变 |
| 架构图的模块位置 | `architecture.py` 顶部的 `ADM`、`STORE`、`MAINT` 等框，箭头按框的边自动对齐 |
| 数据图的方法与顺序 | `replay_outcomes.py` 的 `ROWS`，`maintenance_cost.py` 的 `SERIES`，`scenario_changes.py` 的 `ROWS`（9 种方法，按表 2 分组）与 `MAINTAINERS`（右侧每次运行的失效与修复数） |
| 结果矩阵的情形简称、分组与过期阈值 | `scenario_changes.py` 的 `TEXT`、`GROUP` 与 `STALE` |
| 图的尺寸 | 各脚本的 `W, H`（单栏图宽用 `style.COLUMN`） |

改完运行 `build.py`，再编译论文看效果。图里的含义变了，要同步改 `overleaf/figures/<名称>.tex` 里的图注和 `\Description`。实验数据更新后，先按 `overleaf/README.md` 重新生成 `gen/`，再重建图；核对不通过说明图和正文用的不是同一份数据。
