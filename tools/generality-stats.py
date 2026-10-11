#!/usr/bin/env python3
"""通用性回放的统计：TPC-H、SSB 与 BIRD financial 上的定义库回放（replay-bench --spec），写 overleaf/gen/generality.tex。

用法：python3 tools/generality-stats.py [--exp exp/2026-10-11-generality] [--out overleaf/gen]
输入（均在 --exp 下）：
  libs/<s>.json                      由该基准自己的查询导出的定义库（tools/bench-library.py）
  libs/<s>-kept.json                 支持度筛选后的库（tools/bench-support.py：学习题答案非空、非零）
  <s>-replay-report.json.gz          回放报告（各维护方式 × 11 种变化）
  ssb-contiguity.json                SSB 日期维度上“日期键按月连续”检查的结果
输出：
  overleaf/gen/generality.tex        \\Gn* 宏：各模式与三者合计的定义数、题数、各方法结果、修复题数、维护 DB 秒
  <exp>/generality-stats.json        各模式与合并后的 replay-stats（图 3 第三个面板读合并后的 task_level_common）
口径与 tools/review-results.py 的 \\Tr* 相同：题次取各组共同的题；“覆盖的变化下答错”不计单位变化。
"""

import argparse
import collections
import gzip
import json
import os
import subprocess
import sys
import tempfile

SCHEMAS = [("tpch", "Th"), ("ssb", "Sb"), ("financial", "Fi")]
GROUPS = [("Cond", "condition/snapshot"), ("Schema", "schema/snapshot"), ("Revoke", "revoke/snapshot"), ("Table", "tabletest/snapshot")]
CLASSES = [("Correct", "correct"), ("Wrong", "served_wrong"), ("Needed", "unavailable_needed"), ("Unneeded", "unavailable_unneeded")]


def fmt(x, nd=1):
    if isinstance(x, int):
        return f"{x:,}".replace(",", "{,}")
    return f"{x:.{nd}f}"


def replay_stats(report):
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "r.json"), os.path.join(d, "s.json")
        json.dump(report, open(src, "w", encoding="utf-8"))
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([sys.executable, os.path.join(here, "replay-stats.py"), src, "--json", out], check=True, stdout=subprocess.DEVNULL)
        return json.load(open(out, encoding="utf-8"))


def key_of(x):
    return (x["lib"], x["change"], x["entry"], x["task"])


def macros(m, prefix, report, stats):
    outs = report["outcomes"]
    tl = stats["task_level_common"]
    groups = {(x["policy"], x["oracle"]) for x in outs}
    keys = [{key_of(x) for x in outs if (x["policy"], x["oracle"]) == g} for g in groups]
    common = set.intersection(*keys)
    for key, g in GROUPS:
        t = tl[g]
        m[f"{prefix}{key}N"] = t["n"]
        for suffix, field in CLASSES:
            m[f"{prefix}{key}{suffix}"] = t[field]
        m[f"{prefix}{key}DB"] = stats["maintenance_db_s"][g]["total"]
        m[f"{prefix}{key}WrongModeled"] = sum(1 for x in outs if f"{x['policy']}/{x['oracle']}" == g and x["class"] == "served_wrong"
                                              and x["change"] != "unit" and key_of(x) in common)
    cond = [x for x in outs if x["policy"] == "condition" and key_of(x) in common]
    # MAVRA 在单位变化以外的答错来自哪些定义（库 × 条目）
    m[f"{prefix}CondWrongModeledDefs"] = len({(x["lib"], x["entry"]) for x in cond if x["class"] == "served_wrong" and x["change"] != "unit"})
    m[f"{prefix}CondRepairedTasks"] = sum(1 for x in cond if x["repaired"])
    m[f"{prefix}CondRepairedDefs"] = len({(x["lib"], x["change"], x["entry"]) for x in cond if x["repaired"]})
    m[f"{prefix}CondInvalidatedDefs"] = len({(x["lib"], x["change"], x["entry"]) for x in cond
                                             if x["class"].startswith("unavailable") and x["change"] != "unit"})


COVERED = ["status", "revision", "dupload", "dimhist", "latekey"]
E2E_MODES = [("Cond", "metric-global-snap"), ("Traj", "traj-global"), ("NoShare", "middle")]


def e2e_macros(m, exp):
    """TPC-H 端到端（e2e/）：各方法逐次运行的正确率区间（最小–最大）与合并值、留出题每次运行的提速与 token 节省区间、
    MAVRA 每次运行的修复与失效数。合并值与区间口径同 tools/scen-stats.py（每种变化等权；覆盖破坏 = 五种已建模变化）。"""
    recs = json.load(gzip.open(os.path.join(exp, "e2e", "outcomes.json.gz"), "rt", encoding="utf-8"))["records"]
    stats = json.load(open(os.path.join(exp, "e2e", "scen-stats.json"), encoding="utf-8"))
    scored = [x for x in recs if x["phase"] != "learn" and not x["phase"].endswith("relearn") and x["outcome"] != "error"]
    runs = sorted({x["run"].split("-")[0] for x in scored})
    m["GeRuns"] = len(runs)
    m["GeTasks"] = sum(1 for x in scored if x["mode"] == "metric-global-snap")

    def acc(xs, phases):
        per = []
        for p in phases:
            ps = [x for x in xs if x["phase"] == p]
            if ps:
                per.append(sum(x["outcome"] == "correct" for x in ps) / len(ps))
        return 100 * sum(per) / len(per)

    for key, mode in E2E_MODES:
        v = stats["methods"][mode]
        for g, name in (("modeled", "Modeled"), ("holdout", "Holdout"), ("all", "All"), ("mirror", "Mirror")):
            m[f"Ge{key}{name}"] = round(100 * v[g]["acc"])
        for g, name, phases in (("modeled", "Modeled", COVERED), ("holdout", "Holdout", ["holdout"])):
            vals = [acc([x for x in scored if x["mode"] == mode and x["run"].startswith(r + "-")], phases) for r in runs]
            m[f"Ge{key}{name}Min"], m[f"Ge{key}{name}Max"] = round(min(vals)), round(max(vals))
        for ch in ("dupload", "revision"):
            m[f"Ge{key}{ch.capitalize()}"] = round(acc([x for x in scored if x["mode"] == mode], [ch]))
    g1 = stats["comparisons"]["g1 modeled: MAVRA - trajectory"]
    m["GeCmpModeledTraj"], m["GeCmpModeledTrajLo"], m["GeCmpModeledTrajHi"] = (round(100 * g1["diff"]), round(100 * g1["ci95"][0]),
                                                                               round(100 * g1["ci95"][1]))
    # 留出题：同一轮次里 MAVRA 与独自探索的每题平均秒数与 token 之比
    speed, save = [], []
    for r in runs:
        def mean(mode, f):
            xs = [f(x) for x in scored if x["mode"] == mode and x["run"].startswith(r + "-") and x["phase"] == "holdout"]
            return sum(xs) / len(xs)
        speed.append(mean("middle", lambda x: x["seconds"]) / mean("metric-global-snap", lambda x: x["seconds"]))
        tok = lambda x: x["input_tokens"] + x["output_tokens"]
        save.append(100 * (1 - mean("metric-global-snap", tok) / mean("middle", tok)))
    m["GeHoldSpeedupMin"], m["GeHoldSpeedupMax"] = round(min(speed), 1), round(max(speed), 1)
    m["GeHoldTokSaveMin"], m["GeHoldTokSaveMax"] = round(min(save)), round(max(save))
    v = stats["methods"]["metric-global-snap"]
    reps = [c["repaired"] for c in v["runs"]] if v.get("runs") and "repaired" in v["runs"][0] else None
    m["GeRepairedPerRun"] = round(v["repaired_per_cell"], 1)
    m["GeRevokedPerRun"] = round(v["revoked_per_cell"], 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="exp/2026-10-11-generality")
    ap.add_argument("--out", default="overleaf/gen")
    o = ap.parse_args()
    m, merged, per = {}, None, {}
    totals = collections.Counter()
    for name, prefix in SCHEMAS:
        lib = json.load(open(os.path.join(o.exp, "libs", f"{name}.json"), encoding="utf-8"))
        kept = json.load(open(os.path.join(o.exp, "libs", f"{name}-kept.json"), encoding="utf-8"))
        report = json.load(gzip.open(os.path.join(o.exp, f"{name}-replay-report.json.gz"), "rt", encoding="utf-8"))
        stats = replay_stats(report)
        per[name] = stats
        seeded = [s for s in report["seeds"] if s["policy"] == "condition"][0]["seeded"]
        m[f"Gn{prefix}Queries"] = lib["templates"]
        m[f"Gn{prefix}Derived"] = len(lib["metric_report"]["entries"])
        m[f"Gn{prefix}Kept"] = len(kept["metric_report"]["entries"])
        m[f"Gn{prefix}Seeded"] = seeded
        macros(m, f"Gn{prefix}", report, stats)
        for k in ("Queries", "Derived", "Kept", "Seeded"):
            totals[k] += m[f"Gn{prefix}{k}"]
        if merged is None:
            merged = {k: v for k, v in report.items() if k not in ("outcomes", "maintenance", "libraries", "seeds")}
            merged.update({"outcomes": [], "maintenance": [], "libraries": [], "seeds": []})
        for k in ("outcomes", "maintenance", "libraries", "seeds"):
            merged[k] += report[k]
    for k, v in totals.items():
        m[f"Gn{k}"] = v
    pooled = replay_stats(merged)
    per["pooled"] = pooled
    macros(m, "Gn", merged, pooled)
    e2e_macros(m, o.exp)
    check = json.load(open(os.path.join(o.exp, "tpcds-check.json"), encoding="utf-8"))
    gen = check["generator_on_tpcds"]
    assert gen["differing_outcome_class_vs_hand_written"] == 0 and check["regression_check"]["differing_class_repaired_or_value"] == 0
    m["GnDsGenQuestions"] = gen["questions"]
    contig = json.load(open(os.path.join(o.exp, "ssb-contiguity.json"), encoding="utf-8"))
    m["GnSsbContigBad"] = contig["n_bad"]
    m["GnSsbMonths"] = contig["n_months"]
    json.dump(per, open(os.path.join(o.exp, "generality-stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = ["% generated by tools/generality-stats.py from exp/2026-10-11-generality; do not edit"]
    for k in sorted(m):
        v = m[k]
        lines.append(f"\\newcommand{{\\{k}}}{{{fmt(v)}}}")
    open(os.path.join(o.out, "generality.tex"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({k: m[k] for k in sorted(m) if (k.startswith("Gn") and not k[2:4] in ("Th", "Sb", "Fi")) or k.startswith("Ge")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
