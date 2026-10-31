"""Run matched full methods on the frozen diverse bank under the cumulative cap."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json,os,signal,shutil,subprocess,time,urllib.request
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
TOKEN='diverse-scenarios-20261031-local'

def utc():return datetime.now(timezone.utc).isoformat()
def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)

def command(ds,arm,m,out):
    modes={'ace':'paper-ace','awm':'paper-awm','gmemory':'paper-gmemory','mavra':'metric-global-full'}
    cmd=[str(ROOT/'target/release/agentdb-mid'),'--pool','8','--out',str(out),'metric-bench',
         '--agent','openai','--extractor','openai','--modes',modes[arm],'--metrics','M1,M3,M5',
         '--phrasings','named','--question-set','v2','--scenario-extra-count',str(m),'--holdout-agents','A',
         '--changes','append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror',
         '--repeats','1','--first-repeat','1','--max-steps','20','--sql-timeout-secs','120',
         '--concurrency','1','--trace','--no-explain','--rows','1000000']
    if ds=='tpch':cmd+=['--spec','exp/2026-10-11-generality/schemas/tpch.json','--defs','exp/2026-10-11-generality/e2e/tpch-defs.json']
    return cmd

def health(port,proc):
    until=time.monotonic()+40
    while time.monotonic()<until:
        if proc.poll() is not None:raise RuntimeError(f'Service {port} exited')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=2) as response:
                if response.status==200:return
        except OSError:time.sleep(.5)
    raise RuntimeError(f'Service {port} did not start')

def main():
    p=argparse.ArgumentParser();p.add_argument('--key-file',required=True);p.add_argument('--database-env',required=True);a=p.parse_args()
    assert ROOT.name=='agentdb-diverse-scenarios-20261031'
    cfg=json.loads((HERE/'protocol.json').read_text())
    assert cfg['budget_cny']==20 and cfg['max_repeats']==1
    out=ROOT/'results/diverse-scenarios-20261031';out.mkdir(exist_ok=True)
    assert not (out/'execution-state.json').exists(),'Do not start a duplicate coordinator'
    state={'started_utc':utc(),'status':'starting','cells':[],'complete_repeats':[],'selected_extra_count':None,'implementation_revision':3}
    if (out/'development/development-record.json').exists():
        state['development']=json.loads((out/'development/development-record.json').read_text())
    save(out/'execution-state.json',state)
    files=list(HERE.glob('*.py'))+[HERE/'protocol.json',ROOT/'Cargo.toml',ROOT/'Cargo.lock']
    files+=list((ROOT/'src').rglob('*.rs'))+list((ROOT/'third_party/ace').glob('*'))+list((ROOT/'third_party/awm').glob('*'))
    files+=[ROOT/'tools/relbench/harness.py',ROOT/'tools/relbench/gmemory_service.py',ROOT/'target/release/agentdb-mid']
    files+=list((HERE/'question-banks').rglob('question-bank.json'))
    provenance=json.loads((HERE/'data-provenance.json').read_text())
    for name,record in provenance['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==record['sha256'],name
        files.append(ROOT/name)
    manifest={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()}
    gcore=ROOT/'results/ext/GMemory'
    manifest.update({'gmemory-core/'+str(f.relative_to(gcore)):hashlib.sha256(f.read_bytes()).hexdigest() for f in gcore.rglob('*.py') if '.git' not in f.parts})
    previous=json.loads((HERE/'previous-source-manifest.json').read_text())
    protected=[k for k in previous if k.startswith(('third_party/','gmemory-core/')) or k in ['tools/relbench/harness.py','tools/relbench/gmemory_service.py']]
    assert all(manifest[k]==previous[k] for k in protected),'Published components changed'
    save(out/'frozen-source-manifest.json',manifest)
    db={}
    for line in Path(a.database_env).read_text().splitlines():
        if line.strip().startswith('AGENTDB_URL='):db['AGENTDB_URL']=line.split('=',1)[1].strip().strip('"').strip("'")
    assert db
    env={k:v for k,v in os.environ.items() if 'proxy' not in k.lower() and not k.startswith(('OPENAI_','DEEPSEEK_'))}
    env.update(db)
    env.update(PYTHONPATH=str(ROOT/'.pydeps-relbench'),NO_PROXY='127.0.0.1,localhost',FIG6_PRESERVE_REASONING='1',
        FIG6_MEMORY_URL='http://127.0.0.1:19431/memory',OPENAI_API_KEY=TOKEN,OPENAI_MODEL=cfg['model'],
        OPENAI_REQUIRE_MODEL=cfg['model'],OPENAI_HEDGE='1',OPENAI_REASONING_EFFORT='low',OPENAI_THINKING='enabled',
        OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',MALLOC_ARENA_MAX='2')
    services=[];handles=[];deadline=datetime.fromisoformat(cfg['deadline_utc'])
    try:
        for name,port,args in [('budget-proxy',19430,['--key-file',a.key_file,'--out',str(out/'budget')]),
                               ('memory-service',19431,['--out',str(out/'memory')])]:
            log=(out/f'{name}.log').open('x');handles.append(log)
            proc=subprocess.Popen(['python3','-u',str(HERE/f'{name}.py'),'--port',str(port),*args],cwd=ROOT,env=env,
                stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            services.append(proc);(out/f'{name}.pid').write_text(str(proc.pid));health(port,proc)
        state['status']='running';save(out/'execution-state.json',state)

        def run_cell(ds,arm,m):
            key=f'{ds}-r1-{arm}';folder=out/'cells'/key;folder.mkdir(parents=True,exist_ok=False)
            expected=json.loads((HERE/f'question-banks/{ds}-m{m}/question-bank.json').read_text())
            cmd=command(ds,arm,m,folder)
            record={'key':key,'dataset':ds,'arm':arm,'repeat':1,'extra_count':m,'implementation_revision':3,
                    'eligible_for_final_comparison':True,'started_utc':utc(),'command':cmd}
            save(folder/'launch.json',record)
            cell_env={**env,'FIG6_CELL_KEY':key,'OPENAI_BASE_URL':f'http://127.0.0.1:19430/arm/{key}'}
            with (folder/'console.log').open('x') as log:
                proc=subprocess.Popen(cmd,cwd=ROOT,env=cell_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                (folder/'process.pid').write_text(str(proc.pid))
                while proc.poll() is None:
                    if datetime.now(timezone.utc)>=deadline:(out/'budget/STOP').touch(exist_ok=True)
                    time.sleep(2)
                record['returncode']=proc.returncode
            reports=list(folder.glob('metric-*/report.json'))
            record['completed']=proc.returncode==0 and len(reports)==1
            if len(reports)==1:
                report=json.loads(reports[0].read_text());rows=report['cells'][0]['records']
                actual=[{k:r[k] for k in ['phase','task','metric','ask','question']} for r in rows]
                record['completed'] &= actual==expected and report.get('database_cleaned_up') is True
                record['report_sha256']=hashlib.sha256(reports[0].read_bytes()).hexdigest()
                record['report']=str(reports[0].relative_to(ROOT));record['tasks']=len(rows)
                infra=[r['error'] for r in rows if r.get('error') and any(x in r['error'].lower() for x in ['http 402','http 5','error sending request','connection','timed out'])]
                if infra:record.update(completed=False,infrastructure_errors=infra)
            denied=out/'budget/denied-requests.jsonl'
            if denied.exists() and any(json.loads(line)['arm']==key for line in denied.read_text().splitlines()):record.update(completed=False,budget_or_configuration_denial=True)
            record['finished_utc']=utc();save(folder/'completion.json',record)
            try:
                data=json.dumps({'op':'close','key':key,'arm':arm}).encode()
                urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:19431/memory',data=data,headers={'Content-Type':'application/json'}),timeout=45).read()
            except Exception as error:record['memory_close_error']=type(error).__name__
            print(json.dumps({k:v for k,v in record.items() if k!='command'}),flush=True)
            return record

        with ThreadPoolExecutor(max_workers=2) as pool:
            m=11
            for arm in cfg['arms']:
                b=json.loads((out/'budget/budget-state.json').read_text())
                if datetime.now(timezone.utc)>=deadline or b['status']=='budget_limit' or (out/'budget/STOP').exists():
                    state['stop_reason']='budget_or_deadline';break
                if shutil.disk_usage(ROOT).free<20*1024**3:state['stop_reason']='disk_reserve';break
                assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in manifest.items() if not k.startswith('gmemory-core/')),'Frozen sources changed'
                pair=[f.result() for f in [pool.submit(run_cell,ds,arm,m) for ds in cfg['datasets']]]
                state['cells']+=pair;save(out/'execution-state.json',state)
                if not all(c['completed'] for c in pair):state['stop_reason']='incomplete_cell';break
                if arm=='ace':
                    b=json.loads((out/'budget/budget-state.json').read_text())
                    first=min(c['started_utc'] for c in pair)
                    cost=sum(r['ceiling_cny'] for r in (json.loads(line) for line in (out/'budget/api-usage.jsonl').read_text().splitlines())
                             if r['utc']>=first and r['arm'] in {c['key'] for c in pair})
                    remaining=20-max(b['ceiling_cny'],b.get('observed_account_decrease_cny',0))
                    gate=cfg['scenario_extra_count'];candidates=[]
                    for n in range(12):
                        required=gate['projection_safety_factor']*gate['other_to_ace_cost_ratio']*cost*(23+n)/34+gate['reserve_cny']
                        candidates.append({'extra_count':n,'required_cny':required,'fits':required<remaining})
                    fits=[c for c in candidates if c['fits']]
                    decision={'utc':utc(),'ace_pair_upper_cny':cost,'remaining_cny':remaining,'candidates':candidates,
                              'selected_extra_count':max(c['extra_count'] for c in fits) if fits else None,'uses_accuracy':False}
                    save(out/'selection-decision.json',decision)
                    if not fits:state['stop_reason']='insufficient_matched_budget';break
                    m=decision['selected_extra_count'];state['selected_extra_count']=m
                    save(out/'execution-state.json',state)
        if len(state['cells'])==8 and all(c['completed'] for c in state['cells']):state['complete_repeats']=[1]
        state.update(status='complete' if state['complete_repeats'] else 'incomplete',finished_utc=utc())
        save(out/'execution-state.json',state)
    except Exception as error:
        state.update(status='failed',error=f'{type(error).__name__}: {error}',finished_utc=utc());save(out/'execution-state.json',state);raise
    finally:
        for proc in reversed(services):
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(35)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL)
        for log in handles:log.close()

if __name__=='__main__':main()
