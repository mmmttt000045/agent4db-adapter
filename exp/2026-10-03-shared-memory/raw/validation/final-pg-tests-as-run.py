from pathlib import Path
import os, subprocess, json
from datetime import datetime, timezone
root=Path('/root/agentdb-shared-memory-20261003')
os.chdir(root)
env=dict(os.environ)
for line in (root/'.env').read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key,value=line.removeprefix('export ').split('=',1)
    env[key.strip()]=value.strip().strip(chr(34)).strip(chr(39))
if not env.get('AGENTDB_URL'):
    raise SystemExit('Missing private database configuration')
env['AGENTDB_TEST_URL']=env['AGENTDB_URL']
env['RUST_MIN_STACK']='33554432'
env['PATH']='/root/.cargo/bin:'+env.get('PATH','')
started=datetime.now(timezone.utc).isoformat()
with (root/'results/final-integration.log').open('w') as log:
    r=subprocess.run(['cargo','test','--locked','--','--ignored','--test-threads=1'],env=env,stdout=log,stderr=subprocess.STDOUT)
report={'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'exit_code':r.returncode,'thread_stack_bytes':33554432,'command':['cargo','test','--locked','--','--ignored','--test-threads=1']}
(root/'results/final-integration-run.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(r.returncode)
