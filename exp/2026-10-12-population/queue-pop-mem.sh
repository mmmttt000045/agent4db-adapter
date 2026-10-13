#!/bin/bash
# 2026-10-13 已发表的单智能体记忆作为基线（提交 81a4ebd）：AWM、ACE、Mem0、AgentSM 各自按智能体私有，ACE 与 AgentSM 另各有一个共享版本。
# 设置与 queue-pop-tpcds2.sh 相同（16 个智能体 × 7 题，更正后各回答 4 道，同一抽题配对），每组 3 次重复。
# 用法：queue-pop-mem.sh r1-mem-awm r1-mem-ace ...（标签 = r<重复>-<组>）；
# MIN_FREE（默认 12）：剩余磁盘低于这么多 GB 时不启动新组（每组复制一份 2.4 GB 的模板库）。WAIT_QUOTA=1 时先等网关额度恢复。
cd /root/agentdb-mid
OUT=results/pop-mem-20261013
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 6 > $OUT/concurrency
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
