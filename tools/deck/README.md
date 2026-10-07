# 汇报 PPT

`build-deck.js` 生成 `docs/mavra-system.pptx`：6 页中文 PPT，用三张图讲清楚 MAVRA 的结构、功能和工作流，每页带讲稿备注。

| 页 | 内容 |
| --- | --- |
| 1 | 标题 |
| 2 | MAVRA 做三件事：学习指标定义、数据变了就重新校验、执行前把关 |
| 3 | 系统结构（`figures/overview-zh.png`）：一次请求怎样经过查询服务、指标库、内置智能体与维护 |
| 4 | 工作流①（`figures/lookup-zh.png`）：查询指标定义，再执行 SQL；校验结果缓存怎样复用 |
| 5 | 工作流②（`figures/lifecycle-zh.png`）：指标定义的学习、停用与修复 |
| 6 | 小结 |

三张图由 `tools/figures/overview.py`、`lookup.py`、`lifecycle.py` 画成，按幻灯片尺寸设计（300 mm 宽，12–15 pt 字），用通用词汇：指标定义、指标库、校验规则、校验结果缓存、数据版本、快照、v1/v2、停用、回归测试，不用论文里的符号和自造词。改图后先在 noctis 上重画并转成 PNG，再在本机生成 PPT：

```bash
# noctis，仓库根目录
python3 tools/figures/build.py --deck
cd tools/deck/figures && for f in *.pdf; do pdftoppm -r 300 -png -singlefile $f ${f%.pdf}; done

# 本机（把 tools/deck/figures 取回后）
cd tools/deck
npm ci          # 只需一次，pptxgenjs 4.0.1
npm run build   # 写 docs/mavra-system.pptx；或 node build-deck.js --out 其他路径
```

数值取自端到端实验：5 月门店退货金额 329.4 万（不处理时 658.9 万），学习题 4 月 313.3 万。字体为 Microsoft YaHei；在 Linux 上用 LibreOffice 预览时由 Noto Sans CJK SC 代替。
