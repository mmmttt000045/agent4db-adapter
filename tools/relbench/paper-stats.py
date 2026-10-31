#!/usr/bin/env python3
"""Numbers of the paper's RelBench experiment (exp/2026-10-20-relbench): macros in overleaf/gen/relbench.tex and the
main table's body in overleaf/gen/relbench-table.tex. Per database and arm, over the cutoffs from 2 on (the sessions in
which an arm can use what it kept): tokens with memory operations, LLM calls, tool calls, agent time, cost at
DeepSeek's official off-peak USD prices (standardized repricing, not invoiced cost); the test score per task averaged over all cutoffs; and the no-memory arm's workload (LLM
calls per session, share of schema and probe calls, schema calls repeated from earlier sessions). Sessions are paired
by (task, cutoff); an arm that has not finished yet is printed as "--", and so are the LLM-side cost columns
(tokens, token ratio, LLM calls, USD) of an arm with no LLM in the loop (NO_LLM, FeatPilot), whose structural
zeros would otherwise read as free or infinitely cheap. A session that ends without a valid solution
(every validation leaked or failed, or no solution) is scored as the entity-table reference, the model a team keeps
when feature work fails, and counted in Rb<db><arm>Unsolved; the same for every arm. The table also reports valid
solutions out of all 15 sessions and tasks meeting the prespecified quality tolerance out of all three tasks.

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
# 10-21 night (user): AgentSM (preprint) replaced by two data-preparation systems of the database venues
ARMS = [("none", "None", "No memory"), ("ace", "ACE", "ACE~\\cite{zhang2026ace}"),
        ("gmemory", "GMem", "G-Memory~\\cite{zhang2025gmemory}"), ("awm", "AWM", "AWM~\\cite{wang2025awm}"),
        ("deepprep", "DeepPrep", "DeepPrep~\\cite{fan2026deepprep}"), ("featpilot", "FeatPilot", "FeatPilot$^{*}$~\\cite{liang2025featpilot}"),
        ("mavra", "Mavra", "\\textbf{\\system\\ (ours)}")]
TASK_SHORT = {"post-votes": "post-votes", "user-badge": "user-badge", "user-engagement": "user-engage.",
              "study-outcome": "study-outcome", "study-adverse": "study-adverse", "site-success": "site-success"}
# arms with no LLM in the loop: their LLM-side cost metrics do not apply and print as "--", not 0
NO_LLM = {"featpilot"}
LETTERS = "ABC"


def score_text(value):
    return "--" if value is None else (f"{value:.4f}" if value < 1 else f"{value:.2f}")


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
    ap.add_argument("--sessions-json", help="also write every arm's sessions in arrival order (for the figure)")
    a = ap.parse_args()
    series = {}
    macros, table = {}, []
    work = []
    # every macro exists from the start ("--" until its runs finish), so the paper compiles at any time
    for db, (pre, _) in RUNS.items():
        for m in ("Sessions", "Late", "BestBaseline", "MavraVsBest", "MavraSpeedVsBest"):
            macros[f"Rb{pre}{m}"] = "--"
        for _, name, _ in ARMS:
            for m in ("Tok", "TokX", "Llm", "Tools", "Min", "Speed", "Cost", "TokSave", "Explore", "QA", "QB", "QC", "TokSaveAll", "NotWorse",
                      "Unsolved", "Solved"):
                macros[f"Rb{pre}{name}{m}"] = "--"
    for m in ("RbNoneMedLlm", "RbNoneMedTok", "RbSchemaProbe", "RbSchemaRepeat"):
        macros[m] = "--"
    for db, (pre, pattern) in RUNS.items():
        paths = {arm: pattern.format(arm=arm) for arm, _, _ in ARMS}
        done = {arm: p for arm, p in paths.items() if finished(p)}
        data = {arm: cs.load(p, prices=cs.USD_PRICES) for arm, p in done.items()}
        for arm, p in done.items():
            run = json.load(open(os.path.join(p, "run.json")))
            expected = {(t, c["k"]) for c in run["cutoffs"] for t in c["order"]}
            if set(data[arm]) != expected:
                raise ValueError(f"{p}: completed run has missing or unexpected session records")
            for key, session in data[arm].items():
                if session["test"] is None and session["audit"] == "clean":
                    raise ValueError(f"{p}: {key} has an unresolved test evaluation; recover scoring before publishing")
        if "none" in data and any(set(d) != set(data["none"]) for d in data.values()):
            raise ValueError(f"{db}: completed arms cover different sessions; refusing a partial intersection")
        for arm, p in done.items():  # time-corrections.json: sessions that ran while their cell was paused
            fix = os.path.join(os.path.dirname(p), "time-corrections.json")
            if os.path.exists(fix):
                for key, secs in json.load(open(fix))["seconds"].get(os.path.basename(p), {}).items():
                    t, k = key.rsplit("-k", 1)
                    if (t, int(k)) in data[arm]:
                        data[arm][(t, int(k))]["agent_s"] -= secs
        for arm, p in done.items():
            run = json.load(open(os.path.join(p, "run.json")))
            order = [(c["k"], t) for c in run["cutoffs"] for t in c["order"]]
            series.setdefault(db, {})[arm] = [{"k": k, "task": t, "tokens": data[arm][(t, k)]["tokens"], "agent_s": data[arm][(t, k)]["agent_s"],
                                               "cost": data[arm][(t, k)]["cost"]["offpeak"], "test": data[arm][(t, k)]["test"]}
                                              for k, t in order if (t, k) in data[arm]]
        if "none" in data:  # sessions without a valid solution: the reference's test score (run.json of the no-memory run)
            ref = {(t, c["k"]): v.get("test") for c in json.load(open(os.path.join(done["none"], "run.json")))["cutoffs"]
                   for t, v in (c.get("reference") or {}).items()}
            for d in data.values():
                for key, v in d.items():
                    v["unsolved"] = v["test"] is None
                    if v["unsolved"]:
                        v["test"] = ref.get(key)
        if "none" not in data:
            table.append(f"\\multicolumn{{12}}{{@{{}}l}}{{\\textit{{{db}}}: running}}\\\\")
            table.append("\\midrule")
            continue
        keys = sorted(set.intersection(*(set(d) for d in data.values())), key=lambda x: (x[1], x[0]))
        late = [k for k in keys if k[1] >= 2]
        tasks = sorted({k[0] for k in keys})
        macros[f"Rb{pre}Sessions"] = str(len(keys))
        macros[f"Rb{pre}Late"] = str(len(late))
        w = workload(done["none"])
        work.append(w)
        base = {f: sum(data["none"][k][f] for k in late) for f in ("tokens", "agent_s")}
        base_all = sum(data["none"][k]["tokens"] for k in keys)
        rows = {}
        for arm, name, label in ARMS:
            if arm not in data:
                for m in ("Tok", "TokX", "Llm", "Tools", "Min", "Speed", "Cost", "TokSave", "Explore", "TokSaveAll", "NotWorse", "Unsolved", "Solved"):
                    macros[f"Rb{pre}{name}{m}"] = "--"
                for i, _ in enumerate(tasks):
                    macros[f"Rb{pre}{name}Q{LETTERS[i]}"] = "--"
                rows[arm] = None
                continue
            d = data[arm]
            tok = sum(d[k]["tokens"] for k in late)
            sec = sum(d[k]["agent_s"] for k in late)
            explore = sum(d[k]["by_cat"].get("schema", 0) + d[k]["by_cat"].get("probe", 0) for k in late)
            r = {"tok": tok, "tokx": tok / base["tokens"], "llm": sum(d[k]["llm"] for k in late), "tools": sum(d[k]["tools"] for k in late),
                 "explore": explore, "explore_per": explore / len(late) if late else 0,
                 "min": sec / 60, "speed": base["agent_s"] / sec if sec else float("nan"),
                 "cost": sum(d[k]["cost"]["offpeak"] for k in late), "test": {},
                 "solved": sum(not d[k]["unsolved"] for k in keys), "not_worse": 0}
            for t in tasks:
                ks = [k for k in keys if k[0] == t and all(data[x][k]["test"] is not None for x in data)]
                r["test"][t] = statistics.mean(d[k]["test"] for k in ks) if ks else None
            rows[arm] = r
            # tasks on which the arm's mean test score is not worse than no memory's (pre-registered: AUC within 0.01, MAE within 2%)
            if "none" in rows and rows["none"] is not None:
                nw = 0
                for t in tasks:
                    a_, b_ = r["test"].get(t), rows["none"]["test"].get(t)
                    if a_ is None or b_ is None:
                        continue
                    higher = data["none"][next(k for k in keys if k[0] == t)]["higher"]
                    nw += (a_ >= b_ - 0.01) if higher else (a_ <= b_ * 1.02)
                macros[f"Rb{pre}{name}NotWorse"] = str(nw)
                r["not_worse"] = nw
            macros.update({f"Rb{pre}{name}Tok": f"{tok / 1e6:.2f}", f"Rb{pre}{name}TokX": f"{r['tokx']:.2f}",
                           f"Rb{pre}{name}Llm": str(r["llm"]), f"Rb{pre}{name}Tools": str(r["tools"]),
                           f"Rb{pre}{name}Min": f"{r['min']:.0f}", f"Rb{pre}{name}Speed": f"{r['speed']:.1f}",
                           f"Rb{pre}{name}Cost": f"{r['cost']:.2f}", f"Rb{pre}{name}TokSave": f"{100 * (1 - r['tokx']):.0f}",
                           f"Rb{pre}{name}Explore": f"{r['explore_per']:.1f}",
                           f"Rb{pre}{name}Unsolved": str(sum(1 for k in keys if d[k]["unsolved"])),
                           f"Rb{pre}{name}Solved": str(r["solved"]),
                           f"Rb{pre}{name}TokSaveAll": f"{100 * (1 - sum(d[k]['tokens'] for k in keys) / base_all):.0f}"})
            for i, t in enumerate(tasks):
                v = r["test"][t]
                macros[f"Rb{pre}{name}Q{LETTERS[i]}"] = "--" if v is None else (f"{v:.4f}" if v < 1 else f"{v:.2f}")
        # MAVRA against the best baseline (fewest tokens among the published memories that finished)
        # the token comparison is against the agent memories (the methods built to save repeated work); DeepPrep and FeatPilot
        # search each task anew and are compared on quality and time
        pub = [arm for arm in ("ace", "gmemory", "awm") if rows.get(arm)]
        if rows.get("mavra") and pub:
            best = min(pub, key=lambda x: rows[x]["tok"])
            macros[f"Rb{pre}BestBaseline"] = dict((x, n) for x, n, _ in ARMS)[best]
            macros[f"Rb{pre}MavraVsBest"] = f"{100 * (1 - rows['mavra']['tok'] / rows[best]['tok']):.0f}"
            macros[f"Rb{pre}MavraSpeedVsBest"] = f"{(sum(data[best][k]['agent_s'] for k in late) / sum(data['mavra'][k]['agent_s'] for k in late)):.1f}"
        # Task-specific headings make every score interpretable without a task-order legend.
        headings, best_scores = [], {}
        for t in tasks:
            higher = data['none'][next(k for k in keys if k[0] == t)]['higher']
            metric = r"AUC $\uparrow$" if higher else r"MAE $\downarrow$"
            headings.append(r"\shortstack{" + TASK_SHORT.get(t, t) + r"\\" + metric + "}")
            scores = [r["test"][t] for r in rows.values() if r and r["test"][t] is not None]
            best_scores[t] = score_text((max if higher else min)(scores)) if scores else None
        table.append(r"\RbPanelHeader{" + db + "}{" + "}{".join(headings) + "}")
        for arm, name, label in ARMS:
            r = rows.get(arm)
            if r is None:
                table.append(f"{label} & \\multicolumn{{11}}{{c}}{{(running)}}\\\\")
                continue
            tests = []
            for t in tasks:
                text = score_text(r["test"][t])
                tests.append(r"\textbf{" + text + "}" if text == best_scores[t] else text)
            if arm in NO_LLM:
                head = f"{label} & -- & -- & -- & {r['tools']} & {r['min']:.0f} & -- & "
            else:
                head = f"{label} & {r['tok'] / 1e6:.2f} & {r['tokx']:.2f} & {r['llm']} & {r['tools']} & {r['min']:.0f} & {r['cost']:.2f} & "
            table.append(head + " & ".join(tests) + f" & {r['solved']}/{len(keys)} & {r['not_worse']}/{len(tasks)}\\\\")
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
        # a macro, not rows read by \input inside the tabular: \multicolumn must come first in its cell
        f.write("% generated by tools/relbench/paper-stats.py; do not edit\n\\def\\RbTableBody{%\n" + "\n".join(table) + "\n}\n")
    if a.sessions_json:
        with open(a.sessions_json, "w") as f:
            json.dump(series, f, indent=1)
    print(json.dumps(macros, indent=1))


if __name__ == "__main__":
    main()
