#!/usr/bin/env python3
"""Run the fixed no-LLM supplements after the paid pilot, with durable status."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[2]
os.chdir(root)
out=root/'results/mechanism-systems-20261029'
out.mkdir(parents=True,exist_ok=True)
state_file=out/'status.json'
if state_file.exists():
    previous=json.loads(state_file.read_text())
    if previous['status']=='waiting-for-pilot' and not previous['runs']:
        archive=out/'waiting-before-interface-repair.json'
    else:
        assert previous['status']=='stopped' and previous['error']=='run-C failed; preserve logs and partial results'
        reports=list(out.glob('C-*/report.json'))
        assert len(reports)==1 and 'ss_is_current' in json.loads(reports[0].read_text())['report']['error']
        assert not list(out.glob('C-*/c-progress.json')), 'Never rerun completed measurements silently'
        archive=out/'before-fixture-initialization-repair.json'
    assert not archive.exists()
    state_file.rename(archive)
state={'started_utc':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),'status':'waiting-for-pilot','runs':[]}

def save():
    state['updated_utc']=datetime.now(timezone.utc).isoformat()
    state_file.write_text(json.dumps(state,indent=2))

def execute(stage,cmd,env=None):
    state['status']=stage; save()
    log_path=out/(stage+'.log')
    if log_path.exists(): log_path=out/(stage+'-fixture-repair.log')
    with log_path.open('x') as log:
        r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=3900)
    state['runs'].append({'stage':stage,'exit_code':r.returncode});save()
    if r.returncode: raise RuntimeError(stage+' failed; preserve logs and partial results')

try:
    save()
    pilot=Path('/root/agentdb-mechanism-pilot-20261029/results/mechanism-pilot-20261029/repair-supervisor.json')
    deadline=time.monotonic()+6*3600
    while True:
        p=json.loads(pilot.read_text())
        if 'ended_utc' in p:
            break
        if time.monotonic()>deadline: raise RuntimeError('Pilot wait deadline reached')
        time.sleep(15)
    execute('build',['/root/.cargo/bin/cargo','test','--offline','--release','--no-run','-j','4'])
    for part in ['C','B']:
        env=os.environ.copy(); env['MECHANISM_PART']=part
        execute('run-'+part,['/root/.cargo/bin/cargo','test','--offline','--release','postgres_mechanism_supplement',
                            '--','--ignored','--nocapture','--test-threads=1'],env)
    state['status']='complete'
except Exception as e:
    state.update(status='stopped',error=str(e))
finally:
    state['ended_utc']=datetime.now(timezone.utc).isoformat();save()
print(json.dumps(state,indent=2))
