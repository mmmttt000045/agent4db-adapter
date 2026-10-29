#!/usr/bin/env python3
"""Bounded, resumable experiment queue. Failed attempts are never overwritten."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
OUT=Path('results/official-20261028')
CONFIG=json.loads((HERE/'protocol.json').read_text())


def save(name,obj):
    p=OUT/name
    tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,indent=2)+'\n')
    tmp.replace(p)


def permitted():
    cfg=json.loads((HERE/'protocol.json').read_text())
    if datetime.now(timezone.utc)>=datetime.fromisoformat(cfg['deadline_utc'].replace('Z','+00:00')):
        return False
    state=json.loads((OUT/'budget-state.json').read_text())
    return (not (OUT/'STOP').exists() and state.get('status')!='budget_limit'
            and state['ceiling_cny']+state.get('reserved_cny',0)<cfg['budget_cny']-.4
            and shutil.disk_usage('.').free/2**30>=20)


def launch(name,arm,dataset,candidate='original',development=False):
    out=OUT/name
    if out.exists():
        # A supervisor restart may adopt its already running cell. Never rerun
        # a paid cell, resume incomplete memory, or overwrite its evidence.
        process_file=OUT/(name+'-process.json')
        process=json.loads(process_file.read_text()) if process_file.exists() else {}
        pid=process.get('pid')
        if not pid and (out/'harness.pid').exists():
            pid=int((out/'harness.pid').read_text())
        def same_process():
            if not pid: return False
            try:
                args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
                return any(x.endswith(b'/study-cell.py') for x in args) and str(out).encode() in args
            except FileNotFoundError:
                return False
        while same_process():
            deadline=datetime.fromisoformat(CONFIG['deadline_utc'].replace('Z','+00:00'))
            if datetime.now(timezone.utc)>=deadline or (OUT/'STOP').exists():
                import signal
                if os.getpgid(pid)==pid: os.killpg(pid,signal.SIGTERM)
                else: os.kill(pid,signal.SIGTERM)
                until=time.monotonic()+30
                while same_process() and time.monotonic()<until: time.sleep(1)
                if same_process():
                    if os.getpgid(pid)==pid: os.killpg(pid,signal.SIGKILL)
                    else: os.kill(pid,signal.SIGKILL)
                break
            time.sleep(5)
        report=json.loads((out/'run.json').read_text()) if (out/'run.json').exists() else {}
        return {'name':name,'status':'finished' if report.get('finished') and not report.get('error') else 'failed',
                'adopted_existing':True,'started_utc':process.get('started_utc'),
                'finished_at_server_time':report.get('finished'),
                'observed_completion_utc':datetime.now(timezone.utc).isoformat()}
    if not permitted():
        return {'name':name,'status':'not_started_limit'}
    cmd=['systemd-run','--scope','--quiet','-p','MemoryMax=20G','-p','MemorySwapMax=0',
         'env','PYTHONPATH=.pydeps-relbench','HF_HUB_OFFLINE=1','OMP_WAIT_POLICY=PASSIVE',
         'python3',str(HERE/'study-cell.py'),'--arm',arm,'--dataset',dataset,
         '--candidate',candidate,'--out',str(out),'--cutoffs']
    if development:
        cmd+=['1','2','--tasks',*CONFIG['development']['tasks'],'--development']
    else:
        cmd+=['1','2','3']
    started=datetime.now(timezone.utc).isoformat()
    with (OUT/(name+'.log')).open('x') as f:
        p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        save(name+'-process.json',{'pid':p.pid,'command':cmd,'started_utc':started})
        while p.poll() is None:
            deadline=datetime.fromisoformat(CONFIG['deadline_utc'].replace('Z','+00:00'))
            if datetime.now(timezone.utc)>=deadline or (OUT/'STOP').exists():
                import signal
                os.killpg(p.pid,signal.SIGTERM)
                try: p.wait(30)
                except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL)
                break
            time.sleep(5)
    report=json.loads((out/'run.json').read_text()) if (out/'run.json').exists() else {}
    return {'name':name,'status':'finished' if report.get('finished') and not report.get('error') else 'failed',
            'exit_code':p.poll(),'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat()}


def select():
    if (OUT/'selection.json').exists():
        # Restarting a supervisor must not move the freeze time or reselect
        # after formal evaluation has begun.
        frozen=json.loads((OUT/'selection.json').read_text())
        if frozen.get('candidate') not in CONFIG['development']['candidates']:
            raise ValueError('Unknown frozen candidate; manual audit required')
        return frozen['candidate']
    chosen='original'
    reason='Development comparison incomplete; use unchanged MAVRA.'
    records=[]
    for variant in ('original','compact-reuse'):
        folder=OUT/('dev-'+variant)
        rr=json.loads((folder/'run.json').read_text()) if (folder/'run.json').exists() else {}
        rows=[json.loads(p.read_text()) for p in sorted((folder/'sessions').glob('*.json')) if not p.name.endswith('.partial.json')]
        if not rr.get('finished') or len(rows)!=2 or any((r.get('audit') or {}).get('result')!='clean' for r in rows):
            records.append(None)
        else:
            records.append(rows)
    if all(records):
        old,new=records
        quality=all(a['best_val'] is not None and b['best_val'] is not None and b['best_val']>=a['best_val']-.01
                    for a,b in zip(old,new))
        tok=[sum(r['totals']['tokens_with_learning'] for r in rows) for rows in records]
        if quality and tok[1]<tok[0]:
            chosen='compact-reuse'
        reason={'validation_quality_gate':quality,'development_tokens':tok,'test_labels_used':False}
    result={'candidate':chosen,'reason':reason,'frozen_utc':datetime.now(timezone.utc).isoformat()}
    save('selection.json',result)
    return chosen


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    lock=OUT/'coordinator.lock'
    import fcntl
    with lock.open('w') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state={'status':'development','cells':[],'deadline_utc':CONFIG['deadline_utc']}
        save('status.json',state)
        state['cells'].append(launch('dev-original','mavra','rel-amazon','original',True))
        save('status.json',state)
        # The no-memory control has no parameters to select on development. Run
        # one control while the second development candidate runs. The configured
        # worker bound applies throughout; select() reads development records only.
        datasets=CONFIG['evaluation']['datasets']
        with ThreadPoolExecutor(CONFIG['evaluation']['parallel_cells']) as pool:
            dev=pool.submit(launch,'dev-compact-reuse','mavra','rel-amazon','compact-reuse',True)
            control=pool.submit(launch,f'none-{datasets[0]}-r1','none',datasets[0])
            state['cells'].append(dev.result())
            chosen=select()
            state['status']='evaluation'
            state['frozen_candidate']=chosen
            save('status.json',state)
            # Fill either free slot from this fixed queue. A fast database need
            # not wait idle for its partner, and each cell still runs its whole
            # temporal sequence in isolation. Queue order never uses scores.
            jobs=[control]
            for arm in CONFIG['evaluation']['arms']:
                for dataset in datasets:
                    if arm=='none' and dataset==datasets[0]: continue
                    jobs.append(pool.submit(launch,f'{arm}-{dataset}-r1',arm,dataset,
                                            chosen if arm=='mavra' else 'original'))
            for job in as_completed(jobs):
                state['cells'].append(job.result())
                save('status.json',state)
        state['status']='completed' if all(x['status']=='finished' for x in state['cells'][2:]) else 'finished_with_gaps'
        state['ended_utc']=datetime.now(timezone.utc).isoformat()
        save('status.json',state)


if __name__=='__main__':
    main()
