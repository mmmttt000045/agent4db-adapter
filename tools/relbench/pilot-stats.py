#!/usr/bin/env python3
"""Pilot P1 gates of exp/2026-10-20-relbench/README.md §2 from one run directory of tools/relbench/harness.py.

(a) sessions that ended normally (submitted, patience, validation budget, LLM budget) and produced a test score;
(b) median LLM calls per session; (c) share of schema + probe calls among tool calls; (d) sessions whose best
validation score beats the entity-table reference; (e) in sessions after the first, the share of schema calls
(same tool, same arguments) already made in an earlier session on the same database (order: cutoff, then arrival).

  python3 tools/relbench/pilot-stats.py results/relbench-pilot/none-r1 [--json out.json]
"""
import argparse
import glob
import json
import os
import statistics

NORMAL = {"submitted", "patience", "validation_budget", "llm_budget"}


def key(t):
    a = t.get("args") or {}
    if t["name"] in ("join_path", "check_join"):
        pair = sorted([str(a.get("table_a", a.get("left", ""))).lower(), str(a.get("table_b", a.get("right", ""))).lower()])
        extra = json.dumps(a.get("on"), sort_keys=True) if t["name"] == "check_join" else ""
        return (t["name"], *pair, extra)
    return (t["name"], json.dumps({k: str(v).lower() for k, v in a.items()}, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--json")
    a = ap.parse_args()
    run = json.load(open(os.path.join(a.run, "run.json")))
    order = {(t, c["k"]): i for c in run["cutoffs"] for i, t in enumerate(c["order"])}
    ref = {(t, c["k"]): v for c in run["cutoffs"] for t, v in c["reference"].items()}
    sess = [json.load(open(f)) for f in glob.glob(os.path.join(a.run, "sessions", "*.json"))]
    sess.sort(key=lambda s: (s["k"], order.get((s["task"], s["k"]), 0)))

    rows, seen, rep_num, rep_den = [], set(), 0, 0
    for i, s in enumerate(sess):
        tot = s["totals"]
        schema = [key(t) for t in s["tools"] if t.get("category") == "schema"]
        if i > 0:
            rep_den += len(schema)
            rep_num += sum(1 for k in schema if k in seen)
        seen.update(schema)
        r = ref.get((s["task"], s["k"])) or {}
        higher = s["higher_is_better"]
        best, rval = s.get("best_val"), r.get("val")
        beats = None if best is None or rval is None else (best > rval if higher else best < rval)
        ev = s.get("eval") or {}
        rows.append({
            "task": s["task"], "k": s["k"], "stop": s["stop"], "llm": tot["llm_calls"], "tools": tot["tool_calls"],
            "by_cat": tot["tool_calls_by_category"], "tokens": tot["tokens"], "agent_s": round(s["agent_seconds"], 1),
            "llm_s": round(tot["llm_seconds"], 1), "val_sql_s": round(tot["validation_sql_seconds"], 1),
            "train_s": round(tot["validation_train_seconds"], 1), "validations": len(s["validations"]),
            "best_val": best, "ref_val": rval, "beats_ref": beats, "test": ev.get("test"), "ref_test": r.get("test"),
            "audit": (s.get("audit") or {}).get("result"), "normal": s["stop"] in NORMAL and ev.get("test") is not None,
        })

    n = len(rows)
    tool_total = sum(r["tools"] for r in rows)
    sp = sum(r["by_cat"].get("schema", 0) + r["by_cat"].get("probe", 0) for r in rows)
    beats = [r["beats_ref"] for r in rows if r["beats_ref"] is not None]
    gates = {
        "a_normal": f"{sum(r['normal'] for r in rows)}/{n}", "a_pass": sum(r["normal"] for r in rows) >= 13,
        "b_median_llm_calls": statistics.median(r["llm"] for r in rows) if rows else None,
        "c_schema_probe_share": round(sp / tool_total, 3) if tool_total else None,
        "d_beats_reference": f"{sum(beats)}/{len(beats)}",
        "e_schema_repeat_share": round(rep_num / rep_den, 3) if rep_den else None,
    }
    gates["b_pass"] = gates["b_median_llm_calls"] is not None and gates["b_median_llm_calls"] >= 15
    gates["c_pass"] = gates["c_schema_probe_share"] is not None and gates["c_schema_probe_share"] >= 0.30
    gates["d_pass"] = bool(beats) and sum(beats) >= 2 * len(beats) / 3
    gates["e_pass"] = gates["e_schema_repeat_share"] is not None and gates["e_schema_repeat_share"] >= 0.50
    cost = {
        "tokens_per_session_median": statistics.median(r["tokens"] for r in rows) if rows else None,
        "tokens_total": sum(r["tokens"] for r in rows),
        "agent_seconds_median": statistics.median(r["agent_s"] for r in rows) if rows else None,
        "leaks": sum(r["audit"] == "leak" for r in rows),
    }
    print(f"{'task':16} {'k':>2} {'stop':18} {'llm':>4} {'tools':>5} {'sch':>4} {'prb':>4} {'val':>4} {'tokens':>8} {'agent_s':>8} "
          f"{'best_val':>9} {'ref_val':>8} {'test':>8} {'ref_test':>8} audit")
    for r in rows:
        f = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)
        print(f"{r['task']:16} {r['k']:>2} {str(r['stop']):18} {r['llm']:>4} {r['tools']:>5} {r['by_cat'].get('schema', 0):>4} "
              f"{r['by_cat'].get('probe', 0):>4} {r['validations']:>4} {r['tokens']:>8} {r['agent_s']:>8} {f(r['best_val']):>9} "
              f"{f(r['ref_val']):>8} {f(r['test']):>8} {f(r['ref_test']):>8} {r['audit']}")
    print(json.dumps({"gates": gates, "cost": cost}, indent=1))
    if a.json:
        json.dump({"gates": gates, "cost": cost, "sessions": rows}, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
