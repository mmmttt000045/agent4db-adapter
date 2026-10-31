"""Fresh cross-form queries from each method's condition-matched source checkpoint."""
import argparse,hashlib,importlib.util,json,os,signal,subprocess,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('base_runner',HERE/'run-paired-reuse.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
read,save,now=base.read,base.save,base.now

def main():
    p=argparse.ArgumentParser();p.add_argument('--key-file',required=True);p.add_argument('--database-env',required=True);a=p.parse_args()
    parent=ROOT/'results/diverse-scenarios-20261031';formal=parent/'paired-reuse';state=read(formal/'execution-state.json')
    assert state['status']=='native_base_complete' and all(c['completed'] for c in state['native_cells'])
    n=state['selected_extra_count'];assert 0<n<=4
    for name,count in [('source-replay-smoke.json',6),('native-source-replay-smoke.json',2)]:
        proof=read(HERE/name);assert proof['status']=='passed' and proof['paid_model_calls']==0 and len(proof['cells'])==count
    assert read(formal/'extra-decision.json')['uses_accuracy'] is False
    cfg=read(HERE/'paired-reuse-protocol.json');out=formal/'extra-evaluation';out.mkdir(exist_ok=False)
    plans={}
    for c in cfg['controls']:
        plans[f'{c["dataset"]}-r1-{c["arm"]}-extra']={'root':cfg['controls_source'],'api_root':cfg['controls_source'],'key':c['key'],'arm':c['arm']}
    for c in state['native_cells']:
        plans[f'{c["dataset"]}-r1-mavra-extra']={'root':str(formal),'api_root':str(parent),'key':c['key'],'arm':'mavra'}
    save(out/'source-plan.json',plans)
    files=[HERE/name for name in ['source-cache-front.py','seed-memory-service.py','memory-service.py','run-extra-questions.py','paired-reuse-protocol.json','extra-protocol.json']]+[ROOT/'target/release/agentdb-extra',ROOT/'extra-source/Cargo.toml']+list((ROOT/'extra-source/src').rglob('*.rs'))
    frozen={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files};save(out/'frozen-source-manifest.json',frozen)
    env={k:v for k,v in os.environ.items() if 'proxy' not in k.lower() and not k.startswith(('OPENAI_','DEEPSEEK_'))}
    for line in Path(a.database_env).read_text().splitlines():
        if line.startswith('AGENTDB_URL='):env['AGENTDB_URL']=line.split('=',1)[1].strip().strip('"').strip("'")
    env.update(PYTHONPATH=str(ROOT/'.pydeps-relbench'),NO_PROXY='127.0.0.1,localhost',FIG6_PRESERVE_REASONING='1',FIG6_LEGACY_SHARED_PROMPT='1',FIG6_MEMORY_URL='http://127.0.0.1:19431/memory',
        OPENAI_API_KEY='diverse-scenarios-20261031-local',OPENAI_MODEL='deepseek-flash',OPENAI_REQUIRE_MODEL='deepseek-flash',OPENAI_HEDGE='1',OPENAI_THINKING='enabled',OPENAI_REASONING_EFFORT='low',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
    b=read(parent/'budget/budget-state.json');assert abs(b['reserved_cny'])<1e-8 and (parent/'budget/STOP').exists();(parent/'budget/STOP').unlink()
    state.update(status='running_extra_questions',extra_started_utc=now());save(formal/'execution-state.json',state)
    services=[];logs=[]
    try:
        for name,port,args in [('budget-proxy',19430,['--key-file',a.key_file,'--out',str(parent/'budget')]),
              ('source-cache-front',19432,['--plan',str(out/'source-plan.json'),'--out',str(out/'cache')]),
              ('seed-memory-service',19431,['--plan',str(out/'source-plan.json'),'--out',str(out/'memory')])]:
            log=(out/f'{name}.log').open('x');logs.append(log)
            proc=subprocess.Popen(['python3','-u',str(HERE/f'{name}.py'),'--port',str(port),*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            services.append(proc);base.health(port,proc)
        def cell(ds,arm):
            key=f'{ds}-r1-{arm}-extra';folder=out/'cells'/key;folder.mkdir(parents=True)
            cmd=base.command(ds,folder,extra=n,no_changes=True);cmd[cmd.index('--modes')+1]={'ace':'paper-ace','awm':'paper-awm','gmemory':'paper-gmemory','mavra':'metric-global-full'}[arm]
            cmd[0]=str(ROOT/'target/release/agentdb-extra');cmd+=['--additional-holdout-agent','B']
            record={'key':key,'dataset':ds,'arm':arm,'extra_count':n,'started_utc':now(),'source':plans[key],'command':cmd};save(folder/'launch.json',record)
            with (folder/'console.log').open('x') as log:
                proc=subprocess.Popen(cmd,cwd=ROOT,env={**env,'FIG6_CELL_KEY':key,'OPENAI_BASE_URL':f'http://127.0.0.1:19432/arm/{key}'},stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                (folder/'process.pid').write_text(str(proc.pid));record['returncode']=proc.wait()
            reports=list(folder.glob('metric-*/report.json'));record['completed']=record['returncode']==0 and len(reports)==1
            if reports:
                report=read(reports[0]);records=report['cells'][0]['records'];expected=read(HERE/f'reuse-banks/{ds}-extra{n}/question-bank.json')
                record['completed'] &= len(records)==9+n and [{k:r[k] for k in ['phase','task','metric','ask','question']} for r in records]==expected and report['database_cleaned_up']
                restoration=read(out/'memory'/key/'seed-restoration.json');assert restoration['source_tasks']==9 and restoration['new_api_calls_for_source']==0
                record.update(report=str(reports[0].relative_to(parent)),report_sha256=hashlib.sha256(reports[0].read_bytes()).hexdigest(),restoration=restoration)
            denied=parent/'budget/denied-requests.jsonl'
            if denied.exists() and any(json.loads(line)['arm']==key for line in denied.read_text().splitlines()):record['completed']=False
            record['finished_utc']=now();save(folder/'completion.json',record)
            data=json.dumps({'op':'close','key':key,'arm':arm}).encode();urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:19431/memory',data=data,headers={'Content-Type':'application/json'}),timeout=30).read()
            print(json.dumps({k:v for k,v in record.items() if k!='command'}),flush=True);return record
        with ThreadPoolExecutor(max_workers=1) as pool:
            for arm in ['ace','awm','gmemory','mavra']:
                assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in frozen.items())
                pair=[f.result() for f in [pool.submit(cell,ds,arm) for ds in ['synthetic','tpch']]]
                state['extras']+=pair;save(formal/'execution-state.json',state)
                if not all(c['completed'] for c in pair):break
        state.update(status='complete' if len(state['extras'])==8 and all(c['completed'] for c in state['extras']) else 'incomplete',finished_utc=now())
        if state['status']=='complete':state['complete_repeats']=[1]
        save(formal/'execution-state.json',state)
    finally:
        (parent/'budget/STOP').touch()
        for proc in reversed(services):
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(20)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL)
        for log in logs:log.close()

if __name__=='__main__':main()
