#!/usr/bin/env python3
"""Publication and consumer-performance statistics of the shared memory layer, from archived end-to-end runs.

usage: sharing-stats.py --scen results/scen-20261002 --prev results/scen-20260930 \
           --opt results/scen-20261008-opt/metric-*/cell-r1-metric-global-opt-named.json [--tex-out overleaf/gen]

Publication: what admission does with the learning tasks of every MAVRA-family cell. The funnel (judged, published,
corroborated, refused) is counted on the cells of the current implementation (the g3fix cells of --scen); refusals by
the replay checks (G6 example SQL, G7 canonical SQL) and by the provenance chain are counted over both studies, and the
G7 refusal whose canonical answer is furthest from the learned answer is reported as the example.

Consumer performance (MAVRA = metric-global-snap, three runs; exploring alone = middle; example retrieval = traj-global
and traj-verify):
- production per run: the learning sessions (all tokens and seconds), extraction and admission;
- held-out consumer tasks: tokens (input + output), seconds and accuracy per task, the speedup and the token saving
  against exploring alone, per task and per correct answer;
- maintenance per change (database time of the maintenance events, per run) against the extra cost per task when the
  example-retrieval agent verifies validity itself;
- the cost of invalidated definitions (duplicate load, date-key format, backup copy) for consumers;
- optimization: the test time per published rule candidate and its per-execution saving.
"""
import argparse
import collections
import glob
import importlib.util
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("scen_stats", os.path.join(HERE, "scen-stats.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

BENIGN = ["append", "backfill", "correct", "addcol"]
REPAIRED = ["status", "revision", "dimhist"]
INVALIDATED = ["dupload", "latekey", "mirror"]
G7_RE = re.compile(r"结果 ([0-9.\-]+) 与期望 Num\(([0-9.\-eE]+)\)")


def all_cells(root):
    for f in sorted(glob.glob(os.path.join(root, "*", "metric-*", "cell-*.json"))):
        job = os.path.relpath(f, root).split(os.sep)[0]
        if job.startswith("smoke"):
            continue
        d = json.load(open(f, encoding="utf-8"))
        if d["mode"].startswith("metric-global"):
            yield job, d


def publication(scen, prev):
    funnel = collections.Counter()
    for job, d in all_cells(scen):
        if "g3fix" not in job:
            continue
        for l in d.get("learning", []):
            s = l.get("submit") or {}
            funnel["tasks"] += 1
            if l.get("stage") == "judge":
                funnel["judge_refused"] += 1
                continue
            funnel["judged"] += 1
            if s.get("event") == "promoted":
                funnel["promoted"] += 1
            elif s.get("event") == "corroborated":
                funnel["corroborated"] += 1
            else:
                funnel["refused"] += 1
    refusals = collections.Counter()
    judged_all = 0
    worst = None
    for root in (prev, scen):
        for job, d in all_cells(root):
            for l in d.get("learning", []):
                s = l.get("submit") or {}
                if l.get("stage") == "judge":
                    continue
                judged_all += 1
                if l.get("stage") == "chain":
                    refusals["chain"] += 1
                gate = s.get("failed_gate")
                if gate in ("G6", "G7"):
                    refusals["replay"] += 1
                    m = G7_RE.search(str(s.get("reason") or ""))
                    if m:
                        got, want = float(m.group(1)), float(m.group(2))
                        ratio = max(got, want) / max(min(got, want), 1e-9)
                        if worst is None or ratio > worst[0]:
                            worst = (ratio, got, want, l["task"], job)
    return funnel, refusals, judged_all, worst


def run_cost(d):
    learn = [r for r in d["records"] if r["phase"] == "learn"]
    ex = [l.get("extraction") or {} for l in d.get("learning", [])]
    return {
        "learn_tok": sum(r["run"]["input_tokens"] + r["run"]["output_tokens"] for r in learn),
        "learn_s": sum(r["run"]["seconds"] for r in learn),
        "extract_tok": sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in ex),
        "extract_s": sum(e.get("seconds", 0) for e in ex),
        "admit_s": sum(l.get("gate_seconds", 0) for l in d.get("learning", [])),
    }


def per_task(cells, phases):
    rs = [r for c in cells for r in c["d"]["records"] if r["phase"] in phases and r["outcome"] != "error"]
    return {
        "n": len(rs),
        "tok": statistics.mean(r["run"]["input_tokens"] + r["run"]["output_tokens"] for r in rs),
        "s": statistics.mean(r["run"]["seconds"] for r in rs),
        "acc": sum(r["outcome"] == "correct" for r in rs) / len(rs),
    }


def maint_per_change(cells, phases):
    """Database seconds of the maintenance events per run and change, averaged over runs and the given changes."""
    vals = []
    for c in cells:
        ev = c["d"].get("events", {})
        for p in phases:
            vals.append(sum((e.get("db") or {}).get("ms", 0.0) for e in ev.get(p, []) if e.get("event") == "maintenance") / 1000)
    return statistics.mean(vals)


def optimization(path):
    d = json.load(open(path, encoding="utf-8"))
    tests, saves = [], []
    for r in (d.get("optimizing") or {}).get("rounds", []):
        for t in r.get("tried", []):
            if t.get("event") != "optimize_promoted":
                continue
            wall_s = (t.get("cost") or {}).get("wall_ms", 0) / 1000
            o6 = next(g for g in t["gates"] if g.get("gate") == "O6")
            save_ms = -o6["evidence"]["mean_delta_ms"]
            tests.append(wall_s)
            saves.append(save_ms)
    return tests, saves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scen", required=True)
    ap.add_argument("--prev", required=True)
    ap.add_argument("--opt", required=True)
    ap.add_argument("--tex-out")
    a = ap.parse_args()

    funnel, refusals, judged_all, worst = publication(a.scen, a.prev)
    print("## Publication")
    print(f"current implementation: {dict(funnel)}")
    print(f"both studies: judged {judged_all}, refused by replay {refusals['replay']}, by provenance chain {refusals['chain']}")
    print(f"largest canonical-replay error: {worst}")

    cells, _ = ss.load(a.scen)
    by = collections.defaultdict(list)
    for c in cells:
        by[c["d"]["mode"]].append(c)
    cond, alone, traj, verify = by["metric-global-snap"], by["middle"], by["traj-global"], by["traj-verify"]

    costs = [run_cost(c["d"]) for c in cond]
    prod = {k: statistics.mean(x[k] for x in costs) for k in costs[0]}
    prod_tok = prod["learn_tok"] + prod["extract_tok"]
    prod_s = prod["learn_s"] + prod["extract_s"] + prod["admit_s"]
    hold_c, hold_a = per_task(cond, ["holdout"]), per_task(alone, ["holdout"])
    hold_per_run = hold_c["n"] / len(cond)
    speedup = hold_a["s"] / hold_c["s"]
    tok_save = 100 * (1 - hold_c["tok"] / hold_a["tok"])
    print("\n## Production and consumers")
    print(f"production per run: {prod}; tokens {prod_tok:.0f}, seconds {prod_s:.0f}")
    print(f"held-out per task: alone {hold_a}, MAVRA {hold_c}; {hold_per_run:.0f} held-out tasks per run")
    print(f"held-out speedup {speedup:.1f}x, token saving {tok_save:.0f}%")
    per_correct_a, per_correct_c = hold_a["tok"] / hold_a["acc"], hold_c["tok"] / hold_c["acc"]
    correct_save = 100 * (1 - per_correct_c / per_correct_a)
    print(f"tokens per correct answer: alone {per_correct_a:.0f}, MAVRA {per_correct_c:.0f} ({correct_save:.0f}% fewer)")

    tv = per_task(traj, ["holdout"] + BENIGN)
    vv = per_task(verify, ["holdout"] + BENIGN)
    m_benign, m_repair, m_inval = maint_per_change(cond, BENIGN), maint_per_change(cond, REPAIRED), maint_per_change(cond, INVALIDATED)
    tasks_per_change = statistics.mean(per_task(cond, [p])["n"] / len(cond) for p in BENIGN + REPAIRED + INVALIDATED)
    print("\n## Maintenance against self-verification")
    print(f"maintenance DB s per change and run: benign {m_benign:.1f}, repaired {m_repair:.1f}, invalidated {m_inval:.1f}")
    print(f"self-verification extra per task (held-out + benign): {vv['s'] - tv['s']:.1f} s, {vv['tok'] - tv['tok']:.0f} tokens")
    print(f"consumer tasks per change and run: {tasks_per_change:.1f}")

    valid_c = per_task(cond, ["holdout"] + BENIGN + REPAIRED)
    inval_c, inval_a = per_task(cond, INVALIDATED), per_task(alone, INVALIDATED)
    print("\n## Invalidated definitions")
    print(f"MAVRA valid or repaired: {valid_c}; invalidated: {inval_c}; alone on the invalidating changes: {inval_a}")

    tests, saves = optimization(a.opt)
    print("\n## Optimization")
    print(f"test wall s per published candidate: {[round(x, 1) for x in tests]}")
    print(f"saving ms per execution: {[round(x, 1) for x in saves]}")

    if not a.tex_out:
        return
    k = lambda v: f"{v / 1000:.0f}"
    k1 = lambda v: f"{v / 1000:.1f}"
    money = lambda v: f"{v:,.2f}".replace(",", "{,}")
    macros = {
        "PubTasks": funnel["tasks"], "PubJudged": funnel["judged"], "PubJudgeRefused": funnel["judge_refused"],
        "PubPromoted": funnel["promoted"], "PubCorroborated": funnel["corroborated"], "PubRefused": funnel["refused"],
        "PubAllJudged": judged_all, "PubReplayRefused": refusals["replay"], "PubChainRefused": refusals["chain"],
        "PubExCanon": money(worst[1]) if worst else "--", "PubExAnswer": money(worst[2]) if worst else "--",
        "PubExRatio": f"{worst[0]:.1f}" if worst else "--",
        "AmLearnTokK": k(prod["learn_tok"]), "AmLearnS": f"{prod['learn_s']:.0f}",
        "AmExtractTokK": k(prod["extract_tok"]), "AmExtractS": f"{prod['extract_s']:.0f}", "AmAdmitS": f"{prod['admit_s']:.0f}",
        "AmProdTokK": k(prod_tok), "AmProdS": f"{prod_s:.0f}",
        "AmHoldPerRun": f"{hold_per_run:.0f}",
        "AmHoldTokAloneK": k1(hold_a["tok"]), "AmHoldTokCondK": k1(hold_c["tok"]),
        "AmHoldSAlone": f"{hold_a['s']:.1f}", "AmHoldSCond": f"{hold_c['s']:.1f}",
        "AmHoldSpeedup": f"{speedup:.1f}", "AmHoldTokSave": f"{tok_save:.0f}",
        "AmTokPerCorrectAloneK": k1(per_correct_a), "AmTokPerCorrectCondK": k1(per_correct_c), "AmCorrectTokSave": f"{correct_save:.0f}",
        "AmMaintBenignS": f"{m_benign:.1f}", "AmMaintRepairS": f"{m_repair:.0f}", "AmMaintInvalS": f"{m_inval:.0f}",
        "AmVerifyExtraS": f"{vv['s'] - tv['s']:.0f}", "AmVerifyExtraTokK": k1(vv["tok"] - tv["tok"]),
        "AmTasksPerChange": f"{tasks_per_change:.0f}",
        "AmValidTokCondK": k1(valid_c["tok"]), "AmValidSCond": f"{valid_c['s']:.0f}",
        "AmInvalTokCondK": k1(inval_c["tok"]), "AmInvalSCond": f"{inval_c['s']:.0f}",
        "AmInvalTokAloneK": k1(inval_a["tok"]), "AmInvalSAlone": f"{inval_a['s']:.0f}",
        "AmInvalAccCond": f"{100 * inval_c['acc']:.0f}", "AmInvalAccAlone": f"{100 * inval_a['acc']:.0f}",
        "AmOptTestMinS": f"{min(tests):.1f}", "AmOptTestMaxS": f"{max(tests):.1f}", "AmOptTestTotalS": f"{sum(tests):.0f}",
        "AmOptSaveMinMs": f"{min(saves):.1f}", "AmOptSaveMaxMs": f"{max(saves):.1f}",
    }
    path = os.path.join(a.tex_out, "sharing.tex")
    with open(path, "w", encoding="utf-8") as f:
        f.write("% generated by tools/sharing-stats.py; do not edit\n")
        for name, v in macros.items():
            f.write(f"\\newcommand{{\\{name}}}{{{v}}}\n")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
