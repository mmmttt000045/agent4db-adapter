# 论文与汇报绘图

图形使用 ReportLab、fontTools 与 matplotlib 生成矢量 PDF；论文的中英文图作为编译输入保存在 `overleaf/figures/`，PPT 图保存在 `slides/figures/`。以下路径相对仓库根目录。

## 构建与依赖

```bash
python3 -m pip install -r tools/figures/requirements.txt
make figures                       # 包括群体图和 RelBench 累计图
python3 tools/figures/build.py architecture  # 只画一幅
python3 tools/figures/build.py --out /tmp/mavra-figures  # 主绘图器输出到预览目录
make deck-figures                  # PPT 的六幅图，生成 PDF 并转 PNG
```

系统依赖：Ghostscript（`gs`）、带 `kpsewhich` 的 TeX Live 及 libertine、inconsolata、fandol 字体；中文图还需 Noto Sans CJK SC；PPT 的 PNG 转换需要 Poppler 的 `pdftoppm`。Python 依赖清单用于建立绘图环境，未声明为历史实验环境锁文件。

论文编译直接使用已提交的 PDF，无需绘图环境。`make figures` 调用主绘图器、`population.py` 和 `relbench_cumulative.py`；后两者保留各自现有接口。

## 图形与数据来源

| 输出名（均有英文与 `-zh` 中文 PDF） | 脚本 | 数据或来源 |
| --- | --- | --- |
| `metric-record` | `metric_record.py` | 图 1 贯穿示例：一条指标记录的学习、复用、失效与修复，示意内容无实验数据 |
| `running-example` | `example.py` | 优化实验的学习、使用与修复轨迹，来源见脚本文件头 |
| `architecture` | `architecture.py` | 系统示意 |
| `replay-outcomes` | `replay_outcomes.py` | 验证缓存、TPC-DS 和通用性回放 |
| `maintenance-cost` | `maintenance_cost.py` | `exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json` |
| `scenario-changes` | `scenario_changes.py` | `exp/2026-10-10-scenarios-q5/` |
| `two-schemas` | `two_schemas.py` | 合成场景五轮与通用性 `e2e/` 的正确率 |
| `consumer-cost` | `consumer_cost.py` | 合成场景 `holdout-cost.json` 与通用性 `e2e/outcomes.json.gz` |
| `population` | `population.py` | `exp/2026-10-12-population/population-stats.json` |
| `relbench-cumulative` | `relbench_cumulative.py` | `exp/2026-10-20-relbench/paper-sessions.json` |

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
| 架构图的模块位置 | `architecture.py` 中的 `ADM`、`STORE`、`MAINT`、`LOOKUP`、`EXEC` 坐标；版式以 2026-10-07 最终版为基线，数据库标签固定为 `DataBase` |
| 数据图的方法与顺序 | `replay_outcomes.py` 的 `ROWS`，`maintenance_cost.py` 的 `SERIES`，`scenario_changes.py` 的 `ROWS`（9 种方法，按表 2 分组）与 `MAINTAINERS`（右侧每次运行的失效与修复数） |
| 结果矩阵的情形简称、分组与过期阈值 | `scenario_changes.py` 的 `TEXT`、`GROUP` 与 `STALE` |
| 图的尺寸 | 各脚本的 `W, H`（单栏图宽用 `style.COLUMN`） |

改完运行 `build.py`，再编译论文看效果。图里的含义变了，要同步改 `overleaf/figures/<名称>.tex` 里的图注和 `\Description`。实验数据更新后，先按 `overleaf/README.md` 重新生成 `gen/`，再重建图；核对不通过说明图和正文用的不是同一份数据。

## 实验图的配色（图 3–7，2026-10-11 起）
方法颜色取 Nature（NPG）配色的色相，按色觉与对比度校验调深或调饱和（dataviz 的 validate_palette 逐图检查相邻颜色）：
MAVRA 藏青 `#2F4F9F`，其消融（回归测试用当前数据）浅蓝 `#5F86D6`；示例检索 青绿 `#00A087`；无记忆 棕 `#9C5A26`；
模式变更时失效 珊瑚 `#E3643A`；每次写入即失效 青蓝 `#1F8FB0`；dbt 式表级测试 紫 `#8E5BB0`；只重查变化的表 赭 `#A9740A`；
整定义重查 浅灰 `#B8B8B8`（参照线，带直接标注）、整定义重查 + 查询缓存 深灰 `#3A3A3A`。颜色定义在 `overleaf/latex/preamble.tex`，
`style.method()` 读取。非方法颜色在 `style.py`：答错与过期定义一律深红 `WRONG`，强调区域（MAVRA 所在行、底色组）一律浅藏青 `FOCUS`，
其余结果用中性灰。图 5 的正确率底色是一种藏青色阶（`#F7F8FC`→`#4F6CB5`），过期仍用深红框，MAVRA 行用藏青框。点线图的标记按方法固定：MAVRA 圆、示例检索 方、无记忆 正三角、只重查变化的表 倒三角、查询缓存 空心菱形；
图例里 MAVRA 一律加粗、用藏青。示意图（图 1、2）保留自己的颜色（`ACC` 等常量），不随方法颜色变化。
