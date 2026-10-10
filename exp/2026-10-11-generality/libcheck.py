import json, subprocess, sys
spec, lib, db = sys.argv[1:4]
S = json.load(open(spec)); L = json.load(open(lib))
def q(sql):
    r = subprocess.run(["psql", "-X", "-tA", db, "-c", sql], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "ERROR " + r.stderr.strip().splitlines()[0]
for f in S["facts"]:
    g = ", ".join(f["grain"])
    print("grain", f["table"], q(f"select count(*), count(distinct ({g})) from {f['table']}" if len(f["grain"]) > 1 else f"select count(*), count(distinct {g}) from {f['table']}"))
for d in S["dims"]:
    k = d["key"][0]
    print("dimkey", d["table"], q(f"select count(*), count(distinct {k}) from {d['table']}"), "attr", q(f"select data_type from information_schema.columns where table_name = '{d['table']}' and column_name = '{d['attr']}'"))
cal = S["calendar"]
y0, y1 = S["years"]["learn"], S["years"]["holdout"]
def compile_(m, y, mo):
    frm = m["fact"]
    for j in m["joins"]:
        frm += f" join {j['right']} on " + " and ".join(f"{j['left']}.{a} = {j['right']}.{b}" for a, b in j["on"])
    w = [f"({x})" for x in m["filters"].values()]
    t = m["time"]
    if t.get("strategy") == "column":
        y2, m2 = (y + 1, 1) if mo == 12 else (y, mo + 1)
        w.append(f"{t['fact_col']} >= date '{y}-{mo:02d}-01' and {t['fact_col']} < date '{y2}-{m2:02d}-01'")
    else:
        frm += f" join {t['dim']} on {m['fact']}.{t['fact_col']} = {t['dim']}.{t['dim_col']}"
        w.append(f"{t['dim']}.{t['year_col']} = {y} and {t['dim']}.{t['month_col']} = {mo}")
    return f"select {m['measure']} from {frm} where " + " and ".join(w)
for e in L["metric_report"]["entries"]:
    m = e["metric"]
    print(m["name"], "| learn", q(compile_(m, y0, 3)), "| holdout", q(compile_(m, y1, 9)))
