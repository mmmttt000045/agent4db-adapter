#!/usr/bin/env python3
"""Summarize complete, matched happycoding SQL-only/MAVRA runs; never pool old providers."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path


def load(path):
    meta = json.loads((path / "run.json").read_text())
    if not meta.get("finished") or meta.get("error") or meta.get("smoke"):
        raise ValueError(f"{path}: not a complete production run")
    expected = {(t, c["k"]) for c in meta["cutoffs"] for t in c["order"]}
    if len(expected) != 15 or {k for _, k in expected} != set(range(1, 6)):
        raise ValueError(f"{path}: expected three tasks at five cutoffs")
    refs = {(t, c["k"]): v for c in meta["cutoffs"] for t, v in c["reference"].items()}
    rows = {}
    sources = {}
    for file in sorted((path / "sessions").glob("*.json")):
        if file.name.endswith(".partial.json"):
            raise ValueError(f"{file}: unfinished session")
        s = json.loads(file.read_text())
        key = (s["task"], s["k"])
        if key in rows or s.get("error") or s["stop"] == "llm_error":
            raise ValueError(f"{file}: duplicate or interrupted session")
        ev, audit = s.get("eval") or {}, s.get("audit") or {}
        solved = audit.get("result") == "clean" and ev.get("test") is not None
        if audit.get("result") == "clean" and ev.get("test") is None:
            raise ValueError(f"{file}: clean SQL has unresolved test evaluation")
        test = ev.get("test") if solved else refs[key].get("test")
        if test is None:
            raise ValueError(f"{file}: missing score and fallback")
        if any(x.get("model") != meta["settings"]["require_model"] for x in s["llm"]):
            raise ValueError(f"{file}: response model mismatch")
        totals = s["totals"]
        calls, old_sql = {}, None
        for msg in s["messages"]:
            for call in msg.get("tool_calls") or []:
                calls[call["id"]] = call["function"]["name"]
            if msg.get("role") == "tool" and calls.get(msg.get("tool_call_id")) == "find_program":
                try:
                    old_sql = json.loads(msg["content"]).get("program_sql")
                except (ValueError, TypeError):
                    pass
        first_sql = (s["validations"][0].get("sql") if s["validations"] else None)
        norm = lambda sql: " ".join(sql.split()).rstrip(";") if sql else None
        rows[key] = dict(task=key[0], k=key[1], tokens=totals["tokens_with_learning"],
                         learning_tokens=totals["learn_tokens"], llm_calls=totals["llm_calls"],
                         tool_calls=totals["tool_calls"], agent_seconds=s["agent_seconds"],
                         learning_seconds=totals["learn_seconds"], test=test, solved=solved,
                         higher=s["higher_is_better"], target=s.get("target"), stop=s["stop"],
                         leaked_validations=sum(v.get("leak") is True for v in s["validations"]),
                         first_validation_old_sql=bool(old_sql) and norm(first_sql) == norm(old_sql),
                         goal_at_first_validation=(s.get("goal_reached") or {}).get("validation") == 1,
                         sql_saved=(s.get("sql_memory") or {}).get("saved"),
                         retry_seconds=totals.get("llm_retry_seconds", 0))
        sources[str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
    if set(rows) != expected:
        raise ValueError(f"{path}: session set does not match timeline")
    return meta, rows, sources


def aggregate(rows):
    return {**{key: sum(x[key] for x in rows) for key in
               ("tokens", "learning_tokens", "llm_calls", "tool_calls", "agent_seconds", "learning_seconds",
                "solved", "leaked_validations", "first_validation_old_sql", "goal_at_first_validation", "retry_seconds")},
            "n": len(rows), "test_means": {t: statistics.mean(x["test"] for x in rows if x["task"] == t)
                                             for t in sorted({x["task"] for x in rows})}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args()
    report = {"scope": "One paired sequence per database; descriptive, not independent-run significance.", "databases": {}}
    lines = ["# SQL-only 与 MAVRA 的 happycoding 配对实验", "", report["scope"], "",
             "时间包含共享服务器争用；token 含 MAVRA 学习成本。质量失败使用同一实体表参照，不丢弃会话。", "",
             "| 数据库 | 截点 | SQL-only token | MAVRA token | MAVRA 相对节省 | SQL-only / MAVRA 调用数 |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    quality_lines = []
    for db in ("rel-stack", "rel-trial"):
        data = {arm: load(a.root / f"{arm}-{db}-r{a.run}") for arm in ("sql-only", "mavra")}
        metas = [d[0] for d in data.values()]
        for key in ("model", "llm", "reasoning_effort", "thinking", "base_url", "require_model", "harness_sha256",
                    "MAX_LLM_CALLS", "MAX_VALIDATIONS", "PATIENCE", "SAMPLE_SIZE", "LGB_PARAMS"):
            if metas[0]["settings"].get(key) != metas[1]["settings"].get(key):
                raise ValueError(f"{db}: mismatched {key}")
        if metas[0]["settings"]["llm"] != "happy" or not metas[0]["settings"].get("require_model"):
            raise ValueError("this experiment requires happy with response model verification")
        if [(c["k"], c["order"]) for c in metas[0]["cutoffs"]] != [(c["k"], c["order"]) for c in metas[1]["cutoffs"]]:
            raise ValueError(f"{db}: unmatched arrival order")
        result = {"settings": metas[0]["settings"], "sources": {}, "sessions": {}, "aggregates": {}}
        for arm, (_, rows, sources) in data.items():
            result["sources"].update(sources)
            result["sessions"][arm] = [rows[k] for k in sorted(rows)]
        for scope, min_k in (("all", 1), ("reuse", 2)):
            ag = {arm: aggregate([r for r in d[1].values() if r["k"] >= min_k]) for arm, d in data.items()}
            saving = 1 - ag["mavra"]["tokens"] / ag["sql-only"]["tokens"]
            result["aggregates"][scope] = {**ag, "mavra_token_saving_fraction": saving}
            lines.append(f"| {db} | {min_k}–5 | {ag['sql-only']['tokens']:,} | {ag['mavra']['tokens']:,} | "
                         f"{saving:.1%} | {ag['sql-only']['llm_calls']} / {ag['mavra']['llm_calls']} |")
        quality_lines += ["", f"## {db} 逐任务测试质量", "", "| 任务 | SQL-only | MAVRA | MAVRA 超出质量容差的截点 |",
                          "| --- | ---: | ---: | --- |"]
        for task in sorted({t for t, k in data["mavra"][1]}):
            outside = []
            for k in range(1, 6):
                s, m = (data[arm][1][task, k] for arm in ("sql-only", "mavra"))
                within = m["test"] >= s["test"] - .01 if m["higher"] else m["test"] <= s["test"] * 1.02
                if not within:
                    outside.append(str(k))
            means = result["aggregates"]["all"]
            quality_lines.append(f"| {task} | {means['sql-only']['test_means'][task]:.5f} | "
                                 f"{means['mavra']['test_means'][task]:.5f} | {', '.join(outside) or '无'} |")
        report["databases"][db] = result
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (a.out / "results.md").write_text("\n".join(lines + quality_lines) + "\n")
    print("\n".join(lines + quality_lines))


if __name__ == "__main__":
    main()
