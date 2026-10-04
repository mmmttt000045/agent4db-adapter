#!/usr/bin/env python3
"""Audit shared-memory experiments and generate manuscript tables from raw records.

SQL probe classifier: adopted answer refs (including derivation) take precedence;
remaining successful schema SQL, distribution/count/sample SQL, and explicit
validation patterns count as probes. Unused measure aggregates are attempts,
except recomputations after the first adopted query, which count as validation.
This is a trace proxy, not a semantic proof of intent. No p-values are computed:
three producer streams and repeated probes do not justify task-independent tests.
"""

import argparse
import collections
import hashlib
import json
import re
import statistics
from pathlib import Path

POLICIES = ["isolated", "frozen", "accumulating", "trajectory"]
LABELS = {"isolated": ("Isolated", "隔离"), "frozen": ("Frozen", "冻结"),
          "accumulating": ("Accumulating", "积累"), "trajectory": ("Trajectory", "轨迹")}
TABLE_RE = re.compile(r"\b(store_sales|store_returns|catalog_sales|date_dim|item|etl_batch_log)\b")
COL_RE = re.compile(r"\b(?:ss|sr|cs|d|i)_[a-z_]+\b")
CATALOG_RE = re.compile(r"\b(information_schema|pg_catalog|pg_[a-z_]+)\b")
VALIDATE_RE = re.compile(r"count\s*\(\s*distinct|having\s+count|\bis\s+(?:not\s+)?null\b|row_number\s*\(\s*\)\s*over\s*\(\s*partition")
MEASURE_RE = re.compile(r"\b(sum|avg)\s*\(")
REF_RE = re.compile(r"\br(\d+)\b")


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def reports(paths, kind):
    out = []
    for root in map(Path, paths):
        candidates = [root] if root.is_file() else sorted(root.rglob("report.json"))
        for p in candidates:
            v = json.loads(p.read_text())
            if (kind == "memory" and "prefixes" in v and "records" in v) or (kind == "strategy" and "test_groups" in v):
                out.append((p, v))
    if len(out) != 3:
        raise ValueError(f"Expected exactly three completed {kind} reports, found {len(out)}")
    return out


def refs(record):
    run = record["run"]
    text = " ".join(map(str, run.get("used") or [])) + " " + (run.get("derivation") or "")
    return {int(x) for x in REF_RE.findall(text)}


def classify(call, adopted, first_answer):
    tool, status = call["tool"], call["status"]
    if status in ["error", "rejected"]:
        return status
    if tool in ["list_tables", "describe_table"]:
        return "schema-tool"
    if tool in ["find_metric", "find_trajectory"]:
        return "retrieval"
    if tool in ["check_join", "join_path"]:
        return "relationship"
    if tool != "run_sql":
        return "other"
    sql = re.sub(r"\s+", " ", call["args"]["sql"].lower())
    ref = call.get("ref")
    if ref and int(ref.lstrip("r")) in adopted:
        return "answer-sql"
    if CATALOG_RE.search(sql) and not TABLE_RE.search(re.sub(r"'[^']*'", "", sql)):
        return "schema-sql"
    if not TABLE_RE.search(sql):
        return "compute-sql"
    if VALIDATE_RE.search(sql):
        return "validate-sql"
    if MEASURE_RE.search(sql) and COL_RE.search(sql):
        return "validate-sql" if first_answer is not None and call["t0_ms"] > first_answer else "attempt-sql"
    return "explore-sql"


def mean(xs):
    return statistics.mean(xs) if xs else 0.0


def delta(new, old):
    return 100.0 * (new / old - 1) if old else None


def aggregate(xs):
    correct = sum(x["outcome"] == "correct" for x in xs)
    n = len(xs)
    counts = collections.Counter(x["outcome"] for x in xs)
    sums = {name: sum(x["analysis"][name] for x in xs) for name in
            ["input_tokens", "output_tokens", "rounds", "tools", "schema_calls", "sql_probes", "seconds", "db_ms", "db_queries"]}
    return {"n": n, "correct": correct, "outcomes": dict(counts), "totals": sums,
            "per_attempt": {k: v/n if n else None for k, v in sums.items()},
            "per_correct": {k: v/correct if correct else None for k, v in sums.items()},
            "token_counts_lower_bound": counts["error"] > 0}


def matched_completed(rows, policies):
    """Post hoc sensitivity: select by recorded execution, never by correctness."""
    grouped = collections.defaultdict(list)
    for r in rows:
        if r["defined"]:
            grouped[(r["repeat"], r["wave"], r["phase"], r["task"])].append(r)
    kept = {k: v for k, v in grouped.items()
            if all(r["outcome"] != "error" for r in v if r["policy"] in policies)}
    return {"groups": len(kept), "keys": [list(k) for k in sorted(kept)],
            "selection": "Post hoc recorded-execution sensitivity; all selected policies must return without error. Wrong answers and clarifications are retained. Missingness depends on method order and availability; this does not replace all-attempt analysis.",
            "policies": {p: aggregate([r for xs in kept.values() for r in xs if r["policy"] == p]) for p in policies}}


def analyze_memory(inputs):
    rows, sources, audit = [], [], []
    audited_strata = set()
    models = collections.Counter()
    for p, report in inputs:
        repeat = report["options"]["repeat"]
        if not report["database_cleaned_up"]:
            raise ValueError(f"Database not cleaned up: {p}")
        if report["options"]["metrics"] != ["M1", "M2", "M3", "M5"] or report["options"]["rows"] != 100_000:
            raise ValueError(f"Unexpected main workload: {p}")
        if report["agent"]["require_model"] != "deepseek/deepseek-v4.1-flash":
            raise ValueError(f"Main model is not locked: {p}")
        if report["agent"]["reasoning_effort"] != "high" or report["options"]["max_steps"] != 20 or report["options"]["extract_attempts"] != 2:
            raise ValueError(f"Unexpected model or task budget: {p}")
        calls = collections.defaultdict(list)
        trace_paths = sorted(p.parent.glob("trace-w*.jsonl"))
        for path in trace_paths:
            for line in path.read_text().splitlines():
                c = json.loads(line)
                calls[(c["agent"], c["session"], c["task"])].append(c)
        for r in report["records"]:
            adopted = refs(r)
            events = calls[(r["agent"], r["session"], r["task"])]
            times = [e["t0_ms"] for e in events if e.get("ref") and int(e["ref"].lstrip("r")) in adopted]
            categories = collections.Counter(classify(e, adopted, min(times) if times else None) for e in events)
            if len(events) != r["run"]["tool_calls"] and r["outcome"] != "error":
                raise ValueError(f"Incomplete trace: {r['agent']}")
            r["analysis"] = {"input_tokens": r["run"]["input_tokens"], "output_tokens": r["run"]["output_tokens"],
                             "rounds": r["run"]["steps"], "tools": len(events),
                             "schema_calls": sum(e["tool"] in ["list_tables", "describe_table"] for e in events),
                             "sql_probes": sum(categories[c] for c in ["schema-sql", "validate-sql", "explore-sql"]),
                             "seconds": r["seconds"], "db_ms": r["db"]["ms"], "db_queries": r["db"]["queries"],
                             "categories": dict(categories)}
            models.update(r["run"]["served_models"])
            rows.append(r)
            # First parameter, difference and ranking case per policy/stream,
            # plus every secondary named case. Selection ignores outcomes.
            stratum = (repeat, r["policy"], r["phase"], r["task"].rsplit("-", 1)[-1])
            if stratum not in audited_strata or r["phase"] == "final-named":
                audited_strata.add(stratum)
                audit.append({"repeat": repeat, "policy": r["policy"], "wave": r["wave"], "task": r["task"],
                              "phase": r["phase"], "outcome": r["outcome"],
                              "calls": [{"tool": e["tool"], "sql": (e.get("args") or {}).get("sql"),
                                         "ref": e.get("ref"), "category": classify(e, adopted, min(times) if times else None)} for e in events]})
        exact = []
        for wave in range(1, 5):
            cp = p.parent / f"prefix-{wave}.json"
            v = json.loads(cp.read_text())
            if v["summary"] != report["prefixes"][wave-1]:
                raise ValueError(f"Checkpoint summary mismatch: {cp}")
            if sum("Metric" in e["content"] for e in v["checkpoint"]["store"].values()) != v["summary"]["memory"].get("metric", 0):
                raise ValueError(f"Checkpoint contents mismatch: {cp}")
            exact.append({"wave": wave, "file": str(cp), "sha256": sha256(cp)})
        training = report["training"]
        for t in training:
            models.update(t["run"]["served_models"])
        sources.append({"repeat": repeat, "order": report["order"], "prefixes": report["prefixes"],
                        "attempts": len(training), "correct": sum(t["correct"] for t in training),
                        "published": sum(t["publication"].get("event") == "promoted" for t in training if isinstance(t["publication"], dict)),
                        "seconds": sum(t["total_seconds"] for t in training),
                        "agent_input_tokens": sum(t["run"]["input_tokens"] for t in training),
                        "agent_output_tokens": sum(t["run"]["output_tokens"] for t in training),
                        "extraction_input_tokens": sum((t["extraction"] or {}).get("input_tokens", 0) for t in training),
                        "extraction_output_tokens": sum((t["extraction"] or {}).get("output_tokens", 0) for t in training),
                        "exact_prefixes": exact, "report_sha256": sha256(p)})
    unique = [(r["repeat"], r["policy"], r["wave"], r["phase"], r["task"]) for r in rows]
    if len(rows) != 264 or len(set(unique)) != 264 or {s["repeat"] for s in sources} != {1, 2, 3}:
        raise ValueError("Expected the complete unique 264-attempt, three-stream matrix")
    grouped = collections.defaultdict(list)
    for r in rows:
        grouped[(r["repeat"], r["wave"], r["phase"], r["task"])].append(r)
    for key, xs in grouped.items():
        if {r["policy"] for r in xs} != set(POLICIES) or len({r["question"] for r in xs}) != 1 or len({r["gold"] for r in xs}) != 1:
            raise ValueError(f"Unmatched information or judge across methods: {key}")
    if set(models) != {"deepseek/deepseek-v4.1-flash"}:
        raise ValueError(f"Unexpected recorded served model: {dict(models)}")
    summary = {"primary": {p: aggregate([r for r in rows if r["policy"] == p and r["defined"]]) for p in POLICIES},
               "named": {p: aggregate([r for r in rows if r["policy"] == p and not r["defined"]]) for p in POLICIES},
               "streams": {str(i): {p: aggregate([r for r in rows if r["repeat"] == i and r["policy"] == p and r["defined"]]) for p in POLICIES} for i in [1, 2, 3]},
               "prefixes": {str(w): {p: aggregate([r for r in rows if r["wave"] == w and r["phase"] == "prefix-param" and r["policy"] == p]) for p in POLICIES} for w in range(1, 5)},
               "final_type": {p: aggregate([r for r in rows if r["phase"] == "final-type" and r["policy"] == p]) for p in POLICIES},
               "sources": sources, "served_models": dict(models), "records": rows,
               "audit": {"unique_attempts": len(unique), "matched_questions": len(grouped), "exact_checkpoints": 12,
                         "source_and_consumer_model_labels_checked": True,
                         "extraction_model_labels": "Not individually logged; exact model enforced by the same require_model response guard.",
                         "scope": "Three producer streams; descriptive paired results; named tasks secondary; no test-result publication. SQL probes use declared heuristic classifier."}}
    summary["paired_stream_deltas_pct"] = {str(i): {p: {k: (None if summary["streams"][str(i)][p]["token_counts_lower_bound"] or summary["streams"][str(i)]["isolated"]["token_counts_lower_bound"] else delta(summary["streams"][str(i)][p]["per_attempt"][k], summary["streams"][str(i)]["isolated"]["per_attempt"][k])) for k in ["input_tokens", "rounds", "schema_calls", "sql_probes", "seconds"]} for p in POLICIES if p != "isolated"} for i in [1, 2, 3]}
    summary["completed_sensitivity"] = matched_completed(rows, POLICIES)
    summary["completed_pair_sensitivity"] = {"isolation_accumulation": matched_completed(rows, ["isolated", "accumulating"]),
                                             "frozen_accumulation": matched_completed(rows, ["frozen", "accumulating"])}
    errors = [r for r in rows if r["outcome"] == "error"]
    summary["execution_errors"] = {"n": len(errors), "primary": sum(r["defined"] for r in errors),
                                    "named": sum(not r["defined"] for r in errors),
                                    "http_402": sum("HTTP 402" in (r["error"] or "") for r in errors),
                                    "warning": "Returned-answer accuracy and service availability are separate. Error-path token and round totals are lower bounds; full-matrix cost or accuracy differences involving failed arms are not causal method effects."}
    return summary, audit


def analyze_strategy(inputs):
    captures, settings = [], collections.defaultdict(list)
    for p, v in inputs:
        if not v["database_cleaned_up"] or (v["training_groups"], v["validation_groups"], v["test_groups"]) != (24, 16, 24):
            raise ValueError(f"Invalid strategy partition or cleanup: {p}")
        observed = json.loads((p.parent/"observations.json").read_text())
        if len(observed) != 64*3*3:
            raise ValueError(f"Incomplete strategy acquisition: {p}")
        capture = {"report": str(p), "sha256": sha256(p), "full_observation_ms": v["full_observation_ms"],
                   "collection_seconds": v["collection_seconds"], "results": v["results"]}
        captures.append(capture)
        for s in v["results"]:
            if len(s["tests"]) != 24:
                raise ValueError("Incomplete strategy held-out test")
            for t in s["tests"]:
                if not 40 <= t["group"] < 64 or any(x["pass"] != t["pass"] for x in t["permutations"]):
                    raise ValueError("Strategy test leakage or verdict mismatch")
            settings[s["setting"]].append(s)
    result = {}
    for name, xs in settings.items():
        default = sum(t["default_ms"] for x in xs for t in x["tests"])
        selected = sum(t["selected_ms"] for x in xs for t in x["tests"])
        fixed = collections.defaultdict(float)
        for x in xs:
            for t in x["tests"]:
                for order in t["permutations"]:
                    fixed[tuple(order["order"])] += order["ms"]
        best = min(fixed, key=fixed.get)
        result[name] = {"captures": len(xs), "test_evaluations": sum(len(x["tests"]) for x in xs),
                        "adopted": sum(x["adoption"]["adaptive"]["adopted"] for x in xs),
                        "default_ms": default, "selected_ms": selected, "saving_pct": -delta(selected, default) or 0.0,
                        "best_fixed_ms": fixed[best], "best_fixed_order": best,
                        "fixed_permutation_ms": {str(k): val for k, val in fixed.items()},
                        "capture_saving_pct": [-delta(sum(t["selected_ms"] for t in x["tests"]), sum(t["default_ms"] for t in x["tests"])) for x in xs],
                        "validation_evidence": [x["adoption"]["adaptive"] for x in xs]}
    return {"captures": captures, "settings": result, "full_observation_ms": sum(x["full_observation_ms"] for x in captures),
            "collection_seconds": sum(x["collection_seconds"] for x in captures), "verdict_mismatches": 0,
            "scope": "Three timing repetitions of one synthetic workload; chronological disjoint groups; retrospective best fixed order; observation acquisition excluded from counterfactual test costs."}


def write_macros(path, values):
    path.write_text("% Generated by tools/memory-study-stats.py from audited raw reports.\n" +
                    "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in values.items()))


def latex_strategy(v, gen):
    names = {"key-required": ("Key required", "需要补键"), "repair-exhausted": ("Repair exhausted", "修复耗尽"), "mixed": ("Alternating", "交替")}
    lines = [r"\begin{tabularx}{\linewidth}{@{}Lrrrr@{}}", r"\toprule",
             r"\bt{Setting}{设置} & \bt{Adopt}{采纳} & \bt{Default s}{默认秒} & \bt{Selected s}{选择秒} & \bt{Best fixed s}{最优固定秒}\\", r"\midrule"]
    for name in names:
        x = v["settings"][name]
        lines.append(f"\\bt{{{names[name][0]}}}{{{names[name][1]}}} & {x['adopted']}/3 & {x['default_ms']/1000:.3f} & {x['selected_ms']/1000:.3f} & {x['best_fixed_ms']/1000:.3f}\\\\")
    lines += [r"\bottomrule", r"\end{tabularx}"]
    (gen/"strategy-table.tex").write_text("\n".join(lines)+"\n")
    a, b, c = (v["settings"][k] for k in ["key-required", "repair-exhausted", "mixed"])
    en = f"The scorer adopts in {a['adopted']}/3 key-required captures, {b['adopted']}/3 exhausted-repair captures, and {c['adopted']}/3 alternating captures. Selected test costs change by {-a['saving_pct']:+.1f}\\%, {-b['saving_pct']:+.1f}\\%, and {-c['saving_pct']:+.1f}\\% relative to default, respectively."
    zh = f"需要补键、修复耗尽和交替设置分别在 {a['adopted']}/3、{b['adopted']}/3、{c['adopted']}/3 次采集中采纳；选择后的测试代价相对默认分别变化 {-a['saving_pct']:+.1f}\\%、{-b['saving_pct']:+.1f}\\%、{-c['saving_pct']:+.1f}\\%。"
    write_macros(gen/"strategy.tex", {"StFindingEn": en, "StFindingZh": zh,
                                     "StAuditSeconds": f"{v['full_observation_ms']/1000:.2f}", "StCollectionSeconds": f"{v['collection_seconds']:.2f}"})


def latex_memory(v, gen):
    lines = [r"\begin{tabularx}{\linewidth}{@{}Lrrrrr@{}}", r"\toprule",
             r"\bt{Method}{方法} & \bt{Correct (err)}{正确（异常）} & \bt{Turns}{轮数} & \bt{Input k}{输入千} & \bt{Schema/SQL}{结构/探查} & \bt{Time s}{秒}\\", r"\midrule",
             r"\multicolumn{6}{l}{\bt{Identical explicit definitions (primary)}{相同显式定义（主分析）}}\\"]
    for p in POLICIES:
        x = v["primary"][p]; m = x["per_attempt"]
        bound = r"$\geq$" if x["token_counts_lower_bound"] else ""
        lines.append(f"\\bt{{{LABELS[p][0]}}}{{{LABELS[p][1]}}} & {x['correct']}/{x['n']} ({x['outcomes'].get('error',0)}) & {bound}{m['rounds']:.2f} & {bound}{m['input_tokens']/1000:.2f} & {m['schema_calls']:.2f}/{m['sql_probes']:.2f} & {m['seconds']:.1f}\\\\")
    lines += [r"\midrule", r"\multicolumn{6}{l}{\bt{Metric names only (secondary)}{仅指标名（次分析）}}\\"]
    for p in POLICIES:
        x = v["named"][p]; m = x["per_attempt"]
        bound = r"$\geq$" if x["token_counts_lower_bound"] else ""
        lines.append(f"\\bt{{{LABELS[p][0]}}}{{{LABELS[p][1]}}} & {x['correct']}/{x['n']} ({x['outcomes'].get('error',0)}) & {bound}{m['rounds']:.2f} & {bound}{m['input_tokens']/1000:.2f} & {m['schema_calls']:.2f}/{m['sql_probes']:.2f} & {m['seconds']:.1f}\\\\")
    lines += [r"\bottomrule", r"\end{tabularx}"]
    (gen/"shared-memory-table.tex").write_text("\n".join(lines)+"\n")
    a, i, f = (v["primary"][p] for p in ["accumulating", "isolated", "frozen"])
    input_delta = delta(a["per_attempt"]["input_tokens"], i["per_attempt"]["input_tokens"])
    schema_delta = delta(a["per_attempt"]["schema_calls"], i["per_attempt"]["schema_calls"])
    frozen_delta = delta(a["per_attempt"]["input_tokens"], f["per_attempt"]["input_tokens"])
    errors = v["execution_errors"]
    if errors["n"]:
        returned = sum(x["n"]-x["outcomes"].get("error",0) for x in v["primary"].values())
        correct = sum(x["correct"] for x in v["primary"].values())
        en = f"Execution errors affect {errors['primary']} primary and {errors['named']} named attempts ({errors['http_402']} HTTP 402 errors overall). Of {returned} returned primary answers, {correct} are correct. Error-path tokens and turns are lower bounds; full-matrix differences involving those arms cannot establish method accuracy or cost benefits."
        zh = f"执行错误影响 {errors['primary']} 次主分析和 {errors['named']} 次命名尝试（共 {errors['http_402']} 次 HTTP 402）。主分析实际返回 {returned} 个答案，{correct} 个正确。错误路径的 token 与轮数是下界；涉及这些组的全矩阵差异不能证明方法准确率或成本收益。"
        if not a["token_counts_lower_bound"] and not f["token_counts_lower_bound"]:
            en += f" Frozen and accumulating memory have {f['correct']}/{f['n']} and {a['correct']}/{a['n']} correct answers; accumulating input tokens change by {frozen_delta:+.1f}\\% relative to frozen memory."
            zh += f" 冻结与积累分别答对 {f['correct']}/{f['n']}、{a['correct']}/{a['n']}；积累相对冻结的输入 token 变化 {frozen_delta:+.1f}\\%。"
    else:
        en = f"Accumulating memory answers {a['correct']}/{a['n']} primary tasks correctly, versus {i['correct']}/{i['n']} for isolation and {f['correct']}/{f['n']} for frozen memory. Its input-token and schema-call changes relative to isolation are {input_delta:+.1f}\\% and {schema_delta:+.1f}\\%; input tokens change by {frozen_delta:+.1f}\\% relative to frozen memory."
        zh = f"积累记忆主分析答对 {a['correct']}/{a['n']}，隔离为 {i['correct']}/{i['n']}，冻结为 {f['correct']}/{f['n']}。相对隔离，输入 token 与结构调用分别变化 {input_delta:+.1f}\\%、{schema_delta:+.1f}\\%；相对冻结，输入 token 变化 {frozen_delta:+.1f}\\%。"
    ds = [v["paired_stream_deltas_pct"][str(j)]["accumulating"]["input_tokens"] for j in [1, 2, 3]]
    if all(d is not None for d in ds):
        en += " Whole-stream input-token changes are " + ", ".join(f"{d:+.1f}\\%" for d in ds) + "."
        zh += " 三个完整流的输入 token 变化分别为 " + "、".join(f"{d:+.1f}\\%" for d in ds) + "。"
    if errors["primary"]:
        headline_en = f"A {sum(x['n'] for x in v['primary'].values())}-attempt definition-matched study has {errors['primary']} execution errors; incomplete usage prevents a full-matrix cost comparison."
        headline_zh = f"业务定义相同的 {sum(x['n'] for x in v['primary'].values())} 次尝试中有 {errors['primary']} 次执行异常，不完整用量无法支持全矩阵成本比较。"
    else:
        relation = lambda d: f"{abs(d):.1f}\\% {'fewer' if d < 0 else 'more'}"
        headline_en = f"In {sum(x['n'] for x in v['primary'].values())} definition-matched attempts, accumulating memory uses {relation(input_delta)} input tokens and {relation(schema_delta)} schema-tool calls than isolation, and {relation(frozen_delta)} input tokens than frozen memory."
        headline_zh = f"在 {sum(x['n'] for x in v['primary'].values())} 次业务定义相同的尝试中，积累记忆相对隔离使输入 token {'减少' if input_delta < 0 else '增加'} {abs(input_delta):.1f}\\%、结构工具调用{'减少' if schema_delta < 0 else '增加'} {abs(schema_delta):.1f}\\%；相对冻结使输入 token {'减少' if frozen_delta < 0 else '增加'} {abs(frozen_delta):.1f}\\%。"
        if all(x["correct"] == x["n"] for x in v["primary"].values()):
            headline_en += f" Every policy answers {a['n']}/{a['n']} correctly."
            headline_zh += f" 各方法均答对 {a['n']}/{a['n']}。"
        else:
            headline_en += f" Accumulating and isolated memory answer {a['correct']}/{a['n']} and {i['correct']}/{i['n']} correctly."
            headline_zh += f" 积累与隔离分别答对 {a['correct']}/{a['n']}、{i['correct']}/{i['n']}。"
    source_tokens = sum(sum(x[k] for k in ["agent_input_tokens", "agent_output_tokens", "extraction_input_tokens", "extraction_output_tokens"]) for x in v["sources"])
    write_macros(gen/"shared-memory.tex", {"MmFindingEn": en, "MmFindingZh": zh,
                                          "MmAbstractFindingEn": headline_en, "MmAbstractFindingZh": headline_zh,
                                          "MmPrimaryN": 216, "MmNamedN": 48,
                                          "MmTrainingTasks": sum(x["attempts"] for x in v["sources"]),
                                          "MmErrorsN": errors["n"],
                                          "MmSourceSeconds": f"{sum(x['seconds'] for x in v['sources']):.1f}",
                                          "MmSourceTokensK": f"{source_tokens/1000:.1f}"})
    curves = []
    styles = {"isolated": "mNoShare,mark=square*", "frozen": "mCache,mark=triangle*,densely dashed",
              "accumulating": "mCond,mark=*", "trajectory": "mTraj,mark=diamond*,densely dotted"}
    for p in POLICIES:
        points = " ".join(f"({w},{'nan' if v['prefixes'][str(w)][p]['token_counts_lower_bound'] else format(v['prefixes'][str(w)][p]['per_attempt']['input_tokens']/1000,'.5f')})" for w in range(1, 5))
        curves.append(f"\\addplot[{styles[p]},line width=.8pt,mark size=1.6pt] coordinates {{{points}}};")
        curves.append(f"\\addlegendentry{{\\bt{{{LABELS[p][0]}}}{{{LABELS[p][1]}}}}}")
    (gen/"shared-memory-prefix.tex").write_text("\n".join(curves)+"\n")


def markdown(summary):
    v = summary.get("memory")
    text = "# Shared memory study: audited results\n\n"
    if v:
        text += "Primary tasks provide identical business definitions; all attempts count. Costs per attempt exclude source learning. Errors are execution/service failures, separate from wrong answers. ≥ marks lower-bound usage after a failed execution.\n\n| Policy | Correct | Errors | Turns | Input tokens | Schema calls | SQL probes | Seconds |\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
        for p in POLICIES:
            x = v["primary"][p]; m = x["per_attempt"]
            bound = "≥" if x["token_counts_lower_bound"] else ""
            text += f"| {p} | {x['correct']}/{x['n']} | {x['outcomes'].get('error',0)} | {bound}{m['rounds']:.2f} | {bound}{m['input_tokens']:.1f} | {m['schema_calls']:.2f} | {m['sql_probes']:.2f} | {m['seconds']:.2f} |\n"
        text += "\nNamed secondary correctness: " + ", ".join(f"{p} {v['named'][p]['correct']}/{v['named'][p]['n']}" for p in POLICIES) + ".\n\n"
        text += "Paired stream input-token changes relative to isolation:\n\n| Stream | Frozen | Accumulating | Trajectory |\n|---|---:|---:|---:|\n"
        for i, ds in v["paired_stream_deltas_pct"].items():
            cells = ["unavailable" if ds[p]["input_tokens"] is None else f"{ds[p]['input_tokens']:+.1f}%" for p in ["frozen", "accumulating", "trajectory"]]
            text += f"| {i} | " + " | ".join(cells) + " |\n"
        if v["execution_errors"]["n"]:
            e=v["execution_errors"]
            text += f"\nExecution errors: {e['primary']} primary + {e['named']} named, including {e['http_402']} HTTP 402 credit failures. Full-matrix differences involving failed arms cannot establish method accuracy or cost benefits.\n"
            c=v["completed_sensitivity"]
            text += f"\nPost hoc recorded-execution sensitivity: {c['groups']} matched primary questions with no error in any arm. Selection ignores correctness and retains wrong answers or clarifications. Method order and service availability determine missingness; this does not replace the all-attempt analysis.\n\n| Policy | Correct | Input tokens | Schema calls | SQL probes |\n|---|---:|---:|---:|---:|\n"
            for p,x in c["policies"].items():
                m=x["per_attempt"]
                text += f"| {p} | {x['correct']}/{x['n']} | {m['input_tokens']:.1f} | {m['schema_calls']:.2f} | {m['sql_probes']:.2f} |\n"
        text += "\nSource acquisition:\n\n| Stream | Attempts | Published | Seconds | Agent tokens | Extraction tokens | Final valid entries |\n|---|---:|---:|---:|---:|---:|---:|\n"
        for s in v["sources"]:
            text += f"| {s['repeat']} | {s['attempts']} | {s['published']} | {s['seconds']:.2f} | {s['agent_input_tokens']+s['agent_output_tokens']} | {s['extraction_input_tokens']+s['extraction_output_tokens']} | {s['prefixes'][-1]['valid_metrics']} |\n"
        text += "\nThree producer streams are descriptive replicates. Repeated probes are correlated. SQL probe counts are a trace proxy; error-token totals, if any, are lower bounds. Exact model guard applies to extraction, but its individual return labels are not separately recorded.\n\n"
    if "initial_service_censored" in summary:
        old=summary["initial_service_censored"]
        e=old["execution_errors"]
        returned=sum(x["n"]-x["outcomes"].get("error",0) for x in old["primary"].values())
        correct=sum(x["correct"] for x in old["primary"].values())
        text += f"Initial metered-route experiment is retained separately: 264 attempts; {e['primary']} primary and {e['named']} named execution failures, including {e['http_402']} documented HTTP 402 credit failures. The recovery repeats the full matrix with the same binary, workload, model guard and budget through an available subscription route; producer prefixes, costs and outcomes are never pooled. Of {returned} returned initial primary answers, {correct} were correct; apparent differences in all-attempt success must be separated from availability. Full original statistics and post hoc recorded-execution sensitivity are in `initial-service-censored/`; raw records remain in `raw/results/shared-memory-main/`.\n\n"
    s = summary["strategy"]
    text += "Strategy test replay, summed across three timing captures of one workload:\n\n| Repair setting | Adopted | Default ms | Selected ms | Reduction | Best fixed ms |\n|---|---:|---:|---:|---:|---:|\n"
    for name, x in s["settings"].items():
        text += f"| {name} | {x['adopted']}/3 | {x['default_ms']:.3f} | {x['selected_ms']:.3f} | {x['saving_pct']:.1f}% | {x['best_fixed_ms']:.3f} |\n"
    text += f"\nFull observation acquisition: {s['full_observation_ms']/1000:.2f} seconds of checks; {s['collection_seconds']:.2f} seconds including setup/collection. Verdict mismatches: 0. Acquisition is excluded from the counterfactual test costs; this is not a live agent speedup. The best fixed order is a retrospective test oracle.\n"
    if "metadata" in summary:
        m = summary["metadata"]
        text += "\nExploratory metadata diagnostic (not a preregistered main comparison):\n\n"
        for row in m["records"]:
            cols = row["response"]["profile"]["columns"]
            text += f"- {row['stage']}: {row['response']['source']}; {row['probe_queries']} probe queries; {len(cols)} column definitions; {row['response']['profile']['row_count']} rows.\n"
        text += "\nComment-only changes leave sourced comments stale; additive DDL leaves the profile's column definitions stale, although SELECT * sample columns already expose the new name. An explicit restart refreshes definitions and comments. This is a live-catalog-refresh limitation, not a complete absence of information about the new column.\n"
    return text


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--memory", nargs="+")
    p.add_argument("--initial-memory", nargs="+", help="Retained original matrix with service censoring; never pool with recovery")
    p.add_argument("--strategy", nargs="+", required=True)
    p.add_argument("--metadata")
    p.add_argument("--out", required=True)
    p.add_argument("--latex-root", default="overleaf")
    args = p.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    gen = Path(args.latex_root)/"gen"; gen.mkdir(parents=True, exist_ok=True)
    s = analyze_strategy(reports(args.strategy, "strategy"))
    summary = {"strategy": s}
    if args.metadata:
        m = json.loads(Path(args.metadata).read_text())
        if not m["database_cleaned_up"] or len(m["records"]) != 6:
            raise ValueError("Metadata diagnostic incomplete or database not cleaned up")
        summary["metadata"] = m
    latex_strategy(s, gen)
    if args.memory:
        m, audit = analyze_memory(reports(args.memory, "memory"))
        summary["memory"] = m
        (out/"classification-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n")
        latex_memory(m, gen)
    if args.initial_memory:
        if not args.memory:
            raise ValueError("--initial-memory requires a separate --memory recovery matrix")
        initial, audit = analyze_memory(reports(args.initial_memory, "memory"))
        if {x['report_sha256'] for x in initial['sources']} & {x['report_sha256'] for x in summary['memory']['sources']}:
            raise ValueError("Initial and recovery inputs overlap")
        summary["initial_service_censored"] = initial
        saved=out/"initial-service-censored";saved.mkdir(exist_ok=True)
        initial_summary={"memory":initial,"strategy":s}
        if "metadata" in summary:
            initial_summary["metadata"]=summary["metadata"]
        (saved/"summary.json").write_text(json.dumps(initial_summary,ensure_ascii=False,indent=2)+"\n")
        (saved/"classification-audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
        (saved/"results.md").write_text(markdown(initial_summary))
    (out/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    (out/"results.md").write_text(markdown(summary))
    print(markdown(summary))


if __name__ == "__main__":
    main()
