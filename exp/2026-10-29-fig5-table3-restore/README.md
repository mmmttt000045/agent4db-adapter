# Fig.5 与 Table III 的中间恢复版本

本目录保存 2026-10-29 一次稿件恢复与论文仓库同步的记录，不包含新实验。该版本从 `01daa2133a54ee45a8d1b529b5e04167e81ed340` 恢复每题成本散点图的中英文 PDF、图注及 Table III 源码；具体路径保存在 `github-push-result.json` 的 `exact_restored_paths` 中。

当时已推送并核验的论文仓库提交为 [514d6c4](https://github.com/mmmttt000045/icde-2027-paper/commit/514d6c474cbfd8339c7392acf809d6a5e93e0f25)。该记录中的页码和图号只对应这个中间版本。后续 Table III 更正和 Table IV 恢复见相邻目录 [2026-10-29-table4-fig1](../2026-10-29-table4-fig1/README.md)，当前稿件安排以 [论文说明](../../overleaf/README.md) 为准。

- `github-base.json`：同步前的远端版本与文件信息。
- `prepare.py`、`sync-plan.json`：当时的源码准备逻辑和同步范围。
- `github-push-result.json`：提交、恢复来源、编译及视觉检查的历史结果。
- `consumer_cost-before.py`：修改前的绘图源码记录。

以上文件保留当时状态；整理目录时没有重跑实验、重算数据或覆盖历史记录。
