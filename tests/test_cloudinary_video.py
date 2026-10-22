# check the upload signature and saving the uploaded video in the case
import os, sys, tempfile, json, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH',str(Path(tempfile.gettempdir())/'siyaq_cloudinary_test.db'))
os.environ.setdefault('SECRET_KEY','test-only-cloudinary-secret')
import app as module
from app import app

def test_cloudinary_signature(monkeypatch):
    monkeypatch.setenv('CLOUDINARY_API_SECRET','secret')
    import hashlib
    params={'timestamp':1234,'type':'authenticated','public_id':'siyaq/test'}
    expected=hashlib.sha1(b'public_id=siyaq/test&timestamp=1234&type=authenticatedsecret').hexdigest()
    assert module.cloudinary_sign(params)==expected

def test_cloudinary_presign_and_complete(monkeypatch):
    app.config['TESTING']=True
    monkeypatch.setenv('CLOUDINARY_CLOUD_NAME','testcloud')
    monkeypatch.setenv('CLOUDINARY_API_KEY','testkey')
    monkeypatch.setenv('CLOUDINARY_API_SECRET','testsecret')
    with app.test_client() as client:
        client.get('/login')
        with module.conn() as db:
            db.execute('INSERT OR IGNORE INTO users(full_name,email,password_hash,national_id) VALUES(?,?,?,?)',('Video Test','video@example.test','hash','1999999999'))
            uid=db.execute('SELECT id FROM users WHERE email=?',('video@example.test',)).fetchone()['id']
            db.execute('INSERT OR IGNORE INTO cases(reference,creator_id,accident_type,accident_date,accident_time,location) VALUES(?,?,?,?,?,?)',('CLOUD-TEST',uid,'REAR_END','2026-10-17','10:00','Riyadh'))
            cid=db.execute('SELECT id FROM cases WHERE reference=?',('CLOUD-TEST',)).fetchone()['id']
            db.execute('INSERT OR IGNORE INTO parties(case_id,user_id,position) VALUES(?,?,?)',(cid,uid,'A'))
            party_id=db.execute('SELECT id FROM parties WHERE case_id=? AND position=?',(cid,'A')).fetchone()['id']
        with client.session_transaction() as sess:
            sess['uid']=uid
            sess['csrf']='csrf-test'
        endpoint=f'/api/cases/{cid}/videos/'
        r=client.post(endpoint+'presign',json={'filename':'test.mp4','size':1234,'camera':'front'},headers={'X-CSRF-Token':'csrf-test'})
        assert r.status_code==200, r.get_json()
        data=r.get_json()
        assert data['provider']=='cloudinary'
        assert data['delivery_type']=='authenticated'
        assert 'testsecret' not in json.dumps(data)
        # use sample upload details instead of calling Cloudinary
        monkeypatch.setattr(module,'cloudinary_metadata',lambda pid: {'public_id':pid,'resource_type':'video','type':'authenticated','bytes':1234})
        result=client.post(endpoint+'complete',headers={'X-CSRF-Token':'csrf-test'})
        assert result.status_code==200, result.get_json()
        with module.conn() as db:
            videos=db.execute('SELECT * FROM videos WHERE party_id=?',(party_id,)).fetchall()
            assert len(videos)>=1
            assert any(v['stored_name']=='cloudinary://'+data['public_id'] for v in videos)
