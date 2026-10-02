# 汇报 PPT 生成器

`build-deck.js` 用 pptxgenjs 生成 `docs/mavra-report-<date>.pptx`，所有数值从 `overleaf/gen/*.tex` 的宏读取，与论文同源；重新生成数字后重跑即可。

```bash
cd tools/deck && npm install pptxgenjs jszip   # 一次
NODE_PATH=$PWD/node_modules SKILL_DIR=<pptx skill 目录> node build-deck.js ../../overleaf
```

`SKILL_DIR` 指向含 `scripts/apply_theme.js` 的 pptx 技能目录（写入主题色）。视觉检查：`soffice --headless --convert-to pdf` 后 `pdftoppm -jpeg` 逐页查看（noctis 上有这两个工具）。
