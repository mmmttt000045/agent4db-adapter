#!/usr/bin/env python3
"""Bounded maintenance: restart this study's relay only with no active requests."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/official-20261028'


def active_connections():
    # The relay binds IPv4 loopback. Established/closing connections must finish
    # delivering their responses before maintenance can terminate the process.
    return [line for line in Path('/proc/net/tcp').read_text().splitlines()[1:]
            if int(line.split()[1].split(':')[1], 16) == 18928
            and line.split()[3] not in ('0A', '06')]


def main():
    pidfile = OUT / 'budget-proxy.pid'
    pid = int(pidfile.read_text())
    assert b'budget-proxy.py' in Path(f'/proc/{pid}/cmdline').read_bytes()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        killed = False
        os.kill(pid, signal.SIGSTOP)
        try:
            for _ in range(20):
                state_text = Path(f'/proc/{pid}/status').read_text()
                if any(line.startswith('State:') and 'T' in line for line in state_text.splitlines()):
                    break
                time.sleep(.01)
            else:
                raise RuntimeError('Relay did not stop for a consistent idle check')
            state = json.loads((OUT/'budget-state.json').read_text())
            if abs(state.get('reserved_cny', 0)) < 1e-8 and not active_connections():
                raw = (OUT/'api-usage.jsonl').read_bytes()
                assert len(raw.splitlines()) == state['calls'], 'Ledger/state mismatch'
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                backup = OUT/f'budget-state-before-pricing-{stamp}.json'
                with backup.open('x') as f:
                    json.dump(state, f, indent=2)
                # The stopped process has no in-flight request or undelivered
                # response. New connections cannot incur charges while stopped.
                os.kill(pid, signal.SIGKILL)
                killed = True
                for _ in range(30):
                    if not Path(f'/proc/{pid}').exists():
                        break
                    time.sleep(.05)
                with (OUT/f'budget-proxy-pricing-{stamp}.log').open('x') as log:
                    new = subprocess.Popen([sys.executable, str(Path(__file__).with_name('budget-proxy.py'))],
                                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                pidfile.write_text(str(new.pid)+'\n')
                for _ in range(30):
                    if new.poll() is not None:
                        raise RuntimeError('Replacement relay exited; inspect its log')
                    try:
                        with urlopen('http://127.0.0.1:18928/health', timeout=1) as response:
                            assert json.load(response)['ok']
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Replacement relay did not become healthy')
                result = {'restarted': True, 'utc': stamp, 'old_pid': pid, 'new_pid': new.pid,
                          'inflight_calls_interrupted': 0, 'prior_ledger_rows': state['calls'],
                          'prior_ledger_sha256': hashlib.sha256(raw).hexdigest(),
                          'backup': backup.name}
                (OUT/f'proxy-restart-{stamp}.json').write_text(json.dumps(result, indent=2)+'\n')
                print(json.dumps(result))
                return
        finally:
            if not killed:
                os.kill(pid, signal.SIGCONT)
        time.sleep(2)
    print(json.dumps({'restarted': False, 'reason': 'No idle window; existing relay remains active'}))


if __name__ == '__main__':
    main()
