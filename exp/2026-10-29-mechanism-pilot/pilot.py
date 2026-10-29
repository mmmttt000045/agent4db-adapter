#!/usr/bin/env python3
"""Frozen-source, validation-only 2x2 representation pilot.

The shared harness supplies SQL contracts, model fitting, leakage audits and
session control. Its generic composite-tool hook routes a read-only source
memory; this study does not execute AgentSM or any published memory algorithm.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools/relbench'))
import harness as h

CFG = json.loads((HERE / 'protocol.json').read_text())
for name, key in [('MAX_LLM_CALLS', 'max_model_calls'), ('MAX_VALIDATIONS', 'max_validations'),
                  ('PATIENCE', 'patience'), ('SAMPLE_SIZE', 'training_sample'),
                  ('AUDIT_LEAK_SEEDS', 'audit_seeds'), ('AUDIT_SEEDS', 'publication_seeds'),
                  ('FEATURE_SQL_TIMEOUT_S', 'feature_sql_timeout_seconds'),
                  ('TOOL_OUTPUT_CHARS', 'tool_output_chars')]:
    setattr(h, name, CFG[key])
h.read_sql.__defaults__ = (CFG['feature_sql_timeout_seconds'], None)
h.LLM_RETRIES = 2
h.LGB_PARAMS['n_jobs'] = 4


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


class SourceMemory:
    """All information boundaries are checked again at dispatch, not just UI."""
    def __init__(self, arm, source, middle, definitions):
        self.arm, self.source, self.middle = arm, source, middle
        self.definitions = copy.deepcopy(definitions)
        self.keys = {x['key'] for x in self.definitions['features']}
        self._names = set()
        if arm in ('program', 'full'):
            self._names.add('retrieve_programs')
        if arm in ('definition', 'full'):
            self._names.update(('find_features', 'compose_features'))
        self.outputs = []

    def names(self):
        """Match the harness's callable composite-tool interface."""
        return set(self._names)

    def tool_specs(self):
        specs = {
            'retrieve_programs': ('Retrieve all frozen successful source programs for this entity, including OTHER tasks. You may reuse, rewrite or combine their full SQL. Source audit does not certify the target.',
                                  {'entity': {'type': 'string'}}, ['entity']),
            'find_features': ('Retrieve frozen executable feature definitions and their compiled SQL for this entity. Source publication does not certify the target; validate before use.',
                              {'entity': {'type': 'string'}}, ['entity']),
            'compose_features': ('Compile a chosen subset of frozen definition keys into SQL using {seeds}. Validate on the target before use.',
                                 {'keys': {'type': 'array', 'items': {'type': 'string'}}}, ['keys'])}
        return [{'type': 'function', 'function': {'name': n, 'description': specs[n][0],
                 'parameters': {'type': 'object', 'properties': specs[n][1], 'required': specs[n][2]}}}
                for n in sorted(self._names)]

    def composite(self, name, args, middle=None, agent=None, sid=None, callback=None):
        if name not in self._names:
            return {'error': 'tool not available in this ablation'}
        if name != 'compose_features' and args.get('entity', '').lower() != 'users':
            return {'programs': [], 'features': [], 'note': 'no source for this entity'}
        if name == 'retrieve_programs':
            out = {'programs': [{'source_task': self.source['task'], 'source_cutoff': self.source['k'],
                                'entity': 'users', 'seed_key': 'userid', 'sql': self.source['final_sql'],
                                'source_validation_auc': self.source['best_val'],
                                'source_audit': self.source['audit']}],
                   'note': 'Cross-task access is allowed. This is frozen source information, not target validation.'}
        elif name == 'find_features':
            out = copy.deepcopy(self.definitions)
        else:
            keys = args.get('keys') or []
            if not isinstance(keys, list) or not keys or not set(keys) <= self.keys:
                return {'error': 'select nonempty known source keys'}
            # Keep ordering deterministic despite source middleware hit counters.
            out = self.middle.call('compose_features', 'frozen-source', 'frozen-source', 'frozen-source',
                                   {'keys': sorted(set(keys)), 'seed_key': 'userid'})
        self.outputs.append({'tool': name, 'args': copy.deepcopy(args), 'output': copy.deepcopy(out)})
        return out

    def close(self):
        pass


class PilotRun(h.Run):
    def __init__(self, a, memory=None):
        super().__init__(a)
        self.memory = memory
        self.asm = memory
        # All four arms share the same base metadata/cache implementation.
        self.arm = {'middle_mode': 'relbench-mavra', 'parallel_ok': False}

    def target(self, t, k):
        return None

    def agentsm_sql(self, middle, agent, sid, args, rec):
        """The shared hook must not add AgentSM's model-assisted SQL repair.

        Match the no-memory run_sql branch exactly, including error handling.
        """
        try:
            return middle.call('run_sql', agent, sid, sid, args)
        except Exception as err:
            return {'error': f'{err}'}

    def incumbent(self, t, k, seeds):
        return {'val': None, 'why': 'fixed common pilot budget; no per-method goal'}

    def system_prompt(self, t, k, seeds):
        prompt = super().system_prompt(t, k, seeds)
        prompt += '\n\nThis is a fixed-budget feature engineering session. Any memory tools listed are optional. Choose which information to use; raw SQL may be adapted or combined. Every final solution must pass the same validation and temporal audit. No target result is written to memory.'
        return prompt

    def seed_tables(self, k):
        """Read test entity/time columns only; never deserialize test labels."""
        seeds = {}
        with h.psycopg.connect(self.url, autocommit=True) as con:
            con.execute('DROP SCHEMA IF EXISTS task CASCADE')
            con.execute('CREATE SCHEMA task')
            for t, e in self.tasks.items():
                ec, tc, yc = e['entity_col'].lower(), e['time_col'], e['target_col'].lower()
                folder = Path(self.a.prep) / 'tasks' / t / f'k{k}'
                parts = {}
                for split in ('train', 'val', 'test'):
                    cols = [e['entity_col'], tc] if split == 'test' else None
                    df = h.pd.read_parquet(folder / f'{split}.parquet', columns=cols)
                    df.columns = [c.lower() for c in df.columns]
                    df = df.rename(columns={tc.lower(): 'seed_time'})
                    df['seed_time'] = h.pd.to_datetime(df['seed_time'])
                    if split == 'val' and len(df) > CFG['validation_sample']:
                        df = df.sample(n=CFG['validation_sample'], random_state=42).reset_index(drop=True)
                    parts[split] = df
                tr = parts['train']
                parts['train_sample'] = tr.sample(n=min(len(tr), CFG['training_sample']), random_state=42).reset_index(drop=True)
                for split in ('train', 'train_sample', 'val', 'test'):
                    cols = [ec, 'seed_time'] + ([] if split == 'test' else [yc])
                    types = {ec: 'bigint', 'seed_time': 'timestamp', yc: 'double precision'}
                    con.execute(f"CREATE TABLE task.{h.tname(t)}_{split} ({', '.join(c+' '+types[c] for c in cols)})")
                    h.copy_rows(con, f'task.{h.tname(t)}_{split}', parts[split][cols])
                    con.execute(f'ANALYZE task.{h.tname(t)}_{split}')
                seeds[t] = parts
        return seeds

    def evaluate(self, t, k, sql, seeds, search_path=None):
        e = self.tasks[t]
        ec, yc = e['entity_col'].lower(), e['target_col'].lower()
        xt, st = h.features(self.url, sql, f'task.{h.tname(t)}_train_sample', seeds['train_sample'], ec, search_path)
        xv, sv = h.features(self.url, sql, f'task.{h.tname(t)}_val', seeds['val'], ec, search_path)
        pv, _, fit = h.train_predict(e['task_type'], xt, seeds['train_sample'][yc], xv)
        return {'val': h.score(e['task_type'], seeds['val'][yc], pv), 'test': None, 'development_only': True,
                'sql_seconds': st + sv, 'train_seconds': fit, 'n_features': xt.shape[1]}

    def evaluate_after_run(self, ks):
        raise AssertionError('Pilot must not run test evaluation')

    def session(self, t, k, seeds, middle):
        if self.memory:
            self.memory.outputs = []
        # Probe source programs and compiled SQL on each target before the agent.
        # These outcomes are diagnostic only: no target-based filtering or prompt feedback.
        if self.memory and self.a.arm == 'full':
            diagnosis = {}
            for kind, sql in [('program', self.memory.source['final_sql']), ('compiled', self.memory.definitions.get('sql'))]:
                if sql:
                    try:
                        diagnosis[kind] = self.audit(t, k, sql, seeds)
                    except Exception as err:
                        diagnosis[kind] = {'result': 'error', 'why': str(err)[:500]}
            save(Path(self.a.out) / 'source-target-audit.json', diagnosis)
        rec = super().session(t, k, seeds, middle)
        rec['memory_outputs'] = self.memory.outputs if self.memory else []
        for entry in rec['tools']:
            if self.memory and entry['name'] in self.memory.names():
                entry['category'] = 'memory'
        rec['totals']['tool_calls_by_category'] = {c: sum(x.get('category') == c for x in rec['tools'])
                                                  for c in ('schema', 'probe', 'validate', 'memory', 'submit')}
        rec['pilot'] = {'test_labels_read': False, 'test_scored': False, 'target_writeback': False,
                        'source_sha256': self.memory.source['provenance']['source_sha256'] if self.memory else None}
        save(Path(self.a.out) / 'sessions' / f'{h.tname(t)}-k{k}.json', rec)
        return rec


def options(arm, task, cutoff, out):
    h.ARMS[arm] = {'middle_mode': 'relbench-mavra', 'parallel_ok': False}
    return argparse.Namespace(arm=arm, run=1, tasks=[task], cutoffs=[cutoff], out=str(out),
        data='results/relbench-data/rel-stack', prep='results/relbench-data/rel-stack-prep',
        template='relbench_stack_t1', parallel=1, port=None, keep_db=False, agentsm_memory=None,
        targets_from=None, llm='deepseek', reasoning_effort=CFG['reasoning_effort'], eval_now=True, smoke=False)


def run_source(out):
    a = options('source', CFG['source']['task'], 1, out)
    run = PilotRun(a)
    h.create_run_db(run.url_admin, a.template, run.db_name)
    middle = h.Middle(run.url, 'relbench-mavra', a.out, h.free_port(), 'deepseek', run.llm.effort, run.llm.prefix)
    try:
        seeds = run.seed_tables(1)[CFG['source']['task']]
        archived = json.loads((HERE / 'source-input.json').read_text())
        source = copy.deepcopy(archived)
        audit = run.audit(source['task'], 1, source['final_sql'], seeds)
        save(Path(out) / 'source-audit.json', audit)
        if audit.get('result') != 'clean':
            raise RuntimeError('Frozen source failed fresh audit; preserve diagnostic and stop')
        evaluation = run.evaluate(source['task'], 1, source['final_sql'], seeds)
        ref = run.evaluate(source['task'], 1, run.reference_sql(source['task']), seeds)
        run.refs[(source['task'], 1)] = ref
        source.update(best_val=evaluation['val'], audit=audit, eval=evaluation)
        result = run.learn(source['task'], 1, source, seeds, middle, 'frozen-source', 'frozen-source')
        source['new_learning'] = result
        save(Path(out) / 'source.json', source)
        save(Path(out) / 'source-features.json', middle.get('/v1/features'))
        definitions = middle.call('find_features', 'frozen-source', 'frozen-source', 'frozen-source',
                                  {'entity': 'users', 'query': '', 'seed_key': 'userid'})
        for entry in definitions.get('features', []):
            entry.pop('uses', None)
        save(Path(out) / 'frozen-definitions.json', definitions)
        if not definitions.get('features') or not definitions.get('sql'):
            raise RuntimeError('No admitted definitions; source gate failed')
        return run, middle, source, definitions
    except BaseException:
        middle.close()
        h.drop_db(run.url_admin, run.db_name)
        raise


def main():
    out = ROOT / 'results/mechanism-pilot-20261029'
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'pilot-state.json').exists():
        raise RuntimeError('A pilot state already exists; paid reruns require a separate explicit attempt')
    state = {'started_utc': stamp(), 'status': 'source', 'cells': [], 'protocol_sha256': sha(HERE / 'protocol.json')}
    save(out / 'pilot-state.json', state)
    source_run = source_middle = None
    try:
        source_run, source_middle, source, definitions = run_source(out / 'source')
        pairs = [(target, arm) for target in CFG['targets'] for arm in CFG['arms']]
        random.Random(CFG['ordering_seed']).shuffle(pairs)
        save(out / 'frozen-order.json', pairs)
        for target, arm in pairs:
            name = target['name'] + '-' + arm
            state.update(status='running', current=name)
            save(out / 'pilot-state.json', state)
            start = time.monotonic()
            memory = SourceMemory(arm, source, source_middle, definitions) if arm != 'none' else None
            a = options(arm, target['task'], target['cutoff'], out / name)
            cell = {'name': name, 'arm': arm, 'target': target, 'started_utc': stamp()}
            try:
                PilotRun(a, memory).main()
                cell['status'] = 'complete'
            except h.LlmUnavailable:
                cell.update(status='incomplete_service_or_limit', error=traceback.format_exc()[-2000:])
                raise
            except Exception:
                cell.update(status='failed', error=traceback.format_exc()[-2000:])
                # A failure remains in the matrix; continue other predeclared cells.
            finally:
                cell.update(seconds=time.monotonic() - start, ended_utc=stamp())
                state['cells'].append(cell)
                save(out / 'pilot-state.json', state)
        state['status'] = 'complete'
    except BaseException:
        state.update(status='stopped', error=traceback.format_exc()[-4000:])
        raise
    finally:
        if source_middle:
            source_middle.close()
        if source_run:
            h.drop_db(source_run.url_admin, source_run.db_name)
        state['ended_utc'] = stamp()
        save(out / 'pilot-state.json', state)


if __name__ == '__main__':
    main()
