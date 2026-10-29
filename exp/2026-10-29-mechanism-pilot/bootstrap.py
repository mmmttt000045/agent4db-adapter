#!/usr/bin/env python3
"""Build an isolated, provenance-recorded pilot workspace on the existing server."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root = Path('/root/agentdb-mechanism-pilot-20261029')
base = Path('/root/agentdb-official-20261028')
assert Path.cwd() == root
os.umask(0o077)
for name in ['tools', 'third_party', 'src']:
    target = root / name
    if not target.exists():
        shutil.copytree(base / name, target)
for name in ['Cargo.toml', 'Cargo.lock']:
    shutil.copy2(base / name, root / name)
(root / 'target/release').mkdir(parents=True, exist_ok=True)
shutil.copy2(base / 'target/release/agentdb-mid', root / 'target/release/agentdb-mid')
for source, target in [(base / '.pydeps-relbench', root / '.pydeps-relbench'),
                       (base / 'results/relbench-data', root / 'results/relbench-data')]:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.symlink_to(source.resolve(), target_is_directory=True)
env = {}
for line in (base / '.env').read_text().splitlines():
    if line.startswith('AGENTDB_URL='):
        env['AGENTDB_URL'] = line.split('=', 1)[1]
assert 'AGENTDB_URL' in env
env.update(DEEPSEEK_API_KEY='mavra-official-study-local', DEEPSEEK_BASE_URL='http://127.0.0.1:18929',
           DEEPSEEK_MODEL='deepseek-flash', DEEPSEEK_REASONING_EFFORT='low', DEEPSEEK_THINKING='enabled')
(root / '.env').write_text(''.join(f'{k}={v}\n' for k,v in env.items()))
here = root / 'exp/2026-10-29-mechanism-pilot'
# Source data never leaves the server: verified identical to the local archive.
source_path = base / 'results/official-20261028/mavra-rel-stack-r1/sessions/user_badge-k1.json'
source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
assert source_sha == '48d63517630429494879d10220f752a21d4087b4d3c0c5da03f20f54ae1af8b0'
original = json.loads(source_path.read_text())
allowed = ['task', 'k', 'final_sql', 'best_val', 'higher_is_better', 'metric', 'audit', 'validations', 'totals']
source = {key: original[key] for key in allowed}
source['provenance'] = {'source_sha256': source_sha, 'source_file': str(source_path),
    'source_model_responses': sorted({v.get('model', 'unknown') for v in original['llm']}),
    'historical_source_exploration_tokens': original['totals']['tokens'],
    'historical_extraction_tokens': original['totals']['learn_tokens']}
(here / 'source-input.json').write_text(json.dumps(source, indent=2) + '\n')
# Reuse the existing conservative relay implementation, under this study's own protocol and ledger.
shutil.copy2(base / 'exp/2026-10-28-official/budget-proxy.py', here / 'budget-proxy.py')
cfg = json.loads((here / 'protocol.json').read_text())
cfg['deadline_utc'] = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
(here / 'protocol.json').write_text(json.dumps(cfg, indent=2) + '\n')
manifest = {}
for folder in ['src', 'tools/relbench', 'exp/2026-10-29-mechanism-pilot']:
    for path in sorted((root / folder).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            manifest[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
binary = root / 'target/release/agentdb-mid'
manifest[str(binary.relative_to(root))] = hashlib.sha256(binary.read_bytes()).hexdigest()
(here / 'runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'workspace': str(root), 'binary_sha256': manifest[str(binary.relative_to(root))],
                  'harness_sha256': manifest['tools/relbench/harness.py'], 'deadline_utc': cfg['deadline_utc']}))
