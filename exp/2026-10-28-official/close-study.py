#!/usr/bin/env python3
"""Close a fully completed study, without creating any model request."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
from urllib.request import Request, build_opener, ProxyHandler

BASE = Path(__file__).resolve().parents[2]
RESULTS = BASE/'results/official-20261028'


def stop_owned_process(pid_file, suffix):
    path = RESULTS/pid_file
    if not path.exists(): return 'pid file absent'
    pid = int(path.read_text().strip())
    proc = Path('/proc')/str(pid)
    if not proc.exists(): return 'already exited'
    args = proc.joinpath('cmdline').read_bytes().split(b'\0')
    if proc.joinpath('cwd').resolve() != BASE.resolve() or not any(x.endswith(suffix.encode()) for x in args):
        raise RuntimeError(f'{pid_file}: process identity differs; leave untouched')
    os.kill(pid, signal.SIGTERM)
    return f'SIGTERM sent to verified study process {pid}'


def main():
    for ds in ['rel-stack', 'rel-trial']:
        for arm in ['none', 'mavra', 'ace', 'awm', 'gmemory']:
            folder = RESULTS/f'{arm}-{ds}-r1'
            run = json.loads((folder/'run.json').read_text())
            rows = [json.loads(p.read_text()) for p in (folder/'sessions').glob('*.json') if not p.name.endswith('.partial.json')]
            if not run.get('finished') or run.get('error') or len(rows) != 9:
                raise RuntimeError(f'{folder.name} is not complete; do not stop running work')
            if any((r.get('eval') or {}).get('pending') for r in rows):
                raise RuntimeError(f'{folder.name} has unfinished scoring')
    state = json.loads((RESULTS/'budget-state.json').read_text())
    if abs(state.get('reserved_cny', 0)) > 1e-8:
        raise RuntimeError('Wait for outstanding model calls before closing')
    if (RESULTS/'closing-balance.json').exists():
        print('Study already closed; existing closing balance preserved')
        return
    (RESULTS/'STOP').write_text('All ten formal sequences completed. No further model calls authorized for this study.\n')
    stopped = {'report_loop': stop_owned_process('report-loop.pid', 'report-loop.py'),
               'budget_proxy': stop_owned_process('budget-proxy.pid', 'budget-proxy.py')}
    # Credentials are read only on the remote host and never logged or archived.
    key = Path('/root/.config/mavra-official-20261028/api-key').read_text().strip()
    request = Request('https://api.deepseek.com/user/balance', headers={'Authorization':'Bearer '+key})
    with build_opener(ProxyHandler({})).open(request, timeout=20) as response:
        balance = json.load(response)
    values = [float(x['total_balance']) for x in balance['balance_infos'] if x['currency'] == 'CNY']
    if not values: raise RuntimeError('CNY closing balance unavailable')
    result = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'balance_cny': sum(values),
              'new_calls_blocked': True, 'reason': 'All ten formal sequences complete',
              'stopped_processes': stopped, 'ledger_calls': state['calls'],
              'initial_balance_cny': state['initial_balance_cny'],
              'account_decrease_cny': state['initial_balance_cny'] - sum(values)}
    (RESULTS/'closing-balance.json').write_text(json.dumps(result, indent=2)+'\n')
    status = json.loads((RESULTS/'status.json').read_text())
    known = {cell['name'] for cell in status['cells']}
    for ds in ['rel-stack', 'rel-trial']:
        for arm in ['none', 'mavra', 'ace', 'awm', 'gmemory']:
            name = f'{arm}-{ds}-r1'
            if name not in known:
                run = json.loads((RESULTS/name/'run.json').read_text())
                status['cells'].append({'name': name, 'status': 'finished',
                                        'finished_at_server_time': run['finished'],
                                        'observed_completion_utc': result['checked_utc']})
    status.update(status='completed', ended_utc=result['checked_utc'], model_calls_closed=True)
    (RESULTS/'status.json').write_text(json.dumps(status, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
