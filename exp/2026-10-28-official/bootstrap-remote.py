#!/usr/bin/env python3
"""Prepare the isolated workspace; no original run, database or key is modified."""
import json
import os
from pathlib import Path
import subprocess

root=Path('/root/agentdb-official-20261028')
base=Path('/root/agentdb-mid')
assert Path.cwd()==root
os.umask(0o077)
(root/'results').mkdir(exist_ok=True)
(root/'target/release').mkdir(parents=True,exist_ok=True)
for source,target in [
    (base/'.pydeps-relbench',root/'.pydeps-relbench'),
    (base/'results/relbench-data',root/'results/relbench-data'),
    (base/'results/ext',root/'results/ext')]:
    if not target.exists(): target.symlink_to(source,target_is_directory=True)
# Rebuild from archived current source when necessary; never use a stale binary
# with an unrecorded source tree.
env={}
for line in (base/'.env').read_text().splitlines():
    if line.startswith('AGENTDB_URL='): env['AGENTDB_URL']=line.split('=',1)[1]
assert 'AGENTDB_URL' in env
env.update(DEEPSEEK_API_KEY='mavra-official-study-local',DEEPSEEK_MODEL='deepseek-flash',
           DEEPSEEK_BASE_URL='http://127.0.0.1:18928',DEEPSEEK_REASONING_EFFORT='low',DEEPSEEK_THINKING='enabled')
(root/'.env').write_text(''.join(f'{k}={v}\n' for k,v in env.items()))
(root/'.env').chmod(0o600)
print('isolated workspace and private environment prepared')
