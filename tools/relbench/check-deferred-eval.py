#!/usr/bin/env python3
"""Check that test scores computed after a run (harness `evaluate_after_run`, on views of each cutoff's rows) equal the
scores computed right after each session (`--eval-now`, the pilot's setting). Builds a database holding every cutoff's
rows, re-scores the final SQL of every session in the given run folders, and prints both scores side by side.

  PYTHONPATH=.pydeps-relbench python3 tools/relbench/check-deferred-eval.py --out /root/scratch/deferred \
      results/relbench-pilot/none-r1-refit results/relbench-pilot/mavra-r1-refit
"""
import argparse
import glob
import json
import os
import shutil
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", default="results/relbench-data/rel-stack")
    ap.add_argument("--prep", default="results/relbench-data/rel-stack-prep")
    ap.add_argument("--template", default="relbench_stack_t1")
    c = ap.parse_args()
    a = argparse.Namespace(arm="none", run=0, data=c.data, prep=c.prep, template=c.template, out=c.out, tasks=None,
                           cutoffs=None, targets_from=None, reasoning_effort="medium", eval_now=False)
    r = H.Run(a)
    cuts = [x["test_timestamp"] for x in next(iter(r.tasks.values()))["cutoffs"]]
    H.create_run_db(r.url_admin, a.template, r.db_name)
    rows, worst = [], 0.0
    try:
        r.append(pd.Timestamp(cuts[0]), pd.Timestamp(cuts[-1]))
        for run in c.runs:
            sdir = os.path.join(c.out, "sessions")
            shutil.rmtree(sdir, ignore_errors=True)
            os.makedirs(sdir)
            before = {}
            for f in glob.glob(os.path.join(run, "sessions", "*.json")):
                if f.endswith(".partial.json"):
                    continue
                rec = json.load(open(f))
                if not rec.get("final_sql") or "test" not in (rec.get("eval") or {}):
                    continue
                before[os.path.basename(f)] = rec["eval"]["test"]
                rec["eval"] = {"pending": True}
                json.dump(rec, open(os.path.join(sdir, os.path.basename(f)), "w"))
            r.evaluate_after_run(range(1, len(cuts) + 1))
            for name, t0 in sorted(before.items()):
                t1 = json.load(open(os.path.join(sdir, name)))["eval"].get("test")
                d = abs(t1 - t0) if t1 is not None else float("inf")
                worst = max(worst, d)
                rows.append((os.path.basename(run), name, t0, t1, d))
    finally:
        H.drop_db(r.url_admin, r.db_name)
    for row in rows:
        print(f"{row[0]:<18} {row[1]:<26} now={row[2]:.6f} after={row[3]} diff={row[4]:.2e}")
    print(f"{len(rows)} sessions, largest difference {worst:.2e}")


if __name__ == "__main__":
    main()
