# 汇报 PPT

现有两个汇报文件保存在 [versions/](versions/README.md)，来源与迁移校验值见其说明。生成器输出到 `slides/build/`，与保存的版本分开。以下文件路径除特别说明外均相对仓库根目录。

```bash
# 在仓库根目录
make slides-deps   # 首次安装依赖；等价于 npm --prefix slides ci
make slides        # 使用已有 PNG；等价于 npm --prefix slides run build
make deck-figures  # 修改绘图源码后重画，需要 Python 绘图依赖和 pdftoppm
```

`build-deck.js` 生成 `slides/build/mavra-system.pptx`：17 页中文 PPT，面向没接触过这个领域的听众。每页只讲一件事、一两分钟讲完：页面上只放关键词、数字和图，讲解由汇报人口头完成，完整讲稿在每页的讲稿备注里。先讲清楚“我们在做什么”，再用一个贯穿示例（用户 agent 问“9 月门店营业额是多少？”）说明请求如何处理；方法从三个视角各用一张图讲，每张图之后用同一个示例逐步讲一遍。图上有编号引导阅读顺序（系统架构 1–9：发布 1–2、使用 3–6、写入后的维护与优化 7–9；数据模型 1–7；生命周期 1–10），示例页的表格按同样的编号标注；示例页右上角有棕色“例”标签。配色为 Nature（NPG）科研配色，三张图与幻灯片一致（`tools/figures/deckpal.py`）：发布绿 #00A087、使用藏青 #3C5488、维护与优化青 #4DBBD5（图中加深一档）、待校验橙粉 #F39B7F、失效红 #E64B35、示例棕 #7E6148。用词用数据库、数仓行业的常用说法（SQL、前提条件、版本、校验、发布前校验、执行前校验、自动修复、过滤条件、主键唯一、维表主键唯一、参照完整性、拉链表、静默失效）。

| 页 | 内容 |
| --- | --- |
| 1 | 标题：MAVRA：面向数据 agent 的可维护共享记忆；全称 Metric-Aware Validation and Reuse for Agents |
| 2 | 共享 agent 学到的指标定义：无共享三次求解两次选错列、新题 49%；共享后三次一致、新题 100%、提速 2.5–8.9 倍（两轮实验） |
| 3 | 难点：示意账本（600 / 850 / 650 元），错的是 SQL 默认的前提“每个订单只有一行” |
| 4 | MAVRA 是什么：与 Text-to-SQL 对比（处理对象、产出、状态），两者互补 |
| 5 | 贯穿示例：用户 agent B 问 9 月门店营业额；find_metric → run_sql 声明 v2 → MAVRA 校验后执行 → 2613.9 万 |
| 6 | 同一请求、三种写入：沿用原定义 2613.9 ✓ / 1430.1 ✗ / 2613.9 ✗；MAVRA 照常使用 / 修复为 v3 / 指标失效并通知 |
| 7 | 视角一 · 系统架构（`figures/structure-zh.png`） |
| 8 | 视角一 · 例：增量加载后这个请求的步骤，按图中编号（①② 此前发布、⑦ 写入、③ find_metric、⑧ 只校验 2 个前提 5.5 秒、⑨ v2 有效、③ run_sql、④⑤ 同一快照核对并执行 29 毫秒、⑥ 结果） |
| 9 | 视角二 · 数据模型（`figures/definition-zh.png`） |
| 10 | 视角二 · 例：门店营业额 v2 的 SQL 与 4 个前提（校验什么、学习时的基准值） |
| 11 | 视角三 · 生命周期（`figures/process-zh.png`） |
| 12 | 视角三 · 例：数据更正后 ⑤–⑨：主键唯一不通过 → 唯一可行过滤 ss_is_current = '1' → 回归测试 3 月 1357.0 万 → 发布 v3 → 1293.3 万 |
| 13 | 视角三 · 例：重复加载后 ⑤⑥⑦⑩：主键唯一不通过 → 重复行完全相同、无法修复 → 指标失效并通知 → B 自行探索 |
| 14 | 实验结果 · 准确率：5 种方法在数据不变、11 类写入后、破坏性写入后 |
| 15 | 实验结果 · 正确性：前提可检测的写入 0 个错误结果；并发写入下 0 次违反前提的执行 |
| 16 | 边界：能做到与做不到 |
| 17 | 总结：问题 / 方法 / 结果 |

第 3 页的小账本为示意，页脚注明；其余数字来自存档记录或论文宏。页脚只写“示意 / 实验记录（来源见备注）”，记录路径、运行 ID 和论文宏写在每页讲稿备注的最后一行“来源：”。

数字来源：第 2 页三次独立求解来自 noctis `results/scen-20261002/`（没有共享定义 `dsv41flash-r1-a`、`r2-b`、`r3-a`；MAVRA `dsv41flash-r1–r3-g3fix--snap`），新题正确率与轮数为 `\Ds*` 宏，耗时与 token 为 `tools/sharing-stats.py`（`\AmHold*`）。第 6、9 页沿用定义的答案来自 `dsv41flash-r1-g3fix--schema`（只在表结构变化时失效）。示例页（第 5、6、8、10、12、13 页）与图中“例”的条件结论、修复、优化计时、请求记录与 9 月答案来自优化轮 `results/scen-20261008-opt/metric-1791439498065570`（`metric-global-opt`，增量加载 = append、数据更正 = revision、重复加载 = dupload 三个阶段的 maintenance / revoked / repair_* 事件与 M1-P1 的 records），学习过程来自 `results/scen-20261008-trace/`（本目录副本 `exp/2026-10-08-optimize/trace/`）。第 14 页的端到端准确率与 `overleaf/gen/scen-ds.tex` 的 `\Ds*` 宏一致（MAVRA = `metric-global-snap`，消融 = `metric-global-def`，见 `exp/2026-10-02-scenarios-ds/scen-stats.json`），第 15 页的系统层数字与 `\Rp*`、`\Sn*` 宏一致。题目中的年份略去（合成数据的日期在 2000–2002 年）。

三张图由 `tools/figures/` 画成（`structure.py`、`definition.py`、`process.py`，共用部件在 `parts.py`），按幻灯片尺寸设计（300 mm 宽，12–15 pt 字），只出中文版。改图后先在 noctis 上重画并转成 PNG，再在本机生成 PPT：

```bash
# noctis，仓库根目录
make deck-figures  # 同时生成 PDF 并转换为 PNG

# 本机，仓库根目录（把 slides/figures 取回后）
npm --prefix slides ci          # 首次安装，pptxgenjs 4.0.1
npm --prefix slides run build   # 写 slides/build/mavra-system.pptx
# 自定义输出：node slides/build-deck.js --out /tmp/mavra-preview.pptx
```

字体为 Microsoft YaHei；在 Linux 上用 LibreOffice 预览时由 Noto Sans CJK SC 代替。
