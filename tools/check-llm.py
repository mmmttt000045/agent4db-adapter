"""Minimal official-API smoke check for one provider profile: a plain reply plus one tool round trip.

Usage: python tools/check-llm.py deepseek|zhipu|openai
Reads <PREFIX>_* from .env (process environment wins); never prints credentials or reasoning content.
"""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

PROFILES={'openai':('OPENAI','https://api.openai.com/v1'),'deepseek':('DEEPSEEK','https://api.deepseek.com'),
          'zhipu':('ZHIPU','https://open.bigmodel.cn/api/paas/v4')}
OFFICIAL={'api.openai.com','api.deepseek.com','open.bigmodel.cn'}
# Same rule as src/llm.rs: these thinking modes need reasoning_content sent back during tool calls.
KEEP_REASONING={'api.deepseek.com','open.bigmodel.cn'}

if len(sys.argv)!=2 or sys.argv[1] not in PROFILES:
    raise SystemExit('Usage: python tools/check-llm.py '+'|'.join(PROFILES))
prefix,default_base=PROFILES[sys.argv[1]]
root=Path(__file__).resolve().parents[1]
config={}
if (root/'.env').exists():
    for line in (root/'.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1)
            config[k.strip()]=v.strip().strip('\"\'')
config.update({k:v for k,v in os.environ.items() if v})
get=lambda k:config.get(f'{prefix}_{k}') or None
key,model=get('API_KEY'),get('MODEL')
if not key or not model:
    raise SystemExit(f'Set {prefix}_API_KEY and {prefix}_MODEL in .env.')
base=(get('BASE_URL') or default_base).rstrip('/')
host=urllib.parse.urlparse(base).hostname
if host not in OFFICIAL:
    raise SystemExit('This smoke check only sends credentials to official APIs: '+', '.join(sorted(OFFICIAL)))
extra={'max_tokens':8192}
if get('REASONING_EFFORT'): extra['reasoning_effort']=get('REASONING_EFFORT')
if get('THINKING'): extra['thinking']={'type':get('THINKING')}

def chat(messages,tools=None):
    body={'model':model,'messages':messages,**extra}
    if tools: body['tools']=tools
    req=urllib.request.Request(base+'/chat/completions',data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=300) as response:
            result=json.load(response)
    except urllib.error.HTTPError as e:
        print(json.dumps({'http_status':e.code,'error':e.read().decode(errors='replace').replace(key,'[REDACTED]')[:500]},ensure_ascii=False))
        raise SystemExit(1)
    except (urllib.error.URLError,TimeoutError):
        raise SystemExit('Connection failed or timed out; credentials were not printed.')
    choice=result.get('choices',[{}])[0]
    message=choice.get('message',{})
    print(json.dumps({'model':result.get('model'),'finish_reason':choice.get('finish_reason'),'reply':message.get('content'),
        'tool_calls':[c.get('function',{}).get('name') for c in message.get('tool_calls') or []],
        'usage':result.get('usage')},ensure_ascii=False))
    return choice.get('finish_reason'),message

finish,message=chat([{'role':'user','content':'Reply with exactly OK.'}])
if finish!='stop' or (message.get('content') or '').strip().strip('.').upper()!='OK':
    raise SystemExit('Plain reply check did not complete as expected.')
tools=[{'type':'function','function':{'name':'get_number','description':'Return the secret number.',
        'parameters':{'type':'object','properties':{}}}}]
messages=[{'role':'user','content':'Call get_number, then reply with only the number it returned.'}]
finish,message=chat(messages,tools)
calls=message.get('tool_calls') or []
if not calls:
    raise SystemExit('Tool call check did not complete as expected.')
if host not in KEEP_REASONING: message.pop('reasoning_content',None)
messages+=[message]+[{'role':'tool','tool_call_id':c['id'],'content':'42'} for c in calls]
finish,message=chat(messages,tools)
if finish!='stop' or '42' not in (message.get('content') or ''):
    raise SystemExit('Tool result check did not complete as expected.')
