#!/usr/bin/env python3
"""Audit the proposed common seed binding without calling a model."""
import json
import os
import traceback

import pilot as p
from seed_adapter import bind_seed_key

os.chdir(p.ROOT)
base=p.ROOT/'results/mechanism-pilot-20261029'
assert json.loads((base/'repair-v1/state.json').read_text())['status']=='complete'
assert not (base/'seed-binding-preflight.json').exists()
source=json.loads((base/'source/source.json').read_text())
definitions=json.loads((base/'source/frozen-definitions.json').read_text())
out={'role':'new formal-protocol preparation; not a replacement for original pilot outcomes',
     'llm_calls':0,'binding':'same identifier-only wrapper for program and compiled definitions','targets':[]}
for target in p.CFG['targets']:
    folder=base/'binding-preflight'/target['name'];folder.mkdir(parents=True,exist_ok=True)
    a=p.options('binding-preflight',target['task'],target['cutoff'],folder)
    run=p.PilotRun(a)
    p.h.create_run_db(run.url_admin,a.template,run.db_name)
    try:
        seeds=run.seed_tables(target['cutoff'])[target['task']]
        key=run.tasks[target['task']]['entity_col'].lower()
        row={'target':target,'source_seed_key':'userid','target_seed_key':key,'audits':{}}
        for kind,sql in [('program',source['final_sql']),('compiled',definitions['sql'])]:
            fixed=bind_seed_key(sql,'userid',key)
            try: row['audits'][kind]=run.audit(target['task'],target['cutoff'],fixed,seeds)
            except Exception as e:row['audits'][kind]={'result':'error','reason':str(e)[:1200]}
        out['targets'].append(row)
        p.save(base/'seed-binding-preflight.json',out)
    finally:p.h.drop_db(run.url_admin,run.db_name)
print(json.dumps(out,indent=2))
