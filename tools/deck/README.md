# 汇报 PPT

`build-deck.js` 生成 `docs/mavra-system.pptx`：18 页中文 PPT，把 MAVRA 讲成数据智能体与数据库之间的记忆中间件。先讲它和 Text-to-SQL 的区别，再讲记忆里存什么、记忆怎么写入、读取、使用、维护和迭代，最后用端到端实验里的一个真实例子走一遍；每页带讲稿备注。

| 页 | 内容 |
| --- | --- |
| 1 | 标题 |
| 2 | Text-to-SQL 和 MAVRA 解决的不是同一个问题（翻译一句话 vs. 管理智能体学到的知识；两者是上下游） |
| 3 | 真实记录：不共享记忆，“9 月门店营业额”问三次，两次选错列；有 MAVRA 三次都对、轮数更少 |
| 4 | 记住了还不够：三种日常写入（追加、数据更正、重复装载）之后照旧用记住的定义（对照组） |
| 5 | MAVRA 是什么：智能体调用的工具，以及每个工具背后的记忆管理 |
| 6 | 系统结构（`figures/overview-zh.png`） |
| 7 | 记忆里存什么：表画像、关联路径、指标定义、校验结果 |
| 8 | 一条指标定义记忆的全部内容（实验记录原样） |
| 9 | 记忆管理的五个环节：写入、读取、使用、维护、迭代 |
| 10 | 写入：学习题、7 项发布前校验；“答案核验正确”在部署中由谁做 |
| 11 | 读取与使用（`figures/lookup-zh.png`） |
| 12 | 维护与迭代（`figures/lifecycle-zh.png`） |
| 13 | 迭代：记忆的版本怎么变（佐证、并存、修复为新版本、复用修复、停用并提醒、重新学习） |
| 14 | 回到例子：同样三种写入，加上 MAVRA 一栏 |
| 15 | 数据更正之后 MAVRA 依次做了什么（系统记录原文与耗时） |
| 16 | 回归测试为什么用学习时的数据（对照实验：用当前数据会拒绝正确的修复） |
| 17 | 和已有做法比：Text-to-SQL、检索历史 SQL 示例、语义层、MAVRA |
| 18 | 小结 |

例子页的数字都取自 noctis `results/scen-20261002/` 的存档：MAVRA 第 1 次运行 `dsv41flash-r1-g3fix--snap`（第 3 页用 r1–r3），对照组 `dsv41flash-r{1,2,3}-g3fix--schema`（只在表结构变化时失效），不共享指标定义的智能体 `dsv41flash-r1-a`、`r2-b`、`r3-a`（`middle`），回归测试对照 `dsv41flash-r1-g3fix--exref`。第 17 页的准确率与 `overleaf/gen/scen-ds.tex` 的 `\Ds*` 宏一致。题目中的年份略去（合成数据的日期在 2000–2002 年）。

三张图由 `tools/figures/overview.py`、`lookup.py`、`lifecycle.py` 画成，按幻灯片尺寸设计（300 mm 宽，12–15 pt 字），用标准的数据库术语：指标定义、共享记忆、验证条件、验证结果缓存、表版本、快照、修订 v1/v2、失效、准入检查、修复搜索、谓词、回归测试，不用论文里的符号、自造词或口语化说法。改图后先在 noctis 上重画并转成 PNG，再在本机生成 PPT：

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
