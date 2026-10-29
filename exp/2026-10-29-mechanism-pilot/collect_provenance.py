"""Hash bounded experiment sources, without reading secrets or unrelated data."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform

root=Path('/root/agentdb-mechanism-pilot-20261029')
systems=Path('/root/agentdb-mechanism-systems-20261029')
study=Path('exp/2026-10-29-mechanism-pilot')

def hashes(base):
    out={}
    for folder in ['src','tools/relbench',str(study)]:
        for f in sorted((base/folder).rglob('*')):
            if not f.is_file() or '__pycache__' in f.parts or f.name.startswith('.') or 'manifest' in f.name:continue
            out[str(f.relative_to(base))]=hashlib.sha256(f.read_bytes()).hexdigest()
    for f in [base/'Cargo.lock',base/'target/release/agentdb-mid']:
        if f.is_file():out[str(f.relative_to(base))]=hashlib.sha256(f.read_bytes()).hexdigest()
    return out

data={'collected_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
      'pilot_current_sources':hashes(root),'systems_current_sources':hashes(systems),
      'runtime_protocol':json.loads((root/study/'protocol.json').read_text()),
      'initial_manifest':json.loads((root/study/'runtime-manifest.json').read_text())}
for module in ['numpy','pandas','lightgbm','sklearn','psycopg']:
    m=__import__(module);data.setdefault('libraries',{})[module]=getattr(m,'__version__','unknown')
assert data['pilot_current_sources']['src/metric.rs']==data['systems_current_sources']['src/metric.rs']
data['frozen_feature_compiler_source_exact_match']=True
(root/'results/mechanism-pilot-20261029/runtime-provenance.json').write_text(json.dumps(data,indent=2))
print(json.dumps({'feature_compiler_match':True,'pilot_files':len(data['pilot_current_sources']),
                  'systems_files':len(data['systems_current_sources'])}))
