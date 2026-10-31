"""Free bank, cost-gate and persistent financial checks before the first model call."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--key-file',required=True);args=parser.parse_args()
    assert ROOT.name=='agentdb-diverse-scenarios-20261031'
    cfg=json.loads((HERE/'protocol.json').read_text())
    out=ROOT/'results/diverse-scenarios-20261031'
    assert not (out/'execution-state.json').exists()
    checks={}
    for ds in cfg['datasets']:
        banks=[]
        for m in range(12):
            folder=HERE/f'question-banks/{ds}-m{m}';folder.mkdir(parents=True,exist_ok=True)
            cmd=[str(ROOT/'target/release/agentdb-mid'),'--out',str(folder),'metric-bench',
                 '--question-set','v2','--scenario-extra-count',str(m),'--question-bank-only',
                 '--metrics','M1,M3,M5','--phrasings','named','--holdout-agents','A',
                 '--changes',','.join(cfg['changes'])]
            if ds=='tpch':cmd+=['--spec','exp/2026-10-11-generality/schemas/tpch.json','--defs','exp/2026-10-11-generality/e2e/tpch-defs.json']
            subprocess.run(cmd,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
            bank=json.loads((folder/'question-bank.json').read_text());banks.append(bank)
            assert len(bank)==23+m
            assert len({r['phase'] for r in bank})==13
            scored=[r for r in bank if r['phase']!='learn']
            assert len(scored)==17+m
            assert len({r['ask']['kind'] for r in scored})==5
        maximum=banks[-1]
        for bank in banks:
            selected={(r['phase'],r['task']) for r in bank}
            assert bank==[r for r in maximum if (r['phase'],r['task']) in selected]
            assert bank[:12]==maximum[:12]
            for phase in {r['phase'] for r in maximum if r['phase'] not in ('learn','holdout')}:
                assert [r for r in bank if r['phase']==phase][0]==[r for r in maximum if r['phase']==phase][0]
        checks[ds]={'variants':12,'max_tasks':len(maximum),'max_scored':len(maximum)-6,
                    'max_unique_scored_questions':len({r['question'] for r in maximum if r['phase']!='learn'}),
                    'prefix_invariance':True}
    # The engineering smoke uses different row count but exactly the same questions.
    smoke=list((ROOT/'results/offline-smoke').glob('native/metric-*/report.json'))
    if not smoke:smoke=list((ROOT/'results/offline-smoke').rglob('report.json'))
    assert len(smoke)==1
    rows=json.loads(smoke[0].read_text())['cells'][0]['records']
    # Only two clarified tie/absolute-difference phrasings changed after that smoke.
    actual=[{k:r[k] for k in ('phase','task','metric','ask')} for r in rows]
    expected=json.loads((HERE/'question-banks/synthetic-m11/question-bank.json').read_text())
    assert actual==[{k:r[k] for k in ('phase','task','metric','ask')} for r in expected]
    spec=importlib.util.spec_from_file_location('budget_proxy',HERE/'budget-proxy.py')
    proxy=importlib.util.module_from_spec(spec);spec.loader.exec_module(proxy)
    budget=proxy.Budget(out/'budget',args.key_file)
    assert budget.state['calls']==0 and budget.state['reserved_cny']==0
    assert budget.state['prior_cost_cny']+1e-7>=cfg['prior_priced_usage_cny']
    assert budget.state['prior_cost_cny']<cfg['budget_cny']
    public={'status':'passed','paid_model_calls':0,'question_banks':checks,
            'prior_cumulative_calls':cfg['prior_cumulative_requests'],
            'prior_upper_cny':budget.state['prior_cost_cny'],
            'remaining_upper_cny':cfg['budget_cny']-budget.state['prior_cost_cny'],
            'durable_budget_initialized':True,'smoke_plan_structure_matches':True}
    (HERE/'preflight-check.json').write_text(json.dumps(public,indent=2)+'\n')
    print(json.dumps(public))

if __name__=='__main__':main()
