#!/usr/bin/env python3
"""Archive finished evidence, keeping private account balances on the server."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    root = a.results.resolve()
    state = json.loads((root / "execution-state.json").read_text())
    assert state["status"] in ("complete", "incomplete", "failed"), "Wait for the coordinator to finish"
    budget = json.loads((root / "budget/budget-state.json").read_text())
    assert abs(budget["reserved_cny"]) < 1e-8, "Wait for in-flight calls to be accounted"
    if a.out.exists():
        raise SystemExit("Archive already exists; inspect it before replacing evidence")
    manifest = {"study": root.name, "files": {},
                "redactions": {"budget/budget-state.json": ["initial_balance_cny", "balance_cny"]},
                "private_original": "Original balance fields remain in the server's budget-state.json; spending and every request are retained."}
    with tarfile.open(a.out, "w:gz") as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            assert not path.is_symlink()
            rel = path.relative_to(root).as_posix()
            raw = path.read_bytes()
            if rel == "budget/budget-state.json":
                value = json.loads(raw)
                for name in ("initial_balance_cny", "balance_cny"):
                    value.pop(name, None)
                value["private_balance_fields_redacted"] = True
                raw = (json.dumps(value, indent=2) + "\n").encode()
            manifest["files"][rel] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            info = tarfile.TarInfo(root.name + "/" + rel)
            info.size = len(raw)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(raw))
        raw = (json.dumps(manifest, indent=2) + "\n").encode()
        info = tarfile.TarInfo(root.name + "/archive-manifest.json")
        info.size, info.mode = len(raw), 0o644
        archive.addfile(info, io.BytesIO(raw))
    print(json.dumps({"archive": a.out.name, "files": len(manifest["files"]), "bytes": a.out.stat().st_size,
                      "sha256": hashlib.sha256(a.out.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
