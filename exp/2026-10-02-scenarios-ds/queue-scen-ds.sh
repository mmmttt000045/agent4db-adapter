#!/bin/bash
# 2026-10-02 起的场景主实验（先只用 cline-pass/deepseek-v4.1-flash，设计定下后再补其他模型）。
# 7 种方法 × 3 次重复 × 11 种变化（原 10 种 + 备份副本），当前二进制（修复唯一性、等待修复默认打开）。
# 并发上限读 $OUT/concurrency（ClinePass 不超过 6 个并发请求），相邻启动至少间隔 60 秒。
cd /root/agentdb-mid
OUT=results/scen-20261002
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 6 > $OUT/concurrency
MODEL=deepseek-v4.1-flash
MODES=(middle traj-global metric-global-noguard metric-global-schema metric-global-revoke metric-global-def metric-global)
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
rot() { local k=$1; shift; local a=("$@"); local n=${#a[@]}; local out=(); for i in $(seq 0 $((n-1))); do out+=("${a[$(((i+k)%n))]}"); done; (IFS=,; echo "${out[*]}"); }
JOBS=()
for r in 1 2 3; do
  all=$(rot $((2*(r-1))) "${MODES[@]}")
  IFS=, read -ra m <<< "$all"
  JOBS+=("dsv41flash-r$r-a|${m[0]},${m[1]},${m[2]},${m[3]}")
  JOBS+=("dsv41flash-r$r-b|${m[4]},${m[5]},${m[6]}")
done
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
echo "$(date "+%F %T") all done" >> $OUT/queue.log
