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

def insert_id(c, sql, params):
    if DATABASE_URL:
        return c.execute(sql+' RETURNING id',params).fetchone()['id']
    return c.execute(sql,params).lastrowid

def init_db():
    if DATABASE_URL:
        with conn() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS users(
                id BIGSERIAL PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
                phone TEXT, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'party',
                created_at TEXT DEFAULT to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS'),
                national_id TEXT UNIQUE, birth_date TEXT,
                notification_status INTEGER DEFAULT 1, notification_result INTEGER DEFAULT 1)''')
            c.execute('''CREATE TABLE IF NOT EXISTS cases(
                id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
                creator_id BIGINT NOT NULL REFERENCES users(id), accident_type TEXT NOT NULL,
                accident_date TEXT NOT NULL, accident_time TEXT NOT NULL, location TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_second_party',
                created_at TEXT DEFAULT to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS'))''')
            c.execute('''CREATE TABLE IF NOT EXISTS parties(
                id BIGSERIAL PRIMARY KEY, case_id BIGINT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                user_id BIGINT REFERENCES users(id), position TEXT NOT NULL CHECK(position IN ('A','B')),
                full_name TEXT, national_id TEXT, phone TEXT, description TEXT,
                completed INTEGER NOT NULL DEFAULT 0, UNIQUE(case_id,position))''')
            c.execute('''CREATE TABLE IF NOT EXISTS vehicles(
                id BIGSERIAL PRIMARY KEY, party_id BIGINT NOT NULL UNIQUE REFERENCES parties(id) ON DELETE CASCADE,
                plate TEXT, manufacturer TEXT, model TEXT, year INTEGER, color TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS invitations(
                id BIGSERIAL PRIMARY KEY, case_id BIGINT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, claimed_by BIGINT REFERENCES users(id),
                created_at TEXT DEFAULT to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS'),
                recipient_email TEXT, recipient_phone TEXT, revoked_at TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS videos(
                id BIGSERIAL PRIMARY KEY, case_id BIGINT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                party_id BIGINT NOT NULL REFERENCES parties(id), original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL, processed_name TEXT, privacy_status TEXT NOT NULL DEFAULT 'pending',
                uploaded_at TEXT DEFAULT to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS'),
                processing_note TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS garage_vehicles(
                id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                plate TEXT NOT NULL, manufacturer TEXT NOT NULL, model TEXT NOT NULL,
                year INTEGER NOT NULL, color TEXT NOT NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS analysis_jobs(
                id BIGSERIAL PRIMARY KEY, video_id BIGINT NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'not_started', details TEXT,
                updated_at TEXT DEFAULT to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS'))''')
            c.execute('''CREATE TABLE IF NOT EXISTS expert_accounts(
                id BIGSERIAL PRIMARY KEY, full_name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT to_char(now() at time zone 'UTC','YYYY-MM-DD HH24:MI:SS'))''')
        return
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, phone TEXT, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'party', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY, reference TEXT NOT NULL UNIQUE, creator_id INTEGER NOT NULL REFERENCES users(id), accident_type TEXT NOT NULL, accident_date TEXT NOT NULL, accident_time TEXT NOT NULL, location TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending_second_party', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS parties(id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE, user_id INTEGER REFERENCES users(id), position TEXT NOT NULL CHECK(position IN ('A','B')), full_name TEXT, national_id TEXT, phone TEXT, description TEXT, completed INTEGER NOT NULL DEFAULT 0, UNIQUE(case_id,position));
        CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY, party_id INTEGER NOT NULL UNIQUE REFERENCES parties(id) ON DELETE CASCADE, plate TEXT, manufacturer TEXT, model TEXT, year INTEGER, color TEXT);
        CREATE TABLE IF NOT EXISTS invitations(id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE, token TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, claimed_by INTEGER REFERENCES users(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE, party_id INTEGER NOT NULL REFERENCES parties(id), original_name TEXT NOT NULL, stored_name TEXT NOT NULL, processed_name TEXT, privacy_status TEXT NOT NULL DEFAULT 'pending', uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP, processing_note TEXT);
        CREATE TABLE IF NOT EXISTS garage_vehicles(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, plate TEXT NOT NULL, manufacturer TEXT NOT NULL, model TEXT NOT NULL, year INTEGER NOT NULL, color TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS analysis_jobs(id INTEGER PRIMARY KEY, video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'not_started', details TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS expert_accounts(id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        cols={r[1] for r in c.execute('PRAGMA table_info(users)').fetchall()}
        if 'national_id' not in cols: c.execute('ALTER TABLE users ADD COLUMN national_id TEXT')
        if 'birth_date' not in cols: c.execute('ALTER TABLE users ADD COLUMN birth_date TEXT')
        if 'notification_status' not in cols: c.execute('ALTER TABLE users ADD COLUMN notification_status INTEGER DEFAULT 1')
        if 'notification_result' not in cols: c.execute('ALTER TABLE users ADD COLUMN notification_result INTEGER DEFAULT 1')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_national_id_unique ON users(national_id)')
        invite_cols={r[1] for r in c.execute('PRAGMA table_info(invitations)').fetchall()}
        if 'recipient_email' not in invite_cols: c.execute('ALTER TABLE invitations ADD COLUMN recipient_email TEXT')
        if 'recipient_phone' not in invite_cols: c.execute('ALTER TABLE invitations ADD COLUMN recipient_phone TEXT')
        if 'revoked_at' not in invite_cols: c.execute('ALTER TABLE invitations ADD COLUMN revoked_at TEXT')

def csrf():
    if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(32)
    return session['csrf']
app.jinja_env.globals['csrf_token']=csrf
@app.before_request
def protect():
    if request.method in ('POST','PUT','PATCH','DELETE'):
        if not secrets.compare_digest(request.form.get('csrf_token','') or request.headers.get('X-CSRF-Token',''), session.get('csrf','')): abort(400,'Invalid CSRF token. Refresh and retry.')

def login_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('uid') or current_user() is None:
            session.clear()
            flash('انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.','error')
            return redirect(url_for('login',next=request.path))
        return fn(*args,**kwargs)
    return wrapped

def current_user():
    if not session.get('uid'): return None
    with conn() as c: return c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
@app.context_processor
def globals_ctx(): return {'user':current_user(), 'expert_logged_in': bool(session.get('expert_authenticated'))}

def case_access(case_id):
    with conn() as c:
        case=c.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if not case: abort(404)
        party=c.execute('SELECT * FROM parties WHERE case_id=? AND user_id=?',(case_id,session.get('uid'))).fetchone()
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
    """Email-client-friendly RTL transactional email; content fragments are escaped by callers."""
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
هذه رسالة تلقائية من سياق — لا ترد على هذا البريد.<br>
إذا وصلتك الرسالة بالخطأ، يمكنك تجاهلها بأمان.<br>
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
                              'استخدمي الرمز التالي لإكمال إنشاء حسابك في سياق.',panel,
                              'لأمان حسابك، لا تشاركي رمز التحقق مع أي شخص.')


def invitation_email_html(link, reference):
    safe_link=html_escape(str(link),quote=True)
    safe_ref=html_escape(str(reference))
    panel=(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f8f5;border:1px solid #e1eae4;border-radius:12px;">'
           f'<tr><td style="padding:16px 18px;text-align:right;">'
           f'<div style="color:#718678;font-size:12px;">رقم البلاغ</div>'
           f'<div dir="ltr" style="text-align:right;color:#153d2b;font-weight:bold;font-size:17px;margin-top:6px;">{safe_ref}</div>'
           f'<div style="border-top:1px solid #dfe9e2;margin:14px 0;"></div>'
           f'<div style="color:#718678;font-size:12px;">صلاحية الدعوة</div>'
           f'<div style="color:#153d2b;font-size:14px;font-weight:bold;margin-top:6px;">7 أيام • استخدام واحد</div>'
           f'</td></tr></table>'
           f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr><td align="center" style="padding:26px 0 14px;">'
           f'<a href="{safe_link}" style="display:inline-block;background:#006b36;color:#ffffff;text-decoration:none;font-weight:bold;font-size:16px;padding:16px 30px;border-radius:9px;">فتح الدعوة والانضمام للبلاغ ←</a>'
           f'</td></tr></table>'
           f'<div style="color:#6d8175;font-size:12px;line-height:1.9;overflow-wrap:anywhere;word-break:break-word;">إذا ما فتح الزر، انسخ الرابط التالي إلى المتصفح:<br><a href="{safe_link}" style="color:#006b36;text-decoration:underline;" dir="ltr">{safe_link}</a></div>')
    return branded_email_html('دعوة خاصة • الطرف الثاني','تمت دعوتك للانضمام إلى بلاغ',
                              'وصلك طلب للمشاركة بصفتك الطرف الثاني في بلاغ حادث على سياق. افتح الدعوة، ثم سجّل الدخول أو أنشئ حسابًا ببريدك الموثّق لإكمال بياناتك وإضافة إفادتك أو فيديو الحادث إن توفر.',
                              panel,'هذا الرابط مخصص للبريد الذي استقبل الدعوة فقط. لا تشاركه مع أي شخص. لن تظهر تفاصيل البلاغ قبل التحقق من حسابك.')


def send_brevo_api_email(email, subject, body, html_body=None):
    """Send transactional email through Brevo's REST API, without exposing the API key."""
    api_key=os.getenv('BREVO_API_KEY','').strip()
    sender=os.getenv('BREVO_SENDER_EMAIL',os.getenv('SMTP_FROM','')).strip()
    sender_name=os.getenv('BREVO_SENDER_NAME','Siyaq').strip() or 'Siyaq'
    if not api_key or not sender:
        raise RuntimeError('إعدادات Brevo API غير مكتملة. أضيفي BREVO_API_KEY و BREVO_SENDER_EMAIL إلى ملف .env.')
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
        raise RuntimeError('تعذّر إرسال البريد عبر Brevo API (HTTP '+str(exc.code)+'). راجعي تفعيل API والمرسل وعناوين IP المسموحة.') from exc
    except (URLError,TimeoutError,OSError) as exc:
        app.logger.warning('Brevo API network error: %s',type(exc).__name__)
        raise RuntimeError('تعذّر الاتصال بخدمة Brevo API. تحققي من الإنترنت وحاولي مجددًا.') from exc


def send_email_otp(email, code):
    """Send the OTP using the configured transport (REST API or SMTP)."""
    body=(f'رمز التحقق من حساب سياق: {code}\nصلاحية الرمز 10 دقائق. لا تشارك هذا الرمز مع أي شخص.\n\n'
          f'Siyaq verification code: {code}\nExpires in 10 minutes.')
    if os.getenv('OTP_MODE','api').strip().lower()=='api':
        return send_brevo_api_email(email,'Siyaq | رمز التحقق من البريد الإلكتروني',body,otp_email_html(code))
    host=os.getenv('SMTP_HOST','').strip()
    username=os.getenv('SMTP_USER','').strip()
    password=os.getenv('SMTP_PASSWORD','').strip()
    sender=os.getenv('SMTP_FROM',username).strip()
    port=int(os.getenv('SMTP_PORT','587'))
    if not all((host,username,password,sender)):
        raise RuntimeError('إعدادات SMTP غير مكتملة. راجعي ملف .env.')
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
        raise RuntimeError('تعذّر إرسال رمز البريد. تحققي من إعدادات SMTP.') from exc


def send_case_invitation(email, link, reference):
    """Send a private invitation with the same email transport as registration OTP."""
    body=(
        'مرحبًا،\n\nتمت دعوتك بصفتك الطرف الثاني لاستكمال بيانات بلاغ في سياق.\n'
        'رقم البلاغ: '+reference+'\n\n'
        'افتح الرابط التالي لتسجيل الدخول بحسابك الموثّق وإضافة إفادتك وفيديو الحادث إن توفر:\n'
        +link+'\n\n'
        'الرابط صالح لمدة 7 أيام، ولمرة واحدة، ومخصص للبريد الذي استقبل الدعوة فقط.\n'
        'إذا لم تكن معنيًا بهذا البلاغ، تجاهل الرسالة. لا تشارك الرابط مع أحد.\n\nفريق سياق'
    )
    if os.getenv('OTP_MODE','api').strip().lower()=='api':
        return send_brevo_api_email(email,'Siyaq | دعوة للمشاركة في بلاغ حادث',body,invitation_email_html(link,reference))
    host=os.getenv('SMTP_HOST','').strip()
    username=os.getenv('SMTP_USER','').strip()
    password=os.getenv('SMTP_PASSWORD','').strip()
    sender=os.getenv('SMTP_FROM',username).strip()
    port=int(os.getenv('SMTP_PORT','587'))
    if not all((host,username,password,sender)):
        raise RuntimeError('إعدادات SMTP غير مكتملة. راجعي ملف .env.')
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
        raise RuntimeError('تعذّر إرسال الدعوة. تحققي من إعدادات SMTP.') from exc

def safe_invitation_next(value):
    return bool(re.fullmatch(r'/invite/[A-Za-z0-9_-]{20,100}', value or ''))

def issue_otp(pending):
    code=f'{secrets.randbelow(1000000):06d}'
    mode=os.getenv('OTP_MODE','api').strip().lower()
    if mode=='demo':
        # DEMO IS NOT IDENTITY VERIFICATION. Never permit demo outside localhost.
        if request.remote_addr not in ('127.0.0.1','::1'):
            raise RuntimeError('وضع التجربة متاح محليًا فقط. فعّل إرسال البريد الحقيقي.')
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

def registration_errors(name,nid,phone,birth,password,confirm):
    errors=[]
    if not name: errors.append('أدخل الاسم الكامل.')
    if not re.fullmatch(r'[12]\d{9}',nid): errors.append('رقم الهوية يجب أن يبدأ بـ 1 أو 2 ويتكون من 10 أرقام.')
    if not re.fullmatch(r'05\d{8}',phone): errors.append('رقم الجوال يجب أن يبدأ بـ 05 ويتكون من 10 أرقام.')
    if not birth: errors.append('اختر تاريخ الميلاد.')
    else:
        try:
            if datetime.strptime(birth,'%Y-%m-%d').date()>datetime.now().date(): errors.append('تاريخ الميلاد لا يمكن أن يكون في المستقبل.')
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
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254: errors.append('أدخل بريدًا إلكترونيًا صالحًا.')
        if errors:
            for error in errors: flash(error,'error')
        else:
            with conn() as c: exists=c.execute('SELECT id FROM users WHERE national_id=? OR email=?',(nid,email)).fetchone()
            if exists: flash('رقم الهوية الوطنية أو البريد الإلكتروني مسجل مسبقًا.','error')
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
        flash('انتهت مهلة التحقق. أعد التسجيل.','error')
        return redirect(url_for('register'))
    if request.method=='POST':
        action=request.form.get('action','verify')
        if action=='resend':
            if time.time()-pending.get('last_sent',0)<60: flash('انتظر دقيقة قبل طلب رمز جديد.','error')
            else:
                try:
                    session['pending_registration']=issue_otp(pending)
                    flash('تم طلب رمز جديد.','success')
                except RuntimeError as e: flash(str(e),'error')
        else:
            code=normalized_digits(request.form.get('code',''))
            if pending['attempts']>=5: flash('تجاوزت عدد المحاولات. ابدأ التسجيل مجددًا.','error')
            elif not re.fullmatch(r'\d{6}',code): flash('أدخل رمز التحقق الرقمي الصحيح.','error')
            else:
                pending['attempts']+=1;session['pending_registration']=pending
                try:
                    if hmac.compare_digest(otp_digest(code,pending['email']),pending.get('otp_digest','')):
                        try:
                            with conn() as c:
                                uid=insert_id(c,'INSERT INTO users(full_name,email,phone,password_hash,national_id,birth_date) VALUES(?,?,?,?,?,?)',
                                    (pending['full_name'],pending['email'],pending['phone'],pending['password_hash'],pending['national_id'],pending['birth_date']))
                                # uid returned by insert_id
                            destination=session.get('after_registration')
                            session.clear();session['uid']=uid;csrf()
                            return redirect(destination if safe_invitation_next(destination) else url_for('dashboard'))
                        except (sqlite3.IntegrityError, psycopg.IntegrityError if psycopg else sqlite3.IntegrityError): flash('رقم الهوية مسجل مسبقًا.','error')
                    else: flash('رمز التحقق غير صحيح أو انتهت صلاحيته.','error')
                except RuntimeError as e: flash(str(e),'error')
    return render_template('verify_email.html',email=pending['email'],demo_code=pending.get('demo_code') if os.getenv('OTP_MODE','api').lower()=='demo' else None)

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        nid=normalized_digits(request.form.get('national_id',''))
        with conn() as c:
            u=c.execute('SELECT * FROM users WHERE national_id=?',(nid,)).fetchone()
        if u and check_password_hash(u['password_hash'],request.form.get('password','')):
            session.clear();session['uid']=u['id'];csrf()
            nxt=request.args.get('next','')
            return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('dashboard'))
        flash('رقم الهوية الوطنية أو كلمة المرور غير صحيحة.','error')
    return render_template('auth.html',mode='login')
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
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{3,31}', username):
                flash('معرّف الخبير يجب أن يكون من ٤ إلى ٣٢ حرفًا إنجليزيًا أو رقمًا.', 'error')
            elif not 12 <= len(password) <= 128:
                flash('كلمة المرور يجب أن تحتوي على ١٢ حرفًا على الأقل.', 'error')
            elif password != confirm_password:
                flash('كلمتا المرور غير متطابقتين.', 'error')
            else:
                with conn() as c:
                    existing = c.execute('SELECT id FROM expert_accounts WHERE username=?', (username,)).fetchone()
                    if existing:
                        flash('معرّف الخبير مستخدم بالفعل.', 'error')
                    else:
                        c.execute('INSERT INTO expert_accounts(full_name, username, password_hash) VALUES(?,?,?)',
                                  (pending['full_name'], username, generate_password_hash(password)))
                        session.pop('expert_registration', None)
                        flash('تم إنشاء الحساب. يمكنك تسجيل الدخول الآن.', 'success')
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
        with conn() as c:
            expert = c.execute('SELECT id, password_hash FROM expert_accounts WHERE username=?', (username,)).fetchone()
        valid_registered = bool(expert) and check_password_hash(expert['password_hash'], password)
        expected_username = os.getenv('EXPERT_USERNAME', '').strip().lower()
        expected_hash = os.getenv('EXPERT_PASSWORD_HASH', '').strip()
        valid_legacy = (bool(expected_username) and bool(expected_hash)
                        and hmac.compare_digest(username, expected_username)
                        and check_password_hash(expected_hash, password))
        if valid_registered or valid_legacy:
            session.clear()
            session['expert_authenticated'] = True
            if valid_registered:
                session['expert_id'] = expert['id']
            csrf()
            return redirect(url_for('expert_cases'))
        flash('معرّف الخبير أو كلمة المرور غير صحيحة.', 'error')
    return render_template('expert_login.html')

@app.get('/expert/cases')
def expert_cases():
    if not session.get('expert_authenticated'):
        return redirect(url_for('expert_login'))
    with conn() as c:
        cases = c.execute('SELECT reference, accident_type, accident_date, accident_time, status, created_at FROM cases ORDER BY id DESC LIMIT 100').fetchall()
    return render_template('expert_cases.html', cases=cases)

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
        cases=c.execute('''SELECT DISTINCT ca.* FROM cases ca LEFT JOIN parties p ON p.case_id=ca.id WHERE ca.creator_id=? OR p.user_id=? ORDER BY ca.id DESC''',(session['uid'],session['uid'])).fetchall()
    return render_template('dashboard.html',cases=cases)
@app.route('/cases/new',methods=['GET','POST'])
@login_required
def new_case():
    if request.method=='POST':
        eligible=all(request.form.get(k)=='yes' for k in ('no_injuries','daylight','clear_weather','two_vehicles'))
        if not eligible:
            flash('هذه الحالة خارج نطاق سياق الحالي: الحوادث البسيطة دون إصابات، نهارًا وبطقس واضح ولمركبتين.','error')
            return redirect(url_for('new_case'))
        typ=request.form.get('accident_type'); date=request.form.get('accident_date');time=request.form.get('accident_time'); location=request.form.get('location','').strip()
        if typ not in ('REAR_END','LANE_CHANGE') or not date or not time or not location: flash('جميع بيانات الحادث مطلوبة.','error')
        else:
            ref='SQ-'+datetime.now().strftime('%y%m')+'-'+secrets.token_hex(3).upper()
            with conn() as c:
                cid=insert_id(c,'INSERT INTO cases(reference,creator_id,accident_type,accident_date,accident_time,location) VALUES(?,?,?,?,?,?)',(ref,session['uid'],typ,date,time,location))
                c.execute('INSERT INTO parties(case_id,user_id,position,full_name) VALUES(?,?,?,?)',(cid,session['uid'],'A',current_user()['full_name']))
                c.execute('INSERT INTO parties(case_id,position) VALUES(?,?)',(cid,'B'))
            return redirect(url_for('wizard',case_id=cid,step=1))
    return render_template('new_case.html')
@app.get('/cases/<int:case_id>')
@login_required
def case_detail(case_id):
    case, party = case_access(case_id)
    if not party:
        return redirect(url_for('dashboard'))
    return redirect(url_for('wizard', case_id=case_id, step=7 if party['completed'] else 1))

@app.post('/cases/<int:case_id>/invite')
@login_required
def invite(case_id):
    case,party=case_access(case_id)
    if case['creator_id']!=session['uid']: abort(403)
    recipient_email=request.form.get('recipient_email','').strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',recipient_email) or len(recipient_email)>254:
        flash('أدخل بريدًا إلكترونيًا صحيحًا للطرف الثاني.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    if current_user()['email'].strip().lower()==recipient_email:
        flash('لا يمكن إرسال الدعوة إلى بريد منشئ البلاغ نفسه.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    with conn() as c:
        second=c.execute("SELECT user_id FROM parties WHERE case_id=? AND position='B'",(case_id,)).fetchone()
        if not second or second['user_id']:
            flash('الطرف الثاني مرتبط بالبلاغ بالفعل، ولا يمكن إرسال دعوة جديدة.','error')
            return redirect(url_for('case_detail',case_id=case_id))
        latest=c.execute('SELECT created_at FROM invitations WHERE case_id=? ORDER BY id DESC LIMIT 1',(case_id,)).fetchone()
        if latest and datetime.utcnow()-datetime.fromisoformat(latest['created_at'])<timedelta(seconds=60):
            flash('يرجى الانتظار دقيقة قبل إرسال دعوة أخرى لنفس البلاغ.','error')
            return redirect(url_for('case_detail',case_id=case_id))
    token=secrets.token_urlsafe(32)
    exp=(datetime.utcnow()+timedelta(days=7)).isoformat()
    with conn() as c:
        invitation_id=insert_id(c,'INSERT INTO invitations(case_id,token,expires_at,recipient_email) VALUES(?,?,?,?)',(case_id,hashlib.sha256(token.encode()).hexdigest(),exp,recipient_email))
    public_base=os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/')
    if public_base and not re.fullmatch(r'https://[^\s/]+(?:\:[0-9]{2,5})?',public_base):
        with conn() as c: c.execute('DELETE FROM invitations WHERE id=?',(invitation_id,))
        flash('PUBLIC_BASE_URL يجب أن يكون رابط HTTPS عامًّا بدون مسار، مثل https://siyaq.example.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    link=(public_base+url_for('invitation',token=token)) if public_base else url_for('invitation',token=token,_external=True)
    if not public_base and request.host.split(':')[0] in ('localhost','127.0.0.1'):
        with conn() as c: c.execute('DELETE FROM invitations WHERE id=?',(invitation_id,))
        flash('قبل إرسال الدعوة أضيفي PUBLIC_BASE_URL لرابط موقع سياق المنشور على HTTPS؛ localhost لا يفتح على جوال الطرف الثاني.','error')
        return redirect(url_for('case_detail',case_id=case_id))
    try:
        send_case_invitation(recipient_email,link,case['reference'])
    except RuntimeError as exc:
        with conn() as c: c.execute('DELETE FROM invitations WHERE id=? AND claimed_by IS NULL',(invitation_id,))
        flash(str(exc),'error')
        return redirect(url_for('case_detail',case_id=case_id))
    with conn() as c:
        c.execute('UPDATE invitations SET revoked_at=? WHERE case_id=? AND id<>? AND claimed_by IS NULL AND revoked_at IS NULL',
                  (datetime.utcnow().isoformat(),case_id,invitation_id))
    flash('تم إرسال الدعوة إلى البريد الإلكتروني للطرف الثاني. يُرجى التحقق من صندوق الوارد والرسائل غير المرغوبة.','success')
    return redirect(url_for('case_detail',case_id=case_id))

@app.get('/invite/<token>')
def invitation(token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        inv=c.execute('SELECT * FROM invitations WHERE token=?',(digest,)).fetchone()
        if not inv: abort(404)
        valid=bool(inv['recipient_email'] and not inv['revoked_at'] and not inv['claimed_by'] and inv['expires_at']>datetime.utcnow().isoformat())
        party=c.execute("SELECT user_id FROM parties WHERE case_id=? AND position='B'",(inv['case_id'],)).fetchone()
        if not party or party['user_id']: valid=False
    user=current_user()
    matched=bool(user and user['email'].strip().lower()==inv['recipient_email'].strip().lower())
    return render_template('invitation.html',token=token,valid=valid,matched=matched,recipient_email=inv['recipient_email'])

@app.post('/invite/<token>/accept')
@login_required
def accept_invitation(token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:
        inv=c.execute('SELECT * FROM invitations WHERE token=?',(digest,)).fetchone()
        if not inv or not inv['recipient_email'] or inv['revoked_at'] or inv['expires_at']<=datetime.utcnow().isoformat() or inv['claimed_by']:
            abort(403)
        u=c.execute('SELECT email,full_name,phone FROM users WHERE id=?',(session['uid'],)).fetchone()
        if not u or u['email'].strip().lower()!=inv['recipient_email'].strip().lower(): abort(403)
        party=c.execute("SELECT * FROM parties WHERE case_id=? AND position='B'",(inv['case_id'],)).fetchone()
        if not party or party['user_id']: abort(403)
        updated=c.execute('UPDATE parties SET user_id=?,full_name=? WHERE id=? AND user_id IS NULL',
                          (session['uid'],u['full_name'],party['id']))
        if updated.rowcount!=1: abort(403)
        claimed=c.execute('UPDATE invitations SET claimed_by=? WHERE id=? AND claimed_by IS NULL AND revoked_at IS NULL',
                          (session['uid'],inv['id']))
        if claimed.rowcount!=1: abort(403)
    return redirect(url_for('wizard',case_id=inv['case_id'],step=1))

STEPS=['بيانات الحادث','بيانات الطرف','بيانات المركبة','وصف الحادث','رفع الفيديو','المراجعة','دعوة الطرف الثاني']
@app.route('/cases/<int:case_id>/steps/<int:step>',methods=['GET','POST'])
@login_required
def wizard(case_id,step):
    if step not in range(1,8): abort(404)
    case,party=case_access(case_id)
    if not party: abort(403)
    if step==7 and not party['completed']:
        return redirect(url_for('wizard',case_id=case_id,step=6))
    if request.method=='POST':
        if step==7: abort(405)
        if step==2:
            full_name=request.form.get('full_name','').strip(); national=request.form.get('national_id','').strip(); phone=request.form.get('phone','').strip()
            if not full_name or not re.fullmatch(r'05\d{8}',normalized_digits(phone)): flash('الاسم ورقم الجوال الصحيح مطلوبان.','error');return redirect(request.url)
            with conn() as c: c.execute('UPDATE parties SET full_name=?,national_id=?,phone=? WHERE id=?',(full_name,national,phone,party['id']))
        elif step==3:
            fields=['plate','manufacturer','model','year','color']
            if any(not request.form.get(k,'').strip() for k in fields) or not request.form.get('year','').isdigit():
                flash('أكمل جميع بيانات المركبة.','error'); return redirect(request.url)
            with conn() as c:
                c.execute('''INSERT INTO vehicles(party_id,plate,manufacturer,model,year,color) VALUES(?,?,?,?,?,?) ON CONFLICT(party_id) DO UPDATE SET plate=excluded.plate,manufacturer=excluded.manufacturer,model=excluded.model,year=excluded.year,color=excluded.color''',(party['id'],request.form.get('plate',''),request.form.get('manufacturer',''),request.form.get('model',''),int(request.form['year']) if request.form.get('year','').isdigit() else None,request.form.get('color','')))
        elif step==4:
            with conn() as c:c.execute('UPDATE parties SET description=? WHERE id=?',(request.form.get('description','').strip(),party['id']))
        elif step==5:
            f=request.files.get('video')
            with conn() as c:
                existing_count=c.execute('SELECT COUNT(*) AS n FROM videos WHERE party_id=?',(party['id'],)).fetchone()['n']
            if (not f or not f.filename) and not existing_count:
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
                with conn() as c:
                    video_id=insert_id(c,'INSERT INTO videos(case_id,party_id,original_name,stored_name) VALUES(?,?,?,?)',(case_id,party['id'],secure_filename(f.filename),filename))
                    c.execute('INSERT INTO analysis_jobs(video_id) VALUES(?)',(video_id,))
        elif step==6:
            with conn() as c:
                video_count=c.execute('SELECT COUNT(*) AS n FROM videos WHERE party_id=?',(party['id'],)).fetchone()['n']
            if not video_count:
                flash('يجب رفع فيديو الحادث أولًا قبل إرسال البيانات.','error')
                return redirect(url_for('wizard',case_id=case_id,step=5))
            if request.form.get('consent')!='yes': flash('يجب الموافقة قبل الإرسال.','error');return redirect(request.url)
            with conn() as c:
                c.execute('UPDATE parties SET completed=1 WHERE id=?',(party['id'],))
                count_row=c.execute('SELECT COUNT(*) AS total FROM parties WHERE case_id=? AND completed=1',(case_id,)).fetchone()
                count=count_row['total'] if DATABASE_URL else count_row[0]
                c.execute('UPDATE cases SET status=? WHERE id=?',('submitted' if count==2 else 'awaiting_other_party',case_id))
            flash('تم حفظ بياناتك بنجاح.','success');return redirect(url_for('wizard',case_id=case_id,step=7))
        return redirect(url_for('wizard',case_id=case_id,step=step+1))
    with conn() as c:
        vehicle=c.execute('SELECT * FROM vehicles WHERE party_id=?',(party['id'],)).fetchone()
        videos=c.execute('SELECT * FROM videos WHERE party_id=?',(party['id'],)).fetchall()
    with conn() as c:
        invited=c.execute("SELECT * FROM invitations WHERE case_id=? AND recipient_email IS NOT NULL ORDER BY id DESC LIMIT 1",(case_id,)).fetchone()
        other_party=c.execute("SELECT user_id FROM parties WHERE case_id=? AND position='B'",(case_id,)).fetchone()
    return render_template('wizard.html',case=case,party=party,vehicle=vehicle,videos=videos,step=step,steps=STEPS,invite=invited,other_party=other_party,cloud_upload=bool(os.getenv('VERCEL') or storage_ready() or cloudinary_ready()))
@app.post('/api/cases/<int:case_id>/videos/presign')
@login_required
def video_presign(case_id):
    case, party = case_access(case_id)
    if not party: abort(403)
    if not (cloudinary_ready() or storage_ready()):
        return jsonify(error='خدمة رفع الفيديو غير متاحة حاليًا. يرجى المحاولة لاحقًا.'), 503
    data = request.get_json(silent=True) or {}
    original = str(data.get('filename', ''))
    size = data.get('size')
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    if ext not in ALLOWED or type(size) is not int or not 0 < size <= VIDEO_MAX_BYTES:
        return jsonify(error='يرجى اختيار فيديو بصيغة مدعومة وحجم لا يتجاوز 200 ميجابايت.'), 400
    if cloudinary_ready():
        public_id = f'siyaq/cases/{case_id}/parties/{party["id"]}/{uuid.uuid4().hex}'
        timestamp = int(time.time())
        params = {'public_id': public_id, 'timestamp': timestamp, 'type': 'authenticated'}
        session['pending_video'] = {'provider': 'cloudinary', 'public_id': public_id,
                                    'case_id': case_id, 'party_id': party['id'],
                                    'name': secure_filename(original) or 'video.'+ext,
                                    'size': size, 'expires': time.time()+3600}
        return jsonify(provider='cloudinary', upload_url='https://api.cloudinary.com/v1_1/' +
                       quote(os.environ['CLOUDINARY_CLOUD_NAME'], safe='') + '/video/upload',
                       api_key=os.environ['CLOUDINARY_API_KEY'], timestamp=timestamp,
                       signature=cloudinary_sign(params), public_id=public_id,
                       delivery_type='authenticated', content_type=VIDEO_MIME[ext])
    key = f'cases/{case_id}/parties/{party["id"]}/{uuid.uuid4().hex}.{ext}'
    mime = VIDEO_MIME[ext]
    try:
        upload_url = storage_client().generate_presigned_url('put_object',
            Params={'Bucket':os.environ['S3_BUCKET'], 'Key':key, 'ContentType':mime}, ExpiresIn=600)
    except Exception:
        app.logger.exception('Could not prepare video upload')
        return jsonify(error='تعذر بدء رفع الفيديو. يرجى المحاولة لاحقًا.'), 503
    session['pending_video'] = {'key':key,'case_id':case_id,'party_id':party['id'],
                                'name':secure_filename(original) or 'video.'+ext,
                                'size':size,'expires':time.time()+600}
    return jsonify(upload_url=upload_url, content_type=mime)

@app.post('/api/cases/<int:case_id>/videos/complete')
@login_required
def video_complete(case_id):
    case, party = case_access(case_id)
    if not party: abort(403)
    pending = session.get('pending_video') or {}
    if pending.get('case_id') != case_id or pending.get('party_id') != party['id'] or pending.get('expires',0) < time.time():
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
                existing = c.execute('SELECT id FROM videos WHERE stored_name=?',
                                     ('cloudinary://' + pending['public_id'],)).fetchone()
                if not existing:
                    video_id=insert_id(c,'INSERT INTO videos(case_id,party_id,original_name,stored_name) VALUES(?,?,?,?)',
                                       (case_id,party['id'],pending['name'],'cloudinary://' + pending['public_id']))
                    c.execute('INSERT INTO analysis_jobs(video_id) VALUES(?)',(video_id,))
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
            video_id=insert_id(c,'INSERT INTO videos(case_id,party_id,original_name,stored_name) VALUES(?,?,?,?)',
                (case_id,party['id'],pending['name'],'s3://'+pending['key']))
            c.execute('INSERT INTO analysis_jobs(video_id) VALUES(?)',(video_id,))
        session.pop('pending_video', None)
    except Exception:
        app.logger.exception('Could not finalize video upload')
        return jsonify(error='تعذر حفظ الفيديو. يرجى المحاولة لاحقًا.'), 503
    return jsonify(ok=True, next_url=url_for('wizard',case_id=case_id,step=6))

@app.get('/videos/<int:video_id>/download')
@login_required
def download_video(video_id):
    with conn() as c: v=c.execute('SELECT * FROM videos WHERE id=?',(video_id,)).fetchone()
    if not v:abort(404)
    case_access(v['case_id'])
    public_id = stored_cloudinary_id(v['processed_name'] or v['stored_name'])
    if public_id:
        if not cloudinary_ready(): abort(503)
        # Cloudinary private download API issues an expiring, signed link.
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
    with conn() as c: v=c.execute('SELECT * FROM videos WHERE id=?',(video_id,)).fetchone()
    if not v:abort(404)
    case_access(v['case_id'])
    if stored_s3_key(v['stored_name']) or stored_cloudinary_id(v['stored_name']):
        flash('معالجة الفيديو ستتوفر لاحقًا.','error')
        return redirect(url_for('wizard',case_id=v['case_id'],step=5))
    from privacy import process_privacy
    result=process_privacy(UPLOAD/v['stored_name'],UPLOAD)
    with conn() as c:
        c.execute('UPDATE videos SET processed_name=?,privacy_status=?,processing_note=? WHERE id=?',(result.get('filename'),result['status'],result['note'],video_id))
        c.execute('UPDATE analysis_jobs SET status=?,details=?,updated_at=CAST(CURRENT_TIMESTAMP AS TEXT) WHERE video_id=?',('privacy_processed' if result.get('filename') else 'requires_review',result['note'],video_id))
    flash(result['note'],'success' if result.get('filename') else 'error')
    return redirect(url_for('wizard',case_id=v['case_id'],step=5))

@app.route('/profile',methods=['GET','POST'])
@login_required
def profile():
    tab=request.args.get('tab','personal')
    if request.method=='POST':
        action=request.form.get('action')
        if action=='personal':
            phone=normalized_digits(request.form.get('phone',''))
            if not re.fullmatch(r'05\d{8}',phone): flash('رقم الجوال غير صحيح.','error')
            else:
                with conn() as c:c.execute('UPDATE users SET phone=? WHERE id=?',(phone,session['uid']))
                flash('تم حفظ التغييرات.','success')
        elif action=='password':
            u=current_user(); old=request.form.get('current',''); new=request.form.get('next','')
            if not check_password_hash(u['password_hash'],old):flash('كلمة المرور الحالية غير صحيحة.','error')
            elif len(new)<8 or not re.search(r'[A-Za-z\u0600-\u06FF]',new) or not re.search(r'\d',new):flash('كلمة المرور الجديدة تتطلب ٨ أحرف وحرفًا ورقمًا.','error')
            elif new!=request.form.get('confirm',''):flash('كلمتا المرور غير متطابقتين.','error')
            else:
                with conn() as c:c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new),session['uid']))
                flash('تم تغيير كلمة المرور.','success')
        elif action=='notifications':
            with conn() as c:c.execute('UPDATE users SET notification_status=?,notification_result=? WHERE id=?',(int(request.form.get('status')=='on'),int(request.form.get('result')=='on'),session['uid']))
            flash('تم حفظ تفضيلات الإشعارات محليًا.','success')
        return redirect(url_for('profile',tab=tab))
    with conn() as c: cars=c.execute('SELECT * FROM garage_vehicles WHERE user_id=? ORDER BY id DESC',(session['uid'],)).fetchall()
    return render_template('profile.html',tab=tab,cars=cars)

@app.post('/profile/vehicles')
@login_required
def save_vehicle():
    data={k:request.form.get(k,'').strip() for k in ('plate','manufacturer','model','year','color')}
    if any(not v for v in data.values()) or not re.fullmatch(r'\d{4}',normalized_digits(data['year'])):
        flash('أكمل بيانات المركبة بما فيها سنة من أربعة أرقام.','error');return redirect(url_for('profile',tab='vehicles'))
    data['year']=normalized_digits(data['year'])
    vid=request.form.get('vehicle_id','')
    with conn() as c:
        if vid.isdigit():
            cur=c.execute('UPDATE garage_vehicles SET plate=?,manufacturer=?,model=?,year=?,color=? WHERE id=? AND user_id=?',(*[data[k] for k in ('plate','manufacturer','model','year','color')],int(vid),session['uid']))
            if not cur.rowcount:abort(404)
        else:c.execute('INSERT INTO garage_vehicles(user_id,plate,manufacturer,model,year,color) VALUES(?,?,?,?,?,?)',(session['uid'],*[data[k] for k in ('plate','manufacturer','model','year','color')]))
    flash('تم حفظ المركبة بنجاح.','success');return redirect(url_for('profile',tab='vehicles'))

@app.post('/profile/vehicles/<int:vehicle_id>/delete')
@login_required
def delete_vehicle(vehicle_id):
    with conn() as c:
        cur=c.execute('DELETE FROM garage_vehicles WHERE id=? AND user_id=?',(vehicle_id,session['uid']))
        if not cur.rowcount:abort(404)
    flash('تم حذف المركبة.','success');return redirect(url_for('profile',tab='vehicles'))

@app.get('/privacy')
def privacy_page():return render_template('legal.html',privacy=True)

@app.get('/terms')
def terms_page():return render_template('legal.html',privacy=False)

@app.get('/cases')
@login_required
def cases_page():
    with conn() as c:
        cases=c.execute('SELECT DISTINCT ca.* FROM cases ca LEFT JOIN parties p ON p.case_id=ca.id WHERE ca.creator_id=? OR p.user_id=? ORDER BY ca.id DESC',(session['uid'],session['uid'])).fetchall()
    return render_template('dashboard.html',cases=cases,all_cases=True)

@app.get('/health')
def health():
    with conn() as c: c.execute('SELECT 1')
    return jsonify(status='ok',database='connected')

init_db()
if __name__=='__main__': app.run(debug=os.getenv('FLASK_DEBUG')=='1',port=int(os.getenv('PORT','5000')))
