#!/usr/bin/env python3
"""How often tasks on one database need knowledge that another task on the same database also needs,
measured on public benchmarks that were not built for this paper (no LLM calls).

usage: external-reuse-stats.py --bird DIR --livesql DIR [DIR ...] [--spider2 FILE] --out DIR
                              [--population FILE --tex-out DIR]
       external-reuse-stats.py --from-json reuse-stats.json --population FILE --tex-out DIR

Knowledge per task:
  BIRD          the task's evidence string, split at ';' and line breaks into items; an item is normalized
                (lower case, quotes unified, spaces around punctuation removed) and two items are the same
                knowledge only if their normalized text is equal, so paraphrases count as different knowledge
                and the repetition is a lower bound. A calculation is an item with an arithmetic operator or an
                aggregate or arithmetic function. A second view keys an item by its defined term (the text before
                "refers to", "means", "stands for", "is defined as", or "="), so one definition phrased differently
                by different annotators counts as the same knowledge.
  LiveSQLBench  the entries of the database's knowledge base (*_kb.jsonl) that the task names: an entry's name
                (case-insensitive, whole words, optional plural ending; single lower-case words are skipped as too
                ambiguous; a parenthesized qualifier such as "(Race)" stays part of the name when another entry shares
                the base) or its acronym in parentheses (case-sensitive, whole word), searched in normal_query when
                the release has it and in query otherwise; a named entry brings the entries it depends on
                (children_knowledge, transitively). The benchmark's own task-to-knowledge ids are withheld from the
                public files, so name matching misses tasks that describe a concept without naming it.
  Spider 2.0    the external-knowledge document that the task references.

Statistics are order independent: for every database, a knowledge item used by u tasks contributes u uses of
which u - 1 repeat an earlier use in any arrival order; a task shares knowledge when at least one of its items is
used by another task on the same database.

With --tex-out, the numbers of the paper (overleaf/gen/external.tex, \Ex*) are written, including the token saving that
the cost model of Section 2.2 predicts at a given share r of questions answered from memory,
    1 - (1 - r) * (c_e + c_l) / c_e - r * c_r / c_e,
with c_e, c_r and c_l (tokens per question by exploration, per question from memory, per learned definition) taken
from the population study (--population, population-stats.json of tools/population-stats.py) and r taken from the
repetition of knowledge uses in the benchmarks.
"""
import argparse
import collections
import json
import os
import random
import re

CALC = re.compile(r"[/*+]|\s-\s|\b(divide|subtract|multiply|sum|count|avg|average|max|min|cast|percentage|ratio)\s*\(", re.I)


def norm(s):
    s = s.lower().replace("`", "'").replace('"', "'").replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip(" .;,")
    return re.sub(r"\s*([^\w\s])\s*", r"\1", s)


def summarize(tasks):
    """tasks: list of (db, set of items, set of calculation items, category or None)."""
    def one(sel, pick):
        uses = collections.Counter()
        per_db = collections.defaultdict(collections.Counter)
        n = with_k = 0
        for db, items, calc, _ in sel:
            n += 1
            k = pick(items, calc)
            if k:
                with_k += 1
            for i in k:
                per_db[db][i] += 1
        total = sum(sum(c.values()) for c in per_db.values())
        distinct = sum(len(c) for c in per_db.values())
        shared = 0
        for db, items, calc, _ in sel:
            k = pick(items, calc)
            if k and any(per_db[db][i] > 1 for i in k):
                shared += 1
        return {
            "tasks": n,
            "tasks_with_knowledge": with_k,
            "tasks_with_knowledge_pct": round(100.0 * with_k / n, 1) if n else None,
            "knowledge_uses": total,
            "distinct_items": distinct,
            "uses_repeating_pct": round(100.0 * (total - distinct) / total, 1) if total else None,
            "uses_per_item": round(total / distinct, 2) if distinct else None,
            "tasks_sharing_pct_of_with_knowledge": round(100.0 * shared / with_k, 1) if with_k else None,
            "databases": len({t[0] for t in sel}),
        }
    out = {"all": one(tasks, lambda i, c: i), "calculations": one(tasks, lambda i, c: c)}
    cats = sorted({t[3] for t in tasks if t[3]})
    for cat in cats:
        sel = [t for t in tasks if t[3] == cat]
        out[f"all|{cat}"] = one(sel, lambda i, c: i)
        out[f"calculations|{cat}"] = one(sel, lambda i, c: c)
    return out


TERM = re.compile(r"^(.*?)\s+(?:refers? to|means?|stands? for|is defined as|=)\s+", re.I)


def growth(tasks, at, perms=200, seed=0):
    """Share of the knowledge uses of the n-th task on a database that an earlier task on the same database already
    needed, averaged over random arrival orders and over the databases with at least n tasks with knowledge."""
    rnd = random.Random(seed)
    by_db = collections.defaultdict(list)
    for db, items, _, _ in tasks:
        if items:
            by_db[db].append(items)
    out = {}
    for n in at:
        dbs = [ts for ts in by_db.values() if len(ts) >= n]
        if not dbs:
            continue
        vals = []
        for ts in dbs:
            hit = tot = 0
            for _ in range(perms):
                order = rnd.sample(ts, n)
                seen = set().union(*order[:-1]) if n > 1 else set()
                hit += len(order[-1] & seen)
                tot += len(order[-1])
            vals.append(hit / tot)
        out[str(n)] = {"repeating_pct": round(100.0 * sum(vals) / len(vals), 1), "databases": len(dbs)}
    return out


def bird(d):
    rows = json.load(open(os.path.join(d, "dev.json"), encoding="utf-8"))
    tasks, terms = [], []
    for r in rows:
        raw = [x for x in re.split(r"[;\n]", r.get("evidence") or "") if norm(x)]
        items = {norm(x) for x in raw}
        tasks.append((r["db_id"], items, {i for i in items if CALC.search(i)}, None))
        # the defined term (left of "refers to", "means", "=", ...) identifies the knowledge however it is phrased
        ts = {"term:" + norm(m.group(1)) for x in raw if (m := TERM.match(x.strip())) and norm(m.group(1))}
        calc = {"term:" + norm(m.group(1)) for x in raw if (m := TERM.match(x.strip())) and norm(m.group(1)) and CALC.search(x)}
        terms.append((r["db_id"], ts, calc, None))
    return tasks, terms


def livesql(d):
    rows = [json.loads(l) for l in open(os.path.join(d, "livesqlbench_data.jsonl"), encoding="utf-8")]
    kbs, pats = {}, {}
    for db in sorted({r["selected_database"] for r in rows}):
        kb = [json.loads(l) for l in open(os.path.join(d, db, f"{db}_kb.jsonl"), encoding="utf-8")]
        kbs[db] = {e["id"]: e for e in kb}
        ps = []
        split = [(e, re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", e["knowledge"].strip())) for e in kb]
        bases = collections.Counter((m.group(1) if m else e["knowledge"].strip()).lower() for e, m in split)
        for e, m in split:
            name = e["knowledge"].strip()
            base, paren = (m.group(1), m.group(2)) if m else (name, None)
            acronym = paren is not None and " " not in paren and sum(ch.isupper() for ch in paren) >= 2
            # a qualifier such as "(Race)" or "(3M)" is part of the name when another entry shares the base
            if paren is not None and not acronym and bases[base.lower()] > 1:
                base = name
            if " " in base or any(ch.isupper() for ch in base):
                ps.append((e["id"], re.compile(r"(?<!\w)" + re.escape(base) + r"(?:e?s)?(?!\w)", re.I)))
            if acronym:
                ps.append((e["id"], re.compile(r"(?<!\w)" + re.escape(paren) + r"s?(?!\w)")))
        pats[db] = ps
    def closure(db, ids):
        seen, todo = set(), list(ids)
        while todo:
            i = todo.pop()
            if i in seen or i not in kbs[db]:
                continue
            seen.add(i)
            ch = kbs[db][i].get("children_knowledge")
            if isinstance(ch, list):
                todo += ch
        return seen
    tasks, direct_tasks = [], []
    for r in rows:
        db = r["selected_database"]
        text = r.get("normal_query") or r["query"]
        named = {i for i, p in pats[db] if p.search(text)}
        ids = closure(db, named)
        calc = {i for i in ids if kbs[db][i].get("type") == "calculation_knowledge"}
        tasks.append((db, ids, calc, r["category"]))
        direct_tasks.append((db, named, {i for i in named if kbs[db][i].get("type") == "calculation_knowledge"}, r["category"]))
    types = collections.Counter(e.get("type") for kb in kbs.values() for e in kb.values())
    return tasks, direct_tasks, {"kb_entries": sum(len(k) for k in kbs.values()), "kb_types": dict(types),
                                 "matched_in": "normal_query" if any(r.get("normal_query") for r in rows) else "query"}


def spider2(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    tasks = []
    for r in rows:
        doc = r.get("external_knowledge")
        items = {doc} if doc else set()
        tasks.append((r.get("db") or r.get("db_id") or "?", items, items, None))
    return tasks


def cost_model(pop):
    """c_e, c_r (second half of the agents, no memory and MAVRA), c_l (extraction tokens per learned definition) and the
    share of MAVRA's questions answered from a shared definition, from population-stats.json."""
    m, n = pop["methods"]["metric-global-snap"], pop["methods"]["middle-alone"]
    c_e, c_r = n["late"]["tok"]["mean"], m["late"]["tok"]["mean"]
    c_l = sum(a["learn_tok"]["mean"] for a in m["per_agent"]) / m["v1"]["learns"]["mean"]
    r = m["v1"]["reused"]["mean"] / m["v1"]["n"]["mean"]
    return c_e, c_r, c_l, r


def model_saving(r, c_e, c_r, c_l):
    return 1 - (1 - r) * (c_e + c_l) / c_e - r * c_r / c_e


def write_tex(res, pop, path):
    lines = ["% generated by tools/external-reuse-stats.py; do not edit"]

    def mac(name, val):
        lines.append(f"\\newcommand{{\\Ex{name}}}{{{val}}}")

    def pct(x):
        return f"{x:.0f}"

    def rep(s):
        return 100.0 * (s["knowledge_uses"] - s["distinct_items"]) / s["knowledge_uses"]

    for key, b in (("Ls", "livesqlbench_full"), ("Ll", "livesqlbench_lite"), ("Bd", "bird_dev_terms")):
        r = res[b]
        a, c = r["all"], r["calculations"]
        mac(f"{key}Tasks", f"{a['tasks']:,}")
        mac(f"{key}Dbs", a["databases"])
        mac(f"{key}TasksPerDb", f"{a['tasks'] / a['databases']:.0f}")
        mac(f"{key}NamedPct", pct(a["tasks_with_knowledge_pct"]))
        mac(f"{key}SharePct", pct(a["tasks_sharing_pct_of_with_knowledge"]))
        mac(f"{key}RepeatPct", pct(rep(a)))
        mac(f"{key}CalcRepeatPct", pct(rep(c)))
        g = r.get("growth", {})
        for n, word in (("10", "Tenth"), ("20", "Twentieth"), ("100", "Hundredth")):
            mac(f"{key}{word}", pct(g[n]["repeating_pct"]) if n in g else "--")
        if "meta" in r:
            mac(f"{key}Kb", f"{r['meta']['kb_entries']:,}")
    if pop:
        c_e, c_r, c_l, r_ours = cost_model(pop)
        mac("ModelLearnTokK", f"{c_l / 1e3:.1f}")
        mac("ModelReusePct", pct(100 * r_ours))
        mac("ModelTokSaveOurs", pct(100 * model_saving(r_ours, c_e, c_r, c_l)))
        ls = res["livesqlbench_full"]
        mac("ModelTokSaveLs", pct(100 * model_saving(rep(ls["all"]) / 100, c_e, c_r, c_l)))
        mac("ModelTokSaveLsTwentieth", pct(100 * model_saving(ls["growth"]["20"]["repeating_pct"] / 100, c_e, c_r, c_l)))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bird")
    ap.add_argument("--livesql", nargs="*", default=[])
    ap.add_argument("--spider2")
    ap.add_argument("--out")
    ap.add_argument("--from-json", help="reuse-stats.json of an earlier run: only write --tex-out")
    ap.add_argument("--population", help="population-stats.json for the cost model")
    ap.add_argument("--tex-out")
    o = ap.parse_args()
    pop = json.load(open(o.population, encoding="utf-8")) if o.population else None
    if o.from_json:
        write_tex(json.load(open(o.from_json, encoding="utf-8")), pop, os.path.join(o.tex_out, "external.tex"))
        return
    if not o.out:
        ap.error("--out is required unless --from-json is given")
    res = {}
    if o.bird:
        items, terms = bird(o.bird)
        res["bird_dev"] = summarize(items)
        res["bird_dev_terms"] = summarize(terms)
        res["bird_dev_terms"]["growth"] = growth(terms, [2, 5, 10, 20, 50, 100])
    for d in o.livesql:
        tasks, direct, meta = livesql(d)
        name = "livesqlbench_" + os.path.basename(os.path.normpath(d)).replace("livesqlbench-", "")
        res[name] = dict(summarize(tasks), meta=meta, direct_only=summarize(direct)["all"], growth=growth(tasks, [2, 5, 10, 20]))
    if o.spider2:
        res["spider2_lite"] = summarize(spider2(o.spider2))
    os.makedirs(o.out, exist_ok=True)
    with open(os.path.join(o.out, "reuse-stats.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    lines = ["| benchmark | subset | DBs | tasks | with knowledge % | uses | distinct | uses repeating % | uses/item | sharing tasks % |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for b, r in res.items():
        for sub, s in r.items():
            if sub == "meta" or not isinstance(s, dict) or "tasks" not in s:
                continue
            lines.append(f"| {b} | {sub} | {s['databases']} | {s['tasks']} | {s['tasks_with_knowledge_pct']} | {s['knowledge_uses']} | "
                         f"{s['distinct_items']} | {s['uses_repeating_pct']} | {s['uses_per_item']} | {s['tasks_sharing_pct_of_with_knowledge']} |")
    md = "\n".join(lines) + "\n"
    md += "\nShare of the n-th task's knowledge uses already needed by an earlier task on the same database (random orders):\n"
    for b, r in res.items():
        if "growth" in r:
            md += f"- {b}: " + ", ".join(f"n={n}: {g['repeating_pct']}% ({g['databases']} DBs)" for n, g in r["growth"].items()) + "\n"
    for b, r in res.items():
        if "meta" in r:
            md += f"- {b} knowledge base: {r['meta']}\n"
    with open(os.path.join(o.out, "reuse-stats.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    if o.tex_out:
        write_tex(res, pop, os.path.join(o.tex_out, "external.tex"))


if __name__ == "__main__":
    main()
