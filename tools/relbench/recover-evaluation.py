#!/usr/bin/env python3
"""Retry failed deferred evaluation of audited SQL, without rerunning an agent.

Preserves original records in --out/before; only successful scores are copied back.
The original model, SQL, seeds, and 600-second SQL limit remain in effect.
"""
import argparse
import json
import math
from pathlib import Path
import shutil

import pandas as pd
import harness as H


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--prep", required=True)
    parser.add_argument("--template", required=True)
    args = parser.parse_args()
    records = []
    for path in sorted((args.run / "sessions").glob("*.json")):
        if path.name.endswith(".partial.json"):
            continue
        record = json.loads(path.read_text())
        evaluation = record.get("eval") or {}
        if (record.get("final_sql") and (record.get("audit") or {}).get("result") == "clean"
                and evaluation.get("after_run") and evaluation.get("error") and evaluation.get("test") is None):
            records.append((path, record))
    if not records:
        print("No failed deferred evaluations to recover.")
        return
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "before").mkdir()
    settings = json.loads((args.run / "run.json").read_text())["settings"]
    config = argparse.Namespace(arm="none", run=0, data=args.data, prep=args.prep, template=args.template,
                               out=str(args.out), tasks=None, cutoffs=None, targets_from=None,
                               reasoning_effort=settings["reasoning_effort"], eval_now=False, llm=settings["llm"])
    run = H.Run(config)
    for path, record in records:
        shutil.copy2(path, args.out / "before" / path.name)
        pending = {**record, "eval": {"pending": True}}
        (args.out / "sessions" / path.name).write_text(json.dumps(pending, ensure_ascii=False, indent=1))
    cuts = [c["test_timestamp"] for c in next(iter(run.tasks.values()))["cutoffs"]]
    H.create_run_db(run.url_admin, args.template, run.db_name)
    try:
        run.append(pd.Timestamp(cuts[0]), pd.Timestamp(cuts[-1]))
        run.evaluate_after_run(sorted({r["k"] for _, r in records}))
    finally:
        H.drop_db(run.url_admin, run.db_name)
    recovered = []
    for path, original in records:
        updated = json.loads((args.out / "sessions" / path.name).read_text())
        score = updated["eval"].get("test")
        if score is None or not math.isfinite(score):
            print("Still failed:", path.name, updated["eval"])
            continue
        if json.loads(path.read_text()) != original:
            raise RuntimeError(f"Record changed during recovery: {path}")
        updated["evaluation_recovery"] = {"original": str(args.out / "before" / path.name),
                                          "reason": "retry failed deferred scoring; agent and SQL unchanged"}
        temp = path.with_suffix(".recovery-tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=1))
        temp.replace(path)
        recovered.append({"session": path.name, "test": score})
    (args.out / "recovered.json").write_text(json.dumps(recovered, indent=2))
    print("Recovered:", recovered)
    if len(recovered) != len(records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
