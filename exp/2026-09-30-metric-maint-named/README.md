# 早期单模型指标维护实验（2026-09-30）

历史批次：只给指标名称的端到端 LLM 实验。代码记录为 `5e82e37` 加计算链与 G3 修复。原始结果位置、组合来源和历史数值见 [早期索引](../../docs/history/experiment-index-2026-10-03.md)。

```bash
./target/release/agentdb-mid --pool 16 metric-bench --metrics M1,M2,M3 --phrasings named \
  --modes metric-global,metric-global-def,metric-global-schema,metric-global-revoke,metric-global-noguard
```

[analysis.md](analysis.md) 为历史分析，[verified-results.json](verified-results.json) 保留数值核对，[report.md](report.md) 为报告。原始共享组在 noctis `results/metric-1790700840466648/`；普通中间层只采用 `results/metric-1790690815978959/` 的 `cell-r1-middle-named.json`，该目录其余有提炼缺陷的运行被弃用。

当前场景实验入口为 [题集 v2、五轮运行](../2026-10-10-scenarios-q5/README.md)，不要把两批统计范围混合。
