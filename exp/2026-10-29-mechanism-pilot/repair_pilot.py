#!/usr/bin/env python3
"""Explicit infrastructure repair: only the six interrupted memory cells.

The two completed controls are retained even when they have poor outcomes.
The original source is reused byte for byte; no new extraction or selection.
"""
import copy
import json
from pathlib import Path
import time
import traceback

import pilot as p


class FrozenCompiler:
    def __init__(self, path):
        self.data=json.loads(Path(path).read_text())
        assert self.data['full_sql_exact_match']

    def call(self, name, agent, session, task, args):
        assert name=='compose_features'
        return copy.deepcopy(self.data['subsets']['|'.join(sorted(set(args['keys'])))])


def main():
    base=p.ROOT/'results/mechanism-pilot-20261029'
    out=base/'repair-v1'
    out.mkdir(exist_ok=True)
    assert not (out/'state.json').exists(), 'Repair already started; do not silently rerun'
    original=json.loads((base/'pilot-state.json').read_text())
    assert original['status']=='complete' and len(original['cells'])==8
    failed=[x['name'] for x in original['cells'] if x['status']=='failed']
    assert len(failed)==6 and all('TypeError' in x['error'] and "'set' object is not callable" in x['error']
        for x in original['cells'] if x['status']=='failed')
    source=json.loads((base/'source/source.json').read_text())
    definitions=json.loads((base/'source/frozen-definitions.json').read_text())
    compiler=FrozenCompiler(base/'source/frozen-compiled-subsets.json')
    state={'started_utc':p.stamp(),'status':'running','reason':'callable names interface fix; preserve both completed controls',
           'original_state_sha256':p.sha(base/'pilot-state.json'),'source_sha256':p.sha(base/'source/source.json'),
           'compiler_subsets_sha256':p.sha(base/'source/frozen-compiled-subsets.json'),
           'new_source_extraction':False,'cells':[]}
    p.save(out/'state.json',state)
    try:
        for target,arm in json.loads((base/'frozen-order.json').read_text()):
            name=target['name']+'-'+arm
            if name not in failed: continue
            state['current']=name;p.save(out/'state.json',state)
            start=time.monotonic()
            cell={'name':name,'arm':arm,'target':target,'started_utc':p.stamp()}
            try:
                mem=p.SourceMemory(arm,source,compiler,definitions)
                p.PilotRun(p.options(arm,target['task'],target['cutoff'],out/name),mem).main()
                cell['status']='complete'
            except Exception:
                cell.update(status='failed',error=traceback.format_exc()[-3000:])
                raise  # No repeated cascade after an infrastructure failure.
            finally:
                cell.update(seconds=time.monotonic()-start,ended_utc=p.stamp())
                state['cells'].append(cell);p.save(out/'state.json',state)
        state['status']='complete'
    except BaseException:
        state.update(status='stopped',error=traceback.format_exc()[-3000:]);raise
    finally:
        state['ended_utc']=p.stamp();p.save(out/'state.json',state)


if __name__=='__main__': main()
