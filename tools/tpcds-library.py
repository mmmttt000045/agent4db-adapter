#!/usr/bin/env python3
"""从 TPC-DS 官方查询模板导出一个指标定义库（配对回放的第二个负载，`replay-bench --schema tpcds`）。

用法：python3 tools/tpcds-library.py --templates DIR --schema tpcds.sql --out LIB.json [--notes NOTES.json]
依赖：pglast（PostgreSQL 解析器，带反解析）。

定义的来源与 tools/tpcds-sharing.py 相同：一个 SELECT 块里对某张销售/退货事实表的聚合算一个定义。
为了能被中间层准入并按期间编译，只取满足下面条件的块，并按本文的结构化实现（事实表、度量、粒度、时间角色、
事实表直连的维表关联、单表过滤）记录：
  - 事实表是六张销售/退货表之一，块里恰有一个日期键关联 date_dim（时间角色），没有事实表之间的关联；
  - 维表关联都从事实表直接发出，关联列是维表主键（多对一），同一维表在块里只出现一次；
  - 度量是块里第一个只引用事实表列的聚合，表达式只用规范编译允许的词；
  - 过滤取 WHERE 顶层合取中只引用一张表（事实表或直连维表）的谓词；date_dim 上的谓词是查询参数（期间）；
    引用经维表再关联的表（如 customer → customer_address）或子查询的谓词无法表达，记入 notes 后舍弃。
学习题与留出题的期间与合成基准相同：学习 2001-03，留出 2002-09 单期、2002-09 与 2001-06 之差、2002 年月份排名。
"""

import argparse
import json
import os
import re
import sys

try:
    from pglast import ast, parse_sql
    from pglast.enums import BoolExprType
    from pglast.stream import RawStream
except ImportError:  # pragma: no cover
    sys.exit("需要 pglast：pip install --user pglast")

FACTS = {"store_sales", "store_returns", "catalog_sales", "catalog_returns", "web_sales", "web_returns"}
AGGS = {"sum", "avg", "count", "min", "max"}
WORDS = {"sum", "count", "avg", "min", "max", "distinct", "coalesce", "nullif", "case", "when", "then", "else", "end", "and", "or",
         "not", "null", "is", "in", "between", "like", "as", "round", "abs", "filter", "where", "true", "false", "cast", "numeric",
         "decimal", "int", "integer", "bigint", "float", "double", "precision", "real", "text", "varchar"}  # = metric::SQL_WORDS
ROLE = {"sold": "sold", "returned": "returned", "ship": "ship"}
LEARN = {"kind": "single", "period": {"year": 2001, "m1": 3, "m2": 3}}
HOLDOUT = [
    ("P1", {"kind": "single", "period": {"year": 2002, "m1": 9, "m2": 9}}),
    ("T1", {"kind": "diff", "a": {"year": 2002, "m1": 9, "m2": 9}, "b": {"year": 2001, "m1": 6, "m2": 6}}),
    ("T2", {"kind": "rank_month", "year": 2002}),
]


def load_schema(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    text = re.sub(r"--.*", "", text)
    tables = {}
    for m in re.finditer(r"create table (\w+)\s*\((.*?)\n\);", text, re.S | re.I):
        name, body = m.group(1).lower(), m.group(2)
        cols = [c.lower() for c in re.findall(r"^\s*(\w+)\s+(?:integer|char|varchar|date|time|decimal|int)", body, re.M | re.I)]
        pk = re.search(r"primary key\s*\(([^)]*)\)", body, re.I)
        tables[name] = (cols, tuple(sorted(c.strip().lower() for c in pk.group(1).split(","))) if pk else ())
    return tables


PARAM = "__param__"


def instantiate(tpl):
    """模板参数：text({...}) 取第一个选项，random(a, b, ...) 取 a；其余（ulist、dist、date 等）无法在不跑 dsqgen 的情况下
    取到真实值，换成占位符，引用它的谓词在导出时舍弃并记入 notes。"""
    defs = {}
    for m in re.finditer(r"define\s+(\w+)\s*=\s*(.*?);", tpl, re.I | re.S):
        name, expr = m.group(1).upper(), m.group(2).strip()
        t = re.search(r'text\(\s*\{\s*"([^"]+)"', expr)
        r = re.match(r"random\(\s*(-?\d+)\s*,", expr, re.I)
        defs[name] = t.group(1) if t else r.group(1) if r else PARAM
    body = re.sub(r"^\s*define\s+.*?;\s*$", "", tpl, flags=re.I | re.M | re.S)
    body = re.sub(r"--.*", "", body)
    body = body.replace("[_LIMITA]", "").replace("[_LIMITB]", "").replace("[_LIMITC]", "limit 100")
    body = re.sub(r"\[([A-Za-z_][A-Za-z0-9_.]*)\]", lambda m: defs.get(m.group(1).upper().split(".")[0], PARAM), body)
    body = re.sub(r"(\d+)\s+days\b", r"interval '\1 days'", body, flags=re.I)
    return body


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
    if not fields:
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


def deparse(node):
    s = RawStream()(node)
    s = re.sub(r"\b[A-Za-z_]\w*\.([A-Za-z_]\w*)", r"\1", s)  # 去掉别名限定：TPC-DS 列名带表前缀，不会歧义
    return re.sub(r"\s+", " ", s).strip()


def words_ok(expr, known_cols):
    for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr):
        w = w.lower()
        if w not in WORDS and w not in known_cols:
            return False
    return True


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


def block_definition(sel, schema, qid, bid, notes):
    cols_of = {t: set(c) for t, (c, _) in schema.items()}
    aliases, dup = {}, set()
    for n in walk_block(sel.fromClause):
        if isinstance(n, ast.RangeVar) and (n.relname or "").lower() in schema:
            t = n.relname.lower()
            a = (n.alias.aliasname if n.alias else t).lower()
            if t in aliases.values():
                dup.add(t)
            aliases[a] = t
    facts = sorted({t for t in aliases.values() if t in FACTS})
    if len(facts) != 1:
        return None
    fact = facts[0]
    # 关联谓词：WHERE 顶层合取 + JOIN ON
    preds = list(conjuncts(sel.whereClause))
    for n in walk_block(sel.fromClause):
        if isinstance(n, ast.JoinExpr) and n.quals is not None:
            preds += list(conjuncts(n.quals))
    pairs, rest = {}, []
    for p in preds:
        j = is_join_eq(p, aliases, cols_of)
        if j is None:
            rest.append(p)
            continue
        (ta, ca), (tb, cb) = j
        if ta == fact:
            pairs.setdefault(tb, set()).add((ca, cb))
        elif tb == fact:
            pairs.setdefault(ta, set()).add((cb, ca))
        else:
            notes.append({"query": qid, "block": bid, "fact": fact, "drop": "indirect join", "pred": deparse(p)})
    if any(t in FACTS for t in pairs):
        return None
    time_cols = sorted({fc for fc, _ in pairs.get("date_dim", ())})
    if len(time_cols) != 1 or sorted(dc for _, dc in pairs["date_dim"]) != ["d_date_sk"]:
        return None
    if any(t in dup for t in pairs):
        return None
    joins = []
    for t, on in sorted(pairs.items()):
        if t == "date_dim":
            continue
        dcols = tuple(sorted(dc for _, dc in on))
        if dcols != schema[t][1]:  # 关联列必须是维表主键，才是多对一
            return None
        joins.append({"key": "", "left": fact, "right": t, "on": [[fc, dc] for fc, dc in sorted(on)], "kind": "inner",
                      "filters": {}, "cardinality": "", "loss_ratio": 0.0, "revision": 0})
    allowed = {fact, *(j["right"] for j in joins)}
    known = set().union(*(cols_of[t] for t in allowed))
    # 度量：第一个只引用事实表列的聚合
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
        ts = tables_of(n.args, aliases, cols_of)
        if ts == {fact}:
            expr = deparse(n)
            if PARAM not in expr and words_ok(expr, known):
                measure = expr
                break
    if measure is None:
        return None
    filters = {}
    for p in rest:
        if any(isinstance(m, ast.SubLink) for m in walk(p)):
            notes.append({"query": qid, "block": bid, "fact": fact, "drop": "subquery", "pred": deparse(p)[:120]})
            continue
        ts = tables_of(p, aliases, cols_of)
        if ts is None or len(ts) != 1:
            notes.append({"query": qid, "block": bid, "fact": fact, "drop": "multi-table or unresolved", "pred": deparse(p)[:120]})
            continue
        t = next(iter(ts))
        if t == "date_dim":
            continue  # 期间是查询参数
        if t not in allowed:
            notes.append({"query": qid, "block": bid, "fact": fact, "drop": "table not directly joined", "pred": deparse(p)[:120]})
            continue
        expr = deparse(p)
        if PARAM in expr:
            notes.append({"query": qid, "block": bid, "fact": fact, "drop": "uninstantiated template parameter", "pred": expr[:120]})
            continue
        if time_cols[0] in expr or not words_ok(expr, known) or re.search(r"\d{4}-\d{1,2}", expr):
            notes.append({"query": qid, "block": bid, "fact": fact, "drop": "not expressible as a persistent filter", "pred": expr[:120]})
            continue
        filters[t] = f"{filters[t]} and {expr}" if t in filters else expr
    fc = time_cols[0]
    role = next((r for k, r in ROLE.items() if k in fc), fc)
    name = f"{qid}_b{bid}_{fact}"
    metric = {
        "name": name, "aliases": [],
        "definition": f"TPC-DS {qid} block {bid}: {measure} over {fact}" + (f" with {len(joins)} dimension join(s)" if joins else ""),
        "fact": fact, "measure": measure, "grain": list(schema[fact][1]),
        "time": {"role": role, "fact_col": fc, "dim": "date_dim", "dim_col": "d_date_sk", "grain": "month", "loss_ratio": 0.0},
        "joins": joins, "filters": filters, "empty": "unspecified", "caveats": [], "examples": [], "basis": {"kind": "none"},
    }
    return {
        "key": f"metric:{name}", "status": "Valid", "metric": metric,
        "evidence": {"task": f"{name}-L1", "ask": LEARN, "decimals": 2},
        "holdout": [{"id": f"{name}-{tag}", "ask": ask} for tag, ask in HOLDOUT],
        "source": {"query": qid, "block": bid},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--notes", default=None)
    o = ap.parse_args()
    schema = load_schema(o.schema)
    entries, notes, failed = [], [], []
    files = sorted((f for f in os.listdir(o.templates) if f.endswith(".tpl")), key=lambda f: int(re.sub(r"\D", "", f)))
    for f in files:
        qid = f[:-4]
        sql = instantiate(open(os.path.join(o.templates, f), encoding="utf-8", errors="replace").read())
        try:
            stmts = parse_sql(sql)
        except Exception as e:
            failed.append({"query": qid, "error": str(e)[:200]})
            continue
        bid = 0
        for st in stmts:
            for n in walk(st.stmt):
                if isinstance(n, ast.SelectStmt) and n.fromClause:
                    d = block_definition(n, schema, qid, bid, notes)
                    if d:
                        entries.append(d)
                    bid += 1
    lib = {"cell": "tpcds-templates", "schema": "tpcds", "templates": len(files), "parse_failures": failed,
           "metric_report": {"entries": entries}}
    json.dump(lib, open(o.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if o.notes:
        json.dump(notes, open(o.notes, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by_fact = {}
    for e in entries:
        by_fact[e["metric"]["fact"]] = by_fact.get(e["metric"]["fact"], 0) + 1
    print(json.dumps({"definitions": len(entries), "by_fact": by_fact, "with_joins": sum(1 for e in entries if e["metric"]["joins"]),
                      "with_filters": sum(1 for e in entries if e["metric"]["filters"]), "dropped_predicates": len(notes),
                      "parse_failures": len(failed)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
