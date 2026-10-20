#!/usr/bin/env python3
"""Pilot P2 gate of exp/2026-10-20-relbench/README.md §2: a memory run against the no-memory run with the same draw.

Per session: tokens including learning (charged to the triggering session), LLM calls, tool calls by category, agent
seconds, test score. Gate: from cutoff 2 on, tokens per session <= 1/3 of no memory (total over those sessions), and
the test score not worse (classification AUC within 0.01, regression MAE within 2%), per task averaged over cutoffs.

  python3 tools/relbench/compare-stats.py results/relbench-pilot/none-r1 results/relbench-pilot/mavra-r1
"""
import glob
import json
import os
import statistics
import sys


def load(run):
    out = {}
    for f in glob.glob(os.path.join(run, "sessions", "*.json")):
        s = json.load(open(f))
        tot = s["totals"]
        out[(s["task"], s["k"])] = {
            "tokens": tot.get("tokens_with_learning", tot["tokens"]), "agent_tokens": tot["tokens"],
            "learn_tokens": tot.get("learn_tokens", 0), "llm": tot["llm_calls"], "tools": tot["tool_calls"],
            "by_cat": tot["tool_calls_by_category"], "agent_s": s["agent_seconds"], "llm_s": tot["llm_seconds"],
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
    print(json.dumps(gate, indent=1))


if __name__ == "__main__":
    main()
