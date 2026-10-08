#!/usr/bin/env python3
"""Print the tool-call sequence of every task in a metric-bench trace (trace-<cell>.jsonl).

usage: trace-stats.py <trace.jsonl> [task-id-prefix ...]

For each task: agent, task id, then one line per call — seq, tool, abbreviated arguments,
status, rows / ref, and milliseconds. Arguments are shortened to keep SQL readable.
"""
import json
import sys


def short(v, n=150):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def args_text(tool, args):
    if tool == "run_sql":
        sql = short(args.get("sql", ""), 170)
        m = args.get("metrics")
        return f"sql={sql}" + (f"  metrics={json.dumps(m, ensure_ascii=False)}" if m else "")
    if tool == "final_answer":
        keep = {k: args[k] for k in ("answer", "used", "derivation") if k in args}
        return short(keep, 120)
    return short(args, 120)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    prefixes = sys.argv[2:]
    tasks = {}
    order = []
    with open(sys.argv[1], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            key = (e.get("agent"), e.get("session"), e.get("task"))
            if key not in tasks:
                tasks[key] = []
                order.append(key)
            tasks[key].append(e)
    for key in order:
        agent, session, task = key
        if prefixes and not any(str(task).startswith(p) for p in prefixes):
            continue
        calls = tasks[key]
        total = sum(c.get("ms", 0) for c in calls)
        print(f"## {agent} · {task}  （{len(calls)} 次工具调用，工具侧共 {total:.0f} ms；session {session}）")
        for c in calls:
            extra = ""
            if c.get("rows") is not None:
                extra += f" rows={c['rows']}"
            if c.get("ref"):
                extra += f" ref={c['ref']}"
            status = c.get("status", "")
            res = c.get("result") or ""
            res = short(res, 160) if status != "ok" or c["tool"] in ("find_metric", "join_path", "describe_table") else ""
            print(f"  {c.get('seq', 0) + 1:>2}. {c['tool']:<16} {args_text(c['tool'], c.get('args') or {})}  → {status}{extra} {c.get('ms', 0):.0f}ms")
            if res:
                print(f"      ↳ {res}")
        print()


if __name__ == "__main__":
    main()
