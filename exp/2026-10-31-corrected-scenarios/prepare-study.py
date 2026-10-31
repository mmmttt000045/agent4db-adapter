"""Build a versioned rerun from the archived adapters; preserve the old cohort."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / '2026-10-30-published-scenarios'


def change(s, old, new, count=1):
    assert s.count(old) == count, (s.count(old), old[:90])
    return s.replace(old, new)


def main():
    cfg = json.loads((OLD/'protocol.json').read_text(encoding='utf-8'))
    cfg.update(study='corrected-scenarios-20261031', created_utc=datetime.now(timezone.utc).isoformat(),
        deadline_utc='2026-10-31T15:00:00+00:00',
        authorization='Repair SQL admission and semantic retention, align feedback, rerun all methods, and update compact Fig.6/paper; cumulative DeepSeek CNY 20 including the prior study.',
        status_before_execution='Prepared; no paid calls in this cohort.',
        feedback='All four planners receive the same bounded format of their own previous questions, answers, SQL, observations and binary correctness. ACE/AWM/G-Memory retain their published update algorithms; MAVRA retains native publication/maintenance. No gold SQL/value, hidden change label, or other method trace is exposed.',
        feedback_history={'records':3, 'max_sql_chars':1800, 'max_observations':3, 'max_observation_chars':350,
                          'scope':'same actor; each change restores the post-heldout checkpoint',
                          'excludes':['gold answers','gold SQL','hidden change labels','other methods trajectories']},
        repairs=['AST-bound query-local uniqueness proofs for filtered/derived inputs and correlated EXISTS; keep base-table counterexamples',
                 'Unavailable definitions retain attributed business semantics and explicitly invalid historical mappings; execution is still denied'],
        selection='Retain the entire previous two-schema eleven-change suite; no outcome-based scenario or repeat selection. This rerun is informed by the prior failure analysis and is not an unseen evaluation.',
        prior_priced_usage_cny=8.69698742, prior_actual_debit_cny=8.65,
        prior_private_budget='/root/agentdb-published-scenarios-20261030/results/published-scenarios-20261030/budget/budget-state.json',
        prior_public_archive_sha256='60038c0c10ffb82d57fe9ec194ea2b225d636749b0b2eae5ad14e7f0b5f54006',
        price_policy='Verified weekend off-peak rates; reject outside the frozen weekend window. Carry prior priced usage conservatively and original account baseline; include all new attempts.',
        pricing_window_end_utc='2026-11-01T16:00:00+00:00')
    cfg['offpeak_guard_cny_per_million']={'hit':.02,'miss':1.,'output':4.}
    prior_ledger=HERE.parents[1]/'results/published-scenarios-20261030/budget/api-usage.jsonl'
    cfg['prior_ledger_sha256']=hashlib.sha256(prior_ledger.read_bytes()).hexdigest()
    cfg['execution_order']='Same fixed Latin-rotated arm order, two datasets per arm. Repeat 2 requires the entire first block plus remaining funds > 1.2 times first-block incremental charge + CNY 0.4, and enough time. All charges include failed attempts.'
    (HERE/'protocol.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    service=(OLD/'memory-service.py').read_text(encoding='utf-8')
    service=service.replace('published-scenarios-20261030-local','corrected-scenarios-20261031-local').replace('results/published-scenarios-20261030','results/corrected-scenarios-20261031')
    service=change(service,'        self.active = None\n\n    def gstart','        self.active = None\n        self.feedback = []\n\n    def gstart')
    service=change(service,'        if self.arm == "ace":\n            book =', '''        common = "\\n\\nEnvironment feedback from your own earlier tasks (binary correctness; no reference answers):\\n" + json.dumps(self.feedback[-3:], ensure_ascii=False)
        if self.arm == "mavra":
            return {"system_prompt": common, "user_prompt": "", "common_feedback": self.feedback[-3:]}
        if self.arm == "ace":
            book =''')
    service=change(service,'"system_prompt": "\\n\\n" + block +','"system_prompt": common + "\\n\\n" + block +')
    service=change(service,'"system_prompt": "\\n\\n" + workflows if workflows else "",','"system_prompt": common + ("\\n\\n" + workflows if workflows else ""),')
    service=change(service,'return {"system_prompt": "", "user_prompt": "\\n\\n" + value["prompt"], **value,','return {**value, "system_prompt": common, "user_prompt": "\\n\\n" + value["prompt"],')
    service=change(service,'        self.k += 1\n', '''        self.k += 1
        observations = [{"tool": e["tool"], "output": e["output"][:350]}
                        for e in req["transcript"] if e.get("kind")=="tool" and e.get("tool")=="run_sql"][-3:]
        self.feedback.append({"question":req["question"], "own_answer":req.get("answer"),
            "correct":bool(req["correct"]), "own_sql":(req.get("sql") or "")[:1800], "own_observations":observations})
        self.feedback = self.feedback[-3:]
        if self.arm == "mavra":
            self.active = None
            return {"common_feedback_recorded":True,"feedback_records":len(self.feedback),"input_tokens":0,"output_tokens":0}
''')
    service=change(service,'self.snapshot = {"k": self.k, "state":','self.snapshot = {"k": self.k, "feedback":copy.deepcopy(self.feedback), "state":')
    service=change(service,'        self.k = self.snapshot["k"]\n','        self.k = self.snapshot["k"]\n        self.feedback = copy.deepcopy(self.snapshot["feedback"])\n')
    service=change(service,'arm not in ("ace", "awm", "gmemory")','arm not in ("ace", "awm", "gmemory", "mavra")')
    service=change(service,'                    result = self.begin(req)','                    result = self.begin(req)\n                    result["common_feedback"] = copy.deepcopy(self.feedback[-3:])')
    (HERE/'memory-service.py').write_text(service,encoding='utf-8')

    proxy=(OLD/'budget-proxy.py').read_text(encoding='utf-8')
    proxy=proxy.replace('published-scenarios-20261030-local','corrected-scenarios-20261031-local')
    proxy=proxy.replace('The ceiling uses verified official CNY peak prices, twice the off-peak prices\nduring this study. It is a spending guard, not an invoice. Balance is checked too.',
        'The ceiling carries all prior spending and uses verified weekend off-peak\nprices only inside the frozen weekend window. The original balance is checked too.')
    proxy=change(proxy,"RATES = {'hit': .04, 'miss': 2.0, 'output': 8.0}","RATES = {'hit': .02, 'miss': 1.0, 'output': 4.0}")
    proxy=change(proxy,"PRICING_POLICY = 'official-cny-peak-2026-10-30'","PRICING_POLICY = 'official-weekend-offpeak-cumulative-20261031'")
    proxy=change(proxy,"self.state = {'started_utc': datetime.now(timezone.utc).isoformat(),\n                          'initial_balance_cny': self.balance(), 'ceiling_cny': 0.0,",'''prior_path = Path(self.config['prior_private_budget'])
            prior = json.loads(prior_path.read_text())
            if prior['calls'] != 3378 or abs(prior['reserved_cny']) > 1e-8 or not (prior_path.parent/'STOP').exists():
                raise RuntimeError('Prior study must be closed and fully accounted')
            initial = prior['initial_balance_cny']
            raw = (prior_path.parent/'api-usage.jsonl').read_bytes()
            if hashlib.sha256(raw).hexdigest() != self.config['prior_ledger_sha256']:
                raise RuntimeError('Prior usage ledger hash changed')
            rows = [json.loads(line) for line in raw.splitlines() if line]
            if len(rows) != prior['calls'] or any(not row.get('usage') for row in rows):
                raise RuntimeError('Prior usage is not fully accounted')
            for row in rows:
                local = datetime.fromisoformat(row['utc']).astimezone(timezone(__import__('datetime').timedelta(hours=8)))
                if local.weekday()<5 and (9<=local.hour<12 or 14<=local.hour<18):
                    raise RuntimeError('Prior requests require peak repricing')
            computed = sum(upper_cost(row['usage']) for row in rows)
            if abs(computed-self.config['prior_priced_usage_cny'])>1e-8:
                raise RuntimeError('Prior charge does not match the frozen ledger')
            floor = max(self.config['prior_priced_usage_cny'], max(0.,initial-self.balance()))
            self.state = {'started_utc': datetime.now(timezone.utc).isoformat(),
                          'initial_balance_cny': initial, 'ceiling_cny': floor, 'prior_cost_cny': floor,''')
    proxy=change(proxy,'            reservation = reserve_cost(body)\n', '''            now = datetime.now(timezone.utc)
            beijing = now.astimezone(timezone(__import__('datetime').timedelta(hours=8)))
            if beijing.weekday() < 5 or now >= datetime.fromisoformat(self.config['pricing_window_end_utc']):
                raise RuntimeError('Frozen off-peak pricing window ended')
            reservation = reserve_cost(body)
''')
    (HERE/'budget-proxy.py').write_text(proxy,encoding='utf-8')

    runner=(OLD/'run-study.py').read_text(encoding='utf-8')
    runner=runner.replace('agentdb-published-scenarios-20261030','agentdb-corrected-scenarios-20261031').replace('published-scenarios-20261030','corrected-scenarios-20261031')
    runner=change(runner,'            if arm != "mavra":','            if arm in cfg["arms"]:')
    runner=change(runner,'                cost = max(b["ceiling_cny"], b.get("observed_account_decrease_cny", 0))\n                remaining = cfg["budget_cny"] - cost',
        '                cumulative = max(b["ceiling_cny"], b.get("observed_account_decrease_cny", 0))\n                cost = cumulative - b["prior_cost_cny"]\n                remaining = cfg["budget_cny"] - cumulative')
    (HERE/'run-study.py').write_text(runner,encoding='utf-8')
    for name in ['archive-results.py']:
        (HERE/name).write_bytes((OLD/name).read_bytes())
    smoke=(OLD/'offline-smoke.py').read_text(encoding='utf-8')
    smoke=smoke.replace('for arm in ("ace", "awm", "gmemory"):','for arm in ("ace", "awm", "gmemory", "mavra"):')
    smoke=change(smoke,'                begin = post({**base, "op": "begin"})','                begin = post({**base, "op": "begin"})\n                assert begin["common_feedback"] == []')
    smoke=change(smoke,'                if arm == "awm":','                assert len(warm["common_feedback"]) == 1 and warm["common_feedback"][0]["correct"] is True\n                assert all("phase" not in x and "gold" not in x for x in warm["common_feedback"])\n                if arm == "awm":')
    smoke=smoke.replace('key = "synthetic-r98-ace"','key = "synthetic-r98-mavra"').replace('"--modes", "paper-ace",','"--modes", "metric-global-full",')
    smoke=smoke.replace('"arms": ["ace", "awm", "gmemory"]','"arms": ["ace", "awm", "gmemory", "mavra"]')
    smoke=change(smoke,'            assert report["database_cleaned_up"] is True',
        '            assert report["database_cleaned_up"] is True\n            assert all(r["published_memory"]["common_feedback_recorded"] for r in report["cells"][0]["records"])\n            assert report["cells"][0]["records"][0]["memory_lookup"]["common_feedback"] == []\n            assert len(report["cells"][0]["records"][1]["memory_lookup"]["common_feedback"]) == 1')
    (HERE/'offline-smoke.py').write_text(smoke,encoding='utf-8')
    print('Prepared corrected study: cumulative budget, common feedback, unchanged comparison suite')


if __name__=='__main__': main()
