#!/bin/bash
# 把 queue-scen-ds.sh 启动的各组在“刚完成一组单元”时切换到新二进制（12:02 修复了被包成 HTTP 500 的上游限流），
# 已完成的单元保留，刚开始的单元作废重来；只做一次切换。之后各组跑完时在 queue.log 记 exit。
cd /root/agentdb-mid
OUT=results/scen-20261002
URL=$(grep "^AGENTDB_URL=" .env | cut -d= -f2-)
CHANGES=append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror
log() { echo "$(date "+%F %T") $*" >> $OUT/queue.log; }
done_modes() { ls $OUT/$1/metric-*/cell-r1-*-named.json 2>/dev/null | sed -E "s/.*cell-r1-(.*)-named.json/\1/" | sort -u; }
switch() {
  local tag=$1 modes=$2
  local pid=$(pgrep -f -- "--out $OUT/$tag metric-bench" | head -1)
  [ -z "$pid" ] && { log "supervise: $tag not running"; return; }
  local before=$(done_modes $tag | wc -l)
  while [ "$(done_modes $tag | wc -l)" -eq "$before" ] && kill -0 $pid 2>/dev/null; do sleep 15; done
  kill -0 $pid 2>/dev/null || { log "supervise: $tag exited before switch"; return; }
  local rest=$(for m in ${modes//,/ }; do done_modes $tag | grep -qx "$m" || echo $m; done | paste -sd,)
  kill $pid; sleep 5
  for db in $(psql "$URL" -Atc "select datname from pg_database where datname like agentdb_metric__%"); do psql "$URL" -qc "drop database $db with (force)"; done
  if [ -z "$rest" ]; then log "supervise: $tag finished all modes"; return; fi
  log "supervise: restart $tag with new binary: $rest"
  CLINE_MODEL=cline-pass/deepseek-v4.1-flash ./target/release/agentdb-mid --pool 16 --out $OUT/$tag metric-bench \
    --agent cline --extractor cline --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 \
    --modes $rest --changes $CHANGES >> $OUT/$tag.log 2>&1 < /dev/null
  log "exit $? $tag (supervised)"
}
while read -r tag modes; do switch $tag $modes & sleep 2; done < <(grep " start " $OUT/queue.log | sed -E "s/.* start ([^ ]+) \(.*\): (.*)/\1 \2/")
wait
log "all done (supervised)"
