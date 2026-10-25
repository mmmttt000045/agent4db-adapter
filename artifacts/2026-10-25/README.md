# 2026-10-25 论文与汇报归档

整理时将本机已有论文预览和 PPT 按原字节保存，Overleaf 包在更新目录说明后重新打包，并记录来源路径、文件大小和 SHA-256，见 [manifest.json](manifest.json)。论文正文、图表与实验数值未在本次整理中修改。

| 内容 | 文件 | 来源与用途 |
| --- | --- | --- |
| 完整英文论文预览 | [mavra-shared-memory-preview.pdf](paper/mavra-shared-memory-preview.pdf) | 14 页；来自 `output/pdf/` 的 2026-10-24 现有预览，已核对可读取 |
| 图 1 与引言预览 | [fig1-and-introduction-preview.pdf](paper/fig1-and-introduction-preview.pdf) | 2 页；来自 `output/pdf/` |
| 英文图 1 预览 | [fig1-motivation-preview.png](paper/fig1-motivation-preview.png) | 来自 `output/pdf/` |
| 中文图 1 预览 | [fig1-motivation-zh-preview.png](paper/fig1-motivation-zh-preview.png) | 来自 `output/pdf/` |
| Overleaf 上传包 | [mavra-icde-bilingual.zip](paper/mavra-icde-bilingual.zip) | 62 个文件；已校验 ZIP 完整性，并与当前论文的输入文件逐字节核对一致 |
| 已有完整预览的编译入口 | [fig1-review-en.tex](paper/fig1-review-en.tex) | 编译时额外启用 T1 字体编码；如需复现，将它复制至 `overleaf/` 后编译 |
| 三份新增 PPT | [slides/versions/2026-10-25/](../../slides/versions/2026-10-25/README.md) | 基础版 21 页、常用词汇版 21 页、补充研究背景版 23 页；保留原文件名 |

持续编辑使用 [英文入口](../../overleaf/main-en.tex)、[双语入口](../../overleaf/main.tex) 和 [稿件说明](../../overleaf/README.md)。上传 Overleaf 后，英文选择 `main-en.tex` / pdfLaTeX，双语选择 `main.tex` / XeLaTeX。独立论文仓库为 [icde-2027-paper](https://github.com/mmmttt000045/icde-2027-paper)，与主仓库保留相同论文输入，并单独保留本次论文产物。

完整 PDF 沿用已有预览。本次整理环境没有可用的 TeX Live，内置 Tectonic 的本地格式缓存访问也未成功，因此未重新编译；不把现有预览当作重新验证的投稿 PDF。预览中的作者与单位仍为占位符。

原始实验结果与制作脚本、模板、草稿和预览的完整本机备份见 [archives/2026-10-25/](../../archives/2026-10-25/README.md)，恢复方式见 [备份说明](../../archives/README.md)。
