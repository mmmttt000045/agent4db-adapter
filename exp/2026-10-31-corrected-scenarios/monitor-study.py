"""Print public progress only; never expose keys or either account balance."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'results/corrected-scenarios-20261031'
s=json.loads((p/'execution-state.json').read_text(encoding='utf-8'))
b=json.loads((p/'budget/budget-state.json').read_text(encoding='utf-8'))
active=[]
for directory in sorted((p/'cells').iterdir()):
    if (directory/'completion.json').exists():continue
    journals=list(directory.glob('metric-*/task-journal.jsonl'))
    item={'cell':directory.name}
    if journals and journals[0].stat().st_size:
        lines=journals[0].read_text(encoding='utf-8').splitlines()
        row=json.loads(lines[-1])
        item.update(tasks=len(lines),phase=row['phase'],task=row['task'],outcome=row['outcome'])
    active.append(item)
print(json.dumps({'status':s['status'],'complete_repeats':s['complete_repeats'],
    'complete_cells':sum(c['completed'] and c.get('eligible_for_final_comparison',False) for c in s['cells']),
    'superseded_cells':sum(c['completed'] and not c.get('eligible_for_final_comparison',False) for c in s['cells']),
    'failed_attempts':sum(not c['completed'] for c in s['cells']),
    'new_requests':b['calls'],'cumulative_upper_cny':round(b['ceiling_cny'],5),
    'reserved_cny':round(b['reserved_cny'],5),'active':active}))
