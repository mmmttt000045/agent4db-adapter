#!/usr/bin/env python3
"""Frozen-study adapter; published baseline algorithms stay in the shared harness.

The optional MAVRA candidate changes how its own memory is consumed and avoids
re-extracting exactly identical, already published SQL. It never bypasses query
validation, temporal leakage audits, or the shared stopping rule.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/relbench'))
import harness as h

CONFIG = json.loads((Path(__file__).parent/'protocol.json').read_text())
for name, key in [('MAX_LLM_CALLS','max_model_calls'), ('MAX_VALIDATIONS','max_validations'),
                  ('POST_GOAL_LLM_CALLS','post_goal_calls'), ('SAMPLE_SIZE','training_sample'),
                  ('FEATURE_SQL_TIMEOUT_S','sql_timeout_seconds'), ('AUDIT_LEAK_SEEDS','leak_audit_seeds')]:
    setattr(h, name, CONFIG[key])
h.LLM_RETRIES = 3
ACTUAL_FEATURE_TIMEOUT = h.read_sql.__defaults__[0]
if ACTUAL_FEATURE_TIMEOUT != CONFIG.get('feature_statement_timeout_seconds', 600):
    raise RuntimeError('Feature-statement timeout differs from the audited study setting')


class StudyRun(h.Run):
    def __init__(self, a):
        super().__init__(a)
        if not self.tasks:
            raise ValueError('No tasks selected')
        self.published_sql = set()
        self.arm = dict(self.arm, study='official-20261028', candidate=a.candidate)

    def system_prompt(self, t, k, seeds):
        prompt = super().system_prompt(t,k,seeds)
        if self.a.candidate == 'compact-reuse' and self.arm.get('feature_memory'):
            prompt += ('\n\nMemory usage order: call find_program first. When program_sql is returned, '
                       'validate that complete SQL before fetching feature definitions or re-inspecting the schema. '
                       'If it is unavailable or does not meet the goal, use find_features for cross-task definitions '
                       'and compose_features as needed. Once the goal is reached, submit the validated SQL unless '
                       'you have a concrete, small improvement to test. Never skip temporal guards or validation.')
        return prompt

    def learn(self, t, k, rec, seeds, middle, agent, sid):
        sql = rec.get('final_sql') or ''
        fingerprint = (t, hashlib.sha256(sql.encode()).hexdigest())
        if (self.a.candidate == 'compact-reuse' and fingerprint in self.published_sql
                and (rec.get('audit') or {}).get('result') == 'clean'):
            return {'skipped': 'identical previously published SQL; current validation and audit passed',
                    'input_tokens': 0, 'output_tokens': 0, 'seconds': 0,
                    'sql_sha256': fingerprint[1]}
        result = super().learn(t,k,rec,seeds,middle,agent,sid)
        if result.get('program') and not result.get('error') and (rec.get('audit') or {}).get('result') == 'clean':
            self.published_sql.add(fingerprint)
        return result

    def evaluate(self, t, k, sql, seeds, search_path=None):
        if not self.a.development:
            return super().evaluate(t,k,sql,seeds,search_path)
        # Development uses validation only: do not even open test.parquet.
        e = self.tasks[t]
        ec, yc = e['entity_col'].lower(), e['target_col'].lower()
        xtr,s1 = h.features(self.url,sql,f'task.{h.tname(t)}_train_sample',seeds['train_sample'],ec,search_path)
        xva,s2 = h.features(self.url,sql,f'task.{h.tname(t)}_val',seeds['val'],ec,search_path)
        pv,_,tt = h.train_predict(e['task_type'],xtr,seeds['train_sample'][yc],xva)
        return {'val':h.score(e['task_type'],seeds['val'][yc],pv),'test':None,
                'development_only':True,'sql_seconds':s1+s2,'train_seconds':tt,'n_features':xtr.shape[1]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--arm',required=True,choices=['none','ace','awm','gmemory','mavra'])
    p.add_argument('--dataset',required=True,choices=['rel-stack','rel-trial','rel-amazon'])
    p.add_argument('--run',type=int,default=1)
    p.add_argument('--cutoffs',type=int,nargs='+',default=[1,2,3])
    p.add_argument('--tasks',nargs='+')
    p.add_argument('--out',required=True)
    p.add_argument('--candidate',choices=['original','compact-reuse'],default='original')
    p.add_argument('--development',action='store_true')
    a=p.parse_args()
    a.data=f'results/relbench-data/{a.dataset}'
    a.prep=a.data+'-prep'
    a.template=f'relbench_{a.dataset[4:]}_t1'
    a.parallel=1
    a.port=None
    a.keep_db=False
    a.agentsm_memory=None
    a.targets_from=None
    a.llm='deepseek'
    a.reasoning_effort=CONFIG['reasoning_effort']
    a.eval_now=False
    a.smoke=False
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=False)
    (out/'study-cell.json').write_text(json.dumps({'options':vars(a),'protocol':CONFIG,
        'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'effective_runtime':{'feature_statement_timeout_seconds':ACTUAL_FEATURE_TIMEOUT,
                             'tool_call_http_timeout_seconds':h.FEATURE_SQL_TIMEOUT_S}},indent=2)+'\n')
    def stop(signum,frame):
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,stop)
    StudyRun(a).main()


if __name__=='__main__':
    main()
