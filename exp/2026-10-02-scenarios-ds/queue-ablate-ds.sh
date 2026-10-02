#!/bin/bash
# 2026-10-03 增补的两种方法（见 README.md 的分析方案增补），与主实验同一输出目录、同一模型、同一参数：
#   metric-global-exref  条件级维护，修复回归（G8）以提炼出的示例 SQL 为参照（部署中真正可得的参照）
#   traj-verify          轨迹检索基线加一句“复用前先核对前提”的提示（自验证基线）
# 各 3 次独立重复，一组一个进程；并发上限读 $OUT/concurrency，相邻启动至少间隔 60 秒。
cd /root/agentdb-mid
OUT=results/scen-20261002
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 6 > $OUT/concurrency
MODEL=deepseek-v4.1-flash
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
JOBS=(dsv41flash-r1-exref\|metric-global-exref dsv41flash-r1-trajv\|traj-verify
      dsv41flash-r2-exref\|metric-global-exref dsv41flash-r2-trajv\|traj-verify
      dsv41flash-r3-exref\|metric-global-exref dsv41flash-r3-trajv\|traj-verify)
for j in "${JOBS[@]}"; do
  IFS="|" read -r tag modes <<< "$j"
  while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ]; do sleep 30; done
  mkdir -p $OUT/$tag
  echo "$(date "+%F %T") start $tag ($MODEL): $modes" >> $OUT/queue.log
  ( CLINE_MODEL=cline-pass/$MODEL ./target/release/agentdb-mid --pool 16 --out $OUT/$tag metric-bench \
      --agent cline --extractor cline --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 \
      --modes $modes --changes $CHANGES > $OUT/$tag.log 2>&1 < /dev/null
    echo "$(date "+%F %T") exit $? $tag" >> $OUT/queue.log ) &
  sleep 60
done
wait
echo "$(date "+%F %T") ablation done" >> $OUT/queue.log
