"""Merge several metric-bench runs (e.g. one process per model and repeat) into one Markdown summary.

Usage: python tools/aggregate-metric.py results/metric-A results/metric-B ... > summary.md
Runs are grouped by agent model; cells with the same mode are pooled across runs and repeats.
Counts only; no significance claims.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

runs = []
for d in sys.argv[1:]:
    p = Path(d) / 'report.json'
    if not p.exists():
        print(f'<!-- skipped {d}: no report.json -->')
        continue
    runs.append(json.loads(p.read_text(encoding='utf-8')))
if not runs:
    raise SystemExit('no report.json found')

def table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |', '|' + '|'.join('---' for _ in headers) + '|']
    out += ['| ' + ' | '.join(str(x) for x in r) + ' |' for r in rows]
    return '\n'.join(out)

by_model = defaultdict(list)
for r in runs:
    by_model[r['providers']['agent']].append(r)

print('# 指标经验评测汇总\n')
print('按模型合并多次运行；同一组的各轮、各进程合计。描述性结果，不作显著性声明。\n')
for model, rs in by_model.items():
    cells = [c for r in rs for c in r['cells']]
    recs = [x for c in cells for x in c['records']]
    modes = list(dict.fromkeys(m for r in rs for m in r['options']['modes']))
    changes = list(dict.fromkeys((c['name'], c['label'], c['class']) for r in rs for c in r.get('changes', [])))
    repeats = Counter(c['mode'] for c in cells)
    print(f'## {model}\n')
    print(f'运行 {len(rs)} 次，每组 {dict(repeats)} 个 cell。数据：`{rs[0]["dataset"]}`。'
          f'推理强度：`{rs[0]["providers"]["agent_config"].get("reasoning_effort")}`。\n')
    outcomes = Counter(x['outcome'] for x in recs)
    print(f'全部任务结果：{dict(outcomes)}\n')

    rows = []
    for m in modes:
        xs = [x for x in recs if x['mode'] == m and x['phase'] == 'holdout']
        if xs:
            n = Counter(x['outcome'] for x in xs)
            rows.append([m, len(xs), n['correct'], n['wrong'], n['clarify'], n['error'],
                         round(sum(x['run']['input_tokens'] for x in xs) / len(xs)),
                         round(sum(x['run']['steps'] for x in xs) / len(xs), 1)])
    print('### 留出题\n')
    print(table(['组', '题数', '正确', '错误', '澄清', '出错', '平均输入 token', '平均轮数'], rows) + '\n')

    ans, stale, maint = [], [], []
    for name, label, cls in changes:
        a, s, mt = [label, cls], [label, cls], [label, cls]
        for m in modes:
            xs = [x for x in recs if x['mode'] == m and x['phase'] == name]
            if not xs:
                a.append('—'); s.append('—'); mt.append('—')
                continue
            n = Counter(x['outcome'] for x in xs)
            cell = f"{n['correct']}/{len(xs)}"
            if n['clarify']:
                cell += f" 澄{n['clarify']}"
            if n['error']:
                cell += f" 败{n['error']}"
            a.append(cell)
            s.append(sum(1 for x in xs if x['metric_use']['bad_executed'] > 0))
            evs = [e for c in cells if c['mode'] == m for e in c['events'].get(name, []) if e.get('event') == 'maintenance']
            o = Counter(e['outcome'] for e in evs)
            mt.append('/'.join(str(o[k]) for k in ('refreshed', 'repaired', 'revoked', 'revoked_on_write')) if evs else '0')
        ans.append(a); stale.append(s); maint.append(mt)
    headers = ['场景', '条件'] + modes
    print('### 数据变化场景：答案（正确/题数）\n')
    print(table(headers, ans) + '\n')
    print('### 过期执行（执行了引用不正确口径的 SQL 的任务数）\n')
    print(table(headers, stale) + '\n')
    print('### 维护结果（刷新/撤销后修复/撤销未恢复/逐写入撤销）\n')
    print(table(headers, maint) + '\n')
