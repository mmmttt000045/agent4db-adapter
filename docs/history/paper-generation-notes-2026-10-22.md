# 整理前的论文数值生成说明

> 以下为 2026-10-22 整理前保留在论文 README 中的说明，包含更早批次的命令和数值。它们可能覆盖当前使用的宏；现行入口见 [论文说明](../../overleaf/README.md) 和 [实验索引](../../exp/README.md)。

## 数值与实验存档

实验数据统一保存在仓库的 `exp/`，不再在 Overleaf 工程中保留副本。

| 生成文件 | 来源与生成脚本 |
| --- | --- |
| `gen/replay-safety.tex` | `tools/replay-safety-summary.py`；从 TPC-DS、TPC-H、SSB 与 BIRD financial 的原始回放报告按共同题次重算正确服务、错误服务和拒绝，来源哈希、分库计数及三例错误明细保存在 `exp/2026-10-11-generality/replay-safety-summary.json` |
| `gen/numbers.tex`、`gen/scen-cost.tex` | `tools/paper-results.py`；原始场景结果在 noctis 的 `results/scen-20261002/`，汇总存档在 `exp/2026-10-02-scenarios-ds/paper-results.json` |
| `gen/numbers-prev.tex` | `tools/paper-results.py --numbers-only`；此前一轮三模型实验，原始结果在 noctis 的 `results/scen-20260930/` |
| `gen/scen-ds.tex` | `tools/scen-stats.py`；汇总存档在 `exp/2026-10-02-scenarios-ds/scen-stats.json` |
| `gen/review.tex`、`gen/snapshot-stress.tex` | `tools/review-results.py`；本地存档在 `exp/2026-10-02-cache-baseline-tpcds/` |
| `gen/session-latency.tex` | `tools/session-latency-stats.py --tex-out`；存档在 `exp/2026-10-03-session-latency/` |
| `figures/*.pdf` | `tools/figures/build.py`；图 2–4 直接读取上面的存档（`replay-stats.json`、`tpcds-replay-stats.json`、`cb-1m-share-stats.json`、`paper-results.json`、`scen-stats.json`），并与 `gen/` 中正文引用的数值逐一核对 |
| 工作负载表中的数值 | `exp/2026-10-01-workload-characterization/` |

在 noctis 的仓库根目录重新生成（2026-10-06 核对：前四条命令逐字节复现 `gen/` 中对应文件）：

```bash
python3 tools/paper-results.py --scen results/scen-20260930 --prefix PrevScen --numbers-only overleaf/gen/numbers-prev.tex
python3 tools/paper-results.py --scen results/scen-20261002 --models "DeepSeek V4.1 Flash" --out overleaf/gen \
  --json exp/2026-10-02-scenarios-ds/paper-results.json
python3 tools/scen-stats.py --scen results/scen-20261002 --json exp/2026-10-02-scenarios-ds/scen-stats.json --tex-out overleaf/gen
python3 tools/review-results.py --exp exp/2026-10-02-cache-baseline-tpcds --out overleaf/gen
python3 tools/figures/build.py
```

场景生成命令需要服务器上完整的原始结果；正常编辑与编译不需要重新运行实验。研究状态与实现边界见 [docs/research/README.md](../../docs/research/README.md)，实验索引见 [exp/README.md](../../exp/README.md)，参考文献核对记录见 [docs/history/citation-audit-2026-10-01.md](../../docs/history/citation-audit-2026-10-01.md)。

`overleaf/` 仍是主仓库的普通目录，主仓库远程地址保持不变。独立论文仓库为 [icde-2027-paper](https://github.com/mmmttt000045/icde-2027-paper)，论文源文件放在该仓库根目录，可用 Overleaf 的 GitHub 导入功能创建项目。本地独立工作副本位于同级目录 `../icde-2027-paper/`；本目录的修改不会自动同步过去，需先更新独立工作副本并推送，再在 Overleaf 的 Integrations → GitHub 中手动拉取。Overleaf 中的修改也需先推送回 GitHub，再拉取至本地工作副本。
