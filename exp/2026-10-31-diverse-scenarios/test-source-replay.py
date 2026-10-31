"""Engineering-only replay of each valid control; extra questions use a local fake model."""
import argparse,importlib.util,json,os,signal,subprocess,threading,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
runner=module('reuse_runner',HERE/'run-paired-reuse.py');smoke=module('smoke',HERE/'offline-smoke.py')
def read(p):return json.loads(p.read_text())

def main():
    p=argparse.ArgumentParser();p.add_argument('--only',default='');p.add_argument('--native',action='store_true');a=p.parse_args()
    out=ROOT/('results/offline-native-source-replay' if a.native else 'results/offline-source-replay');out.mkdir(exist_ok=False)
    cfg=read(HERE/'paired-reuse-protocol.json');controls=cfg['controls']
    source_root=cfg['controls_source'];api_root=source_root
    if a.native:
        source_root=str(ROOT/'results/diverse-scenarios-20261031/paired-reuse');api_root=str(ROOT/'results/diverse-scenarios-20261031')
        controls=read(Path(source_root)/'execution-state.json')['native_cells'];assert len(controls)==2 and all(c['completed'] for c in controls)
    if a.only:controls=[c for c in controls if c['key']==a.only]
    plans={f'{c["dataset"]}-r1-{c["arm"]}-source-smoke':{'root':source_root,'api_root':api_root,'key':c['key'],'arm':c['arm']} for c in controls}
    plan=out/'plan.json';plan.write_text(json.dumps(plans,indent=2)+'\n')
    env={k:v for k,v in os.environ.items() if 'proxy' not in k.lower() and not k.startswith(('OPENAI_','DEEPSEEK_'))}
    env.update(PYTHONPATH=str(ROOT/'.pydeps-relbench'),NO_PROXY='127.0.0.1,localhost',FIG6_PRESERVE_REASONING='1',FIG6_LEGACY_SHARED_PROMPT='1',
        FIG6_MEMORY_URL='http://127.0.0.1:19541/memory',OPENAI_API_KEY='offline-only',OPENAI_MODEL='deepseek-flash',OPENAI_REQUIRE_MODEL='deepseek-flash',
        OPENAI_HEDGE='1',OPENAI_THINKING='enabled',OPENAI_REASONING_EFFORT='low',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2')
    for line in Path('/root/agentdb-mid/.env').read_text().splitlines():
        if line.startswith('AGENTDB_URL='):env['AGENTDB_URL']=line.split('=',1)[1].strip().strip('"').strip("'")
    fake=ThreadingHTTPServer(('127.0.0.1',19540),smoke.Fake);threading.Thread(target=fake.serve_forever,daemon=True).start()
    services=[];logs=[];checked=[]
    try:
        for name,port,args in [('source-cache-front',19542,['--plan',str(plan),'--out',str(out/'cache'),'--upstream','http://127.0.0.1:19540']),
             ('seed-memory-service',19541,['--plan',str(plan),'--out',str(out/'memory'),'--proxy','http://127.0.0.1:19542','--front','http://127.0.0.1:19542'])]:
            log=(out/f'{name}.log').open('x');logs.append(log)
            proc=subprocess.Popen(['python3','-u',str(HERE/f'{name}.py'),'--port',str(port),*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            services.append(proc);runner.health(port,proc)
        for c in controls:
            key=f'{c["dataset"]}-r1-{c["arm"]}-source-smoke';folder=out/'cells'/key;folder.mkdir(parents=True)
            cmd=runner.command(c['dataset'],folder,extra=4,no_changes=True);cmd[cmd.index('--modes')+1]={'ace':'paper-ace','awm':'paper-awm','gmemory':'paper-gmemory','mavra':'metric-global-full'}[c['arm']]
            cmd[0]=str(ROOT/'target/release/agentdb-extra');cmd+=['--additional-holdout-agent','B']
            with (folder/'console.log').open('x') as log:
                result=subprocess.run(cmd,cwd=ROOT,env={**env,'FIG6_CELL_KEY':key,'OPENAI_BASE_URL':f'http://127.0.0.1:19542/arm/{key}'},stdout=log,stderr=subprocess.STDOUT,timeout=900)
            assert result.returncode==0,(key,'Native smoke failed')
            report=read(next(folder.glob('metric-*/report.json')));records=report['cells'][0]['records'];assert len(records)==13 and report['database_cleaned_up']
            old=read(next((Path(source_root)/'cells'/c['key']).glob('metric-*/report.json')))['cells'][0]['records'][:9]
            assert [{k:r[k] for k in ['phase','task','question','ask','gold','answer','outcome']} for r in records[:9]]==[{k:r[k] for k in ['phase','task','question','ask','gold','answer','outcome']} for r in old]
            restored=read(out/'memory'/key/'seed-restoration.json');assert restored['source_tasks']==9 and restored['new_api_calls_for_source']==0
            journal=[json.loads(line) for line in (out/'memory'/key/'memory-events.jsonl').read_text().splitlines()]
            begin=next(e for e in journal if e['event']=='request' and e['request']['op']=='begin' and e['request']['phase']=='holdout-extra')
            response=next(e['response'] for e in journal if e['event']=='response' and e['index']==begin['index'])
            assert begin['request']['agent']=='B' and response['common_feedback']==[]
            if c['arm']=='ace':assert response['playbook_bullets']==0
            if c['arm']=='awm':assert response['workflow_chars']==0
            payload=json.dumps({'op':'close','key':key,'arm':c['arm']}).encode();urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:19541/memory',data=payload,headers={'Content-Type':'application/json'}),timeout=30).read()
            checked.append({'cell':key,'source_tasks_verified':9,'extra_tasks':4,'paid_model_calls':0,'restoration':restored})
            print(json.dumps({'passed':key,'source_tasks':9,'fake_extra_tasks':4}),flush=True)
        assert smoke.Fake.missing_reasoning_echo==0
        result={'status':'passed','paid_model_calls':0,'scientific_evidence':False,'cells':checked,'rich_source_and_real_published_update_inputs_verified':True}
        (HERE/('native-source-replay-smoke.json' if a.native else 'source-replay-smoke.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','controls':len(checked),'paid_model_calls':0}))
    finally:
        for proc in reversed(services):
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(20)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL)
        for log in logs:log.close()
        fake.shutdown()

if __name__=='__main__':main()
