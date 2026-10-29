import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEST = ROOT / 'tmp/paper-restore-fig5-table3-20261029'
BEFORE = json.loads((HERE / 'github-base.json').read_text(encoding='utf-8'))
if not DEST.exists():
    shutil.copytree(ROOT/'tmp/paper-github-20261029', DEST)
for p in (ROOT/'overleaf').rglob('*'):
    rel = p.relative_to(ROOT/'overleaf')
    if not p.is_file() or 'build' in rel.parts or p.suffix not in ('.tex', '.pdf', '.bib', '.sh'):
        continue
    out = DEST/rel
    out.parent.mkdir(parents=True, exist_ok=True)
    data = p.read_bytes() if p.suffix == '.pdf' else p.read_text(encoding='utf-8').replace('\r\n', '\n').encode()
    out.write_bytes(data)
notes = (ROOT/'overleaf/README.md').read_text(encoding='utf-8')
notes = notes.replace('(../exp/', '(https://github.com/mmmttt000045/agent4db-adapter/tree/main/exp/').replace('(../tools/', '(https://github.com/mmmttt000045/agent4db-adapter/tree/main/tools/').replace('(../README.md)', '(https://github.com/mmmttt000045/agent4db-adapter)')
(DEST/'source-notes.md').write_text(notes, encoding='utf-8', newline='\n')
readme = (ROOT/'tmp/paper-github-20261029/README.md').read_text(encoding='utf-8')
readme = readme.replace('Fig.5 是完整策略下的调用行为诊断。', 'Fig.5 已按用户要求恢复为上一版每题耗时与 token 散点图，来自独立的早期受控指标实验；Table III 恢复为上一版文字说明式对照表。')
readme = readme.replace('Fig.5 对应正文已加入逐会话来源核验', 'RelBench 正文保留逐会话来源核验')
readme += '\n## Fig.5 与 Table III 恢复记录\n\n这两处恢复自本次更新前的提交 01daa2133a54ee45a8d1b529b5e04167e81ed340。Fig.5 的中英文图形及图注、Table III 源码与该提交逐字节一致。图文引用已随之调整。官方 API 主表、完整结果和复用轨迹审计继续保留，旧图数据不并入官方 API 对照。\n'
(DEST/'README.md').write_text(readme, encoding='utf-8', newline='\n')
review_path = DEST/'evidence/2026-10-29/README.md'
review = (ROOT/'tmp/paper-github-20261029/evidence/2026-10-29/README.md').read_text(encoding='utf-8')
review = '> 版本说明：本文审计的是现已退出正文的调用分布图。当前 Fig.5 已恢复为先前的每题成本散点图；本审计结论保留于 RelBench 正文，原始审计证据不变。\n\n' + review
review_path.write_text(review, encoding='utf-8', newline='\n')

remote = {f['path']: f for f in BEFORE['files']}
files = []
for p in sorted(DEST.rglob('*')):
    if not p.is_file():
        continue
    b = p.read_bytes()
    if p.suffix != '.pdf':
        s = b.decode('utf-8')
        if re.search(r'sk-[A-Za-z0-9]{20,}|(?:postgres(?:ql)?://)[^\s]+:[^\s]+@', s):
            raise RuntimeError('Potential credential in ' + str(p.relative_to(DEST)))
    rel = p.relative_to(DEST).as_posix()
    sha = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
    files.append(dict(path=rel, sha=sha, sha256=hashlib.sha256(b).hexdigest(), size=len(b),
                      mode=remote.get(rel, {}).get('mode', '100644'),
                      binary=p.suffix=='.pdf', changed=sha!=remote.get(rel, {}).get('sha')))
plan = dict(repository='mmmttt000045/icde-2027-paper', branch='main', expected_head=BEFORE['head'],
            base_tree=BEFORE['tree'], source_directory=str(DEST), files=files, deletions=[])
(HERE/'sync-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
with tarfile.open(ROOT/'tmp/paper-restore-fig5-table3-20261029.tar.gz', 'w:gz') as tar:
    for f in files:
        tar.add(DEST/f['path'], arcname=f['path'])
print(json.dumps({'files':len(files), 'changed':[f['path'] for f in files if f['changed']], 'secret_scan':'passed'}))
