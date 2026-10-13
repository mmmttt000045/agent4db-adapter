#!/bin/bash
# 2026-10-13 群体评测第二版重跑（提交 eaee4f1 起：每道题最多查找 3 次记忆）。设置同 queue-pop-tpcds.sh。
# 用法：queue-pop-tpcds2.sh r1-metric-global-snap r1-metric-private ...（标签 = r<重复>-<组>）；
# MIN_FREE（默认 12）：剩余磁盘低于这么多 GB 时不启动新组。WAIT_QUOTA=1 时先每 5 分钟探测一次网关，直到额度恢复再开始（最多 24 小时）。中途探测失败则停止。
# 无记忆组（middle-alone）不用记忆工具，不受这次修改影响，r1–r2 从 results/pop-tpcds-20261012 复制过来。
cd /root/agentdb-mid
OUT=results/pop-tpcds-20261013
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 5 > $OUT/concurrency
probe() {
  ( set -a; . ./.env; set +a
    curl -s -m 120 "$HAPPY_BASE_URL/chat/completions" -H "Authorization: Bearer $HAPPY_API_KEY" -H "Content-Type: application/json" \
      -d "{\"model\":\"$HAPPY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly OK.\"}],\"max_tokens\":512}" ) \
    | grep -q '"choices"'
}
free_gb() { df -BG --output=avail / | tail -1 | tr -dc 0-9; }
if [ "$WAIT_QUOTA" = 1 ]; then
  echo "$(date "+%F %T") waiting for gateway quota" >> $OUT/queue.log
  for i in $(seq 288); do probe && break; sleep 300; done
fi
for tag in "$@"; do
  r=${tag%%-*}; r=${r#r}; mode=${tag#*-}
  ls $OUT/$tag/metric-*/report.json > /dev/null 2>&1 && continue
  while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ] || [ "$(free_gb)" -lt "${MIN_FREE:-12}" ]; do sleep 30; done
  if ! probe; then echo "$(date "+%F %T") probe failed before $tag; queue stopped" >> $OUT/queue.log; break; fi
  mkdir -p $OUT/$tag
  echo "$(date "+%F %T") start $tag (free $(free_gb) GB)" >> $OUT/queue.log
  ( ./target/release/agentdb-mid --pool 8 --out $OUT/$tag metric-bench \
      --agent happy --extractor happy --spec exp/2026-10-11-generality/schemas/tpcds.json \
      --defs exp/2026-10-12-population/tpcds-defs.json --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 --first-repeat $r \
      --question-set v2 --sql-timeout-secs 120 --modes $mode --population --agents 16 --per-agent 7 --returning 4 \
      --pop-change revision --concurrency 1 > $OUT/$tag.log 2>&1 < /dev/null
    echo "$(date "+%F %T") exit $? $tag" >> $OUT/queue.log ) &
  sleep 60
done
wait
echo "$(date "+%F %T") all done: $*" >> $OUT/queue.log
