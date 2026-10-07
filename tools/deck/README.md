# 汇报 PPT

`build-deck.js` 生成 `docs/mavra-system.pptx`：10 页中文 PPT。前半用三张图讲 MAVRA 的结构、功能和工作流，后半用端到端实验的真实记录走一遍“门店营业额”这个例子；每页带讲稿备注。

| 页 | 内容 |
| --- | --- |
| 1 | 标题 |
| 2 | MAVRA 做三件事：学习指标定义、数据变了就重新校验、执行前把关 |
| 3 | 系统结构（`figures/overview-zh.png`） |
| 4 | 工作流①（`figures/lookup-zh.png`）：查询指标定义，再执行 SQL；校验结果缓存怎样复用 |
| 5 | 工作流②（`figures/lifecycle-zh.png`）：指标定义的学习、停用与修复 |
| 6 | 真实例子①：内置智能体学到“门店营业额”（学习题、SQL、存进指标库的定义） |
| 7 | 真实例子②：三种日常写入（追加、数据更正、重复装载）下“9 月门店营业额”的答案，对照组与 MAVRA |
| 8 | 真实例子③：数据更正之后 MAVRA 依次做了什么（系统记录原文与耗时） |
| 9 | 真实例子④：回归测试为什么用学习时的数据（对照实验：用当前数据会拒绝正确的修复） |
| 10 | 小结 |

例子页的数字都取自 noctis `results/scen-20261002/` 的存档：MAVRA 第 1 次运行 `dsv41flash-r1-g3fix--snap`，对照组 `dsv41flash-r{1,2,3}-g3fix--schema`（只在表结构变化时失效），回归测试对照 `dsv41flash-r1-g3fix--exref`。题目中的年份略去（合成数据的日期在 2000–2002 年）。

三张图由 `tools/figures/overview.py`、`lookup.py`、`lifecycle.py` 画成，按幻灯片尺寸设计（300 mm 宽，12–15 pt 字），用通用词汇：指标定义、指标库、校验规则、校验结果缓存、数据版本、快照、v1/v2、停用、回归测试，不用论文里的符号和自造词。改图后先在 noctis 上重画并转成 PNG，再在本机生成 PPT：

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
