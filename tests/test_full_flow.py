# go through a whole case with both parties, and check the data is saved in the EER tables
import io, os, sys, tempfile, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH',str(Path(tempfile.gettempdir())/('siyaq_test_'+str(os.getpid())+'.db')))
os.environ.setdefault('SECRET_KEY','test-only-secret')
os.environ.setdefault('OTP_MODE','demo')
import app as module
from app import app, local_now
import factory

def csrf(c):
    with c.session_transaction() as s: return s['csrf']

def login_as(client, nid):
    with client.session_transaction() as s:
        s['uid']=nid; s['csrf']='flow-csrf'

def post(client, url, data):
    return client.post(url, data={'csrf_token':'flow-csrf', **data})

def car(letters, number):
    return {'plate_letters':letters,'plate_numbers':number,'manufacturer':'Toyota','model':'Camry','year':'2022','color':'White'}

def test_whole_case_with_both_parties(monkeypatch):
    app.config['TESTING']=True
    invites=[]
    monkeypatch.setattr(module,'send_case_invitation',lambda email,link,ref: invites.append(link))
    monkeypatch.setattr(module,'send_status_email',lambda *args: None)
    monkeypatch.setenv('PUBLIC_BASE_URL','https://siyaq.example')
    with module.conn() as db:
        a_nid,a_email=factory.make_party(db,'First Party')
        b_nid,b_email=factory.make_party(db,'Second Party')
    now=local_now()
    with app.test_client() as a:
        login_as(a,a_nid)
        r=post(a,'/cases/new',{'no_injuries':'yes','clear_weather':'yes','two_vehicles':'yes','accident_type':'REAR_END',
               'accident_date':now.strftime('%Y-%m-%d'),'accident_time':now.strftime('%H:%M'),'location':'Riyadh'})
        assert r.status_code==302
        case_id=r.location.split('/cases/')[1].split('/')[0]
        steps=f'/cases/{case_id}/steps/'
        # each step page opens before it is filled
        for n in (1,2,3):
            assert a.get(steps+str(n)).status_code==200, n
            if n<3: assert post(a,steps+str(n),{}).status_code==302
        assert '/steps/4' in post(a,steps+'3',car('أ ب ح','1111')).location
        assert a.get(steps+'4').status_code==200
        r=post(a,steps+'4',{'pos':'REAR','rcase':'normal','zone':'front','description':'I hit the car in front of me.'})
        assert '/steps/5' in r.location
        r=a.post(steps+'5',data={'csrf_token':'flow-csrf','camera':'front','video':(io.BytesIO(b'video'),'a.mp4')},content_type='multipart/form-data')
        assert '/steps/6' in r.location
        assert a.get(steps+'5').status_code==200 and a.get(steps+'6').status_code==200
        assert '/steps/7' in post(a,steps+'6',{'consent':'yes'}).location
        assert post(a,f'/cases/{case_id}/invite',{'recipient_email':b_email}).status_code==302
        for page in ('/dashboard','/cases','/profile?tab=vehicles',steps+'7'):
            assert a.get(page).status_code==200, page
    link='/'+invites[0].split('://',1)[1].split('/',1)[1]
    with app.test_client() as b:
        login_as(b,b_nid)
        assert b.get(link).status_code==200
        assert '/steps/1' in post(b,link+'/accept',{}).location
        assert b.get(steps+'1').status_code==200
        post(b,steps+'1',{})
        assert b.get(steps+'2').status_code==200
        post(b,steps+'2',{})
        assert b.get(steps+'3').status_code==200
        # the same plate as the other party's car is refused
        assert '/steps/3' in post(b,steps+'3',car('أ ب ح','1111')).location
        assert '/steps/4' in post(b,steps+'3',car('د ر س','2222')).location
        # B tries to choose REAR too, but B is always the opposite of A
        assert b.get(steps+'4').status_code==200
        assert '/steps/5' in post(b,steps+'4',{'pos':'REAR','rcase':'normal','zone':'rear','description':'The car behind hit me.'}).location
        assert '/steps/6' in post(b,steps+'5',{}).location  # the video is optional for B
        assert '/steps/7' in post(b,steps+'6',{'consent':'yes'}).location
    with module.conn() as db:
        case=db.execute('SELECT * FROM accident_case WHERE case_id=?',(case_id,)).fetchone()
        assert case['status']=='in_progress'
        assert case['party_a_position']=='REAR'
        assert case['party_b_email']==b_email
        assert case['party_a_description']=='I hit the car in front of me.'
        assert case['party_b_description']=='The car behind hit me.'
        assert db.execute('SELECT COUNT(*) AS n FROM participates WHERE case_id=?',(case_id,)).fetchone()['n']==2
        assert db.execute('SELECT COUNT(*) AS n FROM involves WHERE case_id=?',(case_id,)).fetchone()['n']==2
        video=db.execute('SELECT * FROM dashcam_video WHERE case_id=?',(case_id,)).fetchone()
        assert video['national_id']==a_nid and video['camera_type']=='front'
    with app.test_client() as e:
        with e.session_transaction() as s: s['expert_authenticated']=True
        page=e.get('/expert/cases')
        assert page.status_code==200 and case_id.encode() in page.data

def test_car_in_a_submitted_case_cannot_be_deleted():
    with module.conn() as db:
        nid,_=factory.make_party(db,'Car Owner')
        cid=factory.make_case(db,nid,with_vehicles=True)
        db.execute('UPDATE participation_progress SET completed=1 WHERE case_id=?',(cid,))
        vid=db.execute('SELECT vehicle_id FROM involves WHERE case_id=?',(cid,)).fetchone()['vehicle_id']
    with app.test_client() as c:
        login_as(c,nid)
        post(c,f'/profile/vehicles/{vid}/delete',{})
    with module.conn() as db:
        assert db.execute('SELECT 1 FROM vehicle WHERE vehicle_id=?',(vid,)).fetchone()

def test_case_cannot_have_three_parties():
    import pytest
    with module.conn() as db:
        a,_=factory.make_party(db,'A'); b,_=factory.make_party(db,'B'); c,_=factory.make_party(db,'C')
        cid=factory.make_case(db,a,b)
    with pytest.raises(Exception, match='at most two'):
        with module.conn() as db:
            db.execute('INSERT INTO participates(national_id,case_id) VALUES(?,?)',(c,cid))
