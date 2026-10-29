#!/usr/bin/env python3
"""Analyze all predeclared cells, retaining failures and source setup costs."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE=ROOT/'results/mechanism-pilot-20261029'
OUT=ROOT/'output/mechanism-pilot-20261029'
OUT.mkdir(parents=True,exist_ok=True)
cfg=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def hashfile(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def exact(sql):return (sql or '').replace('\r\n','\n').strip().rstrip(';').rstrip()

source=read(BASE/'source/source.json')
original_source=ROOT/cfg['source']['file']
lineage={'checked':False}
if original_source.exists():
    assert hashfile(original_source)==source['provenance']['source_sha256']
    old=read(original_source)
    calls={c['id']:c['function']['name'] for m in old['messages'] if m['role']=='assistant' for c in m.get('tool_calls',[])}
    responses=[]
    for m in old['messages']:
        tool=calls.get(m.get('tool_call_id'))
        if m['role']=='tool' and tool in ('find_program','find_features','compose_features'):
            v=json.loads(m['content']);responses.append({'tool':tool,'features_returned':len(v.get('features',[])),
                'program_returned':bool(v.get('program')),'sql_returned':bool(v.get('sql'))})
    lineage={'checked':True,'source_sha256':hashfile(original_source),'memory_responses':responses,
             'empty_source_memory':all(not (x['features_returned'] or x['program_returned'] or x['sql_returned']) for x in responses)}
setup=source['new_learning']
historical=source['provenance']['historical_source_exploration_tokens']
extraction=setup['input_tokens']+setup['output_tokens']
attempt=read(BASE/'pilot-state.json')
repair=read(BASE/'repair-v1/state.json') if (BASE/'repair-v1/state.json').exists() else {}
rows=[]
for target in cfg['targets']:
    for arm in cfg['arms']:
        name=target['name']+'-'+arm
        folder=BASE/name if arm=='none' else BASE/'repair-v1'/name
        file=folder/'sessions'/f"{target['task'].replace('-','_')}-k{target['cutoff']}.json"
        original=next(x for x in attempt['cells'] if x['name']==name)
        r={'name':name,'arm':arm,'target':target,'status':'pending','original_attempt_status':original['status']}
        if not file.exists():rows.append(r);continue
        d=read(file)
        if 'totals' not in d:rows.append(r);continue
        totals=d['totals'];clean=d.get('audit',{}).get('result')=='clean' if d.get('audit') else False
        valid=bool(clean and d.get('final_sql') and d.get('best_val') is not None)
        returned=[]
        for entry in d.get('memory_outputs',[]):
            out=entry['output']
            if entry['tool']=='retrieve_programs':
                returned.extend(('program',x['sql']) for x in out.get('programs',[]) if x.get('sql'))
            elif out.get('sql'):returned.append(('compiled',out['sql']))
        provenance=lambda sql:sorted({kind for kind,s in returned if exact(s)==exact(sql) and exact(sql)})
        allocation_source=historical/len(cfg['targets']) if arm!='none' else 0
        allocation_extract=extraction/len(cfg['targets']) if arm in ('definition','full') else 0
        r.update(status='complete',valid=valid,validation_auc=d.get('best_val'),audit=d.get('audit'),stop=d.get('stop'),
                 agent_tokens=totals['tokens'],historical_source_allocated_tokens=allocation_source,
                 new_extraction_allocated_tokens=allocation_extract,
                 amortized_tokens=totals['tokens']+allocation_source+allocation_extract,
                 agent_seconds=d.get('agent_seconds'),tools=totals['tool_calls_by_category'],
                 memory_calls=[x['name'] for x in d['tools'] if x.get('category')=='memory'],
                 exact_final_memory_matches=provenance(d.get('final_sql')),
                 validation_memory_matches=[{'tool_i':v.get('tool_i'),'memory_match':provenance(v.get('sql')),
                     'val':v.get('val'),'leak':v.get('leak'),'error':v.get('error')} for v in d.get('validations',[])],
                 source_path=str(file.relative_to(ROOT)),sha256=hashfile(file),pilot_flags=d.get('pilot'),
                 test_score=d.get('eval',{}).get('test') if d.get('eval') else None)
        assert r['test_score'] is None
        assert r['pilot_flags']['test_labels_read'] is False
        assert r['pilot_flags']['test_scored'] is False
        rows.append(r)

for r in rows:
    baseline=next(x for x in rows if x['target']==r['target'] and x['arm']=='none')
    threshold=baseline.get('validation_auc')-.01 if baseline.get('valid') else None
    r['paired_validation_threshold']=threshold
    r['qualified_on_pilot_validation']=bool(r.get('valid') and r['validation_auc']>=threshold) if threshold is not None else None

failed_tokens=0
for c in attempt['cells']:
    if c['status']!='failed':continue
    paths=list((BASE/c['name']/'sessions').glob('*.partial.json'))
    for f in paths:
        d=read(f)
        failed_tokens+=sum(x.get('input_tokens',0)+x.get('output_tokens',0) for x in d.get('llm',[]))
ledger=read(BASE/'budget-state.json')
audits={}
for target in cfg['targets']:
    f=BASE/'repair-v1'/(target['name']+'-full')/'source-target-audit.json'
    if f.exists():audits[target['name']]=read(f)
data={'phase':'development pilot; validation only; one run per cell',
      'complete':all(r['status']=='complete' for r in rows),
      'source':{'historical_exploration_tokens':historical,'new_extraction_tokens':extraction,
                'drafts':len(setup['events']),'published':sum(e['event']=='promoted' for e in setup['events']),
                'source_sha256':hashfile(BASE/'source/source.json'),'lineage_check':lineage},
      'rows':rows,'source_target_audits':audits,
      'infrastructure_repair':{'failed_cells':6,'retained_completed_controls':2,'partial_tokens':failed_tokens,
            'reason':'names set was incorrectly exposed where the harness expects a callable names(); fixed before six memory-cell reruns',
            'compiled_source':'same seven definitions; all 127 subsets generated by unchanged Rust compiler; full SQL required to match exactly',
            'hidden_sql_repair':'explicitly disabled in shared composite hook before memory cells could run'},
      'new_api_usage':{k:ledger.get(k) for k in ['calls','ceiling_cny','errors','models','pricing_policy']},
      'limits':['one source and two target settings, one repetition',
                'source program contains more features than the seven admitted definitions',
                'validation scores are development data, never test non-inferiority',
                'no paired quality claim where no-memory has no valid SQL',
                'exact SQL matching identifies unchanged adoption only; edited derivations are not automatically assigned',
                'source setup cost is allocated over only two targets; historical source tokens are not new spending',
                'infrastructure interruption and resumed cells preclude a clean timing comparison',
                'HTTP probe timeout 180s differs from frozen Rust server query timeout 300s']}
(OUT/'pilot-analysis.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'pilot-summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# 图 A 小规模预实验结果','',
       '状态：'+('八个单元均完成。' if data['complete'] else '尚未完成，pending 不能当作实验失败结果。'),'',
       '开发集验证结果，每格仅一次；没有读取或评分测试标签。跨任务对照若没有有效 SQL，其质量配对结论留空。','',
       '| 目标 | 组别 | 验证 AUC | 目标审计 | 智能体 token | 含源成本摊销 token | 原样复用来源 |',
       '| --- | --- | ---: | --- | ---: | ---: | --- |']
names={'none':'无记忆','program':'仅完整 SQL','definition':'仅定义','full':'完整 SQL + 定义'}
for r in rows:
    if r['status']!='complete':lines.append(f"| {r['target']['name']} | {names[r['arm']]} | pending | — | — | — | — |");continue
    q=f"{r['validation_auc']:.4f}" if r['validation_auc'] is not None else '无有效方案'
    adoption='/'.join(r['exact_final_memory_matches']) or '无原样匹配'
    lines.append(f"| {r['target']['name']} | {names[r['arm']]} | {q} | {'clean' if r['valid'] else '无通过结果'} | {r['agent_tokens']:,} | {r['amortized_tokens']:,.0f} | {adoption} |")
lines+=['',f"源程序历史探索 {historical:,} token；本次提炼 {extraction:,} token，{data['source']['drafts']} 条候选中 {data['source']['published']} 条获准发布。",
        '源程序成本按每个记忆组的两个目标平摊；提炼成本仅分配给定义组和组合组。不是仅报告便宜的在线调用。','',
        f"新 API 请求共 {ledger['calls']} 次，保守计价上界 {ledger['ceiling_cny']:.4f} 元（非账单金额），含接口故障期间的请求；历史源程序不重复计为本次消费。",'',
        '首轮六个记忆单元因适配接口故障中断，原始结果保留；修复后只补跑中断单元，没有重跑两个已完成的无记忆对照。',
        '原样复用只按返回 SQL 与验证/最终 SQL 的精确匹配记录；无匹配不代表没有参考或改写定义。',
        '正式实验需扩大成完整配对重复，并先解决预算内完成率、源特征内容量差异与目标审计问题。','']
(OUT/'pilot-results.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'complete':data['complete'],'cells':len(rows),'completed':sum(r['status']=='complete' for r in rows),
                  'new_spending_ceiling_cny':ledger['ceiling_cny']}))
