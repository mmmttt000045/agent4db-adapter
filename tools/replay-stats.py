#!/usr/bin/env python3
"""配对回放（replay-bench）的统计：同一指标库、同一变化、同一留出题上，各维护方式的结果配对比较。

用法：python3 tools/replay-stats.py REPORT.json [--json OUT]

口径：
- 题次级：correct / served_wrong / unavailable_needed / unavailable_unneeded（见 replay-bench 报告的 methodology）。
- 定义级（库 × 变化 × 条目）：原定义在变化后至少答错一题 = 需要处理；处理结果按条目的全部受影响题目归为
  全部答对（served_ok）/ 提供且有题答错（served_wrong）/ 不可用（unavailable）。
- 配对差异：条件级（每种 G8 参照）与其余每一组在同一 (库, 变化, 条目, 题) 上逐题比较；答对率之差的 95% 区间按库做
  整群自助法。
- 维护 DB 时间的比值以条件级在主参照下的组为分母（有 condition/example 时取它，否则 condition/judge）。
"""

import argparse
import collections
import json
import random

CLASSES = ["correct", "served_wrong", "unavailable_needed", "unavailable_unneeded"]


def model_of(lib):
    return lib.split("-r")[0]


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def cluster_ci(pairs, libs, reps=2000, seed=7):
    """pairs: lib -> list of (x, y) 0/1；返回答对率之差 x - y 的点估计与 95% 区间（按库重抽）。"""
    rng = random.Random(seed)

    def diff(sample):
        xs = [p for l in sample for p in pairs.get(l, [])]
        return (sum(x for x, _ in xs) - sum(y for _, y in xs)) / len(xs) if xs else 0.0

    point = diff(libs)
    boots = sorted(diff([rng.choice(libs) for _ in libs]) for _ in range(reps))
    return round(100 * point, 1), [round(100 * boots[int(0.025 * reps)], 1), round(100 * boots[int(0.975 * reps) - 1], 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--json", default=None)
    o = ap.parse_args()
    r = json.load(open(o.report, encoding="utf-8"))
    outs = r["outcomes"]
    groups = sorted({(x["policy"], x["oracle"]) for x in outs})
    libs = sorted({x["lib"] for x in outs})
    res = {"libraries": len(libs), "groups": [f"{p}/{q}" for p, q in groups]}

    # 题次级
    task = {}
    for g in groups:
        c = collections.Counter(x["class"] for x in outs if (x["policy"], x["oracle"]) == g)
        n = sum(c.values())
        task[f"{g[0]}/{g[1]}"] = {"n": n, **{k: c[k] for k in CLASSES}, **{k + "_pct": pct(c[k], n) for k in CLASSES}}
    res["task_level"] = task
    # 共同题次：每一组都有结果的 (库, 变化, 条目, 题)；只在部分参照下准入的条目不计，各组在同一批题上比较
    keys = {g: {(x["lib"], x["change"], x["entry"], x["task"]) for x in outs if (x["policy"], x["oracle"]) == g} for g in groups}
    common = set.intersection(*keys.values()) if keys else set()
    task_c = {}
    for g in groups:
        c = collections.Counter(x["class"] for x in outs
                                if (x["policy"], x["oracle"]) == g and (x["lib"], x["change"], x["entry"], x["task"]) in common)
        n = sum(c.values())
        task_c[f"{g[0]}/{g[1]}"] = {"n": n, **{k: c[k] for k in CLASSES}, **{k + "_pct": pct(c[k], n) for k in CLASSES}}
    res["task_level_common"] = task_c

    # 定义级
    by_def = collections.defaultdict(list)
    for x in outs:
        by_def[(x["policy"], x["oracle"], x["lib"], x["change"], x["entry"])].append(x)
    deflevel = {}
    for g in groups:
        c = collections.Counter()
        for k, xs in by_def.items():
            if (k[0], k[1]) != g:
                continue
            needed = any(not x["orig_ok"] for x in xs)
            if xs[0]["status"] != "valid":
                out = "unavailable"
            elif all(x["class"] == "correct" for x in xs):
                out = "served_ok"
            else:
                out = "served_wrong"
            c[("needed" if needed else "not_needed", out)] += 1
        deflevel[f"{g[0]}/{g[1]}"] = {f"{a}:{b}": n for (a, b), n in sorted(c.items())}
    res["definition_level"] = deflevel

    # 按变化、按模型的答对率
    for name, keyf in (("by_change", lambda x: x["change"]), ("by_model", lambda x: model_of(x["lib"]))):
        t = collections.defaultdict(dict)
        for g in groups:
            c = collections.defaultdict(lambda: [0, 0])
            for x in outs:
                if (x["policy"], x["oracle"]) == g:
                    k = keyf(x)
                    c[k][0] += x["class"] == "correct"
                    c[k][1] += 1
            for k, (a, n) in c.items():
                t[k][f"{g[0]}/{g[1]}"] = {"correct_pct": pct(a, n), "n": n}
        res[name] = dict(sorted(t.items()))

    # 配对：条件级（每种参照）vs 其余每一组
    idx = {(x["policy"], x["oracle"], x["lib"], x["change"], x["entry"], x["task"]): x for x in outs}
    paired = {}
    for oracle in sorted({q for p, q in groups if p == "condition"}):
        for other, q2 in groups:
            if (other, q2) == ("condition", oracle):
                continue
            pairs = collections.defaultdict(list)
            agree = collections.Counter()
            for (p, q, lib, ch, e, t), x in idx.items():
                if (p, q) != ("condition", oracle):
                    continue
                y = idx.get((other, q2, lib, ch, e, t))
                if y is None:
                    continue
                pairs[lib].append((int(x["class"] == "correct"), int(y["class"] == "correct")))
                agree[(x["class"], y["class"])] += 1
            n = sum(len(v) for v in pairs.values())
            b = sum(1 for v in pairs.values() for a, c in v if a and not c)
            c_ = sum(1 for v in pairs.values() for a, c in v if c and not a)
            point, ci = cluster_ci(pairs, libs)
            paired[f"condition/{oracle} vs {other}/{q2}"] = {
                "n": n, "same_class_pct": pct(sum(v for (a, c), v in agree.items() if a == c), n),
                "cond_only_correct": b, "other_only_correct": c_, "correct_diff_pp": point, "ci95_pp": ci,
                "discordant": {f"{a}->{c}": v for (a, c), v in agree.items() if a != c},
            }
    res["paired"] = paired

    # 维护数据库时间
    ms = collections.defaultdict(lambda: collections.defaultdict(float))
    for m in r["maintenance"]:
        ms[f"{m['policy']}/{m['oracle']}"][m["change"]] += m["db_ms"] / 1000.0
    res["maintenance_db_s"] = {g: {"total": round(sum(v.values()), 1), **{k: round(s, 2) for k, s in sorted(v.items())}} for g, v in ms.items()}
    base = "condition/example" if "condition/example" in res["maintenance_db_s"] else "condition/judge"
    cond = res["maintenance_db_s"].get(base, {}).get("total")
    res["maintenance_db_s_base"] = base
    for g, v in res["maintenance_db_s"].items():
        v["vs_condition"] = round(v["total"] / cond, 2) if cond else None

    # 准入
    fails = collections.Counter()
    for s in r.get("seeds", []):
        fails[f"{s['policy']}/{s['oracle']}"] += len(s["failed"])
    res["seed_failures"] = dict(fails)

    if o.json:
        json.dump(res, open(o.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
