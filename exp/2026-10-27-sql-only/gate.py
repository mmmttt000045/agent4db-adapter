"""Validate and summarize a complete database pair; never summarize unfinished sessions."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

db = sys.argv[1]
if db not in ('rel-stack', 'rel-trial'):
    raise ValueError('unsupported database')
root = Path('results/sql-only-20261027')
spec = importlib.util.spec_from_file_location('sql_stats', 'tools/relbench/sql-only-stats.py')
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)
data = {arm: stats.load(root / f'{arm}-{db}-r1') for arm in ('sql-only', 'mavra')}
metas = [v[0] for v in data.values()]
fields = ('model', 'llm', 'reasoning_effort', 'thinking', 'base_url', 'require_model',
          'harness_sha256', 'MAX_LLM_CALLS', 'MAX_VALIDATIONS', 'PATIENCE', 'SAMPLE_SIZE', 'LGB_PARAMS')
for key in fields:
    if metas[0]['settings'].get(key) != metas[1]['settings'].get(key):
        raise ValueError(f'{db}: mismatch in {key}')
if metas[0]['settings']['llm'] != 'happy' or metas[0]['settings']['require_model'] != 'deepseek/deepseek-v4.1-flash-1017':
    raise ValueError(f'{db}: unexpected provider or required model')
timeline = lambda m: [(c['k'], c['test_timestamp'], c['order']) for c in m['cutoffs']]
if timeline(metas[0]) != timeline(metas[1]):
    raise ValueError(f'{db}: mismatched timeline or arrival order')

report = {'database': db, 'scope': 'One matched sequence per arm; descriptive, not independent repetitions.',
          'target_rule': 'Each arm uses its own previous-cutoff program refit on current data.',
          'sources': {}, 'sessions': {}, 'aggregates': {}}
for arm, (meta, rows, sources) in data.items():
    report['sources'].update(sources)
    run_path = root / f'{arm}-{db}-r1/run.json'
    report['sources'][str(run_path)] = hashlib.sha256(run_path.read_bytes()).hexdigest()
    report['sessions'][arm] = [rows[k] for k in sorted(rows)]
    errors = []
    for path in sorted((root / f'{arm}-{db}-r1/sessions').glob('*.json')):
        s = json.loads(path.read_text(encoding='utf-8'))
        error = (s.get('learning') or {}).get('error')
        if error:
            errors.append({'task': s['task'], 'k': s['k'], 'error': str(error)[:300]})
    report.setdefault('learning_errors', {})[arm] = errors
for label, ks in [('all', set(range(1, 6))), ('reuse', set(range(2, 6)))] + [(f'k{k}', {k}) for k in range(1, 6)]:
    arms = {arm: stats.aggregate([r for r in rows.values() if r['k'] in ks])
            for arm, (_, rows, _) in data.items()}
    denom = arms['sql-only']['tokens']
    report['aggregates'][label] = {**arms, 'mavra_token_saving_fraction':
                                   1 - arms['mavra']['tokens'] / denom if denom else None}

out = root / f'{db}-summary.json'
out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({'database': db, 'status': 'complete', 'summary': str(out),
                  'all': report['aggregates']['all'], 'reuse': report['aggregates']['reuse'],
                  'learning_errors': report['learning_errors']}, ensure_ascii=False), flush=True)
