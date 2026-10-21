#!/usr/bin/env python3
"""Pilot P2 gate of exp/2026-10-20-relbench/README.md §2: a memory run against the no-memory run with the same draw.

Per session: tokens including learning (charged to the triggering session), LLM calls, tool calls by category, agent
seconds, test score. Gate: from cutoff 2 on, tokens per session <= 1/3 of no memory (total over those sessions), and
the test score not worse (classification AUC within 0.01, regression MAE within 2%), per task averaged over cutoffs.

  python3 tools/relbench/compare-stats.py results/relbench-pilot/none-r1,results/relbench-pilot/none-r1-k45 results/relbench-pilot/mavra-r1
(a comma joins the folders of one run, e.g. a run resumed at a later cutoff)
"""
import collections
import glob
import json
import os
import statistics
import sys


# DeepSeek's price per million tokens, CNY (10-21): input cache hit, input cache miss, output; off-peak and peak
PRICES = {"offpeak": (0.02, 1.0, 4.0), "peak": (0.04, 2.0, 8.0)}


def cost(calls, extra_in, extra_out, prices):
    """Agent calls priced with their cache hits; memory operations (no cache figures) priced as cache misses."""
    hit, miss, out = prices
    c = sum((x.get("cached_tokens") or 0) * hit + (x["input_tokens"] - (x.get("cached_tokens") or 0)) * miss + x["output_tokens"] * out
            for x in calls)
    return (c + extra_in * miss + extra_out * out) / 1e6


def load(runs):
    out = {}
    files = [f for run in runs.split(",") for f in glob.glob(os.path.join(run, "sessions", "*.json")) if not f.endswith(".partial.json")]
    for f in files:
        s = json.load(open(f))
        tot = s["totals"]
        lr = s.get("learning") or {}
        calls = (s.get("llm") or []) + (s.get("llm_sub") or [])
        out[(s["task"], s["k"])] = {
            "cost": {name: cost(calls, lr.get("input_tokens", 0), lr.get("output_tokens", 0), pr) for name, pr in PRICES.items()},
            "goal": s.get("target"), "goal_why": (s.get("target_detail") or {}).get("why"), "goal_reached": bool(s.get("goal_reached")),
            "eval_error": (s.get("eval") or {}).get("error"), "learn_error": lr.get("error"),
            "retry_s": tot.get("llm_retry_seconds", 0),
            "tokens": tot.get("tokens_with_learning", tot["tokens"]), "agent_tokens": tot["tokens"],
            "learn_tokens": tot.get("learn_tokens", 0), "llm": tot["llm_calls"], "tools": tot["tool_calls"],
            # agent time without the leak audit (evaluation machinery; older runs counted it in agent_seconds)
            "by_cat": tot["tool_calls_by_category"],
            "agent_s": s["agent_seconds"] - (0 if "audit_seconds" in s else sum(v.get("audit_seconds", 0) for v in s["validations"])),
            "llm_s": tot["llm_seconds"],
            "test": (s.get("eval") or {}).get("test"), "val": s.get("best_val"), "higher": s["higher_is_better"],
            "audit": (s.get("audit") or {}).get("result"), "stop": s["stop"],
            "published": sum(1 for e in ((s.get("learning") or {}).get("events") or []) if e.get("event") in ("promoted", "corroborated")),
        }
    return out


def main():
    base, other = load(sys.argv[1]), load(sys.argv[2])
    keys = sorted(set(base) & set(other), key=lambda x: (x[1], x[0]))
    print(f"{'task':16} {'k':>2} | {'tok none':>9} {'tok mem':>9} {'x':>5} | {'llm':>7} | {'tools':>7} | {'sec':>11} | {'test none':>9} {'test mem':>9} | pub")
    for k in keys:
        a, b = base[k], other[k]
        x = a["tokens"] / b["tokens"] if b["tokens"] else float("inf")
        f = lambda v: f"{v:.4f}" if isinstance(v, float) else str(v)
        print(f"{k[0]:16} {k[1]:>2} | {a['tokens']:>9} {b['tokens']:>9} {x:>5.1f} | {a['llm']:>3}/{b['llm']:<3} | {a['tools']:>3}/{b['tools']:<3} | "
              f"{a['agent_s']:>5.0f}/{b['agent_s']:<5.0f} | {f(a['test']):>9} {f(b['test']):>9} | {b['published']}")
    late = [k for k in keys if k[1] >= 2]
    ta, tb = sum(base[k]["tokens"] for k in late), sum(other[k]["tokens"] for k in late)
    quality = {}
    for task in sorted({k[0] for k in keys}):
        ks = [k for k in keys if k[0] == task and base[k]["test"] is not None and other[k]["test"] is not None]
        if not ks:
            continue
        ma, mb = statistics.mean(base[k]["test"] for k in ks), statistics.mean(other[k]["test"] for k in ks)
        higher = base[ks[0]]["higher"]
        ok = mb >= ma - 0.01 if higher else mb <= ma * 1.02
        quality[task] = {"none": round(ma, 4), "memory": round(mb, 4), "not_worse": ok}
    gate = {
        "late_sessions": len(late), "late_tokens_none": ta, "late_tokens_memory": tb,
        "late_token_ratio": round(tb / ta, 3) if ta else None, "tokens_pass": bool(ta) and tb <= ta / 3,
        "llm_calls_late": [sum(base[k]["llm"] for k in late), sum(other[k]["llm"] for k in late)],
        "tool_calls_late": [sum(base[k]["tools"] for k in late), sum(other[k]["tools"] for k in late)],
        "agent_seconds_late": [round(sum(base[k]["agent_s"] for k in late)), round(sum(other[k]["agent_s"] for k in late))],
        "quality": quality, "quality_pass": all(q["not_worse"] for q in quality.values()) if quality else False,
        "leaks_memory": sum(1 for k in keys if other[k]["audit"] == "leak"),
    }
    gate["cost_cny_late"] = {name: [round(sum(base[k]["cost"][name] for k in late), 2), round(sum(other[k]["cost"][name] for k in late), 2)]
                             for name in PRICES}
    # what to check before trusting the numbers: sessions cut short, goals missing, scores missing, memory errors
    health = {}
    for label, d in (("none", base), ("memory", other)):
        health[label] = {
            "stops": dict(collections.Counter(d[k]["stop"] for k in keys)),
            "goal_reached": sum(1 for k in late if d[k]["goal_reached"]),
            "no_goal": {f"{k[0]} k{k[1]}": d[k]["goal_why"] for k in late if d[k]["goal"] is None},
            "missing_test": [f"{k[0]} k{k[1]}" for k in keys if d[k]["test"] is None],
            "eval_errors": {f"{k[0]} k{k[1]}": d[k]["eval_error"][:120] for k in keys if d[k]["eval_error"]},
            "learn_errors": {f"{k[0]} k{k[1]}": str(d[k]["learn_error"])[:120] for k in keys if d[k]["learn_error"]},
            "gateway_retry_seconds": round(sum(d[k]["retry_s"] for k in keys)),
        }
    gate["health"] = health
    print(json.dumps(gate, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
