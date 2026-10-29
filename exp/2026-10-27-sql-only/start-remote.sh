#!/usr/bin/env bash
set -euo pipefail
umask 077
log=results/launcher-20261027.log
if [ -e "$log" ]; then
    printf 'A launcher log already exists; refusing to start a duplicate run.\n' >&2
    exit 1
fi
nohup bash exp/2026-10-27-sql-only/run.sh > "$log" 2>&1 < /dev/null &
printf '%s\n' "$!" > results/launcher-20261027.pid
printf 'Started launcher PID %s; log: %s\n' "$!" "$log"
