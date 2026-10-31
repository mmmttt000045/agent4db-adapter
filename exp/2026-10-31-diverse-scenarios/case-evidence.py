"""Extract trace-backed usage and failures without changing the scoring bank."""
import argparse,json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);args=p.parse_args()
    state=read(args.results/'execution-state.json');assert state['status']=='complete'
    m=state['selected_extra_count'];result={'study':'diverse-scenarios-20261031','cells':{}}
    for cell in state['cells']:
        folder=args.results/'cells'/cell['key'];report_path,=folder.glob('metric-*/report.json');report=read(report_path)['cells'][0]
        bank=read(HERE/f'question-banks/{cell["dataset"]}-m{m}/question-bank.json')
        ids={(r['phase'],r['task']) for r in bank}
        events=[json.loads(s) for s in (args.results/'memory'/cell['key']/'memory-events.jsonl').read_text(encoding='utf-8').splitlines()]
        ends=[e['request'] for e in events if e['event']=='request' and e['request']['op']=='end']
        assert len(ends)==len(report['records'])
        tools=Counter();execution=Counter();forms=Counter();failures=[]
        for record,end in zip(report['records'],ends):
            assert record['question']==end['question'] and record['task']==end['task'] and record['phase']==end['phase']
            if (record['phase'],record['task']) not in ids:continue
            observations=[]
            for event in end['transcript']:
                if event.get('kind','tool')!='tool':continue
                tools[event['tool']]+=1
                if event['tool'] not in ('run_sql','run_metric'):continue
                try:output=json.loads(event['output'])
                except (ValueError,TypeError):output={'raw':event['output']}
                if event['tool']=='run_metric':
                    execution['attempts']+=1
                    if event.get('status')!='error' and isinstance(output,dict) and 'ref' in output and 'result' in output:
                        execution['executed']+=1;forms[record['ask']['kind']]+=1
                    else:execution['denied_or_error']+=1
                observations.append({'tool':event['tool'],'status':event.get('status'),'input':event.get('input'),
                                     'output':output})
            if record['phase']!='learn' and record['outcome']!='correct':
                failures.append({'phase':record['phase'],'task':record['task'],'metric':record['metric'],'ask':record['ask'],
                                 'question':record['question'],'outcome':record['outcome'],'answer':record['answer'],
                                 'gold':record['gold'],'error':record.get('error'),'own_final_sql':end.get('sql'),
                                 'executions':observations})
        publications=[{'task':entry.get('task'),'event':(entry.get('submit') or {}).get('event'),
                       'failed_gate':(entry.get('submit') or {}).get('failed_gate'),'reason':(entry.get('submit') or {}).get('reason')}
                      for entry in report.get('learning',[])]
        result['cells'][cell['key']]={'tools':dict(tools),'run_metric':dict(execution),'run_metric_forms':dict(forms),
                                    'learning_publications':publications,'failures':failures,
                                    'raw_report':str(report_path.relative_to(args.results))}
    (HERE/'case-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:{'failures':len(v['failures']),'run_metric':v['run_metric'],'forms':v['run_metric_forms']} for key,v in result['cells'].items()}))

if __name__=='__main__':main()
