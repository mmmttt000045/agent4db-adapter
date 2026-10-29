"""Record the fixed source, executable, inputs and runtime versions without recording secrets."""
import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

files = [Path('target/release/agentdb-mid'), *Path('tools/relbench').glob('*.py'),
         *Path('src').rglob('*.rs'), *Path('exp/2026-10-27-sql-only').glob('*')]
for db in ('rel-stack', 'rel-trial'):
    files += [Path(f'results/relbench-data/{db}/manifest.yaml'),
              Path(f'results/relbench-data/{db}-prep/timeline.json')]
versions = {}
for package in ('lightgbm', 'psycopg', 'numpy', 'pandas', 'pyarrow'):
    try:
        versions[package] = metadata.version(package)
    except metadata.PackageNotFoundError:
        versions[package] = None
record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'host': platform.node(),
          'python': platform.python_version(), 'packages': versions,
          'files': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}}
Path('results/sql-only-20261027/run-provenance.json').write_text(
    json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
