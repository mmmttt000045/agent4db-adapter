#!/usr/bin/env python3
"""Mirror the manuscript (overleaf/ of the main repo) into the paper repo icde-2027-paper.

overleaf/ is the single source. The paper repo receives exactly the files `overleaf/build.sh
pack` collects for compilation (both entries, their \\input and \\includegraphics closure,
references.bib, build.sh); every other tracked file there is deleted, except the paper repo's
own README.md, .gitignore and .gitattributes. Text files are written with LF.

The paper repo's origin/main must still be the commit recorded in
docs/development/paper-sync.json; otherwise someone (e.g. Overleaf) pushed edits that a sync
would overwrite: merge them into overleaf/ first, or pass --force.

    python3 tools/sync-paper-repo.py --repo <clone>                  # dry run
    python3 tools/sync-paper-repo.py --repo <clone> --apply          # write files
    python3 tools/sync-paper-repo.py --repo <clone> --apply --push   # + commit, push, record
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "overleaf"
PACK = SRC / "build" / "mavra-icde-bilingual.zip"
RECORD = ROOT / "docs" / "development" / "paper-sync.json"
KEEP = {"README.md", ".gitignore", ".gitattributes"}  # owned by the paper repo
BINARY = {".pdf", ".png", ".jpg", ".zip"}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def lf(rel: str, data: bytes) -> bytes:
    return data if Path(rel).suffix in BINARY else data.replace(b"\r\n", b"\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--force", action="store_true", help="sync although the paper repo moved")
    a = ap.parse_args()
    dst = a.repo.resolve()
    if not (dst / ".git").exists():
        sys.exit(f"{dst} is not a git checkout")
    if a.push and not a.apply:
        sys.exit("--push needs --apply")

    record = json.loads(RECORD.read_text())
    git(dst, "fetch", "-q", "origin")
    remote = git(dst, "rev-parse", "origin/main")
    if remote != record["remote_commit"] and not a.force:
        print(git(dst, "log", "--oneline", f"{record['remote_commit']}..origin/main"))
        sys.exit("paper repo has commits since the last sync (listed above): merge them into "
                 "overleaf/ first, or rerun with --force")

    subprocess.check_call(["bash", str(SRC / "build.sh"), "pack"], stdout=subprocess.DEVNULL)
    with ZipFile(PACK) as z:
        want = {n: lf(n, z.read(n)) for n in z.namelist() if n not in KEEP}

    have = set(git(dst, "ls-files").splitlines())
    changed = sorted(n for n in want if n in have and (dst / n).read_bytes() != want[n])
    added = sorted(n for n in want if n not in have)
    removed = sorted(have - set(want) - KEEP)
    for title, names in (("changed", changed), ("added", added), ("removed", removed)):
        print(f"{title} ({len(names)}):", *names, sep="\n  ")

    if not a.apply:
        return 0
    for n in changed + added:
        (dst / n).parent.mkdir(parents=True, exist_ok=True)
        (dst / n).write_bytes(want[n])
    for n in removed:
        subprocess.check_call(["git", "-C", str(dst), "rm", "-q", "--", n])

    if a.push:
        git(dst, "add", "-A")
        if subprocess.call(["git", "-C", str(dst), "diff", "--cached", "--quiet"]) == 0:
            print("paper repo already up to date")
            return 0
        head = git(ROOT, "rev-parse", "--short", "HEAD")
        git(dst, "commit", "-q", "-m", f"Sync manuscript from agent4db-adapter {head}")
        git(dst, "push", "-q", "origin", "HEAD:main")
        commit = git(dst, "rev-parse", "HEAD")
        record.update(
            date=datetime.date.today().isoformat(), status="pushed", previous_head=remote,
            remote_commit=commit, source_commit=git(ROOT, "rev-parse", "HEAD"),
            changed_paths=changed + added, deletions=removed,
            commit_url=f"{record['repository_url']}/commit/{commit}",
        )
        RECORD.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        print(f"pushed {commit}; recorded in {RECORD.relative_to(ROOT)} (commit that file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
