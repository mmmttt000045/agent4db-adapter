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
    contig = json.load(open(os.path.join(o.exp, "ssb-contiguity.json"), encoding="utf-8"))
    m["GnSsbContigBad"] = contig["n_bad"]
    m["GnSsbMonths"] = contig["n_months"]
    json.dump(per, open(os.path.join(o.exp, "generality-stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = ["% generated by tools/generality-stats.py from exp/2026-10-11-generality; do not edit"]
    for k in sorted(m):
        v = m[k]
        lines.append(f"\\newcommand{{\\{k}}}{{{fmt(v)}}}")
    open(os.path.join(o.out, "generality.tex"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({k: m[k] for k in sorted(m) if k.startswith("Gn") and not k[2:4] in ("Th", "Sb", "Fi")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
