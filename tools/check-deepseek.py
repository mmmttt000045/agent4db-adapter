"""One minimal official DeepSeek call; never print credentials or reasoning content."""
import json
from pathlib import Path
import urllib.error
import urllib.request

root=Path(__file__).resolve().parents[1]
config={}
for line in (root/'.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k,v=line.split('=',1)
        config[k.strip()]=v.strip().strip('\"\'')
base=config['OPENAI_BASE_URL'].rstrip('/')
if base not in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
    raise SystemExit('This smoke check only sends credentials to the official DeepSeek API.')
body={'model':config['OPENAI_MODEL'],'messages':[{'role':'user','content':'Reply with exactly OK.'}],
      'reasoning_effort':config['OPENAI_REASONING_EFFORT'],
      'thinking':{'type':config['OPENAI_THINKING']},'max_tokens':512}
req=urllib.request.Request(base+'/chat/completions',data=json.dumps(body).encode(),
    headers={'Authorization':'Bearer '+config['OPENAI_API_KEY'],'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(req,timeout=90) as response:
        result=json.load(response)
except urllib.error.HTTPError as e:
    print(json.dumps({'http_status':e.code,'error':e.read().decode(errors='replace').replace(config['OPENAI_API_KEY'],'[REDACTED]')[:500]}))
    raise SystemExit(1)
except (urllib.error.URLError,TimeoutError):
    raise SystemExit('Connection failed or timed out; credentials were not printed.')
choice=result.get('choices',[{}])[0]
print(json.dumps({'model':result.get('model'),'requested_effort':body['reasoning_effort'],
    'finish_reason':choice.get('finish_reason'),'reply':choice.get('message',{}).get('content'),
    'usage':result.get('usage')},ensure_ascii=False))
if choice.get('finish_reason')!='stop' or (choice.get('message',{}).get('content') or '').strip()!='OK':
    raise SystemExit('Response received but the minimal check did not complete as expected.')
