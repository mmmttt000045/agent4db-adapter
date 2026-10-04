# 共享数据库知识与经验：论文重构及补充实验

本目录保留 2026-10-03 的重构前状态、新实验记录、协议变更与审计材料。论文主线是给同一数据库/业务空间的用户侧智能体提供可复用知识与经验证的经验；指标维护提供最强的条件性使用保证。

## 材料

| 路径 | 内容 |
| --- | --- |
| `manifest.json` | 开始时间、基准提交与原有未提交状态 |
| `before-refactor.tar.gz` / `initial-workspace.diff` | 重构前源文件及原有修改；不是新增实验数据 |
| `final-implementation.tar.gz` | 最终代码、测试夹具、运行与分析脚本及研究文档；与各实验时源码独立保存，不含私密环境配置 |
| `raw/results/shared-memory-recovery/` | 完整恢复重复：三生产者流、264 次消费者尝试、12 个知识前缀、逐工具轨迹、运行前源码包及摘要 |
| `raw/results/shared-memory-main/` | 原按量线路的完整 264 次尝试，含 28 次 HTTP 402；不与恢复轮合并 |
| `raw/results/service-recovery-probe/` | 恢复前既有服务线路的可用性及准确模型名检查 |
| `raw/results/strategy-main/` | 三次正式计时采集，各 24/16/24 个不同训练/验证/测试候选；所有固定排列和未采纳结果 |
| `raw/results/strategy/` | 与构建并行的第一次试运行，不进入正式计时汇总 |
| `raw/results/metadata-audit/` | 探索性 HTTP 画像复用、数据更新及目录刷新边界诊断，含完整响应 |
| `raw/validation/` | 单元测试、静态检查及数据库集成日志；保留默认调试栈溢出的失败 |
| `analysis/summary.json` / `analysis/results.md` | 从原始记录生成的完整统计与结论 |
| `analysis/classification-audit.json` | 消费者 SQL 探查分类复核样本 |
| `analysis/initial-service-censored/` | 原始服务失败轮的完整统计与事后完成调用敏感性分析 |
| `analysis/paper-verification.json` / `analysis/cold-package-verification.json` | 四个 PDF 核对；64 文件源码包从空目录编译及主稿内容一致性 |
| `analysis/deliverables.json` | 最终交付文件摘要、测试结果及源码一致性 |

协议见 [shared-memory-study.md](../../docs/shared-memory-study.md)。主实验给各组相同业务定义，命名题另报；来源学习、提炼与完整检查采集不混入已建库消费者代价。三个生产者流及三个同负载计时重复支持描述性结论，不能把相关题视为独立统计重复。

恢复轮主分析四组均 54/54，无服务错误。持续积累相对隔离的每次尝试输入 token 低 **24.4%**、结构查找低 **27.7%**，相对首轮冻结的输入 token 低 **18.9%**。仅报名称的次要题：隔离 3/12、冻结 6/12、积累和轨迹均 12/12。来源学习与提炼累计 343.6 秒、277.2 千 token；不含建表及外部判题 SQL，不宣称净部署收益。原按量轮返回的 197 个主分析答案全部正确，服务失败不能算作推理错误。

## 运行与复算

在有 PostgreSQL、模型凭据的实验机执行：

```bash
CLINE_MODEL=cline-pass/deepseek-v4.1-flash \
CLINE_REQUIRE_MODEL=deepseek/deepseek-v4.1-flash \
CLINE_REASONING_EFFORT=high CLINE_HEDGE=1 \
  python3 tools/run-memory-study.py --jobs 3 --out results/shared-memory-new
python3 tools/run-strategy-study.py
python3 tools/metadata-audit.py
```

从本地归档复算，不需数据库或模型 API：

```bash
python3 tools/memory-study-stats.py \
  --memory exp/2026-10-03-shared-memory/raw/results/shared-memory-recovery \
  --initial-memory exp/2026-10-03-shared-memory/raw/results/shared-memory-main \
  --strategy exp/2026-10-03-shared-memory/raw/results/strategy-main \
  --metadata exp/2026-10-03-shared-memory/raw/results/metadata-audit/report.json \
  --out exp/2026-10-03-shared-memory/analysis
```

分析脚本要求三份完整报告、264 个唯一且配对的消费者尝试、12 个准确知识快照、相同题面/判题值、锁定模型及实验库清理；不接受用部分尝试填补完整矩阵。探查分类是公开的模式规则，采用的答案查询优先排除，SQL 意图不能仅靠规则证明。

运行命令会产生新的实验记录；本次结果以归档的二进制摘要、源码包、实际调用与启动清单为准。按量轮和恢复轮采用同一二进制，但重新生成各自的来源知识；恢复在原轮审计后仅因服务不足决定，不能视为事前安排的第二次重复。

## 保留的技术失败

第一次模型小试在解包网关 `data` 字段前检查了模型名，误丢弃正常回复；已修复并通过普通/嵌套回复的回归测试。随后初始三流在消费者开始前因缺少精确前缀导出而停止，增加快照与草案导出后启动最终三流。所有试运行保留，未按答案或收益重跑。策略三次正式采集没有因采纳/拒绝而重跑。

策略只优化验证检查顺序。元数据诊断验证了画像可复用，却也确认注释与新增列不能在当前进程内全面刷新；重启后的正确响应是独立干预，不算实时维护成功。

策略原二进制仍保存在实验机的技术试运行目录，其摘要与正式策略运行清单一致。`raw/results/strategy-main/inputs/code-as-run.tar.gz` 的 28 个代码文件均逐一匹配当时记录的 SHA-256；其中两个文件撤回后加的草案/快照导出即可恢复，恢复结果必须完全匹配摘要。早期协议文件未被完整存档，不声称已经恢复；最终主实验源码包保留了含执行说明的后续版本。现有启动脚本已补上运行前自动归档源码，已完成实验继续以各自的原始运行清单为准。

## 实验后的正确性修正

最终代码审查发现反向连接引用可能只证明事实键唯一，却让另一侧重复累计事实金额。最终原型在 G3 和规范 SQL 编译处要求每个非时间连接从事实表指向至多一行的另一侧，拒绝反向、自连接与多跳引用。新增真实 PostgreSQL 反例和单元回归；论文同时明确左连接、空粒度键、多个聚合及业务完备性前提。两轮 S1 最终前缀中的 25 个指标条目（含一个未准入候选）全部满足新方向约束，原实验无须重跑。原始代码包保留实验时版本，不改写成最终版本。

条件比较及编译时过滤去重还曾忽略字符串值中的大小写和空格。最终实现采用保留字面量的保守 token 比较，遇到转义、美元引用、注释和不支持的运算符时退回精确文本；不同取值不能共享验证结论或被当成同一过滤。真实数据库测试中 `A B`／`AB`、`ABC`／`abc` 的总体具有不同唯一性，修正版均正确区分。两轮 S1 快照的全部指标／连接过滤及唯一性条件中，没有含内部空格或 ASCII 大写字符的字面量；源码与统计往返核对见 `analysis/source-and-roundtrip-verification.json`。集成测试开发中的错误阶段预期及缺失测试批次表也保留在失败日志中，没有作为实验结果使用。

最终验收常规测试 40 项、PostgreSQL 集成测试 5 项全部通过；Clippy 全目标、格式及 release 构建通过。完整集成日志和执行时的 27 个文件摘要位于 `raw/validation/results/final-integration-v3-full*`，与当前最终代码一致。集成测试使用 32 MiB 线程栈；失败尝试和成功复核分别保留，不覆盖旧记录。完整交付入口见 [验收报告](../../docs/refactor-acceptance.md)。
