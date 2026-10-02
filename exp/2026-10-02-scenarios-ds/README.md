# 场景主实验（DeepSeek V4.1 Flash，2026-10-02 起）

按用户要求，设计定下之前只用订阅模型 `cline-pass/deepseek-v4.1-flash`（新的 ClinePass 账号，密钥只在 noctis `.env`）；设计确定后主实验再补其他模型。

## 设计

- 二进制：noctis `target/release`，源码 `cd3e02e` 起未变（修复候选唯一性 `repair_unique`、等待进行中的修复 `wait_repair` 默认打开；绑定快照执行默认关闭——场景中更新在阶段之间施加，没有并发写入）。
- 方法 7 种：不共享 `middle`、轨迹检索 `traj-global`（新增，AgentSM 式匹配基线）、无守护、只看结构、写入即撤销（重新学习）、定义级、条件级（MAVRA）。
- 变化 11 种：原 10 种 + 备份副本 `mirror`（修复歧义反例）。
- 每种方法 3 次独立重复（每次重新学习）；方法顺序按重复轮换；100 万行；题面只给指标名（named）。
- 6 个进程并行（ClinePass 并发上限），相邻启动间隔 60 秒：`queue-scen-ds.sh`。
- 输出：noctis `results/scen-20261002/dsv41flash-r{1,2,3}-{a,b}/`。

## 轨迹检索基线冒烟（20 万行，1 次，变化 status 与 mirror）

- 10 道学习题全部入库（判题成功且计算链可复核），留出与变化阶段每题平均检索约 1 次。
- 留出题 15/15 答对：数据不变时，按题面检索成功轨迹与共享定义一样有效。
- 状态流水下退货金额 3 题全错（沿用不带状态过滤的旧 SQL，金额翻倍）；备份副本下 6 题错 2 题。
- 输出：noctis `results/scen-20261002/smoke-traj/`。
