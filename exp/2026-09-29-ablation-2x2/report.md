# 2×2 消融与专项测试

配置：`{"agents":24,"rounds":4,"rows":1000000,"seed":42,"tasks":48}`，构建："release"。

|组别|跨 Agent 共享|检查顺序|
|---|---|---|
|A 基线|否|固定|
|B 只加共享|是|固定|
|C 只加反馈|否|自反馈|
|D 组合方案|是|自反馈|

## 指标

主矩阵关闭 singleflight；四组均使用守护、结果缓存与相同的候选级审计规则。A/C 保留每个 Agent 自己的跨会话记忆，经验与反馈不跨 Agent 传播。反馈为内置反馈排序，不调用 LLM。

|组别|请求|符合预期|P95 ms|请求/秒|测量 SQL|测量 DB ms|含训练 SQL|含训练 DB ms|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|A|4608|4608|113.93|1589.44|1095.0|38540.85|3495|310310.09|
|B|4608|4608|27.39|2795.15|462.0|19152.32|562|30184.55|
|C|4608|4608|112.49|1596.13|1101.0|39032.32|3501|312345.70|
|D|4608|4608|37.53|2806.88|473.0|20205.13|573|31318.87|

## 成对消融

Δ=目标组−基线组，成本指标为负表示减少。降幅=(基线−目标)/基线；正数为节约，负数为退化。报告均值和每轮范围，不作显著性声明。

|对比|平均 DB 成本降幅|最小—最大|平均 SQL Δ|
|---|---:|---:|---:|
|共享收益 B−A|50.27%|48.09% — 51.87%|-158.25|
|反馈收益 C−A|-1.31%|-4.19% — 1.70%|1.50|
|共享后的反馈收益 D−B|-5.48%|-9.82% — 0.31%|2.75|
|反馈后的共享收益 D−C|48.17%|44.46% — 53.12%|-157.00|
|整体收益 D−A|47.54%|44.68% — 51.65%|-155.50|

## 交互项

成本交互项 = D−B−C+A。负数才表示超出简单相加的额外节约；D 优于 A 本身不能证明协同。

|轮次|成本交互项 ms|
|---|---:|
|1|509.85|
|2|-199.92|
|3|572.95|
|4|-321.55|

## 专项 1：并发合并

关闭结果缓存，8 个 Agent 同步执行相同真实汇总；只切换 singleflight。

|启用|请求|实际 SQL 执行|合并|墙钟秒|
|---|---:|---:|---:|---:|
|false|8|8|0|0.139|
|true|8|1|7|0.096|

## 专项 2：守护

正确金额为 5919963.6；ETL 增加 98604 条状态行。关闭结果缓存避免旧金额掩盖错误，仅比较守护开关。

```json
[
  {
    "amount": 7379280.0,
    "corrected": null,
    "guard": "Off",
    "join": {
      "path": {
        "evidence": [
          "store_sales 1000000 行中 400000 行关联得上（60.0% 关联不上）"
        ],
        "filters": {},
        "left": "store_sales",
        "left_unique": true,
        "loss_ratio": 0.6,
        "n_join": 400000,
        "n_left": 1000000,
        "on": [
          [
            "ss_ticket_number",
            "sr_ticket_number"
          ],
          [
            "ss_item_sk",
            "sr_item_sk"
          ]
        ],
        "right": "store_returns",
        "right_unique": true
      },
      "source": "reused",
      "valid": true
    },
    "relative_error_percent": 24.650766433766602,
    "stats": {
      "db": {
        "by_kind": {
          "check": [
            4,
            1979.672
          ],
          "exec": [
            1,
            74.205
          ],
          "guard": [
            0,
            0.0
          ],
          "meta": [
            8,
            28.727
          ],
          "probe": [
            0,
            0.0
          ],
          "repair": [
            0,
            0.0
          ]
        },
        "db_ms": 2082.6040000000003,
        "queries": 13
      },
      "entries": 5,
      "feedback": {
        "adaptive": null,
        "adaptive_uses": 0,
        "contexts": {
          "KeyUnique|store_returns(sr_ticket_number,sr_item_sk)": {
            "fails": 0,
            "hits": 0,
            "mrows": 0.6,
            "ms": 367.011957,
            "runs": 1
          },
          "KeyUnique|store_sales(ss_ticket_number,ss_item_sk)": {
            "fails": 0,
            "hits": 0,
            "mrows": 1.5,
            "ms": 1324.467684,
            "runs": 1
          },
          "RowConservation|store_sales>store_returns:(ss_ticket_number=sr_ticket_number, ss_item_sk=sr_item_sk)": {
            "fails": 0,
            "hits": 0,
            "mrows": 2.4,
            "ms": 284.91300800000005,
            "runs": 1
          },
          "SampleFanout|store_sales>store_returns:(ss_ticket_number=sr_ticket_number, ss_item_sk=sr_item_sk)": {
            "fails": 0,
            "hits": 0,
            "mrows": 0.4,
            "ms": 3.3415850000000002,
            "runs": 1
          }
        },
        "epoch": 0,
        "evaluation": "frozen scorer; future distinct candidate groups; observed incremental costs",
        "evidence": {
          "audited_failures_in_window": 0,
          "audited_failures_total": 0,
          "min_evidence": 8,
          "passed": 1,
          "unaudited_failures": 0
        },
        "kinds": {
          "KeyUnique": {
            "fails": 0,
            "hits": 0,
            "mrows": 2.1,
            "ms": 1691.479641,
            "runs": 2
          },
          "RowConservation": {
            "fails": 0,
            "hits": 0,
            "mrows": 2.4,
            "ms": 284.91300800000005,
            "runs": 1
          },
          "SampleFanout": {
            "fails": 0,
            "hits": 0,
            "mrows": 0.4,
            "ms": 3.3415850000000002,
            "runs": 1
          }
        },
        "order_calls": 1,
        "pending_validation": null,
        "policy": null
      },
      "guard_fails": 0,
      "guard_runs": 0,
      "inflight_merged": 0,
      "knowledge_hits": 1,
      "knowledge_misses": 5,
      "notices": 0,
      "repairs": 0,
      "revocations": 0,
      "sql_rejections": 0
    },
    "unfiltered_result": {
      "result": {
        "columns": [
          "sum"
        ],
        "row_count": 1,
        "rows": [
          [
            "7379280.00"
          ]
        ],
        "truncated": false
      },
      "source": "executed"
    }
  },
  {
    "amount": null,
    "corrected": {
      "result": {
        "columns": [
          "sum"
        ],
        "row_count": 1,
        "rows": [
          [
            "5919963.60"
          ]
        ],
        "truncated": false
      },
      "source": "executed"
    },
    "guard": "OnChange",
    "join": {
      "notices": [
        "你用过的经验「join:store_returns|store_sales」已撤销（守卫失败：store_returns(sr_ticket_number, sr_item_sk) 是否唯一，498604 行只有 400000 个不同键（平均每键 1.25 行））。此前基于它得到的结果建议复核。"
      ],
      "path": {
        "evidence": [
          "store_sales 1000000 行中 400000 行关联得上（60.0% 关联不上）",
          "store_returns 需过滤 sr_status = '完成' 才能保持每键一行"
        ],
        "filters": {
          "store_returns": "sr_status = '完成'"
        },
        "left": "store_sales",
        "left_unique": true,
        "loss_ratio": 0.6,
        "n_join": 400000,
        "n_left": 1000000,
        "on": [
          [
            "ss_ticket_number",
            "sr_ticket_number"
          ],
          [
            "ss_item_sk",
            "sr_item_sk"
          ]
        ],
        "right": "store_returns",
        "right_unique": true
      },
      "source": "revalidated",
      "valid": true
    },
    "relative_error_percent": null,
    "stats": {
      "db": {
        "by_kind": {
          "check": [
            7,
            2699.752
          ],
          "exec": [
            1,
            72.134
          ],
          "guard": [
            1,
            2659.472
          ],
          "meta": [
            19,
            54.177
          ],
          "probe": [
            0,
            0.0
          ],
          "repair": [
            2,
            4720.584
          ]
        },
        "db_ms": 10206.119,
        "queries": 30
      },
      "entries": 9,
      "feedback": {
        "adaptive": null,
        "adaptive_uses": 0,
        "contexts": {
          "KeyUnique|store_returns(sr_ticket_number,sr_item_sk)": {
            "fails": 0,
            "hits": 0,
            "mrows": 1.2,
            "ms": 733.27234,
            "runs": 2
          },
          "KeyUnique|store_sales(ss_ticket_number,ss_item_sk)": {
            "fails": 0,
            "hits": 1,
            "mrows": 1.5,
            "ms": 1313.365747,
            "runs": 1
          },
          "RowConservation|store_sales>store_returns:(ss_ticket_number=sr_ticket_number, ss_item_sk=sr_item_sk)": {
            "fails": 0,
            "hits": 0,
            "mrows": 4.8,
            "ms": 646.8163529999999,
            "runs": 2
          },
          "SampleFanout|store_sales>store_returns:(ss_ticket_number=sr_ticket_number, ss_item_sk=sr_item_sk)": {
            "fails": 0,
            "hits": 0,
            "mrows": 0.8,
            "ms": 6.443393,
            "runs": 2
          }
        },
        "epoch": 0,
        "evaluation": "frozen scorer; future distinct candidate groups; observed incremental costs",
        "evidence": {
          "audited_failures_in_window": 0,
          "audited_failures_total": 0,
          "min_evidence": 8,
          "passed": 2,
          "unaudited_failures": 0
        },
        "kinds": {
          "KeyUnique": {
            "fails": 0,
            "hits": 1,
            "mrows": 2.7,
            "ms": 2046.638087,
            "runs": 3
          },
          "RowConservation": {
            "fails": 0,
            "hits": 0,
            "mrows": 4.8,
            "ms": 646.8163529999999,
            "runs": 2
          },
          "SampleFanout": {
            "fails": 0,
            "hits": 0,
            "mrows": 0.8,
            "ms": 6.443393,
            "runs": 2
          }
        },
        "order_calls": 2,
        "pending_validation": null,
        "policy": null
      },
      "guard_fails": 1,
      "guard_runs": 1,
      "inflight_merged": 0,
      "knowledge_hits": 3,
      "knowledge_misses": 8,
      "notices": 1,
      "repairs": 1,
      "revocations": 1,
      "sql_rejections": 1
    },
    "unfiltered_result": {
      "reason": "表 store_returns 现在每个键有多行（状态流水）；统计前需要加过滤 sr_status = '完成'，否则会重复计算",
      "rejected": true,
      "required_filter": {
        "filter": "sr_status = '完成'",
        "table": "store_returns"
      }
    }
  }
]
```

## 复现与解释边界

- 四组共用同样大小的数据库池、数据、任务序列；A/C 的每 Agent 状态独立，B/D 全局共享。共享收益包含画像、关联、检查、结果、版本读取及反馈经验的复用。
- 相同逻辑训练对所有 Agent 执行，测量指标不含训练；含训练成本另列，避免隐藏不共享组的重复学习成本。
- 主矩阵只用稳定 v1 数据，ETL 和 singleflight 分别做专项，不混入两个主因素。
- 审计按固定种子与候选签名抽取，阈值20%；同一候选的开关不因模式、先失败检查或并发调度改变。实际有限候选抽中比例不保证恰为20%。
- 每轮轮换顺序；建议轮数为4的倍数以平衡位置。数据库预热但不清空 OS 缓存。毫秒值仍受调度影响。
- 使用并发脚本 Agent 直接调用工具层，不包含 HTTP、真实 LLM 或 token 成本。D 是共享+内置反馈，不等同于已证明真实模型收益。
- 逐轮 JSON 保留请求输入、预期、实际结果与检查轨迹；source 区分执行、复用、合并。正确拒绝也计作符合预期。
