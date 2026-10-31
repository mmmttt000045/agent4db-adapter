"""Retain the entire interrupted pilot before repairing non-single ask metadata."""
import hashlib,json,os,socket
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
assert ROOT.name=='agentdb-diverse-scenarios-20261031'
out=ROOT/'results/diverse-scenarios-20261031'
state=json.loads((out/'execution-state.json').read_text())
assert state['status']=='incomplete' and len(state['cells'])==2
assert not (out/'development').exists()
for port in (19430,19431):
    with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',port))!=0
budget=json.loads((out/'budget/budget-state.json').read_text())
assert budget['calls']==74 and budget['reserved_cny']<1e-8 and budget['errors']==0
assert all("KeyError: 'period'" in (out/'cells'/cell['key']/'console.log').read_text() for cell in state['cells'])
development=out/'development';development.mkdir()
for name in ('cells','memory','execution-state.json','frozen-source-manifest.json','coordinator.log','coordinator.pid',
             'budget-proxy.log','memory-service.log','budget-proxy.pid','memory-service.pid'):
    path=out/name
    if path.exists():
        assert path.resolve().is_relative_to(ROOT.resolve())
        path.rename(development/name)
record={'utc':datetime.now(timezone.utc).isoformat(),'excluded_from_accuracy':'Both interrupted cells, irrespective of answer outcomes',
        'cause':'SQL adapter assumed Ask::Single period metadata; first Ask::Diff update raised KeyError before memory update',
        'requests':budget['calls'],'incremental_upper_cny':budget['ceiling_cny']-budget['prior_cost_cny'],
        'cumulative_upper_cny':budget['ceiling_cny'],'ledger_sha256':hashlib.sha256((out/'budget/api-usage.jsonl').read_bytes()).hexdigest(),
        'budget_ledger_preserved':True,'protocol_and_native_binary_unchanged':True}
(development/'development-record.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
