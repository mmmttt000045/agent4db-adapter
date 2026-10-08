#!/usr/bin/env python3
"""Statistics of the lifecycle study (metric-bench --lifecycle): one shared library under a cumulative timeline of
updates and waves of fresh consumers, one process per method.

usage: lifecycle-stats.py --mavra CELL.json --traj CELL.json --none CELL.json [--tex-out overleaf/gen] [--json OUT]

Per step and method: accuracy of the wave (one fresh agent per scored question), tokens and seconds per task.
For MAVRA, the layer's events in the step: maintenance outcomes (refreshed, repaired, reinstated by predecessor or by
undoing the rule, invalidated), requests that waited for or merged into a running maintenance, rejected references,
relearned and published definitions, and optimization rounds. Totals count consumer tasks and, separately, production
(learning and relearning sessions, extraction, LLM optimization proposals); tokens per correct answer include
production for the methods that build a memory.
"""
import argparse
import collections
import json
import os

STEP = {
    "none": ("Unchanged data", "数据不变"),
    "append": ("Sales appended", "追加销售"),
    "backfill": ("Late returns", "迟到退货"),
    "correct": ("In-place correction", "原地更正"),
    "addcol": ("New column", "新增列"),
    "status": ("Return status rows", "退货状态行"),
    "revision": ("Restated sales", "更正保留旧行"),
    "dimhist": ("Item SCD Type 2", "商品维度 SCD 2"),
    "rekey": ("Date keys re-keyed", "日期键重编号"),
    "dupload": ("Duplicate load", "重复加载"),
    "cleanup": ("Duplicates removed", "删除重复批次"),
}
BREAKING = {"status", "revision", "dimhist", "rekey", "dupload"}


def tok(r):
    return r["run"]["input_tokens"] + r["run"]["output_tokens"]


def extraction_tokens(steps):
    n = 0
    for x in steps:
        e = x.get("extraction") or {}
        n += e.get("input_tokens", 0) + e.get("output_tokens", 0)
    return n


def proposal_tokens(opt):
    if not opt:
        return 0
    return sum((r.get("proposals") or {}).get("input_tokens", 0) + (r.get("proposals") or {}).get("output_tokens", 0)
               for r in opt.get("rounds", []) if isinstance(r.get("proposals"), dict))


def analyze(path):
    c = json.load(open(path, encoding="utf-8"))
    recs = c["records"]
    learn = [r for r in recs if r["phase"] == "learn"]
    prod_tok = sum(tok(r) for r in learn) + extraction_tokens(c.get("learning", [])) + proposal_tokens(c.get("optimizing"))
    prod_s = sum(r["run"]["seconds"] for r in learn)
    steps = []
    for e in c["epochs"]:
        wave = [r for r in recs if r["phase"] == e["phase"]]
        relearn = [r for r in recs if r["phase"] == e["phase"] + "-relearn"]
        prod_tok += sum(tok(r) for r in relearn) + extraction_tokens(e.get("relearn", [])) + proposal_tokens(e.get("reoptimizing"))
        prod_s += sum(r["run"]["seconds"] for r in relearn)
        ev = e.get("events", []) + e.get("production_events", [])
        out = collections.Counter(x.get("outcome") for x in ev if x.get("event") == "maintenance")
        how = collections.Counter(x.get("how") for x in ev if x.get("event") == "reinstated")
        maint_ms = sum((x.get("db") or {}).get("ms", 0.0) for x in ev if x.get("event") == "maintenance")
        steps.append({
            "phase": e["phase"], "name": e["name"], "n": len(wave),
            "correct": sum(r["outcome"] == "correct" for r in wave),
            "tok": sum(tok(r) for r in wave), "s": sum(r["run"]["seconds"] for r in wave),
            "steps": sum(r["run"].get("steps", 0) for r in wave),
            "declared": sum(1 for r in wave if (r.get("metric_use") or {}).get("declared")),
            "stale_executed": sum((r.get("metric_use") or {}).get("bad_executed", 0) for r in wave),
            "refreshed": out.get("refreshed", 0), "repaired": out.get("repaired", 0),
            "reinstated": out.get("reinstated", 0), "revoked": out.get("revoked", 0),
            "by_predecessor": how.get("predecessor", 0), "by_undo": how.get("undo_rule", 0),
            "waited": sum(1 for x in ev if x.get("event") in ("repair_waited", "maintenance_merged")),
            "ref_rejected": sum(1 for x in ev if x.get("event") == "ref_rejected"),
            "snapshot_rejected": sum(1 for x in ev if x.get("event") == "snapshot_rejected"),
            "relearned": len({x["task"].split("-")[0] for x in e.get("relearn", [])
                              if (x.get("submit") or {}).get("event") in ("promoted", "corroborated")}),
            "relearn_refused": sum(1 for x in e.get("relearn", []) if (x.get("submit") or {}).get("failed_gate")),
            "optimized": (e.get("reoptimizing") or {}).get("published", 0) if e.get("reoptimizing") else 0,
            "maint_s": maint_ms / 1000,
            "wave_s": e.get("wave_seconds", 0.0),
        })
    opt0 = (c.get("optimizing") or {}).get("published", 0) if c.get("optimizing") else 0
    n = sum(s["n"] for s in steps)
    correct = sum(s["correct"] for s in steps)
    cons_tok = sum(s["tok"] for s in steps)
    br = [s for s in steps if s["name"] in BREAKING]
    return {
        "cell": c["cell"], "mode": c["mode"], "timeline": c["timeline"], "concurrency": c.get("concurrency"),
        "steps": steps, "optimized_after_learning": opt0,
        "tasks": n, "correct": correct, "acc": correct / n if n else 0.0,
        "acc_breaking": sum(s["correct"] for s in br) / max(1, sum(s["n"] for s in br)),
        "consumer_tokens": cons_tok, "production_tokens": prod_tok, "production_s": prod_s,
        "tok_per_task": cons_tok / n if n else 0.0, "s_per_task": sum(s["s"] for s in steps) / n if n else 0.0,
        "tok_per_correct": (cons_tok + prod_tok) / correct if correct else float("inf"),
        "seconds": c["seconds"],
    }


def events_text(s):
    en, zh = [], []
    def add(n, e, z):
        if n:
            en.append(f"{n} {e}")
            zh.append(f"{n} {z}" if z.startswith("个") else f"{z} {n}")
    add(s["repaired"], "repaired", "修复")
    add(s["by_predecessor"], "predecessor reinstated", "恢复前一修订")
    add(s["by_undo"], "rule undone", "撤销改写")
    add(s["revoked"], "invalidated", "失效")
    add(s["relearned"], "metric relearned" if s["relearned"] == 1 else "metrics relearned", "个指标重新学习")
    add(s["relearn_refused"], "candidates refused", "个候选被准入拒绝")
    add(s["optimized"], "optimized", "优化")
    return ("; ".join(en) or "--", "；".join(zh) or "--")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mavra", required=True)
    ap.add_argument("--traj", required=True)
    ap.add_argument("--none", required=True)
    ap.add_argument("--tex-out")
    ap.add_argument("--json")
    a = ap.parse_args()
    m, t, z = analyze(a.mavra), analyze(a.traj), analyze(a.none)
    for name, x in (("MAVRA", m), ("example retrieval", t), ("no memory", z)):
        print(f"## {name} ({x['cell']}): {x['correct']}/{x['tasks']} = {100 * x['acc']:.0f}%, breaking {100 * x['acc_breaking']:.0f}%, "
              f"{x['tok_per_task'] / 1000:.1f}k tok/task, {x['s_per_task']:.1f} s/task, production {x['production_tokens'] / 1000:.0f}k tok, "
              f"{x['tok_per_correct'] / 1000:.1f}k tok/correct, run {x['seconds'] / 60:.0f} min")
    print("\nstep               none  traj  MAVRA  events")
    for sz, st, sm in zip(z["steps"], t["steps"], m["steps"]):
        print(f"{sm['phase']:<18} {sz['correct']:>2}/{sz['n']:<2} {st['correct']:>2}/{st['n']:<2} {sm['correct']:>2}/{sm['n']:<2}  "
              f"{events_text(sm)[0]}; waited {sm['waited']}, refs rejected {sm['ref_rejected']}, snapshot rejected {sm['snapshot_rejected']}, "
              f"stale executed {sm['stale_executed']}, maint {sm['maint_s']:.1f} s")
    if a.json:
        json.dump({"mavra": m, "traj": t, "none": z}, open(a.json, "w", encoding="utf-8"), indent=1)
    if not a.tex_out:
        return
    pct = lambda v: f"{100 * v:.0f}"
    k1 = lambda v: f"{v / 1000:.1f}"
    tot = lambda key: sum(s[key] for s in m["steps"])
    macros = {
        "LcSteps": len(m["steps"]), "LcTasks": m["tasks"], "LcWave": m["steps"][0]["n"], "LcConc": m["concurrency"],
        "LcAccCond": pct(m["acc"]), "LcAccTraj": pct(t["acc"]), "LcAccNone": pct(z["acc"]),
        "LcAccBreakCond": pct(m["acc_breaking"]), "LcAccBreakTraj": pct(t["acc_breaking"]), "LcAccBreakNone": pct(z["acc_breaking"]),
        "LcCorrectCond": m["correct"], "LcCorrectTraj": t["correct"], "LcCorrectNone": z["correct"],
        "LcTokTaskCond": k1(m["tok_per_task"]), "LcTokTaskTraj": k1(t["tok_per_task"]), "LcTokTaskNone": k1(z["tok_per_task"]),
        "LcTokCorrectCond": k1(m["tok_per_correct"]), "LcTokCorrectTraj": k1(t["tok_per_correct"]), "LcTokCorrectNone": k1(z["tok_per_correct"]),
        "LcSecTaskCond": f"{m['s_per_task']:.0f}", "LcSecTaskTraj": f"{t['s_per_task']:.0f}", "LcSecTaskNone": f"{z['s_per_task']:.0f}",
        "LcProdTokCondK": f"{m['production_tokens'] / 1000:.0f}",
        "LcRepaired": tot("repaired"), "LcByPred": tot("by_predecessor"), "LcByUndo": tot("by_undo"), "LcRevoked": tot("revoked"),
        "LcRelearned": tot("relearned"), "LcWaited": tot("waited"), "LcStaleExec": tot("stale_executed"),
        "LcOptimized": m["optimized_after_learning"], "LcMaintS": f"{tot('maint_s'):.0f}",
        "LcDeclaredPct": pct(tot("declared") / m["tasks"]),
        "LcRelearnRefused": tot("relearn_refused"),
    }
    # 失效之前（时间线上第一次重复装载之前）每题的 token 与轮数；重复装载一步；之后各步示例检索的答对数
    def before_dup(x):
        out = []
        for st in x["steps"]:
            if st["name"] == "dupload":
                break
            out.append(st)
        return out
    per = lambda st, key: st[key] / st["n"]
    for tag, x in (("Cond", m), ("Traj", t), ("None", z)):
        pre = before_dup(x)
        macros[f"LcPreTokMin{tag}"] = k1(min(per(st, "tok") for st in pre))
        macros[f"LcPreTokMax{tag}"] = k1(max(per(st, "tok") for st in pre))
        macros[f"LcPreTurnsMin{tag}"] = f"{min(per(st, 'steps') for st in pre):.1f}"
        macros[f"LcPreTurnsMax{tag}"] = f"{max(per(st, 'steps') for st in pre):.1f}"
        dup = next((st for st in x["steps"] if st["name"] == "dupload"), None)
        if dup:
            macros[f"LcDupTok{tag}"] = f"{per(dup, 'tok') / 1000:.0f}"
            macros[f"LcDupCorrect{tag}"] = dup["correct"]
        after = x["steps"][x["steps"].index(dup) + 1:] if dup else []
        rk = next((st for st in x["steps"] if st["name"] == "rekey"), None)
        if rk:
            macros[f"LcRekeyCorrect{tag}"] = rk["correct"]
        macros[f"LcPreDeclaredPct{tag}"] = pct(sum(st["declared"] for st in pre) / sum(st["n"] for st in pre))
        if after:
            macros[f"LcAfterCorrectMin{tag}"] = min(st["correct"] for st in after)
            macros[f"LcAfterCorrectMax{tag}"] = max(st["correct"] for st in after)
    with open(os.path.join(a.tex_out, "lifecycle.tex"), "w", encoding="utf-8") as f:
        f.write("% generated by tools/lifecycle-stats.py; do not edit\n")
        for name, v in macros.items():
            f.write(f"\\newcommand{{\\{name}}}{{{v}}}\n")
    with open(os.path.join(a.tex_out, "lifecycle-rows.tex"), "w", encoding="utf-8") as f:
        f.write("% generated by tools/lifecycle-stats.py; do not edit\n")
        for sz, st, sm in zip(z["steps"], t["steps"], m["steps"]):
            en, zh = STEP.get(sm["name"], (sm["name"], sm["name"]))
            ev_en, ev_zh = events_text(sm)
            f.write(f"\\bt{{{en}}}{{{zh}}} & {sz['correct']} & {st['correct']} & {sm['correct']} & \\bt{{{ev_en}}}{{{ev_zh}}}\\\\\n")
        f.write("\\midrule\n")
        f.write(f"\\bt{{Correct, all steps}}{{全部步骤正确率}} & {pct(z['acc'])}\\% & {pct(t['acc'])}\\% & {pct(m['acc'])}\\% & \\\\\n")
        f.write(f"\\bt{{k tokens per task}}{{每题 k token}} & {k1(z['tok_per_task'])} & {k1(t['tok_per_task'])} & {k1(m['tok_per_task'])} & \\\\\n")
        f.write(f"\\bt{{k tokens per correct answer}}{{每个正确答案 k token}} & {k1(z['tok_per_correct'])} & {k1(t['tok_per_correct'])} & "
                f"{k1(m['tok_per_correct'])} & \\\\\n")
    print(f"\nwrote {a.tex_out}/lifecycle.tex and lifecycle-rows.tex")


if __name__ == "__main__":
    main()
