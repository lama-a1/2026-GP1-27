"""Run with: python -m pytest -q (after installing requirements and pytest)."""
import os,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_PATH']=str(Path(tempfile.gettempdir())/('siyaq_test_'+str(os.getpid())+'.db'))
os.environ['SECRET_KEY']='test-only-secret'
os.environ['OTP_MODE']='demo'
from app import app

def csrf(c):
    with c.session_transaction() as s:return s['csrf']

def register(c,nid='1023456789',phone='0551234567'):
    c.get('/register')
    r=c.post('/register',data={'csrf_token':csrf(c),'full_name':'Test User','national_id':nid,'birth_date':'2000-01-01','phone':phone,'email':'test'+nid+'@example.com','password':'password123','confirm_password':'password123'},follow_redirects=True)
    assert r.status_code==200
    with c.session_transaction() as sess: code=sess['pending_registration']['demo_code']
    assert c.post('/verify-email',data={'csrf_token':csrf(c),'code':'000000' if code!='000000' else '999999','action':'verify'}).status_code==200
    return c.post('/verify-email',data={'csrf_token':csrf(c),'code':code,'action':'verify'},follow_redirects=True)

def test_home_and_health():
    app.config['TESTING']=True
    with app.test_client() as c:
        assert c.get('/').status_code==200
        assert c.get('/health').json['database']=='connected'

def test_registration_profile_vehicle_and_case():
    app.config['TESTING']=True
    with app.test_client() as c:
        r=register(c)
        assert r.status_code==200
        assert 'مرحبًا'.encode() in r.data
        assert c.get('/profile?tab=vehicles').status_code==200
        r=c.post('/profile/vehicles',data={'csrf_token':csrf(c),'manufacturer':'تويوتا','model':'كامري','plate':'أ ب ج 1234','year':'2023','color':'أبيض'},follow_redirects=True)
        assert 'كامري'.encode() in r.data
        r=c.post('/cases/new',data={'csrf_token':csrf(c),'no_injuries':'yes','daylight':'yes','clear_weather':'yes','two_vehicles':'yes','accident_type':'REAR_END','vehicle_role':'REAR','accident_date':'2026-10-16','accident_time':'10:28','location':'الرياض'},follow_redirects=True)
        assert r.status_code==200 and b'SQ-' in r.data

def test_csrf_rejection():
    app.config['TESTING']=True
    with app.test_client() as c:assert c.post('/login',data={'national_id':'1023456789','password':'bad'}).status_code==400

def test_email_otp_uses_real_smtp_sender_when_configured(monkeypatch):
    import app as module
    sent=[]
    monkeypatch.setenv('OTP_MODE','smtp')
    monkeypatch.setattr(module,'send_email_otp',lambda email,code: sent.append((email,code)))
    with app.test_request_context('/register',environ_base={'REMOTE_ADDR':'127.0.0.1'}):
        pending=module.issue_otp({'email':'tester@example.com'})
    assert len(sent)==1 and sent[0][0]=='tester@example.com'
    assert len(sent[0][1])==6 and sent[0][1].isdigit()
    assert 'demo_code' not in pending
    assert pending['otp_digest']==module.otp_digest(sent[0][1],'tester@example.com')

def test_email_invitation_is_targeted_single_use_and_private(monkeypatch):
    import app as module
    from urllib.parse import urlparse
    app.config['TESTING']=True
    monkeypatch.setenv('PUBLIC_BASE_URL','https://siyaq.example')
    delivered=[]
    monkeypatch.setattr(module,'send_case_invitation',lambda email,link,reference: delivered.append((email,link,reference)))
    with app.test_client() as creator:
        creator.get('/login')
        with module.conn() as db:
            email='creator'+str(os.getpid())+'@example.com'
            db.execute('INSERT OR IGNORE INTO users(full_name,email,phone,password_hash,national_id) VALUES(?,?,?,?,?)',
                       ('Creator',email,'0551234567','hash','1'+str(os.getpid()).zfill(9)[-9:]))
            uid=db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()['id']
            ref='INVITE-'+str(os.getpid())
            db.execute('INSERT OR IGNORE INTO cases(reference,creator_id,accident_type,accident_date,accident_time,location) VALUES(?,?,?,?,?,?)',
                       (ref,uid,'REAR_END','2026-10-16','11:00','الرياض'))
            case_id=db.execute('SELECT id FROM cases WHERE reference=?',(ref,)).fetchone()['id']
            db.execute("INSERT OR IGNORE INTO parties(case_id,user_id,position,full_name) VALUES(?,?,?,?)",(case_id,uid,'A','Creator'))
            db.execute("INSERT OR IGNORE INTO parties(case_id,position) VALUES(?,?)",(case_id,'B'))
        with creator.session_transaction() as sess: sess['uid']=uid
        page=creator.get('/cases/'+str(case_id))
        assert page.status_code == 302 and '/steps/1' in page.location
        target='second'+str(os.getpid())+'@example.com'
        response=creator.post('/cases/'+str(case_id)+'/invite',data={'csrf_token':csrf(creator),'recipient_email':target.upper()})
        assert response.status_code==302
        assert delivered and delivered[0][0]==target
        assert delivered[0][2]==ref
        link=urlparse(delivered[0][1]).path
        assert creator.get(link).status_code==200
        assert b'Creator' not in creator.get(link).data
        assert creator.post(link+'/accept',data={'csrf_token':csrf(creator)}).status_code==403
    with app.test_client() as other:
        other.get('/login')
        with module.conn() as db:
            db.execute('INSERT OR IGNORE INTO users(full_name,email,phone,password_hash,national_id) VALUES(?,?,?,?,?)',
                       ('Second',target,'0551234568','hash','2'+str(os.getpid()).zfill(9)[-9:]))
            second_id=db.execute('SELECT id FROM users WHERE email=?',(target,)).fetchone()['id']
        with other.session_transaction() as sess: sess['uid']=second_id
        other.get(link)
        result=other.post(link+'/accept',data={'csrf_token':csrf(other)})
        assert result.status_code==302 and '/steps/1' in result.location
        assert other.post(link+'/accept',data={'csrf_token':csrf(other)}).status_code==403


def test_email_invitation_failure_does_not_leave_active_token(monkeypatch):
    import app as module
    monkeypatch.setenv('PUBLIC_BASE_URL','https://siyaq.example')
    def fail(*args): raise RuntimeError('Delivery failed')
    monkeypatch.setattr(module,'send_case_invitation',fail)
    with app.test_client() as client:
        client.get('/login')
        with module.conn() as db:
            email='failcreator'+str(os.getpid())+'@example.com'
            db.execute('INSERT OR IGNORE INTO users(full_name,email,phone,password_hash,national_id) VALUES(?,?,?,?,?)',('Creator',email,'0551234567','hash','3'+str(os.getpid()).zfill(9)[-9:]))
            uid=db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()['id']
            ref='FAIL-'+str(os.getpid())
            db.execute('INSERT OR IGNORE INTO cases(reference,creator_id,accident_type,accident_date,accident_time,location) VALUES(?,?,?,?,?,?)',(ref,uid,'REAR_END','2026-10-16','11:00','الرياض'))
            cid=db.execute('SELECT id FROM cases WHERE reference=?',(ref,)).fetchone()['id']
            db.execute("INSERT OR IGNORE INTO parties(case_id,user_id,position) VALUES(?,?,?)",(cid,uid,'A'))
            db.execute("INSERT OR IGNORE INTO parties(case_id,position) VALUES(?,?)",(cid,'B'))
        with client.session_transaction() as sess: sess['uid']=uid
        client.get('/cases/'+str(cid))
        response=client.post('/cases/'+str(cid)+'/invite',data={'csrf_token':csrf(client),'recipient_email':'failrecipient@example.com'},follow_redirects=True)
        assert b'Delivery failed' in response.data
        with module.conn() as db:
            assert db.execute('SELECT COUNT(*) AS n FROM invitations WHERE case_id=?',(cid,)).fetchone()['n']==0


def test_brevo_rest_api_sends_otp_and_invitation(monkeypatch):
    import app as module
    import json
    sent=[]
    class FakeResponse:
        status=201
        def __enter__(self): return self
        def __exit__(self,*args): return False
    def fake_urlopen(req,timeout):
        assert req.full_url=='https://api.brevo.com/v3/smtp/email'
        assert req.get_header('Api-key')=='test-key'
        sent.append(json.loads(req.data.decode('utf-8')))
        return FakeResponse()
    monkeypatch.setenv('OTP_MODE','api')
    monkeypatch.setenv('BREVO_API_KEY','test-key')
    monkeypatch.setenv('BREVO_SENDER_EMAIL','verified@example.com')
    monkeypatch.setattr(module,'urlopen',fake_urlopen)
    module.send_email_otp('tester@example.com','123456')
    module.send_case_invitation('second@example.com','https://siyaq.example/invite/token','SQ-123')
    assert len(sent)==2
    assert sent[0]['to'][0]['email']=='tester@example.com'
    assert '123456' in sent[0]['textContent']
    assert '123456' in sent[0]['htmlContent']
    assert 'سياق' in sent[0]['htmlContent']
    assert sent[1]['to'][0]['email']=='second@example.com'
    assert 'https://siyaq.example/invite/token' in sent[1]['textContent']
    assert 'https://siyaq.example/invite/token' in sent[1]['htmlContent']
    assert 'فتح الدعوة' in sent[1]['htmlContent']
    assert all(item['sender']['email']=='verified@example.com' for item in sent)
