import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
DEST=ROOT/'tmp/paper-fig3-restore-20261029'
BEFORE=json.loads((HERE/'github-base.json').read_text(encoding='utf-8'))
shutil.copytree(ROOT/'tmp/paper-fig45-official-20261029',DEST,dirs_exist_ok=True)
# Publish only this request's edits. Preserve unrelated unpushed local writing.
allowed=['figures/relbench-cumulative.pdf','figures/relbench-cumulative-zh.pdf',
         'figures/relbench-cumulative.tex','figures/reuse-work.tex',
         'sections/07-evaluation.tex','sections/evaluation/relbench.tex',
         'sections/evaluation/sharing.tex','sections/evaluation/population.tex']
for name in allowed:
    p=ROOT/'overleaf'/name
    rel=Path(name)
    out=DEST/rel;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(p.read_bytes() if p.suffix=='.pdf' else p.read_text(encoding='utf-8').encode())
notes=(ROOT/'overleaf/README.md').read_text(encoding='utf-8')
notes=notes.replace('(../exp/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/exp/').replace('(../tools/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/tools/').replace('(../README.md)','(https://github.com/mmmttt000045/agent4db-adapter)')
(DEST/'source-notes.md').write_text(notes,encoding='utf-8',newline='\n')
readme='''# MAVRA：ICDE 2027 论文

本仓库是独立 Overleaf 论文源码仓库，源文件位于根目录。

| 用途 | 入口与编译器 |
| --- | --- |
| 英文稿 | main-en.tex / pdfLaTeX |
| 中英对照稿 | main.tex / XeLaTeX |

## 当前图表安排（2026-10-29，按用户最新更正）

- Fig.3 恢复历史版本 01daa213 的整张累计图及图注，沿用五截点网关实验，不用昨晚官方API数据。英文、中文 PDF 与原版字节一致。
- 删除上一版新增的六任务质量图；该图不再出现在论文中。旧图文件及数据保留为历史记录。
- 昨晚官方API实验仅用于替换用户所指的原 Fig.5（五方法工作量图）。删除前一张图后，图号自动变为 Fig.4；工作量图的 PDF、数据、版式未再次改动。
- 官方实验的设置、计量、质量与复用轨迹审计集中在工作量图对应小节。所有90个会话及失败结果保留，图中仍为每方法、每库六个复用会话；不与历史网关数据合并。
- 引言、摘要、结论、系统设计、所有表格与数值宏、Fig.1位置均保持此次修改前状态，已逐文件核对。
- Table III 保留能力勾叉表；Table IV 保留用户指定的历史七方法整表及旧数据。

## 证据

- [本次恢复记录](evidence/2026-10-29-fig3-restore/README.md)
- [Fig.3 原版文件哈希](evidence/2026-10-29-fig3-restore/restored-fig3.json)
- [官方API完整分析](evidence/official-20261028/analysis.json)
- [官方API质量与泄漏审计](evidence/official-20261028/evidence-audit.json)
- [复用轨迹审计](evidence/2026-10-29/README.md)
- [较早图表迭代记录](evidence/2026-10-29-fig45/README.md)
- [源码历史说明](source-notes.md)

## 编译与同步

英文选择 main-en.tex / pdfLaTeX，双语选择 main.tex / XeLaTeX。本地可执行 bash build.sh all。GitHub推送后，在 Overleaf 的 GitHub 集成中拉取更新。编译无需实验服务器或模型API。
'''
(DEST/'README.md').write_text(readme,encoding='utf-8',newline='\n')
evidence=DEST/'evidence/2026-10-29-fig3-restore';evidence.mkdir(parents=True,exist_ok=True)
for name in ['README.md','restored-fig3.json']:
    shutil.copyfile(HERE/name,evidence/name)
remote={f['path']:f for f in BEFORE['files']}
files=[]
for p in sorted(DEST.rglob('*')):
    if not p.is_file():continue
    b=p.read_bytes();rel=p.relative_to(DEST).as_posix()
    if p.suffix!='.pdf' and re.search(r'sk-[A-Za-z0-9]{20,}|(?:postgres(?:ql)?://)[^\s]+:[^\s]+@',b.decode('utf-8')):
        raise RuntimeError('Potential credential in '+rel)
    sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    files.append(dict(path=rel,sha=sha,sha256=hashlib.sha256(b).hexdigest(),size=len(b),
                      mode=remote.get(rel,{}).get('mode','100644'),binary=p.suffix=='.pdf',changed=sha!=remote.get(rel,{}).get('sha')))
protected=json.loads((HERE/'protected-files.json').read_text(encoding='utf-8'))
for rel,h in protected.items():
    assert hashlib.sha256((ROOT/'overleaf'/rel).read_bytes()).hexdigest()==h,rel
    assert not next(f for f in files if f['path']==rel)['changed'],rel
plan=dict(repository='mmmttt000045/icde-2027-paper',branch='main',expected_head=BEFORE['head'],
          base_tree=BEFORE['tree'],source_directory=str(DEST),files=files,deletions=[])
(HERE/'sync-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
with tarfile.open(ROOT/'tmp/paper-fig3-restore-20261029.tar.gz','w:gz') as t:
    for f in files:t.add(DEST/f['path'],arcname=f['path'])
print(json.dumps({'files':len(files),'changed':[f['path'] for f in files if f['changed']],
                  'secret_scan':'passed','protected_files':len(protected)},ensure_ascii=True))
