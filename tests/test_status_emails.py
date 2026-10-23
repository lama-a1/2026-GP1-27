# check the case status emails (sent only when the user turned them on)
import os,tempfile,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH',str(Path(tempfile.gettempdir())/('siyaq_test_'+str(os.getpid())+'.db')))
os.environ.setdefault('SECRET_KEY','test-only-secret')
os.environ.setdefault('OTP_MODE','demo')
import app as module
from app import app

def csrf(c):
    with c.session_transaction() as s:return s['csrf']

import factory

def make_user(db,name,notify=1):
    return factory.make_party(db,name,notify=notify)

def make_case(db,a_id,b_id=None):
    # both parties are at the review step, each with a car; party A has a video
    cid=factory.make_case(db,a_id,b_id,accident_type='LANE_CHANGE',progress=5,with_vehicles=True)
    factory.add_video(db,cid,a_id,uuid.uuid4().hex+'.mp4')
    return cid,cid

def submit(client,uid,cid):
    with client.session_transaction() as sess: sess['uid']=uid
    client.get('/cases/'+str(cid)+'/steps/6')
    return client.post('/cases/'+str(cid)+'/steps/6',data={'csrf_token':csrf(client),'consent':'yes'})

def test_both_parties_get_email_when_case_is_in_review(monkeypatch):
    app.config['TESTING']=True
    sent=[]
    monkeypatch.setattr(module,'send_status_email',lambda email,kind,ref,link: sent.append((email,kind,ref)))
    with module.conn() as db:
        a_id,a_email=make_user(db,'first')
        b_id,b_email=make_user(db,'second')
        cid,ref=make_case(db,a_id,b_id)
    monkeypatch.setenv('OTP_MODE','api')
    with app.test_client() as client:
        assert submit(client,a_id,cid).status_code==302
        assert sent==[]  # only one party submitted, no email yet
        assert submit(client,b_id,cid).status_code==302
    assert sorted(sent)==sorted([(a_email,'in_progress',ref),(b_email,'in_progress',ref)])

def test_no_email_when_notifications_are_off(monkeypatch):
    app.config['TESTING']=True
    sent=[]
    monkeypatch.setattr(module,'send_status_email',lambda email,kind,ref,link: sent.append(email))
    with module.conn() as db:
        a_id,a_email=make_user(db,'first',notify=0)
        b_id,b_email=make_user(db,'second')
        cid,ref=make_case(db,a_id,b_id)
    monkeypatch.setenv('OTP_MODE','api')
    with app.test_client() as client:
        submit(client,a_id,cid); submit(client,b_id,cid)
    assert sent==[b_email]

def test_failed_email_does_not_stop_submitting(monkeypatch):
    app.config['TESTING']=True
    def fail(*args): raise RuntimeError('Delivery failed')
    monkeypatch.setattr(module,'send_status_email',fail)
    with module.conn() as db:
        a_id,_=make_user(db,'first')
        b_id,_=make_user(db,'second')
        cid,_=make_case(db,a_id,b_id)
    monkeypatch.setenv('OTP_MODE','api')
    with app.test_client() as client:
        submit(client,a_id,cid)
        assert submit(client,b_id,cid).status_code==302
    with module.conn() as db:
        assert db.execute('SELECT status FROM accident_case WHERE case_id=?',(cid,)).fetchone()['status']=='in_progress'

def test_first_party_gets_email_when_second_party_joins(monkeypatch):
    app.config['TESTING']=True
    sent=[]
    monkeypatch.setattr(module,'send_status_email',lambda email,kind,ref,link: sent.append((email,kind)))
    monkeypatch.setattr(module,'send_case_invitation',lambda email,link,reference: invites.append(link))
    invites=[]
    monkeypatch.setenv('PUBLIC_BASE_URL','https://siyaq.example')
    with module.conn() as db:
        a_id,a_email=make_user(db,'first')
        b_id,b_email=make_user(db,'second')
        cid=factory.make_case(db,a_id,progress=6)
        db.execute('UPDATE participation_progress SET completed=1 WHERE case_id=?',(cid,))
    monkeypatch.setenv('OTP_MODE','api')
    with app.test_client() as creator:
        with creator.session_transaction() as sess: sess['uid']=a_id
        creator.get('/cases/'+str(cid)+'/steps/7')
        creator.post('/cases/'+str(cid)+'/invite',data={'csrf_token':csrf(creator),'recipient_email':b_email})
    path='/'+invites[0].split('://',1)[1].split('/',1)[1]
    with app.test_client() as other:
        with other.session_transaction() as sess: sess['uid']=b_id
        other.get(path)
        assert other.post(path+'/accept',data={'csrf_token':csrf(other)}).status_code==302
    assert sent==[(a_email,'joined')]
