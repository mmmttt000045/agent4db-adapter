#!/usr/bin/env python3
"""Main-table numbers of exp/2026-10-20-relbench/README.md §1.4 for several arms on one database and run: per arm, the
totals over the cutoffs from 2 on and over all cutoffs (tokens with memory operations, LLM calls, tool calls, agent
seconds, cost at DeepSeek's prices), the test score per task averaged over cutoffs, and a health line (sessions cut
short, goals missing, scores missing). Sessions are paired by (task, cutoff); only pairs every arm finished count.

  python3 tools/relbench/arm-table.py none=results/relbench-pilot3/none-rel-stack-r1 mavra=results/relbench-pilot3/mavra-rel-stack-r1 \
      agentsm=results/relbench-pilot3/agentsm-rel-stack-r1 ace=results/relbench-pilot3/ace-rel-stack-r1 gmemory=...
"""
import collections
import importlib.util
import json
import os
import statistics
import sys

spec = importlib.util.spec_from_file_location("compare_stats", os.path.join(os.path.dirname(os.path.abspath(__file__)), "compare-stats.py"))
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def main():
    arms = [a.split("=", 1) for a in sys.argv[1:]]
    data = {name: cs.load(path) for name, path in arms}
    keys = sorted(set.intersection(*(set(d) for d in data.values())), key=lambda x: (x[1], x[0]))
    late = [k for k in keys if k[1] >= 2]
    base = arms[0][0]
    tasks = sorted({k[0] for k in keys})
    rows = {}
    for name, d in data.items():
        def tot(field, ks):
            return sum(d[k][field] for k in ks)
        row = {
            "sessions": len(keys),
            "tokens_late": tot("tokens", late), "tokens_all": tot("tokens", keys),
            "llm_late": tot("llm", late), "tools_late": tot("tools", late),
            "agent_s_late": round(tot("agent_s", late)), "agent_s_all": round(tot("agent_s", keys)),
            "cost_late_offpeak": round(sum(d[k]["cost"]["offpeak"] for k in late), 2),
            "cost_all_offpeak": round(sum(d[k]["cost"]["offpeak"] for k in keys), 2),
            "test": {},
            "health": {
                "stops": dict(collections.Counter(d[k]["stop"] for k in keys)),
                "goal_reached_late": sum(1 for k in late if d[k]["goal_reached"]),
                "no_goal_late": sum(1 for k in late if d[k]["goal"] is None),
                "missing_test": sum(1 for k in keys if d[k]["test"] is None),
                "learn_errors": sum(1 for k in keys if d[k]["learn_error"]),
                "sql_timeouts": sum(d[k]["sql_timeouts"] for k in keys),
            },
        }
        for t in tasks:
            ks = [k for k in keys if k[0] == t and all(data[n][k]["test"] is not None for n in data)]
            if ks:
                row["test"][t] = round(statistics.mean(d[k]["test"] for k in ks), 4)
        rows[name] = row
    b = rows[base]
    print(f"{len(keys)} paired sessions ({len(late)} from cutoff 2); ratios against {base}")
    print(f"{'arm':10} {'tokens k2+':>11} {'x':>5} {'LLM':>5} {'tools':>6} {'agent s':>8} {'x faster':>8} {'CNY k2+':>8} | test " + " ".join(f"{t:>16}" for t in tasks))
    for name, r in rows.items():
        x = r["tokens_late"] / b["tokens_late"] if b["tokens_late"] else float("nan")
        sp = b["agent_s_late"] / r["agent_s_late"] if r["agent_s_late"] else float("nan")
        print(f"{name:10} {r['tokens_late']:>11} {x:>5.2f} {r['llm_late']:>5} {r['tools_late']:>6} {r['agent_s_late']:>8} {sp:>8.2f} {r['cost_late_offpeak']:>8} | "
              + " ".join(f"{r['test'].get(t, float('nan')):>16.4f}" for t in tasks))
    print(json.dumps(rows, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
