#!/usr/bin/env bash
set -euo pipefail
umask 077
export HAPPY_MODEL=deepseek-v4.1-flash
export HAPPY_REQUIRE_MODEL=deepseek/deepseek-v4.1-flash-1017
export HAPPY_REASONING_EFFORT=low
export HAPPY_THINKING=enabled
export HAPPY_HEDGE=1
export OMP_WAIT_POLICY=PASSIVE
export PYTHONPATH=.pydeps-relbench

out=results/sql-only-20261027
mkdir -p "$out"
trap 'rc=$?; if [ "$rc" -ne 0 ]; then python3 exp/2026-10-27-sql-only/status.py failed "$rc"; fi' EXIT
python3 exp/2026-10-27-sql-only/status.py preflight
python3 tools/relbench/test_sql_only.py
python3 exp/2026-10-27-sql-only/preflight.py
python3 exp/2026-10-27-sql-only/provenance.py
tar --exclude=__pycache__ -czf "$out/source-as-run.tar.gz" tools/relbench src target/release/agentdb-mid exp/2026-10-27-sql-only

python3 exp/2026-10-27-sql-only/status.py rel-stack
python3 tools/relbench/run-queue.py exp/2026-10-27-sql-only/cells-stack.txt --out "$out" --parallel 2 --memory-max 24G --min-free-gb 20
python3 exp/2026-10-27-sql-only/gate.py rel-stack

python3 exp/2026-10-27-sql-only/status.py rel-trial
python3 tools/relbench/run-queue.py exp/2026-10-27-sql-only/cells-trial.txt --out "$out" --parallel 2 --memory-max 24G --min-free-gb 20
python3 exp/2026-10-27-sql-only/gate.py rel-trial
python3 tools/relbench/sql-only-stats.py --root "$out" --out "$out"
python3 exp/2026-10-27-sql-only/status.py completed 0
