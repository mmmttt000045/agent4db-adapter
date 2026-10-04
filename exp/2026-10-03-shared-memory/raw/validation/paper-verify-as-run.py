from pathlib import Path
import subprocess,re,json,hashlib
root=Path('/root/agentdb-shared-memory-20261003/overleaf')
report={}
for stem in ['main-en','main','main-en-details','main-details']:
    p=root/'build'/(stem+'.pdf');log=(root/'build'/(stem+'.log')).read_text(errors='replace')
    text=subprocess.check_output(['pdftotext','-layout',str(p),'-']).decode()
    pages=text.split('\f')
    refs=[i+1 for i,t in enumerate(pages) if re.search(r'^\s*(?:\d+\s+)?References\b',t,re.M)]
    record={'pages':int(re.search(r'Output written on .*?\((\d+) pages',log).group(1)),
        'references_begin_page':min(refs),
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'overfull_hbox':len(re.findall(r'Overfull \\hbox',log)),
        'overfull_vbox':len(re.findall(r'Overfull \\vbox',log)),
        'undefined_citations_or_references':len(re.findall(r'(?:Citation|Reference).*undefined|There were undefined',log)),
        'missing_glyphs':len(re.findall('Missing character:',log)),
        'headline_percentages_present':all(v in text for v in ['24.4%','27.7%','18.9%']),
        'visual_review':'English architecture, main results, conclusion/references; bilingual results and extended pages inspected separately.'}
    assert record['overfull_hbox']==0 and record['undefined_citations_or_references']==0 and record['missing_glyphs']==0
    assert record['headline_percentages_present']
    if stem in ['main-en','main']:assert record['overfull_vbox']==0
    if stem=='main-en':assert record['references_begin_page']<=12
    report[stem]=record
Path('/tmp/mavra-paper-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
