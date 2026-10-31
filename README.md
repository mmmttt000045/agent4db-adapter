# MAVRA

MAVRA 是面向数据智能体的共享记忆系统原型：在智能体与 PostgreSQL 之间共享经过检查的指标定义和特征，在数据更新后维护其有效性，并在执行时核对使用的修订。Rust 包与命令名为 `agentdb-mid`。

## 工作入口

| 工作 | 入口 |
| --- | --- |
| 系统开发、运行与测试 | [开发指南](docs/development/README.md)、[源码导览](docs/development/source-map.md) |
| 查看实验依据与复现入口 | [全部实验索引](exp/README.md)、[实验清单](exp/catalog.json) |
| 编辑论文 | [ICDE 稿件说明](overleaf/README.md)；英文投稿 `overleaf/main.tex`，双语 `overleaf/main-bilingual.tex` |
| 修改与生成汇报 PPT | [汇报说明](slides/README.md)、[现有版本](slides/versions/README.md) |
| 了解当前研究状态 | [研究状态与证据](docs/research/README.md) |
| 查阅阶段性方案与历史记录 | [历史文档](docs/history/README.md) |

## 快速开始

以下命令从仓库根目录执行；`make help` 列出构建入口。系统开发需要 Rust stable，论文编译与绘图依赖见各自说明。

```bash
cargo build --release --locked
cp .env.example .env   # 配置本地数据库和所需模型；.env 不进 Git
make check            # Rust 格式、单元测试与 Clippy
```

| 命令 | 用途与输出 |
| --- | --- |
| `make index-check` | 检查实验清单、文件引用与索引是否同步；只用 Python 标准库 |
| `make paper` | 编译两种语言，输出到 `overleaf/build/` |
| `make paper-en` / `make paper-bi` | 单独编译英文 / 双语稿 |
| `make paper-pack` | 生成 `overleaf/build/mavra-icde-bilingual.zip`，无需 TeX 或原始实验数据 |
| `make figures` | 重画论文图，更新受版本管理的 `overleaf/figures/*.pdf` |
| `make slides-deps` | 按锁文件安装 PPT 依赖 |
| `make slides` | 用已有图片生成 `slides/build/mavra-system.pptx` |
| `make deck-figures` | 重画 PPT 图并转换为 PNG，需要绘图环境与 `pdftoppm` |

没有 Make 时，可执行 [Makefile](Makefile) 中对应命令，例如 `bash overleaf/build.sh pack`、`npm --prefix slides run build`。数据库集成测试与模型实验需要显式执行，命令见开发指南和各实验协议。

## 目录与产物

| 路径 | 职责 |
| --- | --- |
| `src/` | Rust 中间层、模型客户端、HTTP 接口与评测程序 |
| `tools/` | 实验启动、统计、绘图与外部基线适配；见 [工具索引](tools/README.md) |
| `exp/` | 按日期保存的实验依据、协议、汇总与必要的原始记录 |
| `overleaf/` | 可独立编译的论文源码、数值宏和图形 |
| `slides/` | PPT 生成器、图片、现有汇报版本与本地构建输出 |
| `docs/` | 开发、当前研究与历史文档 |
| `data/` | 最小数据库测试输入 |
| `third_party/` | 外部基线源码；来源与使用条件见各目录说明 |
| `results/` | 本地实验运行输出，Git 忽略 |
| `ccfa-workfiles/` | 本地分析草稿、源码对照和预览，Git 忽略；正式依据归档到 `exp/` |

论文依赖的 `overleaf/gen/*.tex` 和图形 PDF 作为编译输入提交；常规编译文件与上传包放在 `build/` 中。运行日志、历史源码快照和正式保留的 PPT 有各自的来源说明。新增文件的归属与旧路径映射见 [仓库维护约定](docs/development/repository.md)。
