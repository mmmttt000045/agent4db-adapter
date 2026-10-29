"""Offline integrity tests. Fixtures are temporary and never paper evidence."""
import importlib.util
import json
from pathlib import Path
import shutil
import unittest
import uuid

spec=importlib.util.spec_from_file_location('analysis',Path(__file__).with_name('analyze.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def cell(root,arm,*,bad_audit=False,missing=False,bad_tokens=False):
    folder=root/f'{arm}-rel-stack-r1'
    (folder/'sessions').mkdir(parents=True)
    cutoffs=[]
    for k in (1,2,3):
        ref={t:{'val':.5,'test':.5} for t in ('post-votes','user-badge','user-engagement')}
        cutoffs.append({'k':k,'reference':ref})
        for t in ref:
            if missing and k==3 and t=='user-engagement': continue
            r={'task':t,'k':k,'metric':'roc_auc','higher_is_better':True,
               'final_sql':'fixture SQL, not executed','audit':{'result':'error' if bad_audit else 'clean'},
               'eval':{'test':.9},'totals':{'tokens':100,'learn_tokens':20,
               'tokens_with_learning':119 if bad_tokens else 120,'llm_calls':2,'tool_calls':3,
               'tool_calls_by_category':{'schema':1,'probe':1,'validate':1}}}
            (folder/'sessions'/f'{t}-k{k}.json').write_text(json.dumps(r))
    (folder/'run.json').write_text(json.dumps({'finished':'fixture','cutoffs':cutoffs}))


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.fixture_parent=Path(__file__).resolve().parents[2]/'tmp'
        self.fixture_parent.mkdir(exist_ok=True)
        self.root=self.fixture_parent/('analysis-fixture-'+uuid.uuid4().hex)
        self.root.mkdir()
    def tearDown(self):
        # Delete only this test's verified workspace-owned temporary directory.
        assert self.root.resolve().parent==self.fixture_parent.resolve()
        assert self.root.name.startswith('analysis-fixture-')
        shutil.rmtree(self.root)

    def test_all_planned_cells_are_visible(self):
        data=mod.analyze(self.root)
        self.assertEqual(len(data['cells']),10)
        self.assertFalse(data['comparisons'])

    def test_missing_session_cannot_enter_comparison(self):
        cell(self.root,'none');cell(self.root,'mavra',missing=True)
        data=mod.analyze(self.root)
        self.assertFalse(data['comparisons'])
        self.assertEqual(mod.read_cell(self.root,'mavra','rel-stack')['status'],'complete_with_issues')

    def test_failed_audit_uses_reference_and_keeps_all_cost(self):
        cell(self.root,'mavra',bad_audit=True)
        rows=mod.read_cell(self.root,'mavra','rel-stack')['sessions']
        self.assertTrue(all(r['test']==.5 and not r['valid'] for r in rows))
        self.assertEqual(mod.summarize(rows)['tokens'],9*120)
        self.assertEqual(mod.summarize(rows)['fallback_counts'],{'audit_not_clean':9})

    def test_token_accounting_mismatch_is_rejected(self):
        cell(self.root,'none',bad_tokens=True)
        with self.assertRaises(AssertionError): mod.read_cell(self.root,'none','rel-stack')

    def test_control_pair_is_not_called_full_published_comparison(self):
        cell(self.root,'none');cell(self.root,'mavra')
        comp=mod.analyze(self.root)['comparisons']['rel-stack']
        self.assertFalse(comp['has_published_baseline'])
        self.assertFalse(comp['complete_method_set'])
        self.assertEqual(comp['arms']['mavra']['reuse_tokens'],6*120)

    def test_utf8_server_logs_are_readable_on_windows(self):
        cell(self.root,'none')
        p=next((self.root/'none-rel-stack-r1/sessions').glob('*.json'))
        r=json.loads(p.read_text());r['messages']=[{'content':'中文验证记录 — 提交方案'}]
        p.write_text(json.dumps(r,ensure_ascii=False),encoding='utf-8')
        self.assertEqual(mod.read_cell(self.root,'none','rel-stack')['status'],'complete')

    def test_reuse_phase_does_not_replace_all_cutoff_quality(self):
        cell(self.root,'none')
        rows=mod.read_cell(self.root,'none','rel-stack')['sessions']
        for r in rows:
            r['test']=.1 if r['k']==1 else .9
        s=mod.summarize(rows)
        self.assertAlmostEqual(s['quality']['post-votes']['mean'],(.1+.9+.9)/3)
        self.assertAlmostEqual(s['reuse_quality']['post-votes']['mean'],.9)
        self.assertEqual(s['tokens'],9*120)
        self.assertEqual(s['reuse_tokens'],6*120)


if __name__=='__main__': unittest.main()
