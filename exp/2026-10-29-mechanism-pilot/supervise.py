#!/usr/bin/env python3
"""Own the relay lifetime and retain final process status, without paid retries."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

root = Path(__file__).resolve().parents[2]
os.chdir(root)
here = Path('exp/2026-10-29-mechanism-pilot')
out = Path('results/mechanism-pilot-20261029')
out.mkdir(parents=True, exist_ok=True)
if (out / 'supervisor.json').exists():
    raise SystemExit('Refusing automatic second paid run')
status = {'started_utc': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid()}
(out / 'supervisor.json').write_text(json.dumps(status, indent=2))
relay = run = None
try:
    with (out / 'relay.log').open('x') as log:
        relay = subprocess.Popen([sys.executable, str(here / 'budget-proxy.py'), '--port', '18929', '--out', str(out)],
                                 stdout=log, stderr=subprocess.STDOUT)
    for _ in range(30):
        if relay.poll() is not None:
            raise RuntimeError('Budget relay failed; inspect relay.log')
        try:
            with urllib.request.urlopen('http://127.0.0.1:18929/health', timeout=2) as r:
                if json.load(r).get('ok'):
                    break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('Budget relay startup timed out')
    with (out / 'pilot.log').open('x') as log:
        run = subprocess.Popen([sys.executable, str(here / 'pilot.py')], stdout=log, stderr=subprocess.STDOUT)
    status['pilot_pid'] = run.pid
    (out / 'supervisor.json').write_text(json.dumps(status, indent=2))
    status['exit_code'] = run.wait(timeout=6*3600)
finally:
    if run and run.poll() is None:
        run.terminate()
        try:
            run.wait(30)
        except subprocess.TimeoutExpired:
            run.kill()
            run.wait()
    if relay and relay.poll() is None:
        relay.terminate()
        relay.wait(15)
    status['ended_utc'] = datetime.now(timezone.utc).isoformat()
    (out / 'supervisor.json').write_text(json.dumps(status, indent=2))
