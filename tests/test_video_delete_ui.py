# check the video controls and deleting a video from the case
import os, sys, tempfile, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir())/'siyaq_video_delete_test.db'))
os.environ.setdefault('SECRET_KEY', 'test-only-video-secret')
import app as module


def test_step5_renders_remove_control_and_invite_button():
    source=(Path(__file__).resolve().parents[1]/'templates/wizard.html').read_text()
    js=(Path(__file__).resolve().parents[1]/'static/app.js').read_text()
    assert 'clear-selected-video' in source
    assert "url_for('delete_video',video_id=v.id)" in source
    assert 'send-party-invite' in source
    assert 'window.location.assign(result.next_url)' not in js
    assert "'/steps/5'" in js


def test_uploaded_video_can_be_deleted_by_owner(monkeypatch):
    app=module.app
    app.config['TESTING']=True
    with app.test_client() as client:
        client.get('/login')
        reference='DEL-'+uuid.uuid4().hex[:12]
        email='delete'+uuid.uuid4().hex[:12]+'@example.test'
        import factory
        with module.conn() as db:
            uid,_=factory.make_party(db,'Video Owner',email=email)
            case_id=factory.make_case(db,uid,progress=4,case_id=reference)
            video_id=factory.add_video(db,case_id,uid,'cloudinary://siyaq/test-delete')
        with client.session_transaction() as sess:
            sess['uid']=uid
            sess['csrf']='csrf-test'
        monkeypatch.setenv('CLOUDINARY_CLOUD_NAME','testcloud')
        monkeypatch.setenv('CLOUDINARY_API_KEY','testkey')
        monkeypatch.setenv('CLOUDINARY_API_SECRET','testsecret')
        # return a successful delete response without contacting Cloudinary
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self): return b'{"result":"ok"}'
        monkeypatch.setattr(module, 'urlopen', lambda *args,**kwargs: Response())
        page=client.get(f'/cases/{case_id}/steps/5')
        assert page.status_code==200
        assert b'test.mp4' in page.data
        assert f'/videos/{video_id}/delete'.encode() in page.data
        result=client.post(f'/videos/{video_id}/delete', data={'csrf_token':'csrf-test'})
        assert result.status_code==302 and '/steps/5' in result.location
        with module.conn() as db:
            assert db.execute('SELECT video_id FROM dashcam_video WHERE video_id=?',(video_id,)).fetchone() is None
            assert db.execute('SELECT video_id FROM video_processing WHERE video_id=?',(video_id,)).fetchone() is None
