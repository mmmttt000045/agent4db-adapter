"""Audit all raw attempts and aggregate the predeclared common question bank."""
import argparse,copy,hashlib,json
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
ARMS=['ace','awm','gmemory','mavra']
NAMES={'ace':'ACE','awm':'AWM','gmemory':'G-Memory','mavra':'MAVRA'}
PHASES={'holdout':['holdout'],'benign':['append','backfill','correct','addcol'],
        'modeled':['status','revision','dupload','dimhist','latekey']}
PHASES['all']=['holdout',*PHASES['benign'],*PHASES['modeled'],'unit','mirror']

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def lines(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s]
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def priced(row):
    u=row.get('usage')
    if not u:return row['ceiling_cny']
    local=datetime.fromisoformat(row['utc']).astimezone(timezone(timedelta(hours=8)))
    peak=local.weekday()<5 and (9<=local.hour<12 or 14<=local.hour<18)
    h,m,o=(.04,2,8) if peak else (.02,1,4)
    n=u['prompt_tokens'];hit=u.get('prompt_cache_hit_tokens',(u.get('prompt_tokens_details') or {}).get('cached_tokens',0))
    assert 0<=hit<=n
    return (hit*h+(n-hit)*m+u['completion_tokens']*o)/1e6

def feedback_item(req):
    observations=[];sql=req.get('sql') or ''
    for event in req['transcript']:
        if event.get('kind','tool')!='tool' or event.get('tool') not in ('run_sql','run_metric'):continue
        output=event['output']
        try:
            value=json.loads(output)
            if isinstance(value,dict):
                if event['tool']=='run_metric' and 'result' in value:
                    output=json.dumps({k:v for k,v in value.items() if k not in ('sql','metric')},ensure_ascii=False,separators=(',',':'))
        except (ValueError,TypeError):pass
        observations.append({'tool':event['tool'],'output':output[:350]})
    return {'question':req['question'],'own_answer':req.get('answer'),'correct':bool(req['correct']),
            'own_sql':sql[:1800],'own_observations':observations[-3:]}

def audit_journal(path,records):
    pending={};history=[];snapshot=None;counts=Counter();task_windows=[];active=None;index=0
    for event in lines(path):
        if event['event']=='request':
            assert event['index'] not in pending
            pending[event['index']]=event
            continue
        request_event=pending.pop(event['index']);req=request_event['request'];response=event['response']
        assert 'error' not in response,(path.name,event['index'],response)
        op=req['op'];counts[op]+=1
        if op=='begin':
            assert active is None
            assert response['common_feedback']==history
            block=response['system_prompt'].split('Environment feedback from your own earlier tasks (binary correctness; no reference answers):\n',1)[1].split('\n',1)[0]
            assert json.loads(block)==history
            assert req['question']==records[index]['question']
            active=request_event['utc']
        elif op=='end':
            assert active is not None and req['question']==records[index]['question']
            assert bool(req['correct'])==(records[index]['outcome']=='correct')
            history=(history+[feedback_item(req)])[-3:]
            task_windows.append({'start':active,'end':event['utc'],'phase':records[index]['phase'],'task':records[index]['task']})
            active=None;index+=1
        elif op=='checkpoint':
            assert snapshot is None;snapshot=copy.deepcopy(history)
        elif op=='restore':
            assert snapshot is not None;history=copy.deepcopy(snapshot)
        else:assert op=='close'
    assert not pending and active is None and index==len(records)
    assert counts['begin']==counts['end']==len(records) and counts['checkpoint']==1 and counts['restore']==11
    return dict(counts),task_windows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--results',type=Path,required=True);args=parser.parse_args()
    root=args.results;cfg=read(HERE/'protocol.json');state=read(root/'execution-state.json')
    assert state['status']=='complete' and state['complete_repeats']==[1] and state['implementation_revision']==3
    decision=read(root/'selection-decision.json');m=decision['selected_extra_count']
    assert m==state['selected_extra_count'] and 0<=m<=11 and not decision['uses_accuracy']
    eligible=[c['extra_count'] for c in decision['candidates'] if c['fits']]
    assert m==max(eligible)
    manifest=read(root/'frozen-source-manifest.json')
    assert manifest['exp/2026-10-31-diverse-scenarios/protocol.json']==sha(HERE/'protocol.json')
    budget=read(root/'budget/budget-state.json');usage=lines(root/'budget/api-usage.jsonl')
    close=read(root/'financial-close.json')
    assert (root/'budget/STOP').exists() and budget['reserved_cny']<1e-8
    assert len(usage)==budget['calls']==close['requests'] and budget['errors']==0
    assert abs(budget['prior_cost_cny']+sum(r['ceiling_cny'] for r in usage)-budget['ceiling_cny'])<1e-7
    assert abs(close['cumulative_usage_upper_cny']-budget['ceiling_cny'])<1e-8
    assert max(close['account_decrease_cny'],budget['ceiling_cny'])<=20+1e-8
    assert close['cumulative_requests']==cfg['prior_cumulative_requests']+len(usage)
    assert read(root/'database-cleanup-check.json')['remaining_study_databases']==0
    assert len(state['cells'])==8 and all(c['completed'] and c['eligible_for_final_comparison'] for c in state['cells'])
    profiles=Counter();keys={c['key'] for c in state['cells']}
    for event in lines(root/'budget/api-transcripts.jsonl'):
        assert event['arm'] in keys
        q=event['request'];assert q['model']==cfg['model'] and 0<q['max_tokens']<=cfg['max_output_tokens']
        if q.get('tools'):
            system='\n'.join(str(x.get('content','')) for x in q['messages'] if x['role']=='system')
            assert 'Environment feedback from your own earlier tasks' in system
        else:
            arm=next((x for x in ['gmemory','awm'] if event['arm'].endswith('-'+x)),None)
            if arm:
                assert q['thinking']=={'type':'disabled'} and q['max_tokens']==(512 if arm=='gmemory' else 2048)
                profiles[arm]+=1
    assert profiles['awm'] and profiles['gmemory']
    data={'study':cfg['study'],'study_status':'complete','implementation_revision':3,'complete_repeats':[1],
          'protocol_sha256':sha(HERE/'protocol.json'),'selected_extra_count':m,'groups':PHASES,'datasets':{},
          'aggregation':'Equal weight per setting; all selected questions in each setting. One paired run, no confidence interval or significance claim.',
          'cost':{'authorization_cny':20,'upper_cny':budget['ceiling_cny'],
                  'priced_usage_cny':cfg['prior_priced_usage_cny']+sum(priced(r) for r in usage),
                  'prior_usage_floor_cny':budget['prior_cost_cny'],'incremental_usage_cny':sum(priced(r) for r in usage),
                  'requests':len(usage),'cumulative_requests':close['cumulative_requests'],
                  'account_decrease_observed_cny':close['account_decrease_cny'],'http_errors':budget['errors'],
                  'models':budget['models'],'includes':'All old/new requests including ACE extra questions outside the common bank'},
          'feedback_policy':cfg['feedback'],'repairs':cfg['repairs'],'verified_memory_profiles':dict(profiles)}
    audit={'status':'passed','matched_reference_hashes':{},'cells':[]};macros=[];scored_count=0;raw_count=0;learning_count=0
    md=['# Fig. 6: diverse question comparison','',f'Fixed five-form bank; all eleven changes; one complete paired run. Cost-only gate selected M={m}.','',
        '| Dataset | Method | Held out | Non-breaking | Covered breaks | All settings |',
        '|---|---|---:|---:|---:|---:|']
    for ds,prefix in [('synthetic','PubSynth'),('tpch','PubTpch')]:
        bank=read(HERE/f'question-banks/{ds}-m{m}/question-bank.json');identities={(r['phase'],r['task']) for r in bank}
        data['datasets'][ds]={'arms':{},'unique_scored_questions':len({r['question'] for r in bank if r['phase']!='learn'}),
                              'scored_forms':dict(Counter(r['ask']['kind'] for r in bank if r['phase']!='learn'))}
        for arm in ARMS:
            cell,=[c for c in state['cells'] if c['dataset']==ds and c['arm']==arm]
            directory=root/'cells'/cell['key'];report_path,=directory.glob('metric-*/report.json')
            assert sha(report_path)==cell['report_sha256']
            report=read(report_path);assert report['database_cleaned_up'] and len(report['cells'])==1
            assert report['cells'][0]['mode']==cfg['modes'][arm]
            assert report['options']['metrics']==cfg['metrics'] and report['options']['holdout_agents']==['A'] and report['options']['concurrency']==1
            raw=report['cells'][0]['records'];assert len(raw)==(34 if arm=='ace' else 23+m)
            records=[r for r in raw if (r['phase'],r['task']) in identities]
            assert [{k:r[k] for k in ('phase','task','metric','ask','question')} for r in records]==bank
            refs=[{k:r[k] for k in ('phase','task','metric','agent','ask','question','gold')} for r in records]
            digest=hashlib.sha256(json.dumps(refs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            assert audit['matched_reference_hashes'].setdefault(ds,digest)==digest
            operations,windows=audit_journal(root/'memory'/cell['key']/'memory-events.jsonl',raw)
            audit['cells'].append({'cell':cell['key'],'raw_tasks':len(raw),'selected_tasks':len(records),
                                   'operations':operations,'journal_sha256':sha(root/'memory'/cell['key']/'memory-events.jsonl')})
            phases={}
            for phase in ['learn',*PHASES['all']]:
                rs=[r for r in records if r['phase']==phase]
                assert rs and len({r['task'] for r in rs})==len(rs)
                outcomes=Counter(r['outcome'] for r in rs);assert set(outcomes)<=set(['correct','wrong','error','clarify'])
                phases[phase]={'correct':outcomes['correct'],'n':len(rs),'outcomes':dict(outcomes)}
            tagged=[r for r in usage if r['arm']==cell['key'] and cell['started_utc']<=r['utc']<=cell['finished_utc']]
            assert tagged and all(r['status']==200 and r['model']==cfg['required_reported_model'] for r in tagged)
            selected_usage=[];excluded_usage=[];preparation_usage=[]
            for request in tagged:
                window=next((w for w in windows if w['start']<=request['utc']<=w['end']),None)
                if window is None:preparation_usage.append(request)
                elif (window['phase'],window['task']) in identities:selected_usage.append(request)
                else:excluded_usage.append(request)
            run={'repeat':1,'phases':phases,'requests':len(tagged),'raw_tasks':len(raw),'selected_tasks':len(records),
                 'priced_usage_cny':sum(priced(r) for r in tagged),'cell_seconds':report['cells'][0]['seconds'],
                 'usage_breakdown':{'selected_task_requests':len(selected_usage),'extra_task_requests':len(excluded_usage),
                                    'outside_task_requests':len(preparation_usage),'extra_task_cost_cny':sum(priced(r) for r in excluded_usage)}}
            groups={}
            for group,ps in PHASES.items():
                value=100*sum(phases[p]['correct']/phases[p]['n'] for p in ps)/len(ps)
                groups[group]={'accuracy_pct':value,'run_values_pct':[value],'range_pct':[value,value]}
                macros.append(f'\\newcommand{{\\{prefix}{NAMES[arm].replace("-", "")}{group.capitalize()}}}{{{value:.1f}}}')
            data['datasets'][ds]['arms'][arm]={'runs':[run],'groups':groups}
            md.append('| '+' | '.join([ds,NAMES[arm]]+[f'{groups[g]["accuracy_pct"]:.1f}%' for g in PHASES])+' |')
            raw_count+=len(raw);learning_count+=phases['learn']['n'];scored_count+=len(records)-phases['learn']['n']
    data.update(scored_tasks=scored_count,learning_tasks=learning_count,raw_tasks=raw_count,
                extra_questions_charged_not_scored=raw_count-learning_count-scored_count)
    if state.get('development'):data['development']=state['development']
    macros+=['\\newcommand{\\PubScenarioRepeats}{1}',f'\\newcommand{{\\PubScenarioScored}}{{{scored_count}}}']
    for ds in cfg['datasets']:
        md+=['',f'## {ds}: every setting','','| Setting | ACE | AWM | G-Memory | MAVRA |','|---|---:|---:|---:|---:|']
        for phase in PHASES['all']:
            values=[data['datasets'][ds]['arms'][arm]['runs'][0]['phases'][phase] for arm in ARMS]
            md.append('| '+' | '.join([phase]+[f'{r["correct"]}/{r["n"]}' for r in values])+' |')
    md+=['','## Common question coverage','','Counts below are selected scored questions per method, including repeated questions in distinct change settings.','',
         '| Schema | Distinct questions | Single | Difference | Maximum month | Largest increase | Above-mean count |',
         '|---|---:|---:|---:|---:|---:|---:|']
    for ds in cfg['datasets']:
        coverage=data['datasets'][ds]
        md.append('| '+' | '.join([ds,str(coverage['unique_scored_questions'])]+[str(coverage['scored_forms'].get(k,0)) for k in cfg['scored_forms']])+' |')
    md+=['',f'{scored_count} selected scored tasks, {learning_count} learning tasks; {data["extra_questions_charged_not_scored"]} ACE extras remain archived and charged.',
         f'Cumulative actual debit CNY{close["account_decrease_cny"]:.2f}; conservative ceiling CNY{budget["ceiling_cny"]:.6f}; all {close["cumulative_requests"]} old/new API requests included.',
         'No scenario, question, method or failed answer was selected using accuracy. Different implementation cohorts are not pooled.']
    audit['checks']=['Same selected questions and gold values for all four methods','All raw own-result feedback matches actual planner prompt and journal',
                     'All eleven branches restore the post-heldout checkpoint','No gold SQL/value or hidden change label in the common feedback',
                     'All HTTP calls and extra questions included in cumulative spending']
    write(HERE/'study-stats.json',data);write(HERE/'feedback-comparison-check.json',audit)
    (HERE/'overleaf-numbers.tex').write_text('% Generated from the complete selected common bank by analyse.py.\n'+'\n'.join(macros)+'\n',encoding='utf-8')
    (HERE/'summary.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print('\n'.join(md[:14]))

if __name__=='__main__':main()
