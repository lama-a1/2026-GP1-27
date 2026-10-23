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

def make_user(db,name,notify=1):
    tag=uuid.uuid4().hex[:9]
    email=name+tag+'@example.com'
    digits=str(int(tag,16))[-8:].zfill(8)
    db.execute('INSERT INTO users(full_name,email,phone,password_hash,national_id,notification_status) VALUES(?,?,?,?,?,?)',
               (name,email,'05'+digits,'hash','1'+digits+'0',notify))
    return db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()['id'],email

def make_case(db,a_id,b_id=None):
    ref='STATUS-'+uuid.uuid4().hex[:8]
    db.execute('INSERT INTO cases(reference,creator_id,accident_type,accident_date,accident_time,location) VALUES(?,?,?,?,?,?)',
               (ref,a_id,'LANE_CHANGE','2026-10-16','11:00','الرياض'))
    cid=db.execute('SELECT id FROM cases WHERE reference=?',(ref,)).fetchone()['id']
    db.execute("INSERT INTO parties(case_id,user_id,position,full_name,progress) VALUES(?,?,?,?,?)",(cid,a_id,'A','A',5))
    db.execute("INSERT INTO parties(case_id,user_id,position,full_name,progress) VALUES(?,?,?,?,?)",(cid,b_id,'B','B',5))
    party_a=db.execute("SELECT id FROM parties WHERE case_id=? AND position='A'",(cid,)).fetchone()['id']
    db.execute('INSERT INTO videos(case_id,party_id,original_name,stored_name) VALUES(?,?,?,?)',(cid,party_a,'a.mp4',uuid.uuid4().hex+'.mp4'))
    return cid,ref

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
        assert db.execute('SELECT status FROM cases WHERE id=?',(cid,)).fetchone()['status']=='in_progress'

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
        cid,_=make_case(db,a_id,None)
    monkeypatch.setenv('OTP_MODE','api')
    with app.test_client() as creator:
        with creator.session_transaction() as sess: sess['uid']=a_id
        creator.get('/cases/'+str(cid)+'/steps/1')
        creator.post('/cases/'+str(cid)+'/invite',data={'csrf_token':csrf(creator),'recipient_email':b_email})
    path='/'+invites[0].split('://',1)[1].split('/',1)[1]
    with app.test_client() as other:
        with other.session_transaction() as sess: sess['uid']=b_id
        other.get(path)
        assert other.post(path+'/accept',data={'csrf_token':csrf(other)}).status_code==302
    assert sent==[(a_email,'joined')]
