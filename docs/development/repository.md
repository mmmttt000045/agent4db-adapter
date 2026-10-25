# 仓库维护约定

## 新文件放在哪里

- 系统实现放 `src/`；通用运行和统计脚本放 `tools/`，先在 [工具索引](../../tools/README.md) 登记。专用脚本放对应的 `tools/relbench/`、`tools/reforce/` 或 `tools/figures/`。
- 原始运行输出放 `results/`。选入研究记录的实验按 `exp/YYYY-MM-DD-topic/` 归档，包含协议、结果与原始数据位置；在 `exp/catalog.json` 登记。
- 当前设计、状态与研究笔记放 `docs/research/`；固定的历史协议、已回退方案与阶段审查放 `docs/history/`。旧记录使用历史措辞，不随当前结论改写。
- 论文使用的图形 PDF 和 `overleaf/gen/*.tex` 随源码提交，生成方式见论文与工具说明。编译缓存和常规上传 ZIP 放 `overleaf/build/`。
- PPT 生成器与图片放 `slides/`，生成输出放 `slides/build/`；需要长期保留的版本放 `slides/versions/`，同时登记来源。独立编辑版本不得被生成器覆盖。
- 第三方源码在 `third_party/` 内保留原有来源说明。实验中的 `script-as-run` 和源码快照是当时的运行证据；改进后的工具另存，不覆盖归档。

## 实验登记与更新

`exp/catalog.json` 是实验导航的来源，记录用途、采用范围、证据、分析入口、生成文件、原始数据位置与代码版本记录位置。未知的运行信息回到原协议查证，不以整理时的 Git HEAD 充当运行版本。

```bash
python3 tools/experiment-index.py          # 从清单生成 exp/README.md
python3 tools/experiment-index.py --check  # 检查目录覆盖、引用和索引同步
```

新增实验应在 README 中写明：运行代码版本或源码哈希、配置与命令、数据和模型版本、输出位置、失败与排除规则、统计命令。正式结果有原始文件时保存哈希；只有远端副本时记录远端路径和可取得的校验信息。

当前论文采用范围与数据可用性分开登记。`results/` 被忽略不代表可以删除；原始数据只在服务器的实验也不能宣称已完整离线复现。

## 2026-10-22 路径迁移

| 旧路径 | 当前路径 |
| --- | --- |
| `tools/deck/` | `slides/`；生成输出改为 `slides/build/` |
| `docs/*.pptx` | `slides/versions/`，原文件名与内容保留 |
| `docs/cline-gateway.md` | `docs/development/cline-gateway.md` |
| `docs/related-work.md` | `docs/research/related-work.md` |
| `docs/research-status.md` | 历史正文在 `docs/history/research-status-2026-10-07.md`；当前入口在 `docs/research/README.md` |
| `docs/metric-experience-protocol.md`、`docs/shared-memory-study.md` | `docs/history/` 下的同名文件 |
| `docs/refactor-acceptance.md`、`docs/shared-memory-positioning.md`、`docs/citation-audit-2026-10-01.md` | `docs/history/` 下的同名文件 |
| `overleaf/mavra-sigmod-bilingual.zip` | `docs/history/artifacts/mavra-sigmod-bilingual.zip` |

历史运行报告和压缩包里的旧路径按此表解释。可执行工具与当前导航使用新路径。
