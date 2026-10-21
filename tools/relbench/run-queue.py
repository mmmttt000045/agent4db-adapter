#!/usr/bin/env python3
"""Run harness cells in parallel on noctis (exp/2026-10-20-relbench): at most --parallel at a time, a new cell only when
the disk has --min-free-gb free (each cell copies its template database), every cell inside a memory-capped scope, cells
that already finished skipped (so the queue can be restarted). Cells are lines of a plain file:

    <arm> <dataset> <run> [extra harness arguments...]

e.g. `mavra rel-stack 2` or `agentsm rel-trial 1 --agentsm-memory results/relbench-agentsm/rel-trial/memory.json`.
The dataset name maps to results/relbench-data/<dataset>, <dataset>-prep and the template relbench_<short>_t1.

  python3 tools/relbench/run-queue.py cells.txt --out results/relbench-main --parallel 8
"""
import argparse
import json
import os
import shutil
import subprocess
import time

ENV_DROP = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy")


def log(msg, fh):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    fh.write(line + "\n")
    fh.flush()


def done(out):
    """A cell is done when its harness exited normally (the queue then writes .done) and run.json has no error."""
    try:
        r = json.load(open(os.path.join(out, "run.json")))
    except (OSError, ValueError):
        return False
    return os.path.exists(os.path.join(out, ".done")) and bool(r.get("cutoffs")) and not r.get("error")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cells")
    ap.add_argument("--out", required=True)
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--min-free-gb", type=float, default=8)
    ap.add_argument("--memory-max", default="24G")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    fh = open(os.path.join(a.out, "queue.log"), "a")
    cells = [line.split() for line in open(a.cells) if line.strip() and not line.startswith("#")]
    pending = []
    for c in cells:
        arm, ds, run, extra = c[0], c[1], c[2], c[3:]
        name = f"{arm}-{ds}-r{run}"
        out = os.path.join(a.out, name)
        if done(out):
            log(f"skip {name} (done)", fh)
            continue
        short = ds.replace("rel-", "")
        cmd = ["systemd-run", "--scope", "--quiet", "-p", f"MemoryMax={a.memory_max}", "-p", "MemorySwapMax=0",
               "env", *[f"-u{v}" for v in ENV_DROP], "PYTHONPATH=.pydeps-relbench", "HF_HUB_OFFLINE=1",
               "python3", "tools/relbench/harness.py", "--arm", arm, "--run", run,
               "--data", f"results/relbench-data/{ds}", "--prep", f"results/relbench-data/{ds}-prep",
               "--template", f"relbench_{short}_t1", "--out", out, *extra]
        pending.append((name, out, cmd))
    running = {}
    while pending or running:
        for name, (proc, out) in list(running.items()):
            if proc.poll() is not None:
                ok = proc.returncode == 0
                if ok:
                    open(os.path.join(out, ".done"), "w").write(time.strftime("%Y-%m-%d %H:%M:%S\n"))
                log(f"{'done' if ok else 'FAILED'} {name} (exit {proc.returncode})", fh)
                del running[name]
        free = shutil.disk_usage("/").free / 2 ** 30
        while pending and len(running) < a.parallel and free >= a.min_free_gb:
            name, out, cmd = pending.pop(0)
            if os.path.exists(out):  # an unfinished earlier attempt: kept aside, the cell starts from its first cutoff
                stamp = time.strftime("%m%d-%H%M")
                os.rename(out, f"{out}.aborted-{stamp}")
                if os.path.exists(f"{out}.log"):
                    os.rename(f"{out}.log", f"{out}.aborted-{stamp}.log")
                log(f"moved unfinished {name} to {name}.aborted-{stamp}", fh)
            os.makedirs(out, exist_ok=True)
            proc = subprocess.Popen(cmd, stdout=open(f"{out}.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            running[name] = (proc, out)
            log(f"start {name} (running {len(running)}, free {free:.0f} GB)", fh)
            time.sleep(30)  # let the database copy finish before the next disk check
            free = shutil.disk_usage("/").free / 2 ** 30
        time.sleep(60)
    log("queue finished", fh)


if __name__ == "__main__":
    main()
