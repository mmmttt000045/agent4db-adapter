#!/usr/bin/env bash
set -euo pipefail
umask 077

# Create an isolated experiment root. Never overwrite the October 22 run.
old=/root/agentdb-sql-only-20261022
dest=/root/agentdb-sql-only-20261027
test -d "$old/results/relbench-data/rel-stack-prep"
test -d "$old/results/relbench-data/rel-trial-prep"
test -x "$old/target/release/agentdb-mid"
test -f "$old/recovery-tools/relbench/harness.py"
test -f "$old/recovery-tools/relbench/test_sql_only.py"
mkdir "$dest"
cp -a "$old/tools" "$old/src" "$old/third_party" "$old/target" "$dest/"
cp -p "$old/.env" "$dest/.env"
cp -p "$old/recovery-tools/relbench/harness.py" "$dest/tools/relbench/harness.py"
cp -p "$old/recovery-tools/relbench/test_sql_only.py" "$dest/tools/relbench/test_sql_only.py"
mkdir "$dest/results" "$dest/exp"
ln -s /root/agentdb-mid/results/relbench-data "$dest/results/relbench-data"
ln -s /root/agentdb-mid/.pydeps-relbench "$dest/.pydeps-relbench"
printf 'Prepared isolated experiment root: %s\n' "$dest"
