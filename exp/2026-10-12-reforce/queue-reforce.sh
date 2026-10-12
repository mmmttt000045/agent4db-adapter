#!/bin/bash
# 2026-10-12 ReFoRCE 作使用者：4 组 × 3 次独立重复 × 11 种变化，题集 v2，100 万行，题面只给指标名（设置同 queue-scen-q5.sh）。
# 每个进程一组一次；同时运行的进程数读 $OUT/concurrency（默认 4），相邻启动至少间隔 60 秒。
# 模型：happycoding 网关 deepseek-v4.1-flash（学习智能体、提炼器与 ReFoRCE 相同）。二进制须含 reforce* 组。
cd /root/agentdb-mid
OUT=results/reforce-20261012
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 4 > $OUT/concurrency
MODES=(reforce-mavra reforce-static reforce-traj reforce)
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
JOBS=()
for r in 1 2 3; do
  for k in 0 1 2 3; do
    m=${MODES[$(((k + r - 1) % 4))]}
    JOBS+=("r$r-$m|$m")
  done
done
for j in "${JOBS[@]}"; do
  IFS="|" read -r tag mode <<< "$j"
  while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ]; do sleep 30; done
  mkdir -p $OUT/$tag
  echo "$(date "+%F %T") start $tag" >> $OUT/queue.log
  ( ./target/release/agentdb-mid --pool 8 --out $OUT/$tag metric-bench \
      --agent happy --extractor happy --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 --question-set v2 \
      --modes $mode --changes $CHANGES --reforce-concurrency 3 > $OUT/$tag.log 2>&1 < /dev/null
    echo "$(date "+%F %T") exit $? $tag" >> $OUT/queue.log ) &
  sleep 60
done
wait
echo "$(date "+%F %T") all done" >> $OUT/queue.log
