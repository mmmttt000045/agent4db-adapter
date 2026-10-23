#!/usr/bin/env python3
"""Inventory saved RelBench traces for a future isolated timing replay.

Read-only: no database or model calls. Records exact source hashes and event
locations, including unsupported operations; this is not a timing measurement.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paper_stats", HERE / "paper-stats.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    sessions, failures, totals = [], [], Counter()
    for database, (_, pattern) in P.RUNS.items():
        for arm, _, _ in P.ARMS:
            root = Path(pattern.format(arm=arm))
            if not P.finished(root):
                raise ValueError(f"Incomplete run: {root}")
            run_path = root / "run.json"
            run = json.loads(run_path.read_text())
            for cut in run["cutoffs"]:
                for task in cut["order"]:
                    path = root / "sessions" / f"{task.replace('-', '_')}-k{cut['k']}.json"
                    s = json.loads(path.read_text())
                    assert (s["task"], s["k"], s["arm"]) == (task, cut["k"], arm)
                    events = []
                    for i, tool in enumerate(s["tools"]):
                        sql = (tool.get("args") or {}).get("sql")
                        kind = tool["name"]
                        supported = bool(sql) and kind in ("run_sql", "validate_features")
                        event = {"tool_index": i, "kind": kind, "has_sql": bool(sql),
                                 "sql_validation_replay_candidate": supported,
                                 "original_error": tool.get("error", False)}
                        if supported:
                            event["sql_sha256"] = hashlib.sha256(sql.encode()).hexdigest()
                        else:
                            event["required_adapter"] = (
                                "official DeepPrep operator executor" if arm == "deepprep" else
                                "FeatPilot search trace" if arm == "featpilot" else
                                "MAVRA tool state or schema/metadata operation")
                        events.append(event)
                        totals["tool_events"] += 1
                        totals["sql_validation_candidates"] += int(supported)
                    totals["sessions"] += 1
                    totals["recorded_agent_llm_calls"] += s["totals"]["llm_calls"]
                    totals["validation_records"] += len(s["validations"])
                    totals["scored_validation_records"] += sum("val" in v for v in s["validations"])
                    sessions.append({"database": database, "arm": arm, "task": task, "cutoff": cut["k"],
                                     "source": str(path), "sha256": digest(path),
                                     "run_source": str(run_path), "run_sha256": digest(run_path),
                                     "events": events,
                                     "recorded_agent_llm_seconds": s["totals"].get("llm_seconds"),
                                     "llm_latency_is_shared_host_observation": True,
                                     "final_program_available": bool(s.get("final_sql")),
                                     "final_program_kind": "operator_pipeline" if arm == "deepprep" else "sql"})
                    if arm == "deepprep" and s.get("stop") in ("solution_timeout", "no_solution"):
                        failures.append({"database": database, "task": task, "cutoff": cut["k"],
                                         "source": str(path), "stop": s.get("stop"), "error": s.get("error")})
    assert totals["sessions"] == 210, totals
    return {
        "status": "prepared_not_executed", "totals": dict(totals),
        "scope": "Inventory for component replay; no isolated or end-to-end timing results.",
        "protocol": [
            "Reserve an exclusive PostgreSQL host and compute host; record CPU, memory, storage, software versions and competing processes.",
            "Clone the original cutoff-1 database template for each arm; use the archived timeline, seed samples and append order.",
            "Use run.json cutoff/task order and each session's event order; preserve failed attempts, 600-second feature limits, learner settings and audits.",
            "Replay query/validation candidates with the original executor; adapt metadata, shared memory, DeepPrep operators and FeatPilot search before claiming full coverage.",
            "Measure SQL, feature checks, LightGBM, leakage audits, memory maintenance and setup separately; retain every timeout/error.",
            "Choose and disclose a cache policy; rotate method order and repeat complete replays to estimate variability.",
            "Model-service latency needs separate controlled measurement with identical requests, model settings and cache accounting; saved latencies remain observational.",
            "Report component replay as such. Summing replay components and API estimates is a reconstructed estimate, not a measured end-to-end speedup."
        ],
        "deepprep_failures": failures, "sessions": sessions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = inventory()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": plan["status"], **plan["totals"],
                      "deepprep_failures": len(plan["deepprep_failures"])}, indent=2))


if __name__ == "__main__":
    main()
