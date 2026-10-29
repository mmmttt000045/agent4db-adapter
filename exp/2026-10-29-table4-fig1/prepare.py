import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEST = ROOT/'tmp/paper-table4-fig1-20261029'
BEFORE = json.loads((HERE/'github-base.json').read_text(encoding='utf-8'))
if not DEST.exists():
    shutil.copytree(ROOT/'tmp/paper-restore-fig5-table3-20261029', DEST)
for p in (ROOT/'overleaf').rglob('*'):
    rel=p.relative_to(ROOT/'overleaf')
    if not p.is_file() or 'build' in rel.parts or p.suffix not in ('.tex','.pdf','.bib','.sh'):
        continue
    out=DEST/rel;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(p.read_bytes() if p.suffix=='.pdf' else p.read_text(encoding='utf-8').replace('\r\n','\n').encode())
notes=(ROOT/'overleaf/README.md').read_text(encoding='utf-8')
notes=notes.replace('(../exp/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/exp/').replace('(../tools/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/tools/').replace('(../README.md)','(https://github.com/mmmttt000045/agent4db-adapter)')
(DEST/'source-notes.md').write_text(notes,encoding='utf-8',newline='\n')
readme='''# MAVRA：ICDE 2027 论文

本仓库是独立 Overleaf 论文源码仓库，源文件位于根目录。

| 用途 | 入口与编译器 |
| --- | --- |
| 英文稿 | main-en.tex / pdfLaTeX |
| 中英对照稿 | main.tex / XeLaTeX |
| 正文 | paper.tex、sections/ |
| 图表与数值 | figures/、tables/、gen/ |

## 当前版本：2026-10-29

- Table III 已撤销误回滚，保留能力对照的勾叉表。
- Table IV 按用户明确要求恢复为 01daa213 版本的整张表及旧实验数据：七方法、两数据库、三个任务、五截点，共210个历史网关会话。正文注明该实验的执行限制与历史估价口径。
- 本轮官方API结果另行陈述，共90个会话，包含全部失败及不利结果；完整表仍保留于 tables/official-results.tex，数值与审计证据在 evidence/official-20261028/。两批结果不合并。
- Fig.1 在引言首次引用后声明，并禁止浮到摘要之前的首栏顶部；图形内容不变。
- Fig.3 保留官方API实验含学习的累计成本。Fig.5 保持上一轮已恢复的历史受控指标实验散点图。
- 官方API复用轨迹审计仍在 RelBench 正文。12个MAVRA复用会话中9个首先验证完整旧SQL、6个原样保留；查找工具可以隐式编译。编译结果返回不等于采用，结构化定义的独立增量收益尚未分离。

## 证据与构建

- [复用轨迹审计](evidence/2026-10-29/README.md)
- [逐会话审计摘要](evidence/2026-10-29/lineage-summary.json)
- [官方API完整分析](evidence/official-20261028/analysis.json)
- [官方API质量与泄漏审计](evidence/official-20261028/evidence-audit.json)
- [源码历史说明](source-notes.md)

本地可执行 bash build.sh all。Overleaf 英文入口选择 main-en.tex / pdfLaTeX，中英对照选择 main.tex / XeLaTeX。GitHub 推送后，需要在 Overleaf 的 GitHub 集成中拉取更新。
'''
(DEST/'README.md').write_text(readme,encoding='utf-8',newline='\n')
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
plan=dict(repository='mmmttt000045/icde-2027-paper',branch='main',expected_head=BEFORE['head'],
          base_tree=BEFORE['tree'],source_directory=str(DEST),files=files,deletions=[])
(HERE/'sync-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with tarfile.open(ROOT/'tmp/paper-table4-fig1-20261029.tar.gz','w:gz') as tar:
    for f in files:tar.add(DEST/f['path'],arcname=f['path'])
print(json.dumps({'files':len(files),'changed':[f['path'] for f in files if f['changed']],'secret_scan':'passed'}))
