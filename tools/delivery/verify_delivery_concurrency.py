"""Dedicated live SQL rehearsal; scope none, synthetic rows removed in finally."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
PROJECT = 'xtvueqciogzkyjkkqxcx'

def query(sql):
    p = subprocess.run(['supabase','db','query','--linked','--project-ref',PROJECT,'--output','json',sql],capture_output=True,text=True)
    if p.returncode: raise RuntimeError(p.stderr[-1500:])
    return json.loads(p.stdout)['rows']

def literal(v): return "'"+str(v).replace("'","''")+"'"
def call(name,*args):
    return query('select public.'+name+'('+','.join(literal(x) for x in args)+') result')[0]['result']

def run(output):
    ids=[]; results=[]
    assert query('select count(*) n from delivery_control')[0]['n']==0, 'Requires empty v2'
    try:
        for scenario in ['duplicate_accept','reject_wins','accept_wins','two_workers']:
            cid='delivery-'+uuid.uuid4().hex;ids.append(cid)
            c=dict(id=cid,repository='israelhudson/flutter_code_push_example',version='99.0.0',rc_number=1,rc_tag='poc-v99.0.0-rc.1',source_sha='a'*40,manifest_commit='b'*40,manifest_digest='c'*64,team_id='T09CYB7AS77',channel_id='C0C8DUJB52L',technical_user='UTECH',business_user='UBIZ',solo=False,scope='none')
            call('delivery_register',json.dumps(c))
            query(f"update delivery_control set technical_channel='DTECH',technical_message='100.1',business_channel='DBIZ',business_message='100.2' where id={literal(cid)}")
            def vote(role,action):
                return 'select delivery_decide('+','.join(map(literal,[cid,role,action,'UTECH' if role=='technical' else 'UBIZ','T09CYB7AS77','DTECH' if role=='technical' else 'DBIZ','100.1' if role=='technical' else '100.2']))+')'
            if scenario=='two_workers':
                commands=["select delivery_take("+literal(str(uuid.uuid4()))+") result" for _ in range(2)]
            else:
                if scenario in ('reject_wins','accept_wins'):query(vote('technical','accept'))
                first=vote('business','reject' if scenario=='reject_wins' else 'accept') if scenario!='duplicate_accept' else vote('technical','accept')
                second=vote('business','accept' if scenario=='reject_wins' else 'reject') if scenario!='duplicate_accept' else vote('technical','accept')
                commands=[f'begin; {first}; select pg_sleep(5); commit;',second]
            start=time.monotonic()
            def execute(sql):
                try:return dict(ok=True,rows=query(sql))
                except RuntimeError as e:return dict(ok=False,error=str(e))
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                a=pool.submit(execute,commands[0]);time.sleep(1);b=pool.submit(execute,commands[1]); pair=[a.result(),b.result()]
            state=call('delivery_state',cid)
            if scenario=='two_workers':
                assert all(x['ok'] for x in pair),pair
                taskids=[x['rows'][0]['result']['task']['id'] for x in pair]
                assert len(set(taskids))==2
            else:
                assert pair[0]['ok'],pair
                assert pair[1]['ok']==(scenario=='duplicate_accept'),pair
                assert state['status']=={'duplicate_accept':'pending','reject_wins':'rejected','accept_wins':'approved'}[scenario]
                assert state['revision']==(1 if scenario=='duplicate_accept' else 2)
            assert query("select count(*) n from delivery_outbox where kind='dispatch'")[0]['n']==0
            results.append(dict(scenario=scenario,passed=True,status=state['status'],revision=state['revision'],seconds=round(time.monotonic()-start,2),calls=pair))
            query(f'delete from delivery_outbox where candidate_id={literal(cid)}; delete from delivery_control where id={literal(cid)};')
    finally:
        if ids:
            targets=','.join(map(literal,ids))
            query(f'delete from delivery_outbox where candidate_id in ({targets}); delete from delivery_control where id in ({targets});')
        Path(output).write_text(json.dumps({'tests':results,'remaining':query('select (select count(*) from delivery_control) controls,(select count(*) from delivery_outbox) outbox')},indent=2)+'\n')
    print(json.dumps({'passed':len(results),'synthetic_controls_removed':True}))
if __name__=='__main__':run(sys.argv[1])
