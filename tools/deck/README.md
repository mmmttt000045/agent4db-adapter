# 汇报 PPT

`build-deck.js` 生成 `docs/mavra-system.pptx`：12 页中文 PPT，把 MAVRA 讲成数据智能体与数据库之间的记忆中间件：与 Text-to-SQL 的区别、问题、架构、记忆的内容与管理方式、一个真实例子，最后两页是实验结果；每页带讲稿备注。

| 页 | 内容 |
| --- | --- |
| 1 | 标题 |
| 2 | Text-to-SQL 与 MAVRA：不同层次的问题 |
| 3 | 问题：业务口径不在模式中（同一问题三次独立求解的记录）；共享之后，三种更新使定义失效（对照组） |
| 4 | 系统架构：请求路径（`figures/overview-zh.png`） |
| 5 | 记忆的内容与接口：四类记忆、对应的工具、数据更新后的处理、来源与附带信息 |
| 6 | 记忆管理的五个环节：写入、读取、使用、维护、迭代 |
| 7 | 写入：学习任务、写入记忆的定义、7 项准入检查，“答案判定正确”在部署中的来源 |
| 8 | 读取与使用（`figures/lookup-zh.png`） |
| 9 | 维护与迭代（`figures/lifecycle-zh.png`）+ 修订规则 |
| 10 | 回到例子：三种更新加上 MAVRA 一栏；数据更正后的处理过程；回归测试为何以学习时刻为基准 |
| 11 | 实验结果①：端到端（7 种方法 × 数据未变 / 11 种更新 / 5 种破坏性更新 / 单位变化 / 备份副本） |
| 12 | 实验结果②：系统层（配对回放合成与 TPC-DS、同快照验证、修复的回归基准、维护成本） |

例子页的数字都取自 noctis `results/scen-20261002/` 的存档：MAVRA 第 1 次运行 `dsv41flash-r1-g3fix--snap`（第 3 页用 r1–r3），对照组 `dsv41flash-r{1,2,3}-g3fix--schema`（只在表结构变化时失效），不共享指标定义的智能体 `dsv41flash-r1-a`、`r2-b`、`r3-a`（`middle`），回归测试对照 `dsv41flash-r1-g3fix--exref`。第 11 页的准确率与 `overleaf/gen/scen-ds.tex` 的 `\Ds*` 宏一致；第 12 页与 `\Rp*`、`\Tr*`、`\Sn*`、`\CbStag*` 宏一致（`exp/2026-10-02-cache-baseline-tpcds`、快照压力测试、`exp/2026-10-03-session-latency`）。题目中的年份略去（合成数据的日期在 2000–2002 年）。

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
