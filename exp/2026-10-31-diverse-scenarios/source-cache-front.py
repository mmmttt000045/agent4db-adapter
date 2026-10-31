"""Restore paid source-session responses; only fresh extra questions reach the budget relay."""
import argparse,hashlib,json,threading,urllib.request,urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
class Cache:
    def __init__(self,plan,out,upstream):
        self.lock=threading.Lock();self.cells={};self.out=Path(out);self.out.mkdir(exist_ok=False);self.upstream=upstream
        for key,source in plan.items():
            journal=[json.loads(x) for x in (Path(source['root'])/'memory'/source['key']/'memory-events.jsonl').read_text().splitlines()]
            boundary=next(e['utc'] for e in journal if e['event']=='request' and e['request']['op']=='checkpoint')
            rows=[json.loads(x) for x in (Path(source['api_root'])/'budget/api-transcripts.jsonl').read_text().splitlines()]
            rows=[e for e in rows if e['arm']==source['key'] and e['utc']<=boundary and (source['arm']=='mavra' or e['request'].get('tools'))]
            assert rows and all(e['response']['model']=='deepseek-flash' for e in rows)
            self.cells[key]={'rows':rows,'index':0,'mode':'source','source':source}
        self.save()
    def save(self):
        public={key:{'cached_source_calls':len(v['rows']),'replayed_calls':v['index'],'mode':v['mode'],'source_key':v['source']['key']} for key,v in self.cells.items()}
        (self.out/'cache-state.json').write_text(json.dumps(public,indent=2)+'\n')
    def activate(self,key):
        with self.lock:
            cell=self.cells[key]
            assert cell['index']==len(cell['rows']),(key,'Source prefix not fully consumed',cell['index'],len(cell['rows']))
            cell['mode']='evaluation';self.save();return {'ok':True,'replayed_calls':cell['index']}
    def call(self,key,body,path):
        with self.lock:
            cell=self.cells[key]
            if cell['mode']=='source':
                assert cell['index']<len(cell['rows']),(key,'Attempted uncached source call')
                event=cell['rows'][cell['index']]
                assert bool(body.get('tools'))==bool(event['request'].get('tools')),(key,'Source call profile differs')
                assert body['model']==event['request']['model']=='deepseek-flash'
                cell['index']+=1;self.save()
                with (self.out/'cache-replay.jsonl').open('a') as f:
                    f.write(json.dumps({'key':key,'source_call':event['call'],'source_utc':event['utc'],
                        'source_response_sha256':hashlib.sha256(json.dumps(event['response'],sort_keys=True).encode()).hexdigest(),'new_official_api_charge':False})+'\n')
                return 200,json.dumps(event['response']).encode()
        raw=json.dumps(body).encode();request=urllib.request.Request(self.upstream+path,data=raw,headers={'Content-Type':'application/json','Authorization':'Bearer diverse-scenarios-20261031-local'})
        try:
            with urllib.request.urlopen(request,timeout=600) as response:return response.status,response.read()
        except urllib.error.HTTPError as error:return error.code,error.read()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def reply(self,status,raw):
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.reply(200,b'{"ok":true}')
    def do_POST(self):
        try:
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/activate':status,raw=200,json.dumps(self.server.cache.activate(body['key'])).encode()
            else:
                key=self.path.split('/arm/',1)[1].split('/')[0];status,raw=self.server.cache.call(key,body,self.path)
            self.reply(status,raw)
        except Exception as error:self.reply(500,json.dumps({'error':str(error),'cache_error':True}).encode())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--out',required=True);p.add_argument('--port',type=int,default=19432);p.add_argument('--upstream',default='http://127.0.0.1:19430');a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.cache=Cache(read(a.plan),a.out,a.upstream);server.serve_forever()
