"""Extend the archived runtime's bridge so all four modes receive feedback."""
from pathlib import Path
import hashlib,json

root=Path.cwd()
assert root.name=='agentdb-corrected-scenarios-20261031'
p=root/'src/metricbench.rs';s=p.read_text(encoding='utf-8');before=hashlib.sha256(s.encode()).hexdigest()
def change(old,new,count=1):
    global s
    assert s.count(old)==count,(s.count(old),old[:100])
    s=s.replace(old,new)
change('if !mode.starts_with("paper-") { return Ok(Value::Null); }','if !mode.starts_with("paper-") && mode != "metric-global-full" { return Ok(Value::Null); }')
change('body["arm"] = json!(mode.trim_start_matches("paper-"));','body["arm"] = json!(if mode == "metric-global-full" { "mavra" } else { mode.trim_start_matches("paper-") });')
change('if cell.mode.starts_with("paper-") {','if cell.mode.starts_with("paper-") || cell.mode == "metric-global-full" {',2)
change('format!("agentdb_fig6pub_{}_{stamp}",','format!("agentdb_fig6fix_{}_{stamp}",')
p.write_text(s,encoding='utf-8')
manifest={'base_adapter':'2026-10-30-published-scenarios frozen runtime','src/metricbench.rs':{'before_sha256_lf':before,'after_sha256_lf':hashlib.sha256(s.encode()).hexdigest()},
          'scope':'All four modes enter the same feedback service; native metric publication, maintenance and execution remain enabled.'}
(root/'exp/2026-10-31-corrected-scenarios/runtime-patch-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest))
