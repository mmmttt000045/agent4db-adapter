# 维护扫描的反序复验（2026-09-30）

与 [9 月 29 日实验](../2026-09-29-maint-share/README.md) 配对，改变维护方式的执行顺序，以检查缓存冷热和运行顺序的影响。代码记录为 `5e82e37` 加计算链与 G3 修复；当时记录指出这些修复不涉及 `maint-bench`。

```bash
./target/release/agentdb-mid --pool 16 maint-bench --agents 8 --share 1,2,4,6 \
  --policies condition,condition-scope,definition,schema,revoke
```

[cells.txt](cells.txt)、[report.md](report.md)、[run.log](run.log) 是本地证据。完整原始结果在 noctis `/root/agentdb-mid/results/maint-1790707404365821/`。这是顺序控制，不作为独立统计显著性检验。
