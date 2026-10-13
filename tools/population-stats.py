#!/usr/bin/env python3
"""Population study statistics (metric-bench --population): agents arrive one after another on one database, the
memory starts empty and learns from use.

usage: population-stats.py --runs results/pop-20261012 [--json-out FILE] [--tex-out overleaf/gen]

Methods: no memory (middle-alone: table profiles, join paths and query results kept per question), single-agent memory
(metric-private: same learning, checks and maintenance as MAVRA, but each agent sees only the definitions and schema
knowledge it learned itself), example retrieval (traj-global, shared), MAVRA (metric-global-snap).

Cost of a task: tokens = the agent session's tokens (input + output) plus, when the memory learned from that session,
the extraction's tokens (learning is charged to the session that triggered it); seconds = the agent session's wall time
from the first call to the final answer, i.e. what the user waits for. Learning runs after the answer, so its seconds
(extraction and publication checks) are reported separately as background work. Provider failures (outcome "error")
are not scored and add no cost.

Per method and run, on the unchanged data (phase pop-v1): cost and correct answers per agent in arrival order, and the
cumulative cost of the first N agents. After the change (phase pop-<change>, the same agents return): accuracy, cost per
task, stale executions (a declared use of a definition the audit found wrong on that snapshot) and maintenance database
time. Values are means over runs with the per-run range.
"""
import argparse
import collections
import glob
import json
import os
import statistics

METHODS = ["middle-alone", "metric-private", "traj-global", "metric-global-snap"]
NAMES = {"middle-alone": "No memory", "metric-private": "Single-agent memory", "traj-global": "Example retrieval (shared)",
         "metric-global-snap": "MAVRA"}
KEY = {"middle-alone": "None", "metric-private": "Private", "traj-global": "Traj", "metric-global-snap": "Mavra"}
STEPS = [1, 2, 4, 8, 16]


def load(root):
    cells = []
    for f in sorted(glob.glob(os.path.join(root, "**", "cell-pop-*.json"), recursive=True)):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("population"):
            cells.append(d)
    return cells


def cost(r):
    tok = r["run"]["input_tokens"] + r["run"]["output_tokens"]
    s = r["run"]["seconds"]
    l = r.get("learning") or {}
    ex = l.get("extraction") or {}
    ltok = ex.get("input_tokens", 0) + ex.get("output_tokens", 0)
    ls = ex.get("seconds", 0) + l.get("gate_seconds", 0)
    return tok + ltok, s, ltok, ls


def agent_index(r):
    return int(r["agent"][1:])


def cell_stats(d):
    v1 = [r for r in d["records"] if r["phase"] == "pop-v1" and r["outcome"] != "error"]
    ch = [r for r in d["records"] if r["phase"] not in ("pop-v1",) and r["outcome"] != "error"]
    agents = d["agents"]
    per_agent = []
    for j in range(1, agents + 1):
        rs = [r for r in v1 if agent_index(r) == j]
        c = [cost(r) for r in rs]
        per_agent.append({
            "agent": j, "tasks": len(rs), "correct": sum(r["outcome"] == "correct" for r in rs),
            "tok": sum(x[0] for x in c), "s": sum(x[1] for x in c), "learn_tok": sum(x[2] for x in c), "learn_s": sum(x[3] for x in c),
        })
    cum = {}
    for n in [k for k in STEPS if k <= agents] + ([agents] if agents not in STEPS else []):
        a = per_agent[:n]
        cum[n] = {"tok": sum(x["tok"] for x in a), "s": sum(x["s"] for x in a), "tasks": sum(x["tasks"] for x in a),
                  "correct": sum(x["correct"] for x in a)}

    def summary(rs):
        if not rs:
            return None
        c = [cost(r) for r in rs]
        return {"n": len(rs), "acc": sum(r["outcome"] == "correct" for r in rs) / len(rs),
                "tok": statistics.mean(x[0] for x in c), "s": statistics.mean(x[1] for x in c),
                "learn_tok": sum(x[2] for x in c), "learns": sum(1 for r in rs if (r.get("learning") or {}).get("extraction")),
                "stale": sum(1 for r in rs if r["metric_use"]["bad_executed"] > 0),
                "reused": sum(1 for r in rs if r["metric_use"]["declared"]),
                "steps": statistics.mean(r["run"].get("steps", 0) for r in rs),
                "tools": statistics.mean(r["run"].get("tool_calls", 0) for r in rs),
                "db_s": statistics.mean((r.get("db") or {}).get("ms", 0.0) / 1000 for r in rs)}

    # wrong numeric answers after the change: how far above or below the correct value (answer / gold - 1)
    over = []
    for r in ch:
        if r["outcome"] == "wrong":
            try:
                over.append(float(r["answer"]) / float(r["gold"]) - 1)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    late = [r for r in v1 if agent_index(r) > agents // 2]
    by_metric = collections.defaultdict(list)
    for r in late:
        tok, sec, _, _ = cost(r)
        by_metric[r["metric"]].append((tok, sec, r["outcome"] == "correct"))
    maint = {}
    for p in d["phases"]:
        maint[p["phase"]] = sum((e.get("db") or {}).get("ms", 0.0) for e in p["events"] if e.get("event") == "maintenance") / 1000
    return {"mode": d["mode"], "repeat": d["repeat"], "agents": agents, "per_agent": per_agent, "cum": cum,
            "v1": summary(v1), "late": summary(late), "change": summary(ch), "maint_db_s": maint,
            "errors": sum(r["outcome"] == "error" for r in d["records"]), "change_over": over,
            "by_metric_late": dict(by_metric)}


def agg(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"mean": statistics.mean(vals), "min": min(vals), "max": max(vals), "runs": len(vals)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--json-out")
    ap.add_argument("--tex-out")
    a = ap.parse_args()
    by = collections.defaultdict(list)
    for d in load(a.runs):
        by[d["mode"]].append(cell_stats(d))
    out = {"methods": {}}
    for m in METHODS:
        cs = by.get(m, [])
        if not cs:
            continue
        n_agents = cs[0]["agents"]
        res = {"name": NAMES[m], "runs": len(cs), "errors": sum(c["errors"] for c in cs)}
        for part in ("v1", "late", "change"):
            res[part] = {k: agg([c[part][k] if c[part] else None for c in cs])
                         for k in ("acc", "tok", "s", "n", "learns", "stale", "reused", "steps", "tools", "db_s")}
        res["cum"] = {n: {k: agg([c["cum"][n][k] for c in cs if n in c["cum"]]) for k in ("tok", "s", "tasks", "correct")}
                      for n in cs[0]["cum"]}
        res["per_agent"] = [{k: agg([c["per_agent"][j][k] for c in cs]) for k in ("tok", "s", "correct", "tasks", "learn_tok")}
                            for j in range(n_agents)]
        res["maint_db_s"] = {p: agg([c["maint_db_s"].get(p) for c in cs]) for p in cs[0]["maint_db_s"]}
        res["cells"] = cs
        out["methods"][m] = res

    def total(m, k):
        r = out["methods"].get(m)
        return r and r["cum"][max(r["cum"])][k]["mean"]

    ref = "metric-global-snap"
    savings = {}
    for m in METHODS:
        if m == ref or m not in out["methods"] or ref not in out["methods"]:
            continue
        savings[m] = {"tok_save": 1 - total(ref, "tok") / total(m, "tok"), "speedup": total(m, "s") / total(ref, "s")}
    out["savings_vs"] = savings

    print("| Method | runs | acc v1 | k tok/task | s/task | late k tok | late s | acc after change | stale | total M tok | total h |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for m, r in out["methods"].items():
        ch = r["change"]
        after = f"{ch['acc']['mean']:.0%} | {ch['stale']['mean']:.1f}" if ch["acc"] else "- | -"
        print(f"| {r['name']} | {r['runs']} | {r['v1']['acc']['mean']:.0%} | {r['v1']['tok']['mean'] / 1e3:.1f} | {r['v1']['s']['mean']:.1f} "
              f"| {r['late']['tok']['mean'] / 1e3:.1f} | {r['late']['s']['mean']:.1f} | {after} "
              f"| {total(m, 'tok') / 1e6:.2f} | {total(m, 's') / 3600:.2f} |")
    for m, s in savings.items():
        print(f"MAVRA vs {NAMES[m]}: {s['tok_save']:.0%} fewer tokens, {s['speedup']:.2f}x less agent time")

    if a.json_out:
        json.dump(out, open(a.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    if a.tex_out:
        lines = ["% generated by tools/population-stats.py; do not edit"]

        def mac(name, val):
            lines.append(f"\\newcommand{{\\Pp{name}}}{{{val}}}")

        any_r = next(iter(out["methods"].values()))
        mac("Agents", any_r["cells"][0]["agents"])
        mac("Runs", min(r["runs"] for r in out["methods"].values()))
        # agent sessions answered (unchanged data and after the change), all methods and runs; server failures excluded
        sessions = sum(c["v1"]["n"] + (c["change"]["n"] if c["change"] else 0) for r in out["methods"].values() for c in r["cells"])
        mac("Sessions", f"{sessions:,}")
        for m, r in out["methods"].items():
            k = KEY[m]
            mac(f"{k}Acc", f"{r['v1']['acc']['mean'] * 100:.0f}")
            mac(f"{k}TokK", f"{r['v1']['tok']['mean'] / 1e3:.1f}")
            mac(f"{k}S", f"{r['v1']['s']['mean']:.1f}")
            mac(f"{k}LateTokK", f"{r['late']['tok']['mean'] / 1e3:.1f}")
            mac(f"{k}LateS", f"{r['late']['s']['mean']:.1f}")
            mac(f"{k}LateSteps", f"{r['late']['steps']['mean']:.1f}")
            mac(f"{k}LateTools", f"{r['late']['tools']['mean']:.1f}")
            mac(f"{k}LateDbS", f"{r['late']['db_s']['mean']:.2f}")
            mac(f"{k}LateAcc", f"{r['late']['acc']['mean'] * 100:.0f}")
            mac(f"{k}TotalTokM", f"{total(m, 'tok') / 1e6:.2f}")
            mac(f"{k}TotalH", f"{total(m, 's') / 3600:.1f}")
            if r["change"]["acc"]:
                mac(f"{k}ChangeAcc", f"{r['change']['acc']['mean'] * 100:.0f}")
                mac(f"{k}ChangeStale", f"{r['change']['stale']['mean']:.0f}")
                mac(f"{k}ChangeTokK", f"{r['change']['tok']['mean'] / 1e3:.1f}")
                mac(f"{k}ChangeS", f"{r['change']['s']['mean']:.1f}")
            mac(f"{k}AccMin", f"{r['v1']['acc']['min'] * 100:.0f}")
            mac(f"{k}AccMax", f"{r['v1']['acc']['max'] * 100:.0f}")
            mac(f"{k}Learns", f"{r['v1']['learns']['mean']:.0f}")
            mac(f"{k}Reused", f"{r['v1']['reused']['mean'] / r['v1']['n']['mean'] * 100:.0f}")
            maint = [v["mean"] for p, v in r["maint_db_s"].items() if p != "pop-v1" and v]
            if maint:
                mac(f"{k}MaintS", f"{maint[0]:,.0f}")
            over = [x for c in r["cells"] for x in c["change_over"]]
            if over:
                mac(f"{k}ChangeOverMin", f"{min(over) * 100:.0f}")
                mac(f"{k}ChangeOverMax", f"{max(over) * 100:.0f}")
            mac(f"{k}TotalTokMin", f"{min(c['cum'][max(c['cum'])]['tok'] for c in r['cells']) / 1e6:.2f}")
            mac(f"{k}TotalTokMax", f"{max(c['cum'][max(c['cum'])]['tok'] for c in r['cells']) / 1e6:.2f}")
        # second half of the agents, per question and metric, pooled over runs (the saving is largest where exploring is hardest)
        WORD = {"M1": "One", "M2": "Two", "M3": "Three", "M4": "Four", "M5": "Five"}
        pooled = {}
        for m, r in out["methods"].items():
            acc = collections.defaultdict(list)
            for c in r["cells"]:
                for met, xs in c["by_metric_late"].items():
                    acc[met].extend(xs)
            pooled[m] = acc
            for met, xs in sorted(acc.items()):
                if met in WORD and xs:
                    mac(f"{KEY[m]}M{WORD[met]}TokK", f"{statistics.mean(x[0] for x in xs) / 1e3:.0f}")
                    mac(f"{KEY[m]}M{WORD[met]}S", f"{statistics.mean(x[1] for x in xs):.0f}")
                    mac(f"{KEY[m]}M{WORD[met]}Acc", f"{100 * sum(x[2] for x in xs) / len(xs):.0f}")
        if ref in pooled and "middle-alone" in pooled:
            tx, sx = [], []
            for met, word in WORD.items():
                a, b = pooled[ref].get(met), pooled["middle-alone"].get(met)
                if a and b:
                    t = statistics.mean(x[0] for x in b) / statistics.mean(x[0] for x in a)
                    v = statistics.mean(x[1] for x in b) / statistics.mean(x[1] for x in a)
                    tx.append(t)
                    sx.append(v)
                    mac(f"MavraM{word}TokX", f"{t:.1f}")
                    mac(f"MavraM{word}SpeedX", f"{v:.1f}")
            mac("MavraMetricTokXMin", f"{min(tx):.1f}")
            mac("MavraMetricTokXMax", f"{max(tx):.1f}")
            mac("MavraMetricSpeedXMin", f"{min(sx):.1f}")
            mac("MavraMetricSpeedXMax", f"{max(sx):.1f}")
        for m, s in savings.items():
            # second half of the agents, per question: how many times the tokens and time of MAVRA
            lr, lm = out["methods"][ref]["late"], out["methods"][m]["late"]
            mac(f"MavraLateTokX{KEY[m]}", f"{lm['tok']['mean'] / lr['tok']['mean']:.1f}")
            mac(f"MavraLateSpeedup{KEY[m]}", f"{lm['s']['mean'] / lr['s']['mean']:.1f}")
            mac(f"MavraTokSave{KEY[m]}", f"{s['tok_save'] * 100:.0f}")
            mac(f"MavraSpeedup{KEY[m]}", f"{s['speedup']:.1f}")
        # savings after the first N agents (mean over runs of the cumulative totals): they grow with N
        for m in savings:
            for n, word in ((4, "Four"), (8, "Eight")):
                a_t, b_t = out["methods"][ref]["cum"][n]["tok"]["mean"], out["methods"][m]["cum"][n]["tok"]["mean"]
                a_s, b_s = out["methods"][ref]["cum"][n]["s"]["mean"], out["methods"][m]["cum"][n]["s"]["mean"]
                mac(f"MavraTokSave{KEY[m]}N{word}", f"{(1 - a_t / b_t) * 100:.0f}")
                mac(f"MavraSpeedup{KEY[m]}N{word}", f"{b_s / a_s:.1f}")
        # per-run range of the savings against each method (paired: the same draw of questions per run)
        for m in savings:
            ref_c = {c["repeat"]: c for c in out["methods"][ref]["cells"]}
            pairs = [(ref_c[c["repeat"]], c) for c in out["methods"][m]["cells"] if c["repeat"] in ref_c]
            last = lambda c, k: c["cum"][max(c["cum"])][k]
            saves = [1 - last(a, "tok") / last(b, "tok") for a, b in pairs]
            speeds = [last(b, "s") / last(a, "s") for a, b in pairs]
            mac(f"MavraTokSave{KEY[m]}Min", f"{min(saves) * 100:.0f}")
            mac(f"MavraTokSave{KEY[m]}Max", f"{max(saves) * 100:.0f}")
            mac(f"MavraSpeedup{KEY[m]}Min", f"{min(speeds):.1f}")
            mac(f"MavraSpeedup{KEY[m]}Max", f"{max(speeds):.1f}")
        open(os.path.join(a.tex_out, "population.tex"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
