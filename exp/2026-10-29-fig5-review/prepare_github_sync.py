"""Prepare manuscript-only GitHub files and a matching compile snapshot."""
import hashlib
import json
import pathlib
import re
import tarfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
DEST = ROOT / 'tmp/paper-github-20261029'
DEST.mkdir(parents=True, exist_ok=True)
before = json.loads((HERE/'github-before.json').read_text(encoding='utf-8'))
remote = {f['path']:f for f in before['files']}

def put(path, data):
    p=DEST/path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)

for p in (ROOT/'overleaf').rglob('*'):
    rel=p.relative_to(ROOT/'overleaf')
    if not p.is_file() or 'build' in rel.parts or p.suffix not in ('.tex','.pdf','.bib','.sh'):
        continue
    data=p.read_bytes() if p.suffix=='.pdf' else p.read_text(encoding='utf-8').replace('\r\n','\n').encode()
    put(rel,data)

put('source-notes.md',(ROOT/'overleaf/README.md').read_text(encoding='utf-8').replace('(../exp/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/exp/').replace('(../tools/','(https://github.com/mmmttt000045/agent4db-adapter/tree/main/tools/').replace('(../README.md)','(https://github.com/mmmttt000045/agent4db-adapter)').encode())
put('README.md','''# MAVRA：ICDE 2027 论文

本仓库是 MAVRA 的独立 Overleaf 论文源码仓库。源文件位于根目录。

| 用途 | 入口与编译器 |
| --- | --- |
| 英文稿 | `main-en.tex` / pdfLaTeX |
| 中英对照稿 | `main.tex` / XeLaTeX |
| 正文 | `paper.tex`、`sections/` |
| 图表与数值 | `figures/`、`tables/`、`gen/` |

## 当前同步：2026-10-29

- 集成官方 API 五方法、两数据库、三任务、三截点的完整比较，共90个正式会话；旧网关数据分别陈述。
- 当前主表为 `tables/official-results.tex`，Fig.3 是含学习的累计开销，Fig.5 是完整策略下的调用行为诊断。
- Fig.5 对应正文已加入逐会话来源核验：12个MAVRA复用会话中9个首先验证完整旧SQL，6个原样保留它。查找工具也会隐式编译，因此显式组合调用为零不代表没有编译。
- 明确报告首截点一次编译SQL未通过目标任务时间审计；当前实验尚未分离结构化定义的增量收益。新的组件消融未执行，未把调用数当作核心表示的因果证据。
- 移除当前稿件的自制示例检索比较，保留完整已发表方法结果及质量退步。

逐会话复核及拟议实验见 [Fig.5 复核](evidence/2026-10-29/README.md) 和 [来源摘要](evidence/2026-10-29/lineage-summary.json)。官方比较汇总见 [实验汇总](evidence/official-20261028/analysis.json)。这里仅保存论文所需摘要、来源哈希与审计说明；完整原始会话仍在本轮交付包和授权试验目录中。

## 编译与 Overleaf 同步

在根目录运行 `bash build.sh all` 编译两种语言；`bash build.sh pack` 生成可上传的源码包。需 TeX Live 的 IEEEtran、常用数学/图表宏包；双语稿还需 ctex 和 Noto CJK 字体。无需访问实验服务器或调用模型即可编译。

连接此 GitHub 仓库的 Overleaf 项目，需要在 **Integrations → GitHub → Pull changes from GitHub** 拉取。本次更新 GitHub 源码，不代表 Overleaf 项目已经自动拉取。

英文使用 IEEE conference 模板；作者与单位仍为占位符。投稿前应核对目标会议的最终要求和作者信息。

[完整源码说明与历史记录](source-notes.md) · [MAVRA 主仓库](https://github.com/mmmttt000045/agent4db-adapter)
'''.encode())

review=(HERE/'README.md').read_text(encoding='utf-8')
review=review.replace('本目录中的正文是审阅后的修订草稿，尚未集成或编译。','本次同步已将核验后的表述集成到正文；根目录编译入口共用该修订。')
review=review.replace('可使用本目录 `sharing-revision.tex`','修订已集成至 `sections/evaluation/sharing.tex`')
put('evidence/2026-10-29/README.md',review.encode())
j=json.loads((HERE/'lineage-audit.json').read_text(encoding='utf-8'))
keep=['dataset','task','k','source','tools','memory_outputs','decode_errors','validation_matches','final_sql_sha256','final_match','audit','final_source','validation_count','stop']
summary={k:v for k,v in j.items() if k!='sessions'}
summary['sessions']=[{k:r[k] for k in keep} for r in j['sessions']]
put('evidence/2026-10-29/lineage-summary.json',(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode())
for name in ['analysis.json','evidence-audit.json']:
    put('evidence/official-20261028/'+name,(ROOT/'results/official-20261028'/name).read_bytes())

files=[]
for p in sorted(DEST.rglob('*')):
    if not p.is_file(): continue
    rel=p.relative_to(DEST).as_posix()
    data=p.read_bytes()
    if p.suffix!='.pdf' and re.search(rb'sk-[A-Za-z0-9]{24,}|postgres(?:ql)?://[^\s/:]+:[^\s/@]+@',data):
        raise RuntimeError('Credential-like content in '+rel)
    blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    files.append({'path':rel,'sha':blob,'sha256':hashlib.sha256(data).hexdigest(),
                  'size':len(data),'mode':remote.get(rel,{}).get('mode','100644'),
                  'changed':remote.get(rel,{}).get('sha')!=blob,'binary':p.suffix=='.pdf'})
plan={'created_utc':datetime.now(timezone.utc).isoformat(),'repository':'mmmttt000045/icde-2027-paper',
      'branch':'main','expected_head':before['head'],'base_tree':before['tree'],
      'source_directory':str(DEST),'files':files,'preserve_remote_only':True,'deletions':[]}
(HERE/'github-sync-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with tarfile.open(ROOT/'tmp/paper-github-20261029.tar.gz','w:gz') as t:
    for f in files: t.add(DEST/f['path'],arcname=f['path'])
changed=[f for f in files if f['changed']]
print(json.dumps({'files':len(files),'changed':len(changed),'binary_changed':sum(f['binary'] for f in changed),
                  'paths':[f['path'] for f in changed]},ensure_ascii=False))
