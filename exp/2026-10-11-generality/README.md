# 通用性实验：另外三种模式上的配对回放负载（2026-10-11）

目的：在不是为本文编写的三种模式上重复 TPC-DS 的配对回放（见 `exp/2026-10-02-cache-baseline-tpcds/`），检验维护方法
不依赖 TPC-DS 的约定（`date_dim` / `d_year` / `d_moy`、全局唯一的列名、星型单跳关联、按天连续的日期键）。
本目录只有数据、模式说明与定义库；回放结果另行归档。

| 模式 | 模板库 | 事实表（行数） | 日历 | 与 TPC-DS 不同之处 |
| --- | --- | --- | --- | --- |
| TPC-H SF1 | `tpch_sf1` | lineitem 6,001,215；orders 1,500,000 | 事实表上的 DATE 列 | 没有日期维表；雪花链（lineitem → orders → customer → nation）；时间列可在直连表上（orders.o_orderdate） |
| SSB SF1 | `ssb_sf1` | lineorder 6,001,173 | 日期维表 `date`，键为 yyyymmdd | 日期键在月界跳号；年、月列名 d_year / d_monthnuminyear |
| BIRD financial | `financial` | trans 1,056,320；loan 682 | 事实表上的 DATE 列 | 真实银行数据（PKDD'99）；列名在多张表中重复（account_id、date、amount）；trans 有列名 account 与表名 account 相同 |

## 数据来源
- TPC-H：DuckDB 1.5.6 的 tpch 扩展，`CALL dbgen(sf=1)`；22 条查询取自同一扩展的 `tpch_queries()`（默认替换参数），存于 `queries/tpch/`。
- SSB：ssb-dbgen（github.com/eyalroz/ssb-dbgen，提交 ae1e254，cmake 构建），`dbgen -s 1`；生成器不带查询，13 条标准查询按
  O'Neil, O'Neil, Chen, Revilak,《The Star Schema Benchmark and Augmented Fact Table Indexing》（TPCTC 2009）与 SSB 规范第 3 版
  抄写，存于 `queries/ssb/`（编号 q1_1 … q4_3）。
- financial：BIRD dev（https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip，dev_20240627）的 `dev_databases/financial/financial.sqlite`；
  106 道 financial 题（问题、证据、标准 SQL）存于 `queries/financial.json`（BIRD 以 CC BY-SA 4.0 发布）。
原始下载与生成数据在 noctis `/root/agentdb-mid/results/generality-data/`（不入库）。

## 装载：`tools/bench-load.sh tpch|ssb|financial DATA_DIR [DBNAME]`
与 `tools/tpcds-load.sh` 相同的约定：事实表不建主键（粒度与日期列上建普通索引），维表保留主键；事实表金额列一律 numeric(18,2)
（单位变化 ×100 后能逐字节还原）；SCD2 改写的 TPC-H 属性 p_brand、c_mktsegment 由 char(10) 改为 varchar(20)；标识符小写不加引号。
改名只有一处：financial 的表 `order`（保留字）→ `orders`；district 的 A2–A16 → a2–a16。`date` 作表名或列名不加引号可用（PG 18 上验证）。
SSB 的 d_date 是文本，另加 DATE 列 d_fulldate（由 d_datekey 换算）。

## 模式说明：`schemas/<name>.json`
事实表（粒度、日期列、可平移的新键列、金额列）、维表（键、SCD2 改写的属性、引用它的列）、日历、学习与留出年份（均为 1996 / 1997，
两年各月都有数据），以及每种变化作用的表。TPC-H 的 orders 既是事实表，也被 lineitem 按 o_orderkey 引用（`refs`）；
向 lineitem 追加新订单号的行时，若不同时追加 orders，lineitem → orders 的内连接会丢掉这些行。

## 定义库：`tools/bench-library.py --spec … --queries … --db … --out libs/<name>.json --notes libs/<name>-notes.json`
做法与 `tools/tpcds-library.py` 相同（一个 SELECT 块里对一张事实表的聚合算一个定义），差别见脚本说明：事实表是能经多对一关联
到达块内全部表的那张；关联可成链、须落在一侧的主键或粒度上、构成一棵树；度量与过滤中的列一律写成 表.列；日期列日历的时间列
是带日期（或年份）字面量的谓词所在的列，没有时取事实表的日期列；BIRD 的 SQLite 写法（反引号、双引号字符串、SUM(布尔)）先转换或舍弃。

| 模式 | 查询 | 定义 | 按事实表 | 带关联 | 关联成链 | 带过滤 | 去重 | 舍弃的谓词或块 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TPC-H | 22 | 13 | lineitem 11，orders 2 | 8 | 4 | 7 | 1（q20 块 3 = q01） | 子查询 5，多表或解析不到 3，非树关联 1（q05：c_nationkey = s_nationkey），到不了的表 1（q19：关联在 OR 内），日期字面量 1，引用时间列 1 |
| SSB | 13 | 11 | lineorder 11 | 8 | 0 | 11 | 2（q3_4 = q3_3，q4_2 = q4_1：去掉期间后相同） | 无 |
| financial | 106 | 12 | loan 8，trans 4 | 8 | 3 | 10 | 0 | 非多对一树 6（经 disp / client 的一对多），SUM(布尔) 1，解析失败 1（LIMIT #,#） |

TPC-H 有 1 个定义的时间列在直连表上（q10：orders.o_orderdate）。

## 检查（`libcheck.py SPEC LIB URL`，noctis 上运行）
每张事实表在粒度上唯一、每张维表键唯一；按规范编译的写法（关联、过滤、期间谓词）对每个定义计算学习月（1996-03）与留出月（1997-09）：
SSB 11 个全部为正值；TPC-H 13 个中 11 个为正值，q10（l_returnflag = 'R'）为 NULL、q21（o_orderstatus = 'F'）为 0——TPC-H 只给
1995 年 6 月前的行设置这两个取值，在 1996/1997 的期间上恒为空；financial 的 loan 每月只有 5–23 笔，12 个定义中
bird117 / 118 / 136 / 192（学习月为 0 或 NULL）、bird135 / 160 / 191（两个月都为 0）取值退化，loan 上的 bird90 / 137 两个月都为 1，trans 上的 bird145 / 150 / 170 正常。

## 支持度筛选：`tools/bench-support.py SPEC LIB URL OUT` → `libs/<name>-kept.json`
只保留学习题（学习年 3 月）在初始数据上答案非空、非零的定义：退化的定义在任何变化下都给出同一个常数，各方法都“答对”，不反映维护。
TPC-H 去掉 q10、q21 两个，保留 11 个；SSB 全部 11 个；financial 去掉 7 个 loan 定义与 bird135，保留 5 个（bird90、bird137、bird145、bird150、bird170）。

## 回放：`replay-bench --spec`（2026-10-10）
变化由 `src/specchange.rs` 按模式说明生成（与 TPC-DS 的手写变化同一套 11 种、同一种“业务事实 / 表示”两步与回滚核对），区分列
row_status、is_current、source_system 在准备阶段加入；标准答案 = 原定义加区分列过滤后的规范 SQL，在业务事实改变后、表示改变前计算；
dbt 式表级测试由模式说明推出（粒度唯一、维表键唯一与非空、参照完整性、日期列非空）。TPC-H 的 lineitem 以 l_linenumber 为新键
（追加的明细挂在已有订单上，不在 lineitem → orders 上形成孤儿）。

```
agentdb-mid --pool 16 --out results/generality replay-bench --spec exp/2026-10-11-generality/schemas/<name>.json \
  --libs exp/2026-10-11-generality/libs/<name>-kept.json --policies condition,schema,revoke,tabletest --oracles snapshot --sql-timeout-secs 1800
```
整定义重查与查询缓存不在这三种模式上运行（与 TPC-DS 相同：600 万行上每个受影响定义各做一次修复搜索）。

在新模式上发现、在 TPC-DS 上不出现的两个维护错误（9f92cae 已修，存档的 TPC-DS 与合成数据回放核对过不受影响）：
- 粒度修复把找到的过滤替换了定义自己在事实表上的过滤（financial：trans.bank = 'AB' 被换成 trans.is_current = '1'），
  回归测试因此拒绝了正确的修复；现在两者合取。
- 表对的关联验证先试“大表在左”，一对一关联（loan–account）和比维表小的事实表得到相反方向的路径；现在按定义的方向验证。

SSB 的 yyyymmdd 日期键在月界处跳号：日期键按月连续的检查在 84 个月中 83 个月不成立（`ssb-contiguity.json`），
键范围改写的前提检查因此在 SSB 上拒绝该改写。
