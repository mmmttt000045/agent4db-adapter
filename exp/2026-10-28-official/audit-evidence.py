#!/usr/bin/env python3
"""Read-only checks of raw experimental support, frozen settings and accounting."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_HARNESS = '622565d63424e5f6dfc50828728772d1967f68e8929e7dc7a98ed9f6d7669f10'
EXPECTED_SELECTION = '5e4cdf90184a0c168fdad11739bec3044070df15ef7ff6e6c3e4d1b6e110b93b'


def audit(root, require_complete=False):
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    protocol = read(HERE / 'protocol.json')
    selection = read(root / 'selection.json')
    assert sha(root / 'selection.json') == EXPECTED_SELECTION, 'Frozen selection changed'
    assert selection['candidate'] == 'compact-reuse'
    assert selection['reason']['test_labels_used'] is False
    same_keys = ['MAX_LLM_CALLS', 'MAX_VALIDATIONS', 'PATIENCE', 'SAMPLE_SIZE',
                 'LGB_PARAMS', 'model', 'llm', 'reasoning_effort', 'thinking', 'test_scores']
    common = None
    sources = {'selection.json': sha(root / 'selection.json')}
    cells = []
    session_tokens = 0
    formal_tokens = 0
    counts = Counter()
    for ds in protocol['evaluation']['datasets']:
        reference = None
        expected_support = None
        for arm in protocol['evaluation']['arms']:
            name = f'{arm}-{ds}-r1'
            folder = root / name
            run = read(folder / 'run.json')
            meta = read(folder / 'study-cell.json')
            settings = run['settings']
            values = {k: settings[k] for k in same_keys}
            if common is None: common = values
            assert values == common, f'{name}: common settings differ'
            assert settings['harness_sha256'] == EXPECTED_HARNESS, name
            assert settings['MAX_LLM_CALLS'] == 24 and settings['MAX_VALIDATIONS'] == 5
            assert settings['SAMPLE_SIZE'] == 50000
            opts = meta['options']
            assert opts['cutoffs'] == [1, 2, 3] and opts['parallel'] == 1
            assert opts['development'] is False and opts['eval_now'] is False
            assert opts['candidate'] == ('compact-reuse' if arm == 'mavra' else 'original')
            if 'effective_runtime' in meta:
                assert meta['effective_runtime']['feature_statement_timeout_seconds'] == 600
            recorded_refs = {(t, c['k']): (v['val'], v['test']) for c in run['cutoffs']
                             for t, v in c.get('reference', {}).items()}
            if reference is None: reference = recorded_refs
            assert all(k in reference and reference[k] == v for k, v in recorded_refs.items()), f'{name}: reference mismatch'
            rows = []
            for path in sorted((folder / 'sessions').glob('*.json')):
                if path.name.endswith('.partial.json'): continue
                row = read(path)
                total = row['totals']
                assert total['tokens'] == total['input_tokens'] + total['output_tokens'], path
                assert total['tokens_with_learning'] == total['tokens'] + total['learn_tokens'], path
                assert total['tool_calls'] == sum(total['tool_calls_by_category'].values()), path
                assert total['planner_llm_calls'] <= 24 and len(row['validations']) <= 5, path
                ev = row.get('eval') or {}
                if ev.get('test') is not None:
                    assert ev.get('after_run') is True, f'{path}: test not deferred'
                if row.get('final_sql') and (row.get('audit') or {}).get('result') == 'clean' and ev.get('test') is not None:
                    counts['clean_evaluated_sessions'] += 1
                if not row.get('final_sql'): counts['no_query_sessions'] += 1
                if ev.get('error'): counts['evaluation_error_sessions'] += 1
                if ev.get('pending'): counts['pending_evaluations'] += 1
                rows.append(row)
                session_tokens += total['tokens_with_learning']
                formal_tokens += total['tokens_with_learning']
                sources[path.relative_to(root).as_posix()] = sha(path)
            support = {(row['task'], row['k']) for row in rows}
            if expected_support is None: expected_support = support
            assert len(support) == len(rows), f'{name}: duplicate support'
            assert support <= expected_support, f'{name}: unexpected task/cutoff'
            complete = bool(run.get('finished') and not run.get('error'))
            if complete:
                assert support == expected_support and len(rows) == 9, f'{name}: incomplete finished cell'
                assert not any((row.get('eval') or {}).get('pending') for row in rows), name
            if require_complete: assert complete, f'{name}: not complete'
            counts['saved_formal_sessions'] += len(rows)
            cells.append({'name': name, 'complete': complete, 'sessions': len(rows),
                          'support': sorted([list(x) for x in support])})
            for filename in ['run.json', 'study-cell.json']:
                sources[f'{name}/{filename}'] = sha(folder / filename)
    dev_tokens = 0
    for variant in ['original', 'compact-reuse']:
        folder = root / ('dev-' + variant)
        run = read(folder / 'run.json')
        assert run.get('finished') and not run.get('error')
        rows = [read(p) for p in (folder/'sessions').glob('*.json') if not p.name.endswith('.partial.json')]
        assert len(rows) == 2 and {r['k'] for r in rows} == {1, 2}
        assert all(r['task'] == 'user-churn' and (r.get('eval') or {}).get('test') is None for r in rows)
        assert all(v.get('test') is None for c in run['cutoffs'] for v in c.get('reference', {}).values())
        tokens = sum(r['totals']['tokens_with_learning'] for r in rows)
        dev_tokens += tokens
        session_tokens += tokens
    preflight = read(root / 'preflight.json')
    preflight_tokens = sum(r['input_tokens'] + r['output_tokens'] for r in preflight['responses'])
    raw = (root / 'api-usage.jsonl').read_bytes()
    ledger = [json.loads(line) for line in raw.splitlines() if line]
    ledger_tokens = sum((r.get('usage') or {}).get('total_tokens', 0) for r in ledger)
    difference = ledger_tokens - session_tokens - preflight_tokens
    if require_complete:
        assert difference == 0, f'Provider ledger vs session accounting differs by {difference} tokens'
        assert counts['saved_formal_sessions'] == 90
    sources['api-usage.jsonl'] = hashlib.sha256(raw).hexdigest()
    return {'generated_utc': datetime.now(timezone.utc).isoformat(),
            'complete': all(c['complete'] for c in cells), 'require_complete': require_complete,
            'checks': ['Frozen selection hash unchanged', 'Shared model and execution settings identical',
                       'Common harness source hash identical', 'Parallelism within each cell is one',
                       'Entity-reference validation and test scores identical for each observed task/cutoff',
                       'No duplicate or unexpected task/cutoff', 'Tool-category totals and memory-token accounting match',
                       'All observed final test evaluations marked after_run', 'Development test scores absent'],
            'counts': dict(counts), 'cells': cells, 'common_settings': common,
            'tokens': {'formal_saved': formal_tokens, 'development': dev_tokens, 'preflight': preflight_tokens,
                       'provider_ledger': ledger_tokens, 'inflight_or_unmapped': difference},
            'limitations': ['This audit checks recorded boundaries and support; it is not a proof against every possible source of leakage.',
                            'Incomplete live cells are listed, not certified complete. Final accounting requires zero unmapped tokens.'],
            'sources_sha256': sources}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('results/official-20261028'))
    p.add_argument('--require-complete', action='store_true')
    a = p.parse_args()
    report = audit(a.root, a.require_complete)
    (a.root / 'evidence-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['complete', 'counts', 'tokens']}, indent=2))
