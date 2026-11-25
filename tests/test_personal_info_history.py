# editing the name, national ID and phone: the old values are kept with a timestamp, and a case
# submitted before the change keeps the info the party had at submission
import io, os, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH',str(Path(tempfile.gettempdir())/('siyaq_test_'+str(os.getpid())+'.db')))
os.environ.setdefault('SECRET_KEY','test-only-secret')
os.environ.setdefault('OTP_MODE','demo')
from werkzeug.security import generate_password_hash
import app as module
from app import app, local_now
import factory

def login_as(client, nid):
    with client.session_transaction() as s:
        s['uid']=nid; s['csrf']='flow-csrf'

def post(client, url, data):
    return client.post(url, data={'csrf_token':'flow-csrf', **data})

def car(letters, number):
    return {'plate_letters':letters,'plate_numbers':number,'manufacturer':'Toyota','model':'Camry','year':'2022','color':'White'}

def submit_case(client):
    now=local_now()
    r=post(client,'/cases/new',{'no_injuries':'yes','clear_weather':'yes','two_vehicles':'yes','accident_type':'REAR_END',
           'accident_date':now.strftime('%Y-%m-%d'),'accident_time':now.strftime('%H:%M'),'location':'Riyadh'})
    case_id=r.location.split('/cases/')[1].split('/')[0]
    steps=f'/cases/{case_id}/steps/'
    post(client,steps+'1',{}); post(client,steps+'2',{})
    post(client,steps+'3',car('أ ب ح','1234'))
    post(client,steps+'4',{'pos':'REAR','rcase':'normal','zone':'front','description':'I hit the car in front of me.'})
    client.post(steps+'5',data={'csrf_token':'flow-csrf','camera':'front','video':(io.BytesIO(factory.tiny_video_bytes()),'a.mp4')},content_type='multipart/form-data')
    assert '/steps/7' in post(client,steps+'6',{'consent':'yes'}).location
    return case_id

def test_old_report_keeps_old_info_and_history_keeps_both(monkeypatch):
    app.config['TESTING']=True
    monkeypatch.setattr(module,'send_status_email',lambda *args: None)
    with module.conn() as db:
        nid,_=factory.make_party(db,'Sara Ali Ahmed')
        db.execute('UPDATE accident_party SET password_hash=? WHERE national_id=?',(generate_password_hash('secret123'),nid))
        old_phone=db.execute('SELECT phone FROM accident_party WHERE national_id=?',(nid,)).fetchone()['phone']
    new_nid='2'+nid[1:]
    new_phone='055'+nid[-7:]
    with app.test_client() as a:
        login_as(a,nid)
        case_id=submit_case(a)
        # a national ID change needs the current password
        post(a,'/profile?tab=personal',{'action':'personal','full_name':'Sara Ali Ahmed','national_id':new_nid,'phone':old_phone,'date_of_birth':'2000-01-01','current':'wrong'})
        with module.conn() as db:
            assert db.execute('SELECT 1 FROM accident_party WHERE national_id=?',(nid,)).fetchone()
        r=post(a,'/profile?tab=personal',{'action':'personal','full_name':'Sara Mohammed Ahmed','national_id':new_nid,
                                          'phone':new_phone,'date_of_birth':'1999-05-20','current':'secret123'})
        assert r.status_code==302
        # the session follows the new ID, and the user's pages still work
        for page in ('/dashboard','/cases','/profile'):
            assert a.get(page).status_code==200, page
    with module.conn() as db:
        u=db.execute('SELECT * FROM accident_party WHERE national_id=?',(new_nid,)).fetchone()
        assert u['full_name']=='Sara Mohammed Ahmed' and u['phone']==new_phone and u['date_of_birth']=='1999-05-20'
        assert not db.execute('SELECT 1 FROM accident_party WHERE national_id=?',(nid,)).fetchone()
        # related rows moved to the new ID
        assert db.execute('SELECT 1 FROM participates WHERE national_id=? AND case_id=?',(new_nid,case_id)).fetchone()
        assert db.execute('SELECT 1 FROM vehicle WHERE national_id=?',(new_nid,)).fetchone()
        # the history keeps the old and new value of each changed field, with the time
        rows={r['field']:r for r in db.execute('SELECT * FROM party_info_history WHERE national_id=?',(new_nid,)).fetchall()}
        assert rows['full_name']['old_value']=='Sara Ali Ahmed' and rows['full_name']['new_value']=='Sara Mohammed Ahmed'
        assert rows['national_id']['old_value']==nid and rows['national_id']['new_value']==new_nid
        assert rows['phone']['old_value']==old_phone and rows['phone']['new_value']==new_phone
        assert rows['date_of_birth']['old_value']=='2000-01-01' and rows['date_of_birth']['new_value']=='1999-05-20'
        assert all(r['changed_at'] for r in rows.values())
        # the case submitted before the change keeps the info at submission
        snap=module.case_party_info(db,case_id,new_nid)
        assert snap['full_name']=='Sara Ali Ahmed' and snap['date_of_birth']=='2000-01-01' and snap['national_id']==nid and snap['phone']==old_phone and snap['captured_at']

def test_phone_or_id_of_another_account_is_rejected():
    app.config['TESTING']=True
    with module.conn() as db:
        nid,_=factory.make_party(db,'First Test Party')
        other,_=factory.make_party(db,'Second Test Party')
        other_phone=db.execute('SELECT phone FROM accident_party WHERE national_id=?',(other,)).fetchone()['phone']
    with app.test_client() as a:
        login_as(a,nid)
        post(a,'/profile?tab=personal',{'action':'personal','full_name':'First Test Party','national_id':nid,'phone':other_phone,'date_of_birth':'2000-01-01'})
    with module.conn() as db:
        assert db.execute('SELECT phone FROM accident_party WHERE national_id=?',(nid,)).fetchone()['phone']!=other_phone
        assert not db.execute('SELECT 1 FROM party_info_history WHERE national_id=?',(nid,)).fetchone()

def test_invited_party_sees_case_details_before_accepting(monkeypatch):
    app.config['TESTING']=True
    invites=[]
    monkeypatch.setattr(module,'send_case_invitation',lambda email,link,ref: invites.append(link))
    monkeypatch.setattr(module,'send_status_email',lambda *args: None)
    monkeypatch.setenv('PUBLIC_BASE_URL','https://siyaq.example')
    with module.conn() as db:
        a_nid,_=factory.make_party(db,'Party A Person')
        b_nid,b_email=factory.make_party(db,'Party B Person')
    with app.test_client() as a:
        login_as(a,a_nid)
        case_id=submit_case(a)
        post(a,f'/cases/{case_id}/invite',{'recipient_email':b_email})
    link='/'+invites[0].split('://',1)[1].split('/',1)[1]
    with app.test_client() as b:
        login_as(b,b_nid)
        html=b.get(link).get_data(as_text=True)
        assert 'حادث اصطدام خلفي' in html and 'Toyota Camry' in html and '1234' in html and 'Riyadh' in html
        assert 'Party A Person' not in html
    with app.test_client() as guest:
        assert 'Toyota Camry' not in guest.get(link).get_data(as_text=True)

def test_home_button_in_the_bar():
    app.config['TESTING']=True
    with module.conn() as db: nid,_=factory.make_party(db,'Home Button Person')
    with app.test_client() as a:
        login_as(a,nid)
        html=a.get('/cases').get_data(as_text=True)
        assert 'href="/dashboard">الرئيسية</a>' in html

def test_name_and_birth_date_change_without_password_and_under_18_rejected():
    app.config['TESTING']=True
    with module.conn() as db:
        nid,_=factory.make_party(db,'Noura Saad Ali')
        phone=db.execute('SELECT phone FROM accident_party WHERE national_id=?',(nid,)).fetchone()['phone']
    with app.test_client() as a:
        login_as(a,nid)
        # no password needed when the national ID stays the same
        post(a,'/profile?tab=personal',{'action':'personal','full_name':'Noura Saad Alharbi','national_id':nid,'phone':phone,'date_of_birth':'1998-03-03'})
        # a birth date that makes the user younger than 18 is rejected
        post(a,'/profile?tab=personal',{'action':'personal','full_name':'Noura Saad Alharbi','national_id':nid,'phone':phone,'date_of_birth':'2020-01-01'})
        html=a.get('/profile').get_data(as_text=True)
        assert 'autocomplete="current-password" disabled' in html
    with module.conn() as db:
        u=db.execute('SELECT full_name,date_of_birth FROM accident_party WHERE national_id=?',(nid,)).fetchone()
        assert u['full_name']=='Noura Saad Alharbi' and u['date_of_birth']=='1998-03-03'
        fields=sorted(r['field'] for r in db.execute('SELECT field FROM party_info_history WHERE national_id=?',(nid,)).fetchall())
        assert fields==['date_of_birth','full_name']
