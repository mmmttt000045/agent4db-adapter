#!/usr/bin/env python3
"""Re-run the leakage audit of tools/relbench/harness.py for sessions whose audit did not run (result "unauditable" or
"error" before 4e04d5b, when tables named public.x were not redirected to the audit views).

A fresh copy of the template gets every row up to the last cutoff, then for each affected cutoff the seed tables are
rebuilt and the submitted SQL is audited. Features computed on more data than the session saw can only make a leak
easier to detect: a clean SQL gives the same values for the latest training seeds whatever comes later.

  python3 tools/relbench/reaudit.py --run results/relbench-pilot/none-r1 --data ... --prep ... --template relbench_stack_t1
"""
import argparse
import glob
import json
import os

import pandas as pd

import harness


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--prep", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--llm", default="deepseek", help="provider whose key the harness loads (no model call is made)")
    a = ap.parse_args()
    todo = []
    for f in sorted(glob.glob(os.path.join(a.run, "sessions", "*.json"))):
        s = json.load(open(f))
        if s.get("final_sql") and (s.get("audit") or {}).get("result") in ("unauditable", "error", None):
            todo.append((f, s))
    if not todo:
        print("nothing to re-audit")
        return
    first = json.load(open(todo[0][0]))
    ns = argparse.Namespace(arm=first["arm"], run=first["run"], data=a.data, prep=a.prep, template=a.template,
                            out=os.path.join(a.run, "reaudit"), tasks=None, cutoffs=None, parallel=1, port=None, keep_db=False, smoke=False,
                            targets_from=None, llm=a.llm, reasoning_effort=None, eval_now=True)
    os.makedirs(ns.out, exist_ok=True)
    r = harness.Run(ns)
    harness.create_run_db(r.url_admin, a.template, r.db_name)
    try:
        any_task = next(iter(r.tasks.values()))
        r.append(pd.Timestamp(any_task["cutoffs"][0]["test_timestamp"]), pd.Timestamp(any_task["cutoffs"][-1]["test_timestamp"]))
        for k in sorted({s["k"] for _, s in todo}):
            seeds = r.seed_tables(k)
            for f, s in todo:
                if s["k"] != k:
                    continue
                res = r.audit(s["task"], k, s["final_sql"], seeds[s["task"]])
                res.update(reaudited=True, db_upto=any_task["cutoffs"][-1]["test_timestamp"], previous=s.get("audit"))
                s["audit"] = res
                json.dump(s, open(f, "w"), ensure_ascii=False, indent=1, default=str)
                print(f"{s['task']} k{k}: {res['result']} {res.get('columns_differing', '')}")
    finally:
        harness.drop_db(r.url_admin, r.db_name)


if __name__ == "__main__":
    main()
