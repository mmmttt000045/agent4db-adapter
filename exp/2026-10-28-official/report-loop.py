#!/usr/bin/env python3
"""Keep a machine-readable audit available even if the desktop is offline."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

def main():
    import fcntl
    here=Path(__file__).resolve().parent
    out=Path('results/official-20261028')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'report-loop.lock').open('w') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        (out/'report-loop.pid').write_text(str(os.getpid())+'\n')
        while True:
            subprocess.run(['python3',str(here/'analyze.py'),'--root',str(out),'--out',str(out)],check=False)
            try:
                status=json.loads((out/'status.json').read_text()) if (out/'status.json').exists() else {}
                deadline=datetime.fromisoformat(json.loads((here/'protocol.json').read_text())['deadline_utc'].replace('Z','+00:00'))
                if status.get('status') in ('completed','finished_with_gaps') or datetime.now(timezone.utc)>deadline:
                    break
            except (OSError,json.JSONDecodeError) as err:
                print('Snapshot not yet readable:',type(err).__name__,flush=True)
            time.sleep(60)


if __name__=='__main__': main()
