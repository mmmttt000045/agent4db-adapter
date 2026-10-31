"""Extend the previous full-method bridge; preserve its published adapters."""
from pathlib import Path
import hashlib,json,subprocess

root=Path.cwd()
assert root.name=='agentdb-diverse-scenarios-20261031'
path=root/'src/metricbench.rs'
original=path.read_bytes()
text=original.decode('utf-8')
old='let tasks: Vec<_> = tasks_with(&o.metrics, o.question_set == "v2").into_iter().filter(|t| matches!(t.ask, Ask::Single { .. })).collect();'
assert text.count(old)==1
text=text.replace(old,'let tasks = tasks_with(&o.metrics, o.question_set == "v2");')
path.write_text(text,encoding='utf-8')
patch=root/'exp/2026-10-31-diverse-scenarios/native-bench.patch'
subprocess.run(['git','apply','--check',str(patch)],check=True)
subprocess.run(['git','apply',str(patch)],check=True)
text=path.read_text(encoding='utf-8')
assert text.count('agentdb_fig6fix_')==1
text=text.replace('agentdb_fig6fix_','agentdb_fig6div_')
path.write_text(text,encoding='utf-8')
out={'base':'Corrected 2026-10-31 frozen runtime, complete published memory bridge',
     'before_sha256':hashlib.sha256(original).hexdigest(),
     'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
     'scope':'Remove the single-form restriction; add deterministic diverse task selection and free bank export. Published algorithm, common feedback and checkpoint bridge remain.'}
(root/'exp/2026-10-31-diverse-scenarios/runtime-patch-manifest.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
