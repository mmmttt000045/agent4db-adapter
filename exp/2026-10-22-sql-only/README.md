# RelBench：只复用完整 SQL 的消融对照

## 预先固定的设计（2026-10-22，新增运行之前）

用户要求补“只保存上次完整 SQL”的基线，并使用远端 happycoding 网关。
检验问题：现有 RelBench 重训中的节省，有多少可以由完整 SQL 复用解释？

- 两组：`sql-only` 与 `mavra`；两组均经 happycoding 请求 `deepseek-v4.1-flash`，响应模型须为 `deepseek/deepseek-v4.1-flash-1017`；thinking enabled、reasoning effort low。
- 两库：rel-stack、rel-trial；各三个官方任务、五个既有截点。run=1，沿用随机到达顺序和所有任务。
- 一轮诊断共 60 个会话。每组从空记忆、独立数据库副本开始；不导入旧组方案或将旧网关结果并入配对比较。
- 用户已确认响应标识 `deepseek/deepseek-v4.1-flash-1017` 与主实验为同一模型。请求及响应标识、配置、代码与二进制哈希记录于运行证据；本轮仍使用同网关配对运行，以统一调用设置。
- 预算保持 40 次 LLM、8 次验证、连续两次无提升；从第二截点起以本组上轮方案在新数据上的重拟合分数为目标，达标后允许一次改进（最多再用五次 LLM）。这次不修改停止规则；各组目标值不保证相同。
- 固定 LightGBM、50,000 训练种子、5,000 种子的逐次验证泄漏审计、600 秒特征查询上限及延后测试评估均沿用现有框架。测试标签不反馈给记忆。

## SQL-only 的边界

`sql-only` 使用与 MAVRA 相同的 `relbench-mavra` 底层模式，使表描述、连接和查询缓存范围相同；但不启用提取器、不调用学习接口、不发布任何结构化定义，工具中只有 `find_program`，没有 `find_features` 或 `compose_features`。

每个任务仅保存本组最新一个成功且审计 clean 的完整 SQL。成功条件与 MAVRA 学习一致：验证分数优于实体表参照。模型服务失败的会话不写回；失败不会覆盖此前成功方案。仅能检索本任务、严格更早截点的方案。复用前用当前验证表的 50 个种子执行与 MAVRA 相同的 count 包装检查（300 秒）；返回原 SQL，由智能体继续调用相同的完整验证和泄漏审计。

保存 SQL 不调用 LLM；保存耗时、来源截点和 SQL 哈希单独记录。MAVRA 的提取 token 仍计入其总成本。

## 运行与分析

远端为 `noctis-dmit`，独立目录 `/root/agentdb-sql-only-20261022`，原始输出 `results/sql-only-20261022/`。既有数据库模板和只读准备文件复用；独立实验库由框架建立、结束时删除。最多同时运行两个单元，每单元内任务串行，内存限制 24 GiB。

运行矩阵见 `cells.txt`；启动前执行 `tools/relbench/test_sql_only.py` 与网关工具调用往返检查。协议冻结后发生的修正须单独记录，试跑不混入正式数据。

报告全部五个截点及截点 2–5 两种成本：含学习的 token、LLM/工具调用、会话及学习时间和各任务测试质量。同时报告逐截点差值、审计失败、无有效方案、第一次验证命中旧 SQL 和首次达标比例。不把单轮结果写成独立重复下的显著性或统计非劣效结论。网关异常与恢复轨迹保留，不择优选取会话；不完整组不得作为完整结果。

当前状态：队列已停止。SQL-only／rel-stack 的 15 个会话及测试评估完成；MAVRA／rel-stack 完成 7 个会话后遇到 HTTP 402，MAVRA／rel-trial 完成 3 个会话后因上游空回复导致 HTTP 400，SQL-only／rel-trial 首次请求即遇到 HTTP 402。2026-10-22 15:49 UTC 复测仍为上游 `openrouter_credits` 不足。详见 `status.json`。

预检记录：远端旧配置的响应模型不带 `-1017`，初次连通检查拒绝了 15 个短回复，未启动实验。检查模型列表和实际响应后，只在本次实验进程中固定上述请求／响应标识，不改原服务器 `.env`。

启动：在独立目录执行 `nohup bash exp/2026-10-22-sql-only/run.sh > exp/2026-10-22-sql-only/launcher.log 2>&1 < /dev/null &`。队列完成后自动运行统计；若有未完成组或未解决测试评估，统计脚本拒绝生成完整结果。

## 运行后诊断

服务器日志采用 CST（UTC+8），此前把启动日志 21:15 标成 UTC 是记录错误；实际启动为 2026-10-22 13:15 UTC，以 `run-provenance.json` 为准。

已完成的 SQL-only／rel-stack：全部会话 1,951,358 token，截点 2–5 为 881,889 token；12 个复用会话中 11 个第一次验证达标。三个任务测试均值为 post-votes MAE 0.064422、user-badge AUC 0.860431、user-engagement AUC 0.885703。相对历史 MAVRA 的 1,328,185 复用 token 少 33.6%，但不同批次只能作为初步参照，不能当作本轮完成的配对结论。

空回复根因：网关返回 HTTP 200、`finish_reason=error`，只有推理 token，没有 content 或 tool_calls；原客户端把它追加为仅含 role 的 assistant 消息，下一请求因消息非法被拒。修复先验证回复可用性，最多四次有界重试，重试保留相同对话，消耗 token 仍计入成本。修复代码在本地及远端 `recovery-tools/relbench/`，原始运行代码和记录保留；额度恢复前不重启实验。
