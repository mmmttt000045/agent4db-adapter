# 智能体工作负载刻画（2026-10-01）

补充证据：比较相同分析任务下的智能体探索行为与参数化应用查询，并对照 Redset 工作负载。代码记录为 `9b98bc9`。

```bash
CLINE_MODEL=deepseek/deepseek-v4.1-flash ./target/release/agentdb-mid --pool 16 \
  workload-bench --agent cline --repeats 2 --concurrency 3
python3 tools/workload-stats.py results/workload-*/
```

本地保留 [workload-stats.json](workload-stats.json)、[workload-stats.md](workload-stats.md)、[audit-sample.jsonl](audit-sample.jsonl) 和 `deepseek-v4.1-flash/` 原始轨迹。Redset 统计与说明在 [redset/README.md](redset/README.md)，原始 parquet 只在 noctis `results/workload-baselines/redset/data/`。

采用完成的 DeepSeek 会话；两个 GLM 组因服务余额耗尽未完成，未纳入该统计。详细配置与原始记录说明见 [历史索引](../../docs/history/experiment-index-2026-10-03.md)。
