"""Checks for the experiment's information and evaluation boundaries."""
import inspect
import json
import unittest

import pilot as p
from seed_adapter import bind_seed_key


class DummyMiddle:
    def call(self, name, *args):
        return {'sql': 'compiled subset {seeds}', 'columns': [{'key': 'f1', 'revision': 0}]}


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.source = {'task': 'user-badge', 'k': 1, 'final_sql': 'raw program {seeds}',
                       'best_val': .8, 'audit': {'result': 'clean'}}
        self.defs = {'features': [{'key': 'f1', 'revision': 0, 'definition': 'STRUCTURED'}], 'sql': 'compiled {seeds}'}

    def memory(self, arm):
        return p.SourceMemory(arm, self.source, DummyMiddle(), self.defs)

    def test_exact_factorial_tool_access(self):
        expected = {'none': set(), 'program': {'retrieve_programs'},
                    'definition': {'find_features', 'compose_features'},
                    'full': {'retrieve_programs', 'find_features', 'compose_features'}}
        for arm, names in expected.items():
            m = self.memory(arm)
            self.assertEqual(m.names(), names)
            self.assertEqual({s['function']['name'] for s in m.tool_specs()}, names)

    def test_harness_dispatch_contract(self):
        for arm in ('program','definition','full'):
            m=self.memory(arm)
            for spec in m.tool_specs():
                name=spec['function']['name']
                # This is the actual harness branch which failed in attempt 1.
                self.assertIn(name,m.names())
                args={'keys':['f1']} if name=='compose_features' else {'entity':'users'}
                self.assertNotIn('error',m.composite(name,args,DummyMiddle(),'a','s',lambda _: None))

    def test_probe_error_does_not_invoke_hidden_model_repair(self):
        class BrokenMiddle:
            def call(self,*args): raise RuntimeError('expected SQL failure')
        obj=object.__new__(p.PilotRun)
        rec={}
        self.assertEqual(obj.agentsm_sql(BrokenMiddle(),'a','s',{'sql':'select 1'},rec),
                         {'error':'expected SQL failure'})
        self.assertEqual(rec,{})

    def test_program_only_no_definition_leak_and_cross_task_access(self):
        m = self.memory('program')
        out = m.composite('retrieve_programs', {'entity': 'users'}, sid='user-engagement')
        self.assertEqual(out['programs'][0]['source_task'], 'user-badge')
        self.assertEqual(out['programs'][0]['sql'], self.source['final_sql'])
        self.assertNotIn('STRUCTURED', json.dumps(out))
        self.assertIn('error', m.composite('find_features', {'entity': 'users'}))

    def test_definitions_only_do_not_return_program(self):
        m = self.memory('definition')
        self.assertNotIn('raw program', json.dumps(m.composite('find_features', {'entity': 'users'})))
        self.assertIn('error', m.composite('retrieve_programs', {'entity': 'users'}))

    def test_unknown_keys_and_entity_rejected(self):
        m = self.memory('full')
        self.assertIn('error', m.composite('compose_features', {'keys': ['future-target-feature']}))
        self.assertEqual(m.composite('retrieve_programs', {'entity': 'posts'})['programs'], [])

    def test_frozen_outputs_and_no_mutation(self):
        m = self.memory('full')
        a = m.composite('find_features', {'entity': 'users'})
        a['features'][0]['revision'] = 99
        self.assertEqual(m.composite('find_features', {'entity': 'users'})['features'][0]['revision'], 0)
        self.assertEqual(self.defs['features'][0]['revision'], 0)

    def test_no_method_specific_target(self):
        obj = object.__new__(p.PilotRun)
        self.assertIsNone(obj.target('user-badge', 2))
        self.assertIsNone(obj.incumbent('user-badge', 2, {})['val'])

    def test_test_evaluation_disabled(self):
        obj = object.__new__(p.PilotRun)
        with self.assertRaises(AssertionError):
            obj.evaluate_after_run([1, 2])
        self.assertNotIn('test.parquet', inspect.getsource(p.PilotRun.evaluate))
        self.assertIn("[e['entity_col'], tc] if split == 'test'", inspect.getsource(p.PilotRun.seed_tables))

    def test_next_protocol_binding_preserves_source_table_columns(self):
        sql='select s.userid, s.seed_time, b.userid as feature from {seeds} s join badges b on b.userid=s.userid'
        fixed=bind_seed_key(sql,'userid','owneruserid')
        self.assertIn('b.userid',fixed)
        self.assertIn('select owneruserid as userid, seed_time from {seeds}',fixed)
        self.assertTrue(fixed.endswith('memory_transfer(owneruserid, seed_time)'))
        self.assertEqual(bind_seed_key(sql,'userid','userid'),sql)

    def test_next_protocol_binding_rejects_non_identifier(self):
        with self.assertRaises(ValueError):bind_seed_key('select * from {seeds}','userid','x;select secret')


if __name__ == '__main__':
    unittest.main()
