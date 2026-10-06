#!/usr/bin/env python3
"""把另一次定义库回放中的若干组并入一份回放报告。

用法：python3 tools/merge-replay.py BASE.json OTHER.json[.gz] --groups condition/example,condition/judge --out MERGED.json

前提：两次回放用同一个定义库、同一组变化、同一批留出题（回放不调用大模型，结果是确定性的）；脚本核对库、
变化与被并入组的题目都在 BASE 中出现，否则报错。被并入的组若在 BASE 中已存在也报错。
"""

import argparse
import gzip
import json


def load(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("other")
    ap.add_argument("--groups", required=True)
    ap.add_argument("--out", required=True)
    o = ap.parse_args()
    base, other = load(o.base), load(o.other)
    groups = {tuple(g.split("/")) for g in o.groups.split(",")}
    libs = lambda r: sorted((l["id"], tuple(e["name"] for e in l["entries"])) for l in r["libraries"])
    if libs(base) != libs(other):
        raise SystemExit("两份报告的定义库不同")
    if [c["name"] for c in base["changes"]] != [c["name"] for c in other["changes"]]:
        raise SystemExit("两份报告的变化不同")
    have = {(x["policy"], x["oracle"]) for x in base["outcomes"]}
    if groups & have:
        raise SystemExit(f"BASE 中已有这些组：{sorted(groups & have)}")
    tasks = {(x["lib"], x["change"], x["entry"], x["task"]) for x in base["outcomes"]}
    add = [x for x in other["outcomes"] if (x["policy"], x["oracle"]) in groups]
    missing = [x for x in add if (x["lib"], x["change"], x["entry"], x["task"]) not in tasks]
    if missing:
        raise SystemExit(f"被并入组中有 {len(missing)} 道题不在 BASE 中")
    base["outcomes"] += add
    base["maintenance"] += [x for x in other["maintenance"] if (x["policy"], x["oracle"]) in groups]
    base["seeds"] += [x for x in other.get("seeds", []) if (x["policy"], x["oracle"]) in groups]
    base["merged_from"] = {"source": o.other, "groups": sorted("/".join(g) for g in groups), "outcomes": len(add)}
    with open(o.out, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False)
    print(f"并入 {len(add)} 道题次（{', '.join(sorted('/'.join(g) for g in groups))}）→ {o.out}")


if __name__ == "__main__":
    main()
