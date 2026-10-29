#!/usr/bin/env python3
"""Resume the same spending ledger for an explicit, recorded interface repair."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

root=Path(__file__).resolve().parents[2];os.chdir(root)
here=root/'exp/2026-10-29-mechanism-pilot'
out=root/'results/mechanism-pilot-20261029'
assert 'ended_utc' in json.loads((out/'supervisor.json').read_text())
assert not (out/'repair-supervisor.json').exists()
state={'started_utc':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),'same_ledger':True}
relay=run=None
def save(): (out/'repair-supervisor.json').write_text(json.dumps(state,indent=2))
try:
    save()
    with (out/'repair-relay.log').open('x') as log:
        relay=subprocess.Popen([sys.executable,str(here/'budget-proxy.py'),'--port','18929','--out',str(out)],
                               stdout=log,stderr=subprocess.STDOUT)
    for i in range(30):
        if relay.poll() is not None:raise RuntimeError('repair relay exited')
        try:
            with urllib.request.urlopen('http://127.0.0.1:18929/health',timeout=2) as r:
                if json.load(r).get('ok'):break
        except Exception: time.sleep(1)
    else:raise RuntimeError('repair relay unavailable')
    with (out/'repair-pilot.log').open('x') as log:
        run=subprocess.Popen([sys.executable,str(here/'repair_pilot.py')],stdout=log,stderr=subprocess.STDOUT)
    state['pilot_pid']=run.pid;save()
    state['exit_code']=run.wait(timeout=4*3600)
finally:
    if run and run.poll() is None:
        run.terminate()
        try:run.wait(30)
        except subprocess.TimeoutExpired:run.kill();run.wait()
    if relay and relay.poll() is None:relay.terminate();relay.wait(15)
    state['ended_utc']=datetime.now(timezone.utc).isoformat();save()
