#!/usr/bin/env python3
"""声明了指标修订的回答，是否真的按该修订作答（不调用 LLM，读场景评测已有记录）。

用法：python3 tools/declared-use.py RESULTS_DIR [--json OUT]

对条件级与定义级组（cell-*-metric-global[-def]-named.json）的留出与变化阶段记录：
- 定义是否答对：阶段开始与结束时的审计（规范 SQL 在该阶段数据上逐题比对标准答案）里，同一 (键, 修订) 在该题上是否答对；
- 回答是否答对：记录的 outcome。
四类：follow（定义对、回答对）、deviate（定义对、回答错：声明了有效修订但没按它答）、
override（定义错、回答对）、stale（定义错、回答错）。只统计声明了同一指标的定义的记录；声明了别的指标或未声明单列。
"""

import argparse
import collections
import glob
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--json", default=None)
    o = ap.parse_args()
    files = sorted(glob.glob(os.path.join(o.results, "**", "cell-*-metric-global-named.json"), recursive=True)
                   + glob.glob(os.path.join(o.results, "**", "cell-*-metric-global-def-named.json"), recursive=True))
    total = collections.Counter()
    by_mode = collections.defaultdict(collections.Counter)
    by_model = collections.defaultdict(collections.Counter)
    examples = []
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        model = os.path.basename(os.path.dirname(os.path.dirname(f))).split("-r")[0]
        mode = d["mode"]
        # (键, 修订) → (指标, 该阶段答错的题)
        audit = {}
        for phase, rows in d["audits"].items():
            base = phase[:-4] if phase.endswith("_end") else phase
            for a in rows:
                audit.setdefault((base, a["key"], a["revision"]), (a["metric_def"], set(a["wrong_on"])))
        for r in d["records"]:
            if r["phase"] == "learn" or r["phase"].endswith("-relearn") or r.get("error"):
                continue
            mdef = r["task"].split("-")[0]
            declared = [tuple(x) for x in r["metric_use"]["declared"]]
            own = [(k, v) for k, v in declared if audit.get((r["phase"], k, v), ("", set()))[0] == mdef]
            if not declared:
                cat = "undeclared"
            elif not own:
                cat = "declared_other_or_unaudited"
            else:
                def_ok = any(r["task"] not in audit[(r["phase"], k, v)][1] for k, v in own)
                ans_ok = r["outcome"] == "correct"
                cat = {(True, True): "follow", (True, False): "deviate", (False, True): "override", (False, False): "stale"}[(def_ok, ans_ok)]
                if cat == "deviate" and len(examples) < 12:
                    examples.append({"file": f.split("results/")[-1], "task": r["task"], "phase": r["phase"], "declared": own,
                                     "answer": r["answer"], "gold": r["gold"], "sql": ((r["run"] or {}).get("sql") or "")[:400]})
            total[cat] += 1
            by_mode[mode][cat] += 1
            by_model[model][cat] += 1
    decl = sum(total[k] for k in ("follow", "deviate", "override", "stale"))
    res = {
        "cells": len(files), "records": sum(total.values()), "counts": dict(total),
        "declared_own": decl,
        "deviate_pct_of_declared_own": round(100 * total["deviate"] / decl, 1) if decl else None,
        "deviate_pct_of_valid_def": round(100 * total["deviate"] / (total["follow"] + total["deviate"]), 1) if decl else None,
        "by_mode": {k: dict(v) for k, v in by_mode.items()},
        "by_model": {k: dict(v) for k, v in by_model.items()},
        "deviate_examples": examples,
    }
    if o.json:
        json.dump(res, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
