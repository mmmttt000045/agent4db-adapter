#!/usr/bin/env python3
"""workload-bench 轨迹统计：Agent 负载与应用负载的对照。

用法：python3 tools/workload-stats.py DIR [DIR ...] [--out OUT] [--audit N]
DIR 为 workload-bench 的输出目录（含 trace.jsonl、sessions.jsonl、app.json；report.json 可缺，缺时用上级目录名作模型名）。
依赖 pglast（libpg_query 的查询指纹：去掉常量与空白后的语法树哈希，作为 SQL 模板）。

每次工具调用按以下顺序互斥归类：
  error     调用出错（SQL 语法 / 语义错误、超时、参数错误）
  schema    list_tables、describe_table，或读系统目录（information_schema、pg_*）的 SQL
  answer    会话最终答案声明使用的查询（final_answer 的 used 与 derivation 中的 rN）
  validate  检查假设或复核结果：SQL 含 count(distinct …)、having count、is [not] null、row_number() over (partition …)，
            或在最终答案查询之后、又对度量列做聚合的查询（复算）
  attempt   在最终答案查询之前对度量列做聚合、但未被采用的查询（中间尝试或被放弃的写法）
  explore   其余成功的 SQL（取样、取值分布、范围、计数等数据探查）
"""

import argparse
import collections
import json
import os
import random
import re
import statistics
import sys

try:
    from pglast.parser import fingerprint as _pg_fingerprint
except ImportError:  # pragma: no cover
    sys.exit("需要 pglast：pip install --user pglast")

TABLES = ["store_sales", "store_returns", "catalog_sales", "date_dim", "item", "etl_batch_log"]
TABLE_RE = re.compile(r"\b(" + "|".join(TABLES) + r")\b")
COL_RE = re.compile(r"\b((?:ss|sr|cs|d|i)_[a-z_]+)\b")
CATALOG_RE = re.compile(r"\b(information_schema|pg_catalog|pg_[a-z_]+)\b")
MEASURE_RE = re.compile(r"\b(sum|avg)\s*\(")
VALIDATE_RE = re.compile(
    r"count\s*\(\s*distinct|having\s+count|\bis\s+(?:not\s+)?null\b|row_number\s*\(\s*\)\s*over\s*\(\s*partition"
)
AGG_RE = re.compile(r"\b(count|sum|avg|min|max)\s*\(")
REF_RE = re.compile(r"\br(\d+)\b")
KNOWLEDGE = ("schema", "explore", "validate")


def norm(sql):
    return re.sub(r"\s+", " ", sql.strip().rstrip(";").strip().lower())


_fp_cache = {}


def fingerprint(sql):
    if sql not in _fp_cache:
        try:
            _fp_cache[sql] = _pg_fingerprint(sql)
        except Exception:
            _fp_cache[sql] = "unparsed:" + norm(sql)
    return _fp_cache[sql]


def load_jsonl(path):
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def model_of(d):
    rp = os.path.join(d, "report.json")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            return json.load(f).get("agent", "?")
    return os.path.basename(os.path.dirname(os.path.normpath(d)))


def used_refs(sess):
    run = sess.get("run") or {}
    refs = set()
    for r in run.get("used") or []:
        m = REF_RE.search(str(r))
        if m:
            refs.add(int(m.group(1)))
    refs.update(int(x) for x in REF_RE.findall(run.get("derivation") or ""))
    return refs


def sql_of(call):
    return (call.get("args") or {}).get("sql") or ""


def classify(call, used, t_answer):
    """返回互斥类别；t_answer 为该会话第一条被采用的查询的开始时间（没有时为 None）。"""
    tool, status = call["tool"], call["status"]
    if tool in ("final_answer", "ask_clarification"):
        return None
    if status == "error":
        return "error"
    if tool in ("list_tables", "describe_table"):
        return "schema"
    if tool != "run_sql":
        return "other"
    s = norm(sql_of(call))
    if CATALOG_RE.search(s) and not TABLE_RE.search(re.sub(r"'[^']*'", "", s)):
        return "schema"
    ref = call.get("ref")
    if ref and int(ref.lstrip("r")) in used:
        return "answer"
    if VALIDATE_RE.search(s):
        return "validate"
    if MEASURE_RE.search(s) and COL_RE.search(s):
        if t_answer is not None and call["t0_ms"] > t_answer:
            return "validate"
        return "attempt"
    return "explore"


def fact_key(call, cat):
    """调用获得的数据库知识：同一张表的结构、同一组列上的同类探查或检查算同一事实，与写法无关。"""
    tool = call["tool"]
    if tool == "list_tables":
        return ("schema", "*")
    if tool == "describe_table":
        return ("schema", (call.get("args") or {}).get("table", "?"))
    s = norm(sql_of(call))
    tables = tuple(sorted(set(TABLE_RE.findall(s))))
    if cat == "schema":
        return ("schema",) + (tables or ("*",))
    cols = tuple(sorted(set(COL_RE.findall(s))))
    return (cat, tables, cols, bool(AGG_RE.search(s)))


def text_key(call):
    if call["tool"] == "run_sql":
        return ("sql", norm(sql_of(call)))
    return (call["tool"], json.dumps(call.get("args") or {}, sort_keys=True, ensure_ascii=False))


def template_key(call):
    if call["tool"] == "run_sql":
        return ("sql", fingerprint(sql_of(call)))
    return text_key(call)


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def med(xs):
    return round(statistics.median(xs), 1) if xs else None


def analyze_run(d):
    model = model_of(d)
    sessions = {s["agent"]: s for s in load_jsonl(os.path.join(d, "sessions.jsonl"))}
    calls = [c for c in load_jsonl(os.path.join(d, "trace.jsonl")) if c["agent"] in sessions]
    calls.sort(key=lambda c: (c["t0_ms"], c["agent"], c["step"], c["seq"]))
    by_sess = collections.defaultdict(list)
    for c in calls:
        by_sess[c["agent"]].append(c)
    # 类别
    for a, cs in by_sess.items():
        used = used_refs(sessions[a])
        ans = [c["t0_ms"] for c in cs if c["tool"] == "run_sql" and c.get("ref") and int(c["ref"].lstrip("r")) in used]
        t_answer = min(ans) if ans else None
        for c in cs:
            c["cat"] = classify(c, used, t_answer)
            c["model"] = model
    data = [c for c in calls if c["cat"] is not None]  # 访问数据库的调用（不含 final_answer / 澄清）
    return model, sessions, by_sess, data


def redundancy(data):
    """跨会话重复：按开始时间顺序，某调用获得的知识是否已被另一个会话更早获得过（事实 / 模板 / 原文三个层次），
    以及另一个会话是否在 ±60 秒内获得了同一事实（并发重复）。只统计成功的知识性调用。"""
    earlier = {level: collections.defaultdict(set) for level in ("fact", "template", "text")}
    out = collections.Counter()
    ms = collections.Counter()
    know = sorted((c for c in data if c["cat"] in KNOWLEDGE), key=lambda c: c["t0_ms"])
    times = collections.defaultdict(list)  # fact -> [(t, agent)]
    for c in know:
        times[fact_key(c, c["cat"])].append((c["t0_ms"], c["agent"]))
    for c in know:
        keys = {"fact": fact_key(c, c["cat"]), "template": template_key(c), "text": text_key(c)}
        kind = "sql" if c["tool"] == "run_sql" else "tool"
        out["n"] += 1
        out[f"n_{kind}"] += 1
        ms["all"] += c["ms"]
        for level, k in keys.items():
            agents = earlier[level][k]
            if agents - {c["agent"]}:
                out[level] += 1
                out[f"{level}_{kind}"] += 1
                if level == "fact":
                    ms["fact"] += c["ms"]
            agents.add(c["agent"])
        if any(a != c["agent"] and abs(t - c["t0_ms"]) <= 60_000 for t, a in times[keys["fact"]]):
            out["concurrent60"] += 1
    n, n_sql = out["n"], out["n_sql"]
    return {
        "knowledge_calls": n,
        "knowledge_sql_calls": n_sql,
        "fact_repeat_pct": pct(out["fact"], n),
        "template_repeat_pct": pct(out["template"], n),
        "text_repeat_pct": pct(out["text"], n),
        "sql_fact_repeat_pct": pct(out["fact_sql"], n_sql),
        "sql_template_repeat_pct": pct(out["template_sql"], n_sql),
        "sql_text_repeat_pct": pct(out["text_sql"], n_sql),
        "fact_repeat_db_ms_pct": pct(ms["fact"], ms["all"]),
        "concurrent60_pct": pct(out["concurrent60"], n),
    }


def overlap_pairs(sessions):
    """同时活跃的会话对占比（会话时间窗相交）。"""
    ss = sorted(sessions.values(), key=lambda s: s["t0_ms"])
    n = len(ss)
    k = sum(1 for i in range(n) for j in range(i + 1, n) if ss[j]["t0_ms"] < ss[i]["t1_ms"])
    return k


def stats_for(model, sessions, by_sess, data):
    cats = collections.Counter(c["cat"] for c in data)
    n = len(data)
    sqls = [c for c in data if c["tool"] == "run_sql"]
    # SQL 模板稳定性：一条 SQL 的模板是否已在本负载中出现过（任何会话）
    seen, rep = set(), 0
    for c in sqls:
        k = fingerprint(sql_of(c))
        rep += k in seen
        seen.add(k)
    sess = list(sessions.values())
    per = []
    for a, s in sessions.items():
        cs = [c for c in by_sess.get(a, []) if c["cat"] is not None]
        per.append({
            "calls": len(cs),
            "sql": sum(c["tool"] == "run_sql" for c in cs),
            "seconds": (s["t1_ms"] - s["t0_ms"]) / 1000.0,
            "schema": sum(c["cat"] == "schema" for c in cs),
            "errors": sum(c["cat"] == "error" for c in cs),
            "validate": sum(c["cat"] == "validate" for c in cs),
            "explore": sum(c["cat"] in ("schema", "explore") for c in cs),
            "first_schema": bool(cs) and cs[0]["cat"] == "schema",
        })
    outcomes = collections.Counter(s["outcome"] for s in sess)
    return {
        "model": model,
        "sessions": len(sess),
        "outcomes": dict(outcomes),
        "calls": n,
        "categories": {k: cats[k] for k in ("schema", "explore", "validate", "attempt", "answer", "error", "other")},
        "category_pct": {k: pct(cats[k], n) for k in ("schema", "explore", "validate", "attempt", "answer", "error", "other")},
        "exploration_pct": pct(cats["schema"] + cats["explore"], n),
        "sql_calls": len(sqls),
        "sql_error_pct": pct(sum(c["status"] == "error" for c in sqls), len(sqls)),
        "sql_templates": len(seen),
        "sql_templates_per_100": round(100.0 * len(seen) / len(sqls), 1) if sqls else None,
        "sql_template_repeat_pct": pct(rep, len(sqls)),
        "session": {
            "median_calls": med([p["calls"] for p in per]),
            "median_sql": med([p["sql"] for p in per]),
            "median_seconds": med([p["seconds"] for p in per]),
            "median_schema_calls": med([p["schema"] for p in per]),
            "pct_start_with_schema": pct(sum(p["first_schema"] for p in per), len(per)),
            "pct_with_schema": pct(sum(p["schema"] > 0 for p in per), len(per)),
            "pct_with_error": pct(sum(p["errors"] > 0 for p in per), len(per)),
            "pct_with_validate": pct(sum(p["validate"] > 0 for p in per), len(per)),
            "mean_explore_share_pct": round(100.0 * statistics.mean(xs), 1) if (xs := [p["explore"] / p["calls"] for p in per if p["calls"]]) else None,
        },
        "overlapping_session_pairs": overlap_pairs(sessions),
        "redundancy": redundancy(data),
    }


def ask_kind(s):
    return (s.get("ask") or {}).get("kind", "?")


def equivalence(all_sessions, app):
    """同义不同写法：同一道题（或同一类题：指标 × 题型）答对的会话里，最终 SQL 有多少种模板；应用每类题一种。"""
    per_task = collections.defaultdict(list)
    per_class = collections.defaultdict(list)
    for model, s in all_sessions:
        if s["outcome"] != "correct" or not s.get("final_sql"):
            continue
        form = tuple(sorted(fingerprint(q) for q in s["final_sql"]))
        text = tuple(sorted(norm(q) for q in s["final_sql"]))
        per_task[s["task"]].append((form, text, model))
        per_class[(s["metric"], ask_kind(s))].append((form, text, model))
    app_class = collections.defaultdict(set)
    for a in app:
        app_class[(a["metric"], a["ask"]["kind"])].add(fingerprint(a["sql"]))
    tasks = {t: {"correct": len(v), "templates": len({f for f, _, _ in v}), "texts": len({x for _, x, _ in v})} for t, v in per_task.items()}
    classes = {
        f"{m}/{k}": {"correct": len(v), "templates": len({f for f, _, _ in v}), "app_templates": len(app_class[(m, k)])}
        for (m, k), v in per_class.items()
    }
    multi = [v for v in tasks.values() if v["correct"] >= 2]
    return {
        "tasks_with_2plus_correct": len(multi),
        "mean_templates_per_task": round(statistics.mean(v["templates"] for v in multi), 2) if multi else None,
        "mean_correct_per_task": round(statistics.mean(v["correct"] for v in multi), 2) if multi else None,
        "pct_tasks_with_2plus_templates": pct(sum(v["templates"] >= 2 for v in multi), len(multi)),
        "distinct_template_share_pct": pct(sum(v["templates"] for v in multi), sum(v["correct"] for v in multi)),
        "classes": classes,
        "total_class_templates": sum(v["templates"] for v in classes.values()),
        "total_app_templates": sum(v["app_templates"] for v in classes.values()),
        "per_task": tasks,
    }


def app_stats(app):
    fps = [fingerprint(a["sql"]) for a in app]
    seen, rep = set(), 0
    for f in fps:
        rep += f in seen
        seen.add(f)
    return {
        "queries": len(app),
        "templates": len(seen),
        "template_repeat_pct": pct(rep, len(app)),
        "queries_per_question": 1,
        "exploration_pct": 0.0,
        "validation_pct": 0.0,
        "error_pct": 0.0,
        "note": "应用把每类题（指标 × 题型）写成一条参数化 SQL，与判题的参考 SQL 相同；只执行不探查",
    }


def table(res):
    models = res["runs"]
    cols = [m["model"].split("/")[-1] for m in models] + ["pooled"]
    allm = models + [res["pooled"]]

    def row(name, f):
        return "| " + name + " | " + " | ".join(str(f(m)) for m in allm) + " |"

    lines = ["| metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    lines += [
        row("sessions (correct)", lambda m: f"{m['sessions']} ({m['outcomes'].get('correct', 0)})"),
        row("DB calls / session (median)", lambda m: m["session"]["median_calls"]),
        row("SQL templates per 100 SQL", lambda m: m["sql_templates_per_100"]),
        row("SQL whose template seen before %", lambda m: m["sql_template_repeat_pct"]),
        row("exploration calls % (schema+data)", lambda m: m["exploration_pct"]),
        row("  schema %", lambda m: m["category_pct"]["schema"]),
        row("  data explore %", lambda m: m["category_pct"]["explore"]),
        row("validation calls %", lambda m: m["category_pct"]["validate"]),
        row("abandoned attempts %", lambda m: m["category_pct"]["attempt"]),
        row("final-answer SQL %", lambda m: m["category_pct"]["answer"]),
        row("failed calls %", lambda m: m["category_pct"]["error"]),
        row("failed SQL % (of SQL)", lambda m: m["sql_error_pct"]),
        row("sessions with >=1 failure %", lambda m: m["session"]["pct_with_error"]),
        row("sessions with >=1 validation %", lambda m: m["session"]["pct_with_validate"]),
        row("sessions starting with schema lookup %", lambda m: m["session"]["pct_start_with_schema"]),
        row("session length s (median)", lambda m: m["session"]["median_seconds"]),
        row("knowledge calls: fact seen in earlier session %", lambda m: m["redundancy"]["fact_repeat_pct"]),
        row("  same template %", lambda m: m["redundancy"]["template_repeat_pct"]),
        row("  same text %", lambda m: m["redundancy"]["text_repeat_pct"]),
        row("knowledge SQL: fact / template / text %", lambda m: "{} / {} / {}".format(
            m["redundancy"]["sql_fact_repeat_pct"], m["redundancy"]["sql_template_repeat_pct"], m["redundancy"]["sql_text_repeat_pct"])),
        row("DB time of repeated facts %", lambda m: m["redundancy"]["fact_repeat_db_ms_pct"]),
        row("same fact by another session within 60 s %", lambda m: m["redundancy"]["concurrent60_pct"]),
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", default=None)
    ap.add_argument("--audit", type=int, default=80, help="随机抽取多少条已归类调用供人工核对")
    o = ap.parse_args()
    runs, all_sessions, all_data, app = [], [], [], []
    pooled_sessions, pooled_by_sess = {}, {}
    for d in o.dirs:
        model, sessions, by_sess, data = analyze_run(d)
        if not sessions:
            continue
        runs.append(stats_for(model, sessions, by_sess, data))
        all_sessions += [(model, s) for s in sessions.values()]
        all_data += data
        # 汇总时会话名加模型前缀；跨模型的重复不计（各模型各自一个负载）
        for a, s in sessions.items():
            pooled_sessions[f"{model}|{a}"] = s
            pooled_by_sess[f"{model}|{a}"] = by_sess.get(a, [])
        if not app and os.path.exists(os.path.join(d, "app.json")):
            with open(os.path.join(d, "app.json"), encoding="utf-8") as f:
                app = json.load(f)
    if not runs:
        sys.exit("没有已完成的会话")
    pooled = stats_for("pooled", pooled_sessions, pooled_by_sess, [dict(c, agent=f"{c['model']}|{c['agent']}") for c in all_data])
    # 汇总的冗余按模型分别计算后按调用数加权，避免把不同模型的负载当成同一个
    w = [r["redundancy"]["knowledge_calls"] for r in runs]
    for k in pooled["redundancy"]:
        if k.endswith("_pct"):
            vals = [r["redundancy"][k] for r in runs]
            pooled["redundancy"][k] = round(sum((v or 0) * x for v, x in zip(vals, w)) / sum(w), 1) if sum(w) else None
    res = {"runs": runs, "pooled": pooled, "equivalence": equivalence(all_sessions, app), "application": app_stats(app) if app else None}
    out = o.out or os.path.join(os.path.dirname(os.path.normpath(o.dirs[0])), "stats")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "workload-stats.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    md = table(res)
    eq = res["equivalence"]
    md += "\n\nSame semantics, different SQL (correct sessions only): "
    md += f"{eq['tasks_with_2plus_correct']} questions with >=2 correct sessions; mean {eq['mean_templates_per_task']} templates "
    md += f"over {eq['mean_correct_per_task']} correct sessions per question; {eq['pct_tasks_with_2plus_templates']}% of questions answered with >=2 templates; "
    md += f"{eq['total_class_templates']} templates over {len(eq['classes'])} question classes vs {eq['total_app_templates']} for the application.\n"
    if res["application"]:
        a = res["application"]
        md += f"Application: {a['queries']} queries, {a['templates']} templates, template repeat {a['template_repeat_pct']}%.\n"
    with open(os.path.join(out, "workload-stats.md"), "w", encoding="utf-8") as f:
        f.write(md)
    # 人工核对样本
    rnd = random.Random(7)
    sample = rnd.sample(all_data, min(o.audit, len(all_data)))
    with open(os.path.join(out, "audit-sample.jsonl"), "w", encoding="utf-8") as f:
        for c in sample:
            th = c.get("thought") or {}
            f.write(json.dumps({"model": c["model"], "agent": c["agent"], "task": c["task"], "tool": c["tool"], "cat": c["cat"],
                                "status": c["status"], "sql": sql_of(c) or c.get("args"), "result": (c.get("result") or "")[:200],
                                "reasoning": (th.get("reasoning") or "")[-300:]}, ensure_ascii=False) + "\n")
    print(md)
    print(f"写出 {out}/workload-stats.json、workload-stats.md、audit-sample.jsonl")


if __name__ == "__main__":
    main()
