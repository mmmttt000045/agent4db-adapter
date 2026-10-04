from pathlib import Path
import os, subprocess, json, hashlib, argparse
from datetime import datetime, timezone
parser=argparse.ArgumentParser()
parser.add_argument('--label',required=True)
parser.add_argument('--only')
args=parser.parse_args()
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
source_files=[Path('Cargo.toml'),Path('Cargo.lock'),*sorted(Path('src').rglob('*.rs'))]
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
command=['cargo','test','--locked']
if args.only:command.append(args.only)
command+=['--','--ignored','--test-threads=1']
started=datetime.now(timezone.utc).isoformat()
with (root/f'results/{args.label}.log').open('w') as log:
    r=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
report={'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'exit_code':r.returncode,'thread_stack_bytes':33554432,'command':command,'source_sha256':hashes}
(root/f'results/{args.label}-run.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'}))
raise SystemExit(r.returncode)
