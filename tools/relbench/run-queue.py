#!/usr/bin/env python3
"""Run harness cells in parallel on noctis (exp/2026-10-20-relbench): at most --parallel at a time, a new cell only when
the disk has --min-free-gb free (each cell copies its template database), every cell inside a memory-capped scope.
A cell counts as finished when its run.json says so (the harness writes "finished" after the last test score), so a
restarted queue skips it even if the queue that started it died; a cell whose harness is still running (harness.pid)
is left alone; any other earlier attempt is moved aside and the cell starts from its first cutoff. After a failed cell
the queue drops its database and stops its middle layer. Cells are lines of a plain file:

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
    """The harness finished every cutoff and every test score without an error."""
    try:
        r = json.load(open(os.path.join(out, "run.json")))
    except (OSError, ValueError):
        return False
    return bool(r.get("finished")) and not r.get("error")


def harness_pid(out):
    try:
        return int(open(os.path.join(out, "harness.pid")).read().strip())
    except (OSError, ValueError):
        return None


def running(out):
    """The cell's harness process is alive (its command line names this cell's folder)."""
    pid = harness_pid(out)
    if not pid:
        return False
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return False
    return "harness.py" in cmd and f"--out {out}" in cmd


def admin_url():
    for line in open(".env", encoding="utf-8"):
        if line.startswith("AGENTDB_URL="):
            return line.split("=", 1)[1].strip().rsplit("/", 1)[0] + "/postgres"
    return None


def clean_up(out, fh):
    """A failed or killed cell can leave its database (a full template copy) and its middle layer behind."""
    pid = harness_pid(out)
    if not pid:
        return
    url = admin_url()
    if url:
        q = f"select datname from pg_database where datname like 'relbench\\_%\\_{pid}'"
        names = subprocess.run(["psql", url, "-Atc", q], capture_output=True, text=True).stdout.split()
        for name in names:
            subprocess.run(["psql", url, "-qc", f"drop database if exists {name} with (force)"], capture_output=True)
            log(f"dropped leftover database {name}", fh)
    left = subprocess.run(["pgrep", "-f", f"agentdb-mid --db .*_{pid} "], capture_output=True, text=True).stdout.split()
    for p in left:
        subprocess.run(["kill", p])
        log(f"stopped leftover middle layer {p}", fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cells")
    ap.add_argument("--out", required=True)
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--min-free-gb", type=float, default=15, help="headroom for running cells' growth (appends, seed tables, temp files)")
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
        short = ds.replace("rel-", "")
        cmd = ["systemd-run", "--scope", "--quiet", "-p", f"MemoryMax={a.memory_max}", "-p", "MemorySwapMax=0",
               "env", *[f"-u{v}" for v in ENV_DROP], "PYTHONPATH=.pydeps-relbench", "HF_HUB_OFFLINE=1",
               "python3", "tools/relbench/harness.py", "--arm", arm, "--run", run,
               "--data", f"results/relbench-data/{ds}", "--prep", f"results/relbench-data/{ds}-prep",
               "--template", f"relbench_{short}_t1", "--out", out, *extra]
        pending.append((name, out, cmd))
    running_cells = {}
    waiting_disk = False
    while pending or running_cells:
        for name, (proc, out) in list(running_cells.items()):
            if proc.poll() is not None:
                ok = proc.returncode == 0 and done(out)
                log(f"{'done' if ok else 'FAILED'} {name} (exit {proc.returncode})", fh)
                if not ok:
                    clean_up(out, fh)
                del running_cells[name]
        free = shutil.disk_usage("/").free / 2 ** 30
        while pending and len(running_cells) < a.parallel:
            if free < a.min_free_gb:
                if not waiting_disk:
                    log(f"waiting for disk: {free:.0f} GB free, {a.min_free_gb:.0f} GB needed ({len(pending)} cells pending)", fh)
                waiting_disk = True
                break
            waiting_disk = False
            name, out, cmd = pending.pop(0)
            if done(out):
                log(f"skip {name} (finished)", fh)
                continue
            if running(out):
                log(f"skip {name} (its harness is still running; not touched)", fh)
                continue
            if os.path.exists(out):  # an unfinished earlier attempt: kept aside, the cell starts from its first cutoff
                stamp = time.strftime("%m%d-%H%M")
                clean_up(out, fh)
                os.rename(out, f"{out}.aborted-{stamp}")
                if os.path.exists(f"{out}.log"):
                    os.rename(f"{out}.log", f"{out}.aborted-{stamp}.log")
                log(f"moved unfinished {name} to {name}.aborted-{stamp}", fh)
            os.makedirs(out, exist_ok=True)
            proc = subprocess.Popen(cmd, stdout=open(f"{out}.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            running_cells[name] = (proc, out)
            log(f"start {name} (running {len(running_cells)}, free {free:.0f} GB)", fh)
            time.sleep(30)  # let the database copy finish before the next disk check
            free = shutil.disk_usage("/").free / 2 ** 30
        time.sleep(60)
    log("queue finished", fh)


if __name__ == "__main__":
    main()
