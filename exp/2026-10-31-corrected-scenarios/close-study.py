"""Close a completed comparison and expose spending deltas, never balances."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
import requests
import psycopg

p=argparse.ArgumentParser()
p.add_argument('--key-file',required=True)
p.add_argument('--database-env',required=True)
a=p.parse_args()
root=Path(__file__).resolve().parents[2]
out=root/'results/corrected-scenarios-20261031'
s=json.loads((out/'execution-state.json').read_text())
b=json.loads((out/'budget/budget-state.json').read_text())
assert s['status']=='complete' and s['complete_repeats']
assert abs(b['reserved_cny'])<1e-8 and b['ceiling_cny']<=20+1e-9
(out/'budget/STOP').touch()
http=requests.Session();http.trust_env=False
key=Path(a.key_file).read_text().strip()
reply=http.get('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+key},timeout=20)
reply.raise_for_status()
balance=sum(float(x['total_balance']) for x in reply.json()['balance_infos'] if x['currency']=='CNY')
spent=max(0.,b['initial_balance_cny']-balance)
assert spent<=20+1e-8
public={'utc':datetime.now(timezone.utc).isoformat(),'account_decrease_cny':spent,
    'cumulative_usage_upper_cny':b['ceiling_cny'],'prior_usage_floor_cny':b['prior_cost_cny'],
    'incremental_usage_cny':b['ceiling_cny']-b['prior_cost_cny'],
    'requests':b['calls'],'cumulative_requests':3378+b['calls'],
    'spending_authorization_cny':20,'status':'closed_no_more_model_calls'}
(out/'financial-close.json').write_text(json.dumps(public,indent=2)+'\n')
url=None
for line in Path(a.database_env).read_text().splitlines():
    if line.strip().startswith('AGENTDB_URL='):url=line.split('=',1)[1].strip().strip('"').strip("'")
assert url
prefix='agentdb_fig6fix_'
with psycopg.connect(url,autocommit=True) as db:
    rows=db.execute('select datname from pg_database where left(datname,%s)=%s',(len(prefix),prefix)).fetchall()
assert not rows,'Study databases remain; inspect the exact owned identifiers before cleanup'
(out/'database-cleanup-check.json').write_text(json.dumps({'checked_utc':datetime.now(timezone.utc).isoformat(),'remaining_study_databases':0})+'\n')
print(json.dumps(public))
