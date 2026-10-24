import os, re, sqlite3, secrets, uuid, json, time, hmac, hashlib, smtplib, ssl
from urllib.request import Request, urlopen
from urllib.parse import quote, urlencode
import base64
from urllib.error import HTTPError, URLError
from email.message import EmailMessage
from html import escape as html_escape
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE=Path(__file__).resolve().parent
from dotenv import load_dotenv
load_dotenv(BASE / ".env")
app=Flask(__name__)
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY', secrets.token_hex(32)), MAX_CONTENT_LENGTH=200*1024*1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE')=='1')
DATABASE_URL=os.getenv('DATABASE_URL','').strip()
DB=Path(os.getenv('DATABASE_PATH', '/tmp/siyaq.db' if os.getenv('VERCEL') else str(BASE/'siyaq.db')))
UPLOAD=Path('/tmp/siyaq_uploads') if os.getenv('VERCEL') else BASE/'uploads'
UPLOAD.mkdir(parents=True,exist_ok=True)
ALLOWED={'mp4','mov','avi','webm','mkv'}
VIDEO_MAX_BYTES = 200 * 1024 * 1024
VIDEO_MIME = {'mp4':'video/mp4','mov':'video/quicktime','avi':'video/x-msvideo','webm':'video/webm','mkv':'video/x-matroska'}

def cloudinary_ready():
    return all(os.getenv(k, '').strip() for k in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'))

def cloudinary_sign(params):
    values = '&'.join(f'{key}={params[key]}' for key in sorted(params))
    return hashlib.sha1((values + os.environ['CLOUDINARY_API_SECRET']).encode('utf-8')).hexdigest()

def cloudinary_metadata(public_id):
    cloud = os.environ['CLOUDINARY_CLOUD_NAME']
    auth = base64.b64encode((os.environ['CLOUDINARY_API_KEY'] + ':' + os.environ['CLOUDINARY_API_SECRET']).encode()).decode()
    url = 'https://api.cloudinary.com/v1_1/' + quote(cloud, safe='') + '/resources/video/authenticated/' + quote(public_id, safe='')
    req = Request(url, headers={'Authorization': 'Basic ' + auth, 'Accept': 'application/json'})
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))

def stored_cloudinary_id(value):
    return value[len('cloudinary://'):] if value and value.startswith('cloudinary://') else None

def storage_ready():
    return bool(os.getenv('S3_BUCKET', '').strip() and os.getenv('AWS_REGION', '').strip()
                and os.getenv('AWS_ACCESS_KEY_ID', '').strip() and os.getenv('AWS_SECRET_ACCESS_KEY', '').strip())

def storage_client():
    import boto3
    return boto3.client('s3', region_name=os.environ['AWS_REGION'])

def stored_s3_key(value):
    return value[5:] if value.startswith('s3://') else None



if DATABASE_URL:
    import psycopg
    from psycopg.rows import dict_row

    class PgConnection:
        def __init__(self):
            self.connection=psycopg.connect(DATABASE_URL, row_factory=dict_row)
        def __enter__(self):
            return self
        def __exit__(self,typ,value,traceback):
            try:
                if typ is None: self.connection.commit()
                else: self.connection.rollback()
            finally:
                self.connection.close()
        def execute(self,sql,params=()):
            return self.connection.execute(sql.replace('?', '%s'),params)
else:
    psycopg=None

def conn():
    if DATABASE_URL:
        return PgConnection()
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def insert_id(c, sql, params, key='id'):
    # insert a row and return its new id
    if DATABASE_URL:
        return c.execute(sql+' RETURNING '+key,params).fetchone()[key]
    return c.execute(sql,params).lastrowid

def init_db():
    # create the EER tables and the supporting tables (see schema.py and database/EER_MAPPING.md)
    import schema
    with conn() as c:
        for statement in schema.statements(bool(DATABASE_URL)):
            c.execute(statement)

# ready-made SELECTs that give each row the names the pages use
USER_SQL='''SELECT national_id AS id, national_id, full_name, date_of_birth AS birth_date, phone, email, password_hash,
    notify_status_change AS notification_status, notify_final_result AS notification_result FROM accident_party'''
CASE_SQL='''SELECT ca.*, ca.case_id AS id, ca.case_id AS reference,
    (SELECT national_id FROM participation_progress WHERE case_id=ca.case_id AND position='A') AS creator_id,
    (SELECT joined_at FROM participation_progress WHERE case_id=ca.case_id AND position='A') AS created_at
    FROM accident_case ca'''
VEHICLE_SQL='''SELECT vehicle_id AS id, vehicle_id, plate_letters, plate_number, plate_letters||' '||plate_number AS plate,
    manufacturer, model, year, color, national_id FROM vehicle'''
VIDEO_SQL='''SELECT v.video_id AS id, v.video_id, v.case_id, v.national_id AS party_id, v.national_id,
    v.storage_path AS stored_name, v.camera_type AS camera, v.uploaded_at,
    COALESCE(p.original_name,'video') AS original_name, p.processed_path AS processed_name,
    COALESCE(p.privacy_status,'pending') AS privacy_status, p.note AS processing_note
    FROM dashcam_video v LEFT JOIN video_processing p ON p.video_id=v.video_id'''
OPPOSITE={'FRONT':'REAR','REAR':'FRONT'}

def get_party(c, case, national_id):
    # one party of a case, with the same field names the pages used before
    if not national_id: return None
    row=c.execute('''SELECT pp.*, ap.full_name, ap.phone FROM participation_progress pp
        JOIN accident_party ap ON ap.national_id=pp.national_id WHERE pp.case_id=? AND pp.national_id=?''',
        (case['case_id'],national_id)).fetchone()
    if not row: return None
    party=dict(row)
    a=party['position']=='A'
    party.update(id=row['national_id'], user_id=row['national_id'],
                 description=case['party_a_description'] if a else case['party_b_description'],
                 vehicle_role=case['party_a_position'] if a else OPPOSITE.get(case['party_a_position']))
    return party

def party_at(c, case, position):
    # the party in position A or B (None if B did not join yet)
    row=c.execute('SELECT national_id FROM participation_progress WHERE case_id=? AND position=?',(case['case_id'],position)).fetchone()
    return get_party(c,case,row['national_id']) if row else None

def get_case(c, case_id):
    return c.execute(CASE_SQL+' WHERE ca.case_id=?',(case_id,)).fetchone()

def party_vehicle(c, case_id, national_id):
    # the vehicle this party added to the case (Involves)
    return c.execute('''SELECT v.vehicle_id AS id, v.vehicle_id, v.plate_letters, v.plate_number, v.plate_letters||' '||v.plate_number AS plate,
        v.manufacturer, v.model, v.year, v.color, v.national_id FROM involves i JOIN vehicle v ON v.vehicle_id=i.vehicle_id
        WHERE i.case_id=? AND v.national_id=?''',(case_id,national_id)).fetchone()

def user_cases(c, national_id):
    return c.execute(CASE_SQL+''' WHERE ca.case_id IN (SELECT case_id FROM participates WHERE national_id=?)
        ORDER BY created_at DESC''',(national_id,)).fetchall()

# the 3 case statuses shown to users: pending, in progress, completed
STATUS_LABELS={'pending':'قيد الانتظار','in_progress':'قيد المراجعة','completed':'مكتملة'}
def status_key(raw):
    # get the status of a case (anything not in progress or completed counts as pending)
    return {'submitted':'in_progress','in_progress':'in_progress','approved':'completed','completed':'completed'}.get(raw or '','pending')
app.jinja_env.filters['status_key']=status_key
app.jinja_env.filters['status_label']=lambda raw: STATUS_LABELS[status_key(raw)]

# after 5 wrong passwords, login is locked for 15 minutes
LOGIN_MAX_FAILS=5
LOGIN_LOCK_SECONDS=15*60
def login_locked(key):
    with conn() as c:
        row=c.execute('SELECT locked_until FROM login_attempt WHERE key=?',(key,)).fetchone()
    return bool(row and row['locked_until'] and row['locked_until']>time.time())
def login_failed(key):
    with conn() as c:
        row=c.execute('SELECT count FROM login_attempt WHERE key=?',(key,)).fetchone()
        count=(row['count'] if row else 0)+1
        locked=time.time()+LOGIN_LOCK_SECONDS if count>=LOGIN_MAX_FAILS else None
        c.execute('INSERT INTO login_attempt(key,count,locked_until) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET count=excluded.count,locked_until=excluded.locked_until',
                  (key,0 if locked else count,locked))
def login_succeeded(key):
    with conn() as c: c.execute('DELETE FROM login_attempt WHERE key=?',(key,))
LOCKED_MSG='تم إيقاف تسجيل الدخول مؤقتًا بسبب محاولات متكررة غير صحيحة. يمكن المحاولة مرة أخرى بعد 15 دقيقة.'

def csrf():
    if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(32)
    return session['csrf']
app.jinja_env.globals['csrf_token']=csrf
@app.before_request
def protect():
    if request.method in ('POST','PUT','PATCH','DELETE'):
        expected=session.get('csrf','')
        supplied=request.form.get('csrf_token','') or request.headers.get('X-CSRF-Token','')
        if not expected or not secrets.compare_digest(supplied, expected): abort(400,'Invalid CSRF token. Refresh and retry.')

@app.after_request
def no_cache_for_pages(resp):
    if request.endpoint!='static':
        resp.headers['Cache-Control']='no-store'
    return resp

def login_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('uid') or current_user() is None:
            session.pop('uid',None)
            flash('انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.','error')
            return redirect(url_for('login',next=request.path))
        return fn(*args,**kwargs)
    return wrapped

def current_user():
    if not session.get('uid'): return None
    with conn() as c: return c.execute(USER_SQL+' WHERE national_id=?',(session['uid'],)).fetchone()
@app.context_processor
def globals_ctx(): return {'user':current_user(), 'expert_logged_in': bool(session.get('expert_authenticated'))}

def case_access(case_id):
    # the case and the logged-in user's party in it (403 if they are not in the case)
    with conn() as c:
        case=get_case(c,case_id)
        if not case: abort(404)
        party=get_party(c,case,session.get('uid'))
        if not party and case['creator_id']!=session.get('uid'): abort(403)
        return case,party

@app.get('/')
def home():
    if session.get('expert_authenticated'):
        return redirect(url_for('expert_cases'))
    if current_user():
        return redirect(url_for('dashboard'))
    return render_template('home.html')
def normalized_digits(value):
    return str(value).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')).strip()

def otp_digest(code, email):
    key=app.secret_key.encode() if isinstance(app.secret_key,str) else app.secret_key
    return hmac.new(key, f"{email.lower()}:{code}".encode(), hashlib.sha256).hexdigest()

def branded_email_html(kicker, title, description, panel_html, footer_note):
    # the design of the emails we send (logo, colors, Arabic layout)
    base=os.getenv('PUBLIC_BASE_URL','https://siyaq-plum.vercel.app').strip().rstrip('/')
    logo_url=html_escape(base+'/static/siyaq-email-logo.png',quote=True) if re.fullmatch(r'https://[^\s/]+',base) else ''
    brand_logo=(f'<img src="{logo_url}" alt="سياق | SIYAQ" width="134" height="60" style="display:block;max-width:134px;height:auto;margin:auto;" />' if logo_url else 'سياق | SIYAQ')
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f3f6f4;font-family:Tahoma,Arial,sans-serif;color:#17382a;direction:rtl;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f3f6f4;"><tr><td align="center" style="padding:38px 14px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:570px;background:#ffffff;border:1px solid #e0e9e3;border-radius:18px;overflow:hidden;">
<tr><td align="center" style="background:#006b36;padding:30px 26px;">
<div style="display:inline-block;background:#ffffff;border-radius:12px;padding:8px 20px;">{brand_logo}</div>
<div style="color:#d8f1e1;font-size:12px;margin-top:6px;">منصة سياق لإدارة بلاغات الحوادث المرورية</div>
</td></tr>
<tr><td style="padding:35px 34px 22px;direction:rtl;text-align:right;">
<div style="color:#007342;font-size:12px;font-weight:bold;margin-bottom:12px;">{html_escape(kicker)}</div>
<h1 style="font-size:25px;line-height:1.6;margin:0 0 12px;color:#123d2b;">{html_escape(title)}</h1>
<p style="font-size:15px;line-height:2;margin:0 0 25px;color:#52675c;">{html_escape(description)}</p>
{panel_html}
<p style="font-size:13px;line-height:1.9;color:#697c71;margin:24px 0 0;">{html_escape(footer_note)}</p>
</td></tr>
<tr><td align="center" style="border-top:1px solid #e5ece7;padding:23px 24px;background:#fafcfb;color:#819187;font-size:12px;line-height:1.9;">
هذه رسالة تلقائية من سياق — يُرجى عدم الرد على هذا البريد.<br>
في حال وصول الرسالة بالخطأ، يمكن تجاهلها بأمان.<br>
<span dir="ltr" style="color:#006b36;font-weight:bold;">SIYAQ • سياق</span>
</td></tr></table></td></tr></table></body></html>"""


def otp_email_html(code):
    safe_code=html_escape(str(code))
    panel=(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0f8f3;border:1px solid #d8eadd;border-radius:12px;"><tr><td align="center" style="padding:22px 14px;">'
           f'<div style="font-size:12px;color:#587563;margin-bottom:8px;">رمز التحقق الخاص بك</div>'
           f'<div dir="ltr" style="font-family:Arial,sans-serif;font-size:35px;font-weight:800;letter-spacing:9px;color:#006b36;">{safe_code}</div>'
           f'<div style="font-size:12px;color:#587563;margin-top:12px;">صالح لمدة 10 دقائق</div>'
           f'</td></tr></table>')
    return branded_email_html('التحقق من البريد الإلكتروني','تأكيد بريدك الإلكتروني',
                              'يُستخدم الرمز التالي لإكمال إنشاء الحساب في سياق.',panel,
                              'لأمان الحساب، يُرجى عدم مشاركة رمز التحقق مع أي شخص.')


def invitation_email_html(link, reference):
    safe_link=html_escape(str(link),quote=True)
    safe_ref=html_escape(str(reference))
    panel=(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f8f5;border:1px solid #e1eae4;border-radius:12px;">'
           f'<tr><td style="padding:16px 18px;text-align:right;">'
           f'<div style="color:#718678;font-size:12px;">رقم البلاغ</div>'
           f'<div dir="ltr" style="text-align:right;color:#153d2b;font-weight:bold;font-size:17px;margin-top:6px;">{safe_ref}</div>'
           f'</td></tr></table>'
           f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr><td align="center" style="padding:26px 0 14px;">'
           f'<a href="{safe_link}" style="display:inline-block;background:#006b36;color:#ffffff;text-decoration:none;font-weight:bold;font-size:16px;padding:16px 30px;border-radius:9px;">الانضمام إلى البلاغ</a>'
           f'</td></tr></table>'
           f'<div style="color:#6d8175;font-size:12px;line-height:1.9;overflow-wrap:anywhere;word-break:break-word;">في حال تعذّر فتح الزر، يُرجى نسخ الرابط التالي ولصقه في المتصفح:<br><a href="{safe_link}" style="color:#006b36;text-decoration:underline;" dir="ltr">{safe_link}</a></div>')
    return branded_email_html('دعوة للمشاركة في بلاغ حادث','دعوة للانضمام إلى بلاغ حادث مروري',
                              'السلام عليكم، تمت إضافتك بصفتك الطرف الثاني في بلاغ حادث مروري مسجّل على منصة سياق. نأمل منكم الانضمام إلى البلاغ عبر الزر أدناه، ثم تسجيل الدخول أو إنشاء حساب باستخدام هذا البريد الإلكتروني، لاستكمال بياناتكم وإفادتكم وإرفاق فيديو الحادث إن وُجد.',
                              panel,'هذه الدعوة مخصّصة لصاحب هذا البريد الإلكتروني وتُستخدم مرة واحدة فقط، ويُرجى عدم مشاركتها مع أي طرف آخر. لن تُعرض تفاصيل البلاغ إلا بعد التحقق من الحساب.')


def send_brevo_api_email(email, subject, body, html_body=None):
    # send an email through Brevo
    api_key=os.getenv('BREVO_API_KEY','').strip()
    sender=os.getenv('BREVO_SENDER_EMAIL',os.getenv('SMTP_FROM','')).strip()
    sender_name=os.getenv('BREVO_SENDER_NAME','Siyaq').strip() or 'Siyaq'
    if not api_key or not sender:
        raise RuntimeError('إعدادات Brevo API غير مكتملة. يلزم إضافة BREVO_API_KEY و BREVO_SENDER_EMAIL إلى ملف .env.')
    payload={
        'sender':{'name':sender_name,'email':sender},
        'to':[{'email':email}],
        'subject':subject,
        'textContent':body,
    }
    if html_body:
        payload['htmlContent']=html_body
    req=Request(
        'https://api.brevo.com/v3/smtp/email',
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers={'api-key':api_key,'Content-Type':'application/json','accept':'application/json'},
        method='POST',
    )
    try:
        with urlopen(req,timeout=20) as response:
            if response.status not in (200,201,202):
                raise RuntimeError('تعذّر إرسال البريد عبر Brevo API.')
    except HTTPError as exc:
        app.logger.warning('Brevo API rejected email (HTTP %s)',exc.code)
        raise RuntimeError('تعذّر إرسال البريد عبر Brevo API (HTTP '+str(exc.code)+'). يُرجى مراجعة تفعيل API والمرسل وعناوين IP المسموحة.') from exc
    except (URLError,TimeoutError,OSError) as exc:
        app.logger.warning('Brevo API network error: %s',type(exc).__name__)
        raise RuntimeError('تعذّر الاتصال بخدمة Brevo API. يُرجى التحقق من الاتصال بالإنترنت والمحاولة مجددًا.') from exc


def send_email_otp(email, code):
    # email the user the verification code
    body=(f'رمز التحقق من حساب سياق: {code}\nصلاحية الرمز 10 دقائق. يُرجى عدم مشاركة هذا الرمز مع أي شخص.\n\n'
          f'Siyaq verification code: {code}\nExpires in 10 minutes.')
    if os.getenv('OTP_MODE','api').strip().lower()=='api':
        return send_brevo_api_email(email,'Siyaq | رمز التحقق من البريد الإلكتروني',body,otp_email_html(code))
    host=os.getenv('SMTP_HOST','').strip()
    username=os.getenv('SMTP_USER','').strip()
    password=os.getenv('SMTP_PASSWORD','').strip()
    sender=os.getenv('SMTP_FROM',username).strip()
    port=int(os.getenv('SMTP_PORT','587'))
    if not all((host,username,password,sender)):
        raise RuntimeError('إعدادات SMTP غير مكتملة. يُرجى مراجعة ملف .env.')
    msg=EmailMessage()
    msg['Subject']='Siyaq | رمز التحقق من البريد الإلكتروني'
    msg['From']=sender
    msg['To']=email
    msg.set_content(body)
    msg.add_alternative(otp_email_html(code),subtype='html')
    try:
        if port==465:
            with smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context()) as smtp:
                smtp.login(username,password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host,port,timeout=20) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(username,password)
                smtp.send_message(msg)
    except (smtplib.SMTPException,OSError) as exc:
        app.logger.warning('SMTP send failed: %s',type(exc).__name__)
        raise RuntimeError('تعذّر إرسال رمز البريد. يُرجى التحقق من إعدادات SMTP.') from exc


def send_case_invitation(email, link, reference):
    # email the second party the link to join the case
    body=(
        'السلام عليكم،\n\nتمت إضافتكم بصفتكم الطرف الثاني في بلاغ حادث مروري مسجّل على منصة سياق.\n'
        'رقم البلاغ: '+reference+'\n\n'
        'نأمل منكم الانضمام إلى البلاغ عبر الرابط التالي، وتسجيل الدخول أو إنشاء حساب باستخدام هذا البريد الإلكتروني لاستكمال بياناتكم وإفادتكم:\n'
        +link+'\n\n'
        'هذه الدعوة مخصّصة لصاحب هذا البريد وتُستخدم مرة واحدة فقط. في حال وصلتكم هذه الرسالة عن طريق الخطأ، يمكنكم تجاهلها.\n\nمع التحية،\nفريق منصة سياق'
    )
    if os.getenv('OTP_MODE','api').strip().lower()=='api':
        return send_brevo_api_email(email,'Siyaq | دعوة للمشاركة في بلاغ حادث',body,invitation_email_html(link,reference))
    host=os.getenv('SMTP_HOST','').strip()
    username=os.getenv('SMTP_USER','').strip()
    password=os.getenv('SMTP_PASSWORD','').strip()
    sender=os.getenv('SMTP_FROM',username).strip()
    port=int(os.getenv('SMTP_PORT','587'))
    if not all((host,username,password,sender)):
        raise RuntimeError('إعدادات SMTP غير مكتملة. يُرجى مراجعة ملف .env.')
    msg=EmailMessage()
    msg['Subject']='Siyaq | دعوة للمشاركة في بلاغ حادث'
    msg['From']=sender
    msg['To']=email
    msg.set_content(body)
    msg.add_alternative(invitation_email_html(link,reference),subtype='html')
    try:
        if port==465:
            with smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context()) as smtp:
                smtp.login(username,password); smtp.send_message(msg)
        else:
            with smtplib.SMTP(host,port,timeout=20) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(username,password); smtp.send_message(msg)
    except (smtplib.SMTPException,OSError) as exc:
        app.logger.warning('Invitation SMTP send failed: %s',type(exc).__name__)
        raise RuntimeError('تعذّر إرسال الدعوة. يُرجى التحقق من إعدادات SMTP.') from exc

# case status emails (sent only to users who turned on "status updates" in their settings)
STATUS_EMAILS={
    'joined':('انضمام الطرف الثاني','انضم الطرف الثاني إلى البلاغ',
              'انضم الطرف الثاني إلى البلاغ، وسيستكمل بياناته وإفادته. سيصلك إشعار عند تغيّر حالة البلاغ.'),
    'in_progress':('تحديث حالة البلاغ','البلاغ الآن قيد المراجعة',
                   'أرسل الطرفان بياناتهما، وأصبح البلاغ قيد المراجعة. لا يمكن تعديل البيانات في هذه المرحلة.'),
    'completed':('تحديث حالة البلاغ','اكتملت مراجعة البلاغ',
                 'اكتملت مراجعة البلاغ، ويمكن الاطلاع على النتيجة من صفحة البلاغ في سياق.'),
}

def status_email_html(kind, reference, link):
    kicker,title,description=STATUS_EMAILS[kind]
    safe_link=html_escape(str(link),quote=True)
    panel=(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f8f5;border:1px solid #e1eae4;border-radius:12px;">'
           f'<tr><td style="padding:16px 18px;text-align:right;">'
           f'<div style="color:#718678;font-size:12px;">رقم البلاغ</div>'
           f'<div dir="ltr" style="text-align:right;color:#153d2b;font-weight:bold;font-size:17px;margin-top:6px;">{html_escape(str(reference))}</div>'
           f'</td></tr></table>'
           f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr><td align="center" style="padding:26px 0 14px;">'
           f'<a href="{safe_link}" style="display:inline-block;background:#006b36;color:#ffffff;text-decoration:none;font-weight:bold;font-size:16px;padding:16px 30px;border-radius:9px;">عرض البلاغ</a>'
           f'</td></tr></table>')
    return branded_email_html(kicker,title,description,panel,
                              'يمكن إيقاف هذه الإشعارات من إعدادات الحساب في سياق.')

def send_status_email(email, kind, reference, link):
    # email one user about a change in their case
    kicker,title,description=STATUS_EMAILS[kind]
    subject='Siyaq | '+title
    body=title+'\nرقم البلاغ: '+str(reference)+'\n\n'+description+'\n\n'+link+'\n\nيمكن إيقاف هذه الإشعارات من إعدادات الحساب في سياق.'
    html=status_email_html(kind,reference,link)
    if os.getenv('OTP_MODE','api').strip().lower()=='api':
        return send_brevo_api_email(email,subject,body,html)
    host=os.getenv('SMTP_HOST','').strip(); username=os.getenv('SMTP_USER','').strip()
    password=os.getenv('SMTP_PASSWORD','').strip(); sender=os.getenv('SMTP_FROM',username).strip()
    port=int(os.getenv('SMTP_PORT','587'))
    if not all((host,username,password,sender)): raise RuntimeError('إعدادات البريد غير مكتملة.')
    msg=EmailMessage(); msg['Subject']=subject; msg['From']=sender; msg['To']=email
    msg.set_content(body); msg.add_alternative(html,subtype='html')
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context()) as smtp:
            smtp.login(username,password); smtp.send_message(msg)
    else:
        with smtplib.SMTP(host,port,timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context()); smtp.login(username,password); smtp.send_message(msg)

def notify_case(case_id, kind, only_user_id=None):
    # send the status email to the case parties who turned notifications on
    # (a failed email never stops the user's action, it is only logged)
    if os.getenv('OTP_MODE','api').strip().lower()=='demo':
        return
    with conn() as c:
        case=get_case(c,case_id)
        users=c.execute('''SELECT DISTINCT ap.national_id AS id, ap.email FROM participates p
                           JOIN accident_party ap ON ap.national_id=p.national_id
                           WHERE p.case_id=? AND ap.notify_status_change=1''',(case_id,)).fetchall()
    if not case: return
    public_base=os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/')
    path=url_for('case_detail',case_id=case_id)
    link=public_base+path if re.fullmatch(r'https://[^\s/]+(?:\:[0-9]{2,5})?',public_base) else url_for('case_detail',case_id=case_id,_external=True)
    for u in users:
        if only_user_id is not None and u['id']!=only_user_id: continue
        try: send_status_email(u['email'],kind,case['reference'],link)
        except Exception: app.logger.exception('Status email failed')

def safe_invitation_next(value):
    return bool(re.fullmatch(r'/invite/[A-Za-z0-9_-]{20,100}', value or ''))

def issue_otp(pending):
    code=f'{secrets.randbelow(1000000):06d}'
    mode=os.getenv('OTP_MODE','api').strip().lower()
    if mode=='demo':
        # demo mode shows the code on screen, so it only works on our own computer
        if request.remote_addr not in ('127.0.0.1','::1'):
            raise RuntimeError('وضع التجربة متاح محليًا فقط. يلزم تفعيل إرسال البريد الحقيقي.')
        pending['demo_code']=code
    elif mode in ('smtp','api'):
        send_email_otp(pending['email'],code)
        pending.pop('demo_code',None)
    else:
        raise RuntimeError('OTP_MODE يجب أن يكون api أو smtp أو demo.')
    pending['otp_digest']=otp_digest(code,pending['email'])
    pending['last_sent']=time.time()
    pending['attempts']=0
    return pending

MIN_AGE=18
def age_on(birth_date, today=None):
    today=today or datetime.now().date()
    return today.year-birth_date.year-((today.month,today.day)<(birth_date.month,birth_date.day))

def registration_errors(name,nid,phone,birth,password,confirm):
    errors=[]
    if len(name.split())<3: errors.append('الاسم الثلاثي مطلوب (الاسم الأول واسم الأب واسم العائلة).')
    if not re.fullmatch(r'[12]\d{9}',nid): errors.append('رقم الهوية / الإقامة يجب أن يبدأ بـ 1 أو 2 ويتكون من 10 أرقام.')
    if not re.fullmatch(r'05\d{8}',phone): errors.append('رقم الجوال يجب أن يبدأ بـ 05 ويتكون من 10 أرقام.')
    if not birth: errors.append('تاريخ الميلاد مطلوب.')
    else:
        try:
            born=datetime.strptime(birth,'%Y-%m-%d').date()
            if born>datetime.now().date(): errors.append('تاريخ الميلاد لا يمكن أن يكون في المستقبل.')
            elif age_on(born)<MIN_AGE: errors.append('يجب أن يكون عمرك 18 سنة أو أكثر لإنشاء حساب.')
        except ValueError: errors.append('تاريخ الميلاد غير صالح.')
    if len(password)<8 or not re.search(r'[A-Za-z\u0600-\u06FF]',password) or not re.search(r'\d',password): errors.append('كلمة المرور يجب أن تحتوي على 8 أحرف على الأقل، منها حرف ورقم.')
    if password!=confirm: errors.append('تأكيد كلمة المرور غير مطابق.')
    return errors

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='GET' and safe_invitation_next(request.args.get('next','')):
        session['after_registration']=request.args['next']
    if request.method=='POST':
        name=request.form.get('full_name','').strip()
        nid=normalized_digits(request.form.get('national_id',''))
        phone=normalized_digits(request.form.get('phone',''))
        birth=request.form.get('birth_date','').strip()
        email=request.form.get('email','').strip().lower()
        password=request.form.get('password','')
        errors=registration_errors(name,nid,phone,birth,password,request.form.get('confirm_password',''))
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254: errors.append('البريد الإلكتروني غير صالح.')
        if errors:
            for error in errors: flash(error,'error')
        else:
            with conn() as c:
                taken=[label for col,value,label in (('national_id',nid,'رقم الهوية / الإقامة'),('phone',phone,'رقم الجوال'),('email',email,'البريد الإلكتروني'))
                       if c.execute(f'SELECT 1 FROM accident_party WHERE {col}=?',(value,)).fetchone()]
            if taken: flash(' و'.join(taken)+' مسجل مسبقًا بحساب آخر.','error')
            else:
                try:
                    pending={'full_name':name,'national_id':nid,'phone':phone,'email':email,'birth_date':birth,'password_hash':generate_password_hash(password),'started':time.time(),'attempts':0}
                    session['pending_registration']=issue_otp(pending)
                    return redirect(url_for('verify_email'))
                except RuntimeError as e: flash(str(e),'error')
    return render_template('auth.html',mode='register')

@app.route('/verify-email',methods=['GET','POST'])
def verify_email():
    pending=session.get('pending_registration')
    if not pending: return redirect(url_for('register'))
    if time.time()-pending['started']>1800 or time.time()-pending.get('last_sent',0)>600:
        session.pop('pending_registration',None)
        flash('انتهت مهلة التحقق. يُرجى التسجيل من جديد.','error')
        return redirect(url_for('register'))
    if request.method=='POST':
        action=request.form.get('action','verify')
        if action=='resend':
            if time.time()-pending.get('last_sent',0)<60: flash('يمكن طلب رمز جديد بعد دقيقة.','error')
            else:
                try:
                    session['pending_registration']=issue_otp(pending)
                    flash('تم طلب رمز جديد.','success')
                except RuntimeError as e: flash(str(e),'error')
        else:
            code=normalized_digits(request.form.get('code',''))
            if pending['attempts']>=5: flash('تم تجاوز عدد المحاولات. يُرجى التسجيل من جديد.','error')
            elif not re.fullmatch(r'\d{6}',code): flash('رمز التحقق يتكون من 6 أرقام.','error')
            else:
                pending['attempts']+=1;session['pending_registration']=pending
                try:
                    if hmac.compare_digest(otp_digest(code,pending['email']),pending.get('otp_digest','')):
                        try:
                            with conn() as c:
                                c.execute('INSERT INTO accident_party(national_id,full_name,date_of_birth,phone,email,password_hash) VALUES(?,?,?,?,?,?)',
                                    (pending['national_id'],pending['full_name'],pending['birth_date'],pending['phone'],pending['email'],pending['password_hash']))
                                uid=pending['national_id']
                            destination=session.get('after_registration')
                            session.clear();session['uid']=uid;csrf()
                            return redirect(destination if safe_invitation_next(destination) else url_for('dashboard'))
                        except (sqlite3.IntegrityError, psycopg.IntegrityError if psycopg else sqlite3.IntegrityError): flash('رقم الهوية / الإقامة أو رقم الجوال أو البريد الإلكتروني مسجل مسبقًا بحساب آخر.','error')
                    else: flash('رمز التحقق غير صحيح أو انتهت صلاحيته.','error')
                except RuntimeError as e: flash(str(e),'error')
    return render_template('verify_email.html',email=pending['email'],demo_code=pending.get('demo_code') if os.getenv('OTP_MODE','api').lower()=='demo' else None)

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        nid=normalized_digits(request.form.get('national_id',''))
        key='party:'+nid
        if login_locked(key):
            flash(LOCKED_MSG,'error'); return render_template('auth.html',mode='login')
        with conn() as c:
            u=c.execute(USER_SQL+' WHERE national_id=?',(nid,)).fetchone()
        if u and check_password_hash(u['password_hash'],request.form.get('password','')):
            login_succeeded(key)
            session.clear();session['uid']=u['id'];csrf()
            nxt=request.args.get('next','')
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('dashboard'))
        login_failed(key)
        flash('رقم الهوية الوطنية أو كلمة المرور غير صحيحة.','error')
    return render_template('auth.html',mode='login')
RESET_LINK_MINUTES=30
def send_reset_email(email, link):
    body=('وصلنا طلب لإعادة تعيين كلمة المرور لحسابك في سياق.\n\nلتعيين كلمة مرور جديدة يُرجى فتح الرابط التالي:\n'+link+
          '\n\nالرابط صالح لمدة '+str(RESET_LINK_MINUTES)+' دقيقة ولمرة واحدة. في حال عدم طلب ذلك، يمكن تجاهل الرسالة.')
    panel=(f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr><td align="center" style="padding:10px 0 14px;">'
           f'<a href="{html_escape(link,quote=True)}" style="display:inline-block;background:#006b36;color:#ffffff;text-decoration:none;font-weight:bold;font-size:16px;padding:16px 30px;border-radius:9px;">تعيين كلمة مرور جديدة ←</a>'
           f'</td></tr></table>')
    html=branded_email_html('إعادة تعيين كلمة المرور','طلب تعيين كلمة مرور جديدة',
                            'لتعيين كلمة مرور جديدة لحسابك في سياق، يُرجى استخدام الزر التالي.',panel,
                            'الرابط صالح لمدة '+str(RESET_LINK_MINUTES)+' دقيقة ولمرة واحدة. في حال عدم طلب ذلك، يمكن تجاهل الرسالة.')
    if os.getenv('OTP_MODE','api').strip().lower()=='api':
        return send_brevo_api_email(email,'Siyaq | إعادة تعيين كلمة المرور',body,html)
    host=os.getenv('SMTP_HOST','').strip(); username=os.getenv('SMTP_USER','').strip()
    password=os.getenv('SMTP_PASSWORD','').strip(); sender=os.getenv('SMTP_FROM',username).strip()
    port=int(os.getenv('SMTP_PORT','587'))
    if not all((host,username,password,sender)): raise RuntimeError('إعدادات البريد غير مكتملة.')
    msg=EmailMessage(); msg['Subject']='Siyaq | إعادة تعيين كلمة المرور'; msg['From']=sender; msg['To']=email
    msg.set_content(body); msg.add_alternative(html,subtype='html')
    with smtplib.SMTP(host,port,timeout=20) as smtp:
        smtp.starttls(context=ssl.create_default_context()); smtp.login(username,password); smtp.send_message(msg)

@app.route('/forgot-password',methods=['GET','POST'])
def forgot_password():
    sent=False
    if request.method=='POST':
        nid=normalized_digits(request.form.get('national_id',''))
        with conn() as c: u=c.execute('SELECT national_id AS id,email FROM accident_party WHERE national_id=?',(nid,)).fetchone()
        if u:
            token=secrets.token_urlsafe(32)
            with conn() as c:
                # a new request replaces any earlier unused link
                c.execute('UPDATE password_reset_link SET used_at=? WHERE national_id=? AND used_at IS NULL',(datetime.utcnow().isoformat(),u['id']))
                c.execute('INSERT INTO password_reset_link(national_id,token_hash,expires_at) VALUES(?,?,?)',
                          (u['id'],hashlib.sha256(token.encode()).hexdigest(),time.time()+RESET_LINK_MINUTES*60))
            link=url_for('reset_password',token=token,_external=True)
            if os.getenv('OTP_MODE','api').strip().lower()=='demo' and request.remote_addr in ('127.0.0.1','::1'):
                flash('وضع التجربة (محليًا فقط): رابط إعادة التعيين: '+link,'success')
            else:
                try: send_reset_email(u['email'],link)
                except Exception: app.logger.exception('Password reset email failed')
        sent=True  # same message even if the ID isn't registered, so no one can find out which IDs exist
    return render_template('password_reset.html',stage='request',sent=sent)

@app.route('/reset-password/<token>',methods=['GET','POST'])
def reset_password(token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c: r=c.execute('SELECT * FROM password_reset_link WHERE token_hash=?',(digest,)).fetchone()
    valid=bool(r and not r['used_at'] and r['expires_at']>time.time())
    if not valid:
        return render_template('password_reset.html',stage='invalid')
    if request.method=='POST':
        new=request.form.get('password',''); confirm=request.form.get('confirm_password','')
        if len(new)<8 or not re.search(r'[A-Za-z\u0600-\u06FF]',new) or not re.search(r'\d',new):
            flash('كلمة المرور يجب أن تحتوي على 8 أحرف على الأقل، منها حرف ورقم.','error')
        elif new!=confirm: flash('تأكيد كلمة المرور غير مطابق.','error')
        else:
            with conn() as c:
                c.execute('UPDATE accident_party SET password_hash=? WHERE national_id=?',(generate_password_hash(new),r['national_id']))
                c.execute('UPDATE password_reset_link SET used_at=? WHERE national_id=? AND used_at IS NULL',(datetime.utcnow().isoformat(),r['national_id']))
                nid=r['national_id']
            login_succeeded('party:'+(nid or ''))
            flash('تم تعيين كلمة المرور الجديدة، ويمكن تسجيل الدخول الآن.','success')
            return redirect(url_for('login'))
    return render_template('password_reset.html',stage='reset')

EXPERT_PREFIX='expert_'
@app.route('/expert/register', methods=['GET', 'POST'])
def expert_register():
    if session.get('expert_authenticated'):
        return redirect(url_for('expert_cases'))
    configured_code = os.getenv('EXPERT_REGISTRATION_CODE', '').strip()
    pending = session.get('expert_registration')
    verified = bool(pending and time.time() - pending.get('verified_at', 0) < 600)
    if not verified:
        session.pop('expert_registration', None)
    if request.method == 'POST':
        action = request.form.get('action', 'verify')
        if action == 'verify':
            full_name = request.form.get('full_name', '').strip()
            supplied_code = request.form.get('authorization_code', '').strip()
            if not configured_code or not hmac.compare_digest(supplied_code, configured_code):
                flash('تعذر التحقق من رمز التفويض. يرجى التأكد من البيانات.', 'error')
            elif not 3 <= len(full_name) <= 100:
                flash('يرجى إدخال الاسم الكامل.', 'error')
            else:
                session['expert_registration'] = {'full_name': full_name, 'verified_at': time.time()}
                return redirect(url_for('expert_register'))
        elif action == 'create' and verified:
            suffix = request.form.get('username', '').strip().lower()
            if suffix.startswith(EXPERT_PREFIX): suffix = suffix[len(EXPERT_PREFIX):]
            username = EXPERT_PREFIX + suffix
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,24}', suffix):
                flash('اسم المستخدم بعد expert_ يجب أن يكون من ٣ إلى ٢٥ حرفًا إنجليزيًا أو رقمًا.', 'error')
            elif not 12 <= len(password) <= 128:
                flash('كلمة المرور يجب أن تحتوي على ١٢ حرفًا على الأقل.', 'error')
            elif password != confirm_password:
                flash('كلمتا المرور غير متطابقتين.', 'error')
            else:
                with conn() as c:
                    existing = c.execute('SELECT expert_id FROM authorized_expert WHERE username=?', (username,)).fetchone()
                    if existing:
                        flash('معرّف الخبير مستخدم بالفعل.', 'error')
                    else:
                        c.execute('INSERT INTO authorized_expert(full_name, username, password_hash) VALUES(?,?,?)',
                                  (pending['full_name'], username, generate_password_hash(password)))
                        session.pop('expert_registration', None)
                        flash('تم إنشاء الحساب، ويمكن تسجيل الدخول الآن.', 'success')
                        return redirect(url_for('expert_login'))
        else:
            flash('انتهت صلاحية التحقق. يرجى إعادة المحاولة.', 'error')
    return render_template('expert_register.html', verified=verified, registration_enabled=bool(configured_code))

@app.route('/expert/login', methods=['GET', 'POST'])
def expert_login():
    if session.get('expert_authenticated'):
        return redirect(url_for('expert_cases'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        key = 'expert:' + username
        if login_locked(key):
            flash(LOCKED_MSG, 'error')
            return render_template('expert_login.html')
        with conn() as c:
            expert = c.execute('SELECT expert_id AS id, password_hash FROM authorized_expert WHERE username=?', (username,)).fetchone()
            if not expert and not username.startswith(EXPERT_PREFIX):
                expert = c.execute('SELECT expert_id AS id, password_hash FROM authorized_expert WHERE username=?', (EXPERT_PREFIX+username,)).fetchone()
        valid_registered = bool(expert) and check_password_hash(expert['password_hash'], password)
        expected_username = os.getenv('EXPERT_USERNAME', '').strip().lower()
        expected_hash = os.getenv('EXPERT_PASSWORD_HASH', '').strip()
        valid_legacy = (bool(expected_username) and bool(expected_hash)
                        and hmac.compare_digest(username, expected_username)
                        and check_password_hash(expected_hash, password))
        if valid_registered or valid_legacy:
            login_succeeded(key)
            session.clear()
            session['expert_authenticated'] = True
            if valid_registered:
                session['expert_id'] = expert['id']
            csrf()
            return redirect(url_for('expert_cases'))
        login_failed(key)
        flash('معرّف الخبير أو كلمة المرور غير صحيحة.', 'error')
    return render_template('expert_login.html')

@app.get('/expert/cases')
def expert_cases():
    if not session.get('expert_authenticated'):
        return redirect(url_for('expert_login'))
    with conn() as c:
        cases = c.execute(CASE_SQL+' ORDER BY created_at DESC LIMIT 100').fetchall()
    groups = {k: [x for x in cases if status_key(x['status']) == k] for k in ('pending', 'in_progress', 'completed')}
    return render_template('expert_cases.html', cases=cases, groups=groups)

@app.get('/expert/rules')
def expert_rules():
    if not session.get('expert_authenticated'):
        return redirect(url_for('expert_login'))
    return render_template('expert_rules.html')

@app.post('/expert/logout')
def expert_logout():
    session.clear()
    return redirect(url_for('home'))

@app.post('/logout')
def logout(): session.clear(); return redirect(url_for('home'))
@app.get('/dashboard')
@login_required
def dashboard():
    with conn() as c:
        cases=user_cases(c,session['uid'])
    pending=[x for x in cases if status_key(x['status'])=='pending'][:1]
    return render_template('dashboard.html',cases=cases[:3],pending_cases=pending)
@app.route('/cases/new',methods=['GET','POST'])
@login_required
def new_case():
    if request.method=='POST':
        eligible=all(request.form.get(k)=='yes' for k in ('no_injuries','clear_weather','two_vehicles'))
        if not eligible:
            flash('هذه الحالة خارج نطاق سياق الحالي: الحوادث البسيطة دون إصابات، في ظروف رؤية واضحة ولمركبتين.','error')
            return redirect(url_for('new_case'))
        typ,date,time,location,errors=accident_form(request.form)
        if errors:
            for e in errors: flash(e,'error')
            return render_template('new_case.html',form=request.form)
        else:
            ref='SQ-'+datetime.now().strftime('%y%m')+'-'+secrets.token_hex(3).upper()
            with conn() as c:
                # the case starts as a draft; the car position is chosen later, in the accident description step
                c.execute('INSERT INTO accident_case(case_id,accident_type,accident_date,accident_time,location,status) VALUES(?,?,?,?,?,?)',(ref,typ,date,time,location,'draft'))
                c.execute('INSERT INTO participates(national_id,case_id) VALUES(?,?)',(session['uid'],ref))
                c.execute("INSERT INTO participation_progress(national_id,case_id,position) VALUES(?,?,'A')",(session['uid'],ref))
            return redirect(url_for('wizard',case_id=ref,step=1))
    return render_template('new_case.html',form={})

def accident_form(form,original=None):
    typ=form.get('accident_type'); date=form.get('accident_date','').strip(); time=form.get('accident_time','').strip(); location=form.get('location','').strip()
    errors=[]
    if typ not in ('REAR_END','LANE_CHANGE'): errors.append('نوع الحادث مطلوب.')
    if not date or not time: errors.append('تاريخ الحادث ووقته مطلوبان.')
    else:
        when=accident_moment(date,time)
        unchanged=original is not None and original['accident_date']==date and str(original['accident_time'])[:5]==time[:5]
        if when is None: errors.append('تاريخ أو وقت الحادث غير صالح.')
        elif not unchanged and not accident_within_window(when): errors.append('يجب أن يكون وقت الحادث خلال آخر 24 ساعة، ولا يمكن أن يكون في المستقبل.')
    if len(location)<3: errors.append('موقع الحادث مطلوب.')
    return typ,date,time,location,errors

@app.route('/cases/<case_id>/edit',methods=['GET','POST'])
@login_required
def edit_case(case_id):
    # party A can change the accident info until they submit
    case,party=case_access(case_id)
    if case['creator_id']!=session['uid'] or not party or party['position']!='A': abort(403)
    if party['completed']: return redirect(url_for('wizard',case_id=case_id,step=7))
    if request.method=='POST':
        typ,date,time,location,errors=accident_form(request.form,case)
        if errors:
            for e in errors: flash(e,'error')
            return render_template('new_case.html',form=request.form,editing=case)
        with conn() as c:
            c.execute('UPDATE accident_case SET accident_type=?,accident_date=?,accident_time=?,location=? WHERE case_id=?',(typ,date,time,location,case_id))
            if typ!=case['accident_type']:
                # if the accident type changed the description no longer fits, so we clear it
                c.execute('UPDATE accident_case SET party_a_description=NULL,party_b_description=NULL,party_a_position=NULL WHERE case_id=?',(case_id,))
                c.execute('UPDATE participation_progress SET description_meta=NULL WHERE case_id=?',(case_id,))
                c.execute('UPDATE participation_progress SET progress=3 WHERE case_id=? AND progress>3',(case_id,))
        flash('تم تحديث بيانات الحادث.','success')
        return redirect(url_for('wizard',case_id=case_id,step=1))
    form={'no_injuries':'yes','clear_weather':'yes','two_vehicles':'yes','accident_type':case['accident_type'],
          'accident_date':case['accident_date'],'accident_time':str(case['accident_time'])[:5],'location':case['location']}
    return render_template('new_case.html',form=form,editing=case)

ACCIDENT_WINDOW_HOURS=24
def local_now():
    # Saudi time
    return datetime.utcnow()+timedelta(hours=3)
def accident_moment(date,time_value):
    try: return datetime.strptime(date+' '+time_value[:5],'%Y-%m-%d %H:%M')
    except ValueError: return None
def accident_within_window(when):
    now=local_now()
    return now-timedelta(hours=ACCIDENT_WINDOW_HOURS)<=when<=now
@app.get('/cases/<case_id>')
@login_required
def case_detail(case_id):
    case, party = case_access(case_id)
    if not party:
        return redirect(url_for('dashboard'))
    return redirect(url_for('wizard', case_id=case_id, step=7 if party['completed'] else 1))

@app.post('/cases/<case_id>/cancel')
@login_required
def cancel_case(case_id):
    case,party=case_access(case_id)
    if case['creator_id']!=session['uid'] or not party or party['position']!='A': abort(403)
    if party['completed']:
        flash('لا يمكن إلغاء البلاغ بعد إرسال البيانات.','error')
        return redirect(url_for('wizard',case_id=case_id,step=7))
    with conn() as c:
        videos=c.execute(VIDEO_SQL+' WHERE v.case_id=?',(case_id,)).fetchall()
    # delete the video files before removing the case records
    try:
        for video in videos:
            for path in dict.fromkeys((video['stored_name'],video['processed_name'])):
                if path: delete_stored_file(path)
    except Exception:
        app.logger.exception('Case cancellation: video deletion failed')
        flash('تعذر إلغاء البلاغ حاليًا. يرجى المحاولة مرة أخرى.','error')
        return redirect(url_for('wizard',case_id=case_id,step=1))
    with conn() as c:
        # deleting the case also deletes its parties, vehicles links, videos and invitations (ON DELETE CASCADE);
        # the cars stay in the users' "My vehicles"
        c.execute('DELETE FROM accident_case WHERE case_id=?',(case_id,))
    flash('تم إلغاء البلاغ '+case['reference']+'.','success')
    return redirect(url_for('dashboard'))

def delete_stored_file(path):
    # delete a video from Cloudinary, S3 or the local uploads folder
    public_id = stored_cloudinary_id(path)
    key = stored_s3_key(path)
    if public_id:
        if not cloudinary_ready():
            raise RuntimeError('Cloudinary credentials are missing')
        timestamp = int(time.time())
        params = {'public_id': public_id, 'timestamp': timestamp, 'type': 'authenticated'}
        payload = urlencode({**params, 'api_key': os.environ['CLOUDINARY_API_KEY'],
                             'signature': cloudinary_sign(params)}).encode()
        url = 'https://api.cloudinary.com/v1_1/' + quote(os.environ['CLOUDINARY_CLOUD_NAME'], safe='') + '/video/destroy'
        with urlopen(Request(url, data=payload, method='POST'), timeout=25) as response:
            result = json.loads(response.read().decode())
        if result.get('result') not in ('ok', 'not found'):
            raise RuntimeError('Cloudinary deletion failed')
    elif key:
        if not storage_ready():
            raise RuntimeError('Storage credentials are missing')
        storage_client().delete_object(Bucket=os.environ['S3_BUCKET'], Key=key)
    elif not os.getenv('VERCEL'):
        (UPLOAD / Path(path).name).unlink(missing_ok=True)

@app.post('/cases/<case_id>/invite')
@login_required
def invite(case_id):
    case,party=case_access(case_id)
    if case['creator_id']!=session['uid']: abort(403)
    if not party or not party['completed']:
        # the invitation is sent after the first party submits their data
        flash('يُرجى إرسال بياناتك أولًا قبل دعوة الطرف الثاني.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    recipient_email=request.form.get('recipient_email','').strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',recipient_email) or len(recipient_email)>254:
        flash('البريد الإلكتروني للطرف الثاني غير صحيح.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    if current_user()['email'].strip().lower()==recipient_email:
        flash('لا يمكن إرسال الدعوة إلى بريد منشئ البلاغ نفسه.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    with conn() as c:
        second=c.execute("SELECT national_id FROM participation_progress WHERE case_id=? AND position='B'",(case_id,)).fetchone()
        if second:
            flash('الطرف الثاني مرتبط بالبلاغ بالفعل، ولا يمكن إرسال دعوة جديدة.','error')
            return redirect(url_for('case_detail',case_id=case_id))
        latest=c.execute('SELECT created_at,recipient_email FROM case_invitation WHERE case_id=? ORDER BY invitation_id DESC LIMIT 1',(case_id,)).fetchone()
        # wait 1 minute before resending to the same email, but a different email can be sent right away
        if latest and (latest['recipient_email'] or '').lower()==recipient_email and datetime.utcnow()-datetime.fromisoformat(str(latest['created_at'])[:19].replace(' ','T'))<timedelta(seconds=60):
            flash('يرجى الانتظار دقيقة قبل إرسال دعوة أخرى لنفس البلاغ.','error')
            return redirect(url_for('case_detail',case_id=case_id))
    token=secrets.token_urlsafe(32)
    exp=(datetime.utcnow()+timedelta(days=7)).isoformat()
    with conn() as c:
        invitation_id=insert_id(c,'INSERT INTO case_invitation(case_id,token_hash,expires_at,recipient_email) VALUES(?,?,?,?)',(case_id,hashlib.sha256(token.encode()).hexdigest(),exp,recipient_email),'invitation_id')
    public_base=os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/')
    if public_base and not re.fullmatch(r'https://[^\s/]+(?:\:[0-9]{2,5})?',public_base):
        with conn() as c: c.execute('DELETE FROM case_invitation WHERE invitation_id=?',(invitation_id,))
        flash('PUBLIC_BASE_URL يجب أن يكون رابط HTTPS عامًّا بدون مسار، مثل https://siyaq.example.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    link=(public_base+url_for('invitation',token=token)) if public_base else url_for('invitation',token=token,_external=True)
    if os.getenv('INVITE_MODE','').strip().lower()=='demo' and request.remote_addr in ('127.0.0.1','::1'):
        # demo on our computer: no email is sent, the link shows on screen instead
        with conn() as c:
            c.execute('UPDATE case_invitation SET revoked_at=? WHERE case_id=? AND invitation_id<>? AND claimed_by IS NULL AND revoked_at IS NULL',
                      (datetime.utcnow().isoformat(),case_id,invitation_id))
            c.execute('UPDATE accident_case SET party_b_email=? WHERE case_id=?',(recipient_email,case_id))
        flash('وضع التجربة: لم يُرسل بريد. يُفتح هذا الرابط في نافذة خاصة ويُسجَّل بحساب بريده '+recipient_email+' : '+url_for('invitation',token=token,_external=True),'success')
        return redirect(url_for('case_detail',case_id=case_id))
    if not public_base and request.host.split(':')[0] in ('localhost','127.0.0.1'):
        with conn() as c: c.execute('DELETE FROM case_invitation WHERE invitation_id=?',(invitation_id,))
        flash('قبل إرسال الدعوة يلزم إضافة PUBLIC_BASE_URL لرابط موقع سياق المنشور على HTTPS؛ localhost لا يفتح على جوال الطرف الثاني.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    try:
        send_case_invitation(recipient_email,link,case['reference'])
    except RuntimeError as exc:
        with conn() as c: c.execute('DELETE FROM case_invitation WHERE invitation_id=? AND claimed_by IS NULL',(invitation_id,))
        flash(str(exc),'error')
        return redirect(url_for('case_detail',case_id=case_id))
    with conn() as c:
        c.execute('UPDATE case_invitation SET revoked_at=? WHERE case_id=? AND invitation_id<>? AND claimed_by IS NULL AND revoked_at IS NULL',
                  (datetime.utcnow().isoformat(),case_id,invitation_id))
        c.execute('UPDATE accident_case SET party_b_email=? WHERE case_id=?',(recipient_email,case_id))
    flash('تم إرسال الدعوة إلى البريد الإلكتروني للطرف الثاني. يُرجى التحقق من صندوق الوارد والرسائل غير المرغوبة.','success')
    return redirect(url_for('case_detail',case_id=case_id))

@app.get('/invite/<token>')
def invitation(token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        inv=c.execute('SELECT * FROM case_invitation WHERE token_hash=?',(digest,)).fetchone()
        if not inv: abort(404)
        valid=bool(inv['recipient_email'] and not inv['revoked_at'] and not inv['claimed_by'] and inv['expires_at']>datetime.utcnow().isoformat())
        if c.execute("SELECT 1 FROM participation_progress WHERE case_id=? AND position='B'",(inv['case_id'],)).fetchone(): valid=False
    user=current_user()
    matched=bool(user and user['email'].strip().lower()==inv['recipient_email'].strip().lower())
    return render_template('invitation.html',token=token,valid=valid,matched=matched,recipient_email=inv['recipient_email'])

@app.post('/invite/<token>/accept')
@login_required
def accept_invitation(token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        inv=c.execute('SELECT * FROM case_invitation WHERE token_hash=?',(digest,)).fetchone()
        if not inv or not inv['recipient_email'] or inv['revoked_at'] or inv['expires_at']<=datetime.utcnow().isoformat() or inv['claimed_by']:
            abort(403)
        u=c.execute('SELECT email FROM accident_party WHERE national_id=?',(session['uid'],)).fetchone()
        if not u or u['email'].strip().lower()!=inv['recipient_email'].strip().lower(): abort(403)
        if c.execute("SELECT 1 FROM participation_progress WHERE case_id=? AND position='B'",(inv['case_id'],)).fetchone(): abort(403)
        if c.execute('SELECT 1 FROM participates WHERE case_id=? AND national_id=?',(inv['case_id'],session['uid'])).fetchone(): abort(403)
        claimed=c.execute('UPDATE case_invitation SET claimed_by=? WHERE invitation_id=? AND claimed_by IS NULL AND revoked_at IS NULL',
                          (session['uid'],inv['invitation_id']))
        if claimed.rowcount!=1: abort(403)
        # the second party joins the case (Participates)
        c.execute('INSERT INTO participates(national_id,case_id) VALUES(?,?)',(session['uid'],inv['case_id']))
        c.execute("INSERT INTO participation_progress(national_id,case_id,position) VALUES(?,?,'B')",(session['uid'],inv['case_id']))
        c.execute('UPDATE accident_case SET party_b_email=? WHERE case_id=?',(u['email'],inv['case_id']))
        creator=get_case(c,inv['case_id'])
    # tell the first party that the second party joined
    if creator: notify_case(inv['case_id'],'joined',only_user_id=creator['creator_id'])
    return redirect(url_for('wizard',case_id=inv['case_id'],step=1))

# Saudi plate letters and their English letters
PLATE_LETTERS={'أ':'A','ب':'B','ح':'J','د':'D','ر':'R','س':'S','ص':'X','ط':'T','ع':'E','ق':'G','ك':'K','ل':'L','م':'Z','ن':'N','هـ':'H','و':'U','ى':'V'}
PLATE_LATIN={v:k for k,v in PLATE_LETTERS.items()}
def parse_plate(letters_raw,numbers_raw):
    letters=[]
    # accept letters with or without spaces
    for token in re.sub(r'[\sـ]+','',str(letters_raw or '')):
        token=PLATE_LATIN.get(token.upper(),token)
        if token=='ه': token='هـ'
        if token in ('ا','إ','آ'): token='أ'
        if token=='ي': token='ى'
        letters.append(token)
    numbers=normalized_digits(numbers_raw or '')
    if not re.fullmatch(r'\d{1,4}',numbers): return None,'أرقام اللوحة يجب أن تكون من 1 إلى 4 أرقام.'
    if not 1<=len(letters)<=3 or any(l not in PLATE_LETTERS for l in letters): return None,'حروف اللوحة يجب أن تكون من 1 إلى 3 حروف من حروف اللوحات السعودية.'
    return ' '.join(letters)+' '+numbers,None
def split_plate(plate):
    parts=str(plate or '').split()
    if parts and parts[-1].isdigit(): return ' '.join(parts[:-1]),parts[-1]
    return '',''
app.jinja_env.globals.update(split_plate=split_plate,PLATE_LETTERS=PLATE_LETTERS)

def vehicle_form_errors(form):
    plate,error=parse_plate(form.get('plate_letters',''),form.get('plate_numbers',''))
    data={'plate':plate}
    for k in ('manufacturer','model','color'): data[k]=form.get(k,'').strip()
    data['year']=normalized_digits(form.get('year',''))
    errors=[error] if error else []
    if not data['manufacturer']: errors.append('الشركة المصنعة مطلوبة.')
    if not data['model']: errors.append('الطراز مطلوب.')
    if not re.fullmatch(r'\d{4}',data['year']) or not 1950<=int(data['year'])<=datetime.now().year+1: errors.append('سنة الصنع يجب أن تكون 4 أرقام صحيحة.')
    if not data['color']: errors.append('لون المركبة مطلوب.')
    data['plate_letters'],data['plate_number']=split_plate(plate) if plate else ('','')
    return data,errors

def vehicle_locked(c, vehicle_id):
    # a car can't be changed or deleted while it is in a case its owner already submitted
    return bool(c.execute('''SELECT 1 FROM involves i JOIN vehicle v ON v.vehicle_id=i.vehicle_id
        JOIN participation_progress pp ON pp.case_id=i.case_id AND pp.national_id=v.national_id
        WHERE i.vehicle_id=? AND pp.completed=1''',(vehicle_id,)).fetchone())

def save_owner_vehicle(c, owner, data, vehicle_id=None):
    # add or update a car in the owner's "My vehicles" (VEHICLE, registered by ACCIDENT_PARTY)
    # returns (vehicle_id, error, changed)
    values=(data['plate_letters'],data['plate_number'],data['manufacturer'],data['model'],int(data['year']),data['color'])
    same=c.execute('SELECT * FROM vehicle WHERE national_id=? AND plate_letters=? AND plate_number=?',(owner,data['plate_letters'],data['plate_number'])).fetchone()
    if vehicle_id:
        old=c.execute('SELECT * FROM vehicle WHERE vehicle_id=? AND national_id=?',(vehicle_id,owner)).fetchone()
        if not old: return None,'المركبة غير موجودة.',False
        if same and same['vehicle_id']!=old['vehicle_id']: return None,'هذه اللوحة مسجلة مسبقًا في مركباتك.',False
    else:
        old=same
    if old:
        changed=(old['plate_letters'],old['plate_number'],old['manufacturer'],old['model'],int(old['year']),old['color'])!=values
        if changed and vehicle_locked(c,old['vehicle_id']):
            return None,'لا يمكن تعديل هذه المركبة لأنها مرتبطة ببلاغ تم إرساله.',False
        if changed:
            c.execute('UPDATE vehicle SET plate_letters=?,plate_number=?,manufacturer=?,model=?,year=?,color=? WHERE vehicle_id=?',(*values,old['vehicle_id']))
        return old['vehicle_id'],None,changed
    new_id=insert_id(c,'INSERT INTO vehicle(plate_letters,plate_number,manufacturer,model,year,color,national_id) VALUES(?,?,?,?,?,?,?)',(*values,owner),'vehicle_id')
    return new_id,None,True

def save_party_progress(case_id,national_id,step):
    with conn() as c: c.execute('UPDATE participation_progress SET progress=? WHERE case_id=? AND national_id=? AND progress<?',(step,case_id,national_id,step))

def opposite_description(case, first):
    # Keep the same event and express the choices from the second party's view.
    try:
        meta=json.loads(first['description_meta'] or '{}') if first else {}
    except (ValueError, TypeError):
        meta={}
    if not isinstance(meta,dict): meta={}
    zones={'front':'rear','rear':'front','left':'right','right':'left',
           'front-left':'rear-right','front-right':'rear-left',
           'rear-left':'front-right','rear-right':'front-left'}
    result={}
    if case['accident_type']=='REAR_END':
        pos=OPPOSITE.get(case['party_a_position'] or meta.get('pos'))
        if pos: result['pos']=pos
        if meta.get('rcase') in ('normal','sudden','cutin'): result['rcase']=meta['rcase']
    else:
        side={'left':'right','right':'left'}.get(meta.get('side'))
        who={'me':'other','other':'me','both':'both'}.get(meta.get('who'))
        if side: result['side']=side
        if who: result['who']=who
    if meta.get('zone') in zones: result['zone']=zones[meta['zone']]
    return result

STEPS=['بيانات الحادث','بيانات الطرف','بيانات المركبة','وصف الحادث','رفع الفيديو','المراجعة','دعوة الطرف الثاني']
@app.route('/cases/<case_id>/steps/<int:step>',methods=['GET','POST'])
@login_required
def wizard(case_id,step):
    if step not in range(1,8): abort(404)
    case,party=case_access(case_id)
    if not party: abort(403)
    locked_meta={}
    if party['position']=='B':
        with conn() as c:
            locked_meta=opposite_description(case,party_at(c,case,'A'))
    nid=party['national_id']
    progress=party['progress'] or 0
    if party['completed'] and step<7:
        return redirect(url_for('wizard',case_id=case_id,step=7))
    if not party['completed'] and step>min(progress+1,6):
        flash('يُرجى إكمال الخطوات بالترتيب قبل الانتقال للخطوة التالية.','error')
        return redirect(url_for('wizard',case_id=case_id,step=min(progress+1,6)))
    if request.method=='POST':
        if step==7: abort(405)
        if step==3:
            data,errors=vehicle_form_errors(request.form)
            if errors:
                for e in errors: flash(e,'error')
                return redirect(request.url)
            garage_id=request.form.get('garage_id','')
            with conn() as c:
                other_car=c.execute('''SELECT 1 FROM involves i JOIN vehicle v ON v.vehicle_id=i.vehicle_id
                    WHERE i.case_id=? AND v.national_id<>? AND v.plate_letters=? AND v.plate_number=?''',
                    (case_id,nid,data['plate_letters'],data['plate_number'])).fetchone()
                if other_car:
                    flash('هذه اللوحة مسجلة لمركبة الطرف الآخر في نفس البلاغ.','error')
                    return redirect(request.url)
                is_new=not c.execute('SELECT 1 FROM vehicle WHERE national_id=? AND plate_letters=? AND plate_number=?',(nid,data['plate_letters'],data['plate_number'])).fetchone()
                # also saves the car in "My vehicles" (updates it if it's already there)
                vehicle_id,error,changed=save_owner_vehicle(c,nid,data,int(garage_id) if garage_id.isdigit() else None)
                if error:
                    flash(error,'error'); return redirect(request.url)
                # link this car to the case (Involves), replacing an earlier choice
                c.execute('''DELETE FROM involves WHERE case_id=? AND vehicle_id IN
                    (SELECT vehicle_id FROM vehicle WHERE national_id=?)''',(case_id,nid))
                c.execute('INSERT INTO involves(case_id,vehicle_id) VALUES(?,?)',(case_id,vehicle_id))
            if is_new: flash('أُضيفت المركبة إلى «مركباتي» لاستخدامها في البلاغات القادمة.','success')
            elif changed: flash('تم تحديث بيانات المركبة في «مركباتي».','success')
        elif step==4:
            text=request.form.get('description','').strip()
            f=request.form
            errors=[]
            if case['accident_type']=='REAR_END':
                meta={'pos':f.get('pos'),'rcase':f.get('rcase'),'zone':f.get('zone')}
                meta.update(locked_meta)
                # the second party's car position is always the opposite of the first party's
                if party['position']=='B' and case['party_a_position']: meta['pos']=OPPOSITE[case['party_a_position']]
                if meta['pos'] not in ('FRONT','REAR'): errors.append('موقع المركبة مطلوب (الأمامية أو الخلفية).')
                if meta['rcase'] not in ('normal','sudden','cutin'): errors.append('ما حدث قبل الصدمة مطلوب.')
                if meta['zone'] not in ('front','rear'): errors.append('مكان الصدمة مطلوب.')
            else:
                meta={'side':f.get('side'),'who':f.get('who'),'zone':f.get('zone')}
                meta.update(locked_meta)
                if meta['side'] not in ('left','right'): errors.append('جهة سيارة الطرف الآخر مطلوبة.')
                if meta['who'] not in ('me','other','both'): errors.append('تحديد من غيّر المسار مطلوب.')
                if meta['zone'] not in ZONES: errors.append('مكان الصدمة مطلوب.')
            if not 10<=len(text)<=500: errors.append('وصف الحادث يجب أن يكون من 10 إلى 500 حرف.')
            if errors:
                for e in errors: flash(e,'error')
                return redirect(request.url)
            column='party_a_description' if party['position']=='A' else 'party_b_description'
            with conn() as c:
                c.execute(f'UPDATE accident_case SET {column}=? WHERE case_id=?',(text,case_id))
                c.execute('UPDATE participation_progress SET description_meta=? WHERE case_id=? AND national_id=?',(json.dumps(meta),case_id,nid))
                if case['accident_type']=='REAR_END':
                    # only the first party's position is stored (party_a_position); the second party has the opposite
                    position=meta['pos'] if party['position']=='A' else OPPOSITE[meta['pos']]
                    c.execute('UPDATE accident_case SET party_a_position=? WHERE case_id=?',(position,case_id))
        elif step==5:
            f=request.files.get('video')
            with conn() as c:
                existing_count=c.execute('SELECT COUNT(*) AS n FROM dashcam_video WHERE case_id=? AND national_id=?',(case_id,nid)).fetchone()['n']
            camera=request.form.get('camera')
            if f and f.filename and existing_count:
                flash('يمكن رفع فيديو واحد فقط. لاستبداله يُحذف الفيديو الحالي أولًا.','error')
                return redirect(request.url)
            if f and f.filename and camera not in allowed_cameras(case,party):
                flash('يُرجى تحديد الكاميرا التي صُوّر بها الفيديو.','error')
                return redirect(request.url)
            if (not f or not f.filename) and not existing_count and party['position']=='A':
                flash('يجب اختيار فيديو الحادث قبل المتابعة.','error')
                return redirect(request.url)
            if f and f.filename and request.content_length and request.content_length>200*1024*1024:
                flash('حجم الفيديو يتجاوز 200 ميجابايت.','error')
                return redirect(request.url)
            if f and f.filename and os.getenv('VERCEL'):
                flash('يرجى رفع الفيديو باستخدام خانة الرفع الظاهرة في الصفحة.','error')
                return redirect(request.url)
            if f and f.filename:
                ext=f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else ''
                if ext not in ALLOWED: flash('صيغة الفيديو غير مدعومة.','error');return redirect(request.url)
                filename=uuid.uuid4().hex+'.'+ext
                f.save(UPLOAD/filename)
                with conn() as c: add_video(c,case_id,nid,filename,camera,secure_filename(f.filename))
        elif step==6:
            with conn() as c:
                video_count=c.execute('SELECT COUNT(*) AS n FROM dashcam_video WHERE case_id=? AND national_id=?',(case_id,nid)).fetchone()['n']
            if not video_count and party['position']=='A':
                flash('يجب رفع فيديو الحادث أولًا قبل إرسال البيانات.','error')
                return redirect(url_for('wizard',case_id=case_id,step=5))
            if request.form.get('consent')!='yes': flash('يجب الموافقة قبل الإرسال.','error');return redirect(request.url)
            with conn() as c:
                c.execute('UPDATE participation_progress SET completed=1 WHERE case_id=? AND national_id=?',(case_id,nid))
                count=c.execute('SELECT COUNT(*) AS total FROM participation_progress WHERE case_id=? AND completed=1',(case_id,)).fetchone()['total']
                c.execute('UPDATE accident_case SET status=? WHERE case_id=?',('in_progress' if count==2 else 'pending',case_id))
            # both parties submitted, so tell them the case is now in review
            if count==2: notify_case(case_id,'in_progress')
            save_party_progress(case_id,nid,6)
            flash('تم حفظ بياناتك بنجاح.','success');return redirect(url_for('wizard',case_id=case_id,step=7))
        save_party_progress(case_id,nid,step)
        return redirect(url_for('wizard',case_id=case_id,step=step+1))
    with conn() as c:
        vehicle=party_vehicle(c,case_id,nid)
        videos=c.execute(VIDEO_SQL+' WHERE v.case_id=? AND v.national_id=?',(case_id,nid)).fetchall()
        invited=c.execute("SELECT * FROM case_invitation WHERE case_id=? ORDER BY invitation_id DESC LIMIT 1",(case_id,)).fetchone()
        party_b=party_at(c,case,'B')
        other_party={'user_id':party_b['national_id']} if party_b else None
        garage=c.execute(VEHICLE_SQL+' WHERE national_id=? ORDER BY vehicle_id DESC',(nid,)).fetchall()
        other=party_at(c,case,'B' if party['position']=='A' else 'A')
        first_vehicle=party_vehicle(c,case_id,case['creator_id']) if party['position']=='B' else None
    try: desc_meta=json.loads(party['description_meta'] or '{}')
    except ValueError: desc_meta={}
    return render_template('wizard.html',garage=garage,other=other,first_vehicle=first_vehicle,case=case,party=party,vehicle=vehicle,videos=videos,step=step,progress=progress,desc_meta=desc_meta,locked_meta=locked_meta,cameras=allowed_cameras(case,party),steps=STEPS if party['position']=='A' else STEPS[:6]+['اكتمال البلاغ'],invite=invited,other_party=other_party,cloud_upload=bool(os.getenv('VERCEL') or storage_ready() or cloudinary_ready()))

def add_video(c, case_id, national_id, storage_path, camera, original_name):
    # save an uploaded video (DASHCAM_VIDEO) and its processing record (supporting table)
    video_id=insert_id(c,'INSERT INTO dashcam_video(storage_path,camera_type,case_id,national_id) VALUES(?,?,?,?)',(storage_path,camera,case_id,national_id),'video_id')
    c.execute('INSERT INTO video_processing(video_id,original_name) VALUES(?,?)',(video_id,original_name))
    return video_id

ZONES=('front','front-left','front-right','left','right','rear-left','rear-right','rear')
def allowed_cameras(case,party):
    # rear-end: the rear car needs its front camera video, the front car needs its rear camera video
    if case['accident_type']=='REAR_END' and party['vehicle_role']=='REAR': return ('front',)
    if case['accident_type']=='REAR_END' and party['vehicle_role']=='FRONT': return ('rear',)
    return ('front','rear')

@app.post('/api/cases/<case_id>/videos/presign')
@login_required
def video_presign(case_id):
    case, party = case_access(case_id)
    if not party: abort(403)
    if not (cloudinary_ready() or storage_ready()):
        return jsonify(error='خدمة رفع الفيديو غير متاحة حاليًا. يرجى المحاولة لاحقًا.'), 503
    data = request.get_json(silent=True) or {}
    with conn() as c:
        if c.execute('SELECT 1 FROM dashcam_video WHERE case_id=? AND national_id=?',(case_id,party['national_id'])).fetchone():
            return jsonify(error='يمكن رفع فيديو واحد فقط. لاستبداله يُحذف الفيديو الحالي أولًا.'), 400
    camera = data.get('camera')
    if camera not in allowed_cameras(case, party):
        return jsonify(error='يُرجى تحديد الكاميرا التي صُوّر بها الفيديو.'), 400
    original = str(data.get('filename', ''))
    size = data.get('size')
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    if ext not in ALLOWED or type(size) is not int or not 0 < size <= VIDEO_MAX_BYTES:
        return jsonify(error='يرجى اختيار فيديو بصيغة مدعومة وحجم لا يتجاوز 200 ميجابايت.'), 400
    if cloudinary_ready():
        public_id = f'siyaq/cases/{case_id}/parties/{party["national_id"]}/{uuid.uuid4().hex}'
        timestamp = int(time.time())
        params = {'public_id': public_id, 'timestamp': timestamp, 'type': 'authenticated'}
        session['pending_video'] = {'provider': 'cloudinary', 'public_id': public_id,
                                    'case_id': case_id, 'party_id': party['national_id'],
                                    'name': secure_filename(original) or 'video.'+ext,
                                    'size': size, 'camera': camera, 'expires': time.time()+3600}
        return jsonify(provider='cloudinary', upload_url='https://api.cloudinary.com/v1_1/' +
                       quote(os.environ['CLOUDINARY_CLOUD_NAME'], safe='') + '/video/upload',
                       api_key=os.environ['CLOUDINARY_API_KEY'], timestamp=timestamp,
                       signature=cloudinary_sign(params), public_id=public_id,
                       delivery_type='authenticated', content_type=VIDEO_MIME[ext])
    key = f'cases/{case_id}/parties/{party["national_id"]}/{uuid.uuid4().hex}.{ext}'
    mime = VIDEO_MIME[ext]
    try:
        upload_url = storage_client().generate_presigned_url('put_object',
            Params={'Bucket':os.environ['S3_BUCKET'], 'Key':key, 'ContentType':mime}, ExpiresIn=600)
    except Exception:
        app.logger.exception('Could not prepare video upload')
        return jsonify(error='تعذر بدء رفع الفيديو. يرجى المحاولة لاحقًا.'), 503
    session['pending_video'] = {'key':key,'case_id':case_id,'party_id':party['national_id'],
                                'name':secure_filename(original) or 'video.'+ext,
                                'size':size,'camera':camera,'expires':time.time()+600}
    return jsonify(upload_url=upload_url, content_type=mime)

@app.post('/api/cases/<case_id>/videos/complete')
@login_required
def video_complete(case_id):
    case, party = case_access(case_id)
    if not party: abort(403)
    pending = session.get('pending_video') or {}
    if pending.get('case_id') != case_id or pending.get('party_id') != party['national_id'] or pending.get('expires',0) < time.time():
        return jsonify(error='انتهت مهلة رفع الفيديو. يرجى إعادة المحاولة.'), 400
    if pending.get('provider') == 'cloudinary':
        if not cloudinary_ready():
            return jsonify(error='خدمة رفع الفيديو غير متاحة حاليًا.'), 503
        try:
            meta = cloudinary_metadata(pending['public_id'])
            if (meta.get('public_id') != pending['public_id'] or
                meta.get('resource_type') != 'video' or meta.get('type') != 'authenticated' or
                meta.get('bytes') != pending['size']):
                return jsonify(error='لم يكتمل رفع الفيديو. يرجى إعادة المحاولة.'), 400
            with conn() as c:
                existing = c.execute('SELECT video_id FROM dashcam_video WHERE storage_path=?',
                                     ('cloudinary://' + pending['public_id'],)).fetchone()
                if not existing and not c.execute('SELECT 1 FROM dashcam_video WHERE case_id=? AND national_id=?',(case_id,party['national_id'])).fetchone():
                    add_video(c,case_id,party['national_id'],'cloudinary://' + pending['public_id'],pending.get('camera'),pending['name'])
            session.pop('pending_video', None)
        except Exception:
            app.logger.exception('Could not verify video upload')
            return jsonify(error='تعذر تأكيد رفع الفيديو. يرجى المحاولة لاحقًا.'), 503
        return jsonify(ok=True, next_url=url_for('wizard',case_id=case_id,step=6))
    if not storage_ready():
        return jsonify(error='خدمة رفع الفيديو غير متاحة حاليًا.'), 503
    try:
        meta = storage_client().head_object(Bucket=os.environ['S3_BUCKET'], Key=pending['key'])
        if meta['ContentLength'] != pending['size']:
            return jsonify(error='لم يكتمل رفع الفيديو. يرجى إعادة المحاولة.'), 400
        with conn() as c:
            if c.execute('SELECT 1 FROM dashcam_video WHERE case_id=? AND national_id=?',(case_id,party['national_id'])).fetchone():
                return jsonify(error='يمكن رفع فيديو واحد فقط.'), 400
            add_video(c,case_id,party['national_id'],'s3://'+pending['key'],pending.get('camera'),pending['name'])
        session.pop('pending_video', None)
    except Exception:
        app.logger.exception('Could not finalize video upload')
        return jsonify(error='تعذر حفظ الفيديو. يرجى المحاولة لاحقًا.'), 503
    return jsonify(ok=True, next_url=url_for('wizard',case_id=case_id,step=6))

@app.post('/videos/<int:video_id>/delete')
@login_required
def delete_video(video_id):
    # delete a video, only allowed before the case is submitted
    with conn() as c:
        video = c.execute(VIDEO_SQL+' WHERE v.video_id=?', (video_id,)).fetchone()
    if not video:
        abort(404)
    case, party = case_access(video['case_id'])
    if not party or video['party_id'] != party['national_id']:
        abort(403)
    if party['completed']:
        flash('لا يمكن حذف الفيديو بعد إرسال البيانات النهائية.', 'error')
        return redirect(url_for('wizard', case_id=video['case_id'], step=5))
    paths = [video['stored_name']]
    if video['processed_name'] and video['processed_name'] != video['stored_name']:
        paths.append(video['processed_name'])
    try:
        for path in paths:
            public_id = stored_cloudinary_id(path)
            key = stored_s3_key(path)
            if public_id:
                if not cloudinary_ready():
                    raise RuntimeError('Cloudinary credentials are missing')
                timestamp = int(time.time())
                params = {'public_id': public_id, 'timestamp': timestamp, 'type': 'authenticated'}
                payload = urlencode({**params, 'api_key': os.environ['CLOUDINARY_API_KEY'],
                                     'signature': cloudinary_sign(params)}).encode()
                url = 'https://api.cloudinary.com/v1_1/' + quote(os.environ['CLOUDINARY_CLOUD_NAME'], safe='') + '/video/destroy'
                with urlopen(Request(url, data=payload, method='POST'), timeout=25) as response:
                    result = json.loads(response.read().decode())
                if result.get('result') not in ('ok', 'not found'):
                    raise RuntimeError('Cloudinary deletion failed')
            elif key:
                if not storage_ready():
                    raise RuntimeError('Storage credentials are missing')
                storage_client().delete_object(Bucket=os.environ['S3_BUCKET'], Key=key)
            else:
                if not os.getenv('VERCEL'):
                    (UPLOAD / Path(path).name).unlink(missing_ok=True)
    except Exception:
        app.logger.exception('Video deletion failed')
        flash('تعذر حذف الفيديو حاليًا. يرجى المحاولة مرة أخرى.', 'error')
        return redirect(url_for('wizard', case_id=video['case_id'], step=5))
    with conn() as c:
        c.execute('DELETE FROM dashcam_video WHERE video_id=? AND national_id=?', (video_id, party['national_id']))
    flash('تم حذف الفيديو، ويمكن اختيار فيديو آخر.', 'success')
    return redirect(url_for('wizard', case_id=video['case_id'], step=5))

@app.get('/videos/<int:video_id>/download')
@login_required
def download_video(video_id):
    with conn() as c: v=c.execute(VIDEO_SQL+' WHERE v.video_id=?',(video_id,)).fetchone()
    if not v:abort(404)
    case_access(v['case_id'])
    public_id = stored_cloudinary_id(v['processed_name'] or v['stored_name'])
    if public_id:
        if not cloudinary_ready(): abort(503)
        # make a download link that only works for 2 minutes
        expires = int(time.time()) + 120
        fmt = v['original_name'].rsplit('.', 1)[-1].lower() if '.' in v['original_name'] else 'mp4'
        params = {'public_id': public_id, 'format': fmt, 'type': 'authenticated', 'expires_at': expires}
        params.update({'api_key': os.environ['CLOUDINARY_API_KEY'], 'signature': cloudinary_sign(params)})
        url = ('https://api.cloudinary.com/v1_1/' + quote(os.environ['CLOUDINARY_CLOUD_NAME'],safe='') +
               '/video/download?' + urlencode(params))
        return redirect(url)
    key = stored_s3_key(v['processed_name'] or v['stored_name'])
    if key:
        if not storage_ready(): abort(503)
        try:
            link=storage_client().generate_presigned_url('get_object', Params={
                'Bucket':os.environ['S3_BUCKET'],'Key':key,
                'ResponseContentDisposition':f'attachment; filename="{secure_filename(v["original_name"])}"'}, ExpiresIn=120)
            return redirect(link)
        except Exception:
            app.logger.exception('Video download failed')
            abort(503)
    if os.getenv('VERCEL'): abort(404)
    return send_from_directory(UPLOAD,v['processed_name'] or v['stored_name'],as_attachment=True,download_name=v['original_name'])
@app.post('/videos/<int:video_id>/process')
@login_required
def process_video(video_id):
    with conn() as c: v=c.execute(VIDEO_SQL+' WHERE v.video_id=?',(video_id,)).fetchone()
    if not v:abort(404)
    case_access(v['case_id'])
    if stored_s3_key(v['stored_name']) or stored_cloudinary_id(v['stored_name']):
        flash('معالجة الفيديو ستتوفر لاحقًا.','error')
        return redirect(url_for('wizard',case_id=v['case_id'],step=5))
    from privacy import process_privacy
    result=process_privacy(UPLOAD/v['stored_name'],UPLOAD)
    with conn() as c:
        c.execute('UPDATE video_processing SET processed_path=?,privacy_status=?,note=? WHERE video_id=?',(result.get('filename'),result['status'],result['note'],video_id))
        c.execute('UPDATE video_processing SET job_status=?,job_details=?,updated_at=CAST(CURRENT_TIMESTAMP AS TEXT) WHERE video_id=?',('privacy_processed' if result.get('filename') else 'requires_review',result['note'],video_id))
    flash(result['note'],'success' if result.get('filename') else 'error')
    return redirect(url_for('wizard',case_id=v['case_id'],step=5))

@app.route('/profile',methods=['GET','POST'])
@login_required
def profile():
    tab=request.args.get('tab','personal')
    if request.method=='POST':
        action=request.form.get('action')
        if action=='email_request':
            new_email=request.form.get('email','').strip().lower()
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',new_email) or len(new_email)>254: flash('البريد الإلكتروني غير صالح.','error')
            elif new_email==current_user()['email'].strip().lower(): flash('هذا هو بريدك الحالي.','error')
            else:
                with conn() as c: taken=c.execute('SELECT 1 FROM accident_party WHERE email=?',(new_email,)).fetchone()
                if taken: flash('هذا البريد مسجل بحساب آخر.','error')
                else:
                    try:
                        session['pending_email']=issue_otp({'email':new_email,'started':time.time(),'attempts':0})
                        flash('أرسلنا رمز تحقق إلى '+new_email+'.','success')
                    except RuntimeError as e: flash(str(e),'error')
        elif action=='email_verify':
            pending=session.get('pending_email')
            code=normalized_digits(request.form.get('code',''))
            if not pending or time.time()-pending.get('last_sent',0)>600:
                session.pop('pending_email',None); flash('انتهت صلاحية الرمز. يُرجى طلب رمز جديد.','error')
            elif pending['attempts']>=5:
                session.pop('pending_email',None); flash('تم تجاوز عدد المحاولات. يُرجى طلب رمز جديد.','error')
            else:
                pending['attempts']+=1; session['pending_email']=pending
                if re.fullmatch(r'\d{6}',code) and hmac.compare_digest(otp_digest(code,pending['email']),pending.get('otp_digest','')):
                    with conn() as c: c.execute('UPDATE accident_party SET email=? WHERE national_id=?',(pending['email'],session['uid']))
                    session.pop('pending_email',None); flash('تم تحديث بريدك الإلكتروني.','success')
                else: flash('رمز التحقق غير صحيح.','error')
        elif action=='email_cancel':
            session.pop('pending_email',None)
        elif action=='password':
            u=current_user(); old=request.form.get('current',''); new=request.form.get('next','')
            if not check_password_hash(u['password_hash'],old):flash('كلمة المرور الحالية غير صحيحة.','error')
            elif check_password_hash(u['password_hash'],new):flash('لا يمكن استخدام كلمة المرور الحالية. يرجى اختيار كلمة مرور جديدة.','error')    
            elif len(new)<8 or not re.search(r'[A-Za-z\u0600-\u06FF]',new) or not re.search(r'\d',new):flash('كلمة المرور الجديدة تتطلب ٨ أحرف وحرفًا ورقمًا.','error')
            elif new!=request.form.get('confirm',''):flash('كلمتا المرور غير متطابقتين.','error')
            else:
                with conn() as c:c.execute('UPDATE accident_party SET password_hash=? WHERE national_id=?',(generate_password_hash(new),session['uid']))
                flash('تم تغيير كلمة المرور.','success')
        elif action=='notifications':
            # save the notification setting for status updates
            with conn() as c:c.execute('UPDATE accident_party SET notify_status_change=? WHERE national_id=?',(int(request.form.get('status')=='on'),session['uid']))
            flash('تم حفظ تفضيلات الإشعارات بنجاح.','success')
        return redirect(url_for('profile',tab=tab))
    with conn() as c: cars=c.execute(VEHICLE_SQL+' WHERE national_id=? ORDER BY vehicle_id DESC',(session['uid'],)).fetchall()
    pending_email=session.get('pending_email')
    return render_template('profile.html',tab=tab,cars=cars,pending_email=pending_email,
                           demo_code=pending_email.get('demo_code') if pending_email and os.getenv('OTP_MODE','api').lower()=='demo' else None)

@app.post('/profile/vehicles')
@login_required
def save_vehicle():
    data,errors=vehicle_form_errors(request.form)
    if errors:
        for e in errors: flash(e,'error')
        return redirect(url_for('profile',tab='vehicles'))
    vid=request.form.get('vehicle_id','')
    with conn() as c:
        _,error,_=save_owner_vehicle(c,session['uid'],data,int(vid) if vid.isdigit() else None)
    if error:
        flash(error,'error');return redirect(url_for('profile',tab='vehicles'))
    flash('تم حفظ المركبة بنجاح.','success');return redirect(url_for('profile',tab='vehicles'))

@app.post('/profile/vehicles/<int:vehicle_id>/delete')
@login_required
def delete_vehicle(vehicle_id):
    with conn() as c:
        car=c.execute('SELECT vehicle_id FROM vehicle WHERE vehicle_id=? AND national_id=?',(vehicle_id,session['uid'])).fetchone()
        if not car: abort(404)
        if c.execute('SELECT 1 FROM involves WHERE vehicle_id=?',(vehicle_id,)).fetchone():
            flash('لا يمكن حذف هذه المركبة لأنها مرتبطة ببلاغ.','error');return redirect(url_for('profile',tab='vehicles'))
        c.execute('DELETE FROM vehicle WHERE vehicle_id=?',(vehicle_id,))
    flash('تم حذف المركبة.','success');return redirect(url_for('profile',tab='vehicles'))

@app.get('/privacy')
def privacy_page():return render_template('legal.html',privacy=True)

@app.get('/terms')
def terms_page():return render_template('legal.html',privacy=False)

@app.get('/cases')
@login_required
def cases_page():
    with conn() as c:
        cases=user_cases(c,session['uid'])
    return render_template('dashboard.html',cases=cases,all_cases=True)

@app.get('/health')
def health():
    with conn() as c: c.execute('SELECT 1')
    return jsonify(status='ok',database='connected')

init_db()
if __name__=='__main__': app.run(debug=os.getenv('FLASK_DEBUG')=='1',port=int(os.getenv('PORT','5000')))
