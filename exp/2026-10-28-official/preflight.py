#!/usr/bin/env python3
"""Small, billed tool round-trip; persist usage and actual returned model only."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0,'tools/relbench')
import harness as h

env=h.load_env()
llm=h.Llm(env,'deepseek')
messages=[{'role':'user','content':'Call get_number before replying, then report the returned number.'}]
spec=[{'type':'function','function':{'name':'get_number','description':'Get the number.',
       'parameters':{'type':'object','properties':{},'required':[]}}}]
first=llm.chat(messages,spec,max_tokens=1024)
m=first.pop('message')
assert (m.get('tool_calls') or [{}])[0].get('function',{}).get('name')=='get_number','tool invocation failed'
messages += [llm.history(m),{'role':'tool','tool_call_id':m['tool_calls'][0]['id'],'content':'42'}]
second=llm.chat(messages,spec,max_tokens=1024)
assert '42' in (second.pop('message').get('content') or ''),'tool round trip failed'
with h.psycopg.connect(h.base_url(env['AGENTDB_URL'])+'/postgres',autocommit=True) as con:
    templates=[x[0] for x in con.execute("SELECT datname FROM pg_database WHERE datname IN ('relbench_stack_t1','relbench_trial_t1','relbench_amazon_t1')")]
assert len(templates)==3
report={'utc':datetime.now(timezone.utc).isoformat(),'status':'passed','endpoint':'https://api.deepseek.com',
        'local_budget_relay':llm.base,'model':llm.model,'effort':llm.effort,
        'templates':sorted(templates),'responses':[first,second]}
Path('results/official-20261028/preflight.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
