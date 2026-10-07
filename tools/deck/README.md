# 汇报 PPT

`build-deck.js` 生成 `docs/mavra-system.pptx`：6 页中文 PPT，只讲 MAVRA 的结构、功能和工作流，围绕三张系统图展开，每页带讲稿备注。

| 页 | 内容 |
| --- | --- |
| 1 | 标题 |
| 2 | MAVRA 做三件事：学习并共享口径、数据变了就维护、使用时把关 |
| 3 | 系统结构（`figures/overview-zh.png`）：一个请求怎样流经三个模块 |
| 4 | 工作流①（`figures/lookup-zh.png`）：查找有效定义、在快照上执行，检查结果的复用 |
| 5 | 工作流②（`figures/lifecycle-zh.png`）：口径的学习、失效与修复 |
| 6 | 小结：结构、功能、工作流各一句 |

三张图由 `tools/figures/overview.py`、`lookup.py`、`lifecycle.py` 画成（说明见 `tools/figures/README.md`），不进论文。改图后先在 noctis 上重画并转成 PNG，再在本机生成 PPT：

```bash
# noctis，仓库根目录
python3 tools/figures/build.py --deck
cd tools/deck/figures && for f in *.pdf; do pdftoppm -r 400 -png -singlefile $f ${f%.pdf}; done

# 本机（把 tools/deck/figures 取回后）
cd tools/deck
npm ci          # 只需一次，pptxgenjs 4.0.1
npm run build   # 写 docs/mavra-system.pptx；或 node build-deck.js --out 其他路径
```

字体为 Microsoft YaHei；在 Linux 上用 LibreOffice 预览时由 Noto Sans CJK SC 代替。
