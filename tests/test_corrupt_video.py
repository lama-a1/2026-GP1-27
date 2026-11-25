# a corrupted video or a file that is not a video is rejected at the upload step, and the user stays on the step
import io, os, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH',str(Path(tempfile.gettempdir())/'siyaq_corrupt_video_test.db'))
os.environ.setdefault('SECRET_KEY','test-only-corrupt-video-secret')
import app as module
import factory
from app import app

def _write(tmp_path, name, data):
    p=tmp_path/name; p.write_bytes(data); return p

def test_container_check(tmp_path):
    good=factory.tiny_video_bytes()
    assert module.video_file_ok(_write(tmp_path,'ok.mp4',good))
    assert not module.video_file_ok(_write(tmp_path,'cut.mp4',good[:len(good)//2]))      # recording cut off
    assert not module.video_file_ok(_write(tmp_path,'text.mp4',b'not a video'*100))       # renamed text file
    assert not module.video_file_ok(_write(tmp_path,'noise.mp4',os.urandom(4000)))        # random bytes

def test_corrupted_upload_is_rejected_and_not_saved():
    app.config['TESTING']=True
    with app.test_client() as client:
        client.get('/login')
        with module.conn() as db:
            uid,_=factory.make_party(db,'Corrupt Video Test')
            cid=factory.make_case(db,uid,progress=4)
        with client.session_transaction() as sess:
            sess['uid']=uid; sess['csrf']='csrf-test'
        good=factory.tiny_video_bytes()
        r=client.post(f'/cases/{cid}/steps/5',data={'csrf_token':'csrf-test','camera':'front',
                      'video':(io.BytesIO(good[:len(good)//2]),'cut.mp4')},content_type='multipart/form-data',follow_redirects=True)
        assert module.CORRUPT_VIDEO_MSG in r.get_data(as_text=True)
        with module.conn() as db:
            assert not db.execute('SELECT 1 FROM dashcam_video WHERE case_id=?',(cid,)).fetchone()
        r=client.post(f'/cases/{cid}/steps/5',data={'csrf_token':'csrf-test','camera':'front',
                      'video':(io.BytesIO(good),'ok.mp4')},content_type='multipart/form-data')
        with module.conn() as db:
            assert db.execute('SELECT COUNT(*) AS n FROM dashcam_video WHERE case_id=?',(cid,)).fetchone()['n']==1
