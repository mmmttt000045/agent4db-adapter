#!/usr/bin/env python3
"""Check the actual G-Memory SDK request at a fake local API; no paid calls."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("study_memory", HERE / "memory-service.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Fake(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.requests.append(req)
        assert req["max_tokens"] == 512
        assert req["thinking"] == {"type": "disabled"}, req.get("thinking")
        raw = json.dumps({"id": "offline-provider-check", "model": "deepseek-flash",
                          "choices": [{"index": 0, "message": {"role": "assistant", "content": "Use the required time filter and aggregate once per fact row."}, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    out = ROOT / "results/offline-provider-repair"
    out.mkdir(exist_ok=False)
    fake = ThreadingHTTPServer(("127.0.0.1", 19340), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    actor = mod.Actor("synthetic-r97-gmemory", "gmemory", out, "http://127.0.0.1:19340", "deepseek-flash")
    req = {"question": "Compute monthly revenue.", "task": "M1-L0", "metric": "M1", "agent": "A", "phase": "learn",
           "ask": {"kind": "single", "period": {"year": 2001, "m1": 3, "m2": 3}}}
    try:
        actor.begin(req)
        end = actor.end({**req, "correct": True, "sql": "SELECT 0", "answer": "0", "transcript": [
            {"kind": "assistant", "message": {"role": "assistant", "content": "The total is zero."}},
            {"kind": "tool", "tool": "final_answer", "call_id": "offline-final", "status": "final", "input": {"answer": "0"}, "output": "recorded"}]})
        assert end["memory_size"] == 1
        assert Fake.requests and all(r["thinking"] == {"type": "disabled"} and r["max_tokens"] == 512 for r in Fake.requests)
        result = {"passed": True, "fake_requests": len(Fake.requests), "paid_calls": 0, "thinking": "disabled", "max_tokens": 512,
                  "memory_size": end["memory_size"]}
        (out / "profile-check.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    finally:
        actor.close()
        fake.shutdown()
