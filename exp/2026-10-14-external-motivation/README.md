# 用别人的 benchmark 验证动机（2026-10-14）

问题：同一数据库上的不同任务（会话、智能体）是否反复需要同样的数据库知识？只做统计，不调用大模型。

## 数据（noctis `results/external-benchmarks/`，不入库）
- BIRD dev（`dev_20240627/dev.json`，1,534 题、11 个库；来源 bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip，只解压了 dev.json 与 dev_tables.json）。
- LiveSQLBench base-full-v1（600 题、22 个库，PostgreSQL）与 base-lite（270 题、18 个库）：任务文件与每库知识库 `*_kb.jsonl`
  （经 hf-mirror.com 下载；noctis 直连 huggingface.co 失败）。BIRD-Interact（ICLR 2026 oral）建立在它之上。
  公开文件不含任务到知识条目的 id（`external_knowledge` 为空，需发邮件向维护者申请）。
- Spider 2.0-lite（`spider2-lite.jsonl`，547 题、158 个库；本机从 GitHub 下载后拷到 noctis，noctis 访问 raw.githubusercontent.com 超时）。

## 方法（`tools/external-reuse-stats.py`）
- BIRD：evidence 按 `;` 与换行切成条目；逐字视图要求规范化后文本相同（下界）；术语视图按被定义的词（"refers to"、"means"、"="
  等左侧）判断是否同一知识。
- LiveSQLBench：在 normal_query（full）或 query（lite）中按名称或括号里的缩写匹配知识库条目，并带上它依赖的条目
  （children_knowledge 传递闭包）；另报只算直接点名条目的结果。人工核对 20 个随机任务：匹配到的条目都正确；
  漏掉的多为复数形式和同前缀条目，已修正（复数后缀、非缩写的括号限定词保留在名称里）。仍会漏掉只描述概念、不点名的任务。
- Spider 2.0-lite：任务引用的外部知识文档。
- 统计与到达顺序无关：每库每个知识条目被 u 个任务用到，计 u 次使用、其中 u−1 次重复；增长曲线对每库随机抽 200 种到达顺序。

## 结果（`reuse-stats.md`、`reuse-stats.json`）
- LiveSQLBench full：82% 的任务点名了知识库条目，其中 78% 与同库另一任务共用至少一条；知识使用中 49.5% 重复（只算直接点名 28%）；
  计算类知识 54% 重复。同库第 10 个任务所需知识有 48% 已被此前任务需要过，第 20 个任务 65%。lite：78% 共用，40% 重复，第 10 个任务 47%。
- BIRD dev（术语视图）：51% 的题与同库另一题共用一个被定义的术语，28% 的使用重复；第 10 题 15%、第 20 题 24%、第 100 题 33%。
  逐字视图（下界）：41% 共用、22.5% 重复。
- Spider 2.0-lite：每库题目很少（中位数 2），只有 20% 的题引用外部文档，其中 52% 与同库另一题共用文档；不适合衡量同库重复。
- 对照：本文自建负载（表 1）中查找重复已有事实为 93%，高于这些公开 benchmark；公开 benchmark 为覆盖面而刻意多样化，且每库只有 27–140 题。

## 外部文献中的探索代价
- Liu et al., CIDR 2026（liu2026agents）表 1（已对照 PDF 核实）：OpenAI o3 对 22 个多数据库任务各做两次，共 44 条轨迹；平均每条 12.67 条 SQL，
  其中查看表 3.44、查看特定列 3.56（合计 7.00，约 55%），尝试部分查询 4.28、尝试完整查询 1.26；给出人工提示后 SQL 降到 10.38（−18.1%）。

## 进论文（2026-10-14）
- 引言第一段与 §2.1 以这些外部数字开头；新表 `overleaf/tables/external.tex`（表 2）；我们自己的 100 个会话改为测量“会话代价”，93% 注明是自建题目上的数字。
- 宏：`overleaf/gen/external.tex`（`\Ex*`），由 `tools/external-reuse-stats.py --tex-out` 生成；也可只从存档 JSON 重新生成：
  `python3 -I tools/external-reuse-stats.py --from-json exp/2026-10-14-external-motivation/reuse-stats.json --population exp/2026-10-12-population/population-stats.json --tex-out overleaf/gen`
- 代价模型（§2.2）：节省 = 1 − (1−r)(c_e+c_ℓ)/c_e − r·c_r/c_e，c_e、c_r 取人群实验后一半智能体每题 token（无记忆 55.8k、MAVRA 10.0k），
  c_ℓ 为每学一个定义的提取 token（5.8k）。r = 89%（MAVRA 实测从共享定义作答的比例）时模型给出 72%，与实测一致；
  r 取 LiveSQLBench 知识使用的重复率 50% 时为 35%，取第 20 个任务的 65% 时为 50%。
