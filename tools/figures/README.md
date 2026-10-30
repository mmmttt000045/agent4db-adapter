# 论文与汇报绘图

图形使用 ReportLab、fontTools 与 matplotlib 生成矢量 PDF；论文的中英文图作为编译输入保存在 `overleaf/figures/`，PPT 图保存在 `slides/figures/`。以下路径相对仓库根目录。

## 构建与依赖

```bash
python3 -m pip install -r tools/figures/requirements.txt
make figures                       # 包括群体、RelBench 累计和机制图
python3 tools/figures/build.py architecture  # 只画一幅
python3 tools/figures/mechanism.py  # A/B/C 中英文图及数值宏
python3 tools/figures/build.py --out /tmp/mavra-figures  # 主绘图器输出到预览目录
make deck-figures                  # PPT 的六幅图，生成 PDF 并转 PNG
```

数据图使用 Matplotlib 直接输出带嵌入字体的矢量 PDF，无需 TeX Live 或 Ghostscript。英文优先使用 Times New Roman，其次为 Liberation Serif、DejaVu Serif；中文需要系统安装 SimSun 或 Noto CJK 等字体。示意图仍需带 `kpsewhich` 的 TeX Live 及 libertine、inconsolata、fandol 字体，中文示意图使用 Noto Sans CJK SC。PDF 预览和 PPT 的 PNG 转换需要 Poppler 的 `pdftoppm`。Python 依赖清单用于建立绘图环境，未声明为历史实验环境锁文件。

论文编译直接使用已提交的 PDF，无需绘图环境。`make figures` 调用主绘图器、`population.py`、`relbench_cumulative.py` 和 `mechanism.py`；各自保留现有接口。

## 图形与数据来源

| 输出名（均有英文与 `-zh` 中文 PDF） | 脚本 | 数据或来源 |
| --- | --- | --- |
| `metric-record` | `metric_record.py` | 图 1 动机图：多个智能体通过不同的探针、顺序和回访路径重复发现重叠知识；成束请求与返回、共同表上的重复读取表现冗余负载。轨迹、包与路径数量均为示意 |
| `running-example` | `example.py` | 优化实验的学习、使用与修复轨迹，来源见脚本文件头 |
| `architecture` | `architecture.py` | 系统示意 |
| `replay-outcomes` | `replay_outcomes.py` | 验证缓存、TPC-DS 和通用性回放 |
| `maintenance-cost` | `maintenance_cost.py` | `exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json` |
| `scenario-changes` | `scenario_changes.py` | `exp/2026-10-10-scenarios-q5/` |
| `two-schemas` | `two_schemas.py` | 合成场景五轮与通用性 `e2e/` 的正确率 |
| `consumer-cost` | `consumer_cost.py` | 合成场景 `holdout-cost.json` 与通用性 `e2e/outcomes.json.gz` |
| `population` | `population.py` | `exp/2026-10-12-population/population-stats.json` |
| `relbench-cumulative` | `relbench_cumulative.py` | `exp/2026-10-20-relbench/paper-sessions.json` |
| `memory-access-pilot` | `mechanism.py` | `exp/2026-10-29-mechanism-pilot/pilot-summary.json`，八格开发预实验 |
| `fixed-sharing` | `mechanism.py` | 同批 `system-summary.json` 的 B，固定定义数的三轮共享对照 |
| `snapshot-control` | `mechanism.py` | 同批 `system-summary.json` 的 C，以及 10-02 批次的 `snapshot-binding-stats.json` / `snapshot-binding-shards-stats.json`；新因果对照与归档开销分开呈现 |

具体哪些图进入稿件，由 `overleaf/sections/` 和图形包装 `.tex` 的引用决定；不使用固定图号来标识脚本。`baselines.py` 是保留的辅助图，不包含在 `make figures` 中；早期外部记忆基线的采用范围以 RelBench 协议为准。

## 汇报图

`build.py --deck` 绘制 `structure`、`definition`、`process` 三张机制图，以及 `run-publish`、`run-use`、`run-maintain` 三张过程图，只生成中文版。共用组件在 `parts.py`、`deckparts.py`，配色在 `deckpal.py`。这些脚本和论文绘图共用工具，输出到 `slides/figures/`；PPT 生成与版本说明见 [slides/README.md](../../slides/README.md)。

## 数值核对

数据图读取 `exp/` 中的归档，并按各脚本的实现与 `overleaf/gen/` 宏交叉核对。场景题集、重复轮次和采用的运行必须一致；更新数据时先检查 [实验索引](../../exp/README.md) 和 [论文说明](../../overleaf/README.md)，再重算宏和图形。

方法颜色从 `overleaf/latex/preamble.tex` 读取；图注、标签与 `Description` 在各图对应的 `.tex` 中维护。单图尺寸以脚本内的 `W`、`H` 为准。

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

**示意图文字转成轮廓**，PDF 不嵌入字体，pdfLaTeX、XeLaTeX 和各种阅读器里显示都一样，也不会出现投稿系统拒收的 Type 3 字体：

- 普通文字用 fontTools 排版，字体与论文一致：Linux Biolinum（标签）、Inconsolata zi4（反引号里的代码，同 `\code`），按 GPOS 表做字距调整；中文落到 Noto Sans CJK SC。中文标签里不要用“……”（会取到西文省略号），写“等”。
- `$...$` 里的数学用 matplotlib 的 MathText 排版，字母用 Libertine（与正文的 newtxmath 一致），缺的符号用 STIX。数学和普通文字共用基线，一个标签里可以混排。
- `text(..., width=...)` 给出可用宽度时，标签超宽会直接报错，改布局不会悄悄把字挤出框。

**共享设置**（`style.py`）：颜色、方法名称、`gen/` 宏的读取与核对，以及 `build()`（每幅图写英文和中文两份）。架构图脚本提供 `NAME`、`W`、`H` 和 `draw(sheet, lang)`。

**数据图**（`mplstyle.py`）：数据图脚本提供 `NAME`、`W`、`H`（毫米）和 `figure(lang)`，返回一个 Matplotlib Figure；`mplstyle.setup(lang)` 设置衬线字体、白底、黑色完整坐标框、向内刻度与普通字重的图例。`mplstyle.save()` 直接保存矢量 PDF，以 `pdf.fonttype=42` 嵌入字体并保留可检索文字。字体大小按单图的印刷尺寸设置；标签通常为 7.5 pt，刻度 7 pt，紧凑图例和分类标签最低 6.5 pt。

## 想改的话

| 想改什么 | 改哪里 |
| --- | --- |
| 某个标签的文字 | 各脚本里的 `LABELS` / `TEXT` 字典，`en` 与 `zh` 各一份 |
| 方法名称或颜色 | 名称在 `style.py` 的 `METHODS`；颜色改 `preamble.tex` 的 `\definecolor`，图和表一起变 |
| 架构图的模块位置 | `architecture.py` 中的 `ADM`、`STORE`、`MAINT`、`LOOKUP`、`EXEC` 坐标；版式以 2026-10-07 最终版为基线，数据库标签固定为 `DataBase` |
| 数据图的方法与顺序 | `replay_outcomes.py` 的 `ROWS`，`maintenance_cost.py` 的 `SERIES`，`scenario_changes.py` 的 `ROWS`（9 种方法，按表 2 分组）与 `MAINTAINERS`（右侧每次运行的失效与修复数） |
| 结果矩阵的情形简称、分组与过期阈值 | `scenario_changes.py` 的 `TEXT`、`GROUP` 与 `STALE` |
| 图的尺寸 | 各脚本的 `W, H`（单栏图宽用 `style.COLUMN`） |

改完运行 `build.py`，再编译论文看效果。图里的含义变了，要同步改 `overleaf/figures/<名称>.tex` 里的图注和 `\Description`。实验数据更新后，先按 `overleaf/README.md` 重新生成 `gen/`，再重建图；核对不通过说明图和正文用的不是同一份数据。

## 当前正文实验图的样式

正文中的 `population`、`relbench-cumulative`、`consumer-cost` 和 `two-schemas` 使用常规折线图或分组柱状图。方法颜色沿用 `preamble.tex`，与表格一致；线型、空心标记、黑色柱框和纹理提供额外区分。图例文字统一为黑色、普通字重，各方法采用相同线宽，不单独加粗 MAVRA。

- 群体代价：三幅折线图，均值曲线加每个智能体位置的最小值--最大值误差线；每题 token 面板保留对数轴。正确率移至图注。
- RelBench 累计 token：每个数据库一幅折线图，用竖直虚线分隔截点，学习与复用阶段在图注解释。
- 留出查询代价：时间和 token 分成两个分组柱状图，柱高是合并全部问题后的均值，误差线覆盖各次运行的均值。
- 两种模式的正确率：作为维护边界的受控研究，仅保留无记忆与 MAVRA，按情形分组，从零起画；保留各次运行的最小值--最大值范围和原有情形等权汇总方式。自制示例检索不再进入当前稿件；原始归档保留。

2026-10-28 的官方 API 重构见 [实验协议](../../exp/2026-10-28-official/README.md)。新的 Fig.5 将解释智能体工具调用的组成，另用表格计入内部记忆开销；只有完整配对结果通过核对后才替换原 `consumer-cost`，不能将开发或未完成运行当作正式图表。

这些误差线表示运行范围，不是置信区间。图注和 `Description` 必须与图形一起更新；原始数据、宏核对以及统计汇总逻辑不因样式修改而变化。每幅图同时生成英文和中文版本，并以实际单栏或通栏尺寸检查文字、图例和留白。

## 2026-10-29 三幅机制图

`mechanism.py` 同时生成上述 A/B/C 的中英文矢量 PDF 及 `overleaf/gen/mechanism.tex`，来源哈希保存至 `exp/2026-10-29-mechanism-pilot/paper-integration/figure-sources.json`。A/B 为 84.6 mm 单栏图，C 为 178 mm 通栏图；图注在各自 `.tex` 中维护。所有标签不小于 6.5 pt。

论文版本去掉预览页的总标题与长脚注，把实验范围放入图注和正文；先前 `output/mechanism-pilot-20261029/` 的审阅图不覆盖。A 的缺失方案不画 AUC 零值、仍保留 token；B 的三轮误差线保留 96 次查询异常格；C 分开受控正确性与归档读写开销。数字与限制不因排版而改变。
