#!/usr/bin/env python3
"""定义库的支持度筛选（通用性回放的前置步骤）：只保留学习题在初始数据上答案非空、非零的定义。

用法：python3 tools/bench-support.py SPEC LIB DB_URL OUT
  学习题的答案按规范编译的同一写法计算（与 exp/2026-10-11-generality/libcheck.py 相同）。答案为空或为零的定义
  不可能被智能体从这道学习题学到（例如 TPC-H 只在 1995 年前的行上有 l_returnflag = 'R'），保留它们只会让各方法
  在变化后都“答对”同一个常数。被筛掉的定义与原因写进输出的 excluded 字段。
"""
import json
import subprocess
import sys


def main():
    spec, lib, db, out = sys.argv[1:5]
    S = json.load(open(spec))
    L = json.load(open(lib))

    def q(sql):
        r = subprocess.run(["psql", "-X", "-tA", db, "-c", sql], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else "ERROR " + (r.stderr.strip().splitlines() or ["?"])[0]

    def compile_(m, y, mo):
        frm = m["fact"]
        for j in m["joins"]:
            frm += f" join {j['right']} on " + " and ".join(f"{j['left']}.{a} = {j['right']}.{b}" for a, b in j["on"])
        w = [f"({x})" for x in m["filters"].values()]
        for j in m["joins"]:
            w += [f"({x})" for x in j.get("filters", {}).values()]
        t = m["time"]
        if t.get("strategy") == "column":
            y2, m2 = (y + 1, 1) if mo == 12 else (y, mo + 1)
            w.append(f"{t['fact_col']} >= date '{y}-{mo:02d}-01' and {t['fact_col']} < date '{y2}-{m2:02d}-01'")
        else:
            frm += f" join {t['dim']} on {m['fact']}.{t['fact_col']} = {t['dim']}.{t['dim_col']}"
            w.append(f"{t['dim']}.{t.get('year_col', 'd_year')} = {y} and {t['dim']}.{t.get('month_col', 'd_moy')} = {mo}")
        return f"select {m['measure']} from {frm} where " + " and ".join(w)

    kept, excluded = [], []
    for e in L["metric_report"]["entries"]:
        ask = e["evidence"]["ask"]["period"]
        v = q(compile_(e["metric"], ask["year"], ask["m1"]))
        try:
            ok = float(v) != 0.0
        except ValueError:
            ok = False
        (kept if ok else excluded).append(e if ok else {"key": e["key"], "learning_value": v or "NULL"})
    L["metric_report"]["entries"] = kept
    L["excluded"] = excluded
    L["support_rule"] = "学习题在初始数据上的答案非空、非零"
    json.dump(L, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"kept": len(kept), "excluded": excluded}, ensure_ascii=False))


if __name__ == "__main__":
    main()
