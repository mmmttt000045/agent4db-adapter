"""Rerun the changed native method against all six valid frozen controls."""
import argparse,hashlib,json,os,signal,subprocess,time,urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def read(p):return json.loads(p.read_text())
def save(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def now():return datetime.now(timezone.utc).isoformat()
def health(port,proc):
    for _ in range(80):
        assert proc.poll() is None
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1).read();return
        except OSError:time.sleep(.5)
    raise RuntimeError('Local service startup failed')

def command(ds,folder,extra=0,no_changes=False):
    cmd=[str(ROOT/'target/release/agentdb-mid'),'--pool','8','--out',str(folder),'metric-bench','--agent','openai','--extractor','openai',
         '--modes','metric-global-full','--metrics','M1,M3,M5','--phrasings','named','--question-set','v1','--legacy-single',
         '--additional-holdout-count',str(extra),'--holdout-agents','A','--changes','append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror',
         '--repeats','1','--first-repeat','1','--max-steps','20','--sql-timeout-secs','120','--concurrency','1','--trace','--no-explain','--rows','1000000']
    if no_changes:cmd+=['--no-changes']
    if ds=='tpch':cmd+=['--spec','exp/2026-10-11-generality/schemas/tpch.json','--defs','exp/2026-10-11-generality/e2e/tpch-defs.json']
    return cmd

def main():
    p=argparse.ArgumentParser();p.add_argument('--key-file',required=True);p.add_argument('--database-env',required=True);a=p.parse_args()
    assert ROOT.name=='agentdb-diverse-scenarios-20261031'
    cfg=read(HERE/'paired-reuse-protocol.json');parent=ROOT/'results/diverse-scenarios-20261031';out=parent/'paired-reuse';out.mkdir(exist_ok=False)
    b=read(parent/'budget/budget-state.json');assert b['calls']==1540 and abs(b['reserved_cny'])<1e-8 and abs(b['ceiling_cny']-cfg['start_ceiling_cny'])<1e-7
    assert read(HERE/'reuse-compatibility-check.json')['status']=='passed'
    smoke=read(ROOT/'results/offline-smoke/smoke-result.json');assert smoke['full_trace_contract'] and smoke['paid_model_calls']==0
    llm=(ROOT/'src/llm.rs').read_text();assert '"kind":"assistant"' in llm and '"kind":"tool"' in llm and 'FIG6_PRESERVE_REASONING' in llm
    files=[ROOT/'Cargo.toml',ROOT/'Cargo.lock',ROOT/'target/release/agentdb-mid',HERE/'memory-service.py',HERE/'budget-proxy.py',HERE/'paired-reuse-protocol.json',HERE/'run-paired-reuse.py']+list((ROOT/'src').rglob('*.rs'))
    manifest={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    save(out/'frozen-source-manifest.json',manifest)
    env={k:v for k,v in os.environ.items() if 'proxy' not in k.lower() and not k.startswith(('OPENAI_','DEEPSEEK_'))}
    for line in Path(a.database_env).read_text().splitlines():
        if line.startswith('AGENTDB_URL='):env['AGENTDB_URL']=line.split('=',1)[1].strip().strip('"').strip("'")
    assert env.get('AGENTDB_URL')
    env.update(PYTHONPATH=str(ROOT/'.pydeps-relbench'),NO_PROXY='127.0.0.1,localhost',FIG6_PRESERVE_REASONING='1',FIG6_LEGACY_SHARED_PROMPT='1',
        FIG6_MEMORY_URL='http://127.0.0.1:19431/memory',OPENAI_API_KEY='diverse-scenarios-20261031-local',OPENAI_MODEL='deepseek-flash',
        OPENAI_REQUIRE_MODEL='deepseek-flash',OPENAI_HEDGE='1',OPENAI_REASONING_EFFORT='low',OPENAI_THINKING='enabled',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
    state={'status':'starting','started_utc':now(),'controls':cfg['controls'],'native_cells':[],'extras':[],'implementation_revision':4};save(out/'execution-state.json',state)
    (parent/'budget/STOP').unlink();services=[];logs=[]
    try:
        for name,port,args in [('budget-proxy',19430,['--key-file',a.key_file,'--out',str(parent/'budget')]),('memory-service',19431,['--out',str(out/'memory')])]:
            log=(out/f'{name}.log').open('x');logs.append(log)
            proc=subprocess.Popen(['python3','-u',str(HERE/f'{name}.py'),'--port',str(port),*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            services.append(proc);health(port,proc)
        state['status']='running_native_base';save(out/'execution-state.json',state)
        def cell(ds):
            key=f'{ds}-r1-mavra-repaired';folder=out/'cells'/key;folder.mkdir(parents=True)
            cmd=command(ds,folder);record={'key':key,'dataset':ds,'arm':'mavra','started_utc':now(),'command':cmd,'repeat':1}
            save(folder/'launch.json',record)
            with (folder/'console.log').open('x') as log:
                proc=subprocess.Popen(cmd,cwd=ROOT,env={**env,'FIG6_CELL_KEY':key,'OPENAI_BASE_URL':f'http://127.0.0.1:19430/arm/{key}'},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                (folder/'process.pid').write_text(str(proc.pid));record['returncode']=proc.wait()
            reports=list(folder.glob('metric-*/report.json'));record['completed']=record['returncode']==0 and len(reports)==1
            if reports:
                report=read(reports[0]);rows=report['cells'][0]['records'];expected=read(HERE/f'reuse-banks/{ds}-base/question-bank.json')
                record['completed'] &= [{k:r[k] for k in ['phase','task','metric','ask','question']} for r in rows]==expected and report['database_cleaned_up']
                record.update(tasks=len(rows),report=str(reports[0].relative_to(parent)),report_sha256=hashlib.sha256(reports[0].read_bytes()).hexdigest())
                control=next(c for c in cfg['controls'] if c['dataset']==ds)
                oldreport=read(next((Path(cfg['controls_source'])/'cells'/control['key']).glob('metric-*/report.json')))
                ref=lambda data:[{k:r[k] for k in ['phase','task','metric','ask','question','gold']} for r in data]
                record['completed'] &= ref(rows)==ref(oldreport['cells'][0]['records'])
            denied=parent/'budget/denied-requests.jsonl'
            if denied.exists() and any(json.loads(s)['arm']==key for s in denied.read_text().splitlines()):record['completed']=False
            record['finished_utc']=now();save(folder/'completion.json',record)
            data=json.dumps({'op':'close','key':key,'arm':'mavra'}).encode();urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:19431/memory',data=data,headers={'Content-Type':'application/json'}),timeout=30).read()
            print(json.dumps({k:v for k,v in record.items() if k!='command'}),flush=True);return record
        with ThreadPoolExecutor(max_workers=2) as pool:state['native_cells']=list(pool.map(cell,['synthetic','tpch']))
        state['status']='native_base_complete' if all(c['completed'] for c in state['native_cells']) else 'incomplete'
        if state['status']=='native_base_complete':
            b=read(parent/'budget/budget-state.json');remaining=20-max(b['ceiling_cny'],b.get('observed_account_decrease_cny',0));gate=cfg['extra_gate'];candidates=[]
            for n in range(5):
                needed=gate['factor']*n*(gate['baseline_old_holdout_cost_per_extra_per_schema_sum_cny']+gate['native_old_holdout_cost_per_extra_per_schema_sum_cny'])+(gate['reserve_cny'] if n else 0)
                candidates.append({'extra_count':n,'required_cny':needed,'fits':needed<remaining})
            state['selected_extra_count']=max(c['extra_count'] for c in candidates if c['fits'])
            save(out/'extra-decision.json',{'utc':now(),'uses_accuracy':False,'remaining_cny':remaining,'candidates':candidates,'selected_extra_count':state['selected_extra_count']})
        state['finished_base_utc']=now();save(out/'execution-state.json',state)
    finally:
        (parent/'budget/STOP').touch()
        for proc in reversed(services):
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(20)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL)
        for log in logs:log.close()

if __name__=='__main__':main()
