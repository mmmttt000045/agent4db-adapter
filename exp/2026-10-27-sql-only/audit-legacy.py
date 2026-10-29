"""Audit the completed 10-22 SQL-only cell against its archived hashes and historical paper data.

Run with UTF-8 mode from the repository root. Raw 10-22 session files must first be copied from
the path recorded in the experiment index. This is a descriptive cross-batch diagnostic only.
"""
import hashlib
import importlib.util
import json
import statistics
from pathlib import Path

status = json.loads(Path('exp/2026-10-22-sql-only/status.json').read_text(encoding='utf-8'))
expected = status['cells']['sql-only-rel-stack-r1']['files_sha256']
bad = [name for name, digest in expected.items()
       if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest]
if bad:
    raise RuntimeError(f'legacy files do not match archived hashes: {bad}')
spec = importlib.util.spec_from_file_location('sql_stats', 'tools/relbench/sql-only-stats.py')
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)
meta, rows, _ = stats.load(Path('results/sql-only-20261022/sql-only-rel-stack-r1'))
historical = json.loads(Path('exp/2026-10-20-relbench/paper-sessions.json').read_text(encoding='utf-8'))['rel-stack']['mavra']
result = {
    'scope': 'Historical, different provider and run batch; not the new paired result.',
    'verified_files': len(expected),
    'sql_only_model': meta['settings']['require_model'],
    'sql_only_all': stats.aggregate(list(rows.values())),
    'sql_only_reuse': stats.aggregate([r for r in rows.values() if r['k'] >= 2]),
    'historical_mavra_all_tokens': sum(r['tokens'] for r in historical),
    'historical_mavra_reuse_tokens': sum(r['tokens'] for r in historical if r['k'] >= 2),
    'historical_mavra_test_means': {
        task: statistics.mean(r['test'] for r in historical if r['task'] == task)
        for task in sorted({r['task'] for r in historical})
    },
}
print(json.dumps(result, indent=2, ensure_ascii=False))
