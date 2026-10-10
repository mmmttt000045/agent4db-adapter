#!/bin/bash
# 通用性端到端：TPC-H 上的场景实验，无记忆 / 示例检索 / MAVRA × 3 次独立重复 × 11 种变化，
# 题集 v2，题面只给指标名；其余与 exp/2026-10-10-scenarios-q5 相同。数据、变化与标准答案来自模式描述（metric-bench --spec）。
# 模型服务：happycoding 网关的 deepseek-v4.1-flash（2026-10-10 用户指定；回报模型 deepseek/deepseek-v4.1-flash，
# HAPPY_REQUIRE_MODEL 丢弃不符的回复）。TPC-H 每个进程两份 1.5 GB 的库，并发 4。
cd /root/agentdb-mid
OUT=results/e2e-tpch
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 4 > $OUT/concurrency
AGENT=${AGENT:-happy}
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
MODES=(middle traj-global metric-global-snap)
for r in 1 2 3; do
  for k in 0 1 2; do
    mode=${MODES[$(((k + r - 1) % 3))]}
    tag=r$r-$mode
    while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ]; do sleep 30; done
    mkdir -p $OUT/$tag
    echo "$(date "+%F %T") start $tag ($AGENT)" >> $OUT/queue.log
    ( ./target/release/agentdb-mid --pool 16 --out $OUT/$tag metric-bench \
        --agent $AGENT --extractor $AGENT --spec exp/2026-10-11-generality/schemas/tpch.json \
        --defs exp/2026-10-11-generality/e2e/tpch-defs.json --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 \
        --question-set v2 --sql-timeout-secs 120 --modes $mode --changes $CHANGES > $OUT/$tag.log 2>&1 < /dev/null
      echo "$(date "+%F %T") exit $? $tag" >> $OUT/queue.log ) &
    sleep 60
  done
done
wait
echo "$(date "+%F %T") all done" >> $OUT/queue.log
