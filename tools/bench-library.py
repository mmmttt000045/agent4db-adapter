#!/usr/bin/env python3
"""从一个基准自带的查询导出指标定义库（通用性实验的配对回放负载，exp/2026-10-11-generality）。

用法：python3 tools/bench-library.py --spec SPEC.json --queries SRC --db URL --out LIB.json [--notes NOTES.json] [--db-id ID]
  SPEC     exp/2026-10-11-generality/schemas/<name>.json（事实表、日历、年份）
  SRC      目录（每个 *.sql 一条查询，编号取文件名）或 BIRD 格式的 JSON（question_id、db_id、SQL；按 --db-id 过滤）
  URL      模板库的连接串（读取列、类型与主键）
依赖：pglast（PostgreSQL 解析器，带反解析）、psql。

做法与 tools/tpcds-library.py 相同：一个 SELECT 块里对某张事实表的聚合算一个定义，只取本文的结构化实现能表达的块。
与 TPC-DS 版的差别由模式说明驱动：
  - 事实表由 SPEC 给出；块的事实表是能经多对一关联到达块内全部其他表的那张（其余事实表只能作为一侧出现，
    例如 lineitem → orders 按 o_orderkey 关联）；关联必须落在一侧的主键（维表）或粒度（事实表）上；
  - 关联可以成链（雪花：lineitem → orders → customer → nation），每张表至多出现一次，关联图必须是树；
  - 日历是日期维表时，恰有一个“事实表日期键 = 维表键”的关联作为时间角色，维表上的谓词是期间参数；
    日历是日期列时，块里带日期字面量的谓词所在的列（事实表或其直连表上）是时间列，这些谓词是期间参数；
    没有这样的谓词时取事实表在 SPEC 中的日期列；
  - 度量取块里第一个只引用块内表的聚合；过滤取 WHERE 顶层合取（及 JOIN ON）中只引用一张已关联表的谓词；
  - 度量与过滤里的列一律写成 表.列（financial 的 account_id、date、amount 在多张表里同名）；
  - BIRD 的 SQL 是 SQLite 方言：去掉反引号，表 order 改名 orders，双引号里不是列名或表名的内容按字符串处理。
学习题与留出题的期间取 SPEC 的年份：学习 learn 年 3 月；留出 holdout 年 9 月单期、它与 learn 年 6 月之差、holdout 年月份排名。
"""

import argparse
import json
import os
import re
import subprocess
import sys

try:
    from pglast import ast, parse_sql
    from pglast.enums import BoolExprType
    from pglast.stream import RawStream
except ImportError:  # pragma: no cover
    sys.exit("需要 pglast：pip install --user pglast")

AGGS = {"sum", "avg", "count", "min", "max"}
WORDS = {"sum", "count", "avg", "min", "max", "distinct", "coalesce", "nullif", "case", "when", "then", "else", "end", "and", "or",
         "not", "null", "is", "in", "between", "like", "as", "round", "abs", "filter", "where", "true", "false", "cast", "numeric",
         "decimal", "int", "integer", "bigint", "float", "double", "precision", "real", "text", "varchar"}  # = metric::SQL_WORDS
CMP = {"=", "<>", "!=", "<", ">", "<=", ">="}
RENAME = {"order": "orders"}  # financial：保留字表名
DATE_LIT = re.compile(r"\d{4}-\d{1,2}")


def period_pred(text):
    """谓词是否像期间参数：日期字面量，或年份字面量（SQLite 写法 STRFTIME('%Y', date) = '1997'）。"""
    return bool(DATE_LIT.search(text) or re.search(r"'(19|20)\d{2}'|\b(19|20)\d{2}\b", text))


def psql(db, sql):
    r = subprocess.run(["psql", "-X", "-tA", "-F", "\t", db, "-c", sql], capture_output=True, text=True, check=True)
    return [line.split("\t") for line in r.stdout.splitlines() if line]


def load_schema(db):
    cols, types = {}, {}
    for t, c, ty in psql(db, "select table_name, column_name, data_type from information_schema.columns "
                             "where table_schema = 'public' order by table_name, ordinal_position"):
        cols.setdefault(t, []).append(c)
        types[(t, c)] = ty
    keys = {}
    for t, k in psql(db, "select tc.relname, string_agg(a.attname, ',' order by a.attname) from pg_constraint k "
                         "join pg_class tc on tc.oid = k.conrelid join pg_namespace n on n.oid = tc.relnamespace "
                         "cross join unnest(k.conkey) u(attnum) join pg_attribute a on a.attrelid = tc.oid and a.attnum = u.attnum "
                         "where k.contype = 'p' and n.nspname = 'public' group by tc.relname"):
        keys[t] = tuple(k.split(","))
    return cols, types, keys


def walk(n):
    if isinstance(n, ast.Node):
        yield n
        for f in n.__slots__:
            yield from walk(getattr(n, f, None))
    elif isinstance(n, (list, tuple)):
        for x in n:
            yield from walk(x)


def walk_block(n, top=True):
    if isinstance(n, ast.Node):
        if not top and isinstance(n, ast.SelectStmt):
            return
        yield n
        for f in n.__slots__:
            yield from walk_block(getattr(n, f, None), False)
    elif isinstance(n, (list, tuple)):
        for x in n:
            yield from walk_block(x, False)


def colref(node, aliases, cols_of):
    fields = [f.sval for f in (node.fields or ()) if isinstance(f, ast.String)]
    if not fields or len(fields) != len(node.fields or ()):
        return None
    col = fields[-1].lower()
    if len(fields) >= 2:
        t = aliases.get(fields[-2].lower())
        return (t, col) if t and col in cols_of.get(t, ()) else None
    owners = {t for t in aliases.values() if col in cols_of.get(t, ())}
    return (next(iter(owners)), col) if len(owners) == 1 else None


def tables_of(expr, aliases, cols_of):
    """表达式引用的基表集合；None 表示有解析不到的列引用。"""
    out = set()
    for n in walk(expr):
        if isinstance(n, ast.ColumnRef):
            c = colref(n, aliases, cols_of)
            if c is None:
                return None
            out.add(c[0])
    return out


def cols_in(expr, aliases, cols_of):
    return {colref(n, aliases, cols_of) for n in walk(expr) if isinstance(n, ast.ColumnRef)}


def qualify(expr, aliases, cols_of):
    """把表达式里的列引用改写成 表.列（就地修改 AST）。"""
    for n in walk(expr):
        if isinstance(n, ast.ColumnRef):
            c = colref(n, aliases, cols_of)
            if c:
                n.fields = (ast.String(sval=c[0]), ast.String(sval=c[1]))


def deparse(node):
    return re.sub(r"\s+", " ", RawStream()(node)).strip()


def words_ok(expr, known):
    bare = re.sub(r"'(?:[^']|'')*'", "''", expr)
    return all(w.lower() in WORDS or w.lower() in known for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", bare))


def conjuncts(n):
    if isinstance(n, ast.BoolExpr) and n.boolop == BoolExprType.AND_EXPR:
        for a in n.args:
            yield from conjuncts(a)
    elif n is not None:
        yield n


def is_join_eq(n, aliases, cols_of):
    if not isinstance(n, ast.A_Expr) or [x.sval for x in n.name] != ["="]:
        return None
    if not (isinstance(n.lexpr, ast.ColumnRef) and isinstance(n.rexpr, ast.ColumnRef)):
        return None
    a, b = colref(n.lexpr, aliases, cols_of), colref(n.rexpr, aliases, cols_of)
    if not a or not b or a[0] == b[0]:
        return None
    return a, b


def join_tree(fact, tables, edges, keys):
    """从事实表出发按多对一关联长成一棵树。返回 (关联列表, 剩余的关联谓词, 到不了的表)。"""
    reached, joins, used = [fact], [], set()
    grew = True
    while grew:
        grew = False
        for pair, preds in edges.items():
            if pair in used:
                continue
            a, b = pair
            for left, right in ((a, b), (b, a)):
                if left in reached and right not in reached:
                    on = [(lc, rc) if lt == left else (rc, lc) for (lt, lc), (rt, rc) in preds]
                    if tuple(sorted(r for _, r in on)) == keys.get(right):
                        joins.append({"left": left, "right": right, "on": sorted(on)})
                        reached.append(right)
                        used.add(pair)
                        grew = True
                    break
    return joins, [p for p in edges if p not in used], set(tables) - set(reached)


def role_of(col):
    c = col.split(".")[-1]
    for k, r in (("ship", "ship date"), ("receipt", "receipt date"), ("commit", "commit date"), ("order", "order date"),
                 ("sold", "sold date"), ("return", "return date")):
        if k in c:
            return r
    return c


class Ctx:
    def __init__(self, spec, cols, types, keys):
        self.spec = spec
        self.cols_of = {t: set(c) for t, c in cols.items()}
        self.types = types
        self.facts = {f["table"]: f for f in spec["facts"]}
        self.keys = dict(keys)
        for t, f in self.facts.items():
            self.keys[t] = tuple(sorted(f["grain"]))
        self.cal = spec["calendar"]
        y0, y1 = spec["years"]["learn"], spec["years"]["holdout"]
        self.learn = {"kind": "single", "period": {"year": y0, "m1": 3, "m2": 3}}
        self.holdout = [
            ("P1", {"kind": "single", "period": {"year": y1, "m1": 9, "m2": 9}}),
            ("T1", {"kind": "diff", "a": {"year": y1, "m1": 9, "m2": 9}, "b": {"year": y0, "m1": 6, "m2": 6}}),
            ("T2", {"kind": "rank_month", "year": y1}),
        ]

    def is_date(self, t, c):
        return self.types.get((t, c)) == "date"


def block_definition(sel, cx, qid, bid, notes):
    note = lambda fact, why, pred="": notes.append({"query": qid, "block": bid, "fact": fact, "drop": why, "pred": pred[:160]})
    aliases, seen, dup = {}, set(), set()
    for n in walk_block(sel.fromClause):
        if isinstance(n, ast.RangeVar) and (n.relname or "").lower() in cx.cols_of:
            t = n.relname.lower()
            a = (n.alias.aliasname if n.alias else t).lower()
            if t in seen:
                dup.add(t)
            seen.add(t)
            aliases[a] = t
    facts = [t for t in cx.facts if t in seen]
    has_agg = any(isinstance(n, ast.FuncCall) and [x.sval for x in n.funcname][-1].lower() in AGGS for n in walk_block(sel.targetList))
    if not facts or not has_agg:
        return None
    if dup:
        note(None, f"table used twice: {sorted(dup)}")
        return None
    cal_dim = cx.cal["table"] if cx.cal["kind"] == "dim" else None
    preds = list(conjuncts(sel.whereClause))
    for n in walk_block(sel.fromClause):
        if isinstance(n, ast.JoinExpr) and n.quals is not None:
            preds += list(conjuncts(n.quals))
    edges, rest, time_edges = {}, [], []
    for p in preds:
        j = is_join_eq(p, aliases, cx.cols_of)
        if j is None:
            rest.append(p)
            continue
        (ta, ca), (tb, cb) = j
        if cal_dim in (ta, tb):
            time_edges.append(j if tb == cal_dim else (j[1], j[0]))
            continue
        edges.setdefault(tuple(sorted((ta, tb))), []).append(j)
    others = seen - {cal_dim}
    fact = joins = None
    for f in facts:
        js, left, unreached = join_tree(f, others, edges, cx.keys)
        if not left and not unreached:
            fact, joins = f, js
            break
    if fact is None:
        js, left, unreached = join_tree(facts[0], others, edges, cx.keys)
        why = "join not a many-to-one tree" if left else f"tables not reachable by many-to-one joins: {sorted(unreached)}"
        note(facts[0], why, "; ".join(f"{a}-{b}" for a, b in left))
        return None
    joined = [j["right"] for j in joins]
    allowed = [fact, *joined]
    direct = {fact} | {j["right"] for j in joins if j["left"] == fact}
    # 时间角色
    if cal_dim:
        tcols = {(ta, ca, cb) for (ta, ca), (_, cb) in time_edges}
        if len(tcols) != 1 or next(iter(tcols))[0] != fact or next(iter(tcols))[2] != cx.cal["key"]:
            note(fact, "date dimension not joined exactly once from the fact by its key", str(sorted(tcols)))
            return None
        time_col = next(iter(tcols))[1]
        time_ref = (fact, time_col)
        time = {"role": role_of(time_col), "fact_col": time_col, "dim": cal_dim, "dim_col": cx.cal["key"], "grain": "month",
                "loss_ratio": 0.0, "year_col": cx.cal["year_col"], "month_col": cx.cal["month_col"]}
    else:
        dated = set()
        for p in rest:
            if any(isinstance(m, ast.SubLink) for m in walk(p)):
                continue
            cs = cols_in(p, aliases, cx.cols_of)
            if None in cs:
                continue
            if period_pred(deparse(p)):
                dated |= {c for c in cs if c and c[0] in direct and cx.is_date(*c)}
        spec_col = (fact, cx.facts[fact]["date"])
        if not dated or spec_col in dated:
            time_ref = spec_col
        elif len(dated) == 1:
            time_ref = next(iter(dated))
        else:
            note(fact, "several date columns carry period predicates", str(sorted(dated)))
            return None
        time = {"role": role_of(time_ref[1]), "fact_col": f"{time_ref[0]}.{time_ref[1]}", "dim": "", "dim_col": "",
                "grain": "month", "loss_ratio": 0.0, "strategy": "column"}
    known = set(allowed) | set().union(*(cx.cols_of[t] for t in allowed))
    # 度量：第一个只引用块内已关联表的聚合
    measure = None
    for n in walk_block(sel.targetList):
        if not isinstance(n, ast.FuncCall):
            continue
        name = [x.sval for x in n.funcname][-1].lower()
        if name not in AGGS:
            continue
        if n.agg_star:
            measure = "count(*)"
            break
        if any(isinstance(m, ast.SubLink) for m in walk(n.args)):
            continue
        if any(isinstance(x, (ast.BoolExpr, ast.NullTest)) or (isinstance(x, ast.A_Expr) and [y.sval for y in x.name][0] in CMP)
               for x in n.args or ()):
            note(None, "aggregate over a boolean (SQLite dialect)", deparse(n))
            continue  # SQLite 的 SUM(x = 'C')：PostgreSQL 不能对布尔值求和
        ts = tables_of(n.args, aliases, cx.cols_of)
        if ts is None or not ts or not ts <= set(allowed):
            continue
        qualify(n, aliases, cx.cols_of)
        expr = deparse(n)
        if words_ok(expr, known) and not DATE_LIT.search(expr):
            measure = expr
            break
    if measure is None:
        note(fact, "no expressible aggregate")
        return None
    filters = {}
    for p in rest:
        if any(isinstance(m, ast.SubLink) for m in walk(p)):
            note(fact, "subquery", deparse(p))
            continue
        ts = tables_of(p, aliases, cx.cols_of)
        if ts is None or len(ts) != 1:
            note(fact, "multi-table or unresolved", deparse(p))
            continue
        t = next(iter(ts))
        if t == cal_dim:
            continue  # 期间是查询参数
        if t not in allowed:
            note(fact, "table not joined", deparse(p))
            continue
        cs = cols_in(p, aliases, cx.cols_of)
        if time_ref in cs:
            if not period_pred(deparse(p)):
                note(fact, "references the time column", deparse(p))
            continue  # 时间列上的日期范围是期间参数
        qualify(p, aliases, cx.cols_of)
        expr = deparse(p)
        if isinstance(p, ast.BoolExpr) and p.boolop == BoolExprType.OR_EXPR:
            expr = f"({expr})"  # 与同表的其他过滤用 and 连接时保持优先级
        if DATE_LIT.search(expr):
            note(fact, "date literal (question parameter)", expr)
            continue
        if not words_ok(expr, known):
            note(fact, "not expressible as a persistent filter", expr)
            continue
        filters[t] = f"{filters[t]} and {expr}" if t in filters else expr
    js = [{"key": "", "left": j["left"], "right": j["right"], "on": [[l, r] for l, r in j["on"]], "kind": "inner", "filters": {},
           "cardinality": "", "loss_ratio": 0.0, "revision": 0} for j in joins]
    name = f"{qid}_b{bid}_{fact}"
    label = cx.spec.get("label", cx.spec["name"])
    metric = {
        "name": name, "aliases": [],
        "definition": f"{label} {qid} block {bid}: {measure} over {fact}" + (f" with {len(js)} join(s)" if js else ""),
        "fact": fact, "measure": measure, "grain": list(cx.facts[fact]["grain"]), "time": time, "joins": js, "filters": filters,
        "empty": "unspecified", "caveats": [], "examples": [], "basis": {"kind": "none"},
    }
    return {
        "key": f"metric:{name}", "status": "Valid", "metric": metric,
        "evidence": {"task": f"{name}-L1", "ask": cx.learn, "decimals": 2},
        "holdout": [{"id": f"{name}-{tag}", "ask": ask} for tag, ask in cx.holdout],
        "source": {"query": qid, "block": bid},
    }


def sqlite_to_pg(sql, names):
    """BIRD（SQLite 方言）→ 可被 PostgreSQL 解析器读的文本：反引号去掉并改名，双引号里不是列名或表名的当字符串。"""
    sql = re.sub(r"`([^`]*)`", lambda m: RENAME.get(m.group(1).lower(), m.group(1)), sql)
    sql = re.sub(r'"([^"]*)"', lambda m: m.group(1) if m.group(1).lower() in names else "'" + m.group(1).replace("'", "''") + "'", sql)
    return re.sub(r"\b(from|join)\s+order\b", r"\1 orders", sql, flags=re.I)


def sources(path, db_id, names):
    if os.path.isdir(path):
        for f in sorted(x for x in os.listdir(path) if x.endswith(".sql")):
            yield f[:-4], open(os.path.join(path, f), encoding="utf-8").read(), None
    else:
        for x in json.load(open(path, encoding="utf-8")):
            if db_id and x.get("db_id") != db_id:
                continue
            yield f"bird{x['question_id']}", sqlite_to_pg(x["SQL"], names), x.get("question")


def signature(e):
    m = e["metric"]
    return json.dumps([m["fact"], m["measure"].lower(), [(j["left"], j["right"], j["on"]) for j in m["joins"]], m["filters"],
                       m["time"]["fact_col"]], sort_keys=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--notes", default=None)
    ap.add_argument("--db-id", default=None)
    o = ap.parse_args()
    spec = json.load(open(o.spec, encoding="utf-8"))
    cx = Ctx(spec, *load_schema(o.db))
    names = set(cx.cols_of) | set().union(*cx.cols_of.values())
    entries, notes, failed, dups, seen, n = [], [], [], [], {}, 0
    for qid, sql, question in sources(o.queries, o.db_id, names):
        n += 1
        try:
            stmts = parse_sql(sql)
        except Exception as e:
            failed.append({"query": qid, "error": str(e)[:200]})
            continue
        bid = 0
        for st in stmts:
            for node in walk(st.stmt):
                if isinstance(node, ast.SelectStmt) and node.fromClause:
                    d = block_definition(node, cx, qid, bid, notes)
                    if d:
                        if question:
                            d["source"]["question"] = question
                        s = signature(d)
                        if s in seen:
                            dups.append({"query": qid, "block": bid, "same_as": seen[s]})
                        else:
                            seen[s] = d["metric"]["name"]
                            entries.append(d)
                    bid += 1
    lib = {"cell": f"{spec['name']}-queries", "schema": spec["name"], "templates": n, "parse_failures": failed,
           "duplicates": dups, "metric_report": {"entries": entries}}
    json.dump(lib, open(o.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if o.notes:
        json.dump(notes, open(o.notes, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by_fact, reasons = {}, {}
    for e in entries:
        by_fact[e["metric"]["fact"]] = by_fact.get(e["metric"]["fact"], 0) + 1
    for x in notes:
        reasons[x["drop"].split(":")[0]] = reasons.get(x["drop"].split(":")[0], 0) + 1
    print(json.dumps({"queries": n, "definitions": len(entries), "by_fact": by_fact,
                      "with_joins": sum(1 for e in entries if e["metric"]["joins"]),
                      "chains": sum(1 for e in entries if any(j["left"] != e["metric"]["fact"] for j in e["metric"]["joins"])),
                      "with_filters": sum(1 for e in entries if e["metric"]["filters"]),
                      "time_on_joined_table": sum(1 for e in entries if e["metric"]["time"].get("strategy") == "column"
                                                  and not e["metric"]["time"]["fact_col"].startswith(e["metric"]["fact"] + ".")),
                      "duplicates": len(dups), "dropped": reasons, "parse_failures": len(failed)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
