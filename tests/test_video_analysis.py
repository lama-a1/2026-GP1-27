# Sprint 2: the automatic video analysis runs inside the website and its events reach the EER tables
import json, os, shutil, sys, tempfile, uuid
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir()) / ('siyaq_test_' + str(os.getpid()) + '.db')))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
os.environ.setdefault('OTP_MODE', 'demo')
import app as module
from app import app
import factory

FAKE = {'version': 'test', 'accident_type': 'LANE_CHANGE', 'vehicle_b': 2, 'collision_frame': 37,
        'video': {'fps': 10, 'frames': 50, 'duration_s': 5.0, 'window_start_s': 0.0, 'width': 1280, 'height': 720},
        'assumptions': {'camera_fov_deg': 110.0, 'real_heights_m': {'car': 1.55}}, 'quality': {'flags': []},
        'vehicles': [{'track_id': 2, 'role': 'B', 'class': 'car', 'frames': 37, 'min_distance_m': 1.2,
                      'mean_rel_speed_mps': -3.6, 'longitudinal': 'approaching', 'lateral': 'moving left'}],
        'tracks': {'2': [[25, .6, .4, .8, .6], [37, .3, .2, .9, .9]]},
        'series': {'t': [i / 10 for i in range(50)], 'b_distance_m': [None] * 50, 'b_ttc_s': [None] * 50,
                   'a_heading_rate_deg_s': [0] * 50, 'b_rel_speed_mps': [None] * 50},
        'events': [{'type': 'lane_change', 'vehicle': 'B', 'track_id': 2, 'start': 25, 'end': 32, 'start_t': 2.5, 'end_t': 3.2,
                    'measures': {'direction': 'left', 'lateral_shift_m': 3.0}},
                   {'type': 'collision', 'vehicle': 'B', 'track_id': 2, 'start': 37, 'end': 37, 'start_t': 3.7, 'end_t': 3.7,
                    'measures': {'time_s': 3.7, 'min_ttc_last_1s_s': 0.38}}],
        'timing_s': {'total': 6.2}}


def setup_case(db):
    a, _ = factory.make_party(db, 'Party A')
    case_id = factory.make_case(db, a, accident_type='LANE_CHANGE', with_vehicles=True)
    vid = factory.add_video(db, case_id, a, uuid.uuid4().hex + '.mp4')
    return a, case_id, vid


def login_expert(client):
    with client.session_transaction() as s:
        s['expert_authenticated'] = True
        s['csrf'] = 'va-csrf'


def login(client, nid):
    with client.session_transaction() as s:
        s['uid'] = nid
        s['csrf'] = 'va-csrf'


def test_analyse_saves_result_and_eer_events(monkeypatch):
    app.config['TESTING'] = True
    import siyaq_cv.analyse
    seen = {}
    monkeypatch.setattr(siyaq_cv.analyse, 'analyse_video', lambda path, typ: seen.update(type=typ) or FAKE)
    with module.conn() as db:
        nid, case_id, vid = setup_case(db)
    with app.test_client() as client:
        login(client, nid)
        r = client.post(f'/videos/{vid}/analyse', headers={'X-CSRF-Token': 'va-csrf'})
        assert r.get_json()['status'] == 'done'
        assert seen['type'] == 'LANE_CHANGE'                     # the accident type chosen in the case form
        # the party does not see the technical analysis page, the expert does
        assert client.get(f'/videos/{vid}/analysis').status_code == 403
    with app.test_client() as expert:
        login_expert(expert)
        page = expert.get(f'/videos/{vid}/analysis').data.decode()
        for text in ('تغيير مسار', 'لحظة الاصطدام', 'مقدار الانتقال الجانبي', 'تتبع المركبات'):
            assert text in page
    with module.conn() as db:
        types = [r['event_type'] for r in db.execute('SELECT event_type FROM detected_event WHERE video_id=?', (vid,))]
        assert sorted(types) == ['collision', 'lane_change']
        assert db.execute('''SELECT count(*) AS n FROM involvement i JOIN detected_event e ON e.event_id=i.event_id
                             WHERE e.video_id=? AND i.vehicle_role='Vehicle B' ''', (vid,)).fetchone()['n'] == 2
        assert db.execute('SELECT job_status FROM video_processing WHERE video_id=?', (vid,)).fetchone()['job_status'] == 'done'
    # analysing again (by the expert) replaces the old events instead of adding duplicates
    with app.test_client() as expert:
        login_expert(expert)
        expert.post(f'/videos/{vid}/analyse', headers={'X-CSRF-Token': 'va-csrf'})
    with module.conn() as db:
        assert db.execute('SELECT count(*) AS n FROM detected_event WHERE video_id=?', (vid,)).fetchone()['n'] == 2


def test_other_users_cannot_see_the_analysis():
    with module.conn() as db:
        nid, case_id, vid = setup_case(db)
        stranger, _ = factory.make_party(db, 'Stranger')
    with app.test_client() as client:
        login(client, stranger)
        assert client.get(f'/videos/{vid}/analysis').status_code == 403
        assert client.post(f'/videos/{vid}/analyse', headers={'X-CSRF-Token': 'va-csrf'}).status_code == 403


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / 'siyaq_cv/models/yolov8n.onnx').exists(), reason='model missing')
def test_real_engine_on_a_generated_video(tmp_path):
    # a tiny synthetic video: the engine must run end to end without PyTorch
    import cv2, numpy as np
    p = str(tmp_path / 'v.mp4')
    w = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 180))
    for i in range(20):
        fr = np.full((180, 320, 3), 90, np.uint8)
        cv2.rectangle(fr, (140 - i, 90 - i), (180 + i, 120 + i), (40, 40, 200), -1)
        w.write(fr)
    w.release()
    from siyaq_cv.analyse import analyse_video
    r = analyse_video(p, 'REAR_END')
    assert r['video']['frames'] == 20 and 'events' in r and 'torch' not in sys.modules


def test_second_party_cannot_reach_the_first_party_video(monkeypatch):
    import siyaq_cv.analyse
    monkeypatch.setattr(siyaq_cv.analyse, 'analyse_video', lambda path, typ: FAKE)
    with module.conn() as db:
        a, case_id, vid = setup_case(db)
        b, _ = factory.make_party(db, 'Party B')
        db.execute('INSERT INTO participates(national_id,case_id) VALUES(?,?)', (b, case_id))
        db.execute('INSERT INTO participation_progress(national_id,case_id,position,progress) VALUES(?,?,?,?)', (b, case_id, 'B', 0))
    with app.test_client() as client:
        login(client, b)
        assert client.post(f'/videos/{vid}/analyse', headers={'X-CSRF-Token': 'va-csrf'}).status_code == 403
        assert client.get(f'/videos/{vid}/stream').status_code == 403
        assert client.get(f'/videos/{vid}/analysis-status').status_code == 403


def test_status_page_starts_the_analysis_and_expert_list_shows_it(monkeypatch):
    import siyaq_cv.analyse
    monkeypatch.setattr(siyaq_cv.analyse, 'analyse_video', lambda path, typ: FAKE)
    with module.conn() as db:
        nid, case_id, vid = setup_case(db)
        db.execute('UPDATE participation_progress SET completed=1 WHERE case_id=?', (case_id,))
    with app.test_client() as client:
        login(client, nid)
        page = client.get(f'/cases/{case_id}/steps/7').data.decode()
        assert f'"{vid}"' in page and '/analyse' in page          # the background start for this party's video
        client.post(f'/videos/{vid}/analyse', headers={'X-CSRF-Token': 'va-csrf'})
        # once it is done, the page no longer starts it again
        assert '/analyse' not in client.get(f'/cases/{case_id}/steps/7').data.decode()
    with app.test_client() as expert:
        login_expert(expert)
        listing = expert.get('/expert/cases').data.decode()
        assert f'/videos/{vid}/analysis' in listing and 'اكتمل' in listing


def test_cloudinary_fetch_signs_with_timestamp_and_falls_back(monkeypatch, tmp_path):
    # the private download API rejects a request without a timestamp (HTTP 400); if it still fails,
    # the signed delivery URL is tried
    import io
    from urllib.error import HTTPError
    import video_analysis as va
    for k, x in {'CLOUDINARY_CLOUD_NAME': 'demo', 'CLOUDINARY_API_KEY': 'k', 'CLOUDINARY_API_SECRET': 's'}.items():
        monkeypatch.setenv(k, x)
    monkeypatch.setattr(module, 'cloudinary_metadata', lambda pid: {'format': 'mov'})
    seen = []

    def fake_open(req, timeout=0):
        seen.append(req.full_url)
        if 'api.cloudinary.com' in req.full_url:
            raise HTTPError(req.full_url, 400, 'Bad Request', {}, None)
        return io.BytesIO(b'video-bytes')
    monkeypatch.setattr(va, 'urlopen', fake_open)
    v = {'processed_name': None, 'stored_name': 'cloudinary://siyaq/x', 'original_name': 'a.mp4'}
    path = va.fetch_video(module, v, str(tmp_path))
    assert open(path, 'rb').read() == b'video-bytes'
    assert 'timestamp=' in seen[0] and 'format=mov' in seen[0]
    assert seen[1].startswith('https://res.cloudinary.com/demo/video/authenticated/s--')
