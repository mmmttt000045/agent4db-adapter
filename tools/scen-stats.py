#!/usr/bin/env python3
"""场景主实验的统计，按 exp/2026-10-02-scenarios-ds/README.md 中预先写定的分析方案。

用法：python3 tools/scen-stats.py --scen results/scen-20261002 [--json OUT] [--reps 4000] [--tex-out overleaf/gen]
--tex-out 时另写 scen-ds.tex（\\Ds* 数值宏）。图 4 由 tools/figures/scenario_groups.py 直接读取 --json 的输出。

- 计分题：留出题与各变化下重问的题；学习题与重新学习题不计分。
- 服务端失败的题（outcome = error）不计分，单列数量；replaced.txt 中被整组重跑替换的原组不计。
- 每种方法的正确率：每种变化（含留出）等权平均；另给“已建模的破坏性变化”（status、revision、dupload、dimhist、latekey）
  与留出、正常变化、备份副本、单位变化各自的正确率。
- 95% 区间：按组（方法 × 重复）整群自助法：同一方法的组有放回重抽，组内题目整体带入。
- 预先声明的比较：(a) 已建模破坏性变化下 条件级 − 轨迹检索、条件级 − 定义级；(b) 全部情形 条件级 − 不共享；
  (c) 留出题 条件级 − 轨迹检索。差值的区间对两种方法各自独立整群重抽。(a)–(c) 与 e2、e3 中的“条件级”是当时的主配置
  metric-global（G8 参照为标准答案 SQL）；d1、d2 是 2026-10-03 增补的 metric-global-exref（G8 参照为智能体自己的 SQL）。
- 2026-10-06 晚起论文的 MAVRA 是 metric-global-snap（G8 以智能体自己的 SQL 为参照、在学习时快照上比较）：宏 \DsCond*
  指它，\DsCondCur* 指 metric-global-exref（同一参照、在当前数据上比较，消融），\DsCondGold* 指 metric-global。
  g1、g2 是 metric-global-snap 启动前写定的比较；f、h 两组是同口径补算、不在预先写定方案内的比较。
  方法列表按时间先后追加，新方法的自助样本排在最后，已报告的区间不变。
"""

import argparse
import collections
import glob
import json
import os
import random

METHODS = ["middle", "traj-global", "traj-verify", "metric-global-noguard", "metric-global-schema", "metric-global-revoke",
           "metric-global-def", "metric-global", "metric-global-exref", "metric-global-snap"]
NAMES = {"middle": "No sharing", "traj-global": "Trajectory retrieval", "traj-verify": "Trajectory + self-check",
         "metric-global-noguard": "No validation", "metric-global-schema": "Schema-change invalidation",
         "metric-global-revoke": "Invalidate-on-write", "metric-global-def": "Definition-level",
         "metric-global": "MAVRA (gold SQL)", "metric-global-exref": "MAVRA, G8 on current data", "metric-global-snap": "MAVRA"}
PHASES = ["holdout", "append", "backfill", "correct", "addcol", "status", "revision", "dupload", "dimhist", "latekey", "unit", "mirror"]
GROUPS = {
    "all": PHASES,
    "holdout": ["holdout"],
    "benign": ["append", "backfill", "correct", "addcol"],
    "modeled": ["status", "revision", "dupload", "dimhist", "latekey"],
    "mirror": ["mirror"],
    "unit": ["unit"],
}


def load(root):
    rp = os.path.join(root, "replaced.txt")
    replaced = {x.strip() for x in open(rp, encoding="utf-8")} if os.path.exists(rp) else set()
    cells, skipped = [], []
    for f in sorted(glob.glob(os.path.join(root, "*", "metric-*", "cell-*.json"))):
        job = os.path.relpath(f, root).split(os.sep)[0]
        if job.startswith("smoke"):
            continue
        if f"{job}/{os.path.basename(f)[:-5]}" in replaced:
            skipped.append(f)
            continue
        cells.append({"job": job, "file": f, "d": json.load(open(f, encoding="utf-8"))})
    return cells, skipped


def cell_stats(c):
    """组内每个阶段的 [答对, 有效题]，以及过期使用、服务端失败、轮数、输入 token、维护 DB 时间、撤销与修复。"""
    d = c["d"]
    acc = collections.defaultdict(lambda: [0, 0])
    stale = collections.Counter()
    errors, turns, tokens = 0, [], []
    for r in d["records"]:
        p = r["phase"]
        if p == "learn" or p.endswith("-relearn"):
            continue
        if r["outcome"] == "error":
            errors += 1
            continue
        acc[p][0] += r["outcome"] == "correct"
        acc[p][1] += 1
        u = r.get("metric_use") or {}
        stale[p] += (u.get("bad_found", 0) or 0) > 0 or (u.get("bad_executed", 0) or 0) > 0
        turns.append(r["run"]["steps"])
        tokens.append(r["run"]["input_tokens"])
    ev = collections.Counter()
    maint = 0.0
    for p, evs in d.get("events", {}).items():
        if p in ("learn", "holdout"):
            continue
        for e in evs:
            ev[e.get("event", "?")] += 1
            if e.get("event") == "maintenance":
                maint += (e.get("db") or {}).get("ms", 0.0) / 1000.0
    return {"acc": dict(acc), "stale": dict(stale), "errors": errors, "turns": turns, "tokens": tokens,
            "revoked": ev["revoked"], "repaired": ev["repair_promoted"], "maint_s": maint}


def rate(cells, phases):
    """各阶段等权：先在每个阶段把这些组的题合在一起求正确率，再对有题的阶段取平均。"""
    vals = []
    for p in phases:
        k = sum(c["acc"].get(p, [0, 0])[0] for c in cells)
        n = sum(c["acc"].get(p, [0, 0])[1] for c in cells)
        if n:
            vals.append(k / n)
    return sum(vals) / len(vals) if vals else None


def boot(cells, phases, reps, rnd):
    out = []
    for _ in range(reps):
        s = [rnd.choice(cells) for _ in cells]
        v = rate(s, phases)
        if v is not None:
            out.append(v)
    return out  # 不排序：两种方法的抽样按序号相减即独立差值样本


def ci(xs):
    xs = sorted(xs)
    return [xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]] if xs else [None, None]


KEY = {"middle": "NoShare", "traj-global": "Traj", "traj-verify": "TrajVerify", "metric-global-noguard": "Noguard",
       "metric-global-schema": "Schema", "metric-global-revoke": "Revoke", "metric-global-def": "Def", "metric-global": "CondGold",
       "metric-global-exref": "CondCur", "metric-global-snap": "Cond"}


def tex(res, out):
    pct = lambda v: f"{100 * v:.0f}" if v is not None else "--"
    q = {"DsCells": sum(res["cells"].values()), "DsReplaced": res["replaced_cells_excluded"],
         "DsProviderErrors": sum(r["provider_errors"] for r in res["methods"].values())}
    for m, r in res["methods"].items():
        k = KEY[m]
        for g in GROUPS:
            q[f"Ds{k}{g.capitalize()}"] = pct(r[g]["acc"])
            lo, hi = r[g]["ci95"]
            q[f"Ds{k}{g.capitalize()}Lo"] = pct(lo)
            q[f"Ds{k}{g.capitalize()}Hi"] = pct(hi)
        q[f"Ds{k}StaleModeled"] = r["stale_tasks"]["modeled"]
        q[f"Ds{k}StaleMirror"] = r["stale_tasks"]["mirror"]
        q[f"Ds{k}StaleUnit"] = r["stale_tasks"]["unit"]
        q[f"Ds{k}Revoked"] = f"{r['revoked_per_cell']:.1f}"
        q[f"Ds{k}Repaired"] = f"{r['repaired_per_cell']:.1f}"
        q[f"Ds{k}Turns"] = f"{r['turns_per_task']:.1f}" if r["turns_per_task"] else "--"
        q[f"Ds{k}TokK"] = f"{r['input_tokens_per_task'] / 1000:.1f}" if r["input_tokens_per_task"] else "--"
        q[f"Ds{k}MaintS"] = f"{r['maint_db_s_per_cell']:.0f}"
    names = {"a1 modeled: MAVRA (gold SQL) - trajectory": "DsCmpModeledGoldTraj",
             "a2 modeled: MAVRA (gold SQL) - definition-level": "DsCmpModeledGoldDef",
             "b all: MAVRA (gold SQL) - no sharing": "DsCmpAllGoldNoShare",
             "c holdout: MAVRA (gold SQL) - trajectory": "DsCmpHoldoutGoldTraj",
             "d1 modeled: MAVRA, G8 on current data - trajectory": "DsCmpModeledCurTraj",
             "d2 modeled: MAVRA, G8 on current data - MAVRA (gold SQL)": "DsCmpModeledCurGold",
             "e1 modeled: trajectory+self-check - trajectory": "DsCmpModeledVerifyTraj",
             "e2 modeled: MAVRA (gold SQL) - trajectory+self-check": "DsCmpModeledGoldVerify",
             "e3 all: MAVRA (gold SQL) - trajectory+self-check": "DsCmpAllGoldVerify",
             "f1 modeled: MAVRA, G8 on current data - definition-level": "DsCmpModeledCurDef",
             "f2 all: MAVRA, G8 on current data - no sharing": "DsCmpAllCurNoShare",
             "f3 holdout: MAVRA, G8 on current data - trajectory": "DsCmpHoldoutCurTraj",
             "f4 modeled: MAVRA, G8 on current data - trajectory+self-check": "DsCmpModeledCurVerify",
             "f5 all: MAVRA, G8 on current data - trajectory+self-check": "DsCmpAllCurVerify",
             "g1 modeled: MAVRA - trajectory": "DsCmpModeledTraj",
             "g2 modeled: MAVRA - MAVRA, G8 on current data": "DsCmpModeledCur",
             "h1 modeled: MAVRA - definition-level": "DsCmpModeledDef",
             "h2 all: MAVRA - no sharing": "DsCmpAllNoShare",
             "h3 holdout: MAVRA - trajectory": "DsCmpHoldoutTraj",
             "h4 modeled: MAVRA - trajectory+self-check": "DsCmpModeledCondVerify",
             "h5 all: MAVRA - trajectory+self-check": "DsCmpAllCondVerify",
             "h6 modeled: MAVRA - MAVRA (gold SQL)": "DsCmpModeledGold"}
    for label, name in names.items():
        c = res["comparisons"].get(label)
        if c:
            q[name] = f"{100 * c['diff']:.0f}"
            q[name + "Lo"] = f"{100 * c['ci95'][0]:.0f}"
            q[name + "Hi"] = f"{100 * c['ci95'][1]:.0f}"
    with open(os.path.join(out, "scen-ds.tex"), "w", encoding="utf-8") as f:
        f.write("% generated by tools/scen-stats.py; do not edit\n")
        for k, v in q.items():
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scen", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--reps", type=int, default=4000)
    ap.add_argument("--tex-out", default=None)
    o = ap.parse_args()
    raw, skipped = load(o.scen)
    by = collections.defaultdict(list)
    for c in raw:
        by[c["d"]["mode"]].append(cell_stats(c))
    rnd = random.Random(20261002)
    res = {"cells": {m: len(by[m]) for m in METHODS if m in by}, "replaced_cells_excluded": len(skipped), "methods": {}, "comparisons": {},
           "per_change": {}}
    boots = {}
    for m in METHODS:
        if m not in by:
            continue
        cs = by[m]
        row = {"name": NAMES[m], "cells": len(cs), "provider_errors": sum(c["errors"] for c in cs)}
        for g, ps in GROUPS.items():
            b = boot(cs, ps, o.reps, rnd)
            boots[(m, g)] = b
            v = rate(cs, ps)
            row[g] = {"acc": v, "ci95": ci(b)}
        row["stale_tasks"] = {g: sum(c["stale"].get(p, 0) for c in cs for p in ps) for g, ps in GROUPS.items() if g != "all"}
        row["revoked_per_cell"] = sum(c["revoked"] for c in cs) / len(cs)
        row["repaired_per_cell"] = sum(c["repaired"] for c in cs) / len(cs)
        row["maint_db_s_per_cell"] = sum(c["maint_s"] for c in cs) / len(cs)
        allt = [t for c in cs for t in c["turns"]]
        allk = [t for c in cs for t in c["tokens"]]
        row["turns_per_task"] = sum(allt) / len(allt) if allt else None
        row["input_tokens_per_task"] = sum(allk) / len(allk) if allk else None
        res["methods"][m] = row
        res["per_change"][m] = {p: rate(cs, [p]) for p in PHASES}

    def diff(a, b, g):
        if (a, g) not in boots or (b, g) not in boots:
            return None
        xa, xb = boots[(a, g)], boots[(b, g)]
        n = min(len(xa), len(xb))
        ds = [xa[i] - xb[i] for i in range(n)]
        point = res["methods"][a][g]["acc"] - res["methods"][b][g]["acc"]
        return {"diff": point, "ci95": ci(ds)}

    res["comparisons"] = {
        # 预先写定的分析方案（a–c 为主实验，d、e 为 2026-10-03 增补；见 exp/2026-10-02-scenarios-ds/README.md）
        "a1 modeled: MAVRA (gold SQL) - trajectory": diff("metric-global", "traj-global", "modeled"),
        "a2 modeled: MAVRA (gold SQL) - definition-level": diff("metric-global", "metric-global-def", "modeled"),
        "b all: MAVRA (gold SQL) - no sharing": diff("metric-global", "middle", "all"),
        "c holdout: MAVRA (gold SQL) - trajectory": diff("metric-global", "traj-global", "holdout"),
        "d1 modeled: MAVRA, G8 on current data - trajectory": diff("metric-global-exref", "traj-global", "modeled"),
        "d2 modeled: MAVRA, G8 on current data - MAVRA (gold SQL)": diff("metric-global-exref", "metric-global", "modeled"),
        "e1 modeled: trajectory+self-check - trajectory": diff("traj-verify", "traj-global", "modeled"),
        "e2 modeled: MAVRA (gold SQL) - trajectory+self-check": diff("metric-global", "traj-verify", "modeled"),
        "e3 all: MAVRA (gold SQL) - trajectory+self-check": diff("metric-global", "traj-verify", "all"),
        # 2026-10-06 补算：G8 在当前数据上比较的 MAVRA 与其余方法的同口径比较，不在预先写定的方案内
        "f1 modeled: MAVRA, G8 on current data - definition-level": diff("metric-global-exref", "metric-global-def", "modeled"),
        "f2 all: MAVRA, G8 on current data - no sharing": diff("metric-global-exref", "middle", "all"),
        "f3 holdout: MAVRA, G8 on current data - trajectory": diff("metric-global-exref", "traj-global", "holdout"),
        "f4 modeled: MAVRA, G8 on current data - trajectory+self-check": diff("metric-global-exref", "traj-verify", "modeled"),
        "f5 all: MAVRA, G8 on current data - trajectory+self-check": diff("metric-global-exref", "traj-verify", "all"),
        # 2026-10-06 晚，metric-global-snap 启动前写定（README 分析方案增补）
        "g1 modeled: MAVRA - trajectory": diff("metric-global-snap", "traj-global", "modeled"),
        "g2 modeled: MAVRA - MAVRA, G8 on current data": diff("metric-global-snap", "metric-global-exref", "modeled"),
        # 同口径补算，不在预先写定的方案内
        "h1 modeled: MAVRA - definition-level": diff("metric-global-snap", "metric-global-def", "modeled"),
        "h2 all: MAVRA - no sharing": diff("metric-global-snap", "middle", "all"),
        "h3 holdout: MAVRA - trajectory": diff("metric-global-snap", "traj-global", "holdout"),
        "h4 modeled: MAVRA - trajectory+self-check": diff("metric-global-snap", "traj-verify", "modeled"),
        "h5 all: MAVRA - trajectory+self-check": diff("metric-global-snap", "traj-verify", "all"),
        "h6 modeled: MAVRA - MAVRA (gold SQL)": diff("metric-global-snap", "metric-global", "modeled"),
    }
    res["comparisons"] = {k: v for k, v in res["comparisons"].items() if v is not None}
    if o.json:
        json.dump(res, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if o.tex_out:
        tex(res, o.tex_out)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
