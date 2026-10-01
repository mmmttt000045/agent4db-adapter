#!/usr/bin/env python3
"""快照绑定实验（postgres_snapshot_binding）的汇总表。

用法：python3 tools/snapshot-stats.py REPORT.json [--json OUT]

- 交错：每种交错 × 模式的 served / violation / rejected 次数（violation = 答案所在数据违反所引用修订的粒度条件）。
- 随机并发：每种写者协议（提交后通知 / 不通知）× 模式的调用分类，violation 的次数与 Wilson 95% 上界。
- 读者开销：无写入与良性写入后的调用延迟（两轮的中位数取平均）。
- 写者开销：有无版本触发器时单行语句吞吐（顺序 / 8 并发）与批量语句耗时，三轮取中位数。
"""

import argparse
import collections
import json
import math
import statistics


def wilson_upper(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round(100 * (c + r) / d, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--json", default=None)
    o = ap.parse_args()
    r = json.load(open(o.report, encoding="utf-8"))
    res = {"rows": r["rows"], "trials": r["trials"]}
    res["interleavings"] = [
        {"case": x["case"], "mode": x["mode"], **{k: x["counts"].get(k, 0) for k in ("served", "violation", "rejected", "error")},
         "latency_p50_ms": round(x["latency_ms"]["p50"], 1)}
        for x in r["interleavings"]
    ]
    st = []
    for x in r["stress"]:
        c = x["counts"]
        answered = c.get("served", 0) + c.get("violation", 0)
        st.append({"notify": x["notify"], "mode": x["mode"], "trials": x["trials"], "calls": sum(c.values()),
                   "served": c.get("served", 0), "violation": c.get("violation", 0), "rejected": c.get("rejected", 0),
                   "error": c.get("error", 0),
                   "violation_pct_of_answered": round(100 * c.get("violation", 0) / answered, 2) if answered else None,
                   "violation_wilson95_upper_pct": wilson_upper(c.get("violation", 0), answered),
                   "trials_with_violation": sum(1 for t in x["per_trial"] if t["counts"].get("violation", 0) > 0),
                   "violation_start_minus_commit_ms": x["violation_start_minus_commit_ms"]})
    res["stress"] = st
    ro = collections.defaultdict(lambda: collections.defaultdict(list))
    for x in r["reader_overhead"]:
        for k in ("steady_ms", "first_after_write_ms", "second_after_write_ms"):
            ro[x["mode"]][k].append(x[k]["p50"])
    res["reader_p50_ms"] = {m: {k: round(statistics.mean(v), 1) for k, v in d.items()} for m, d in ro.items()}
    wo = collections.defaultdict(lambda: collections.defaultdict(list))
    for x in r["writer_overhead"]:
        for k in ("sequential_stmt_per_s", "concurrent8_stmt_per_s", "bulk_ms_per_stmt"):
            wo["trigger" if x["trigger"] else "no_trigger"][k].append(x[k])
    res["writer_median"] = {m: {k: round(statistics.median(v), 1) for k, v in d.items()} for m, d in wo.items()}
    if "trigger" in res["writer_median"] and "no_trigger" in res["writer_median"]:
        a, b = res["writer_median"]["trigger"], res["writer_median"]["no_trigger"]
        res["writer_ratio_trigger_over_none"] = {k: round(a[k] / b[k], 2) for k in a}
    if o.json:
        json.dump(res, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
