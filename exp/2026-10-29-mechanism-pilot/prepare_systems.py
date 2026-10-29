#!/usr/bin/env python3
"""Create an isolated test-only checkout from the frozen pilot source."""
from pathlib import Path
import hashlib
import json
import os
import shutil

base = Path('/root/agentdb-mechanism-pilot-20261029')
root = Path('/root/agentdb-mechanism-systems-20261029')
study = 'exp/2026-10-29-mechanism-pilot'
assert not root.exists(), 'Do not replace an existing experiment checkout'
os.umask(0o077)
root.mkdir()
for folder in ['src', 'tools']:
    shutil.copytree(base/folder, root/folder)
for name in ['Cargo.toml', 'Cargo.lock']:
    shutil.copy2(base/name, root/name)
(root/'data').mkdir()
shutil.copy2('/root/agentdb-mid/data/mock_fixture.sql',root/'data/mock_fixture.sql')
(root/study).mkdir(parents=True)
for name in ['system_tests.rs', 'systems-protocol.json', 'run_systems.py']:
    shutil.copy2(base/study/name, root/study/name)
# Cache reuse only: no dependency source or result files are uploaded.
shutil.copytree('/root/agentdb-official-20261028/target', root/'target')
env = next(x.split('=',1)[1] for x in (base/'.env').read_text().splitlines() if x.startswith('AGENTDB_URL='))
(root/'.env').write_text('AGENTDB_TEST_URL='+env+'\n')

def replace(path, old, new):
    path = root/path
    s=path.read_text()
    assert s.count(old)==1, (str(path), s.count(old))
    path.write_text(s.replace(old,new))

replace('src/middle.rs', '    pub exec_pause_ms: u64,', '''    pub exec_pause_ms: u64,
    #[cfg(test)]
    pub experiment_detach: bool,
    #[cfg(test)]
    #[serde(skip)]
    pub experiment_barrier: Option<Arc<(std::sync::atomic::AtomicBool, tokio::sync::Notify, tokio::sync::Notify)>>,''')
replace('src/middle.rs','            exec_pause_ms: 0,','''            exec_pause_ms: 0,
            #[cfg(test)]
            experiment_detach: false,
            #[cfg(test)]
            experiment_barrier: None,''')
old = '''        let v = snap.query(QKind::Exec, sql).await?.to_json(self.cfg.max_rows);
        snap.commit().await?;
        Ok(json!({"result": v, "source": "snapshot", "snapshot": {"versions": vers, "checks_run": run, "checks_reused": reused}}))'''
new = '''        // Experiment-only matched control: every preceding version read,
        // guard and cache operation is identical; only snapshot lifetime differs.
        #[cfg(test)]
        if self.cfg.experiment_detach {
            snap.commit().await?;
            if let Some(b) = &self.cfg.experiment_barrier {
                if b.0.load(std::sync::atomic::Ordering::SeqCst) {
                    b.1.notify_one();
                    b.2.notified().await;
                }
            }
            let v = self.db.query(QKind::Exec, sql).await?.to_json(self.cfg.max_rows);
            return Ok(json!({"result":v,"source":"tx-precheck",
                "snapshot":{"versions":vers,"checks_run":run,"checks_reused":reused}}));
        }
        #[cfg(test)]
        if let Some(b) = &self.cfg.experiment_barrier {
            if b.0.load(std::sync::atomic::Ordering::SeqCst) {
                b.1.notify_one();
                b.2.notified().await;
            }
        }
        let v = snap.query(QKind::Exec, sql).await?.to_json(self.cfg.max_rows);
        snap.commit().await?;
        Ok(json!({"result": v, "source": "snapshot", "snapshot": {"versions": vers, "checks_run": run, "checks_reused": reused}}))'''
replace('src/middle/metrics.rs',old,new)
with (root/'src/integration_tests.rs').open('a') as f:
    f.write('\ninclude!(concat!(env!("CARGO_MANIFEST_DIR"), "/'+study+'/system_tests.rs"));\n')
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
          for folder in ['src',study] for p in (root/folder).rglob('*') if p.is_file()}
(root/study/'systems-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'checkout':str(root),'modified_core':['src/middle.rs','src/middle/metrics.rs'],
                  'production_build_behavior':'unchanged; additions are cfg(test) only'}))
