#!/bin/bash
# 按预先写定的规则重跑：学习或重新学习阶段出现服务端失败的组整组重跑（同一方法、同一重复编号），用修复后的二进制。
# 有空位（运行中的 metric-bench 少于 6 个）才启动，相邻启动间隔 60 秒。被替换的原组写进 $OUT/replaced.txt，统计时排除。
cd /root/agentdb-mid
OUT=results/scen-20261002
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
log() { echo "$(date '+%F %T') $*" >> $OUT/queue.log; }
RERUNS=(
  "dsv41flash-r2-b-rerun|metric-global|dsv41flash-r2-b/cell-r1-metric-global-named"
  "dsv41flash-r3-a-rerun|metric-global-revoke|dsv41flash-r3-a/cell-r1-metric-global-revoke-named"
  "dsv41flash-r1-b-rerun|metric-global-revoke|dsv41flash-r1-b/cell-r1-metric-global-revoke-named"
)
running() { pgrep -fc -- "--out $OUT/.* metric-bench" || true; }
for j in "${RERUNS[@]}"; do
  IFS='|' read -r tag mode replaced <<< "$j"
  while [ "$(running)" -ge 6 ]; do sleep 60; done
  echo "$replaced" >> $OUT/replaced.txt
  mkdir -p $OUT/$tag
  log "start $tag (rerun, replaces $replaced): $mode"
  ( CLINE_MODEL=cline-pass/deepseek-v4.1-flash ./target/release/agentdb-mid --pool 16 --out $OUT/$tag metric-bench \
      --agent cline --extractor cline --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 \
      --modes $mode --changes $CHANGES > $OUT/$tag.log 2>&1 < /dev/null
    log "exit $? $tag" ) &
  sleep 60
done
wait
log "reruns done"
