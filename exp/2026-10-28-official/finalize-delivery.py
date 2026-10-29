"""Freeze local delivery evidence and package completed, reviewed artifacts (no API calls)."""
import hashlib
import json
import pathlib
import re
import zipfile
from datetime import datetime, timezone
from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXP = ROOT / 'exp/2026-10-28-official'
RESULTS = ROOT / 'results/official-20261028'
OUT = ROOT / 'output/pdf'
now = datetime.now(timezone.utc).isoformat()

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def save(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

names = ['mavra-official-report-zh', 'mavra-paper-en', 'mavra-paper-bilingual',
         'fig5-reuse-work-en', 'fig5-reuse-work-zh', 'fig3-cumulative-en', 'fig3-cumulative-zh']
pdfs = [OUT / (n + '.pdf') for n in names]
assert json.loads((RESULTS/'expenses.json').read_text())['final']
assert json.loads((RESULTS/'evidence-audit.json').read_text())['complete']
qa = {'verified_utc': now, 'status': 'complete; compiled and visually reviewed',
      'pdfs': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'pages': len(PdfReader(p).pages)} for p in pdfs],
      'review': {'report_pages': [1,2,3,4,5,6], 'english_paper_pages': [1,8,9,10,12,13],
                 'bilingual_paper_pages': [1,13,14,16], 'standalone_figures': 'both languages reviewed',
                 'english_body_last_page': 12, 'english_references_first_page': 13,
                 'compiler': 'remote TeX Live; latexmk PDF and XeLaTeX, exit 0; no undefined references or overfull boxes'},
      'evidence_sha256': {n: sha(RESULTS/n) for n in ['analysis.json','evidence-audit.json','expenses.json','closing-balance.json']},
      'formal_sessions': 90, 'formal_sequences': 10, 'official_requests': 1669,
      'account_charge_cny': 14.63, 'usage_charge_cny': 14.62816972, 'authorized_budget_cny': 50,
      'limitations': ['One sequence per method/database, no independent repeats or confidence interval.',
                     'MAVRA passes 5/6 full-sequence quality margins; study-adverse MAE is 3.3% higher than no memory.',
                     'No explicit feature-composition calls; end-to-end savings cannot isolate feature composition.',
                     'Historical gateway studies remain separate from official-API results.']}
save(EXP/'delivery-verification.json', qa)
integration = json.loads((EXP/'integration-audit.json').read_text())
integration.update(status=qa['status'], final_review_utc=now, verification_file='delivery-verification.json')
save(EXP/'integration-audit.json', integration)
readme = EXP/'README.md'
text = readme.read_text(encoding='utf-8')
start = text.index('状态（')
end = text.index('\n\n', start)
text = text[:start] + ('状态（最终交付，北京时间2026-10-29 04:16）：10个正式序列、90个会话及最终评分全部完成，完整性审计通过。'
    '实际账户扣款14.63元，官方用量重算14.62816972元，低于50元授权。全部模型调用已在03:49:31前结束，专用代理、排队和汇总进程已关闭；STOP阻止新增调用。'
    '新主表、Fig.3累计图和Fig.5机制图已集成至overleaf正文；英文15页（正文至12页）、双语22页，编译及目视检查完成。'
    '以下跟进条目保留为按时间记录的历史，不代表仍有未完成实验。') + text[end:]
text += ('\n\n## 最终交付\n\n'
         '- `output/pdf/mavra-official-report-zh.pdf`：6页中文报告，覆盖全方法结果、质量限制、机制、费用与审计。\n'
         '- `output/pdf/mavra-paper-en.pdf`、`mavra-paper-bilingual.pdf`：已集成并编译的完整稿件。\n'
         '- `output/pdf/fig5-reuse-work-{en,zh}.pdf`：减少探索与保留验证的机制分解。\n'
         '- `output/pdf/fig3-cumulative-{en,zh}.pdf`：含记忆学习的累计开销；相同名称PNG可预览。\n'
         '- `output/mavra-official-delivery.zip`：最终PDF、图片、稿件源码、实验方案、代码及完整原始结果。\n'
         '- `delivery-verification.json`、`integration-audit.json`：最终文件哈希、版面检查与集成备份。\n\n'
         '相对无记忆，MAVRA在rel-stack/rel-trial总token减少31.8%/32.4%，复用阶段减少66.2%/54.6%。'
         '全序列5/6任务满足预定质量门槛；study-adverse的MAE高3.3%。将全部0.669M开发token计入MAVRA，合并两库仍少21.3%。'
         '仅完成每方法每库一条序列，不声称显著性或普遍质量优势；没有显式特征组合调用，不将收益独归于特征重组。\n')
readme.write_text(text, encoding='utf-8')
amend = json.loads((EXP/'amendments.json').read_text())
amend.append({'recorded_utc': now, 'changes': ['Completed all frozen formal evaluations; reconciled all 1669 responses and 90 formal sessions. Closed model calls and saved closing balance.',
    'Integrated complete published-method results, archived unused ad hoc baseline figures with original evidence retained, compiled both manuscripts and reviewed final layouts. No model or test-driven configuration changes.',
    'Delivered complete study with quality regressions, missing independent repetitions and mechanism limitations explicit.'],
    'files': {n: sha(EXP/n) for n in ['close-study.py','build-delivery-report.py','build-figures.py','delivery-verification.json','integration-audit.json']}})
save(EXP/'amendments.json', amend)

files = set(pdfs)
files.update(OUT/(n+'.png') for n in names[3:])
files.add(OUT/'mavra-official-report-zh.json')
for base, suffixes in [(EXP,{'.py','.json','.md','.tex','.pdf'}),
                       (ROOT/'overleaf',{'.tex','.pdf','.bib','.bst','.cls','.sty'}),
                       (RESULTS,{'.json','.jsonl','.md','.log','.txt',''})]:
    for p in base.rglob('*'):
        if p.is_file() and not p.is_symlink() and p.suffix.lower() in suffixes and not any(x in ('build','__pycache__','.git') for x in p.relative_to(base).parts):
            files.add(p)
secret = re.compile(rb'sk-[A-Za-z0-9]{24,}|postgres(?:ql)?://[^\s/:]+:[^\s/@]+@')
for p in files:
    if p.suffix.lower() not in ('.pdf','.png') and secret.search(p.read_bytes()):
        raise RuntimeError('Credential-like content requires inspection: '+str(p.relative_to(ROOT)))
manifest = {'created_utc': now, 'files': {str(p.relative_to(ROOT)).replace('\\','/'): sha(p) for p in sorted(files)}}
save(ROOT/'output/mavra-official-delivery-manifest.json', manifest)
archive = ROOT/'output/mavra-official-delivery.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files): z.write(p, p.relative_to(ROOT).as_posix())
    z.write(ROOT/'output/mavra-official-delivery-manifest.json','delivery-manifest.json')
print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256':sha(archive), 'files':len(files), 'pdfs':qa['pdfs']},ensure_ascii=False))
