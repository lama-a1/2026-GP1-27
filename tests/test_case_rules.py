# check the accident time limit and deleting all files when a case is cancelled
import json
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs
import app as module
import factory


def make_case(original, processed):
    with module.conn() as db:
        uid, _ = factory.make_party(db, 'Test Case Owner')
        cid = factory.make_case(db, uid)
        vid = factory.add_video(db, cid, uid, original, processed)
    return uid, cid, vid


def cancel(uid, cid):
    with module.app.test_client() as client:
        with client.session_transaction() as session:
            session['uid'] = uid
            session['csrf'] = 'case-check'
        return client.post(f'/cases/{cid}/cancel', data={'csrf_token': 'case-check'})


def test_accident_time_rejects_future_and_old_values(monkeypatch):
    now = datetime(2026, 10, 22, 12, 0)
    monkeypatch.setattr(module, 'local_now', lambda: now)
    assert module.accident_within_window(now)
    assert module.accident_within_window(now - timedelta(hours=24))
    assert not module.accident_within_window(now + timedelta(seconds=1))
    assert not module.accident_within_window(now - timedelta(hours=24, seconds=1))


def test_cancel_removes_original_and_processed_local_files(monkeypatch):
    with tempfile.TemporaryDirectory() as folder:
        monkeypatch.setattr(module, 'UPLOAD', Path(folder))
        for name in ['original.mp4', 'processed.mp4']:
            (Path(folder) / name).write_bytes(b'test')
        uid, cid, vid = make_case('original.mp4', 'processed.mp4')
        assert cancel(uid, cid).status_code == 302
        assert not list(Path(folder).iterdir())
        with module.conn() as db:
            assert db.execute('SELECT case_id FROM accident_case WHERE case_id=?', (cid,)).fetchone() is None
            assert db.execute('SELECT video_id FROM dashcam_video WHERE video_id=?', (vid,)).fetchone() is None
            assert db.execute('SELECT video_id FROM video_processing WHERE video_id=?', (vid,)).fetchone() is None


def test_cancel_removes_both_cloudinary_files(monkeypatch):
    for name, value in [('CLOUDINARY_CLOUD_NAME', 'testcloud'), ('CLOUDINARY_API_KEY', 'testkey'), ('CLOUDINARY_API_SECRET', 'testsecret')]:
        monkeypatch.setenv(name, value)
    deleted = []

    # use a local response instead of deleting real Cloudinary files
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps({'result': 'ok'}).encode()

    def remove(request, timeout):
        deleted.append(parse_qs(request.data.decode())['public_id'][0])
        return Response()

    monkeypatch.setattr(module, 'urlopen', remove)
    uid, cid, vid = make_case('cloudinary://siyaq/original', 'cloudinary://siyaq/processed')
    assert cancel(uid, cid).status_code == 302
    assert deleted == ['siyaq/original', 'siyaq/processed']


def test_cancel_removes_both_s3_files(monkeypatch):
    for name, value in [('S3_BUCKET', 'test-bucket'), ('AWS_REGION', 'test-region'), ('AWS_ACCESS_KEY_ID', 'test-key'), ('AWS_SECRET_ACCESS_KEY', 'test-secret')]:
        monkeypatch.setenv(name, value)
    deleted = []

    class Storage:
        def delete_object(self, **values): deleted.append(values['Key'])

    monkeypatch.setattr(module, 'storage_client', lambda: Storage())
    uid, cid, vid = make_case('s3://cases/original.mp4', 's3://cases/processed.mp4')
    assert cancel(uid, cid).status_code == 302
    assert deleted == ['cases/original.mp4', 'cases/processed.mp4']


def test_failed_file_deletion_keeps_the_case(monkeypatch):
    uid, cid, vid = make_case('cloudinary://siyaq/keep-original', None)

    def fail(path): raise OSError('test storage failure')

    monkeypatch.setattr(module, 'delete_stored_file', fail)
    assert cancel(uid, cid).status_code == 302
    with module.conn() as db:
        assert db.execute('SELECT case_id FROM accident_case WHERE case_id=?', (cid,)).fetchone() is not None
        assert db.execute('SELECT video_id FROM dashcam_video WHERE video_id=?', (vid,)).fetchone() is not None
