#!/usr/bin/env python3
"""通用验证缓存基线（maint-bench 的 definition-cache 策略）的汇总。

用法：python3 tools/cache-baseline-stats.py DIR [DIR ...] [--json OUT]
DIR 为 maint-bench 的输出目录（含 maint-*/cell-*.json），可给多个（如共享度扫描、零共享对照、4M）。

每组（共享度 k × 维护方式 × 到达方式）汇总各次变化后的使用期：中间层 DB 时间、等待维护的总时长、
过期使用、误撤销、不可用；并给出相对同一 (目录, k, 到达方式) 下定义级的 DB 时间比例。
"""

import argparse
import collections
import glob
import json
import os

POLICIES = ["definition", "definition-cache", "condition-scope", "condition"]


def load(d):
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "**", "cell-*.json"), recursive=True)):
        c = json.load(open(f, encoding="utf-8"))
        ev = c.get("events", [])
        rows.append({
            "dir": os.path.basename(os.path.normpath(d)), "cell": c["cell"], "share": c.get("share"), "policy": c["policy"],
            "arrival": c["arrival"], "repeat": c.get("repeat", 1), "specs": c.get("specs"),
            "db_s": sum(e["db"]["ms"] for e in ev) / 1000.0,
            "queries": sum(e["db"]["queries"] for e in ev),
            "wait_s": sum(e.get("wait_ms", 0) for e in ev) / 1000.0,
            "uses": sum(e.get("uses", 0) for e in ev),
            "stale": sum(e.get("stale_uses", 0) for e in ev),
            "false_revocations": sum(e.get("false_revocations", 0) for e in ev),
            "unavailable": sum(e.get("unavailable_uses", 0) for e in ev),
            "per_change_db_s": {e["event"]: round(e["db"]["ms"] / 1000.0, 2) for e in ev},
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--json", default=None)
    o = ap.parse_args()
    rows = [r for d in o.dirs for r in load(d)]
    groups = collections.defaultdict(dict)
    for r in rows:
        groups[(r["dir"], r["share"], r["arrival"])].setdefault(r["policy"], []).append(r)
    table = []
    for (d, k, arr), byp in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1] or 0, x[0][2])):
        mean = lambda xs, f: sum(f(x) for x in xs) / len(xs)
        base = mean(byp["definition"], lambda x: x["db_s"]) if "definition" in byp else None
        for p in POLICIES:
            if p not in byp:
                continue
            xs = byp[p]
            db = mean(xs, lambda x: x["db_s"])
            table.append({
                "dir": d, "share": k, "arrival": arr, "policy": p, "repeats": len(xs), "specs": xs[0]["specs"],
                "db_s": round(db, 1), "vs_definition": round(db / base, 3) if base else None,
                "wait_s": round(mean(xs, lambda x: x["wait_s"]), 1),
                "uses": sum(x["uses"] for x in xs), "stale": sum(x["stale"] for x in xs),
                "false_revocations": sum(x["false_revocations"] for x in xs), "unavailable": sum(x["unavailable"] for x in xs),
            })
    res = {"rows": table, "cells": rows}
    if o.json:
        json.dump(res, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    hdr = ["dir", "k", "arrival", "policy", "specs", "DB s", "vs def", "wait s", "uses", "stale", "false rev", "unavail"]
    print(" | ".join(hdr))
    for t in table:
        print(" | ".join(str(x) for x in [t["dir"], t["share"], t["arrival"], t["policy"], t["specs"], t["db_s"], t["vs_definition"],
                                          t["wait_s"], t["uses"], t["stale"], t["false_revocations"], t["unavailable"]]))


if __name__ == "__main__":
    main()
