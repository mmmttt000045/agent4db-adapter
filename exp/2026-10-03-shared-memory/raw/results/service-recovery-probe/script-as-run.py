from pathlib import Path
import concurrent.futures, json, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
v={}
for line in Path('.env').read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        k,x=line.split('=',1);v[k]=x.strip().strip(chr(34)).strip(chr(39))
settings=[('kunyou','KUNYOU',v['KUNYOU_MODEL'],v['KUNYOU_BASE_URL']),
          ('official','OPENAI','deepseek-v4.1-flash',v['OPENAI_BASE_URL']),
          ('cline-pass','CLINE','cline-pass/deepseek-v4.1-flash','https://api.cline.bot/api/v1')]
def probe(setting):
    name,prefix,model,base=setting
    headers={'Authorization':'Bearer '+v[prefix+'_API_KEY'],'Content-Type':'application/json','User-Agent':'agentdb-mid/0.1.0'}
    if prefix=='CLINE':headers['x-client-type']='cline-cli'
    body={'model':model,'messages':[{'role':'user','content':'Reply OK.'}],'max_tokens':128,'reasoning_effort':'high'}
    req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(body).encode(),headers=headers)
    record={'service':name,'requested_model':model,'host':urllib.parse.urlparse(base).hostname,'utc':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            x=json.load(response)
        if isinstance(x.get('data'),dict):x=x['data']
        record.update(status=200,served_model=x.get('model'),usage=x.get('usage'),finish_reason=x.get('choices',[{}])[0].get('finish_reason'))
    except urllib.error.HTTPError as e:
        record.update(status=e.code,error=e.read().decode(errors='replace')[:1200].replace(v[prefix+'_API_KEY'],'[REDACTED]'))
    except (urllib.error.URLError,TimeoutError) as e:
        record.update(status='connection-error',error=type(e).__name__)
    print(json.dumps(record,ensure_ascii=False),flush=True)
    return record
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
    results=list(ex.map(probe,settings))
p=Path('results/service-recovery-probe');p.mkdir(exist_ok=True)
(p/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
