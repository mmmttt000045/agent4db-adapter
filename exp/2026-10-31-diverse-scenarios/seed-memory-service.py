"""Restore exact earlier post-heldout memories; source warmup is never newly scored."""
import argparse,copy,importlib.util,json,os,shutil,urllib.request
from pathlib import Path
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('memory_service',HERE/'memory-service.py');service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
PLANS={};FRONT='http://127.0.0.1:19432'

class SeededActor(service.Actor):
    def __init__(self,key,arm,directory,proxy,model):
        super().__init__(key,arm,directory,proxy,model)
        self.seed=PLANS[key];self.source_root=Path(self.seed['root']);source=self.source_root/'memory'/self.seed['key']
        raw=[json.loads(x) for x in (source/'memory-events.jsonl').read_text().splitlines()];pending={};self.prefix=[]
        for e in raw:
            if e['event']=='request':pending[e['index']]=e;continue
            request=pending.pop(e['index'])['request']
            self.prefix.append((request,e['response']))
            if request['op']=='checkpoint':break
        assert self.prefix[-1][0]['op']=='checkpoint'
        self.cursor=0;self.warmup=True;self.original_source=source
        self.feedback_agent='A'
        self.actor.timeline={'K':32 if key.startswith('synthetic-') else 26}
    def expected(self,req):
        old,response=self.prefix[self.cursor];self.cursor+=1
        assert old['op']==req['op']
        for field in ('phase','task','metric','agent','ask','question'):
            if field in old:assert old[field]==req[field],(self.key,field)
        if req['op']=='end':
            assert req.get('answer')==old.get('answer') and bool(req['correct'])==bool(old['correct'])
            actions=lambda r:[(e['tool'],e.get('input')) for e in r['transcript'] if e.get('kind','tool')=='tool' and e.get('tool')]
            assert actions(req)==actions(old),(self.key,'Replayed source actions differ')
        return old,copy.deepcopy(response)
    def begin(self,req):
        if not self.warmup:
            if req['agent']!=self.feedback_agent:
                self.feedback=[];self.feedback_agent=req['agent']
            return super().begin(req)
        _,response=self.expected(req)
        return super().begin(req) if self.arm=='mavra' else response
    def end(self,req):
        if not self.warmup:return super().end(req)
        _,response=self.expected(req)
        return super().end(req) if self.arm=='mavra' else response
    def load_control(self):
        ends=[q for q,_ in self.prefix if q['op']=='end'];assert len(ends)==9
        self.k=0;self.feedback=[]
        for req in ends:
            self.k+=1;t=req['metric'];agent=req['agent'];period=req['ask']['period'];cutoff=f"{period['year']:04}-{period['m1']:02}-01"
            entry=self.actor.tasks.setdefault(t,{'cutoffs':[]})
            while len(entry['cutoffs'])<self.k:entry['cutoffs'].append({'test_timestamp':cutoff})
            entry['cutoffs'][self.k-1]={'test_timestamp':cutoff};self.actor.task_desc[t]={'description':req['question']};self.actor.refs[(t,self.k)]={'val':.5}
            if self.arm=='awm' and req['correct']:self.actor.awm_pool.setdefault(agent,[]).append(self.actor.awm_experience(t,self.k,service.messages(req)))
            observations=[{'tool':e['tool'],'output':e['output'][:350]} for e in req['transcript'] if e.get('kind')=='tool' and e['tool']=='run_sql'][-3:]
            self.feedback=(self.feedback+[{'question':req['question'],'own_answer':req.get('answer'),'correct':bool(req['correct']),
                'own_sql':(req.get('sql') or '')[:1800],'own_observations':observations}])[-3:]
        if self.arm=='ace':
            self.actor.playbooks['A']=(self.original_source/'branch-000/playbooks/A-k9.txt').read_text();self.actor.ace_steps['A']=9
        if self.arm=='awm':self.actor.awm_workflows['A']=(self.original_source/'branch-000/workflows/A-k9.txt').read_text()
        if self.arm=='gmemory':shutil.copytree(self.original_source/'post-heldout-gmemory',self.branch/'gmemory')
        self.active=None
    def checkpoint(self):
        if not self.warmup:return super().checkpoint()
        old,response=self.expected({'op':'checkpoint'})
        assert self.cursor==len(self.prefix)
        if self.arm!='mavra':self.load_control()
        assert self.k==9
        result=super().checkpoint()
        raw=json.dumps({'key':self.key}).encode();reply=json.load(urllib.request.urlopen(urllib.request.Request(FRONT+'/activate',data=raw,headers={'Content-Type':'application/json'}),timeout=10))
        assert reply['ok'];self.warmup=False
        (self.root/'seed-restoration.json').write_text(json.dumps({'source':self.seed,'source_tasks':9,'restored_k':self.k,'replayed_api_calls':reply['replayed_calls'],
            'new_api_calls_for_source':0,'utc':datetime.now(timezone.utc).isoformat(),'warmup_actions_answers_and_labels_match_source':True},indent=2)+'\n')
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--out',required=True);p.add_argument('--port',type=int,default=19431);p.add_argument('--proxy',default='http://127.0.0.1:19432');p.add_argument('--front',default='http://127.0.0.1:19432');p.add_argument('--model',default='deepseek-flash');a=p.parse_args()
    PLANS=json.loads(Path(a.plan).read_text());FRONT=a.front;service.Actor=SeededActor
    server=service.ThreadingHTTPServer(('127.0.0.1',a.port),service.Handler);server.actors={};server.registry_lock=service.threading.Lock();server.args=a;server.serve_forever()
