#!/usr/bin/env python3
"""Loopback-only official API relay with a durable, conservative spending cap.

Credentials never enter the repository, request logs, or experiment archive.
The ceiling carries all prior spending and uses verified weekend off-peak
prices only inside the frozen weekend window. The original balance is checked too.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time

ROOT = Path(__file__).resolve().parent
LOCAL_TOKEN = 'corrected-scenarios-20261031-local'
RATES = {'hit': .02, 'miss': 1.0, 'output': 4.0}  # verified official CNY/M peak prices
PRICING_POLICY = 'official-weekend-offpeak-cumulative-20261031'
PRICING_SOURCE = 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'


def upper_cost(usage):
    total = int(usage.get('prompt_tokens', 0))
    hit = int(usage.get('prompt_cache_hit_tokens',
                        (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)))
    hit = max(0, min(total, hit))
    return (hit * RATES['hit'] + (total-hit) * RATES['miss'] +
            int(usage.get('completion_tokens', 0)) * RATES['output']) / 1e6


def reserve_cost(body):
    # UTF-8 bytes plus envelope overhead is conservative for text/tool schemas.
    n = len(json.dumps(body, ensure_ascii=False).encode('utf-8')) + 4096
    return (n * RATES['miss'] + body['max_tokens'] * RATES['output']) / 1e6


def reprice_legacy_ceiling(state, rows):
    """Revalue known usage, retaining unknown charges at their original ceiling."""
    if len(rows) != state['calls']:
        raise RuntimeError('Usage ledger/state count mismatch; inspect before repricing')
    original_logged = sum(r['ceiling_cny'] for r in rows)
    unlogged = max(0., state['ceiling_cny'] - original_logged)
    return unlogged + sum(upper_cost(r['usage']) if r.get('usage') else r['ceiling_cny'] for r in rows)


class Budget:
    def __init__(self, directory, key_file):
        import requests
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'budget-state.json'
        self.key = Path(key_file).read_text().strip()
        self.lock = threading.Lock()
        self.reserved = 0.0
        self.http = requests.Session()
        self.http.trust_env = False
        self.headers = {'Authorization': 'Bearer ' + self.key}
        self.config = json.loads((ROOT/'protocol.json').read_text())
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state.get('pricing_policy') != PRICING_POLICY:
                if self.state.get('pricing_policy') is not None:
                    raise RuntimeError('Unknown prior pricing policy; inspect before migration')
                ledger = self.directory / 'api-usage.jsonl'
                raw = ledger.read_bytes()
                rows = [json.loads(line) for line in raw.splitlines() if line]
                previous = self.state['ceiling_cny']
                revised = reprice_legacy_ceiling(self.state, rows)
                audit = {'utc': datetime.now(timezone.utc).isoformat(),
                         'source': PRICING_SOURCE, 'rates_cny_per_million': RATES,
                         'old_ceiling_cny': previous, 'new_ceiling_cny': revised,
                         'outstanding_reservation_retained_cny': self.state.get('reserved_cny', 0),
                         'ledger_rows': len(rows), 'ledger_sha256': hashlib.sha256(raw).hexdigest(),
                         'authorization_cny': self.config['budget_cny']}
                with (self.directory/'pricing-migration.json').open('x') as f:
                    json.dump(audit, f, indent=2)
                self.state['ceiling_cny'] = revised
            # Outstanding reservations from an unclean restart remain charged.
            self.state['ceiling_cny'] += self.state.get('reserved_cny', 0)
        else:
            prior_path = Path(self.config['prior_private_budget'])
            prior = json.loads(prior_path.read_text())
            if prior['calls'] != 3378 or abs(prior['reserved_cny']) > 1e-8 or not (prior_path.parent/'STOP').exists():
                raise RuntimeError('Prior study must be closed and fully accounted')
            initial = prior['initial_balance_cny']
            raw = (prior_path.parent/'api-usage.jsonl').read_bytes()
            if hashlib.sha256(raw).hexdigest() != self.config['prior_ledger_sha256']:
                raise RuntimeError('Prior usage ledger hash changed')
            rows = [json.loads(line) for line in raw.splitlines() if line]
            if len(rows) != prior['calls'] or any(not row.get('usage') for row in rows):
                raise RuntimeError('Prior usage is not fully accounted')
            for row in rows:
                local = datetime.fromisoformat(row['utc']).astimezone(timezone(__import__('datetime').timedelta(hours=8)))
                if local.weekday()<5 and (9<=local.hour<12 or 14<=local.hour<18):
                    raise RuntimeError('Prior requests require peak repricing')
            computed = sum(upper_cost(row['usage']) for row in rows)
            if abs(computed-self.config['prior_priced_usage_cny'])>1e-8:
                raise RuntimeError('Prior charge does not match the frozen ledger')
            floor = max(self.config['prior_priced_usage_cny'], max(0.,initial-self.balance()))
            self.state = {'started_utc': datetime.now(timezone.utc).isoformat(),
                          'initial_balance_cny': initial, 'ceiling_cny': floor, 'prior_cost_cny': floor,
                          'calls': 0, 'errors': 0, 'models': {}, 'status': 'ready'}
        self.state['pricing_policy'] = PRICING_POLICY
        self.state['rates_cny_per_million'] = RATES
        self.save()

    def balance(self):
        r = self.http.get('https://api.deepseek.com/user/balance', headers=self.headers, timeout=20)
        r.raise_for_status()
        values = [float(x['total_balance']) for x in r.json()['balance_infos'] if x['currency']=='CNY']
        if not values:
            raise RuntimeError('CNY balance unavailable; stop rather than guess a conversion')
        return sum(values)

    def save(self):
        self.state['reserved_cny'] = self.reserved
        self.state['updated_utc'] = datetime.now(timezone.utc).isoformat()
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, indent=2)+'\n')
        temp.replace(self.path)

    def acquire(self, body):
        with self.lock:
            self.config = json.loads((ROOT/'protocol.json').read_text())
            cap = min(20.0, float(self.config['budget_cny']))
            if datetime.now(timezone.utc) >= datetime.fromisoformat(self.config['deadline_utc'].replace('Z','+00:00')):
                raise RuntimeError('Study deadline reached')
            if (self.directory/'STOP').exists():
                raise RuntimeError('Study stop requested')
            now = datetime.now(timezone.utc)
            beijing = now.astimezone(timezone(__import__('datetime').timedelta(hours=8)))
            if beijing.weekday() < 5 or now >= datetime.fromisoformat(self.config['pricing_window_end_utc']):
                raise RuntimeError('Frozen off-peak pricing window ended')
            reservation = reserve_cost(body)
            bal = self.balance()
            spent = max(0., self.state['initial_balance_cny']-bal)
            self.state['balance_cny'] = bal
            self.state['observed_account_decrease_cny'] = spent
            if max(spent, self.state['ceiling_cny']) + self.reserved + reservation > cap or bal < self.reserved+reservation:
                self.state['status'] = 'budget_limit'
                self.save()
                raise RuntimeError('Study spending limit reached')
            self.reserved += reservation
            self.save()
            return reservation

    def finish(self, reservation, status, data, elapsed, arm='unassigned', request=None):
        usage = data.get('usage') or {}
        charge = upper_cost(usage) if usage else reservation
        # If no usage was returned the full reservation stays charged.
        with self.lock:
            self.reserved -= reservation
            self.state['ceiling_cny'] += charge
            self.state['calls'] += 1
            self.state['errors'] += int(status != 200)
            model = data.get('model', 'unreported')
            self.state['models'][model] = self.state['models'].get(model, 0)+1
            row = {'utc': datetime.now(timezone.utc).isoformat(), 'status': status,
                   'model': model, 'usage': usage, 'ceiling_cny': charge, 'seconds': elapsed,
                   'response_id': data.get('id'), 'pricing_policy': PRICING_POLICY, 'arm': arm}
            with (self.directory/'api-usage.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
            with (self.directory/'api-transcripts.jsonl').open('a') as f:
                f.write(json.dumps({'call': self.state['calls'], 'utc': row['utc'],
                                   'arm': arm, 'request': request, 'response': data}, ensure_ascii=False)+'\n')
            self.save()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, status, data):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/health':
            self.send_json(200, {'ok': True, 'upstream': 'https://api.deepseek.com'})
        else:
            self.send_json(404, {'error': 'unknown route'})

    def do_POST(self):
        import requests
        b = self.server.budget
        parts = self.path.strip('/').split('/')
        arm = parts[1] if len(parts) >= 4 and parts[0] == 'arm' else 'unassigned'
        route = '/' + '/'.join(parts[2:]) if arm != 'unassigned' else self.path
        if route not in ('/chat/completions', '/v1/chat/completions'):
            return self.send_json(404, {'error': 'unknown route'})
        if self.headers.get('Authorization') != 'Bearer '+LOCAL_TOKEN:
            return self.send_json(401, {'error': 'local study token required'})
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 4_000_000:
                raise ValueError('request size outside study limit')
            body = json.loads(self.rfile.read(size))
            if body.get('model') != b.config['model'] or body.get('stream'):
                raise ValueError('only the frozen model and non-streaming requests are allowed')
            body['max_tokens'] = min(int(body.get('max_tokens') or b.config['max_output_tokens']),
                                     b.config['max_output_tokens'])
            reservation = b.acquire(body)
        except Exception as e:
            with b.lock:
                with (b.directory/'denied-requests.jsonl').open('a') as f:
                    f.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(),
                                        'arm': arm, 'error': str(e)})+'\n')
            return self.send_json(402, {'error': {'message': str(e), 'type': 'study_limit'}})
        start = time.monotonic()
        try:
            # Per-request session: no implicit retries, no third-party gateways.
            with requests.Session() as s:
                s.trust_env = False
                r = s.post('https://api.deepseek.com/chat/completions', json=body,
                           headers=b.headers, timeout=300)
                status, data = r.status_code, r.json()
        except Exception:
            status, data = 503, {'error': {'message': 'official API transport failure', 'type': 'upstream'}}
        b.finish(reservation, status, data, time.monotonic()-start, arm, body)
        self.send_json(status, data)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=19330)
    p.add_argument('--out', default='results/published-scenarios-20261030/budget')
    p.add_argument('--key-file', required=True)
    args = p.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.budget = Budget(args.out, args.key_file)
    server.serve_forever()
