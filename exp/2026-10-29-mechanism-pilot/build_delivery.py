#!/usr/bin/env python3
"""Package verified scientific figures and bounded, credential-free evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import py_compile
import zipfile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'output/mechanism-pilot-20261029'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


a = read(OUT / 'pilot-analysis.json')
s = read(OUT / 'system-analysis.json')
assert a['complete'] and len(a['rows']) == 8
assert all(row['test_score'] is None for row in a['rows'])
assert s['B']['complete'] and s['B']['requests'] == 9216
assert s['B']['unavailable'] == 0
assert s['C']['complete'] and s['C']['gate_passed']
assert all(x['cleaned_up'] for x in s['sources'].values())
assert read(ROOT / 'results/mechanism-systems-20261029/status.json')['status'] == 'complete'

main = ['figure-a-pilot', 'figure-b-controlled', 'figure-c-combined-preview']
files = [OUT / (name + ext) for name in main for ext in ['.pdf', '.png', '.svg']]
files += [OUT / (name + ext) for name in ['figure-b-archive-preview', 'figure-c-archive-preview']
          for ext in ['.pdf', '.png']]
files += [OUT / name for name in ['pilot-analysis.json', 'pilot-results.md', 'system-analysis.json',
                                 'archive-preview-evidence.json', 'combined-c-evidence.json']]
files += [HERE / name for name in ['README.md', 'protocol.json', 'systems-protocol.json',
                                  'formal-a-next.json', 'seed-binding-preflight.json']]
files += [ROOT / 'results/mechanism-pilot-20261029/runtime-provenance.json']
assert all(p.is_file() and p.stat().st_size for p in files)

font_checks = {}
for path in [p for p in files if p.suffix == '.pdf']:
    pdf = PdfReader(path)
    assert len(pdf.pages) == 1
    embedded = []
    for font_ref in pdf.pages[0]['/Resources']['/Font'].values():
        font = font_ref.get_object()
        descendants = font.get('/DescendantFonts', [font])
        for item in descendants:
            f = item.get_object()
            desc = f.get('/FontDescriptor')
            assert desc is not None, f'No font descriptor: {path}'
            desc = desc.get_object()
            assert any(key in desc for key in ['/FontFile', '/FontFile2', '/FontFile3']), path
            embedded.append(str(f.get('/BaseFont')))
    font_checks[path.name] = {'pages': 1, 'embedded_fonts': embedded,
                             'width_pt': float(pdf.pages[0].mediabox.width),
                             'height_pt': float(pdf.pages[0].mediabox.height)}

for path in HERE.glob('*.py'):
    py_compile.compile(str(path), doraise=True)

manifest = {
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'A development pilot; B fixed-definition controlled supplement; C matched safety plus archived overhead',
    'verification': {'A_cells': 8, 'A_valid_solutions': sum(r['valid'] for r in a['rows']),
                     'B_cells': 72, 'B_requests': 9216, 'B_unavailable': 0,
                     'C_calls': 30, 'C_gate_passed': True, 'system_database_cleanup': True,
                     'python_syntax': 'all study scripts passed', 'pdf_fonts': font_checks},
    'style_sources': {str(p.relative_to(ROOT)): sha(p) for p in [
        ROOT / 'tools/figures/style.py', ROOT / 'tools/figures/mplstyle.py',
        ROOT / 'overleaf/latex/preamble.tex']},
    'files': {str(p.relative_to(ROOT)): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in files},
    'exclusions': 'No credentials, account balances or raw model conversations in this delivery archive.',
}
manifest_file = OUT / 'delivery-manifest.json'
manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
with zipfile.ZipFile(OUT / 'mechanism-figures-review.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files + [manifest_file]:
        archive.write(path, str(path.relative_to(ROOT)).replace('\\', '/'))
print(json.dumps({'verification': {k: v for k, v in manifest['verification'].items() if k != 'pdf_fonts'},
                  'zip': str(OUT / 'mechanism-figures-review.zip')}, ensure_ascii=False))
