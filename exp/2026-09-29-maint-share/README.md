# 维护方式与共享度扫描（2026-09-29）

早期机制实验，不调用模型。代码版本记录为 `5e82e37`，100 万行、8 个脚本智能体，扫描四个共享度、五种维护方式及两种到达方式。

```bash
./target/release/agentdb-mid --pool 16 maint-bench --agents 8 --share 1,2,4,6
```

[cells.txt](cells.txt) 保存逐组合计，[report.md](report.md) 是运行报告，[run.log](run.log) 是日志。完整原始报告位于 noctis `/root/agentdb-mid/results/maint-1790686347212630/`。

配置与旧结果汇总见 [历史索引](../../docs/history/experiment-index-2026-10-03.md)，协议见 [指标实验协议](../../docs/history/metric-experience-protocol.md)。当前论文的通用缓存、规模与回放依据见 [10-02 实验](../2026-10-02-cache-baseline-tpcds/README.md)。
