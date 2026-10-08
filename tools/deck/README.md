# 汇报 PPT

`build-deck.js` 生成 `docs/mavra-system.pptx`：10 页中文 PPT（用户要求控制在 10 页，不再加页），按一条主线讲 MAVRA：智能体学到的数据库知识共享出去后会因数据变化悄悄失效；MAVRA 作为共享记忆层承担三项职责——发布、依赖、维护与改进。全场用一个例子贯穿：门店营业额 v1（学到）→ v2（优化：日期键范围）→ v3（数据更正后修复）；修订（v）是同一条定义的第几版写法，口径不变，调用原文里的 revision: N 即 v(N+1)。每页带讲稿备注，备注里可以用账本、管理员、拍照片这类比喻，幻灯片正文用标准数据库术语并配一句通俗解释。

| 页 | 内容 |
| --- | --- |
| 1 | 标题 |
| 2 | Text-to-SQL 与 MAVRA：不同层次的问题；同一问题三次独立求解的记录（口径不在模式中） |
| 3 | 问题：示意账本（600 / 850 / 650 元）+ 实验真实记录（增量加载、数据更正、重复加载） |
| 4 | MAVRA：系统架构图（`figures/overview-zh.png`）+ 三项职责（发布 / 依赖 / 维护与改进）+ 工具与“声明”（run_sql 的 metrics 参数）+ 谁参与 |
| 5 | 一个例子贯穿全场：门店营业额 v1 / v2 / v3 的表（为什么会有它、SQL 写法、依赖的条件、9 月的结果）；三次变化各是什么；为什么要编号 |
| 6 | 发布：v1 怎么来的（求解、抽取、7 项准入、发布、知识卡）；四类条件与命题 1；准入拦下的一例（丢了类别过滤，1352.1 万对 274.1 万） |
| 7 | 依赖：用户智能体 B 的真实调用（声明 revision 1 = v2）；表版本 + 验证结果缓存；为什么要同一快照；并发实验 |
| 8 | 维护与改进：v1 → v2 的优化记录（候选、等价、更省、发布）与 v2 → v3 的修复记录（发现、搜索、唯一、回归、用时）；修不好时失效 |
| 9 | 实验结果：端到端表（6 种方法）+ 系统层四条 + 共享与回本、维护、负结果 |
| 10 | 保证边界（能做什么 / 做不到什么）与三句话总结（问题 / 方法 / 结果） |

第 3 页的小账本和第 7 页的 10:00 时刻为示意，页脚注明；其余数字来自存档记录或论文宏。

第 6–8 页的调用记录来自 noctis `results/scen-20261008-trace/`（`metric-bench --trace`，仅 M1 与数据更正，本目录副本 `exp/2026-10-08-optimize/trace/`）。例子页的数字都取自 noctis `results/scen-20261002/` 的存档：MAVRA 第 1 次运行 `dsv41flash-r1-g3fix--snap`（第 2 页用 r1–r3），对照组 `dsv41flash-r{1,2,3}-g3fix--schema`（只在表结构变化时失效），不共享指标定义的智能体 `dsv41flash-r1-a`、`r2-b`、`r3-a`（`middle`），回归测试对照 `dsv41flash-r1-g3fix--exref`。第 9 页的端到端准确率与 `overleaf/gen/scen-ds.tex` 的 `\Ds*` 宏一致，系统层数字与 `\Rp*`、`\Tr*`、`\Sn*`、`\CbStag*` 宏一致（`exp/2026-10-02-cache-baseline-tpcds`、快照压力测试、`exp/2026-10-03-session-latency`）。题目中的年份略去（合成数据的日期在 2000–2002 年）。

PPT 现在只用架构图 `overview-zh.png`（第 4 页）；`lookup.py`、`lifecycle.py` 两张图保留在 `figures/` 里，10 页版本不再使用。三张图都由 `tools/figures/` 画成，按幻灯片尺寸设计（300 mm 宽，12–15 pt 字），用标准的数据库术语：指标定义、共享记忆、验证条件、验证结果缓存、表版本、快照、修订 v1/v2、失效、准入检查、修复搜索、谓词、回归测试，不用论文里的符号、自造词或口语化说法。改图后先在 noctis 上重画并转成 PNG，再在本机生成 PPT：

```bash
# noctis，仓库根目录
python3 tools/figures/build.py --deck
cd tools/deck/figures && for f in *.pdf; do pdftoppm -r 300 -png -singlefile $f ${f%.pdf}; done

# 本机（把 tools/deck/figures 取回后）
cd tools/deck
npm ci          # 只需一次，pptxgenjs 4.0.1
npm run build   # 写 docs/mavra-system.pptx；或 node build-deck.js --out 其他路径
```

图中数值取自同一次运行：学习题 3 月门店营业额 1357.0 万；数据更正后 9 月 1293.3 万（不处理时 1430.1 万）。字体为 Microsoft YaHei；在 Linux 上用 LibreOffice 预览时由 Noto Sans CJK SC 代替。
