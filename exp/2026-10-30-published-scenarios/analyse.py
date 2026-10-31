#!/usr/bin/env python3
"""Verify complete matched blocks and aggregate Fig.6 without selecting outcomes."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PHASES = {
    "holdout": ["holdout"],
    "benign": ["append", "backfill", "correct", "addcol"],
    "modeled": ["status", "revision", "dupload", "dimhist", "latekey"],
    "all": ["holdout", "append", "backfill", "correct", "addcol", "status", "revision", "dupload", "dimhist", "latekey", "unit", "mirror"],
}
ARMS = ["ace", "awm", "gmemory", "mavra"]
NAMES = {"ace": "ACE", "awm": "AWM", "gmemory": "G-Memory", "mavra": "MAVRA"}


def cost(row):
    # Exact published time bands; billed currency can be reconciled separately.
    when = datetime.fromisoformat(row["utc"]).astimezone(timezone(timedelta(hours=8)))
    peak = when.weekday() < 5 and (9 <= when.hour < 12 or 14 <= when.hour < 18)
    rates = (.04, 2., 8.) if peak else (.02, 1., 4.)
    u = row.get("usage") or {}
    if not u:
        return row["ceiling_cny"]  # retain unknown usage conservatively
    n = int(u.get("prompt_tokens", 0))
    hit = int(u.get("prompt_cache_hit_tokens", (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)))
    assert 0 <= hit <= n
    return (hit * rates[0] + (n - hit) * rates[1] + int(u.get("completion_tokens", 0)) * rates[2]) / 1e6


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--out", type=Path, default=HERE)
    a = p.parse_args()
    cfg = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    state = json.loads((a.results / "execution-state.json").read_text(encoding="utf-8"))
    repeats = state["complete_repeats"]
    assert repeats and len(repeats) == len(set(repeats))
    manifest = json.loads((a.results / "frozen-source-manifest.json").read_text(encoding="utf-8"))
    cfg_path = "exp/2026-10-30-published-scenarios/protocol.json"
    assert hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest() == manifest[cfg_path]
    rows = [json.loads(line) for line in (a.results / "budget/api-usage.jsonl").read_text(encoding="utf-8").splitlines() if line]
    completed_keys = {c["key"] for c in state["cells"] if c["completed"] and c["repeat"] in repeats}
    profiles = {"awm": 0, "gmemory": 0}
    with (a.results / "budget/api-transcripts.jsonl").open(encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            if event["arm"] not in completed_keys:
                continue
            q = event["request"]
            assert q["model"] == cfg["model"] and 0 < q["max_tokens"] <= cfg["max_output_tokens"]
            if not q.get("tools"):
                arm = "gmemory" if "-gmemory" in event["arm"] else "awm" if "-awm" in event["arm"] else None
                if arm:
                    assert q["thinking"] == {"type": "disabled"}, (event["call"], event["arm"])
                    assert q["max_tokens"] == (512 if arm == "gmemory" else 2048)
                    profiles[arm] += 1
    assert all(profiles.values())
    budget = json.loads((a.results / "budget/budget-state.json").read_text(encoding="utf-8"))
    assert len(rows) == budget["calls"]
    assert abs(sum(r["ceiling_cny"] for r in rows) - budget["ceiling_cny"]) < 1e-6
    assert budget["ceiling_cny"] + budget["reserved_cny"] <= cfg["budget_cny"] + 1e-9
    assert budget["reserved_cny"] < 1e-8
    close_path = a.results / "financial-close.json"
    financial_close = json.loads(close_path.read_text(encoding="utf-8")) if close_path.exists() else None
    observed_decrease = budget.get("observed_account_decrease_cny")
    if financial_close:
        assert state["status"] == "complete" and financial_close["status"] == "closed_no_more_model_calls"
        assert financial_close["requests"] == len(rows)
        assert abs(financial_close["peak_price_upper_cny"] - budget["ceiling_cny"]) < 1e-8
        observed_decrease = financial_close["account_decrease_cny"]
        assert 0 <= observed_decrease <= cfg["budget_cny"]
    data = {"study": cfg["study"], "study_status": state["status"], "complete_repeats": repeats, "protocol_sha256": manifest[cfg_path],
            "aggregation": "Equal weight per setting, then equal weight per complete paired repeat; ranges are observed runs, not confidence intervals.",
            "groups": PHASES, "datasets": {}, "cost": {
                "authorization_cny": cfg["budget_cny"], "upper_cny": budget["ceiling_cny"],
                "priced_usage_cny": sum(cost(r) for r in rows),
                "account_decrease_observed_cny": observed_decrease,
                "requests": len(rows), "http_errors": sum(r["status"] != 200 for r in rows),
                "models": budget["models"], "includes": "all requests, memory, extraction, optimization, retries and incomplete attempts"},
            "incomplete_attempts": [c["key"] for c in state["cells"] if c["repeat"] not in repeats or not c["completed"]]}
    data["verified_memory_profiles"] = profiles
    macros = []
    md = ["# Fig. 6: published-memory comparison", "", "This is the newly budgeted single-period cohort. Only complete matched repeats enter accuracy; every paid attempt enters spending.", "",
          f"Complete matched repeats: {len(repeats)}. Observed ranges are not confidence intervals.", "",
          "| Dataset | Method | Held out | Non-breaking | Covered breaks | All settings |", "|---|---|---:|---:|---:|---:|"]
    for ds, prefix in (("synthetic", "PubSynth"), ("tpch", "PubTpch")):
        dataset = {"arms": {}}
        for arm in ARMS:
            runs = []
            for rep in repeats:
                cell = [c for c in state["cells"] if c["dataset"] == ds and c["arm"] == arm and c["repeat"] == rep and c["completed"]]
                assert len(cell) == 1 and cell[0]["completed"]
                if cell[0].get("source_manifest"):
                    per_cell_source = json.loads((a.results / cell[0]["source_manifest"]).read_text(encoding="utf-8"))
                    assert all(per_cell_source[k] == v for k,v in manifest.items() if k.startswith(("src/", "third_party/", "gmemory-core/")) or k == "target/release/agentdb-mid")
                directory = a.results / "cells" / cell[0]["key"]
                files = list(directory.glob("metric-*/report.json"))
                assert len(files) == 1
                f = files[0]
                assert hashlib.sha256(f.read_bytes()).hexdigest() == cell[0]["report_sha256"]
                report = json.loads(f.read_text(encoding="utf-8"))
                assert len(report["cells"]) == 1 and report["cells"][0]["mode"] == cfg["modes"][arm]
                assert report["options"]["metrics"] == cfg["metrics"] and report["options"]["holdout_agents"] == ["A"]
                assert report["options"]["concurrency"] == 1
                records = report["cells"][0]["records"]
                assert len(records) == cfg["expected_tasks_per_cell"][ds]
                assert all(r["ask"]["kind"] == "single" for r in records)
                assert all(r["outcome"] in ("correct", "wrong", "error", "clarify") for r in records)
                phases = {}
                for phase in ["learn"] + PHASES["all"]:
                    rs = [r for r in records if r["phase"] == phase]
                    assert rs and len({(r["agent"], r["task"]) for r in rs}) == len(rs)
                    phases[phase] = {"correct": sum(r["outcome"] == "correct" for r in rs), "n": len(rs),
                                     "outcomes": {k: sum(r["outcome"] == k for r in rs) for k in ("correct", "wrong", "error", "clarify")}}
                tagged = [r for r in rows if r["arm"] == cell[0]["key"]]
                assert tagged and all(r["model"] == cfg["required_reported_model"] for r in tagged if r["status"] == 200)
                runs.append({"repeat": rep, "phases": phases, "requests": len(tagged),
                             "cell_seconds": report["cells"][0]["seconds"],
                             "priced_usage_cny": sum(cost(r) for r in tagged)})
            groups = {}
            for group, phases in PHASES.items():
                values = [100 * sum(run["phases"][p]["correct"] / run["phases"][p]["n"] for p in phases) / len(phases) for run in runs]
                groups[group] = {"accuracy_pct": sum(values) / len(values), "run_values_pct": values,
                                 "range_pct": [min(values), max(values)]}
                macros.append(f"\\newcommand{{\\{prefix}{NAMES[arm].replace('-', '')}{group.capitalize()}}}{{{groups[group]['accuracy_pct']:.1f}}}")
            dataset["arms"][arm] = {"runs": runs, "groups": groups}
            md.append("| " + " | ".join([ds, NAMES[arm]] + [f"{groups[g]['accuracy_pct']:.1f}%" for g in PHASES]) + " |")
        data["datasets"][ds] = dataset
    macros.append(f"\\newcommand{{\\PubScenarioRepeats}}{{{len(repeats)}}}")
    n_scored = len(repeats) * len(ARMS) * sum(cfg["expected_scored_tasks_per_cell"].values())
    data["scored_tasks"] = n_scored
    data["learning_tasks"] = len(repeats) * len(ARMS) * len(cfg["datasets"]) * 6
    macros.append(f"\\newcommand{{\\PubScenarioScored}}{{{n_scored}}}")
    md += ["", f"Priced usage (including every attempt): CNY {data['cost']['priced_usage_cny']:.4f}. Conservative peak-price ceiling: CNY {data['cost']['upper_cny']:.4f}; authorization: CNY 20.",
           f"Observed account decrease at final close: CNY {observed_decrease:.2f}. Total API requests: {len(rows)}; HTTP errors: {data['cost']['http_errors']}." if financial_close else "Financial close is pending.",
           "", "The cohort fixes M1/M3/M5, two learning questions per metric, one scored period per setting, and eleven independent changes on synthetic retail and TPC-H SF1. ACE/AWM are SQL adaptations of released components; G-Memory uses the unchanged official core. Post-task binary correctness, without gold answers/SQL, feeds published memory updates. Full MAVRA retains its native checked publication, maintenance, optimization and snapshot execution."]
    for ds in ("synthetic", "tpch"):
        md += ["", f"## {ds}: every setting", "", "Counts are correct/scored over complete matched repeats.", "",
               "| Setting | ACE | AWM | G-Memory | MAVRA |", "|---|---:|---:|---:|---:|"]
        for phase in PHASES["all"]:
            counts = []
            for arm in ARMS:
                runs = data["datasets"][ds]["arms"][arm]["runs"]
                k = sum(run["phases"][phase]["correct"] for run in runs)
                n = sum(run["phases"][phase]["n"] for run in runs)
                counts.append(f"{k}/{n}")
            md.append("| " + " | ".join([phase] + counts) + " |")
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "study-stats.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (a.out / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (a.out / "overleaf-numbers.tex").write_text("% Generated by analyse.py; complete matched repeats only.\n" + "\n".join(macros) + "\n", encoding="utf-8")
    print("\n".join(md[4:17]))


if __name__ == "__main__":
    main()
