"""Read-only status for the owned pilot; never print credentials or balances."""
import json
import os
from pathlib import Path
import pilot as p

os.chdir(p.ROOT)
out=p.ROOT/'results/mechanism-pilot-20261029'
ledger=json.loads((out/'budget-state.json').read_text())
print(json.dumps({'budget':{k:ledger.get(k) for k in ['calls','ceiling_cny','status','errors']}}))
state=json.loads((out/'repair-v1/state.json').read_text())
for f in (out/'repair-v1'/state['current']/'sessions').glob('*.partial.json'):
    d=json.loads(f.read_text())
    print(json.dumps({'cell':state['current'],'llm_calls':len(d.get('llm',[])),
        'tools':[{k:t.get(k) for k in ['name','seconds','error']} for t in d.get('tools',[])],
        'recent_tool_errors':[m.get('content','')[:400] for m in d.get('messages',[]) if m.get('role')=='tool' and 'error' in m.get('content','')][-3:]}))
with p.h.psycopg.connect(p.h.load_env()['AGENTDB_URL'],autocommit=True) as con:
    rows=con.execute("""select pid,datname,state,wait_event_type,wait_event,
        extract(epoch from(clock_timestamp()-query_start))::int as query_seconds,
        left(query,180) from pg_stat_activity
        where datname like 'relbench_%' and state='active' order by query_start""").fetchall()
print(json.dumps({'active_queries':rows},default=str))
