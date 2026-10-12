#!/bin/bash
# 2026-10-12 群体评测第二版（TPC-DS SF1）：4 组 × 5 次独立重复。见 README“第二版设计”。
# 每组一个进程：16 个智能体依次到来（同时在场 1 个），各答 7 道抽样题；施加“更正保留旧行”后同一批智能体各再答 4 道
# 读到 store_sales 的题。第 r 次重复的抽题由 --first-repeat r 决定，四组相同（配对）。
# 同时运行的进程数读 $OUT/concurrency（默认 5：每组复制 2.4 GB 模板库，snap / private 再复制一份学习时快照库）；
# 剩余磁盘低于 12 GB 时不启动新组。模型：happycoding 网关 deepseek-v4.1-flash（智能体与提炼器）。
cd /root/agentdb-mid
OUT=results/pop-tpcds-20261012
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 5 > $OUT/concurrency
MODES=(middle-alone metric-private metric-global-snap traj-global)
JOBS=()
for r in 1 2 3 4 5; do
  for m in "${MODES[@]}"; do
    JOBS+=("r$r-$m|$m|$r")
  done
done
probe() {
  ( set -a; . ./.env; set +a
    curl -s -m 120 "$HAPPY_BASE_URL/chat/completions" -H "Authorization: Bearer $HAPPY_API_KEY" -H "Content-Type: application/json" \
      -d "{\"model\":\"$HAPPY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly OK.\"}],\"max_tokens\":512}" ) \
    | grep -q '"choices"'
}
free_gb() { df -BG --output=avail / | tail -1 | tr -dc 0-9; }
for j in "${JOBS[@]}"; do
  IFS="|" read -r tag mode r <<< "$j"
  ls $OUT/$tag/metric-*/report.json > /dev/null 2>&1 && continue
  while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ] || [ "$(free_gb)" -lt 12 ]; do sleep 30; done
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
echo "$(date "+%F %T") all done" >> $OUT/queue.log
