"""Run balanced, sequential cells against one immutable real dataset.

No credentials are passed in process arguments or written to result manifests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=ROOT/'results/tlc-real-data')
    p.add_argument('--agents',type=int,default=24)
    p.add_argument('--variants',type=int,default=16)
    p.add_argument('--rounds',type=int,default=6)
    p.add_argument('--no-result-cache',action='store_true')
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    out=a.out or ROOT/f'results/tlc-suite-{int(time.time())}'
    out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,AGENTDB_URL=(a.data/'connection.txt').read_text(encoding='utf-8').strip())
    exes={}
    for version,source in [('new',ROOT/'target/release/agentdb-mid.exe'),('old',ROOT/'target/baseline-build/release/agentdb-mid.exe')]:
        exes[version]=out/f'{version}.exe'
        shutil.copy2(source,exes[version])
    manifest=dict(agents=a.agents,variants=a.variants,rounds=a.rounds,no_result_cache=a.no_result_cache,
        dataset=json.loads((a.data/'manifest.json').read_text(encoding='utf-8')),
        executables={k:digest(v) for k,v in exes.items()},
        sources={str(f.relative_to(ROOT)):digest(f) for f in (ROOT/'src').glob('*.rs')},
        baseline='6fb11ba plus identical realbench harness',
        protocol='Six arms (2x2 + previous D + Mock), rotated positions; same task order seed within round; fresh adapter per cell; no OS cache flushing; January then February; all data resident before experiment; scripted agents, not LLMs.')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    oracle=out/'oracle.json'
    subprocess.run([str(exes['new']),'--out',str(out),'real-bench','--oracle',str(oracle),'--oracle-only','--variants',str(a.variants)],env=env,check=True)
    groups=[('A','new','A'),('B','new','B'),('C','new','C'),('oldD','old','D'),('D','new','D'),('M','new','M')]
    cells=[]
    for r in range(a.rounds):
        for offset in range(len(groups)):
            label,version,mode=groups[(r+offset)%len(groups)]
            cell=out/f'round-{r}-{label}'
            print(f'Round {r+1}/{a.rounds} {label}',flush=True)
            cmd=[str(exes[version]),'--pool','16','--out',str(cell),'real-bench','--mode',mode,'--agents',str(a.agents),
                '--variants',str(a.variants),'--seed',str(42+r*1009),'--oracle',str(oracle)]
            if a.no_result_cache: cmd.append('--no-result-cache')
            t=time.time()
            with (out/f'round-{r}-{label}.log').open('w',encoding='utf-8') as log:
                result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f'{label} failed; inspect cell log (credentials excluded)')
            data=json.loads((cell/'report.json').read_text(encoding='utf-8'))
            tasks=sum(x['tasks'] for x in data['phases']); correct=sum(x['correct'] for x in data['phases'])
            cells.append(dict(round=r,group=label,directory=str(cell.relative_to(out)),db_ms=data['total_database']['db_ms'],
                wall_seconds=data['wall_seconds'],tasks=tasks,correct=correct,process_seconds=time.time()-t))
            (out/'cells.json').write_text(json.dumps(cells,indent=2),encoding='utf-8')
            print(f'  {correct}/{tasks}; DB {data["total_database"]["db_ms"]:.1f} ms; wall {data["wall_seconds"]:.2f}s',flush=True)
    print(f'Results: {out}',flush=True)

if __name__=='__main__': main()
