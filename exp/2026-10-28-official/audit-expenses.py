#!/usr/bin/env python3
"""Reconcile the immutable official usage ledger; never makes API calls."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def audit(root, final=False):
    raw = (root / 'api-usage.jsonl').read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    state = json.loads((root / 'budget-state.json').read_text(encoding='utf-8'))
    pricing = json.loads((HERE / 'pricing-verification.json').read_text(encoding='utf-8'))
    rates = {k: Decimal(str(v)) for k, v in pricing['cny_per_million']['offpeak'].items()}
    cost = Decimal(0)
    totals = Counter()
    unknown = []
    ids = []
    times = []
    for i, row in enumerate(rows):
        instant = datetime.fromisoformat(row['utc'].replace('Z', '+00:00'))
        local = instant.astimezone(timezone(timedelta(hours=8)))
        # This study is wholly within the verified overnight off-peak window.
        if not ((local.date().isoformat() == '2026-10-28' and local.hour >= 18)
                or (local.date().isoformat() == '2026-10-29' and local.hour < 9)):
            raise ValueError(f'Row {i + 1} is outside the verified billing window')
        times.append(instant)
        if row.get('response_id'):
            ids.append(row['response_id'])
        usage = row.get('usage')
        if not usage:
            unknown.append(i + 1)
            continue
        prompt = int(usage['prompt_tokens'])
        output = int(usage['completion_tokens'])
        hit = int(usage.get('prompt_cache_hit_tokens',
                            (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)))
        if min(prompt, output, hit) < 0 or hit > prompt:
            raise ValueError(f'Invalid token counts in row {i + 1}')
        miss = prompt - hit
        if int(usage.get('prompt_cache_miss_tokens', miss)) != miss:
            raise ValueError(f'Cache accounting mismatch in row {i + 1}')
        if int(usage.get('total_tokens', prompt + output)) != prompt + output:
            raise ValueError(f'Total token mismatch in row {i + 1}')
        totals.update(hit=hit, miss=miss, output=output, prompt=prompt, total=prompt + output)
        cost += (hit * rates['hit'] + miss * rates['miss'] + output * rates['output']) / 1_000_000
    duplicate_ids = [key for key, count in Counter(ids).items() if count > 1]
    consistent = len(rows) == state['calls']
    closing_path = root / 'closing-balance.json'
    closing = json.loads(closing_path.read_text(encoding='utf-8')) if closing_path.exists() else None
    if final:
        if not consistent or abs(state.get('reserved_cny', 0)) > 1e-8:
            raise ValueError('Final ledger must agree with the settled relay state')
        if duplicate_ids or unknown:
            raise ValueError('Duplicate responses or missing usage require a manual expense audit')
        if not closing or not closing.get('new_calls_blocked'):
            raise ValueError('Final expenses require a closing balance after blocking new calls')
        closed = datetime.fromisoformat(closing['checked_utc'].replace('Z', '+00:00'))
        if times and closed < max(times):
            raise ValueError('Closing balance predates the last response')
    initial = Decimal(str(state['initial_balance_cny']))
    last = Decimal(str(closing['balance_cny'] if closing else state['balance_cny']))
    account = initial - last
    sources = ['api-usage.jsonl', 'budget-state.json'] + (['closing-balance.json'] if closing else [])
    return {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'final': final,
        'scope': 'All official API calls in this study, including preflight and both development candidates.',
        'ledger_rows': len(rows), 'state_calls': state['calls'], 'ledger_state_consistent': consistent,
        'http_errors': sum(row['status'] != 200 for row in rows),
        'models': dict(Counter(row.get('model', 'unreported') for row in rows)),
        'duplicate_response_ids': duplicate_ids, 'unknown_usage_rows': unknown,
        'first_response_utc': min(times).isoformat() if times else None,
        'last_response_utc': max(times).isoformat() if times else None,
        'tokens': dict(totals), 'price_source': pricing['source'],
        'price_checked_utc': pricing['checked_utc'], 'cny_per_million': pricing['cny_per_million']['offpeak'],
        'known_usage_charge_cny': float(cost),
        'initial_balance_cny': float(initial), 'last_balance_cny': float(last),
        'balance_checked_utc': closing['checked_utc'] if closing else state['updated_utc'],
        'observed_account_decrease_cny': float(account),
        'account_minus_usage_charge_cny': float(account - cost),
        'protective_ceiling_cny': state['ceiling_cny'], 'authorized_budget_cny': 50.0,
        'interpretation': 'Usage charge is reconstructed from provider token counts and verified official off-peak prices. The account decrease is observed cash movement, not an itemized invoice; it may include other account activity or billing rounding. The protective ceiling is not actual spending. Historical per-row ceiling prices are never summed as an invoice.',
        'sources_sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources},
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('results/official-20261028'))
    p.add_argument('--out', type=Path)
    p.add_argument('--final', action='store_true')
    a = p.parse_args()
    result = audit(a.root, a.final)
    out = a.out or a.root / 'expenses.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['final', 'ledger_rows', 'ledger_state_consistent', 'known_usage_charge_cny', 'observed_account_decrease_cny', 'account_minus_usage_charge_cny']}, indent=2))
