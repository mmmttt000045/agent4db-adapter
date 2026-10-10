#!/bin/bash
# 通用性端到端（可选，待用户批准模型用量）：TPC-H 上的场景实验，无记忆 / 示例检索 / MAVRA × 3 次独立重复 × 11 种变化，
# 题集 v2，题面只给指标名；其余与 exp/2026-10-10-scenarios-q5 相同。数据、变化与标准答案来自模式描述（metric-bench --spec）。
# MODEL 取 ClinePass（cline-pass/...）或经用户同意的按量计费路由（deepseek/deepseek-v4.1-flash）。
cd /root/agentdb-mid
OUT=results/e2e-tpch
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 6 > $OUT/concurrency
MODEL=${MODEL:-cline-pass/deepseek-v4.1-flash}
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
MODES=(middle traj-global metric-global-snap)
for r in 1 2 3; do
  for k in 0 1 2; do
    mode=${MODES[$(((k + r - 1) % 3))]}
    tag=r$r-$mode
    while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ]; do sleep 30; done
    mkdir -p $OUT/$tag
    echo "$(date "+%F %T") start $tag ($MODEL)" >> $OUT/queue.log
    ( CLINE_MODEL=$MODEL ./target/release/agentdb-mid --pool 16 --out $OUT/$tag metric-bench \
        --agent cline --extractor cline --spec exp/2026-10-11-generality/schemas/tpch.json \
        --defs exp/2026-10-11-generality/e2e/tpch-defs.json --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 \
        --question-set v2 --sql-timeout-secs 120 --modes $mode --changes $CHANGES > $OUT/$tag.log 2>&1 < /dev/null
      echo "$(date "+%F %T") exit $? $tag" >> $OUT/queue.log ) &
    sleep 60
  done
done
wait
echo "$(date "+%F %T") all done" >> $OUT/queue.log
