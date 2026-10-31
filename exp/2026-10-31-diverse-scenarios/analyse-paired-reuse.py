"""Condition-matched frozen controls, fresh native runs and fresh cross-form queries."""
import argparse,copy,hashlib,importlib.util,json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('shared_analysis',HERE/'analyse.py');shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
ARMS=shared.ARMS;NAMES=shared.NAMES
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def lines(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def report(folder):
    p,=folder.glob('metric-*/report.json');return p,read(p)
def events(path):
    pending={};out=[]
    for e in lines(path):
        if e['event']=='request':pending[e['index']]=e
        else:
            q=pending.pop(e['index']);assert 'error' not in e['response'];out.append((q,e))
    assert not pending
    return out

def audit_extra(journal,source_journal,arm,records,n):
    actual=events(journal);source=events(source_journal);prefix=[]
    for q,r in source:
        prefix.append((q,r))
        if q['request']['op']=='checkpoint':break
    source_index=0;history=[];snapshot=None;counts=Counter();index=0;extra_seen=0;feedback_agent='A'
    for q,r in actual:
        req=q['request'];response=r['response'];op=req['op'];counts[op]+=1
        if op=='end':
            assert any(e.get('kind')=='assistant' for e in req['transcript'])
            assert all('kind' in e for e in req['transcript'])
            assert any(e.get('tool')=='final_answer' for e in req['transcript'])
        if source_index<len(prefix):
            old_q,old_r=prefix[source_index];old=old_q['request'];assert old['op']==op
            for field in ['phase','task','metric','ask','question']:
                if field in old:assert req[field]==old[field]
            if op=='begin':
                if arm!='mavra':
                    # Replayed controls return the exact source planner prompts.
                    # dispatch overwrites the unused feedback metadata before the
                    # source state is loaded at the checkpoint; no model is called.
                    assert {k:v for k,v in response.items() if k!='common_feedback'}=={k:v for k,v in old_r['response'].items() if k!='common_feedback'}
                    assert response['common_feedback']==[]
                    block=response['system_prompt'].split('Environment feedback from your own earlier tasks (binary correctness; no reference answers):\n',1)[1].split('\n',1)[0]
                    assert json.loads(block)==history
                else:assert response['common_feedback']==history
            elif op=='end':
                assert req['answer']==old['answer'] and bool(req['correct'])==bool(old['correct'])
                assert bool(req['correct'])==(records[index]['outcome']=='correct');index+=1
                reference=req if arm=='mavra' else old
                history=(history+[shared.feedback_item(reference)])[-3:]
            elif op=='checkpoint':snapshot=copy.deepcopy(history)
            source_index+=1
            continue
        if op=='restore':assert snapshot is not None;history=copy.deepcopy(snapshot);feedback_agent='A'
        elif op=='begin':
            assert req['agent']=='B'
            if req['agent']!=feedback_agent:history=[];feedback_agent=req['agent']
            assert req['phase']=='holdout-extra' and response['common_feedback']==history
            block=response['system_prompt'].split('Environment feedback from your own earlier tasks (binary correctness; no reference answers):\n',1)[1].split('\n',1)[0]
            assert json.loads(block)==history
        elif op=='end':
            assert req['phase']=='holdout-extra' and req['question']==records[index]['question']
            assert bool(req['correct'])==(records[index]['outcome']=='correct')
            index+=1;extra_seen+=1;history=(history+[shared.feedback_item(req)])[-3:]
        else:assert op=='close'
    assert source_index==len(prefix) and index==9+n and extra_seen==n and counts['restore']==1
    return dict(counts)

def native_evidence(rows,journal,learning,selected_phase=None):
    ends=[q['request'] for q,r in events(journal) if q['request']['op']=='end'];assert len(rows)==len(ends)
    counts=Counter();forms=Counter();failures=[]
    for row,end in zip(rows,ends):
        if selected_phase and row['phase']!=selected_phase:continue
        executions=[]
        for e in end['transcript']:
            if e.get('kind','tool')!='tool' or e.get('tool') not in ['run_sql','run_metric']:continue
            try:value=json.loads(e['output'])
            except (ValueError,TypeError):value={'raw':e['output']}
            if e['tool']=='run_metric':
                counts['attempted']+=1
                if isinstance(value,dict) and 'ref' in value and 'result' in value:
                    counts['executed']+=1;forms[row['ask']['kind']]+=1
                else:counts['denied_or_error']+=1
            executions.append({'tool':e['tool'],'input':e['input'],'output':value,'status':e.get('status')})
        if row['phase']!='learn' and row['outcome']!='correct':
            failures.append({k:row.get(k) for k in ['phase','task','ask','question','answer','gold','outcome','error']}|{'executions':executions})
    return {'run_metric':dict(counts),'run_metric_forms':dict(forms),'failures':failures,
            'learning_publications':[{'task':x.get('task'),'event':(x.get('submit') or {}).get('event'),'failed_gate':(x.get('submit') or {}).get('failed_gate'),'reason':(x.get('submit') or {}).get('reason')} for x in learning]}

def audit_fresh_api(root,state):
    rows=lines(root/'budget/api-transcripts.jsonl')
    fresh={c['key']:c['arm'] for c in [*state['native_cells'],*state['extras']]}
    checks={}
    for key,arm in fresh.items():
        selected=[x for x in rows if x['arm']==key];assert selected
        planning=[x for x in selected if x['request'].get('tools')]
        memory=[x for x in selected if not x['request'].get('tools')]
        for x in selected:
            q=x['request'];assert q['model']==x['response']['model']=='deepseek-flash' and 0<q['max_tokens']<=16384
            if q.get('tools'):
                system='\n'.join(str(y.get('content','')) for y in q['messages'] if y['role']=='system')
                assert 'Environment feedback from your own earlier tasks' in system
                assert q['thinking']=={'type':'enabled'} and q.get('reasoning_effort')=='low'
            elif arm in ['awm','gmemory']:
                assert q['thinking']=={'type':'disabled'} and q['max_tokens']==(2048 if arm=='awm' else 512)
        raw='\n'.join(json.dumps(x['request'],ensure_ascii=False) for x in memory)
        if arm=='ace':assert 'TOOL CALL run_sql' in raw and 'TOOL OUTPUT' in raw
        if arm=='awm':assert 'run_sql(' in raw and '<action>' in raw
        if arm=='gmemory':assert 'run_sql:' in raw
        checks[key]={'planning_calls':len(planning),'memory_or_extraction_calls':len(memory),'full_actual_update_inputs':True}
    return checks

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--controls',type=Path,required=True);a=p.parse_args()
    root=a.results;formal=root/'paired-reuse';cfg=read(HERE/'paired-reuse-protocol.json');ep=read(HERE/'extra-protocol.json');state=read(formal/'execution-state.json')
    assert state['status']=='complete' and len(state['native_cells'])==2 and all(c['completed'] for c in state['native_cells'])
    n=state['selected_extra_count'];assert 0<=n<=4
    if n:assert len(state['extras'])==8 and all(c['completed'] for c in state['extras'])
    decision=read(formal/'extra-decision.json');assert n==max(c['extra_count'] for c in decision['candidates'] if c['fits']) and not decision['uses_accuracy']
    groups=copy.deepcopy(ep['aggregation'])
    if not n:groups.pop('novel');groups['all'].remove('holdout-extra')
    usage=lines(root/'budget/api-usage.jsonl');b=read(root/'budget/budget-state.json');close=read(root/'financial-close.json')
    assert len(usage)==b['calls']==close['requests'] and abs(b['reserved_cny'])<1e-8
    assert abs(b['prior_cost_cny']+sum(u['ceiling_cny'] for u in usage)-b['ceiling_cny'])<1e-7
    assert max(b['ceiling_cny'],close['account_decrease_cny'])<=20+1e-8 and (root/'budget/STOP').exists()
    assert close['cumulative_requests']==5144+len(usage)
    data={'study':'paired-reuse-20261031','study_status':'complete','implementation_revision':4,'complete_repeats':[1],
          'selected_extra_count':n,'groups':groups,'display_groups':ep['display_groups_if_extended' if n else 'display_groups_if_not_extended'],
          'aggregation':ep['weighting'],'datasets':{},'reused_control_cells':6,'fresh_native_base_cells':2,'extra_cells':8 if n else 0,
          'feedback_policy':cfg['feedback'],'source_protocol_sha256':sha(HERE/'paired-reuse-protocol.json'),'extra_protocol_sha256':sha(HERE/'extra-protocol.json'),
          'cost':{'authorization_cny':20,'upper_cny':b['ceiling_cny'],'priced_usage_cny':14.30771646+sum(shared.priced(u) for u in usage),
                  'prior_usage_floor_cny':b['prior_cost_cny'],'incremental_usage_cny':sum(shared.priced(u) for u in usage),'requests':len(usage),
                  'cumulative_requests':close['cumulative_requests'],'account_decrease_observed_cny':close['account_decrease_cny'],
                  'http_errors':b['errors'],'models':b['models'],'includes':'All previous, invalid, interrupted, current and extra official API calls; cached paid-source replay creates no new charge.'}}
    audit={'status':'passed','matched_reference_hashes':{},'cells':[],'fresh_api_profiles':audit_fresh_api(root,state)};case={'study':data['study'],'native':{}};macros=[];total=0;learning_total=0
    md=['# Fig.6: checked execution and cross-form transfer','',f'All six unchanged baseline controls are retained from the valid corrected cohort; the changed native method is rerun. Additional M3 forms: {n}/schema, chosen by spending only.','',
        '| Schema | Method | Non-breaking | Covered breaks | New forms | All settings |','|---|---|---:|---:|---:|---:|']
    for ds,prefix in [('synthetic','PubSynth'),('tpch','PubTpch')]:
        dataset={'arms':{}};unique=None
        for arm in ARMS:
            if arm=='mavra':
                c,=[c for c in state['native_cells'] if c['dataset']==ds];folder=formal/'cells'/c['key'];journal=formal/'memory'/c['key']/'memory-events.jsonl';origin='fresh native'
            else:
                c,=[c for c in cfg['controls'] if c['dataset']==ds and c['arm']==arm];folder=a.controls/'cells'/c['key'];journal=a.controls/'memory'/c['key']/'memory-events.jsonl';origin='unchanged frozen control'
            rp,report_data=report(folder);assert sha(rp)==c['report_sha256'];cell=report_data['cells'][0];base_rows=cell['records'];assert report_data['database_cleaned_up']
            operations,_=shared.audit_journal(journal,base_rows);rows=list(base_rows)
            audit['cells'].append({'dataset':ds,'arm':arm,'origin':origin,'tasks':len(rows),'operations':operations,'journal_sha256':sha(journal)})
            if arm=='mavra':case['native'][ds]={'base':native_evidence(base_rows,journal,cell.get('learning',[]))}
            if n:
                extra,=[c for c in state['extras'] if c['dataset']==ds and c['arm']==arm];ef=formal/'extra-evaluation/cells'/extra['key'];ej=formal/'extra-evaluation/memory'/extra['key']/'memory-events.jsonl'
                erp,erd=report(ef);assert sha(erp)==extra['report_sha256'];erows=erd['cells'][0]['records'];assert erd['database_cleaned_up']
                ops=audit_extra(ej,journal,arm,erows,n);added=[r for r in erows if r['phase']=='holdout-extra'];assert len(added)==n;rows+=added
                audit['cells'].append({'dataset':ds,'arm':arm,'origin':'fresh extra branch','source_tasks_not_counted_twice':9,'tasks':n,'operations':ops,'journal_sha256':sha(ej)})
                if arm=='mavra':case['native'][ds]['extra']=native_evidence(erows,ej,[],selected_phase='holdout-extra')
            refs=[{k:r[k] for k in ['phase','task','metric','agent','ask','question','gold']} for r in rows]
            digest=hashlib.sha256(json.dumps(refs,sort_keys=True,ensure_ascii=False).encode()).hexdigest();assert audit['matched_reference_hashes'].setdefault(ds,digest)==digest
            phase_data={}
            for ph in ['learn',*groups['all']]:
                selected=[r for r in rows if r['phase']==ph];assert selected
                phase_data[ph]={'correct':sum(r['outcome']=='correct' for r in selected),'n':len(selected),'outcomes':dict(Counter(r['outcome'] for r in selected))}
            scores={}
            for group,phases in groups.items():
                value=100*sum(phase_data[ph]['correct']/phase_data[ph]['n'] for ph in phases)/len(phases)
                scores[group]={'accuracy_pct':value,'run_values_pct':[value],'range_pct':[value,value]}
                macros.append(f'\\newcommand{{\\{prefix}{NAMES[arm].replace("-", "")}{group.capitalize()}}}{{{value:.1f}}}')
            measured=[u for u in usage if u.get('arm')==f'{ds}-r1-{arm}-extra'] if n else []
            extra_usage={'questions':n,'official_calls':len(measured),'prompt_tokens':sum(u['usage']['prompt_tokens'] for u in measured),
                         'output_tokens':sum(u['usage']['completion_tokens'] for u in measured),
                         'total_tokens':sum(u['usage']['total_tokens'] for u in measured),'priced_cny':sum(shared.priced(u) for u in measured),
                         'includes':'Fresh consumer planning and normal published memory updates; cached source replay excluded.'}
            if n:assert measured
            dataset['arms'][arm]={'runs':[{'repeat':1,'source':origin,'phases':phase_data}],'groups':scores,'extra_usage':extra_usage}
            md.append('| '+' | '.join([ds,NAMES[arm]]+[f'{scores[g]["accuracy_pct"]:.1f}%' if g in scores else '—' for g in ['benign','modeled','novel','all']])+' |')
            count=len([r for r in rows if r['phase']!='learn']);total+=count;learning_total+=phase_data['learn']['n']
            uq=len({r['question'] for r in rows if r['phase']!='learn'});assert unique in (None,uq);unique=uq
        dataset['unique_scored_questions']=unique;dataset['scored_forms']=dict(Counter(r['ask']['kind'] for r in rows if r['phase']!='learn'));data['datasets'][ds]=dataset
    data.update(scored_tasks=total,learning_tasks=learning_total,formal_tasks=total+learning_total,
                unique_scored_questions=sum(v['unique_scored_questions'] for v in data['datasets'].values()),cached_warmup_tasks_not_scored_again=72 if n else 0)
    macros+=['\\newcommand{\\PubScenarioRepeats}{1}',f'\\newcommand{{\\PubScenarioScored}}{{{total}}}',f'\\newcommand{{\\PubExtraCount}}{{{n}}}']
    macros += [f'\\newcommand{{\\PubDistinctQuestions}}{{{data["unique_scored_questions"]}}}',f'\\newcommand{{\\PubScenarioSettings}}{{{len(groups["all"])}}}']
    joint={}
    for arm in ARMS:
        entries=[data['datasets'][ds]['arms'][arm] for ds in ['synthetic','tpch']]
        phases=[v for entry in entries for ph,v in entry['runs'][0]['phases'].items() if ph!='learn']
        correct=sum(v['correct'] for v in phases);count=sum(v['n'] for v in phases)
        joint[arm]={'equal_schema_accuracy_pct':sum(v['groups']['all']['accuracy_pct'] for v in entries)/2,
                    'correct':correct,'n':count,'micro_accuracy_pct':100*correct/count}
        macros.append(f'\\newcommand{{\\PubJoint{NAMES[arm].replace("-", "")}Acc}}{{{joint[arm]["equal_schema_accuracy_pct"]:.1f}}}')
    data['joint_summary']={'arms':joint,'weighting':'Equal weight for both schemas and all thirteen settings within each schema.',
        'status':'Descriptive summary added after execution; not a new preregistered endpoint. All methods, schemas, settings and failed answers retained.',
        'statistical_significance_claim':False}
    overview=['## Both schemas: descriptive summary','',
              'Both schemas and all settings are retained with equal weights. This summary was added after execution; it does not change the frozen protocol or claim statistical significance.','',
              '| Method | Equal-schema accuracy | Correct / answers | Micro accuracy |',
              '|---|---:|---:|---:|']
    for arm in ARMS:
        v=joint[arm]
        overview.append(f'| {NAMES[arm]} | {v["equal_schema_accuracy_pct"]:.1f}% | {v["correct"]}/{v["n"]} | {v["micro_accuracy_pct"]:.1f}% |')
    md[4:4]=overview+['']
    transfer={}
    for arm in ARMS:
        entries=[data['datasets'][ds]['arms'][arm] for ds in ['synthetic','tpch']]
        transfer[arm]={'questions':2*n,'correct':sum(v['runs'][0]['phases']['holdout-extra']['correct'] for v in entries),
                       **{k:sum(v['extra_usage'][k] for v in entries) for k in ['official_calls','total_tokens','priced_cny']}}
    baseline=min(ARMS[:-1],key=lambda arm:transfer[arm]['official_calls'])
    data['transfer_summary']={'arms':transfer,'fewest_call_baseline':baseline,
        'call_reduction_pct':100*(1-transfer['mavra']['official_calls']/transfer[baseline]['official_calls']),
        'scope':'Fresh additional queries and all normal online memory updates; original source learning excluded for every method. Whole-method comparison, not a representation ablation.'}
    for quantity,key in [('total_tokens','token_reduction_pct'),('priced_cny','priced_cost_reduction_pct')]:
        comparator=min(ARMS[:-1],key=lambda arm:transfer[arm][quantity])
        data['transfer_summary'][key]=100*(1-transfer['mavra'][quantity]/transfer[comparator][quantity])
        data['transfer_summary'][key+'_baseline']=comparator
    macros += [f'\\newcommand{{\\PubTransferCallSaving}}{{{data["transfer_summary"]["call_reduction_pct"]:.1f}}}',
               f'\\newcommand{{\\PubTransferTokenSaving}}{{{data["transfer_summary"]["token_reduction_pct"]:.1f}}}']
    macros += [f'\\newcommand{{\\PubTransferMAVRACorrect}}{{{transfer["mavra"]["correct"]}}}',f'\\newcommand{{\\PubTransferCount}}{{{2*n}}}',
               f'\\newcommand{{\\PubTransferMAVRACalls}}{{{transfer["mavra"]["official_calls"]}}}',f'\\newcommand{{\\PubTransferBaselineCalls}}{{{transfer[baseline]["official_calls"]}}}',
               f'\\newcommand{{\\PubTransferBaseline}}{{{NAMES[baseline]}}}']
    for ds in ['synthetic','tpch']:
        md+=['',f'## {ds}: all settings','','| Setting | ACE | AWM | G-Memory | MAVRA |','|---|---:|---:|---:|---:|']
        for ph in groups['all']:
            cells=[data['datasets'][ds]['arms'][arm]['runs'][0]['phases'][ph] for arm in ARMS]
            md.append('| '+' | '.join([ph]+[f'{c["correct"]}/{c["n"]}' for c in cells])+' |')
    md+=['','## Fresh transfer-query cost','','| Schema | Method | Correct | Calls | Tokens/question | CNY/question |','|---|---|---:|---:|---:|---:|']
    for ds in ['synthetic','tpch']:
        for arm in ARMS:
            v=data['datasets'][ds]['arms'][arm];u=v['extra_usage'];q=v['runs'][0]['phases']['holdout-extra']
            md.append('| '+' | '.join([ds,NAMES[arm],f'{q["correct"]}/{q["n"]}',str(u['official_calls']),f'{u["total_tokens"]/n:,.0f}',f'{u["priced_cny"]/n:.6f}'])+' |')
    md+=['',f'{total} scored answers, {learning_total} learning tasks and {data["unique_scored_questions"]} distinct scored questions. Cached source warmup is excluded from these totals.',
         f'Cumulative account debit CNY{close["account_decrease_cny"]:.2f}; conservative ceiling CNY{b["ceiling_cny"]:.6f}; all {close["cumulative_requests"]} old/new official API requests included.',
         'One run per method, with unchanged condition-matched frozen controls. No confidence intervals or statistical-significance claim. Every original failure is retained; the entire failed diverse-trajectory cohort is development-only and its costs remain charged.']
    write(HERE/'study-stats.json',data);write(HERE/'feedback-comparison-check.json',audit);write(HERE/'case-evidence.json',case)
    (HERE/'summary.md').write_text('\n'.join(md)+'\n',encoding='utf-8');(HERE/'overleaf-numbers.tex').write_text('% Generated by analyse-paired-reuse.py.\n'+'\n'.join(macros)+'\n',encoding='utf-8')
    print('\n'.join(md[:14]))

if __name__=='__main__':main()
