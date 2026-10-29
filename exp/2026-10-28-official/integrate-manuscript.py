#!/usr/bin/env python3
"""Install reviewed paper sources and complete-data figures with a source backup."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PAPER = ROOT / 'overleaf'
GENERATED = PAPER / 'build/official-rebuild'


def main():
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    data = read(ROOT/'results/official-20261028/analysis.json')
    evidence = read(ROOT/'results/official-20261028/evidence-audit.json')
    if not evidence['complete'] or not evidence['require_complete']:
        raise SystemExit('Complete raw-evidence audit required before manuscript integration')
    if not all(c['complete_method_set'] for c in data['comparisons'].values()):
        raise SystemExit('Complete five-method comparisons required')
    manifest = read(HERE/'staging-manifest.json')
    for name, expected in manifest['sources'].items():
        actual = sha(PAPER/name) if (PAPER/name).exists() else None
        if actual != expected:
            raise SystemExit(f'Active manuscript changed since staging: {name}; reconcile before integration')
    for name, expected in manifest['staged'].items():
        if sha(HERE/'manuscript'/name) != expected:
            raise SystemExit(f'Staged source hash changed without review: {name}')
    replacements = {name: HERE/'manuscript'/name for name in manifest['staged']}
    replacements['gen/official-numbers.tex'] = GENERATED/'official-numbers.tex'
    replacements['tables/official-results.tex'] = GENERATED/'official-results.tex'
    for stem in ['reuse-work', 'reuse-work-zh', 'official-cumulative', 'official-cumulative-zh']:
        replacements[f'figures/{stem}.pdf'] = GENERATED/(stem+'.pdf')
    for name, source in replacements.items():
        assert (PAPER/name).resolve().is_relative_to(PAPER.resolve())
        if not source.is_file():
            raise SystemExit(f'Missing final artifact: {source}')
        if source.suffix == '.tex' and 'PREVIEW:' in source.read_text(encoding='utf-8'):
            raise SystemExit(f'Preview source cannot be installed: {source}')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = GENERATED/('pre-integration-sources-'+stamp+'.zip')
    before = {name: sha(PAPER/name) if (PAPER/name).exists() else None for name in replacements}
    with zipfile.ZipFile(backup, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in replacements:
            if (PAPER/name).exists(): archive.write(PAPER/name, name)
        archive.writestr('pre-integration-manifest.json', json.dumps(before, indent=2))
    for name, source in replacements.items():
        target = PAPER/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    audit = {'integrated_utc': datetime.now(timezone.utc).isoformat(),
             'backup': str(backup), 'backup_sha256': sha(backup),
             'analysis_sha256': sha(ROOT/'results/official-20261028/analysis.json'),
             'evidence_sha256': sha(ROOT/'results/official-20261028/evidence-audit.json'),
             'before': before, 'after': {name: sha(PAPER/name) for name in replacements},
             'status': 'installed; final complete-paper compilation and visual review required'}
    (HERE/'integration-audit.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'files_installed':len(replacements),'backup':str(backup)},indent=2))


if __name__ == '__main__': main()
