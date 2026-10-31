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
    memory_inputs = []
    missing_reasoning_echo = 0

    def log_message(self, *_):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.calls += 1
        if req.get("tools"):
            Fake.missing_reasoning_echo += sum(m.get('role')=='assistant' and bool(m.get('tool_calls')) and 'reasoning_content' not in m for m in req.get('messages',[]))
            executed = any(m.get('role')=='tool' for m in req.get('messages',[]))
            msg = {"role": "assistant", "content": None, "reasoning_content": "offline test",
                   "tool_calls": [{"id": f"fake-{Fake.calls}", "type": "function",
                                   "function": {"name": "final_answer" if executed else "run_sql", "arguments": '{"answer":"0","sql":"SELECT 0","bullet_ids":[]}' if executed else '{"sql":"SELECT 0"}'}}]}
        else:
            Fake.memory_inputs.append(json.dumps(req,ensure_ascii=False))
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
    with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:19441/memory", data=data,
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
    fake = ThreadingHTTPServer(("127.0.0.1", 19440), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    with (out / "memory-service.log").open("x") as log:
        service = subprocess.Popen(["python3", "-u", str(HERE / "memory-service.py"), "--port", "19441", "--proxy", "http://127.0.0.1:19440",
                                    "--out", str(out / "memory")], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            for _ in range(60):
                if service.poll() is not None:
                    raise RuntimeError("Memory service exited")
                try:
                    urllib.request.urlopen("http://127.0.0.1:19441/health", timeout=1).read()
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
                transcript.insert(1,{"kind":"tool","tool":"run_metric" if arm=="mavra" else "run_sql",
                    "call_id":"smoke-execution","status":"ok","input":{"sql":"SELECT 0"},
                    "output":json.dumps({"ref":"r1","result":{"columns":["v"],"rows":[["0"]]},"sql":"SELECT 0","source":"snapshot"})})
                transcript=[{k:e[k] for k in ('tool','input','output')} for e in transcript if e.get('tool')]
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
                assert warm["common_feedback"][0]["own_sql"]=="SELECT 0"
                assert warm["common_feedback"][0]["own_observations"][0]["tool"]==("run_metric" if arm=="mavra" else "run_sql")
                if arm == "awm":
                    assert warm["workflow_chars"] > 0
                if arm == "gmemory":
                    assert end["memory_size"] == 1 and warm["n_success"] == 1
                post({**base, "op": "end", "correct": True, "answer": "0", "sql": "SELECT 0", "transcript": transcript})
                # All five forms must reach every published update algorithm.
                forms=[base['ask'],{'kind':'diff','a':{'year':2002,'m1':9,'m2':9},'b':{'year':2001,'m1':6,'m2':6}},
                       *[{'kind':kind,'year':2002} for kind in ('rank_month','peak_rise','above_mean')]]
                for number,ask in enumerate(forms):
                    question={**base,'ask':ask,'task':f'M1-S{number}','question':f'Offline analytical form {ask["kind"]}.'}
                    post({**base,'op':'restore'})
                    post({**question,'op':'begin'})
                    post({**question,'op':'end','correct':True,'answer':'0','sql':'SELECT 0','transcript':transcript})
                post({**base, "op": "close"})
                results[arm] = {"initial": begin, "first_update": end, "restored": restored, "warm": warm,'update_forms':[x['kind'] for x in forms]}
            # One tiny native run checks Rust question/trace/checkpoint boundaries.
            key = "synthetic-r98-mavra"
            native_env = {**env, "OPENAI_API_KEY": "offline-only", "OPENAI_MODEL": "deepseek-flash", "OPENAI_REQUIRE_MODEL": "deepseek-flash",
                          "OPENAI_BASE_URL": "http://127.0.0.1:19440", "OPENAI_THINKING": "enabled", "OPENAI_REASONING_EFFORT": "low",
                          "OPENAI_HEDGE": "1", "FIG6_PRESERVE_REASONING": "1", "FIG6_CELL_KEY": key,
                          "FIG6_MEMORY_URL": "http://127.0.0.1:19441/memory"}
            c = [str(ROOT / "target/release/agentdb-mid"), "--pool", "4", "--out", str(out / "native"), "metric-bench",
                 "--agent", "openai", "--extractor", "openai", "--modes", "metric-global-full", "--metrics", "M1,M3,M5", "--phrasings", "named",
                 "--holdout-agents", "A", "--question-set", "v2", "--scenario-extra-count", "11", "--changes", "append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror", "--max-steps", "2", "--rows", "10000", "--concurrency", "1", "--trace", "--no-explain"]
            with (out / "native.log").open("x") as native_log:
                run = subprocess.run(c, cwd=ROOT, env=native_env, stdout=native_log, stderr=subprocess.STDOUT, timeout=180)
            assert run.returncode == 0, "Native bridge smoke failed"
            reports = list((out / "native").glob("metric-*/report.json"))
            report = json.loads(reports[0].read_text())
            assert len(report["cells"][0]["records"]) == 34
            assert report["database_cleaned_up"] is True
            assert all(r["published_memory"]["common_feedback_recorded"] for r in report["cells"][0]["records"])
            assert report["cells"][0]["records"][0]["memory_lookup"]["common_feedback"] == []
            assert len(report["cells"][0]["records"][1]["memory_lookup"]["common_feedback"]) == 1
            native_feedback=report["cells"][0]["records"][1]["memory_lookup"]["common_feedback"][0]
            assert native_feedback['own_sql']=='SELECT 0' and native_feedback['own_observations']
            assert native_feedback['own_observations'][0]['tool']=='run_sql'
            journal=out/'memory'/key/'memory-events.jsonl'
            ends=[json.loads(line)['request'] for line in journal.read_text().splitlines() if json.loads(line).get('event')=='request' and json.loads(line)['request']['op']=='end']
            assert any(e.get('kind')=='assistant' and e['message'].get('tool_calls') for e in ends[0]['transcript'])
            assert any(e.get('kind')=='tool' and e.get('tool')=='final_answer' for e in ends[0]['transcript'])
            assert Fake.missing_reasoning_echo==0
            assert any('TOOL CALL run_sql' in request and 'TOOL OUTPUT' in request for request in Fake.memory_inputs)
            assert any('run_sql(' in request and '<action>' in request for request in Fake.memory_inputs)
            assert any('run_sql:' in request for request in Fake.memory_inputs)
            results['full_trace_contract']={'assistant_and_final_events':True,'reasoning_echo':True,'ace_actions':True,'awm_actions':True,'gmemory_actions':True}
            results["native"] = {"tasks": 34, "database_cleaned_up": True}
            results["fake_model_calls"] = Fake.calls
            results["scientific_evidence"] = False
            results["paid_model_calls"] = 0
            (out / "smoke-result.json").write_text(json.dumps(results, indent=2) + "\n")
            print(json.dumps({"ok": True, "arms": ["ace", "awm", "gmemory", "mavra"], "native_tasks": 34, "paid_model_calls": 0}), flush=True)
        finally:
            import signal
            os.killpg(service.pid, signal.SIGTERM)
            service.wait(30)
            fake.shutdown()


if __name__ == "__main__":
    main()
