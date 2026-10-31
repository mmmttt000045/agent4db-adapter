"""Offline cumulative-cap tests. No network or real credentials."""
import importlib.util,json,tempfile,threading,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

spec=importlib.util.spec_from_file_location('proxy',Path(__file__).with_name('budget-proxy.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class FixedDate(datetime):
    current=datetime(2026,10,31,3,0,tzinfo=timezone.utc)
    @classmethod
    def now(cls,tz=None): return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.old_root,self.old_date=mod.ROOT,mod.datetime
        mod.ROOT=self.root;mod.datetime=FixedDate
        FixedDate.current=datetime(2026,10,31,3,0,tzinfo=timezone.utc)
        self.cfg={'budget_cny':20,'deadline_utc':'2026-10-31T15:00:00+00:00','pricing_window_end_utc':'2026-11-01T16:00:00+00:00'}
        (self.root/'protocol.json').write_text(json.dumps(self.cfg))
        self.b=mod.Budget.__new__(mod.Budget);self.b.directory=self.root;self.b.path=self.root/'budget-state.json'
        self.b.lock=threading.Lock();self.b.reserved=0;self.b.balance=lambda:91.35
        self.b.state={'initial_balance_cny':100,'ceiling_cny':8.69698742,'prior_cost_cny':8.69698742,'calls':0,'errors':0,'models':{},'status':'ready'}
        self.body={'messages':[],'max_tokens':16384}
    def tearDown(self): mod.ROOT=self.old_root;mod.datetime=self.old_date;self.temp.cleanup()
    def test_prior_expense_is_carried_through_success(self):
        r=self.b.acquire(self.body)
        self.assertGreater(self.b.state['ceiling_cny']+self.b.reserved,8.69698742)
        self.b.finish(r,200,{'model':'deepseek-flash','usage':{'prompt_tokens':1000,'completion_tokens':100}},1,'fake')
        self.assertAlmostEqual(self.b.state['ceiling_cny'],8.69838742)
        self.assertEqual(self.b.state['calls'],1)
    def test_parallel_reservations_respect_the_cumulative_cap(self):
        self.b.state['ceiling_cny']=19.90
        self.b.acquire(self.body)
        with self.assertRaisesRegex(RuntimeError,'spending limit'):self.b.acquire(self.body)
        self.assertLessEqual(self.b.state['ceiling_cny']+self.b.reserved,20)
    def test_account_decrease_is_also_guarded(self):
        self.b.balance=lambda:79.99
        with self.assertRaisesRegex(RuntimeError,'spending limit'):self.b.acquire(self.body)
    def test_unknown_failure_keeps_its_full_charge(self):
        reservation=self.b.acquire(self.body)
        self.b.finish(reservation,503,{},1,'fake')
        self.assertAlmostEqual(self.b.state['ceiling_cny'],8.69698742+reservation)
        self.assertEqual(self.b.state['errors'],1)
    def test_outside_weekend_fails_closed(self):
        FixedDate.current=datetime(2026,10,30,3,0,tzinfo=timezone.utc)
        with self.assertRaisesRegex(RuntimeError,'pricing window'):self.b.acquire(self.body)
    def test_stop_file_is_honored(self):
        (self.root/'STOP').touch()
        with self.assertRaisesRegex(RuntimeError,'stop requested'):self.b.acquire(self.body)
    def test_offpeak_token_prices_and_reservation(self):
        self.assertAlmostEqual(mod.upper_cost({'prompt_tokens':1000000,'prompt_cache_hit_tokens':500000,'completion_tokens':100000}),.91)
        self.assertGreater(mod.reserve_cost(self.body),16384*4/1e6)

if __name__=='__main__':unittest.main()
