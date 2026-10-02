#!/usr/bin/env python3
"""场景主实验的统计，按 exp/2026-10-02-scenarios-ds/README.md 中预先写定的分析方案。

用法：python3 tools/scen-stats.py --scen results/scen-20261002 [--json OUT] [--reps 4000]

- 计分题：留出题与各变化下重问的题；学习题与重新学习题不计分。
- 服务端失败的题（outcome = error）不计分，单列数量；replaced.txt 中被整组重跑替换的原组不计。
- 每种方法的正确率：每种变化（含留出）等权平均；另给“已建模的破坏性变化”（status、revision、dupload、dimhist、latekey）
  与留出、正常变化、备份副本、单位变化各自的正确率。
- 95% 区间：按组（方法 × 重复）整群自助法：同一方法的组有放回重抽，组内题目整体带入。
- 预先声明的比较：(a) 已建模破坏性变化下 条件级 − 轨迹检索、条件级 − 定义级；(b) 全部情形 条件级 − 不共享；
  (c) 留出题 条件级 − 轨迹检索。差值的区间对两种方法各自独立整群重抽。
"""

import argparse
import collections
import glob
import json
import os
import random

METHODS = ["middle", "traj-global", "metric-global-noguard", "metric-global-schema", "metric-global-revoke", "metric-global-def",
           "metric-global"]
NAMES = {"middle": "No sharing", "traj-global": "Trajectory retrieval", "metric-global-noguard": "Unguarded",
         "metric-global-schema": "Schema-only", "metric-global-revoke": "Revoke-on-write", "metric-global-def": "Definition-level",
         "metric-global": "MAVRA (condition-level)"}
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scen", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--reps", type=int, default=4000)
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
        "a1 modeled: MAVRA - trajectory": diff("metric-global", "traj-global", "modeled"),
        "a2 modeled: MAVRA - definition-level": diff("metric-global", "metric-global-def", "modeled"),
        "b all: MAVRA - no sharing": diff("metric-global", "middle", "all"),
        "c holdout: MAVRA - trajectory": diff("metric-global", "traj-global", "holdout"),
    }
    if o.json:
        json.dump(res, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
