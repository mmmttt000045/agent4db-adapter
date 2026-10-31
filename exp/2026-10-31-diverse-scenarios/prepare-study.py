"""Prepare a bounded, outcome-independent expansion; never reset cumulative spending."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'2026-10-31-corrected-scenarios'
ROOT=HERE.parents[1]

def change(text,old,new):
    assert text.count(old)==1,(text.count(old),old[:80])
    return text.replace(old,new)

def main():
    assert not (HERE/'protocol.json').exists(),'Inspect prepared files before replacing the protocol'
    old=json.loads((OLD/'protocol.json').read_text(encoding='utf-8'))
    stats=json.loads((OLD/'study-stats.json').read_text(encoding='utf-8'))
    ace=sum(stats['datasets'][ds]['arms']['ace']['runs'][0]['priced_usage_cny'] for ds in old['datasets'])
    other=sum(stats['datasets'][ds]['arms'][arm]['runs'][0]['priced_usage_cny'] for ds in old['datasets'] for arm in old['arms'] if arm!='ace')
    ledger=ROOT/'results/corrected-scenarios-20261031/budget/api-usage.jsonl'
    cfg={**old,'study':'diverse-scenarios-20261031','created_utc':datetime.now(timezone.utc).isoformat(),
         'authorization':'Optimize the implementation and increase question quantity/diversity, keeping the cumulative CNY20 limit and compact figure/paper.',
         'max_repeats':1,'question_set':'v2','scored_forms':['single','diff','rank_month','peak_rise','above_mean'],
         'workload_scope':'Same two schemas, M1/M3/M5 and all eleven independent changes. Six heldout questions per cell and one mandatory question per change; up to one further question per change under a predeclared cost gate.',
         'question_selection':'Fixed five-form cycle (3*phase_index+1+2*slot)%5, affected metric cycle, August and difference holdouts. Historical backfill questions target the affected learning year. No score-based selection.',
         'scenario_extra_count':{'max':11,'mandatory_scored_per_cell':17,'target_scored_per_cell':28,
             'second_question_rank':'(phase_index*7+3)%11',
             'gate':'ACE runs max=11 first on both schemas. Choose the largest M0..11 whose projected remaining full-method cost fits; apply the same M to every arm. ACE second questions outside M remain archived/charged and cannot affect selected tasks after branch restore.',
             'other_to_ace_cost_ratio':other/ace,'projection_safety_factor':1.15,'reserve_cny':.15,
             'previous_ace_cost_cny':ace,'previous_other_cost_cny':other},
         'execution_order':'ACE, AWM, G-Memory, MAVRA; datasets run in parallel, one agent task per cell. One matched run; adaptive extra count uses spending only.',
         'selection':'All eleven original scenarios are mandatory, including lossy dates and units. All outcomes on the selected common bank enter accuracy. Original study retained separately; versions are not pooled.',
         'expected_tasks_per_cell':'23+M; ACE raw max34; selected34 when M=11',
         'expected_scored_tasks_per_cell':'17+M on each schema/arm',
         'prior_priced_usage_cny':14.30771646,'prior_actual_debit_cny':14.30,
         'prior_private_budget':'/root/agentdb-corrected-scenarios-20261031/results/corrected-scenarios-20261031/budget/budget-state.json',
         'prior_batch_requests':1766,'prior_cumulative_requests':5144,'prior_floor_before_batch_cny':8.69698742,
         'prior_public_archive_sha256':'dfe1e2fb3ed6f4c6f86417bdbfa97cfd0c01999e7dabb5129c460dfa61b8e320',
         'prior_ledger_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest(),
         'repairs':['Table-owned filter qualification fixes ambiguous shared column names in metric/feature compilation',
                    'run_metric compiles stored definitions for model-supplied kinds/periods and retains revision/snapshot checks',
                    'Common business-key evidence instruction for all methods; native tool-use guidance for available metric execution'],
         'data_changes':'None: original generators, templates and reference libraries retained, including known clone-growth and missing-date limitations.',
         'reporting':'Equal setting weights, then group means. Full common selected question bank, no incomplete method substitution. One run is not statistical-significance evidence. Include total cumulative spending and every discarded extra request.'}
    (HERE/'protocol.json').write_text(json.dumps(cfg,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    proxy=(OLD/'budget-proxy.py').read_text(encoding='utf-8').replace('corrected-scenarios-20261031','diverse-scenarios-20261031')
    proxy=proxy.replace('default=19330','default=19430').replace('results/published-scenarios-20261030/budget','results/diverse-scenarios-20261031/budget').replace('CNY/M peak prices','CNY/M weekend prices')
    proxy=change(proxy,"prior['calls'] != 3378","prior['calls'] != self.config['prior_batch_requests']")
    proxy=change(proxy,"computed = sum(upper_cost(row['usage']) for row in rows)",
        "assert abs(prior['prior_cost_cny']-self.config['prior_floor_before_batch_cny'])<1e-8\n            computed = prior['prior_cost_cny'] + sum(upper_cost(row['usage']) for row in rows)")
    proxy=change(proxy,"if abs(computed-self.config['prior_priced_usage_cny'])>1e-8:",
        "if abs(computed-self.config['prior_priced_usage_cny'])>1e-8 or abs(computed-prior['ceiling_cny'])>1e-8:")
    (HERE/'budget-proxy.py').write_text(proxy,encoding='utf-8')
    memory=(OLD/'memory-service.py').read_text(encoding='utf-8').replace('corrected-scenarios-20261031','diverse-scenarios-20261031')
    memory=memory.replace('19330','19430').replace('19331','19431')
    memory=change(memory,'self.actor.timeline = {"K": 32 if key.startswith("synthetic-") else 26}','self.actor.timeline = {"K": 34}')
    old_observations='''observations = [{"tool": e["tool"], "output": e["output"][:350]}
                        for e in req["transcript"] if e.get("kind")=="tool" and e.get("tool")=="run_sql"][-3:]
        self.feedback.append({"question":req["question"], "own_answer":req.get("answer"),
            "correct":bool(req["correct"]), "own_sql":(req.get("sql") or "")[:1800], "own_observations":observations})'''
    new_observations='''executions = [e for e in req["transcript"] if e.get("kind")=="tool" and e.get("tool") in ("run_sql","run_metric")]
        observations=[]
        own_sql=req.get("sql") or ""
        for e in executions:
            output=e["output"]
            try:
                value=json.loads(output)
                if isinstance(value,dict):
                    output=json.dumps({k:value[k] for k in ("ref","result","source") if k in value},ensure_ascii=False) if "result" in value else output
                    if not req.get("sql"): own_sql=value.get("sql") or e.get("input",{}).get("sql") or own_sql
            except (ValueError,TypeError): pass
            observations.append({"tool":e["tool"],"output":output[:350]})
        self.feedback.append({"question":req["question"], "own_answer":req.get("answer"),
            "correct":bool(req["correct"]), "own_sql":own_sql[:1800], "own_observations":observations[-3:]})'''
    memory=change(memory,old_observations,new_observations)
    memory=memory.replace('e.get("kind")=="tool" and e.get("tool") in ("run_sql","run_metric")','e.get("kind","tool")=="tool" and e.get("tool") in ("run_sql","run_metric")')
    memory=change(memory,'period = req["ask"]["period"]',
        'ask = req["ask"]\n        # Question anchor used only as harness task-file metadata.\n        period = ask.get("period") or ask.get("a") or {"year": ask["year"], "m1": 1}')
    (HERE/'memory-service.py').write_text(memory,encoding='utf-8')
    for name in ['archive-results.py','test-budget.py']:
        (HERE/name).write_bytes((OLD/name).read_bytes())
    close=(OLD/'close-study.py').read_text(encoding='utf-8').replace('corrected-scenarios-20261031','diverse-scenarios-20261031')
    close=close.replace('3378+b[\'calls\']','5144+b[\'calls\']').replace("prefix='agentdb_fig6fix_'","prefix='agentdb_fig6div_'")
    (HERE/'close-study.py').write_text(close,encoding='utf-8')
    print(json.dumps({'prior_floor_cny':cfg['prior_priced_usage_cny'],'remaining_upper_cny':20-cfg['prior_priced_usage_cny'],
        'target_scored':224,'forms':cfg['scored_forms'],'all_changes_retained':True,'new_paid_calls':0}))

if __name__=='__main__':main()
