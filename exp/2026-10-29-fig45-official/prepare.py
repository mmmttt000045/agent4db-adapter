import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEST = ROOT/'tmp/paper-fig45-official-20261029'
BEFORE = json.loads((HERE/'github-base.json').read_text(encoding='utf-8'))
if not DEST.exists():
    shutil.copytree(ROOT/'tmp/paper-table4-fig1-20261029', DEST)
for p in (ROOT/'overleaf').rglob('*'):
    rel=p.relative_to(ROOT/'overleaf')
    if not p.is_file() or 'build' in rel.parts or p.suffix not in ('.tex','.pdf','.bib','.sh'):
        continue
    out=DEST/rel;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(p.read_bytes() if p.suffix=='.pdf' else p.read_text(encoding='utf-8').replace('\r\n','\n').encode())
notes=(ROOT/'overleaf/README.md').read_text(encoding='utf-8')
notes=notes.replace('(../exp/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/exp/').replace('(../tools/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/tools/').replace('(../README.md)','(https://github.com/mmmttt000045/agent4db-adapter)')
(DEST/'source-notes.md').write_text(notes,encoding='utf-8',newline='\n')
readme=(ROOT/'tmp/paper-table4-fig1-20261029/README.md').read_text(encoding='utf-8')
readme=readme.replace('- Fig.3 保留官方API实验含学习的累计成本。Fig.5 保持上一轮已恢复的历史受控指标实验散点图。',
                    '- Fig.3：官方API实验含学习的累计成本。Fig.4：同一实验五方法、六任务的测试质量与有效方案（全部90个会话）。Fig.5：恢复今早的五方法工作量分解版式与数据（每方法、每库六个复用会话），并修正记忆内部开销说明。每张图回答不同的问题。')
readme=readme.replace('官方API复用轨迹审计仍在 RelBench 正文。','官方API复用轨迹审计保留在 Fig.5 对应正文。')
readme=readme.replace('## 证据与构建','## 本次 Fig.4/5 重构\n\n使用已发表的 ACE、AWM、G-Memory，以及共同无记忆对照与 MAVRA。失败按冻结协议保留回退分数；不隐藏不利完成结果。Fig.4 表示质量与有效方案，Fig.5 表示探索和验证工作量；两者都不冒充已完成的特征组合消融。原 Fig.4 的记忆作用域消融保留正文与表格，旧图留档。\n\n逐点数值、来源哈希和范围说明在 [图表证据](evidence/2026-10-29-fig45/README.md)。\n\n## 证据与构建')
(DEST/'README.md').write_text(readme,encoding='utf-8',newline='\n')
evidence=DEST/'evidence/2026-10-29-fig45';evidence.mkdir(parents=True,exist_ok=True)
for name in ('figure-data.json','README.md'):
    shutil.copyfile(HERE/name,evidence/name)
remote={f['path']:f for f in BEFORE['files']}
files=[]
for p in sorted(DEST.rglob('*')):
    if not p.is_file():continue
    b=p.read_bytes()
    if p.suffix!='.pdf' and re.search(r'sk-[A-Za-z0-9]{20,}|(?:postgres(?:ql)?://)[^\s]+:[^\s]+@',b.decode('utf-8')):
        raise RuntimeError('Potential credential in '+str(p.relative_to(DEST)))
    rel=p.relative_to(DEST).as_posix()
    sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    files.append(dict(path=rel,sha=sha,sha256=hashlib.sha256(b).hexdigest(),size=len(b),
                      mode=remote.get(rel,{}).get('mode','100644'),binary=p.suffix=='.pdf',
                      changed=sha!=remote.get(rel,{}).get('sha')))
protected=json.loads((HERE/'protected-files.json').read_text(encoding='utf-8'))
for p,h in protected.items():
    assert hashlib.sha256((ROOT/'overleaf'/p).read_bytes()).hexdigest()==h,p
    f=next(f for f in files if f['path']==p)
    assert not f['changed'],p
plan=dict(repository='mmmttt000045/icde-2027-paper',branch='main',expected_head=BEFORE['head'],
          base_tree=BEFORE['tree'],source_directory=str(DEST),files=files,deletions=[])
(HERE/'sync-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with tarfile.open(ROOT/'tmp/paper-fig45-official-20261029.tar.gz','w:gz') as tar:
    for f in files:tar.add(DEST/f['path'],arcname=f['path'])
print(json.dumps({'files':len(files),'changed':[f['path'] for f in files if f['changed']],'secret_scan':'passed','protected_files':'unchanged'}))
