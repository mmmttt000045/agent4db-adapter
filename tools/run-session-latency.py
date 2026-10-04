#!/usr/bin/env python3
"""Run the preregistered fixed-library matrix on the experiment host."""

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCES = ["dsv41flash-r1-b", "dsv41flash-r2-b-rerun", "dsv41flash-r3-a"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default="target/release/agentdb-mid")
    parser.add_argument("--sources-root", default="/root/agentdb-mid/results/scen-20261002")
    parser.add_argument("--out", default="results/session-latency-20261003")
    parser.add_argument("--jobs", type=int, choices=[1, 2], default=2)
    parser.add_argument("--rows", type=int, default=1_000_000)
    args = parser.parse_args()
    binary, root, out = Path(args.binary).resolve(), Path(args.sources_root).resolve(), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out / "launcher.json").exists():
        raise SystemExit("Output already contains a run manifest; choose a new directory to preserve earlier runs.")
    jobs = []
    for idx, source in enumerate(SOURCES):
        found = sorted((root / source).rglob("cell-*-metric-global-named.json"))
        if len(found) != 1:
            raise SystemExit(f"Expected one completed source cell for {source}; found {len(found)}")
        original = found[0]
        snapshot = out / "inputs" / original.relative_to(root)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, snapshot)
        command = [str(binary), "--pool", "16", "--out", str(out / source), "session-bench",
                   "--libs", str(snapshot), "--rows", str(args.rows), "--agent", "cline", "--order-offset", str(idx)]
        jobs.append({"library": source, "source": str(original), "snapshot": str(snapshot),
                     "sha256": sha256(original), "command": command, "log": str(out / f"{source}.log")})
    manifest = {"started_utc": datetime.now(timezone.utc).isoformat(), "binary": str(binary),
                "binary_sha256": sha256(binary), "options": vars(args), "jobs": jobs}
    (out / "launcher.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    def run(job):
        start = datetime.now(timezone.utc).isoformat()
        with open(job["log"], "w") as log:
            result = subprocess.run(job["command"], stdout=log, stderr=subprocess.STDOUT, check=False)
        return {"library": job["library"], "started_utc": start,
                "finished_utc": datetime.now(timezone.utc).isoformat(), "exit_code": result.returncode}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(run, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            (out / "launcher-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
            print(f"{result['library']} exited {result['exit_code']}", flush=True)
    if any(result["exit_code"] for result in results):
        raise SystemExit("At least one library run failed; preserve partial outputs and inspect logs.")
    print(f"Completed all three libraries: {out}", flush=True)


if __name__ == "__main__":
    main()
