"""Balanced real-model comparison; credentials remain in ignored local files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/tlc-deepseek'

def main():
    OUT.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('\"\'')
    env['AGENTDB_URL'] = (ROOT / 'results/tlc-real-data/connection.txt').read_text().strip()
    exe = OUT / 'experiment.exe'
    shutil.copy2(ROOT / 'target/release/agentdb-mid.exe', exe)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = dict(rounds=4, agents=24, variants=16,
        model={k: env.get(k) for k in ['OPENAI_BASE_URL', 'OPENAI_MODEL', 'OPENAI_REASONING_EFFORT', 'OPENAI_THINKING']},
        binary_sha256=digest(exe), sources={str(p.relative_to(ROOT)): digest(p) for p in (ROOT/'src').glob('*.rs')},
        dataset=json.loads((ROOT/'results/tlc-real-data/manifest.json').read_text(encoding='utf-8')),
        protocol='B fixed / D statistics / M Mock / L real model; four cyclic order rotations; same seeds; immutable real records; warm PostgreSQL; check study is separate from business tasks; failures retained; no outcome-based reruns.')
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    oracle = OUT/'oracle.json'
    subprocess.run([str(exe), '--out', str(OUT), 'real-bench', '--oracle', str(oracle), '--oracle-only', '--variants', '16'], env=env, check=True)
    cells = []
    for study in ['checks', 'cache-on', 'cache-off']:
        for r in range(4):
            for pos in range(4):
                mode = 'BDML'[(r+pos)%4]
                name = f'{study}-{r}-{mode}'
                cell = OUT/name
                cmd = [str(exe), '--pool', '16', '--out', str(cell), 'real-bench', '--mode', mode,
                       '--oracle', str(oracle), '--agents', '24', '--variants', '16', '--seed', str(42+r*1009)]
                if study == 'checks': cmd += ['--check-study']
                if study == 'cache-off': cmd += ['--no-result-cache']
                print(f'Start {name}', flush=True)
                start = time.monotonic()
                with (OUT/f'{name}.log').open('w', encoding='utf-8') as log:
                    result = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
                record = dict(study=study, round=r, mode=mode, directory=name,
                              exit_code=result.returncode, process_seconds=time.monotonic()-start)
                cells.append(record)
                (OUT/'cells.json').write_text(json.dumps(cells, indent=2), encoding='utf-8')
                print(f'End {name}: exit={result.returncode} wall={record["process_seconds"]:.2f}s', flush=True)

if __name__ == '__main__':
    main()
