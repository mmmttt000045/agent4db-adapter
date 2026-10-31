#!/usr/bin/env python3
"""Engineering smoke only: local fake model, no network model or scientific scores."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class Fake(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *_):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.calls += 1
        if req.get("tools"):
            msg = {"role": "assistant", "content": None, "reasoning_content": "offline test",
                   "tool_calls": [{"id": f"fake-{Fake.calls}", "type": "function",
                                   "function": {"name": "final_answer", "arguments": '{"answer":"0","bullet_ids":[]}'}}]}
        else:
            msg = {"role": "assistant", "content": '{"operations":[],"bullet_tags":[]}', "reasoning_content": "offline test"}
        raw = json.dumps({"id": f"offline-{Fake.calls}", "model": "deepseek-flash",
                          "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def post(body):
    data = json.dumps(body).encode()
    with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:19341/memory", data=data,
                                     headers={"Content-Type": "application/json"}), timeout=240) as response:
        value = json.load(response)
    assert not value.get("error"), value
    return value


def main():
    out = ROOT / "results/offline-smoke"
    out.mkdir(exist_ok=False)
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower() and not k.startswith(("OPENAI_", "DEEPSEEK_"))}
    env["PYTHONPATH"] = str(ROOT / ".pydeps-relbench")
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["OMP_NUM_THREADS"] = "2"
    env["OPENBLAS_NUM_THREADS"] = "2"
    for line in Path("/root/agentdb-mid/.env").read_text().splitlines():
        if line.startswith("AGENTDB_URL="):
            env["AGENTDB_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    fake = ThreadingHTTPServer(("127.0.0.1", 19340), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    with (out / "memory-service.log").open("x") as log:
        service = subprocess.Popen(["python3", "-u", str(HERE / "memory-service.py"), "--port", "19341", "--proxy", "http://127.0.0.1:19340",
                                    "--out", str(out / "memory")], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            for _ in range(60):
                if service.poll() is not None:
                    raise RuntimeError("Memory service exited")
                try:
                    urllib.request.urlopen("http://127.0.0.1:19341/health", timeout=1).read()
                    break
                except OSError:
                    time.sleep(.5)
            results = {}
            for arm in ("ace", "awm", "gmemory", "mavra"):
                base = {"key": f"synthetic-r99-{arm}", "arm": arm, "question": "Compute the monthly total.",
                        "task": "M1-L0", "metric": "M1", "agent": "A", "phase": "learn",
                        "ask": {"kind": "single", "period": {"year": 2001, "m1": 3, "m2": 3}}}
                transcript = [{"kind": "assistant", "message": {"role": "assistant", "content": "The total is zero."}},
                              {"kind": "tool", "tool": "final_answer", "call_id": "smoke-final", "status": "final",
                               "input": {"answer": "0"}, "output": "recorded"}]
                begin = post({**base, "op": "begin"})
                assert begin["common_feedback"] == []
                end = post({**base, "op": "end", "correct": True, "answer": "0", "sql": "SELECT 0", "transcript": transcript})
                cp = post({**base, "op": "checkpoint"})
                assert cp["k"] == 1
                post({**base, "op": "begin"})
                post({**base, "op": "end", "correct": True, "answer": "0", "sql": "SELECT 0", "transcript": transcript})
                restored = post({**base, "op": "restore"})
                assert restored["k"] == 1 and restored["branch"] == 1
                warm = post({**base, "op": "begin"})
                assert len(warm["common_feedback"]) == 1 and warm["common_feedback"][0]["correct"] is True
                assert all("phase" not in x and "gold" not in x for x in warm["common_feedback"])
                if arm == "awm":
                    assert warm["workflow_chars"] > 0
                if arm == "gmemory":
                    assert end["memory_size"] == 1 and warm["n_success"] == 1
                post({**base, "op": "close"})
                results[arm] = {"initial": begin, "first_update": end, "restored": restored, "warm": warm}
            # One tiny native run checks Rust question/trace/checkpoint boundaries.
            key = "synthetic-r98-mavra"
            native_env = {**env, "OPENAI_API_KEY": "offline-only", "OPENAI_MODEL": "deepseek-flash", "OPENAI_REQUIRE_MODEL": "deepseek-flash",
                          "OPENAI_BASE_URL": "http://127.0.0.1:19340", "OPENAI_THINKING": "enabled", "OPENAI_REASONING_EFFORT": "low",
                          "OPENAI_HEDGE": "1", "FIG6_PRESERVE_REASONING": "1", "FIG6_CELL_KEY": key,
                          "FIG6_MEMORY_URL": "http://127.0.0.1:19341/memory"}
            c = [str(ROOT / "target/release/agentdb-mid"), "--pool", "4", "--out", str(out / "native"), "metric-bench",
                 "--agent", "openai", "--extractor", "openai", "--modes", "metric-global-full", "--metrics", "M1", "--phrasings", "named",
                 "--holdout-agents", "A", "--changes", "append", "--max-steps", "2", "--rows", "10000", "--concurrency", "1", "--trace", "--no-explain"]
            with (out / "native.log").open("x") as native_log:
                run = subprocess.run(c, cwd=ROOT, env=native_env, stdout=native_log, stderr=subprocess.STDOUT, timeout=180)
            assert run.returncode == 0, "Native bridge smoke failed"
            reports = list((out / "native").glob("metric-*/report.json"))
            report = json.loads(reports[0].read_text())
            assert len(report["cells"][0]["records"]) == 4
            assert report["database_cleaned_up"] is True
            assert all(r["published_memory"]["common_feedback_recorded"] for r in report["cells"][0]["records"])
            assert report["cells"][0]["records"][0]["memory_lookup"]["common_feedback"] == []
            assert len(report["cells"][0]["records"][1]["memory_lookup"]["common_feedback"]) == 1
            results["native"] = {"tasks": 4, "database_cleaned_up": True}
            results["fake_model_calls"] = Fake.calls
            results["scientific_evidence"] = False
            results["paid_model_calls"] = 0
            (out / "smoke-result.json").write_text(json.dumps(results, indent=2) + "\n")
            print(json.dumps({"ok": True, "arms": ["ace", "awm", "gmemory", "mavra"], "native_tasks": 4, "paid_model_calls": 0}), flush=True)
        finally:
            import signal
            os.killpg(service.pid, signal.SIGTERM)
            service.wait(30)
            fake.shutdown()


if __name__ == "__main__":
    main()
