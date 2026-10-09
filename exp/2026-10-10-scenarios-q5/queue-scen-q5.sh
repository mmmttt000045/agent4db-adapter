#!/bin/bash
# 2026-10-10 场景主实验重跑：题集 v2（每个指标 5 道计分题）、9 种方法 × 5 次独立重复 × 11 种变化，
# 模型与 10-02 相同（cline-pass/deepseek-v4.1-flash），100 万行，题面只给指标名。
# 每轮 9 种方法按轮次轮换顺序后分成 3 个进程（每个 3 种方法）；并发上限读 $OUT/concurrency（ClinePass 不超过 6），
# 相邻启动至少间隔 60 秒。二进制须含 7e9b532（--question-set v2）。
cd /root/agentdb-mid
OUT=results/scen-20261010
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 6 > $OUT/concurrency
MODEL=deepseek-v4.1-flash
MODES=(middle traj-global traj-verify metric-global-schema metric-global-revoke metric-global-def metric-global-snap metric-global-exref metric-global)
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
rot() { local k=$1; shift; local a=("$@"); local n=${#a[@]}; local out=(); for i in $(seq 0 $((n-1))); do out+=("${a[$(((i+k)%n))]}"); done; (IFS=,; echo "${out[*]}"); }
JOBS=()
for r in 1 2 3 4 5; do
  all=$(rot $((2*(r-1))) "${MODES[@]}")
  IFS=, read -ra m <<< "$all"
  JOBS+=("dsv41flash-r$r-a|${m[0]},${m[1]},${m[2]}")
  JOBS+=("dsv41flash-r$r-b|${m[3]},${m[4]},${m[5]}")
  JOBS+=("dsv41flash-r$r-c|${m[6]},${m[7]},${m[8]}")
done
for j in "${JOBS[@]}"; do
  IFS="|" read -r tag modes <<< "$j"
  while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ]; do sleep 30; done
  mkdir -p $OUT/$tag
  echo "$(date "+%F %T") start $tag ($MODEL): $modes" >> $OUT/queue.log
  ( CLINE_MODEL=cline-pass/$MODEL ./target/release/agentdb-mid --pool 16 --out $OUT/$tag metric-bench \
      --agent cline --extractor cline --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 --question-set v2 \
      --modes $modes --changes $CHANGES > $OUT/$tag.log 2>&1 < /dev/null
    echo "$(date "+%F %T") exit $? $tag" >> $OUT/queue.log ) &
  sleep 60
done
wait
echo "$(date "+%F %T") all done" >> $OUT/queue.log
