"""Verify replay of the isolated benchmark patch and archive the measured source."""
import hashlib,json,subprocess,tarfile,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
assert ROOT.name=='agentdb-diverse-scenarios-20261031'
assert not (ROOT/'results/diverse-scenarios-20261031/execution-state.json').exists()
old=Path('/root/agentdb-corrected-scenarios-20261031/src/metricbench.rs').read_bytes()
with tempfile.TemporaryDirectory(prefix='mavra-replay-') as temp:
    work=Path(temp);(work/'src').mkdir()
    text=old.decode()
    restricted='let tasks: Vec<_> = tasks_with(&o.metrics, o.question_set == "v2").into_iter().filter(|t| matches!(t.ask, Ask::Single { .. })).collect();'
    assert text.count(restricted)==1
    path=work/'src/metricbench.rs'
    path.write_text(text.replace(restricted,'let tasks = tasks_with(&o.metrics, o.question_set == "v2");'))
    subprocess.run(['git','apply',str(HERE/'native-bench.patch')],cwd=work,check=True)
    replay=path.read_text().replace('agentdb_fig6fix_','agentdb_fig6div_').encode()
    assert replay==(ROOT/'src/metricbench.rs').read_bytes(),'Patch replay differs from measured benchmark'
manifest={'base':'Corrected 2026-10-31 frozen runtime, complete published memory bridge',
          'before_sha256':hashlib.sha256(old).hexdigest(),
          'after_sha256':hashlib.sha256(replay).hexdigest(),
          'patch_sha256':hashlib.sha256((HERE/'native-bench.patch').read_bytes()).hexdigest(),
          'replay_verified':True}
(HERE/'runtime-patch-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
files=[ROOT/'Cargo.toml',ROOT/'Cargo.lock',ROOT/'data/mock_fixture.sql']
files+=list((ROOT/'src').rglob('*.rs'))
files+=[p for p in (ROOT/'third_party').rglob('*') if p.is_file()]
files+=[ROOT/'tools/relbench/harness.py',ROOT/'tools/relbench/gmemory_service.py']
files+=[p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py','.json','.patch','.log') and '__pycache__' not in p.parts]
provenance=json.loads((HERE/'data-provenance.json').read_text())
files+=[ROOT/name for name in provenance['files']]
files=sorted(set(files))
source={str(p.relative_to(ROOT)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in files}
(HERE/'source-archive-manifest.json').write_text(json.dumps(source,indent=2)+'\n')
archive=HERE/'runtime-source.tgz'
with tarfile.open(archive,'w:gz') as tar:
    for p in files:tar.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
    tar.add(HERE/'source-archive-manifest.json',arcname=str((HERE/'source-archive-manifest.json').relative_to(ROOT)))
result={'files':len(files)+1,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'bytes':archive.stat().st_size,'patch_replay_verified':True,'paid_model_calls_before_freeze':0}
(HERE/'source-archive.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
