"""Offline checks of the spending ceiling; no credentials or network calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import threading
from datetime import datetime, timezone, timedelta
import json

spec=importlib.util.spec_from_file_location('budget_proxy',Path(__file__).with_name('budget-proxy.py'))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CeilingTests(unittest.TestCase):
    def mock_budget(self, directory):
        b = mod.Budget.__new__(mod.Budget)
        b.directory = Path(directory)
        b.path = b.directory/'state.json'
        b.lock = threading.Lock()
        b.reserved = 0.
        b.balance = lambda: 100.
        b.state = {'initial_balance_cny':100., 'ceiling_cny':0., 'calls':0, 'errors':0, 'models':{}, 'status':'ready'}
        return b

    def test_unknown_usage_retains_full_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.mock_budget(d)
            b.reserved = .14
            b.finish(.14, 503, {'error':'transport'}, 1., 'fake')
            self.assertEqual(b.reserved, 0.)
            self.assertAlmostEqual(b.state['ceiling_cny'], .14)

    def test_parallel_reservations_cannot_exceed_twenty(self):
        previous = mod.ROOT
        try:
            with tempfile.TemporaryDirectory() as d:
                mod.ROOT = Path(d)
                (mod.ROOT/'protocol.json').write_text(json.dumps({'budget_cny':50., 'deadline_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}))
                b = self.mock_budget(d)
                b.state['ceiling_cny'] = 19.80
                body = {'messages':[], 'max_tokens':16384}
                b.acquire(body)
                with self.assertRaisesRegex(RuntimeError, 'spending limit'):
                    b.acquire(body)
                self.assertLessEqual(b.state['ceiling_cny']+b.reserved,20.)
        finally:
            mod.ROOT = previous

    def test_no_cache_is_not_free(self):
        self.assertAlmostEqual(mod.upper_cost({'prompt_tokens':1000000,'completion_tokens':1000000}),10.)

    def test_official_cache_field(self):
        self.assertAlmostEqual(mod.upper_cost({'prompt_tokens':1000000,'prompt_cache_hit_tokens':500000}),1.02)

    def test_sdk_cache_field(self):
        self.assertAlmostEqual(mod.upper_cost({'prompt_tokens':1000000,'prompt_tokens_details':{'cached_tokens':500000}}),1.02)

    def test_cache_cannot_exceed_input(self):
        self.assertAlmostEqual(mod.upper_cost({'prompt_tokens':1000,'prompt_cache_hit_tokens':2000}),.00004)

    def test_reservation_includes_output_ceiling(self):
        body={'messages':[{'role':'user','content':'small input'}],'max_tokens':16384}
        self.assertGreater(mod.reserve_cost(body),16384*8/1e6)

    def test_reprice_retains_unknown_and_unlogged_charges(self):
        rows=[{'usage':{'prompt_tokens':1000000},'ceiling_cny':3.},
              {'usage':{},'ceiling_cny':.6}]
        state={'calls':2,'ceiling_cny':4.0}
        self.assertAlmostEqual(mod.reprice_legacy_ceiling(state,rows),3.0)

    def test_reprice_count_mismatch_stops(self):
        with self.assertRaises(RuntimeError):
            mod.reprice_legacy_ceiling({'calls':1,'ceiling_cny':1.},[])

    def test_peak_ceiling_is_twice_current_offpeak(self):
        u={'prompt_tokens':1000000,'prompt_cache_hit_tokens':250000,'completion_tokens':100000}
        offpeak=(250000*.02+750000*1+100000*4)/1e6
        self.assertAlmostEqual(mod.upper_cost(u),2*offpeak)


if __name__=='__main__':
    unittest.main()
