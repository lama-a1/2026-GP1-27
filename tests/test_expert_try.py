# Expert trial page: analyse any video without a case; nothing is stored and the uploaded copy is deleted
import io, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir()) / ('siyaq_test_' + str(os.getpid()) + '.db')))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
os.environ.setdefault('OTP_MODE', 'demo')
import pytest
import app as module
from app import app
import video_analysis
from test_video_analysis import FAKE


def expert(client):
    with client.session_transaction() as s:
        s['expert_authenticated'] = True
        s['csrf'] = 't'


def test_only_the_expert_can_use_it():
    app.config['TESTING'] = True
    with app.test_client() as c:
        assert c.get('/expert/try').status_code == 302
        with c.session_transaction() as s:
            s['csrf'] = 't'
        assert c.post('/expert/try/analyse', headers={'X-CSRF-Token': 't'}).status_code == 403
        assert c.post('/expert/try/presign', json={}, headers={'X-CSRF-Token': 't'}).status_code == 403


def test_local_upload_is_analysed_and_nothing_is_saved(monkeypatch):
    app.config['TESTING'] = True
    import siyaq_cv.analyse
    seen = {}
    monkeypatch.setattr(siyaq_cv.analyse, 'analyse_video', lambda path, kind: seen.update(path=path, kind=kind, exists=os.path.exists(path)) or FAKE)
    monkeypatch.setattr(module, 'cloudinary_ready', lambda: False)
    with module.conn() as db:
        before = db.execute('SELECT COUNT(*) AS n FROM video_analysis').fetchone()['n']
    with app.test_client() as c:
        expert(c)
        assert 'تجربة التحليل الآلي' in c.get('/expert/try').get_data(as_text=True)
        assert c.post('/expert/try/presign', json={'filename': 'crash.mp4', 'size': 1000}, headers={'X-CSRF-Token': 't'}).get_json() == {'provider': 'direct'}
        r = c.post('/expert/try/analyse', headers={'X-CSRF-Token': 't'},
                   data={'accident_type': 'LANE_CHANGE', 'video': (io.BytesIO(b'fake video'), 'crash.mp4')}, content_type='multipart/form-data')
    body = r.get_json()
    assert r.status_code == 200 and seen['kind'] == 'LANE_CHANGE' and seen['exists']
    assert not os.path.exists(seen['path'])                     # the temporary copy is gone
    assert 'id="va-data"' in body['html'] and 'id="va-video"' in body['html']
    with module.conn() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM video_analysis').fetchone()['n'] == before


@pytest.mark.parametrize('fails', [False, True])
def test_cloudinary_copy_is_deleted_after_the_analysis(monkeypatch, fails):
    app.config['TESTING'] = True
    import siyaq_cv.analyse
    for k, v in {'CLOUDINARY_CLOUD_NAME': 'demo', 'CLOUDINARY_API_KEY': 'k', 'CLOUDINARY_API_SECRET': 's'}.items():
        monkeypatch.setenv(k, v)
    deleted = []
    monkeypatch.setattr(module, 'delete_stored_file', lambda p: deleted.append(p))

    def fake_fetch(h, v, folder):
        path = os.path.join(folder, 'video.mp4'); open(path, 'wb').write(b'x'); return path
    monkeypatch.setattr(video_analysis, 'fetch_video', fake_fetch)

    def fake_analyse(path, kind):
        if fails:
            raise RuntimeError('boom')
        return FAKE
    monkeypatch.setattr(siyaq_cv.analyse, 'analyse_video', fake_analyse)
    with app.test_client() as c:
        expert(c)
        ticket = c.post('/expert/try/presign', json={'filename': 'crash.mp4', 'size': 1000}, headers={'X-CSRF-Token': 't'}).get_json()
        assert ticket['provider'] == 'cloudinary' and ticket['public_id'].startswith('siyaq/expert-trials/')
        r = c.post('/expert/try/analyse', json={'accident_type': 'REAR_END'}, headers={'X-CSRF-Token': 't'})
        with c.session_transaction() as s:
            assert 'expert_trial' not in s
    assert r.status_code == (500 if fails else 200)
    assert deleted == ['cloudinary://' + ticket['public_id']]
