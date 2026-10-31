"""Archive the adapter metadata repair; original code, failures and fees persist."""
import hashlib,json,tarfile
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
assert ROOT.name=='agentdb-diverse-scenarios-20261031'
out=ROOT/'results/diverse-scenarios-20261031'
assert not (out/'execution-state.json').exists()
prior=json.loads((out/'development/frozen-source-manifest.json').read_text())
allowed=['memory-service.py','offline-smoke.py','run-study.py','prepare-study.py']
allowed={str((HERE/name).relative_to(ROOT)) for name in allowed}
changed={}
for name,digest in prior.items():
    if name.startswith('gmemory-core/'):path=ROOT/'results/ext/GMemory'/name.removeprefix('gmemory-core/')
    else:path=ROOT/name
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=digest:
        assert name in allowed,name
        changed[name]=actual
smoke=json.loads((ROOT/'results/offline-smoke/smoke-result.json').read_text())
assert smoke['paid_model_calls']==0 and smoke['native']['tasks']==34
assert all(len(smoke[arm]['update_forms'])==5 for arm in ('ace','awm','gmemory','mavra'))
manifest={'utc':datetime.now(timezone.utc).isoformat(),'implementation_revision':3,
          'reason':'Allow five analytical Ask forms in the adapter task-file timestamp metadata, rather than assuming a single period',
          'changed_source_hashes':changed,'protocol_unchanged':True,'native_binary_unchanged':True,
          'published_upstream_unchanged':True,'all_five_forms_tested_on_all_four_memory_arms':True,
          'selection_rule':'All initial interrupted cells excluded; all their fees retained; common question bank and eleven scenarios unchanged'}
(HERE/'implementation-amendment.json').write_text(json.dumps(manifest,indent=2)+'\n')
files=[ROOT/name for name in changed]+[HERE/'recover-adapter.py',HERE/'amend-source.py',HERE/'implementation-amendment.json',
       ROOT/'results/offline-smoke/smoke-result.json',out/'development/development-record.json']
archive=HERE/'runtime-source-recovery.tgz'
assert not archive.exists()
with tarfile.open(archive,'w:gz') as tar:
    for p in files:tar.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
record={'files':len(files),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size}
(HERE/'source-recovery.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
