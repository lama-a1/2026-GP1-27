# the second party's car position is fixed by the first party's choice
import os, tempfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH',str(Path(tempfile.gettempdir())/('siyaq_test_'+str(os.getpid())+'.db')))
os.environ.setdefault('SECRET_KEY','test-only-secret')
os.environ.setdefault('OTP_MODE','demo')
import app as module
from app import app
import factory

def test_second_party_cannot_choose_position():
    app.config['TESTING']=True
    with module.conn() as db:
        a,_=factory.make_party(db,'First Party')
        b,_=factory.make_party(db,'Second Party')
        cid=factory.make_case(db,a,b,progress=3,with_vehicles=True)
        db.execute("UPDATE accident_case SET party_a_position='FRONT' WHERE case_id=?",(cid,))
    with app.test_client() as c:
        with c.session_transaction() as s: s['uid']=b; s['csrf']='t'
        page=c.get(f'/cases/{cid}/steps/4').data.decode()
        assert 'data-locked="1"' in page and 'data-role="REAR"' in page
        # even if B sends FRONT, the first party's position stays FRONT
        c.post(f'/cases/{cid}/steps/4',data={'csrf_token':'t','pos':'FRONT','rcase':'normal','zone':'front','description':'The car behind hit me.'})
    with module.conn() as db:
        assert db.execute('SELECT party_a_position FROM accident_case WHERE case_id=?',(cid,)).fetchone()['party_a_position']=='FRONT'

def test_first_party_can_choose_position():
    app.config['TESTING']=True
    with module.conn() as db:
        a,_=factory.make_party(db,'Only Party')
        cid=factory.make_case(db,a,progress=3,with_vehicles=True)
    with app.test_client() as c:
        with c.session_transaction() as s: s['uid']=a; s['csrf']='t'
        page=c.get(f'/cases/{cid}/steps/4').data.decode()
        assert 'data-locked=""' in page
