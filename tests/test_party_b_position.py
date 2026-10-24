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

def meta_of(cid, nid):
    import json
    with module.conn() as db:
        row=db.execute('SELECT description_meta FROM participation_progress WHERE case_id=? AND national_id=?',(cid,nid)).fetchone()
    return json.loads(row['description_meta'])

def post_step4(nid, cid, data):
    with app.test_client() as c:
        with c.session_transaction() as s: s['uid']=nid; s['csrf']='t'
        return c.post(f'/cases/{cid}/steps/4',data={'csrf_token':'t',**data})

def test_rear_end_zone_follows_position_and_story_stays_free():
    app.config['TESTING']=True
    with module.conn() as db:
        a,_=factory.make_party(db,'Front Car')
        b,_=factory.make_party(db,'Rear Car')
        cid=factory.make_case(db,a,b,progress=3,with_vehicles=True)
    # A is the front car and says it slowed down normally, but picks the wrong zone
    post_step4(a,cid,{'pos':'FRONT','rcase':'normal','zone':'front','description':'The car behind hit me.'})
    assert meta_of(cid,a)['zone']=='rear'
    # B tells a different story (sudden stop): allowed, only the position and zone are fixed
    post_step4(b,cid,{'pos':'FRONT','rcase':'sudden','zone':'rear','description':'The front car braked for no reason.'})
    m=meta_of(cid,b)
    assert m['pos']=='REAR' and m['zone']=='front' and m['rcase']=='sudden'
    with module.conn() as db:
        assert db.execute('SELECT party_b_description FROM accident_case WHERE case_id=?',(cid,)).fetchone()[0]=='The front car braked for no reason.'

def test_lane_change_only_side_is_fixed():
    app.config['TESTING']=True
    with module.conn() as db:
        a,_=factory.make_party(db,'Lane A')
        b,_=factory.make_party(db,'Lane B')
        cid=factory.make_case(db,a,b,progress=3,with_vehicles=True,accident_type='LANE_CHANGE')
    post_step4(a,cid,{'side':'left','who':'other','zone':'front-left','description':'The other car moved into my lane.'})
    # B disagrees about who changed lanes and picks its own zone
    post_step4(b,cid,{'side':'left','who':'other','zone':'right','description':'The other car moved into my lane.'})
    m=meta_of(cid,b)
    assert m['side']=='right' and m['who']=='other' and m['zone']=='right'
