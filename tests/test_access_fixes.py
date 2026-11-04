# party B cannot download party A's video, and the expert lockout counts both spellings of the username
import os, sys, tempfile, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir()) / ('siyaq_test_' + str(os.getpid()) + '.db')))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
os.environ.setdefault('OTP_MODE', 'demo')
import app as module
from app import app
import factory


def test_party_b_cannot_download_party_a_video():
    app.config['TESTING'] = True
    with module.conn() as db:
        a, _ = factory.make_party(db, 'Party A')
        b, _ = factory.make_party(db, 'Party B')
        case_id = factory.make_case(db, a, b)
        vid = factory.add_video(db, case_id, a, uuid.uuid4().hex + '.mp4')
    with app.test_client() as client:
        with client.session_transaction() as s:
            s['uid'] = b
        assert client.get(f'/videos/{vid}/download').status_code == 403


def test_expert_lockout_same_counter_with_or_without_prefix():
    app.config['TESTING'] = True
    name = 'lock' + uuid.uuid4().hex[:6]
    for i in range(module.LOGIN_MAX_FAILS):
        module.login_failed('expert:' + module.EXPERT_PREFIX + name)
    with app.test_client() as client:
        client.get('/expert/login')
        with client.session_transaction() as s:
            token = s['csrf']
        r = client.post('/expert/login', data={'csrf_token': token, 'username': name, 'password': 'x'})
        assert module.LOCKED_MSG.encode('utf-8') in r.data
