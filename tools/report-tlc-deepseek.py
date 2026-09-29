"""Summarize every predeclared cell, including errors and model overhead."""
import json
import hashlib
from pathlib import Path
import statistics as st

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/tlc-deepseek'

def interval(xs):
    if not xs: return None
    m = st.mean(xs)
    h = 3.182446 * st.stdev(xs) / len(xs)**0.5 if len(xs) == 4 else None
    return dict(mean=m, ci95=[m-h,m+h] if h is not None else None, rounds=len(xs))

def main():
    cells = json.loads((OUT/'cells.json').read_text(encoding='utf-8'))
    rows, checks, calls, errors, policies = [], [], [], [], []
    for c in cells:
        d = OUT/c['directory']
        if c['exit_code']:
            errors.append(dict(cell=c['directory'], exit_code=c['exit_code']))
            continue
        for journal in d.rglob('optimizer.jsonl'):
            for line in journal.read_text(encoding='utf-8').splitlines():
                e = json.loads(line)
                if e['event'] == 'model_response': calls.append(dict(cell=c['directory'], journal=str(journal.relative_to(d)), **e['data']))
        if c['study'] == 'checks':
            r = json.loads((d/'check-study.json').read_text(encoding='utf-8'))
            for x in r['experiments']:
                events = x['events']
                for subset, ev in [('all',events),('deployment', [e for e in events if e['index']>=16])]:
                    candidate = sum(p['db_ms'] for e in ev for p in e['paired_execution'] if p['candidate'])
                    baseline = sum(p['db_ms'] for e in ev for p in e['paired_execution'] if not p['candidate'])
                    checks.append(dict(cell=c['directory'], round=c['round'], mode=c['mode'], probe=x['key_probe_required'], subset=subset,
                        trials=len(ev), candidate_ms=candidate, baseline_ms=baseline, saving_pct=100*(1-candidate/baseline),
                        adopted=sum(e['adopted_before_execution'] for e in ev),
                        matches=sum(e['paired_execution'][0]['pass']==e['paired_execution'][1]['pass'] for e in ev),
                        both_rejected=sum(all(not p['pass'] for p in e['paired_execution']) for e in ev),
                        observation_ms=sum(e['full_observation_db_ms'] for e in ev)))
                for dec in x['decisions']:
                    if 'error' in dec: errors.append(dict(cell=c['directory'], probe=x['key_probe_required'], **dec))
                    if 'proposal' in dec:
                        p=dec['proposal']; policies.append(dict(cell=c['directory'],probe=x['key_probe_required'],policy=p['policy'],wall_ms=p['proposal_wall_ms']))
        else:
            r=json.loads((d/'report.json').read_text(encoding='utf-8'))
            rows.append(dict(study=c['study'],round=c['round'],mode=c['mode'],wall_seconds=r['wall_seconds'],
                db_ms=r['total_database']['db_ms'],tasks=sum(p['tasks'] for p in r['phases']),correct=sum(p['correct'] for p in r['phases']),
                applies=sum('apply' in p and 'Ok' in p['apply'] for p in r['decisions']),
                reordered=sum(t['detail'].get('event')=='planned_order' and t['detail'].get('checks')!=['KeyUnique','RowConservation','SampleFanout'] for trace in r['traces'] for t in trace),
                proposals=sum('proposal' in p for p in r['decisions'])))
            for dec in r['decisions']:
                if 'error' in dec: errors.append(dict(cell=c['directory'],**dec))
    comparisons=[]
    for study in ['cache-on','cache-off']:
        for baseline in ['B','D','M']:
            for metric in ['db_ms','wall_seconds']:
                vals=[]
                for n in range(4):
                    lookup={r['mode']:r[metric] for r in rows if r['study']==study and r['round']==n}
                    if 'L' in lookup and baseline in lookup: vals.append(100*(1-lookup['L']/lookup[baseline]))
                comparisons.append(dict(study=study, baseline=baseline, metric=metric, saving_pct=interval(vals)))
    sums=[]
    for mode in 'BDML':
        for probe in [True,False]:
            for subset in ['all','deployment']:
                group=[r for r in checks if r['mode']==mode and r['probe']==probe and r['subset']==subset]
                if group:
                    sums.append(dict(mode=mode,probe=probe,subset=subset,saving_pct=interval([r['saving_pct'] for r in group]),
                        **{k:sum(r[k] for r in group) for k in ['trials','adopted','matches','both_rejected','candidate_ms','baseline_ms','observation_ms']}))
    usage=dict(successful_responses=len(calls), input_tokens=sum(c['usage']['input_tokens'] for c in calls),
        output_tokens=sum(c['usage']['output_tokens'] for c in calls),wall_seconds=sum(c['wall_ms'] for c in calls)/1000,
        reasoning_tokens=sum(c['usage']['provider_usage'].get('completion_tokens_details',{}).get('reasoning_tokens',0) for c in calls))
    data=dict(completed_cells=len(cells),planned_cells=48,main=rows,comparisons=comparisons,check_summary=sums,
              checks=checks,model_usage=usage,model_calls=calls,policies=policies,errors=errors)
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    data['provenance_verified']=(hashlib.sha256((OUT/'experiment.exe').read_bytes()).hexdigest()==manifest['binary_sha256']
        and all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest['sources'].items()))
    assert data['provenance_verified'], 'Experiment binary/source provenance mismatch'
    (ROOT/'docs/deepseek-real-validation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(completed_cells=len(cells),usage=usage,errors=errors),ensure_ascii=False,indent=2))
    if len(cells) != 48: return
    def ci(x):
        return f'{x["mean"]:.2f}% [{x["ci95"][0]:.2f}, {x["ci95"][1]:.2f}]' if x and x['ci95'] else '未完成'
    lines=['# DeepSeek 真实数据对照实验（2026-09-29）', '',
        '模型：DeepSeek 官方 `deepseek-flash`（V4.1 Flash），thinking enabled，reasoning_effort=max。固定规则 B、内置统计反馈 D、Mock M、真实模型 L 使用同一 release 可执行文件。', '',
        '**结论：本次真实模型没有表现出优于统计反馈或 Mock 的增量收益。** 无需补查的失败候选上，模型能够通过独立验证并显著减少检查执行耗时，但便宜的统计策略也得到相同收益；正常业务没有实际换序，同步模型提案增加了全程等待。该结论只覆盖本次数据、负载及三检查排列的策略空间。', '',
        '## 设计与边界', '',
        '- 数据：NYC TLC 2024 年 1、2 月全部 5,972,150 条行程，265 个区域，数据库约 1.027 GiB；来源和 SHA256 在原始 manifest 中。没有复制业务行扩容。',
        '- 正常业务：24 个脚本 agent，320 个参数化任务（10 种 SQL 结构），4 轮轮换模式顺序，结果缓存开/关各一套。不是 24 个大模型 agent，也不是 320 种独立 SQL 结构。',
        '- 正常业务 M/L 在 D 的内置反馈之上增加管理提案，在一月结束后提案、二月结束后校验；没有应用后的第三阶段，因此只能评估提案开销和验证门槛，不能据此宣称已部署策略带来端到端提升。',
        '- 失败检查专项：每轮两个受控的补查状态，每状态 48 个日期候选；前 8 个训练、接着 8 个独立验证，最后 32 个观察部署效果。D 使用已有的 3 样本/8 新候选规则，可能早于 M/L 启用，因此同时报告共同的最后 32 个候选。',
        '- 每个候选以交替顺序真实执行当前策略和固定策略，比较判定及耗时；随后执行全部检查采集证据，额外成本单列。模型仅获得聚合性能统计，不能生成 SQL 或关闭检查。',
        '- 同一数据库顺序运行，固定每轮工作负载种子，不清空 OS/PG 缓存。四轮 t 区间是描述性区间，不代表生产分布或严格随机独立样本；没有因结果不好重跑。', '',
        '## 正常业务结果', '',
        '| 缓存 | 组 | 正确任务 / 总任务 | 平均 DB 累计时间 s | 平均全程墙钟 s | 策略应用数 |',
        '|---|---|---:|---:|---:|---:|']
    for study in ['cache-on','cache-off']:
        for mode in 'BDML':
            g=[r for r in rows if r['study']==study and r['mode']==mode]
            if g: lines.append(f'| {study} | {mode} | {sum(r["correct"] for r in g)} / {sum(r["tasks"] for r in g)} | {st.mean(r["db_ms"] for r in g)/1000:.3f} | {st.mean(r["wall_seconds"] for r in g):.3f} | {sum(r["applies"] for r in g)} |')
    lines += ['', f'正常业务实际换序轨迹共 {sum(r["reordered"] for r in rows)} 次。DB 时间是并发 SQL 耗时之和，不能当作用户等待时间。全程墙钟包括同步模型提案；后台异步部署会有不同的延迟表现。', '',
        '| 缓存 | L 对照组 | DB 成本减少（四轮均值及描述性 95% 区间） | 全程墙钟减少 |', '|---|---|---:|---:|']
    for study in ['cache-on','cache-off']:
        for base in 'BDM':
            pair=[c for c in comparisons if c['study']==study and c['baseline']==base]
            lines.append(f'| {study} | {base} | {ci(pair[0]["saving_pct"])} | {ci(pair[1]["saving_pct"])} |')
    lines += ['', '正值表示节省，负值表示更慢。若策略没有实际改变，DB 时间差异不能归因为模型优化。', '',
        '## 失败检查专项', '',
        '| 需补查键 | 组 | 全 48 候选的检查成本节省 | 最后 32 候选的检查成本节省 | 实际采用次数 / 全部候选 |', '|---|---|---:|---:|---:|']
    for probe in [True,False]:
        for mode in 'BDML':
            a=next(r for r in sums if r['probe']==probe and r['mode']==mode and r['subset']=='all')
            b=next(r for r in sums if r['probe']==probe and r['mode']==mode and r['subset']=='deployment')
            lines.append(f'| {"是" if probe else "否"} | {mode} | {ci(a["saving_pct"])} | {ci(b["saving_pct"])} | {a["adopted"]} / {a["trials"]} |')
    lines += ['', '上述节省仅为检查执行的毛收益，不包含完整采样、模型费用或网络等待。固定组 B 两次执行相同顺序，非零差值反映测量噪声。', '',
        '| 需补查键 | L 候选/固定检查累计 s | L 完整观察成本 s | 判定一致 / 候选数 |', '|---|---:|---:|---:|']
    for probe in [True,False]:
        a=next(r for r in sums if r['probe']==probe and r['mode']=='L' and r['subset']=='all')
        lines.append(f'| {"是" if probe else "否"} | {a["candidate_ms"]/1000:.3f} / {a["baseline_ms"]/1000:.3f} | {a["observation_ms"]/1000:.3f} | {a["matches"]} / {a["trials"]} |')
    fast=next(r for r in sums if not r['probe'] and r['mode']=='L' and r['subset']=='all')
    fast_wait=sum(c['wall_ms'] for c in calls if c['cell'].startswith('checks-') and 'manager-false' in c['journal'])/1000
    lines += ['', f'无需补查场景：L 全部四轮毛节省 {(fast["baseline_ms"]-fast["candidate_ms"])/1000:.3f} 秒，但完整观察额外花费 {fast["observation_ms"]/1000:.3f} 秒，模型提案另等待 {fast_wait:.3f} 秒。该专项为单工作线程，因此这些时间可以比较；即便不计模型费用，当前实验规模也没有抵消证据采集成本。配对固定策略的对照执行另属实验测量开销，未算成生产所需成本。']
    lines += ['', '这些候选是人为选择的真实数据错误关联，不是自然生产流量；判定一致只证明这组候选的一致性，不能证明任意 SQL 的语义正确性。', '',
        '## 模型用量与可解释性', '',
        f'- 成功 API 响应：{usage["successful_responses"]}；输入 {usage["input_tokens"]:,} tokens，输出 {usage["output_tokens"]:,} tokens，其中推理 {usage["reasoning_tokens"]:,}；成功响应累计等待 {usage["wall_seconds"]:.3f} 秒。推理 tokens 是输出的子集，不重复相加。',
        f'- 进程/提案错误记录：{len(errors)}。费用未按未经核实的单价换算；超时和重试可能产生未返回的用量，以上只统计收到的 usage。',
        '- 模型的理由、输入统计、提案顺序、验证结果和应用/拒绝轨迹均保存在本地 JSON；未保存或公开模型内部思维链。',
        '- 模型能看到三种检查的总体失败率和成本，却没有每个候选的补查状态。因此便宜检查优先可能在必须补查键的路径增加成本，独立验证门槛是必要环节。',
        '- 策略空间只有三种检查的六种排列；简单统计规则已能发现便宜的失败检查，真实模型未必提供额外价值。', '',
        '## 复现与证据', '',
        '在项目根目录配置被忽略的 `.env` 与 `results/tlc-real-data/connection.txt` 后执行：', '',
        '```powershell', 'cargo build --locked --release', 'python tools/run-tlc-deepseek.py', 'python tools/report-tlc-deepseek.py', '```', '',
        '运行器拒绝覆盖已有 `results/tlc-deepseek`，复跑前应保留并重命名该目录。清单保存源码及可执行文件哈希；所有 48 个单元的日志、逐任务结果、专项配对测量及优化审计保留在该目录。', '',
        '机器可读汇总：[deepseek-real-validation.json](deepseek-real-validation.json)。先前无真实模型报告：[real-data-validation.md](real-data-validation.md)。', '',
        '![检查毛收益和正常业务全程等待对比](figures/deepseek-validation.png)']
    (ROOT/'docs/deepseek-real-validation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__': main()
