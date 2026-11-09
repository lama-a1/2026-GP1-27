# Sprint 2: automatic analysis of each uploaded dashcam video (detection, tracking, movement, traffic events).
# Runs inside the website (also on Vercel): the engine in siyaq_cv/ uses ONNX + OpenCV optical flow, no PyTorch.
# No traffic rule and no fault percentage here - those belong to Sprint 3.
import json
import os
import tempfile
import time
from datetime import datetime
from urllib.parse import quote, urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from flask import abort, jsonify, redirect, render_template, send_from_directory, url_for

EVENT_AR = {
    'collision': 'لحظة الاصطدام', 'lane_change': 'تغيير مسار', 'sudden_stop': 'توقف مفاجئ للمركبة الأمامية',
    'following_distance': 'مسافة التتابع', 'overtaking': 'تجاوز',
}
VEHICLE_AR = {'A': 'مركبة صاحب الفيديو', 'B': 'المركبة الأخرى في الحادث', 'other': 'مركبة أخرى'}
# measure -> (Arabic label, unit)
MEASURE_AR = {
    'time_s': ('وقت الحدث', 'ث'), 'jolt_score': ('شدة الاهتزاز (z)', ''),
    'b_box_height_frac': ('حجم المركبة في الصورة (ارتفاع/عرض)', ''),
    'b_distance_at_impact_m': ('المسافة عند الاصطدام', 'م'), 'b_distance_1s_before_m': ('المسافة قبل الاصطدام بثانية', 'م'),
    'closing_speed_last_1s_mps': ('سرعة الاقتراب في آخر ثانية', 'م/ث'), 'closing_speed_last_1s_kmh': ('سرعة الاقتراب في آخر ثانية', 'كم/س'),
    'min_ttc_last_1s_s': ('أقل زمن متبقٍ للاصطدام (TTC) في آخر ثانية', 'ث'), 'b_lateral_at_impact_m': ('الإزاحة الجانبية عند الاصطدام', 'م'),
    'a_heading_change_last_1s_deg': ('تغير اتجاه مركبة صاحب الفيديو في آخر ثانية', '°'),
    'direction': ('الاتجاه', ''), 'duration_s': ('المدة', 'ث'),
    'offset_start': ('البعد عن منتصف الصورة في البداية', ''), 'offset_end': ('البعد عن منتصف الصورة في النهاية', ''),
    'lateral_start_m': ('الموقع الجانبي في البداية', 'م'), 'lateral_end_m': ('الموقع الجانبي في النهاية', 'م'),
    'lateral_shift_m': ('مقدار الانتقال الجانبي', 'م'), 'max_lateral_speed_mps': ('أعلى سرعة جانبية', 'م/ث'),
    'mean_box_flow_dx_px': ('الحركة الجانبية بالتدفق البصري (متوسط)', 'بكسل/إطار'),
    'b_distance_start_m': ('المسافة في البداية', 'م'), 'b_distance_end_m': ('المسافة في النهاية', 'م'),
    'seconds_before_collision': ('قبل الاصطدام بـ', 'ث'),
    'heading_change_deg': ('مقدار تغير الاتجاه', '°'), 'max_heading_rate_deg_s': ('أعلى معدل لتغير الاتجاه', '°/ث'),
    'background_shift_px': ('انزياح الخلفية بالتدفق البصري', 'بكسل'), 'b_lateral_start_m': ('موقع المركبة الأخرى الجانبي', 'م'),
    'ttc_at_start_s': ('زمن الاصطدام المتبقي عند البداية', 'ث'), 'min_ttc_s': ('أقل زمن متبقٍ للاصطدام', 'ث'),
    'closing_speed_before_mps': ('سرعة الاقتراب قبل التوقف', 'م/ث'), 'closing_speed_after_mps': ('سرعة الاقتراب بعد التوقف', 'م/ث'),
    'max_closing_speed_mps': ('أعلى سرعة اقتراب', 'م/ث'), 'relative_deceleration_mps2': ('التباطؤ النسبي للمركبة الأمامية', 'م/ث²'),
    'b_distance_m': ('المسافة بين المركبتين', 'م'), 'closing_speed_mps': ('سرعة الاقتراب', 'م/ث'), 'ttc_s': ('الزمن المتبقي للاصطدام', 'ث'),
    'gap_closing_time_s': ('زمن انغلاق المسافة', 'ث'), 'safe_distance': ('مسافة الأمان', ''),
    'side': ('الجانب', ''), 'distance_start_m': ('المسافة في البداية', 'م'), 'distance_end_m': ('المسافة في النهاية', 'م'),
    'mean_rel_speed_mps': ('متوسط السرعة النسبية', 'م/ث'), 'mean_rel_speed_kmh': ('متوسط السرعة النسبية', 'كم/س'),
    'crossed_line_side': ('خط المسار الذي قُطع (من جهة مركبة صاحب الفيديو)', ''),
    'crossed_line_type': ('نوع الخط المقطوع', ''),
    'crossed_line_frames': ('عدد الإطارات التي حُدد فيها نوع الخط', ''),
    'crossed_line_solid_share': ('نسبة الإطارات التي ظهر فيها الخط متصلًا', ''),
}
VALUE_AR = {'left': 'يسار', 'right': 'يمين', 'Maintained': 'محافظ عليها', 'Not maintained': 'غير محافظ عليها',
            'approaching': 'تقترب', 'moving away': 'تبتعد', 'steady gap': 'مسافة ثابتة', 'moving left': 'تتحرك يسارًا',
            'moving right': 'تتحرك يمينًا', 'same position': 'لا حركة جانبية', 'car': 'سيارة', 'bus': 'حافلة', 'truck': 'شاحنة',
            'Solid': 'متصل', 'Dashed': 'متقطع', 'Unclear': 'غير واضح',
            'dark_or_night': 'إضاءة منخفضة أو ليل', 'blurred': 'صورة غير واضحة'}


def register(app, h):
    """h = the app module (conn, VIDEO_SQL, get_case, current_user, ...)."""
    from functools import wraps
    from flask import session

    def is_expert():
        return bool(session.get('expert_authenticated'))

    def load_video(video_id, owner_ok=True):
        # experts can open every analysis; a party can only reach the analysis of their own video
        # (the other party's video stays private, and the analysis page itself is for the expert)
        with h.conn() as c:
            v = c.execute(h.VIDEO_SQL + ' WHERE v.video_id=?', (video_id,)).fetchone()
            if not v:
                abort(404)
            case = h.get_case(c, v['case_id'])
        if is_expert():
            return dict(v), case
        if owner_ok and session.get('uid') and h.current_user() is not None and v['national_id'] == session.get('uid'):
            return dict(v), case
        abort(403)

    def expert_or_party(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not is_expert() and (not session.get('uid') or h.current_user() is None):
                return redirect(url_for('expert_login'))
            return fn(*args, **kwargs)
        return wrapped

    def case_analysis(case_id):
        """Analysis state of all videos in a case, for the party timeline and the expert list."""
        with h.conn() as c:
            rows = c.execute(
                'SELECT v.video_id, v.national_id, v.camera_type, pp.position, a.status, a.started_at '
                'FROM dashcam_video v '
                'LEFT JOIN participation_progress pp ON pp.case_id=v.case_id AND pp.national_id=v.national_id '
                'LEFT JOIN video_analysis a ON a.video_id=v.video_id '
                'WHERE v.case_id=? ORDER BY pp.position', (case_id,)).fetchall()
        videos = []
        for r in rows:
            st = r['status'] or 'none'
            if st == 'running' and _age_s(r['started_at']) >= 330:     # the run was cut off (time limit)
                st = 'failed'
            videos.append({'video_id': r['video_id'], 'position': r['position'], 'camera': r['camera_type'], 'status': st})
        states = {v['status'] for v in videos}
        state = ('none' if not videos else 'done' if states == {'done'} else 'failed' if 'failed' in states
                 else 'running' if 'running' in states else 'none')
        return {'videos': videos, 'state': state}

    app.jinja_env.globals['case_analysis'] = case_analysis

    @app.get('/videos/<int:video_id>/analysis')
    @expert_or_party
    def video_analysis_page(video_id):
        if not is_expert():
            abort(403)                                          # parties don't see the technical analysis
        v, case = load_video(video_id)
        with h.conn() as c:
            row = c.execute('SELECT * FROM video_analysis WHERE video_id=?', (video_id,)).fetchone()
        row = dict(row) if row else None
        result = json.loads(row['result_json']) if row and row.get('result_json') else None
        story = None
        if result:
            # what the "what happened before the impact" charts need (events without their thumbnails)
            keep = ('direction', 'side', 'safe_distance', 'b_distance_m', 'crossed_line_type')
            story = {'events': [dict({k: e.get(k) for k in ('type', 'vehicle', 'start_t', 'end_t')},
                                     m={k: v for k, v in (e.get('measures') or {}).items() if k in keep})
                                for e in result.get('events', [])],
                     'chart': result.get('chart') or {}, 'labels': EVENT_AR, 'vehicles': VEHICLE_AR,
                     'lanes': {k: (result.get('lane_markings') or {}).get(k) for k in ('left_line', 'right_line')},
                     'lateral': {k: m.get('lateral_m') for k, m in result.get('measures_b', {}).items()}}
        return render_template('video_analysis.html', v=v, case=case, row=row, result=result, story=story,
                               event_ar=EVENT_AR, vehicle_ar=VEHICLE_AR, measure_ar=MEASURE_AR, value_ar=VALUE_AR)

    @app.post('/videos/<int:video_id>/analyse')
    @expert_or_party
    def video_analyse(video_id):
        v, case = load_video(video_id)
        with h.conn() as c:
            row = c.execute('SELECT status, started_at FROM video_analysis WHERE video_id=?', (video_id,)).fetchone()
            if row and row['status'] == 'done' and not is_expert():
                return jsonify(status='done')                   # a party never re-runs a finished analysis
            if row and row['status'] == 'running' and row['started_at'] and _age_s(row['started_at']) < 330:
                return jsonify(status='running')
            if row:
                c.execute("UPDATE video_analysis SET status='running', error=NULL, started_at=? WHERE video_id=?", (_now(), video_id))
            else:
                c.execute("INSERT INTO video_analysis(video_id,status,started_at) VALUES(?,?,?)", (video_id, 'running', _now()))
            c.execute("UPDATE video_processing SET job_status='running', updated_at=? WHERE video_id=?", (_now(), video_id))
        try:
            with tempfile.TemporaryDirectory(prefix='siyaq_') as tmp:
                path = fetch_video(h, v, tmp)
                from siyaq_cv.analyse import analyse_video
                result = analyse_video(path, case['accident_type'])      # accident type = the user's choice
            with h.conn() as c:
                save_result(h, c, video_id, result)
                c.execute("UPDATE video_processing SET job_status='done', job_details=NULL, updated_at=? WHERE video_id=?", (_now(), video_id))
            return jsonify(status='done')
        except Exception as e:
            app.logger.exception('Video analysis failed')
            with h.conn() as c:
                c.execute("UPDATE video_analysis SET status='failed', error=?, finished_at=? WHERE video_id=?",
                          (type(e).__name__ + ': ' + str(e)[:300], _now(), video_id))
                c.execute("UPDATE video_processing SET job_status='failed', job_details=?, updated_at=? WHERE video_id=?",
                          (type(e).__name__, _now(), video_id))
            return jsonify(status='failed'), 500

    @app.get('/videos/<int:video_id>/analysis-status')
    @expert_or_party
    def video_analysis_status(video_id):
        load_video(video_id)
        with h.conn() as c:
            row = c.execute('SELECT status FROM video_analysis WHERE video_id=?', (video_id,)).fetchone()
        return jsonify(status=row['status'] if row else None)

    @app.get('/videos/<int:video_id>/stream')
    @expert_or_party
    def video_stream(video_id):
        v, case = load_video(video_id)
        stored = v['processed_name'] or v['stored_name']
        public_id = h.stored_cloudinary_id(stored)
        if public_id:
            if not h.cloudinary_ready():
                abort(503)
            return redirect(cloudinary_video_url(public_id))
        key = h.stored_s3_key(stored)
        if key:
            if not h.storage_ready():
                abort(503)
            return redirect(h.storage_client().generate_presigned_url(
                'get_object', Params={'Bucket': os.environ['S3_BUCKET'], 'Key': key}, ExpiresIn=600))
        if os.getenv('VERCEL'):
            abort(404)
        return send_from_directory(h.UPLOAD, stored, conditional=True)


def _now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def _age_s(text):
    try:
        return (datetime.utcnow() - datetime.strptime(text, '%Y-%m-%d %H:%M:%S')).total_seconds()
    except (TypeError, ValueError):
        return 1e9


def fetch_video(h, v, folder):
    """Copy the stored video to a temporary file (the API secret is only used here, on the server)."""
    stored = v['processed_name'] or v['stored_name']
    name = v['original_name'] or 'video.mp4'
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else 'mp4'
    dest = os.path.join(folder, 'video.' + ext)
    public_id = h.stored_cloudinary_id(stored)
    if public_id:
        # the format Cloudinary stored (it can differ from the uploaded file name), then two ways to get the file:
        # 1) the private download API (needs a timestamp in the signature), 2) the signed delivery URL
        try:
            fmt = h.cloudinary_metadata(public_id).get('format') or ext
        except Exception:
            fmt = ext
        errors = []
        for url in (cloudinary_download_url(h, public_id, fmt), cloudinary_video_url(public_id, fmt)):
            try:
                with urlopen(Request(url), timeout=120) as r, open(dest, 'wb') as out:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                return dest
            except HTTPError as e:
                errors.append(f"{e.code} {e.headers.get('X-Cld-Error') or e.reason}")
        raise RuntimeError('Cloudinary: ' + ' | '.join(errors))
    key = h.stored_s3_key(stored)
    if key:
        h.storage_client().download_file(os.environ['S3_BUCKET'], key, dest)
        return dest
    return str(h.UPLOAD / stored)


def cloudinary_download_url(h, public_id, fmt):
    """Private download URL (Cloudinary Admin API), valid for 10 minutes."""
    now = int(time.time())
    params = {'public_id': public_id, 'format': fmt, 'type': 'authenticated', 'timestamp': now, 'expires_at': now + 600}
    params.update(api_key=os.environ['CLOUDINARY_API_KEY'], signature=h.cloudinary_sign(params))
    return ('https://api.cloudinary.com/v1_1/' + quote(os.environ['CLOUDINARY_CLOUD_NAME'], safe='') +
            '/video/download?' + urlencode(params))


def cloudinary_video_url(public_id, fmt='mp4'):
    """Signed delivery URL for an authenticated video, converted to mp4 so every browser can play it."""
    import base64
    import hashlib
    to_sign = public_id + '.' + fmt
    sig = base64.urlsafe_b64encode(hashlib.sha1((to_sign + os.environ['CLOUDINARY_API_SECRET']).encode()).digest())[:8].decode()
    return ('https://res.cloudinary.com/' + quote(os.environ['CLOUDINARY_CLOUD_NAME'], safe='') +
            '/video/authenticated/s--' + sig + '--/' + quote(public_id) + '.' + fmt)


def save_result(h, c, video_id, result):
    """Save the full result, and the events in the EER tables (DETECTED_EVENT, DETECTED_VEHICLE, INVOLVEMENT,
    BOUNDING_BOX) so later sprints can use them."""
    old = c.execute('SELECT event_id FROM detected_event WHERE video_id=?', (video_id,)).fetchall()
    for e in old:
        dv = c.execute('SELECT detected_vehicle_id FROM involvement WHERE event_id=?', (e['event_id'],)).fetchall()
        c.execute('DELETE FROM detected_event WHERE event_id=?', (e['event_id'],))
        for d in dv:
            c.execute('DELETE FROM detected_vehicle WHERE detected_vehicle_id=?', (d['detected_vehicle_id'],))
    tracks = result.get('tracks', {})
    for e in result['events']:
        event_id = h.insert_id(c, '''INSERT INTO detected_event(event_type,event_value,start_time,end_time,video_id)
                                     VALUES(?,?,?,?,?)''',
                               (e['type'], json.dumps(e['measures'], ensure_ascii=False), e['start_t'], e['end_t'], video_id),
                               key='event_id')
        tid = e.get('track_id')
        boxes = [b for b in tracks.get(str(tid), []) if e['start'] <= b[0] <= e['end']] if tid is not None else []
        if boxes:
            dv = h.insert_id(c, 'INSERT INTO detected_vehicle(vehicle_id) VALUES(NULL)', (), key='detected_vehicle_id')
            role = 'Vehicle B' if e['vehicle'] == 'B' else 'Other vehicle'
            c.execute('INSERT INTO involvement(event_id,detected_vehicle_id,vehicle_role,track_id) VALUES(?,?,?,?)',
                      (event_id, dv, role, str(tid)))
            for b in (boxes[0], boxes[-1]) if len(boxes) > 1 else boxes:
                c.execute('INSERT INTO bounding_box(event_id,vehicle_role,bounding_box) VALUES(?,?,?)',
                          (event_id, role, json.dumps({'frame': b[0], 'box': b[1:]})))
    c.execute("UPDATE video_analysis SET status='done', result_json=?, engine_version=?, error=NULL, finished_at=? WHERE video_id=?",
              (json.dumps(result, ensure_ascii=False), result.get('version'), _now(), video_id))
