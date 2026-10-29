"""Expense reconciliation safeguards, independent of the running experiment."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('expense_audit', HERE / 'audit-expenses.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExpenseTests(unittest.TestCase):
    def setUp(self):
        self.test_base = (HERE.parents[1] / 'tmp' / 'expense-audit-tests').resolve()
        self.test_base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_base)
        self.root = Path(self.temp.name)
        self.row = {'utc': '2026-10-28T11:00:00+00:00', 'status': 200,
                    'response_id': 'unique', 'model': 'deepseek-flash',
                    'usage': {'prompt_tokens': 1_000_000, 'prompt_cache_hit_tokens': 500_000,
                              'prompt_cache_miss_tokens': 500_000, 'completion_tokens': 100_000,
                              'total_tokens': 1_100_000}, 'ceiling_cny': 999.0}
        self.state = {'calls': 1, 'reserved_cny': 0, 'initial_balance_cny': 10,
                      'balance_cny': 9.09, 'updated_utc': '2026-10-28T11:01:00+00:00',
                      'ceiling_cny': 1.82}
        self.closing = {'checked_utc': '2026-10-28T11:02:00+00:00',
                        'balance_cny': 9.09, 'new_calls_blocked': True}

    def tearDown(self):
        assert self.root.resolve().is_relative_to(self.test_base)
        self.temp.cleanup()

    def save(self, rows=None):
        (self.root/'api-usage.jsonl').write_text('\n'.join(json.dumps(x) for x in (rows or [self.row]))+'\n')
        (self.root/'budget-state.json').write_text(json.dumps(self.state))
        (self.root/'closing-balance.json').write_text(json.dumps(self.closing))

    def test_recomputes_offpeak_price_not_historical_ceiling(self):
        self.save()
        out = module.audit(self.root, final=True)
        self.assertAlmostEqual(out['known_usage_charge_cny'], .91)
        self.assertAlmostEqual(out['observed_account_decrease_cny'], .91)
        self.assertAlmostEqual(out['account_minus_usage_charge_cny'], 0)

    def test_final_requires_consistent_settled_state(self):
        self.state['calls'] = 2
        self.save()
        self.assertFalse(module.audit(self.root)['ledger_state_consistent'])
        with self.assertRaises(ValueError): module.audit(self.root, final=True)
        self.state['calls'] = 1
        self.state['reserved_cny'] = .1
        self.save()
        with self.assertRaises(ValueError): module.audit(self.root, final=True)

    def test_duplicate_or_unknown_usage_cannot_be_silently_finalized(self):
        self.state['calls'] = 2
        self.save([self.row, self.row])
        with self.assertRaises(ValueError): module.audit(self.root, final=True)
        self.state['calls'] = 1
        self.row['usage'] = {}
        self.save()
        self.assertEqual(module.audit(self.root)['unknown_usage_rows'], [1])
        with self.assertRaises(ValueError): module.audit(self.root, final=True)

    def test_closing_balance_must_follow_last_response(self):
        self.closing['checked_utc'] = '2026-10-28T10:59:00+00:00'
        self.save()
        with self.assertRaises(ValueError): module.audit(self.root, final=True)

    def test_wrong_cache_or_time_cannot_receive_offpeak_price(self):
        self.row['usage']['prompt_cache_miss_tokens'] = 999
        self.save()
        with self.assertRaises(ValueError): module.audit(self.root)
        self.row['usage']['prompt_cache_miss_tokens'] = 500_000
        self.row['utc'] = '2026-10-28T03:00:00+00:00'
        self.save()
        with self.assertRaises(ValueError): module.audit(self.root)


if __name__ == '__main__': unittest.main()
