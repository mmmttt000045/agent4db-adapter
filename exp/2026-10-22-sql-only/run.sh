#!/usr/bin/env bash
set -euo pipefail

# Run from the isolated experiment root on noctis. Credentials stay in its private .env.
export HAPPY_MODEL=deepseek-v4.1-flash
export HAPPY_REQUIRE_MODEL=deepseek/deepseek-v4.1-flash-1017
export HAPPY_REASONING_EFFORT=low
export HAPPY_THINKING=enabled
export HAPPY_HEDGE=1
export OMP_WAIT_POLICY=PASSIVE

PYTHONPATH=.pydeps-relbench python3 tools/relbench/test_sql_only.py
python3 - <<'PY'
import hashlib
import json
import platform
from pathlib import Path
from datetime import datetime, timezone

files = [Path('target/release/agentdb-mid'), *Path('tools/relbench').glob('*.py'),
         *Path('src').rglob('*.rs'), *Path('exp/2026-10-22-sql-only').glob('*.sh'),
         Path('exp/2026-10-22-sql-only/cells.txt')]
for db in ('rel-stack', 'rel-trial'):
    files += [Path(f'results/relbench-data/{db}/manifest.yaml'),
              Path(f'results/relbench-data/{db}-prep/timeline.json')]
record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'host': platform.node(),
          'python': platform.python_version(),
          'files': {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
Path('exp/2026-10-22-sql-only/run-provenance.json').write_text(json.dumps(record, indent=2))
PY

python3 tools/relbench/run-queue.py exp/2026-10-22-sql-only/cells.txt \
    --out results/sql-only-20261022 --parallel 2 --memory-max 24G --min-free-gb 20
python3 tools/relbench/sql-only-stats.py --root results/sql-only-20261022 \
    --out exp/2026-10-22-sql-only
