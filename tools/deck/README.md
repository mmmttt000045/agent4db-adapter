# 汇报 PPT 生成器

`build-deck.js` 生成中文 MAVRA 汇报，使用可编辑的文本、图形、表格和原生图表，每页含讲稿备注与来源。10 月 12 日版面向**没有接触过这个方向的听众**：**22 页正文 + 5 页问答附录**，按"背景（数据智能体是什么、口径为什么是业务知识、共享的趋势）→ 问题（贯穿例子、现有手段为什么挡不住）→ 做法（记录 / 维护 / 约束使用 / 处理失效四步，各一页）→ 系统 → 两层实验 → 边界 → 贡献与进展 → 想讨论的问题"展开；附录放形式化、修复细节、基线对照、完整会话延迟和工作负载刻画，供问答使用。每页标题是一句完整的话，正文用白话，术语第一次出现时用退货金额的例子解释；讲稿备注写给汇报人，说明这页该怎么讲、数字的口径是什么。
```bash
cd tools/deck
npm ci
npm run build
```

默认构建产物为 `docs/mavra-report-2026-10-12.pptx`。自定义日期或输出位置：

```bash
node build-deck.js ../../overleaf --date 2026-10-12 --out ../../docs/mavra-report-2026-10-12.pptx
```

直接运行脚本而不指定 `--date` 时采用当天 UTC 日期。省略论文目录时按脚本位置定位仓库；显式传入的相对路径按当前工作目录解析。不再需要外部 `SKILL_DIR` 或主题脚本。

论文结果从 `overleaf/gen/{numbers,scen-ds,review,numbers-prev,session-latency}.tex` 读取。固定库会话分阶段结果从 `exp/2026-10-03-session-latency/stats.json` 读取，业务定义相同的探索对照从 `exp/2026-10-03-shared-memory/analysis/summary.json` 读取；背景中的工作负载数值与贯穿例子沿用论文。缺失宏、非数值图表数据或会话宏与归档不一致时构建失败。旁边生成的 `.sources.json` 保存来源 SHA-256、实际引用的宏及逐页提纲，便于核对和更新。

先更新论文及结果宏，再重建。会话完成时间包含 LLM、工具与入场排队；学习和库导入成本单列。完整会话页并列呈现通用缓存的结果，不把 DB 工作量减少当作所有到达方式下的延迟优势。

在安装了 LibreOffice 和中文字体的环境中，可导出便于查看的 PDF：

```bash
soffice --headless --convert-to pdf --outdir ../../docs ../../docs/mavra-report-2026-10-12.pptx
```

视觉检查逐页确认中文字体、文本完整性、表格高度与图表标签。当前字体为 Microsoft YaHei；Linux 渲染可使用 Noto Sans CJK SC 替代。
