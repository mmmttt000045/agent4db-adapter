#!/usr/bin/env python3
"""Run the predeclared matched study; all paid traffic uses one capped relay."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOKEN = "corrected-scenarios-20261031-local"


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def command(key, dataset, arm, repeat, out):
    modes = {"ace": "paper-ace", "awm": "paper-awm", "gmemory": "paper-gmemory", "mavra": "metric-global-full"}
    c = [str(ROOT / "target/release/agentdb-mid"), "--pool", "8", "--out", str(out), "metric-bench",
         "--agent", "openai", "--extractor", "openai", "--modes", modes[arm], "--metrics", "M1,M3,M5",
         "--phrasings", "named", "--question-set", "v1", "--holdout-agents", "A", "--changes",
         "append,backfill,correct,addcol,status,revision,dupload,dimhist,latekey,unit,mirror",
         "--repeats", "1", "--first-repeat", str(repeat), "--max-steps", "20", "--sql-timeout-secs", "120",
         "--concurrency", "1", "--trace", "--no-explain", "--rows", "1000000"]
    if dataset == "tpch":
        c += ["--spec", "exp/2026-10-11-generality/schemas/tpch.json", "--defs", "exp/2026-10-11-generality/e2e/tpch-defs.json"]
    return c


def wait_health(port, proc):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Study service on {port} exited")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(.5)
    raise RuntimeError("Study service did not become ready")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--key-file", required=True)
    p.add_argument("--database-env", required=True)
    a = p.parse_args()
    if ROOT.name != "agentdb-corrected-scenarios-20261031":
        raise SystemExit("Run in the isolated study checkout")
    out = ROOT / "results/corrected-scenarios-20261031"
    out.mkdir(parents=True, exist_ok=False)
    cfg = json.loads((HERE / "protocol.json").read_text())
    assert cfg["budget_cny"] == 20 and cfg["max_repeats"] <= 2
    deadline = datetime.fromisoformat(cfg["deadline_utc"])
    state = {"started_utc": utc(), "status": "starting", "cells": [], "complete_repeats": []}
    save(out / "execution-state.json", state)
    files = list(HERE.glob("*.py")) + [HERE / "protocol.json", ROOT / "Cargo.toml", ROOT / "Cargo.lock"]
    files += list((ROOT / "src").rglob("*.rs")) + list((ROOT / "third_party/ace").glob("*")) + list((ROOT / "third_party/awm").glob("*"))
    files += [ROOT / "tools/relbench/harness.py", ROOT / "tools/relbench/gmemory_service.py", ROOT / "target/release/agentdb-mid"]
    manifest = {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()}
    gcore = ROOT / "results/ext/GMemory"
    manifest.update({"gmemory-core/" + str(f.relative_to(gcore)): hashlib.sha256(f.read_bytes()).hexdigest()
                     for f in gcore.rglob("*.py") if ".git" not in f.parts})
    save(out / "frozen-source-manifest.json", manifest)
    db = {}
    for line in Path(a.database_env).read_text().splitlines():
        if line.strip().startswith("AGENTDB_URL="):
            db["AGENTDB_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not db:
        raise RuntimeError("Database connection was not configured")
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower() and not k.startswith(("OPENAI_", "DEEPSEEK_"))}
    env.update(db)
    env.update(PYTHONPATH=str(ROOT / ".pydeps-relbench"), NO_PROXY="127.0.0.1,localhost",
               FIG6_PRESERVE_REASONING="1", FIG6_MEMORY_URL="http://127.0.0.1:19331/memory",
               OPENAI_API_KEY=TOKEN, OPENAI_MODEL=cfg["model"], OPENAI_REQUIRE_MODEL=cfg["model"], OPENAI_HEDGE="1",
               OPENAI_REASONING_EFFORT="low", OPENAI_THINKING="enabled", OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4",
               MKL_NUM_THREADS="4", MALLOC_ARENA_MAX="2")
    services = []
    handles = []
    try:
        for name, port, args in [
            ("budget-proxy", 19330, ["--key-file", a.key_file, "--out", str(out / "budget")]),
            ("memory-service", 19331, ["--out", str(out / "memory")]),
        ]:
            log = (out / f"{name}.log").open("x")
            handles.append(log)
            proc = subprocess.Popen(["python3", "-u", str(HERE / f"{name}.py"), *args], cwd=ROOT, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            services.append(proc)
            (out / f"{name}.pid").write_text(str(proc.pid))
            wait_health(port, proc)
        state["status"] = "running"
        save(out / "execution-state.json", state)

        def run_cell(dataset, arm, repeat):
            key = f"{dataset}-r{repeat}-{arm}"
            cell_out = out / "cells" / key
            cell_out.mkdir(parents=True, exist_ok=False)
            c = command(key, dataset, arm, repeat, cell_out)
            cell_env = {**env, "FIG6_CELL_KEY": key, "OPENAI_BASE_URL": f"http://127.0.0.1:19330/arm/{key}"}
            record = {"key": key, "dataset": dataset, "arm": arm, "repeat": repeat, "started_utc": utc(), "command": c}
            save(cell_out / "launch.json", record)
            with (cell_out / "console.log").open("x") as log:
                proc = subprocess.Popen(c, cwd=ROOT, env=cell_env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                (cell_out / "process.pid").write_text(str(proc.pid))
                while proc.poll() is None:
                    if datetime.now(timezone.utc) >= deadline or (out / "budget/STOP").exists():
                        (out / "budget/STOP").touch(exist_ok=True)
                        # Native cleanup needs an opportunity to finish after denied calls.
                    time.sleep(2)
                record["returncode"] = proc.returncode
            reports = list(cell_out.glob("metric-*/report.json"))
            record["report"] = str(reports[0].relative_to(ROOT)) if len(reports) == 1 else None
            record["completed"] = proc.returncode == 0 and len(reports) == 1
            record["finished_utc"] = utc()
            if record["completed"]:
                report = json.loads(reports[0].read_text())
                rows = report["cells"][0]["records"]
                phases = set(row["phase"] for row in rows)
                record["task_counts"] = {p: sum(r["phase"] == p for r in rows) for p in sorted(phases)}
                record["completed"] = (len(report["cells"]) == 1 and set(cfg["changes"] + ["learn", "holdout"]) == phases
                                       and len(rows) == (32 if dataset == "synthetic" else 26)
                                       and report.get("database_cleaned_up") is True)
                infrastructure_errors = [r["error"] for r in rows if r.get("error") and
                                         any(s in r["error"].lower() for s in ("http 402", "http 5", "error sending request", "connection", "timed out"))]
                if infrastructure_errors:
                    record["completed"] = False
                    record["infrastructure_errors"] = infrastructure_errors
                record["report_sha256"] = hashlib.sha256(reports[0].read_bytes()).hexdigest()
            denials = out / "budget/denied-requests.jsonl"
            if denials.exists():
                denied = [json.loads(line) for line in denials.read_text().splitlines() if line]
                if any(r["arm"] == key for r in denied):
                    record["completed"] = False
                    record["budget_or_configuration_denial"] = True
            save(cell_out / "completion.json", record)
            if arm in cfg["arms"]:
                try:
                    data = json.dumps({"op": "close", "key": key, "arm": arm}).encode()
                    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:19331/memory", data=data,
                                             headers={"Content-Type": "application/json"}), timeout=45).read()
                except Exception as e:
                    record["memory_close_error"] = type(e).__name__
            print(json.dumps({k: v for k, v in record.items() if k != "command"}), flush=True)
            return record

        block_start = time.monotonic()
        for repeat in range(1, cfg["max_repeats"] + 1):
            arms = cfg["arms"][repeat - 1:] + cfg["arms"][:repeat - 1]
            block = []
            # Matched datasets run together for one arm; fixed arm order.
            with ThreadPoolExecutor(max_workers=2) as pool:
                for arm in arms:
                    if datetime.now(timezone.utc) >= deadline:
                        state["stop_reason"] = "deadline"
                        break
                    b = json.loads((out / "budget/budget-state.json").read_text())
                    if shutil.disk_usage(ROOT).free < 20 * 1024**3:
                        state["stop_reason"] = "disk_reserve"
                        break
                    if b["status"] == "budget_limit" or (out / "budget/STOP").exists():
                        state["stop_reason"] = "budget"
                        break
                    futures = [pool.submit(run_cell, ds, arm, repeat) for ds in cfg["datasets"]]
                    pair = [f.result() for f in futures]
                    block += pair
                    state["cells"] += pair
                    save(out / "execution-state.json", state)
                    if not all(c["completed"] for c in pair):
                        state["stop_reason"] = "incomplete_cell"
                        break
            if len(block) != 8 or not all(c["completed"] for c in block):
                break
            state["complete_repeats"].append(repeat)
            save(out / "execution-state.json", state)
            if repeat == 1:
                b = json.loads((out / "budget/budget-state.json").read_text())
                cumulative = max(b["ceiling_cny"], b.get("observed_account_decrease_cny", 0))
                cost = cumulative - b["prior_cost_cny"]
                remaining = cfg["budget_cny"] - cumulative
                elapsed = time.monotonic() - block_start
                enough_time = (deadline - datetime.now(timezone.utc)).total_seconds() > elapsed * 1.2
                decision = {"utc": utc(), "first_block_upper_cny": cost, "remaining_cny": remaining,
                            "required_cny": 1.2 * cost + .4, "elapsed_seconds": elapsed,
                            "enough_time": enough_time, "start_second_repeat": remaining > 1.2 * cost + .4 and enough_time}
                save(out / "repeat-decision.json", decision)
                if not decision["start_second_repeat"]:
                    state["stop_reason"] = "predeclared_repeat_gate"
                    break
        state["status"] = "complete" if state["complete_repeats"] else "incomplete"
        state["finished_utc"] = utc()
        save(out / "execution-state.json", state)
    except Exception as e:
        state.update(status="failed", error=f"{type(e).__name__}: {e}", finished_utc=utc())
        save(out / "execution-state.json", state)
        raise
    finally:
        # Only processes launched by this study are signalled.
        for proc in reversed(services):
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(35)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
        for log in handles:
            log.close()


if __name__ == "__main__":
    main()
