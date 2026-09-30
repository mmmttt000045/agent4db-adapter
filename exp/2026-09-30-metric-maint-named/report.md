# 指标经验评测

查询 Agent：`openai-compatible:deepseek-flash`；提炼器：`openai-compatible:deepseek-flash`；温度：未设置（服务端默认）。数据：`{"catalog_sales":500000,"date_dim":1096,"item":1000,"store_returns":395878,"store_sales":1000000}`。

本报告是单次运行的描述性结果，不作显著性声明。协议见 docs/metric-experience-protocol.md。

## 1. 答案

两种题面分开报告。请求澄清单独计数，不算正确也不算错误；出错指模型或网络调用失败。

### 题面：不带口径

| 组 | 阶段 | 题集 | 题数 | 正确 | 错误 | 请求澄清 | 出错 |
|---|---|---|---|---|---|---|---|
| metric-global | 留出 | 参数留出 | 3 | 3 | 0 | 0 | 0 |
| metric-global | 留出 | 题型留出 | 6 | 6 | 0 | 0 | 0 |
| metric-global | 正常新增后 | 参数留出 | 2 | 2 | 0 | 0 | 0 |
| metric-global | 正常新增后 | 题型留出 | 4 | 4 | 0 | 0 | 0 |
| metric-global | ETL v2 后 | 参数留出 | 2 | 2 | 0 | 0 | 0 |
| metric-global | ETL v2 后 | 题型留出 | 4 | 4 | 0 | 0 | 0 |
| metric-global-def | 留出 | 参数留出 | 3 | 3 | 0 | 0 | 0 |
| metric-global-def | 留出 | 题型留出 | 6 | 6 | 0 | 0 | 0 |
| metric-global-def | 正常新增后 | 参数留出 | 2 | 2 | 0 | 0 | 0 |
| metric-global-def | 正常新增后 | 题型留出 | 4 | 4 | 0 | 0 | 0 |
| metric-global-def | ETL v2 后 | 参数留出 | 2 | 2 | 0 | 0 | 0 |
| metric-global-def | ETL v2 后 | 题型留出 | 4 | 4 | 0 | 0 | 0 |
| metric-global-schema | 留出 | 参数留出 | 3 | 3 | 0 | 0 | 0 |
| metric-global-schema | 留出 | 题型留出 | 6 | 6 | 0 | 0 | 0 |
| metric-global-schema | 正常新增后 | 参数留出 | 2 | 2 | 0 | 0 | 0 |
| metric-global-schema | 正常新增后 | 题型留出 | 4 | 4 | 0 | 0 | 0 |
| metric-global-schema | ETL v2 后 | 参数留出 | 2 | 1 | 1 | 0 | 0 |
| metric-global-schema | ETL v2 后 | 题型留出 | 4 | 2 | 2 | 0 | 0 |
| metric-global-revoke | 留出 | 参数留出 | 3 | 3 | 0 | 0 | 0 |
| metric-global-revoke | 留出 | 题型留出 | 6 | 6 | 0 | 0 | 0 |
| metric-global-revoke | 正常新增后 | 参数留出 | 2 | 2 | 0 | 0 | 0 |
| metric-global-revoke | 正常新增后 | 题型留出 | 4 | 4 | 0 | 0 | 0 |
| metric-global-revoke | ETL v2 后 | 参数留出 | 2 | 2 | 0 | 0 | 0 |
| metric-global-revoke | ETL v2 后 | 题型留出 | 4 | 4 | 0 | 0 | 0 |
| metric-global-noguard | 留出 | 参数留出 | 3 | 2 | 1 | 0 | 0 |
| metric-global-noguard | 留出 | 题型留出 | 6 | 5 | 1 | 0 | 0 |
| metric-global-noguard | 正常新增后 | 参数留出 | 2 | 1 | 1 | 0 | 0 |
| metric-global-noguard | 正常新增后 | 题型留出 | 4 | 3 | 1 | 0 | 0 |
| metric-global-noguard | ETL v2 后 | 参数留出 | 2 | 0 | 2 | 0 | 0 |
| metric-global-noguard | ETL v2 后 | 题型留出 | 4 | 1 | 3 | 0 | 0 |

## 2. 效率（留出阶段，出错除外）

数据库一栏是任务期间中间层的全部查询；最终 SQL 一栏是参与答案的 SQL 的 EXPLAIN 结果，事后执行。

| 题面 | 组 | 题数 | LLM 轮数 | 工具调用 | 输入 token | 输出 token | 墙钟 s | DB 查询 | DB ms | 最终 SQL ms | 最终 SQL 缓冲块 | 事实表扫描节点 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 不带口径 | metric-global | 9 | 4.6 | 7.0 | 20487.6 | 3468.4 | 16.2 | 4.9 | 935.5 | 532.2 | 11113.1 | 1.8 |
| 不带口径 | metric-global-def | 9 | 4.8 | 7.0 | 16306.0 | 2541.9 | 11.5 | 4.8 | 434.6 | 331.6 | 21951.0 | 1.7 |
| 不带口径 | metric-global-schema | 9 | 4.3 | 6.8 | 16521.9 | 2489.6 | 11.1 | 4.8 | 195.2 | 122.4 | 40881.1 | 1.8 |
| 不带口径 | metric-global-revoke | 9 | 4.1 | 6.0 | 12270.7 | 2307.0 | 10.2 | 4.0 | 257.6 | 123.0 | 19707.7 | 1.6 |
| 不带口径 | metric-global-noguard | 9 | 6.2 | 11.7 | 33156.2 | 7804.8 | 34.1 | 4.8 | 133.0 | 71.6 | 10545.4 | 1.8 |

## 3. 指标经验的产生

“错误口径晋升”按 v1 留出题审计：已晋升口径的规范 SQL 答错任一留出题即计入。

| 组 | 学习题 | 判定成功 | 计算链通过 | 提炼成功 | 晋升 | 候选（首个未过门槛） | 提炼 token 入/出 | 提炼 s | 门槛 DB ms | 错误口径晋升 | M2/M3 口径含状态过滤 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| r1-metric-global-named | 6 | 6 | 6 | 6 | 6 | — | 9073/37334 | 159.3 | 27055 | 0/4 | 0/3 |
| r1-metric-global-def-named | 6 | 6 | 6 | 6 | 5 | G3×1 | 9014/33961 | 144.3 | 20542 | 0/5 | 0/3 |
| r1-metric-global-schema-named | 6 | 6 | 6 | 6 | 6 | — | 9159/43096 | 187.3 | 25460 | 0/5 | 0/3 |
| r1-metric-global-revoke-named | 6 | 6 | 6 | 6 | 5 | G3×1 | 9085/42039 | 188.2 | 19751 | 0/3 | 0/2 |
| r1-metric-global-noguard-named | 6 | 6 | 6 | 6 | 4 | G3×2 | 9124/34347 | 144.9 | 15160 | 0/2 | 0/1 |

## 4. 检索与声明（留出、正常新增、v2 合计）

| 组 | 任务 | 调用 find_metric | 命中有效口径 | 命中后声明引用 | 引用被执行端拒绝 |
|---|---|---|---|---|---|
| r1-metric-global-named | 21 | 21 | 21 | 21 | 0 |
| r1-metric-global-def-named | 21 | 21 | 21 | 20 | 0 |
| r1-metric-global-schema-named | 21 | 21 | 21 | 21 | 0 |
| r1-metric-global-revoke-named | 21 | 21 | 21 | 21 | 0 |
| r1-metric-global-noguard-named | 21 | 21 | 20 | 20 | 0 |

## 5. 过期与撤销

“不正确口径”指阶段开始时审计答错留出题的口径。误撤销：被撤销的条目在该阶段审计中并无错误。使用修复口径：find_metric 返回了修订号大于 0 的条目。

| 组 | 阶段 | 检索到不正确口径 | 声明引用不正确口径 | 执行了引用不正确口径的 SQL | 撤销 | 误撤销 | 修复候选 | 修复恢复有效 | 修复被拒 / 失败 / 跳过 | 使用修复口径的任务（正确/总数） |
|---|---|---|---|---|---|---|---|---|---|---|
| r1-metric-global-named | 留出 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-named | 正常新增后 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-named | ETL v2 后 | 0 | 0 | 0 | 3 | 0 | 3 | 3 | 0 | 6/6 |
| r1-metric-global-def-named | 留出 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-def-named | 正常新增后 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-def-named | ETL v2 后 | 0 | 0 | 0 | 3 | 0 | 3 | 3 | 0 | 6/6 |
| r1-metric-global-schema-named | 留出 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-schema-named | 正常新增后 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-schema-named | ETL v2 后 | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-revoke-named | 留出 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-revoke-named | 正常新增后 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 0 | 3/3 |
| r1-metric-global-revoke-named | ETL v2 后 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-noguard-named | 留出 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-noguard-named | 正常新增后 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0 |
| r1-metric-global-noguard-named | ETL v2 后 | 5 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0/0 |

修复后恢复有效的口径，在 v2 结束时的审计：

| 组 | 修复后有效的口径 | 其中答错留出题 |
|---|---|---|
| r1-metric-global-named | 3 | 0 |
| r1-metric-global-def-named | 3 | 0 |
| r1-metric-global-schema-named | 0 | 0 |
| r1-metric-global-revoke-named | 0 | 0 |
| r1-metric-global-noguard-named | 0 | 0 |

## 6. 依赖表有写入后的维护

各组的条件、受限修复与回归相同，只有维护方式不同。刷新：待验证，重查通过后继续使用；撤销后修复 / 撤销未恢复：条件不成立而正式撤销，随后受限修复，回归通过与否；需重新提炼：逐写入撤销，只能由 A 重新学习。条件处理（跳过/复用/执行/强制/交给关联经验）：跳过＝读到的表未变化；复用＝同一版本上已有同一条件或蕴含它的结论；执行＝本次访问数据库（含在途合并）；强制＝定义级重验重跑关联守卫；交给关联经验＝由关联经验按其守卫涉及的表决定是否重跑。维护 DB 按事件内计量，本评测顺序执行，不混入其他请求。

| 组 | 阶段 | 维护次数 | 刷新 | 撤销后修复 | 撤销未恢复 | 需重新提炼 | 合并的并发维护 | 条件：跳过/复用/执行/强制/交给关联经验 | 修复复用 | 维护墙钟 s | 维护 DB ms | 重新学习：晋升/任务 | 重新学习 token | 重新学习 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1-metric-global-named | 正常新增后 | 3 | 3 | 0 | 0 | 0 | 0 | 3/2/1/0/2 | 0 | 5.5 | 5466 | — | — | — |
| r1-metric-global-named | ETL v2 后 | 3 | 0 | 3 | 0 | 0 | 0 | 1/0/1/0/2 | 0 | 16.9 | 16896 | — | — | — |
| r1-metric-global-def-named | 正常新增后 | 3 | 3 | 0 | 0 | 0 | 0 | 0/0/3/4/0 | 0 | 19.0 | 19027 | — | — | — |
| r1-metric-global-def-named | ETL v2 后 | 3 | 0 | 3 | 0 | 0 | 0 | 0/0/2/3/0 | 0 | 33.9 | 33933 | — | — | — |
| r1-metric-global-schema-named | 正常新增后 | 4 | 4 | 0 | 0 | 0 | 0 | 0/0/0/0/0 | 0 | 0.0 | 0 | — | — | — |
| r1-metric-global-schema-named | ETL v2 后 | 3 | 3 | 0 | 0 | 0 | 0 | 0/0/0/0/0 | 0 | 0.0 | 0 | — | — | — |
| r1-metric-global-revoke-named | 正常新增后 | 2 | 0 | 0 | 0 | 2 | 0 | 0/0/0/0/0 | 0 | 0.0 | 0 | 4/4 | 211856 | 446 |
| r1-metric-global-revoke-named | ETL v2 后 | 2 | 0 | 0 | 0 | 2 | 0 | 0/0/0/0/0 | 0 | 0.0 | 0 | 3/4 | 357322 | 458 |
| r1-metric-global-noguard-named | 正常新增后 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0/0/0/0 | 0 | -0.0 | -0 | — | — | — |
| r1-metric-global-noguard-named | ETL v2 后 | 0 | 0 | 0 | 0 | 0 | 0 | 0/0/0/0/0 | 0 | -0.0 | -0 | — | — | — |

## 7. 成本

提炼与晋升门槛不在请求路径上；守卫、守护、受限修复与 G8 回归在 find_metric 与 run_sql 的请求路径上。离开请求路径不代表成本消失。逐写入撤销组的重新学习与提炼见第 6 节，不计入本表。

| 组 | 提炼 token | 门槛 DB ms | 请求路径守卫、守护与修复 DB ms | 命中任务 | 每个命中任务分摊的提炼 token |
|---|---|---|---|---|---|
| r1-metric-global-named | 46407 | 27055 | 17564 | 21 | 2210 |
| r1-metric-global-def-named | 42975 | 20542 | 50978 | 21 | 2046 |
| r1-metric-global-schema-named | 52255 | 25460 | 5518 | 21 | 2488 |
| r1-metric-global-revoke-named | 51124 | 19751 | 0 | 21 | 2434 |
| r1-metric-global-noguard-named | 43471 | 15160 | 5551 | 20 | 2174 |

## 说明

- 判题器与数据、任务生成器同源，不是外部确认的业务金标准。
- 直连组不跑学习；带口径题面下所有组得到相同的业务定义。
- 指标守护的结果依赖任务顺序：关联重验证和粒度修复会写入经验库，影响后续 run_sql 审查。顺序固定，见逐任务记录。
- 受限修复与 G8 使用学习集判题器，实验之外需要业务方确认。
- EXPLAIN 在任务结束后执行，会改变后续任务的缓存状态。
