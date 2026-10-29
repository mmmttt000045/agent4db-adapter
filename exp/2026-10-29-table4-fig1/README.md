# Table IV 历史数据恢复与 Fig.1 位置调整

本目录记录 2026-10-29 的稿件更正与论文仓库同步，不包含新实验。依据 `github-push-result.json`，本次恢复了 `01daa2133a54ee45a8d1b529b5e04167e81ed340` 中的历史 Table IV，以及配套 `gen/relbench.tex` 和 `gen/relbench-table.tex`；Table III 撤销此前误回滚，另将 Fig.1 声明移到引言首次引用之后。

当时已推送并核验的论文仓库提交为 [b2755c2](https://github.com/mmmttt000045/icde-2027-paper/commit/b2755c23953b646e27ccd5fe9a1f9cf1798cca92)。历史网关数据与官方 API 结果分别陈述，没有合并两批结果。该次提交的编译页数和视觉检查记录保留在 `github-push-result.json`，不能替代后续稿件的编译验证。

- `github-base.json`：更正前的远端版本与文件信息。
- `prepare.py`、`sync-plan.json`：源码准备逻辑、文件范围和目标版本。
- `github-push-result.json`：恢复来源、精确文件清单、提交及核验结果。

当前图表安排与源码入口见 [论文说明](../../overleaf/README.md)。整理目录时未更改原始记录或实验数据。
