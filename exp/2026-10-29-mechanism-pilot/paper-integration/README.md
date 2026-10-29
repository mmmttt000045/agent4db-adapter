# 2026-10-29 机制图合入论文

用户在完成审阅后明确要求“可以合进论文了，重构相关段落”。本记录区分实验执行与论文采用：原先冻结的预实验协议不变，此次将已有证据写入共用中英文正文，不新增模型调用或数据库实验。

## 采用位置与解释

| 原审阅图 | 当前图号 / 英文页码 | 正文位置 | 证据范围 |
| --- | --- | --- | --- |
| A | Fig.5 / p.10 | V-C Program and definition access | 八格开发预实验；六格有效、两格无 SQL。验证 AUC 与在线/源探索/提炼成本分别呈现，无测试标签评分，不作表示优势或组合器增益推断 |
| B | Fig.6 / p.11 | V-F Amortizing validation and maintenance | 固定 16 定义，三轮、72 格、9,216 请求；SQL/版本缓存强对照和异常格全部保留。图中范围非置信区间，活跃表集合改变的限制保留 |
| C | Fig.7 / p.12 | V-H Snapshot binding | (a) 同版本源、只改变快照生命周期的 30 次受控调用；(b,c) 分别来自归档读与写批次，版本来源混淆与不可合成同一吞吐/安全性曲线的限制明示 |

旧两种模式正确率图顺延为 Fig.8。此前 Fig.3/4 的 PDF 与包装图注保持原样。实验段落按政策比较、开发诊断、受控机制组织；Related Work 与 Discussion and Conclusion 同步，减少重复协议/背景，但保留成本口径、失败单元、来源审计、抽样预算与各实验限制。原 68 个引用键及参考文献文件均保留。

## 图形与来源

新增 `tools/figures/mechanism.py`，从四份已存档 JSON 同时生成六份中英文矢量 PDF 和 `overleaf/gen/mechanism.tex`。输入路径及 SHA256 见 [figure-sources.json](figure-sources.json)。统一使用现有 `mplstyle.py`、`style.py` 及论文配色；A/B 单栏、C 通栏，最低 6.5 pt 图形文字、嵌入字体、黑色坐标框、空心点/线型和柱纹理。原审阅版 PDF/PNG/SVG 保留在 `output/mechanism-pilot-20261029/`。

A/B/C 图注不混用旧预览与新增对照。特别保留 A 的失败成本、B 的 96 次查询/199.36% 异常格、C 的人工屏障不进入性能测量。标量宏由同一输入生成，避免手工更新图文时漂移。

## 构建与交付

- 英文：`overleaf/build/main-en.pdf`，15 页；正文在第 12 页结束，第 13 页开始 AI 声明及参考文献。
- 双语：`overleaf/build/main.pdf`，22 页，供中英对照阅读。
- 源码：`overleaf/build/mavra-icde-mechanism-20261029.zip`；默认 `mavra-icde-bilingual.zip` 内容相同。包含 73 份实际依赖文件，两种语言入口、图和数值宏，未包含原始模型对话或实验配置。
- 上传 Overleaf 后，英文入口 `main-en.tex` / pdfLaTeX，双语入口 `main.tex` / XeLaTeX。源文件不含本机字体绝对路径；最终分页以实际编译环境为准。

图形重建命令为 `python3 tools/figures/mechanism.py`；论文编译/打包入口为 `overleaf/build.sh`。本机通过 Tectonic 离线缓存编译。英文直接编译源码；双语临时副本在 `tmp/mechanism-paper-build/`，仅将三行 CJK 字体声明映射到随副本复制的 Noto 字体（相对路径 `fonts/`），以解决本机没有注册字体的问题；未把此更改写回正式源码或上传包。最初应用编译器无可写缓存，随后本地调用使用 `tmp/tectonic-cache/`。双语字体定位失败的尝试没有作为交付文件。

本地仍有既有 Tectonic 后端的字体替代与重复浮动对象提示；最终日志无未定义引用、缺字或 overfull 盒。英文修改页与双语新增图页均渲染检查，图例、刻度、图注、正文未相互覆盖。没有通过缩小正文字号、页边距或删除异常数据来满足正文页数。

源码包依据现有 `build.sh pack` 的依赖收集逻辑生成，未连接或同步独立论文仓库、GitHub 或远端 Overleaf。

## 可追溯性与核查

- [before-files.json](before-files.json)：本次合入前，论文目录已有文件的 SHA256；`before-sources/` 保存源文本快照。
- [changed-files.json](changed-files.json)：相对于上述快照的论文文件变更，而非相对于 Git HEAD 的全部未提交变更。
- [validation.json](validation.json)：新图字体、数据/数值宏、原图哈希、引用键、页数/图号、打包依赖及编译日志核查。
- 旧默认源码包在 `before-package/mavra-icde-bilingual.zip` 保存一份，避免覆盖旧交付。

实验索引采用状态更新为当前采用，但图 A 的研究级别仍是开发预实验。全目录索引的五个既有未登记日期目录问题继续记录，不在本次合入中补造实验记录。
