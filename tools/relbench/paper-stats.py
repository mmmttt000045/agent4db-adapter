#!/usr/bin/env python3
"""Numbers of the paper's RelBench experiment (exp/2026-10-20-relbench): macros in overleaf/gen/relbench.tex and the
main table's body in overleaf/gen/relbench-table.tex. Per database and arm, over the cutoffs from 2 on (the sessions in
which an arm can use what it kept): tokens with memory operations, LLM calls, tool calls, agent time, cost at
DeepSeek's off-peak prices; the test score per task averaged over all cutoffs; and the no-memory arm's workload (LLM
calls per session, share of schema and probe calls, schema calls repeated from earlier sessions). Sessions are paired
by (task, cutoff); an arm that has not finished yet is printed as "--".

  python3 tools/relbench/paper-stats.py --out overleaf/gen
"""
import argparse
import glob
import importlib.util
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("compare_stats", os.path.join(HERE, "compare-stats.py"))
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)
spec = importlib.util.spec_from_file_location("pilot_stats", os.path.join(HERE, "pilot-stats.py"))
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)

# database -> (macro prefix, run folders by arm); the paper's runs (README §4)
RUNS = {
    "rel-stack": ("Stack", "results/relbench-pilot3/{arm}-rel-stack-r1"),
    "rel-trial": ("Trial", "results/relbench-main/{arm}-rel-trial-r1"),
}
ARMS = [("none", "None", "No memory"), ("agentsm", "AgentSM", "AgentSM~\\cite{biswal2026agentsm}"),
        ("ace", "ACE", "ACE~\\cite{zhang2026ace}"), ("gmemory", "GMem", "G-Memory~\\cite{zhang2025gmemory}"),
        ("awm", "AWM", "AWM~\\cite{wang2025awm}"), ("mavra", "Mavra", "\\textbf{\\system\\ (ours)}")]
TASK_SHORT = {"post-votes": "post-votes", "user-badge": "user-badge", "user-engagement": "user-engage.",
              "study-outcome": "study-outcome", "study-adverse": "study-adverse", "site-success": "site-success"}
LETTERS = "ABC"


def finished(path):
    try:
        r = json.load(open(os.path.join(path, "run.json")))
    except (OSError, ValueError):
        return False
    return bool(r.get("finished")) or (bool(r.get("cutoffs")) and os.path.exists(os.path.join(path, ".done")))


def workload(path):
    """No-memory sessions of one run: median LLM calls, schema+probe share, repeated schema calls (pilot-stats.py)."""
    run = json.load(open(os.path.join(path, "run.json")))
    order = {(t, c["k"]): i for c in run["cutoffs"] for i, t in enumerate(c["order"])}
    sess = [json.load(open(f)) for f in glob.glob(os.path.join(path, "sessions", "*.json")) if not f.endswith(".partial.json")]
    sess.sort(key=lambda s: (s["k"], order.get((s["task"], s["k"]), 0)))
    seen, num, den, tools, sp = set(), 0, 0, 0, 0
    for i, s in enumerate(sess):
        schema = [ps.key(t) for t in s["tools"] if t.get("category") == "schema"]
        if i:
            den += len(schema)
            num += sum(1 for k in schema if k in seen)
        seen.update(schema)
        by = s["totals"]["tool_calls_by_category"]
        tools += s["totals"]["tool_calls"]
        sp += by.get("schema", 0) + by.get("probe", 0)
    return {"med_llm": statistics.median(s["totals"]["llm_calls"] for s in sess),
            "med_tok": statistics.median(s["totals"]["tokens"] for s in sess),
            "schema_probe": sp / tools, "repeat": num / den if den else None, "sessions": len(sess)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    macros, table = {}, []
    work = []
    for db, (pre, pattern) in RUNS.items():
        paths = {arm: pattern.format(arm=arm) for arm, _, _ in ARMS}
        done = {arm: p for arm, p in paths.items() if finished(p)}
        data = {arm: cs.load(p) for arm, p in done.items()}
        if "none" not in data:
            continue
        keys = sorted(set.intersection(*(set(d) for d in data.values())), key=lambda x: (x[1], x[0]))
        late = [k for k in keys if k[1] >= 2]
        tasks = sorted({k[0] for k in keys})
        macros[f"Rb{pre}Sessions"] = str(len(keys))
        macros[f"Rb{pre}Late"] = str(len(late))
        w = workload(done["none"])
        work.append(w)
        base = {f: sum(data["none"][k][f] for k in late) for f in ("tokens", "agent_s")}
        rows = {}
        for arm, name, label in ARMS:
            if arm not in data:
                for m in ("Tok", "TokX", "Llm", "Tools", "Min", "Speed", "Cost", "TokSave"):
                    macros[f"Rb{pre}{name}{m}"] = "--"
                for i, _ in enumerate(tasks):
                    macros[f"Rb{pre}{name}Q{LETTERS[i]}"] = "--"
                rows[arm] = None
                continue
            d = data[arm]
            tok = sum(d[k]["tokens"] for k in late)
            sec = sum(d[k]["agent_s"] for k in late)
            r = {"tok": tok, "tokx": tok / base["tokens"], "llm": sum(d[k]["llm"] for k in late), "tools": sum(d[k]["tools"] for k in late),
                 "min": sec / 60, "speed": base["agent_s"] / sec if sec else float("nan"),
                 "cost": sum(d[k]["cost"]["offpeak"] for k in late), "test": {}}
            for t in tasks:
                ks = [k for k in keys if k[0] == t and all(data[x][k]["test"] is not None for x in data)]
                r["test"][t] = statistics.mean(d[k]["test"] for k in ks) if ks else None
            rows[arm] = r
            macros.update({f"Rb{pre}{name}Tok": f"{tok / 1e6:.2f}", f"Rb{pre}{name}TokX": f"{r['tokx']:.2f}",
                           f"Rb{pre}{name}Llm": str(r["llm"]), f"Rb{pre}{name}Tools": str(r["tools"]),
                           f"Rb{pre}{name}Min": f"{r['min']:.0f}", f"Rb{pre}{name}Speed": f"{r['speed']:.1f}",
                           f"Rb{pre}{name}Cost": f"{r['cost']:.2f}", f"Rb{pre}{name}TokSave": f"{100 * (1 - r['tokx']):.0f}"})
            for i, t in enumerate(tasks):
                v = r["test"][t]
                macros[f"Rb{pre}{name}Q{LETTERS[i]}"] = "--" if v is None else (f"{v:.4f}" if v < 1 else f"{v:.2f}")
        # MAVRA against the best baseline (fewest tokens among the published memories that finished)
        pub = [arm for arm, _, _ in ARMS if arm not in ("none", "mavra") and rows.get(arm)]
        if rows.get("mavra") and pub:
            best = min(pub, key=lambda x: rows[x]["tok"])
            macros[f"Rb{pre}BestBaseline"] = dict((x, n) for x, n, _ in ARMS)[best]
            macros[f"Rb{pre}MavraVsBest"] = f"{100 * (1 - rows['mavra']['tok'] / rows[best]['tok']):.0f}"
            macros[f"Rb{pre}MavraSpeedVsBest"] = f"{(sum(data[best][k]['agent_s'] for k in late) / sum(data['mavra'][k]['agent_s'] for k in late)):.1f}"
        # table panel
        table.append(f"\\multicolumn{{9}}{{@{{}}l}}{{\\textit{{{db}}} ({len(late)} sessions from cutoff 2; test: "
                     + ", ".join(f"{TASK_SHORT.get(t, t)} {'AUC' if data['none'][next(k for k in keys if k[0] == t)]['higher'] else 'MAE'}" for t in tasks)
                     + ")}\\\\")
        for arm, name, label in ARMS:
            r = rows.get(arm)
            if r is None:
                table.append(f"{label} & \\multicolumn{{8}}{{c}}{{(running)}}\\\\")
                continue
            tests = " & ".join("--" if r["test"][t] is None else (f"{r['test'][t]:.3f}" if r["test"][t] < 1 else f"{r['test'][t]:.2f}") for t in tasks)
            table.append(f"{label} & {r['tok'] / 1e6:.2f} & {r['tokx']:.2f} & {r['llm']} & {r['tools']} & {r['min']:.0f} & {r['cost']:.2f} & {tests}\\\\")
        table.append("\\midrule")
    if table and table[-1] == "\\midrule":
        table.pop()
    if work:
        macros["RbNoneMedLlm"] = f"{statistics.median(w['med_llm'] for w in work):.0f}"
        macros["RbNoneMedTok"] = f"{statistics.median(w['med_tok'] for w in work) / 1e3:.0f}"
        macros["RbSchemaProbe"] = f"{100 * statistics.mean(w['schema_probe'] for w in work):.0f}"
        reps = [w["repeat"] for w in work if w["repeat"] is not None]
        macros["RbSchemaRepeat"] = f"{100 * statistics.mean(reps):.0f}" if reps else "--"
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "relbench.tex"), "w") as f:
        f.write("% generated by tools/relbench/paper-stats.py; do not edit\n")
        for k, v in sorted(macros.items()):
            f.write(f"\\providecommand{{\\{k}}}{{}}\\renewcommand{{\\{k}}}{{{v}}}\n")
    with open(os.path.join(a.out, "relbench-table.tex"), "w") as f:
        f.write("% generated by tools/relbench/paper-stats.py; do not edit\n" + "\n".join(table) + "\n")
    print(json.dumps(macros, indent=1))


if __name__ == "__main__":
    main()
