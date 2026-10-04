#!/usr/bin/env python3
"""Run three independent producer streams with immutable binary and source hashes."""

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default="target/release/agentdb-mid")
    parser.add_argument("--out", default="results/shared-memory-main")
    parser.add_argument("--jobs", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--rows", type=int, default=100_000)
    args = parser.parse_args()
    binary, out = Path(args.binary).resolve(), Path(args.out).resolve()
    if (out / "launcher.json").exists():
        raise SystemExit("Choose a new output directory; completed and partial attempts must be preserved.")
    out.mkdir(parents=True, exist_ok=True)
    inputs = out / "inputs"
    inputs.mkdir()
    pinned = inputs / "agentdb-mid"
    shutil.copy2(binary, pinned)
    source_files = [Path("Cargo.toml"), Path("Cargo.lock"), *sorted(Path("src").rglob("*.rs")),
                    Path("docs/shared-memory-study.md"), Path(__file__).resolve().relative_to(Path.cwd())]
    hashes = {str(p): sha256(p) for p in source_files}
    (inputs / "source-sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    archive_path = inputs / "primary-source.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for p in source_files:
            archive.add(p, arcname=p.as_posix(), recursive=False)
    jobs = []
    for repeat in [1, 2, 3]:
        command = [str(pinned), "--pool", "16", "--out", str(out / f"stream-{repeat}"),
                   "memory-bench", "--rows", str(args.rows), "--metrics", "M1,M2,M3,M5",
                   "--repeat", str(repeat), "--agent", "cline", "--extractor", "cline",
                   "--max-steps", "20", "--extract-attempts", "2"]
        jobs.append({"repeat": repeat, "command": command, "log": str(out / f"stream-{repeat}.log")})
    env_keys = ["CLINE_MODEL", "CLINE_REQUIRE_MODEL", "CLINE_REASONING_EFFORT", "CLINE_HEDGE"]
    manifest = {"started_utc": now(), "options": vars(args), "binary_sha256": sha256(pinned),
                "sources": hashes, "model_overrides": {k: os.environ[k] for k in env_keys if k in os.environ},
                "source_archive_sha256": sha256(archive_path),
                "jobs": jobs,
                "protocol": "Same producer prefixes; fresh consumers; all defined attempts primary; named secondary. No reruns conditioned on accuracy."}
    (out / "launcher.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def run(job):
        started = now()
        with open(job["log"], "w") as log:
            result = subprocess.run(job["command"], stdout=log, stderr=subprocess.STDOUT, check=False)
        return {"repeat": job["repeat"], "started_utc": started, "finished_utc": now(), "exit_code": result.returncode}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(run, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            (out / "launcher-results.json").write_text(json.dumps(results, indent=2) + "\n")
            print(f"Stream {result['repeat']} finished, exit {result['exit_code']}", flush=True)
    if any(r["exit_code"] for r in results):
        raise SystemExit("A stream failed; retain all partial and error artifacts.")
    print(f"Completed all three streams: {out}", flush=True)


if __name__ == "__main__":
    main()
