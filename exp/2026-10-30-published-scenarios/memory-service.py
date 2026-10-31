#!/usr/bin/env python3
"""Published ACE/AWM adapters and the unchanged G-Memory core for SQL tasks.

Only the agent's question, own transcript, and binary correctness cross this
boundary. Gold SQL/answers and change labels never appear in memory prompts.
Every independent scenario restores the post-heldout checkpoint.
"""
import argparse
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import threading
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("relbench_harness", ROOT / "tools/relbench/harness.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
# Domain wording only. All published online sampling/induction settings remain.
h.AWM_OVERRIDES[0] = ("Given a list of web navigation tasks", "Given a list of analytical SQL tasks")
STATE_FIELDS = ("playbooks", "ace_steps", "awm_pool", "awm_workflows", "refs", "tasks", "task_desc")


def messages(req):
    result = [{"role": "system", "content": "Analytical SQL agent"},
              {"role": "user", "content": req["question"]}]
    for event in req["transcript"]:
        if event.get("kind") == "assistant":
            result.append({**event["message"], "role": "assistant"})
        elif event.get("kind") == "tool":
            content = event["output"]
            if event.get("status") == "error":
                content = json.dumps({"error": content}, ensure_ascii=False)
            result.append({"role": "tool", "tool_call_id": event["call_id"], "content": content})
    return result


class Actor:
    def __init__(self, key, arm, directory, proxy, model):
        self.key, self.arm = key, arm
        self.root = Path(directory) / key
        self.root.mkdir(parents=True, exist_ok=False)
        self.lock = threading.Lock()
        self.journal = self.root / "memory-events.jsonl"
        self.index, self.k, self.snapshot, self.gmem = 0, 0, None, None
        self.branch_index = 0
        self.branch = self.root / "branch-000"
        self.branch.mkdir()
        self.env = {"DEEPSEEK_API_KEY": "published-scenarios-20261030-local", "DEEPSEEK_MODEL": model,
                    "DEEPSEEK_BASE_URL": f"{proxy}/arm/{key}", "DEEPSEEK_THINKING": "enabled",
                    "DEEPSEEK_REASONING_EFFORT": "low", "DEEPSEEK_REQUIRE_MODEL": model}
        self.llm = h.Llm(self.env)
        # The official API is behind a loopback accounting relay. Older harness
        # versions infer the provider from the URL and otherwise omit G-Memory's
        # non-thinking override. This cohort is exclusively official DeepSeek.
        self.llm.keep_reasoning = True
        self.actor = h.Run.__new__(h.Run)
        self.actor.llm = self.llm
        self.actor.a = SimpleNamespace(out=str(self.branch), run=int(key.split("-r")[1].split("-")[0]))
        self.actor.timeline = {"K": 32 if key.startswith("synthetic-") else 26}
        for name in STATE_FIELDS:
            setattr(self.actor, name, {})
        self.active = None

    def gstart(self):
        if self.gmem is None:
            self.gmem = h.GMemoryService(self.env, str(self.branch), self.llm)
        return self.gmem

    def gsend(self, req):
        value = self.gstart().send(req)
        if value.get("error"):
            raise RuntimeError(value["error"])
        return value

    def close(self):
        if self.gmem is not None:
            self.gmem.close()
            self.gmem.err.close()
            self.gmem = None

    def begin(self, req):
        if self.active is not None:
            raise ValueError("Previous task has not ended")
        self.active = (req["task"], req["agent"], req["phase"])
        if self.arm == "ace":
            book = self.actor.playbooks.get(req["agent"], h.ACE_EMPTY_PLAYBOOK)
            block = (Path(h.ACE_DIR) / "appworld_playbook_block.txt").read_text().replace("{{ playbook }}", book)
            return {"system_prompt": "\n\n" + block + "\nReport any used playbook bullet IDs in final_answer.bullet_ids.",
                    "user_prompt": "", "playbook_bullets": h.ace_pb.get_playbook_stats(book)["total_bullets"]}
        if self.arm == "awm":
            workflows = self.actor.awm_workflows.get(req["agent"], "")
            return {"system_prompt": "\n\n" + workflows if workflows else "", "user_prompt": "",
                    "workflow_chars": len(workflows)}
        value = self.gsend({"op": "begin", "task_main": req["question"], "task_description": req["question"]})
        return {"system_prompt": "", "user_prompt": "\n\n" + value["prompt"], **value,
                "input_tokens": value.get("prompt_tokens", 0), "output_tokens": value.get("completion_tokens", 0)}

    def end(self, req):
        if self.active != (req["task"], req["agent"], req["phase"]):
            raise ValueError("Task-end mismatch")
        t0 = time.monotonic()
        self.k += 1
        t, agent, k = req["metric"], req["agent"], self.k
        period = req["ask"]["period"]
        cutoff = f"{period['year']:04}-{period['m1']:02}-01"
        e = self.actor.tasks.setdefault(t, {"cutoffs": []})
        while len(e["cutoffs"]) < k:
            e["cutoffs"].append({"test_timestamp": cutoff})
        e["cutoffs"][k - 1] = {"test_timestamp": cutoff}
        self.actor.task_desc[t] = {"description": req["question"]}
        correctness = float(bool(req["correct"]))
        rec = {"metric": "answer_correctness", "best_val": correctness, "higher_is_better": True,
               "validations": [{"val": correctness}], "stop": "model_error" if req.get("error") else "task_end",
               "final_sql": req.get("sql"), "bullet_ids": []}
        for event in req["transcript"]:
            if event.get("tool") == "final_answer":
                rec["bullet_ids"] = event["input"].get("bullet_ids") or []
        self.actor.refs[(t, k)] = {"val": .5}
        msgs = messages(req)
        if self.arm == "ace":
            result = self.actor.ace_update(t, k, rec, msgs, agent)
        elif self.arm == "awm":
            result = self.actor.awm_update(t, k, rec, msgs, agent)
        else:
            for event in req["transcript"]:
                if event.get("kind") != "tool":
                    continue
                self.gsend({"op": "step", "agent": agent,
                            "action": event["tool"] + ": " + json.dumps(event["input"], ensure_ascii=False),
                            "observation": event["output"][:h.GMEMORY_OBS_CHARS],
                            "reward": -1 if event.get("status") == "error" else 0})
            value = self.gsend({"op": "end", "label": bool(req["correct"]),
                               "feedback": "The final answer was correct." if req["correct"] else "The final answer was incorrect."})
            result = {**value, "input_tokens": value.get("prompt_tokens", 0),
                      "output_tokens": value.get("completion_tokens", 0)}
        self.active = None
        result["seconds"] = time.monotonic() - t0
        return result

    def checkpoint(self):
        if self.active is not None or self.snapshot is not None:
            raise ValueError("Invalid checkpoint boundary")
        self.snapshot = {"k": self.k, "state": {name: copy.deepcopy(getattr(self.actor, name)) for name in STATE_FIELDS}}
        if self.arm == "gmemory":
            self.close()
            shutil.copytree(self.branch / "gmemory", self.root / "post-heldout-gmemory")
        return {"ok": True, "k": self.k, "boundary": "post-heldout"}

    def restore(self):
        if self.active is not None or self.snapshot is None:
            raise ValueError("No checkpoint available")
        self.close()
        self.k = self.snapshot["k"]
        for name, value in self.snapshot["state"].items():
            setattr(self.actor, name, copy.deepcopy(value))
        self.branch_index += 1
        self.branch = self.root / f"branch-{self.branch_index:03}"
        self.branch.mkdir()
        self.actor.a.out = str(self.branch)
        if self.arm == "gmemory":
            shutil.copytree(self.root / "post-heldout-gmemory", self.branch / "gmemory")
        return {"ok": True, "k": self.k, "branch": self.branch_index}

    def dispatch(self, req):
        with self.lock:
            self.index += 1
            started = datetime.now(timezone.utc).isoformat()
            # Archive before execution, so partial updates cannot disappear.
            with self.journal.open("a") as f:
                f.write(json.dumps({"event": "request", "index": self.index, "utc": started, "request": req}, ensure_ascii=False) + "\n")
            try:
                op = req["op"]
                if op == "begin":
                    result = self.begin(req)
                elif op == "end":
                    result = self.end(req)
                elif op == "checkpoint":
                    result = self.checkpoint()
                elif op == "restore":
                    result = self.restore()
                elif op == "close":
                    self.close()
                    result = {"ok": True}
                else:
                    raise ValueError("Unknown operation")
            except Exception as e:
                traceback.print_exc()
                result = {"error": f"{type(e).__name__}: {e}"}
            with self.journal.open("a") as f:
                f.write(json.dumps({"event": "response", "index": self.index, "utc": datetime.now(timezone.utc).isoformat(),
                                    "response": result}, ensure_ascii=False) + "\n")
            return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, value):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.reply(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= 8_000_000:
                raise ValueError("Request size outside limit")
            req = json.loads(self.rfile.read(n))
            key, arm = req["key"], req["arm"]
            if not key.replace("-", "").isalnum() or arm not in ("ace", "awm", "gmemory"):
                raise ValueError("Invalid actor")
            with self.server.registry_lock:
                if key not in self.server.actors:
                    if req["op"] != "begin":
                        raise ValueError("First operation must be begin")
                    self.server.actors[key] = Actor(key, arm, self.server.args.out, self.server.args.proxy, self.server.args.model)
                actor = self.server.actors[key]
            if actor.arm != arm:
                raise ValueError("Actor arm mismatch")
            result = actor.dispatch(req)
            self.reply(500 if result.get("error") else 200, result)
        except Exception as e:
            traceback.print_exc()
            self.reply(500, {"error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=19331)
    p.add_argument("--proxy", default="http://127.0.0.1:19330")
    p.add_argument("--model", default="deepseek-flash")
    p.add_argument("--out", default="results/published-scenarios-20261030/memory")
    a = p.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    server.actors, server.registry_lock, server.args = {}, threading.Lock(), a
    server.serve_forever()
