#!/bin/bash
# 2026-10-12 群体评测（共享 vs 单智能体记忆）：4 组 × 5 次独立重复，100 万行合成零售数据，题集 v2，5 个指标。
# 每组一个进程：16 个智能体依次到来（同时在场 1 个），各答 7 道抽样题；施加“更正保留旧行”后同一批智能体各再答 4 道
# 读到被写入表的题。第 r 次重复的抽题由 --first-repeat r 决定，四组相同（配对）。
# 同时运行的进程数读 $OUT/concurrency（默认 10），相邻启动间隔 30 秒。模型：happycoding 网关 deepseek-v4.1-flash（智能体与提炼器）。
cd /root/agentdb-mid
OUT=results/pop-20261012
mkdir -p $OUT
[ -f $OUT/concurrency ] || echo 10 > $OUT/concurrency
MODES=(metric-global-snap metric-private traj-global middle)
JOBS=()
for r in 1 2 3 4 5; do
  for m in "${MODES[@]}"; do
    JOBS+=("r$r-$m|$m|$r")
  done
done
# 网关可用性：一次最小请求（10-12 11:47 起曾出现额度耗尽，403 insufficient_user_quota）
probe() {
  ( set -a; . ./.env; set +a
    curl -s -m 120 "$HAPPY_BASE_URL/chat/completions" -H "Authorization: Bearer $HAPPY_API_KEY" -H "Content-Type: application/json" \
      -d "{\"model\":\"$HAPPY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly OK.\"}],\"max_tokens\":512}" ) \
    | grep -q '"choices"'
}
for j in "${JOBS[@]}"; do
  IFS="|" read -r tag mode r <<< "$j"
  # 已完成的组（有 report.json）跳过
  ls $OUT/$tag/metric-*/report.json > /dev/null 2>&1 && continue
  while [ "$(jobs -rp | wc -l)" -ge "$(cat $OUT/concurrency)" ]; do sleep 30; done
  if ! probe; then echo "$(date "+%F %T") probe failed before $tag; queue stopped" >> $OUT/queue.log; break; fi
  mkdir -p $OUT/$tag
  echo "$(date "+%F %T") start $tag" >> $OUT/queue.log
  ( ./target/release/agentdb-mid --pool 8 --out $OUT/$tag metric-bench \
      --agent happy --extractor happy --metrics M1,M2,M3,M4,M5 --phrasings named --repeats 1 --first-repeat $r \
      --question-set v2 --modes $mode --population --agents 16 --per-agent 7 --returning 4 --pop-change revision \
      --concurrency 1 > $OUT/$tag.log 2>&1 < /dev/null
    echo "$(date "+%F %T") exit $? $tag" >> $OUT/queue.log ) &
  sleep 30
done
wait
echo "$(date "+%F %T") all done" >> $OUT/queue.log
