#!/usr/bin/env python3
"""Collect all three preregistered timing repetitions; retain negative decisions."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--binary", default="results/shared-memory-main/inputs/agentdb-mid")
    p.add_argument("--out", default="results/strategy-main")
    args = p.parse_args()
    binary, out = Path(args.binary).resolve(), Path(args.out).resolve()
    if (out / "launcher.json").exists():
        raise SystemExit("Output already has a manifest. Preserve previous attempts.")
    out.mkdir(parents=True, exist_ok=True)
    inputs = out / "inputs"
    inputs.mkdir()
    pinned = inputs / "agentdb-mid"
    shutil.copy2(binary, pinned)
    source_files = [Path("Cargo.toml"), Path("Cargo.lock"), *sorted(Path("src").rglob("*.rs")),
                    Path("docs/shared-memory-study.md"), Path(__file__).resolve().relative_to(Path.cwd())]
    hashes = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files}
    (inputs / "source-sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    archive_path = inputs / "strategy-source.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for f in source_files:
            archive.add(f, arcname=f.as_posix(), recursive=False)
    commands = [[str(pinned), "--out", str(out / f"capture-{i}"), "strategy-bench",
                 "--rows", "100000", "--groups", "64", "--measurements", "3"] for i in [1, 2, 3]]
    manifest = {"started_utc": now(), "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "sources": hashes, "source_archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "commands": commands, "options": vars(args),
                "protocol": "Three sequential timing captures of one fixed workload, no outcome-based reruns. Each capture has disjoint 24/16/24 train/validation/test groups."}
    (out / "launcher.json").write_text(json.dumps(manifest, indent=2) + "\n")
    results = []
    for i, command in enumerate(commands, 1):
        start = now()
        with (out / f"capture-{i}.log").open("w") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        results.append({"capture": i, "started_utc": start, "finished_utc": now(), "exit_code": result.returncode})
        (out / "launcher-results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(f"Capture {i} finished, exit {result.returncode}", flush=True)
    if any(r["exit_code"] for r in results):
        raise SystemExit("At least one capture failed; all partial records retained.")


if __name__ == "__main__":
    main()
