# 工作区原始材料备份

| 日期 | 备份范围 |
| --- | --- |
| [2026-10-25](2026-10-25/README.md) | 本机 `results/` 的现有实验原始结果、论文／PPT 制作过程中的脚本、模板、草稿、图形与检查记录，以及历史基线源码副本 |

代码、论文源码、参考文献、实验协议与已采用的证据继续按原目录保存在 Git 中；已保留的论文 PDF、Overleaf 包和正式 PPT 入口见 [产物索引](../artifacts/README.md)。大体积原始材料采用分卷 ZIP，每卷最多 45 MiB，便于随仓库一起推送。`manifest.json` 记录每个原始文件、分卷和合并后 ZIP 的 SHA-256。

## 校验

从仓库根目录执行，需要 Python 3.11 或更新版本，只使用标准库：

```bash
python tools/workspace-backup.py verify archives/2026-10-25
```

该命令逐一校验分卷、合并后的 ZIP，以及每个原始文件的大小、CRC 和 SHA-256，不访问数据库或模型，也不改写原始数据。

## 恢复

选择一个新的空目录：

```bash
python tools/workspace-backup.py restore archives/2026-10-25 --destination restored-workspace
```

脚本校验后按原路径解压到目标目录，例如 `restored-workspace/results/` 和 `restored-workspace/tmp/mavra_red/`。目标目录必须为空，以避免覆盖已有材料。临时合并文件放在本地 `tmp/backup-staging/`，操作完成后自动清理。

## 范围与本机保留项

备份只反映整理时本机实际存在的文件，服务器上的其他原始实验仍按 [实验清单](../exp/catalog.json) 登记。本机的密钥文件、含密码的数据库连接文件、Git 内部文件、字体与编译依赖缓存、Rust 构建产物和 Python 字节码不打包；其中发现的历史源码副本单独保留，具体范围见日期说明。原始 `results/`、`tmp/` 和 `output/` 文件留在本机，归档不删除它们。
