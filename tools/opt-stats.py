#!/usr/bin/env python3
"""Summarize a metric-bench cell run in the metric-global-opt mode.

usage: opt-stats.py <opt cell json> [<baseline cell json>]

Prints, per definition, the published optimization candidate with its cost evidence (O6), the
rejected candidates with the failing gate, then per-phase accuracy (and the baseline's, if given),
and for the held-out phase how many user-agent queries adopted the date-key-range form and their
EXPLAIN execution time compared with the baseline run.
"""
import json
import statistics
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def o6(tried):
    for g in tried.get("gates", []):
        if g.get("gate") == "O6":
            return g
    return {}


def summarize_optimizing(cell):
    opt = cell.get("optimizing") or {}
    rounds = opt.get("rounds") or []
    print(f"优化轮：{len(rounds)} 条定义，{opt.get('published')} 条发布，{opt.get('seconds', 0):.0f} 秒")
    print()
    print("| 定义 | 结果 | 候选 | 来源 | 执行时间 ms（当前 → 候选） | 节省 | 95% 区间 ms | 期间数 | 读块（当前 → 候选） |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rounds:
        pub = None
        for t in r.get("tried", []):
            if t.get("event") == "optimize_promoted":
                pub = t
        if pub:
            g = o6(pub)
            ev = g.get("evidence", {})
            ci = ev.get("ci95", [0, 0])
            bl = g.get("blocks", {})
            print(
                f"| {r['key']} | 发布 r{pub['revision']} | {pub['candidate']} | {pub['source']} | "
                f"{ev.get('baseline_ms', 0):.1f} → {ev.get('policy_ms', 0):.1f} | {100 * g.get('saving', 0):.1f}% | "
                f"[{ci[0]:.1f}, {ci[1]:.1f}] | {ev.get('episodes', 0)} | {bl.get('old', 0):.0f} → {bl.get('new', 0):.0f} |"
            )
        else:
            print(f"| {r['key']} | 未发布 | — | — | — | — | — | — | — |")
    print()
    print("被拒绝的候选：")
    for r in rounds:
        for t in r.get("tried", []):
            if t.get("event") == "optimize_rejected":
                g = o6(t)
                extra = ""
                if t.get("gate") == "O6":
                    ev = g.get("evidence", {})
                    extra = f"（{ev.get('baseline_ms', 0):.1f} → {ev.get('policy_ms', 0):.1f} ms，省 {100 * g.get('saving', 0):.1f}%）"
                print(f"- {r['key']}：{t['candidate']}（{t['source']}）→ {t['gate']}：{t.get('reason')}{extra}")
        p = r.get("proposals") or {}
        if p:
            print(f"  模型提议：{p.get('proposed')} 个候选，{p.get('attempts')} 次调用，{p.get('seconds', 0):.0f} 秒，错误 {p.get('errors')}")
    print()


def is_eval(rec):
    return rec.get("phase") not in ("learn",) and not str(rec.get("phase", "")).endswith("-relearn")


def accuracy(cell):
    out = {}
    for rec in cell.get("records", []):
        if not is_eval(rec):
            continue
        ph = rec["phase"]
        n, c = out.get(ph, (0, 0))
        out[ph] = (n + 1, c + (1 if rec.get("outcome") == "correct" else 0))
    return out


def summarize_accuracy(cell, base):
    acc = accuracy(cell)
    bacc = accuracy(base) if base else {}
    print("| 阶段 | 优化模式 正确/题数 | 对照（-snap） |")
    print("| --- | --- | --- |")
    for ph, (n, c) in acc.items():
        b = bacc.get(ph)
        print(f"| {ph} | {c}/{n} | {b[1]}/{b[0] if b else '—'} |" if b else f"| {ph} | {c}/{n} | — |")
    n = sum(v[0] for v in acc.values())
    c = sum(v[1] for v in acc.values())
    print(f"| 全部 | {c}/{n} ({100 * c / n:.0f}%) | ", end="")
    if bacc:
        bn = sum(v[0] for v in bacc.values())
        bc = sum(v[1] for v in bacc.values())
        print(f"{bc}/{bn} ({100 * bc / bn:.0f}%) |")
    else:
        print("— |")
    print()


def holdout_sql(cell, base):
    recs = [r for r in cell.get("records", []) if r.get("phase") == "holdout"]
    adopted = [r for r in recs if "between (select min(" in (r.get("run", {}).get("sql") or "").lower()]
    joined = [r for r in recs if "date_dim" in (r.get("run", {}).get("sql") or "").lower()]
    print(f"留出阶段用户智能体的 SQL：{len(recs)} 题，采用日期键范围写法 {len(adopted)} 题，连接 date_dim {len(joined)} 题")
    ms = [r["explain"]["exec_ms"] for r in recs if r.get("explain") and r["explain"].get("exec_ms") is not None]
    if ms:
        print(f"  EXPLAIN 执行时间：均值 {statistics.mean(ms):.1f} ms，中位数 {statistics.median(ms):.1f} ms")
    if base:
        brecs = [r for r in base.get("records", []) if r.get("phase") == "holdout"]
        bms = [r["explain"]["exec_ms"] for r in brecs if r.get("explain") and r["explain"].get("exec_ms") is not None]
        if bms:
            print(f"  对照（-snap）：均值 {statistics.mean(bms):.1f} ms，中位数 {statistics.median(bms):.1f} ms")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cell = load(sys.argv[1])
    base = load(sys.argv[2]) if len(sys.argv) > 2 else None
    print(f"cell：{cell.get('cell')}，{cell.get('seconds', 0):.0f} 秒；optimizations = {cell.get('stats', {}).get('optimizations')}")
    print()
    summarize_optimizing(cell)
    summarize_accuracy(cell, base)
    holdout_sql(cell, base)


if __name__ == "__main__":
    main()
