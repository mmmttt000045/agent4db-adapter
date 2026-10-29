"""Offline checks of the spending ceiling; no credentials or network calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('budget_proxy',Path(__file__).with_name('budget-proxy.py'))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CeilingTests(unittest.TestCase):
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
