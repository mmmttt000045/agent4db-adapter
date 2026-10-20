#!/usr/bin/env python3
"""AgentSM (Biswal et al., arXiv 2601.15709, preprint) for the RelBench harness, reimplemented from the paper (no
official code; two files of its anonymous repository survive on the Wayback Machine). See
exp/2026-10-20-relbench/reproduction-notes.md for every choice the paper leaves open and every adaptation.

Offline (`build`), once per database before evaluation, on the database at the first cutoff (Algorithm 1):
  GenQ writes synthetic tasks from the schema and up to 5 of the database's own tasks; an agent with only the schema
  and SQL tools (no validation, no submission) runs each one; answers are not checked. Each trajectory is split into
  exploration / execution / validation by rules on the tool calls, written as markdown with one header per step from
  the model, and indexed by the task text (all-MiniLM-L6-v2). Frequent consecutive tool sequences within one phase
  become composite tools (support >= 0.5, at most 3 tools, tools seen in several phases excluded), named by the model.
Online (`Memory`), read-only: `retrieve_trajectory` returns the exploration segment of the most similar synthetic
task of the same database; `schema_linking` runs a sub-agent with vector search over columns and a 5-step budget;
run_sql repairs a failing statement once; the composite tools run their tool sequence.

  python3 tools/relbench/agentsm.py build --data results/relbench-data/rel-stack --prep results/relbench-data/rel-stack-prep \
      --template relbench_stack_t1 --out results/relbench-agentsm/rel-stack --n 33
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import threading
import time

import numpy as np

import harness

GENQ_EXAMPLES = 5
SYNTH_MAX_LLM_CALLS = 20
OUTPUT_CHARS = 1000  # the archived parser cuts each output at 1000 characters
SUPPORT = 0.5
MAX_COMPOSITE = 3
LINKER_STEPS = 5
LINKER_TOP_K = 15
EMBED_PYTHON = "results/ext/venv-gmem/bin/python"

# GenQ(S, K, Q): the archived generator's prompt, with "Text2SQL questions" read as the benchmark's prediction tasks
GENQ_PROMPT = """
You are generating diverse, analytical prediction tasks for the database schema "{db}".

Context:
- Existing benchmark tasks for this schema:
{examples}
- External knowledge: {knowledge}

Requirements for the new task:
1) Different analytical pattern than the examples (entities, targets, time windows, joins, aggregates, filters, etc.).
2) Realistic and specific (include concrete entities/metrics relevant to the domain).
3) Answerable from the schema; avoid vague or unbounded tasks.

Return ONLY this JSON:
{{
  "question": "...",
  "reasoning": "one or two sentences explaining the analytical pattern and coverage"
}}
"""

SYNTH_SYSTEM = """You are a data agent working on a PostgreSQL database: {desc}
Explore the database to work out how to solve the task below: which tables, columns, joins and values it needs.
Tools: list_tables, describe_table and run_sql (read-only, at most 50 rows). When you know how to solve it, reply with a short description of the solution and no tool call."""

HEADERS_PROMPT = """Below are the steps of an agent's trajectory on a database task. Give each step a short markdown header (3-8 words) that says what the step does.
Return ONLY a JSON list of strings, one per step, in order.

Task: {task}

Steps:
{steps}"""

COMPOSITE_PROMPT = """The following sequence of tools is often called together by agents exploring a database: {seq}.
Give it a short snake_case tool name and a one-sentence description of what the combined tool does.
Return ONLY this JSON: {{"name": "...", "description": "..."}}"""

LINKER_SYSTEM = """You are a schema linking agent for a PostgreSQL database. Map the task below to the tables, columns and joins it needs.
Tools: vector_search(query) finds columns by meaning; describe_table(table); run_sql(sql) (read-only, at most 50 rows).
You have at most {steps} steps. Finish with a reply (no tool call) that lists the relevant tables, their columns, and the join keys."""

SQL_REPAIR_PROMPT = """This PostgreSQL query failed.
Query:
{sql}
Error:
{error}
Return ONLY the corrected query, with no explanation."""


def phase_of(name, args):
    """Phase of one tool call (the paper classifies steps by rules, not by position)."""
    if name in ("list_tables", "describe_table", "join_path", "check_join"):
        return "exploration"
    if name == "run_sql":
        q = (args.get("sql") or "").lower()
        if re.search(r"information_schema|pg_catalog", q) or (re.search(r"\blimit\s+\d+", q) and not re.search(r"\bgroup\s+by\b|\bjoin\b", q)):
            return "exploration"
        return "execution"
    if name in ("validate_features",):
        return "execution"
    return "validation"


def split_phases(steps):
    """Steps after the last execution step are validation (checking the result)."""
    phases = [phase_of(s["name"], s["args"]) for s in steps]
    last_exec = max([i for i, p in enumerate(phases) if p == "execution"], default=-1)
    return [("validation" if i > last_exec >= 0 and p != "exploration" else p) for i, p in enumerate(phases)]


class Embedder:
    def __init__(self, out):
        self.err = open(os.path.join(out, "embed.log"), "a")
        e = {k: v for k, v in os.environ.items() if "proxy" not in k.lower() and k != "PYTHONPATH"}
        e.update(HF_ENDPOINT="https://hf-mirror.com", TOKENIZERS_PARALLELISM="false")
        here = os.path.dirname(os.path.abspath(__file__))
        self.proc = subprocess.Popen([EMBED_PYTHON, os.path.join(here, "embed_service.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self.err, env=e, text=True, bufsize=1)
        if not json.loads(self.proc.stdout.readline() or "{}").get("ready"):
            raise RuntimeError("embedding service did not start; see embed.log")
        self.lock = threading.Lock()

    def __call__(self, texts):
        with self.lock:
            self.proc.stdin.write(json.dumps({"texts": texts}) + "\n")
            self.proc.stdin.flush()
            return np.array(json.loads(self.proc.stdout.readline())["vectors"])

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(30)


def tool_loop(llm, system, user, tools, call, max_calls, log_calls):
    """A plain tool-calling loop; `call(name, args) -> output dict`. Returns (steps, final text)."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    steps = []
    for _ in range(max_calls):
        r = llm.chat(msgs, tools)
        m = r.pop("message")
        log_calls.append(r)
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls")} | {"role": "assistant"})
        calls = m.get("tool_calls") or []
        if not calls:
            return steps, m.get("content") or ""
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            out = call(name, args)
            text = json.dumps(out, ensure_ascii=False, default=str)
            steps.append({"name": name, "args": args, "output": text[:OUTPUT_CHARS]})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": text[:harness.TOOL_OUTPUT_CHARS]})
    return steps, ""


def spec(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": req}}}


SCHEMA_TOOLS = [
    spec("list_tables", "List the tables with estimated row counts and comments.", {}, []),
    spec("describe_table", "Profile a table: columns, types, null ratios, distinct counts, common values, sample rows.", {"table": {"type": "string"}}, ["table"]),
    spec("run_sql", "Run one read-only SQL query on PostgreSQL; returns at most 50 rows.", {"sql": {"type": "string"}}, ["sql"]),
]


def build(a):
    """Offline memory of one database (Algorithm 1)."""
    os.makedirs(a.out, exist_ok=True)
    ns = argparse.Namespace(arm="none", run=0, data=a.data, prep=a.prep, template=a.template, out=a.out, tasks=None, cutoffs=None,
                            parallel=1, port=None, keep_db=False, smoke=False)
    r = harness.Run(ns)
    llm = r.llm
    log_calls = []
    harness.create_run_db(r.url_admin, a.template, r.db_name)
    middle = None
    try:
        middle = harness.Middle(r.url, "middle-alone", a.out, 18900 + os.getpid() % 90)
        desc = r.manifest.get("description", "")
        examples = "\n".join(f"- {r.task_desc[t]['description']}" for t in list(r.tasks)[:GENQ_EXAMPLES]) or "- (no benchmark tasks available)"
        tasks = []
        for i in range(a.n):
            g = llm.chat([{"role": "user", "content": GENQ_PROMPT.format(db=a.db_name, examples=examples, knowledge=desc or "(none)")}])
            log_calls.append({k: v for k, v in g.items() if k != "message"})
            text = g["message"].get("content") or ""
            try:
                q = json.loads(text[text.find("{"): text.rfind("}") + 1])["question"]
            except (ValueError, KeyError):
                continue
            tasks.append({"id": f"syn{i}", "question": q})
        harness.log(f"GenQ: {len(tasks)} synthetic tasks")
        def synth(tsk):
            sid = f"agentsm-build-{tsk['id']}"

            def call(name, args):
                try:
                    return middle.call(name, "agentsm-synth", sid, sid, args)
                except Exception as err:
                    return {"error": str(err)}

            calls = []
            steps, final = tool_loop(llm, SYNTH_SYSTEM.format(desc=desc), f"Task: {tsk['question']}", SCHEMA_TOOLS, call,
                                     SYNTH_MAX_LLM_CALLS, calls)
            return steps, final, calls

        import concurrent.futures as cf

        with cf.ThreadPoolExecutor(4) as ex:
            runs = list(ex.map(synth, tasks))
        trajs = []
        for k, (tsk, (steps, final, calls)) in enumerate(zip(tasks, runs)):
            log_calls.extend(calls)
            phases = split_phases(steps)
            listing = "\n".join(f"{i + 1}. {s['name']} {json.dumps(s['args'], ensure_ascii=False)[:200]}" for i, s in enumerate(steps))
            headers = []
            if steps:
                h = llm.chat([{"role": "user", "content": HEADERS_PROMPT.format(task=tsk["question"], steps=listing)}])
                log_calls.append({k2: v for k2, v in h.items() if k2 != "message"})
                ht = h["message"].get("content") or ""
                try:
                    headers = json.loads(ht[ht.find("["): ht.rfind("]") + 1])
                except ValueError:
                    headers = []
            segments = collections.defaultdict(str)
            for i, (s, p) in enumerate(zip(steps, phases)):
                head = headers[i] if i < len(headers) and isinstance(headers[i], str) else s["name"]
                segments[p] += f"## {head}\n**Action:** {s['name']}({json.dumps(s['args'], ensure_ascii=False)})\n**Observation:** {s['output']}\n\n"
            if final:
                segments["validation"] += f"## Final answer\n{final[:OUTPUT_CHARS]}\n"
            trajs.append({**tsk, "steps": [{"name": s["name"], "args": s["args"], "phase": p} for s, p in zip(steps, phases)],
                          "segments": dict(segments)})
            harness.log(f"synthetic {k + 1}/{len(tasks)}: {len(steps)} steps")
        # composite tools: consecutive sequences within one phase, from tools that appear in a single phase only
        tool_phases = collections.defaultdict(set)
        for tr in trajs:
            for s in tr["steps"]:
                tool_phases[s["name"]].add(s["phase"])
        single = {t for t, ps in tool_phases.items() if len(ps) == 1}
        support = collections.Counter()
        for tr in trajs:
            seen = set()
            st = tr["steps"]
            for size in range(2, MAX_COMPOSITE + 1):
                for i in range(len(st) - size + 1):
                    win = st[i:i + size]
                    if len({s["phase"] for s in win}) == 1 and all(s["name"] in single for s in win):
                        seen.add(tuple(s["name"] for s in win))
            support.update(seen)
        composites = []
        for seq, f in support.most_common():
            if not trajs or f / len(trajs) < SUPPORT:
                continue
            c = llm.chat([{"role": "user", "content": COMPOSITE_PROMPT.format(seq=" -> ".join(seq))}])
            log_calls.append({k2: v for k2, v in c.items() if k2 != "message"})
            ct = c["message"].get("content") or ""
            try:
                nd = json.loads(ct[ct.find("{"): ct.rfind("}") + 1])
                name = re.sub(r"[^a-z0-9_]", "_", nd["name"].lower())[:40]
            except (ValueError, KeyError):
                continue
            composites.append({"name": name, "description": nd.get("description", ""), "tools": list(seq), "support": f / len(trajs)})
        emb = Embedder(a.out)
        vecs = emb([t["question"] for t in trajs]).tolist() if trajs else []
        emb.close()
        cost = {"llm_calls": len(log_calls), "input_tokens": sum(x.get("input_tokens", 0) for x in log_calls),
                "output_tokens": sum(x.get("output_tokens", 0) for x in log_calls)}
        json.dump({"db": a.db_name, "n": a.n, "built_on": r.timeline["tasks"][next(iter(r.tasks))]["cutoffs"][0]["test_timestamp"],
                   "trajectories": trajs, "vectors": vecs, "composites": composites, "offline_cost": cost},
                  open(os.path.join(a.out, "memory.json"), "w"), ensure_ascii=False, indent=1)
        harness.log(f"memory: {len(trajs)} trajectories, {len(composites)} composite tools, cost {cost}")
    finally:
        if middle:
            middle.close()
        harness.drop_db(r.url_admin, r.db_name)


class Memory:
    """AgentSM at evaluation time (read-only memory of one database)."""

    def __init__(self, path, run, out):
        self.m = json.load(open(path))
        # composite tools named alike by the model get distinct names (a tool list must not repeat a name)
        seen = set()
        for c in self.m["composites"]:
            base, i = c["name"], 2
            while c["name"] in seen:
                c["name"] = f"{base}_{i}"
                i += 1
            seen.add(c["name"])
        self.vecs = np.array(self.m["vectors"]) if self.m["vectors"] else np.zeros((0, 384))
        self.run = run
        self.emb = Embedder(out)
        self.cols = None
        self.col_vecs = None

    def close(self):
        self.emb.close()

    def tool_specs(self):
        out = [
            spec("retrieve_trajectory", "Retrieve the trajectory of the most similar earlier task on this database (exploration phase by default). Call it before you start.",
                 {"query": {"type": "string"}, "phase": {"type": "string", "enum": ["exploration", "execution", "validation"]}}, ["query"]),
            spec("schema_linking", "Ask the schema linking agent to map a task to the relevant tables, columns and joins (vector search over columns, at most 5 steps).",
                 {"question": {"type": "string"}}, ["question"]),
        ]
        for c in self.m["composites"]:
            out.append(spec(c["name"], f"{c['description']} (runs {' -> '.join(c['tools'])}; pass the arguments of each call in order)",
                            {"calls": {"type": "array", "items": {"type": "object"}}}, ["calls"]))
        return out

    def names(self):
        return {"retrieve_trajectory", "schema_linking", *(c["name"] for c in self.m["composites"])}

    def retrieve(self, query, phase="exploration"):
        if not len(self.vecs):
            return {"trajectory": None, "note": "no stored trajectories"}
        q = self.emb([query])[0]
        i = int(np.argmax(self.vecs @ q))
        tr = self.m["trajectories"][i]
        return {"similar_task": tr["question"], "phase": phase, "trajectory": tr["segments"].get(phase, "(empty)")}

    def _columns(self, middle, agent, sid):
        if self.cols is None:
            tables = middle.call("list_tables", agent, sid, sid, {}).get("tables", [])
            cols = []
            for t in tables:
                p = middle.call("describe_table", agent, sid, sid, {"table": t["table"]}).get("profile", {})
                for c in p.get("columns", []):
                    cols.append(f"{t['table']}.{c['name']} ({c.get('type')}){': ' + c['comment'] if c.get('comment') else ''}")
            self.cols = cols
            self.col_vecs = self.emb(cols)
        return self.cols

    def schema_linking(self, question, middle, agent, sid, llm, log_calls):
        cols = self._columns(middle, agent, sid)

        def call(name, args):
            if name == "vector_search":
                q = self.emb([args.get("query", "")])[0]
                top = np.argsort(-(self.col_vecs @ q))[:LINKER_TOP_K]
                return {"columns": [cols[i] for i in top]}
            if name in ("describe_table", "run_sql"):
                try:
                    return middle.call(name, agent, sid, sid, args)
                except Exception as err:
                    return {"error": str(err)}
            return {"error": f"unknown tool {name}"}

        tools = [spec("vector_search", "Find columns whose meaning matches the query.", {"query": {"type": "string"}}, ["query"]), *SCHEMA_TOOLS[1:]]
        steps, final = tool_loop(llm, LINKER_SYSTEM.format(steps=LINKER_STEPS), f"Task: {question}", tools, call, LINKER_STEPS, log_calls)
        return {"schema_mapping": final or "(the schema linking agent used its 5 steps without a final mapping)", "_sub_tool_calls": len(steps)}

    def composite(self, name, args, middle, agent, sid, run_sql):
        c = next(x for x in self.m["composites"] if x["name"] == name)
        calls = args.get("calls") or []
        outs = []
        for i, t in enumerate(c["tools"]):
            a = calls[i] if i < len(calls) and isinstance(calls[i], dict) else {}
            outs.append({t: run_sql(a) if t == "run_sql" else middle.call(t, agent, sid, sid, a)})
        return {"results": outs}


def repair_sql(llm, sql, error, log_calls):
    r = llm.chat([{"role": "user", "content": SQL_REPAIR_PROMPT.format(sql=sql, error=error)}])
    log_calls.append({k: v for k, v in r.items() if k != "message"})
    text = (r["message"].get("content") or "").strip()
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--data", required=True)
    b.add_argument("--prep", required=True)
    b.add_argument("--template", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--n", type=int, required=True, help="synthetic tasks for this database (its share of the global n = 100)")
    b.add_argument("--db-name", dest="db_name", default=None)
    a = ap.parse_args()
    if a.cmd == "build":
        a.db_name = a.db_name or os.path.basename(a.data.rstrip("/"))
        build(a)


if __name__ == "__main__":
    main()
