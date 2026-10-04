from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import tarfile
import zipfile

root = Path('/root/agentdb-shared-memory-20261003')
source_zip = root / 'final-overleaf.zip'
report = {
    'verified_utc': datetime.now(timezone.utc).isoformat(),
    'zip_sha256': hashlib.sha256(source_zip.read_bytes()).hexdigest(),
    'command': ['bash', 'build.sh', 'all'],
    'fresh_extract_directory': 'package-verification',
    'papers': {},
}
with zipfile.ZipFile(source_zip) as z:
    members = [i for i in z.infolist() if not i.is_dir()]
    report['source_file_count'] = len(members)
    for i in members:
        assert z.read(i) == (root / 'package-verification' / i.filename).read_bytes()
        assert z.read(i) == (root / 'overleaf' / i.filename).read_bytes()
report['source_matches_primary_and_extracted_tree'] = True
for stem, expected_pages in [('main-en', 13), ('main', 20)]:
    build = root / 'package-verification' / 'build'
    pdf = build / (stem + '.pdf')
    log = (build / (stem + '.log')).read_text(errors='replace')
    cold_text = subprocess.check_output(['pdftotext', '-layout', str(pdf), '-'])
    primary_text = subprocess.check_output([
        'pdftotext', '-layout', str(root / 'overleaf' / 'build' / (stem + '.pdf')), '-'
    ])
    assert cold_text == primary_text
    text = cold_text.decode()
    record = {
        'pages': int(re.search(r'Output written on .*?\((\d+) pages', log).group(1)),
        'references_begin_page': min(
            i + 1 for i, page in enumerate(text.split('\f'))
            if re.search(r'^\s*(?:\d+\s+)?References\b', page, re.M)
        ),
        'overfull_hbox': len(re.findall(r'Overfull \\hbox', log)),
        'overfull_vbox': len(re.findall(r'Overfull \\vbox', log)),
        'undefined_citations_or_references': len(re.findall(
            r'(?:Citation|Reference).*undefined|There were undefined', log
        )),
        'missing_glyphs': len(re.findall('Missing character:', log)),
        'extracted_text_byte_identical_to_primary': True,
        'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
    }
    assert record['pages'] == expected_pages
    assert all(record[k] == 0 for k in (
        'overfull_hbox', 'overfull_vbox', 'undefined_citations_or_references', 'missing_glyphs'
    ))
    report['papers'][stem] = record
(root / 'results' / 'cold-package-verification.json').write_text(
    json.dumps(report, indent=2) + '\n'
)

paths = []
for pattern in (
    'results/*acceptance.log', 'results/final-integration*',
    'results/orientation-test-*/report.json',
    'results/mock-1791058611339788/report.json',
    'results/repair-ambiguity-1791058613162634/report.json',
    'results/snapshot-binding-1791058692146772/report.json',
    'results/scenario-test-1791058592570583/report.json',
    'results/cold-package-verification.json',
    'package-verification/build/*.log',
):
    paths.extend(p for p in root.glob(pattern) if p.is_file())
with tarfile.open(root / 'final-validation.tar.gz', 'w:gz') as archive:
    for p in sorted(set(paths)):
        archive.add(p, arcname=str(p.relative_to(root)))
print(json.dumps({'cold_package': report, 'archived_validation_files': len(set(paths))}))
