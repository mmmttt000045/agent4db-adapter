"""Write a small atomic status file; run.json files remain the authoritative evidence."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

dest = Path('results/sql-only-20261027/status.json')
data = {'updated_utc': datetime.now(timezone.utc).isoformat(), 'state': sys.argv[1],
        'exit_code': int(sys.argv[2]) if len(sys.argv) > 2 else None}
tmp = dest.with_suffix('.tmp')
tmp.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
os.replace(tmp, dest)
print(json.dumps(data), flush=True)
