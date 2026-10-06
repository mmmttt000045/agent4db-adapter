# 论文矢量图生成器

论文的四幅图都由这里的 Python 脚本直接画成矢量 PDF，不经过 TikZ、pgfplots、Visio 或 PPT：

| 图 | 脚本 | 输出（`overleaf/figures/`） | 数据 |
| --- | --- | --- | --- |
| 图 1 定义共享条件 | `sharing.py` | `sharing.pdf` | 受控负载的结构（写在脚本里，计数与图注核对） |
| 图 2 系统架构 | `architecture.py` | `architecture.pdf` | 无 |
| 图 3 维护代价 | `maintenance_cost.py` | `maintenance-cost.pdf` | `exp/2026-10-02-cache-baseline-tpcds/cb-1m-share-stats.json` |
| 图 4 场景正确率 | `scenario_groups.py` | `scenario-groups.pdf` | `exp/2026-10-02-scenarios-ds/scen-stats.json` |

每幅图生成两份：`<名称>.pdf` 用于英文稿（`main-en.tex`），`<名称>-zh.pdf` 用于双语稿（`main.tex`），标签为中文。`overleaf/figures/<名称>.tex` 按 `\ifbilingual` 选用其中一份，标题、标签和 `\Description` 仍写在 tex 文件里。

```bash
python3 tools/figures/build.py                  # 全部，写入 overleaf/figures/
python3 tools/figures/build.py sharing          # 只生成某几幅
python3 tools/figures/build.py --out /tmp/x     # 写到别处预览
pdftoppm -r 400 -png /tmp/x/sharing.pdf /tmp/x/sharing
```

依赖：`reportlab`、`matplotlib`、`fonttools`，以及带 `kpsewhich` 的 TeX Live（libertine、inconsolata 字体）；中文版另需 Noto Sans CJK SC。noctis 上都已具备，本机没有装 reportlab。生成的 PDF 是论文源文件，要提交到仓库，Overleaf 不运行 Python。

## 数据核对

- 图 3、图 4 直接读取 `exp/` 中的存档，不经过 `gen/` 的中间文件。图里每个数值按正文的格式化方式，与 `overleaf/gen/review.tex`（`\Cb*`）和 `scen-ds.tex`（`\Ds*`）中正文引用的宏比较，不一致就报错停止。
- 图 1 的 19 个定义、41 个条件实例、7 个条件、8 个待验证定义、19 次与 3 次检查，都由脚本里的结构算出，并与图注写的数比较。
- 方法颜色从 `overleaf/latex/preamble.tex` 的 `\definecolor` 读取，与表格里的色块是同一组定义；方法名称与表 3 一致（`style.py` 的 `METHODS`）。

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

**共享设置**（`style.py`）：颜色、方法名称、`gen/` 宏的读取与核对，以及 `build()`（每幅图写英文和中文两份）。每个图脚本只需提供 `NAME`、`W`、`H` 和 `draw(sheet, lang)`。

## 想改的话

| 想改什么 | 改哪里 |
| --- | --- |
| 某个标签的文字 | 各脚本里的 `LABELS` / `TEXT` 字典，`en` 与 `zh` 各一份 |
| 方法名称或颜色 | 名称在 `style.py` 的 `METHODS`；颜色改 `preamble.tex` 的 `\definecolor`，图和表一起变 |
| 架构图的模块位置 | `architecture.py` 顶部的 `ADM`、`STORE`、`MAINT` 等框，箭头按框的边自动对齐 |
| 图 1 的定义族与条件 | `sharing.py` 的 `FAMILIES` 与 `CONDITIONS` |
| 图 3、图 4 的方法与顺序 | `maintenance_cost.py` 的 `SERIES`，`scenario_groups.py` 的 `ROWS` 与 `GROUPS` |
| 图的尺寸 | 各脚本的 `W, H`（单栏图宽用 `style.COLUMN`） |

改完运行 `build.py`，再编译论文看效果。图里的含义变了，要同步改 `overleaf/figures/<名称>.tex` 里的图注和 `\Description`。实验数据更新后，先按 `overleaf/README.md` 重新生成 `gen/`，再重建图；核对不通过说明图和正文用的不是同一份数据。
