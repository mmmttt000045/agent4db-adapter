#!/usr/bin/env python3
"""Exercise the completed-run audit against an intact copy and two damaged copies."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
source = repo / 'results/sql-only-20261027'
temp_root = (repo / 'tmp').resolve()
if not source.is_dir() or not temp_root.is_relative_to(repo):
    raise SystemExit('Expected the copied run data and the workspace tmp directory.')

with tempfile.TemporaryDirectory(prefix='sql-only-audit-test-', dir=temp_root) as name:
    tmp = Path(name).resolve()
    if not tmp.is_relative_to(temp_root):
        raise SystemExit('Temporary directory escaped the workspace.')
    root = tmp / 'run'
    shutil.copytree(source, root)
    cmd = [sys.executable, str(repo / 'exp/2026-10-27-sql-only/analyze-results.py'),
           '--root', str(root), '--out', str(tmp / 'out'), '--tex-out', str(tmp / 'sql-only.tex')]

    def invoke():
        return subprocess.run(cmd, cwd=repo, text=True, capture_output=True)

    result = invoke()
    if result.returncode:
        raise AssertionError(result.stderr)
    summary = json.loads((tmp / 'out/verified-results.json').read_text(encoding='utf-8'))
    assert summary['rel-stack']['aggregates']['reuse']['sql-only']['tokens_with_learning'] == 923365
    assert summary['rel-trial']['aggregates']['reuse']['mavra']['tokens_with_learning'] == 2370229

    session = next((root / 'mavra-rel-stack-r1/sessions').glob('*.json'))
    original = session.read_bytes()
    session.write_bytes(original + b' ')
    result = invoke()
    assert result.returncode != 0 and 'source hash mismatch' in result.stderr
    session.write_bytes(original)

    status = root / 'status.json'
    status.write_text('{"state":"rel-trial","exit_code":null}', encoding='utf-8')
    result = invoke()
    assert result.returncode != 0 and 'not complete' in result.stderr
print('Audit passed intact data and rejected a changed session and an incomplete run.')
