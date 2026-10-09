# 汇报 PPT

`build-deck.js` 生成 `docs/mavra-system.pptx`：8 页中文 PPT，面向没接触过这个领域的听众（用户要求不超过 10 页，不要复杂）。先讲清楚“我们在做什么”，再讲方法：方法从三个角度各用一张图讲，每张图先讲抽象的机制，再用绿色“例”标出贯穿全场的例子门店营业额。术语先解释再使用，幻灯片正文用标准数据库术语，比喻和细节放在讲稿备注里。

| 页 | 内容 |
| --- | --- |
| 1 | 标题：MAVRA：面向数据 agent 的可维护共享记忆；全称 Metric-Aware Validation and Reuse for Agents |
| 2 | 我们在做什么：数据 agent 与口径；没有共享（三次独立求解两次选错列，新题 49%）对比共享定义（三次一致、5 → 3 轮，新题 100%，快 8.9 倍）；难点（数据在写入，定义悄悄变错）与 MAVRA 一句话；和 Text-to-SQL 不在同一层 |
| 3 | 难点：示意账本（600 / 850 / 650 元）+ 实验记录（三种日常写入：增量加载、数据更正、重复加载，都问 9 月）；“定义没错，错的是默认的前提”，所以要把前提写成可检查的条件 |
| 4 | 角度一 · 结构（`figures/structure-zh.png`）：内置 agent 学一次、用户 agent 用很多次；MAVRA 共享记忆层里的共享记忆与三项职责（发布：准入检查；依赖：使用前在快照上验证；维护与改进）；数据库、表版本与快照 |
| 5 | 角度二 · 对象（`figures/definition-zh.png`）：条件从写法的结构推出（求和 → 粒度键唯一，连接 → 日期键唯一，内连接 → 日期键完整性，日期键范围 → 日期键按月连续）；三种写入下条件的结论与沿用写法的答案（同一个 2613.9 万一对一错，只有粒度键唯一能分辨） |
| 6 | 角度三 · 过程（`figures/process-zh.png`）：状态图——学习、准入检查发布、有效、待验证、使用时验证；成立则继续使用；不成立则修复搜索、回归测试、发布新修订；无唯一修复则定义失效、重新学习；改进发布等价且更快的新修订 |
| 7 | 实验结果：三个数（共享快 8.9 倍；破坏性写入后 73%；条件能发现的写入 0 错答、并发 0 次误答）+ 端到端表（5 种方法）+ 还做不到的 |
| 8 | 总结：问题 / 方法 / 结果三句话；能做到与做不到 |

第 3 页的小账本为示意，页脚注明；其余数字来自存档记录或论文宏。页脚只写“示意 / 实验记录（来源见备注）”，记录路径、运行 ID 和论文宏写在每页讲稿备注的最后一行“来源：”。

数字来源：第 2 页三次独立求解来自 noctis `results/scen-20261002/`（没有共享定义 `dsv41flash-r1-a`、`r2-b`、`r3-a`；MAVRA `dsv41flash-r1–r3-g3fix--snap`），新题正确率与轮数为 `\Ds*` 宏，耗时与 token 为 `tools/sharing-stats.py`（`\AmHold*`）。第 3 页与第 5 页沿用定义的答案来自 `dsv41flash-r1-g3fix--schema`（只在表结构变化时失效）。第 5、6 页的条件结论、修复、改进计时与 9 月答案来自优化轮 `results/scen-20261008-opt/metric-1791439498065570`（`metric-global-opt`，增量加载 = append、数据更正 = revision、重复加载 = dupload 三个阶段的 maintenance / revoked / repair_* 事件），学习过程来自 `results/scen-20261008-trace/`（本目录副本 `exp/2026-10-08-optimize/trace/`）。第 7 页的端到端准确率与 `overleaf/gen/scen-ds.tex` 的 `\Ds*` 宏一致（MAVRA = `metric-global-snap`，消融 = `metric-global-def`，见 `exp/2026-10-02-scenarios-ds/scen-stats.json`），系统层数字与 `\Rp*`、`\Sn*` 宏一致。题目中的年份略去（合成数据的日期在 2000–2002 年）。

三张图由 `tools/figures/` 画成（`structure.py`、`definition.py`、`process.py`，共用部件在 `parts.py`），按幻灯片尺寸设计（300 mm 宽，12–15 pt 字），只出中文版。改图后先在 noctis 上重画并转成 PNG，再在本机生成 PPT：

```bash
# noctis，仓库根目录
python3 tools/figures/build.py --deck
cd tools/deck/figures && for f in *.pdf; do pdftoppm -r 300 -png -singlefile $f ${f%.pdf}; done

# 本机（把 tools/deck/figures 取回后）
cd tools/deck
npm ci          # 只需一次，pptxgenjs 4.0.1
npm run build   # 写 docs/mavra-system.pptx；或 node build-deck.js --out 其他路径
```

字体为 Microsoft YaHei；在 Linux 上用 LibreOffice 预览时由 Noto Sans CJK SC 代替。
