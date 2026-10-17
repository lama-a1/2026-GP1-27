import { useEffect, useMemo, useState } from "react"
import logo from "./assets/siyaq-logo.png"

type Screen = "landing" | "login" | "register" | "otp" | "reset" | "home" | "cases" | "wizard" | "pending" | "invite" | "party2" | "processing" | "expert-login" | "expert-register" | "expert" | "review" | "rules" | "final" | "profile" | "privacy" | "terms"

type IconName = "arrow" | "check" | "shield" | "video" | "car" | "file" | "user" | "clock" | "spark" | "upload" | "lock" | "download" | "eye" | "alert" | "menu" | "close" | "chevron" | "logout" | "edit" | "plus" | "trash" | "pin"

type Vehicle = {
  id: number
  make: string
  model: string
  year: string
  plate: string
  color: string
}

type PersonalInfo = {
  name: string
  phone: string
  email: string
}

type SharedCaseInfo = {
  type: "lane" | "rear"
  date: string
  time: string
  location: string
  /** Rear-end only: which vehicle Party A was. Party B is automatically the other one. */
  partyAPosition: "front" | "back" | null
}

const positionLabel = (p: "front" | "back" | null) =>
  p === "front"
    ? "المركبة الأمامية"
    : p === "back"
      ? "المركبة الخلفية"
      : "غير محدد"
const otherPosition = (p: "front" | "back" | null) =>
  p === "front" ? "back" : p === "back" ? "front" : null
/** Front vehicle must upload its REAR camera; rear vehicle must upload its FRONT camera. */
const requiredCamera = (p: "front" | "back" | null) =>
  p === "front" ? "الكاميرا الخلفية" : "الكاميرا الأمامية"

const ME = "هند العبدالله"

const isStrongPassword = (value: string) =>
  value.length >= 8 && /[A-Za-z\u0600-\u06FF]/.test(value) && /\d/.test(value)

const getTodayValue = () => {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

const formatCaseDate = (value: string) =>
  new Intl.DateTimeFormat("ar-SA", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(`${value}T12:00:00`))

const paths: Record<IconName, React.ReactNode> = {
  arrow: (
    <>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  shield: (
    <path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Zm-3 9 2 2 4-5" />
  ),
  video: (
    <>
      <rect x="3" y="6" width="13" height="12" rx="2" />
      <path d="m16 10 5-3v10l-5-3" />
    </>
  ),
  car: (
    <>
      <path d="m5 16-1-3 2-5h12l2 5-1 3M6 8l2-3h8l2 3M5 16v2M19 16v2" />
      <circle cx="8" cy="13.5" r=".7" />
      <circle cx="16" cy="13.5" r=".7" />
    </>
  ),
  file: (
    <>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v5h5M9 13h6M9 17h6" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c.7-4.2 3.4-6 8-6s7.3 1.8 8 6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v6l4 2" />
    </>
  ),
  spark: (
    <>
      <path d="m12 3 1.3 4.2L17 9l-3.7 1.8L12 15l-1.3-4.2L7 9l3.7-1.8L12 3Z" />
      <path d="m19 14 .7 2.3L22 17l-2.3.7L19 20l-.7-2.3L16 17l2.3-.7L19 14Z" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4m-4 4 4-4 4 4M5 15v5h14v-5" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10" width="14" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3" />
    </>
  ),
  download: (
    <>
      <path d="M12 4v11m-4-4 4 4 4-4M5 19h14" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3 2.5 20h19L12 3Z" />
      <path d="M12 9v5M12 17h.01" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  logout: (
    <>
      <path d="M10 5H5v14h5M14 8l4 4-4 4M9 12h9" />
    </>
  ),
  edit: (
    <>
      <path d="m4 20 4.5-1 10-10-3.5-3.5-10 10L4 20Z" />
      <path d="m13.5 7 3.5 3.5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  trash: (
    <>
      <path d="M5 7h14M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6" />
    </>
  ),
  pin: (
    <>
      <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
}

function Icon({ name, size = 20 }: { name: IconName size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}

function Button({
  children,
  onClick,
  variant = "primary",
  icon,
  disabled,
  type = "button",
  wide,
}: {
  children: React.ReactNode
  onClick?: () => void
  variant?: "primary" | "secondary" | "ghost" | "danger"
  icon?: IconName
  disabled?: boolean
  type?: "button" | "submit"
  wide?: boolean
}) {
  return (
    <button
      type={type}
      className={`btn btn-${variant}${wide ? " btn-wide" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {icon && <Icon name={icon} />}
      {children}
    </button>
  )
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  hint,
  error,
  dir,
  readOnly,
}: {
  label: string
  value?: string
  onChange?: (v: string) => void
  placeholder?: string
  type?: string
  hint?: string
  error?: string
  dir?: "rtl" | "ltr"
  readOnly?: boolean
}) {
  return (
    <label className={`field${error ? " field-error" : ""}`}>
      <span>{label}</span>
      <input
        aria-invalid={!!error}
        dir={dir}
        type={type}
        value={value}
        placeholder={placeholder}
        readOnly={readOnly}
        style={
          readOnly
            ? {
                background: "var(--canvas)",
                color: "var(--muted)",
                cursor: "not-allowed",
              }
            : undefined
        }
        onChange={(e) => onChange?.(e.target.value)}
      />
      {(error || hint) && <small>{error || hint}</small>}
    </label>
  )
}

function Brand({
  compact = false,
  onClick,
}: {
  compact?: boolean
  onClick?: () => void
}) {
  return (
    <button
      className="brand"
      onClick={onClick}
      aria-label="العودة إلى الرئيسية"
    >
      <img src={logo} alt="سياق" />
      {!compact && <span>تحليل واضح، وقرار بمراجعة خبير</span>}
    </button>
  )
}

function Badge({
  tone = "wait",
  children,
}: {
  tone?: "wait" | "progress" | "done" | "info"
  children: React.ReactNode
}) {
  return (
    <span className={`badge badge-${tone}`}>
      <i />
      {children}
    </span>
  )
}

function Header({
  onNavigate,
  expert = false,
}: {
  onNavigate: (s: Screen) => void
  expert?: boolean
}) {
  const [open, setOpen] = useState(false)
  return (
    <header className="header">
      <div className="shell header-inner">
        <Brand compact onClick={() => onNavigate(expert ? "expert" : "home")} />
        <nav className={open ? "nav open" : "nav"}>
          <button
            onClick={() => {
              onNavigate(expert ? "expert" : "home")
              setOpen(false)
            }}
          >
            {expert ? "الحالات" : "الرئيسية"}
          </button>
          {expert && (
            <button
              onClick={() => {
                onNavigate("rules")
                setOpen(false)
              }}
            >
              قواعد سياق
            </button>
          )}
          {!expert && (
            <button
              onClick={() => {
                onNavigate("cases")
                setOpen(false)
              }}
            >
              بلاغاتي
            </button>
          )}
          {!expert && (
            <button onClick={() => onNavigate("profile")}>
              إعدادات الحساب
            </button>
          )}
          <Button
            variant="ghost"
            icon="logout"
            onClick={() => onNavigate("landing")}
          >
            تسجيل الخروج
          </Button>
        </nav>
        <button
          className="icon-btn menu-btn"
          onClick={() => setOpen(!open)}
          aria-label="فتح القائمة"
        >
          <Icon name={open ? "close" : "menu"} />
        </button>
      </div>
    </header>
  )
}

function ProgressStory({
  active = 0,
  compact = false,
}: {
  active?: number
  compact?: boolean
}) {
  const items = [
    ["video", "الفيديو"],
    ["eye", "الأدلة"],
    ["spark", "التحليل"],
    ["file", "نسبة مقترحة"],
    ["user", "مراجعة الخبير"],
    ["shield", "قرار معتمد"],
  ] as [IconName, string][]
  return (
    <div className={`story${compact ? " compact" : ""}`}>
      {items.map(([icon, label], i) => (
        <div
          className={`story-step ${
            i < active ? "done" : i === active ? "active" : ""
          }`}
          key={label}
        >
          <span>
            <Icon name={i < active ? "check" : icon} />
          </span>
          <b>{label}</b>
          {i < items.length - 1 && <i className="story-line" />}
        </div>
      ))}
    </div>
  )
}

function Landing({ go }: { go: (s: Screen) => void }) {
  return (
    <main className="landing">
      <style>{`
      .landing .topbar .brand { flex-shrink: 0; }
      .landing .mobile-expert-link { display: none; }
      @media (max-width: 640px) {
        .landing .topbar .expert-entry { display: none; }
        .landing .topbar .top-actions .btn { min-height: 42px; padding: 8px 18px; }
        .landing .mobile-expert-link { display: block; width: 100%; text-align: center; margin-top: 14px; }
      }
    `}</style>
      <div className="topbar shell">
        <Brand compact onClick={() => go("landing")} />
        <div className="top-actions">
          <span className="expert-entry">
            <Button variant="secondary" onClick={() => go("expert-login")}>
              دخول الخبير المختص
            </Button>
          </span>
          <Button onClick={() => go("login")}>تسجيل الدخول</Button>
        </div>
      </div>
      <section className="hero shell">
        <div className="hero-copy">
          <Badge tone="info">نظام سعودي لدعم قرار الحوادث البسيطة</Badge>
          <h1>
            من فيديو الحادث
            <br />
            <em>إلى قرار واضح.</em>
          </h1>
          <p>
            يحلّل سياق تسجيل كاميرا المركبة، ويعرض الأدلة ونسبة الخطأ المقترحة
            لمختص معتمد قبل إصدار النتيجة النهائية.
          </p>
          <div className="hero-actions">
            <Button onClick={() => go("login")} icon="arrow">
              ابدأ باستخدام سياق
            </Button>
            <Button variant="secondary" onClick={() => go("register")}>
              إنشاء حساب
            </Button>
          </div>
          <div className="trust-line">
            <Icon name="shield" />
            <span>
              النتيجة لا تصبح نهائية إلا بعد مراجعة واعتماد الخبير المختص
            </span>
          </div>
          <button
            className="text-link center mobile-expert-link"
            onClick={() => go("expert-login")}
          >
            أنت خبير معتمد؟ دخول الخبير المختص
          </button>
        </div>
        <div className="hero-visual">
          <div className="road-card">
            <div className="road-head">
              <span>مسار الحالة</span>
              <Badge tone="progress">قيد المراجعة</Badge>
            </div>
            <ProgressStory active={4} compact />
            <div className="suggestion">
              <div>
                <small>النسبة المقترحة من سياق</small>
                <strong>٢٥٪</strong>
                <span>الطرف الأول</span>
              </div>
              <div className="split-bar">
                <i />
                <i />
              </div>
              <div>
                <small>بانتظار اعتماد الخبير</small>
                <strong>٧٥٪</strong>
                <span>الطرف الثاني</span>
              </div>
            </div>
            <div className="evidence-mini">
              <Icon name="eye" />
              <div>
                <b>٣ أدلة داعمة</b>
                <span>مرتبطة بالحركة والقاعدة المرورية</span>
              </div>
              <Icon name="chevron" />
            </div>
          </div>
        </div>
      </section>
      <section className="scope shell">
        <div>
          <span className="eyebrow">كيف يعمل سياق؟</span>
          <h2>تحليل مفهوم، خطوة بخطوة</h2>
        </div>
        <ProgressStory active={2} />
        <div className="eligibility">
          <div>
            <Icon name="check" />
            <span>حوادث بسيطة بدون إصابات</span>
          </div>
          <div>
            <Icon name="check" />
            <span>أضرار مادية فقط</span>
          </div>
          <div>
            <Icon name="check" />
            <span>تصادم خلفي أو تغيير مسار</span>
          </div>
          <div>
            <Icon name="check" />
            <span>نهار وطقس واضح</span>
          </div>
        </div>
        <p className="scope-note">
          <Icon name="alert" /> سياق أداة مساندة ولا يحل محل إجراءات الإبلاغ
          الرسمية أو قرار المختص.
        </p>
      </section>
      <footer>
        <div className="shell">
          <Brand compact onClick={() => go("landing")} />
          <span>© ٢٠٢٦ سياق — نموذج تجريبي</span>
          <button onClick={() => go("privacy")}>سياسة الخصوصية</button>
          <button onClick={() => go("terms")}>الشروط</button>
          <button onClick={() => go("expert-login")}>دخول الخبراء</button>
        </div>
      </footer>
    </main>
  )
}

function AuthShell({
  children,
  title,
  subtitle,
  go,
}: {
  children: React.ReactNode
  title: string
  subtitle: string
  go: (s: Screen) => void
}) {
  return (
    <main className="auth-page">
      <div className="auth-brand">
        <Brand compact onClick={() => go("landing")} />
      </div>
      <div className="auth-side">
        <div>
          <Badge tone="info">قرار بشري مدعوم بالأدلة</Badge>
          <h2>
            لأن تفاصيل الحادث
            <br />
            تصنع فارقًا.
          </h2>
          <p>
            نجمع التسجيل، والأحداث المرصودة، والقاعدة ذات الصلة في مسار واحد
            واضح.
          </p>
        </div>
        <ProgressStory active={3} compact />
      </div>
      <section className="auth-card">
        <div className="auth-title">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {children}
        <div className="auth-security">
          <Icon name="lock" /> اتصال آمن ومعلوماتك متاحة للمصرح لهم فقط
        </div>
      </section>
    </main>
  )
}

function Login({ go }: { go: (s: Screen) => void }) {
  const [id, setId] = useState("١٠٢٣٤٥٦٧٨٩")
  const [password, setPassword] = useState("12345678")
  const [error, setError] = useState("")
  const submit = () => {
    if (!id || !password)
      setError("تعذر تسجيل الدخول. تحقق من البيانات وحاول مرة أخرى.")
    else go("home")
  }
  return (
    <AuthShell
      title="مرحبًا بعودتك"
      subtitle="سجّل الدخول لمتابعة بلاغاتك أو بدء بلاغ جديد."
      go={go}
    >
      {error && (
        <div className="alert error">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}
      <div className="form-stack">
        <Field
          label="رقم الهوية الوطنية"
          value={id}
          onChange={setId}
          dir="ltr"
        />
        <Field
          label="كلمة المرور"
          value={password}
          onChange={setPassword}
          type="password"
        />
        <button className="text-link start" onClick={() => go("reset")}>
          نسيت كلمة المرور؟
        </button>
        <Button wide onClick={submit}>
          تسجيل الدخول
        </Button>
      </div>
      <div className="auth-switch">
        ليس لديك حساب؟{" "}
        <button onClick={() => go("register")}>إنشاء حساب</button>
      </div>
    </AuthShell>
  )
}

function Register({ go }: { go: (s: Screen) => void }) {
  const [name, setName] = useState("")
  const [id, setId] = useState("")
  const [phone, setPhone] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const submit = () => {
    if (!name.trim() || id.length < 10 || !phone.startsWith("05"))
      return setError("تحقق من البيانات المطلوبة قبل المتابعة.")
    if (!isStrongPassword(password))
      return setError(
        "يجب أن تتكون كلمة المرور من ٨ أحرف على الأقل وتتضمن حرفًا ورقمًا.",
      )
    if (password !== confirm) return setError("كلمتا المرور غير متطابقتين.")
    go("otp")
  }
  return (
    <AuthShell
      title="إنشاء حساب"
      subtitle="أدخل بياناتك مرة واحدة لتستخدمها في بلاغاتك القادمة."
      go={go}
    >
      {error && (
        <div className="alert error">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}
      <div className="form-grid">
        <Field
          label="الاسم الكامل"
          value={name}
          onChange={setName}
          placeholder="مثال: نورة محمد العتيبي"
        />
        <Field label="تاريخ الميلاد" type="date" />
        <Field
          label="رقم الهوية الوطنية"
          value={id}
          onChange={setId}
          placeholder="١٠ أرقام"
          dir="ltr"
          error={
            id.length > 0 && id.length < 10
              ? "تحقق من رقم الهوية الوطنية."
              : undefined
          }
        />
        <Field
          label="رقم الجوال"
          value={phone}
          onChange={setPhone}
          placeholder="05xxxxxxxx"
          dir="ltr"
          error={
            phone.length > 0 && !phone.startsWith("05")
              ? "أدخل رقم جوال صحيح."
              : undefined
          }
        />
        <Field
          label="كلمة المرور"
          value={password}
          onChange={setPassword}
          type="password"
          hint="٨ أحرف على الأقل، وتتضمن حرفًا ورقمًا."
        />
        <Field
          label="تأكيد كلمة المرور"
          value={confirm}
          onChange={setConfirm}
          type="password"
          error={
            confirm && confirm !== password
              ? "كلمتا المرور غير متطابقتين."
              : undefined
          }
        />
      </div>
      <Button wide onClick={submit}>
        متابعة وتحقق من الجوال
      </Button>
      <div className="auth-switch">
        لديك حساب؟ <button onClick={() => go("login")}>تسجيل الدخول</button>
      </div>
    </AuthShell>
  )
}

function Otp({ go }: { go: (s: Screen) => void }) {
  const [code, setCode] = useState(["", "", "", ""])
  const [error, setError] = useState("")
  return (
    <AuthShell
      title="تحقق من رقم الجوال"
      subtitle="أرسلنا رمزًا من ٤ أرقام إلى الرقم المنتهي بـ ٤٢١."
      go={go}
    >
      <div className="otp" dir="ltr">
        {code.map((v, i) => (
          <input
            key={i}
            value={v}
            maxLength={1}
            inputMode="numeric"
            aria-label={`الرقم ${i + 1}`}
            onChange={(e) => {
              const next = [...code]
              next[i] = e.target.value
              setCode(next)
            }}
          />
        ))}
      </div>
      <p className="center muted">
        يمكنك طلب رمز جديد بعد <b>٠٠:٤٨</b>
      </p>
      {error && (
        <div className="alert error">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}
      <Button
        wide
        onClick={() =>
          code.every(Boolean)
            ? go("home")
            : setError("أدخل رمز التحقق المكوّن من ٤ أرقام.")
        }
      >
        تأكيد وإنشاء الحساب
      </Button>
      <button
        className="text-link center"
        onClick={() => {
          setCode(["", "", "", ""])
          setError("")
        }}
      >
        إعادة إرسال الرمز
      </button>
    </AuthShell>
  )
}

function Reset({ go }: { go: (s: Screen) => void }) {
  const [step, setStep] = useState(0)
  const [id, setId] = useState("")
  const [code, setCode] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const titles = [
    "استعادة كلمة المرور",
    "أدخل رمز التحقق",
    "كلمة مرور جديدة",
    "تم تحديث كلمة المرور",
  ]
  const subtitles = [
    "أدخل رقم الهوية الوطنية المرتبط بحسابك.",
    "أرسلنا رمزًا تجريبيًا إلى رقم الجوال المسجل.",
    "اختر كلمة مرور قوية لحسابك.",
    "يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة.",
  ]
  const validPassword = isStrongPassword(password)
  return (
    <AuthShell title={titles[step]} subtitle={subtitles[step]} go={go}>
      {error && (
        <div className="alert error">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}
      {step === 0 && (
        <div className="form-stack">
          <Field
            label="رقم الهوية الوطنية"
            value={id}
            onChange={setId}
            placeholder="١٠ أرقام"
            dir="ltr"
          />
          <Button
            wide
            onClick={() => {
              if (id.length < 10) return setError("تحقق من رقم الهوية الوطنية.")
              setError("")
              setStep(1)
            }}
          >
            إرسال رمز التحقق عبر واتساب
          </Button>
          <p className="muted">
            إذا كانت البيانات مرتبطة بحساب مسجل، فسيتم إرسال رمز الاستعادة إلى
            رقم الجوال المسجل.
          </p>
        </div>
      )}
      {step === 1 && (
        <div className="form-stack">
          <Field
            label="رمز التحقق"
            value={code}
            onChange={setCode}
            placeholder="أدخل ١٢٣٤ للتجربة"
            dir="ltr"
          />
          <Button
            wide
            onClick={() =>
              code === "1234" || code === "١٢٣٤"
                ? (setError(""), setStep(2))
                : setError("رمز التحقق غير صحيح. استخدم ١٢٣٤ للتجربة.")
            }
          >
            تحقق من الرمز
          </Button>
          <button className="text-link center" onClick={() => setCode("")}>
            إعادة إرسال الرمز
          </button>
        </div>
      )}
      {step === 2 && (
        <div className="form-stack">
          <Field
            label="كلمة المرور الجديدة"
            value={password}
            onChange={setPassword}
            type="password"
            hint="٨ أحرف على الأقل، وتتضمن حرفًا ورقمًا."
          />
          <Field
            label="تأكيد كلمة المرور"
            value={confirm}
            onChange={setConfirm}
            type="password"
            error={
              confirm && confirm !== password
                ? "كلمتا المرور غير متطابقتين."
                : undefined
            }
          />
          <Button
            wide
            onClick={() => {
              if (!validPassword)
                return setError(
                  "اختر كلمة مرور من ٨ أحرف على الأقل وتتضمن حرفًا ورقمًا.",
                )
              if (password !== confirm)
                return setError("كلمتا المرور غير متطابقتين.")
              setError("")
              setStep(3)
            }}
          >
            حفظ كلمة المرور
          </Button>
        </div>
      )}
      {step === 3 && (
        <div className="success-panel">
          <span>
            <Icon name="check" size={28} />
          </span>
          <h3>تم تحديث كلمة المرور</h3>
          <p>أصبحت كلمة المرور الجديدة جاهزة للاستخدام.</p>
          <Button wide onClick={() => go("login")}>
            العودة لتسجيل الدخول
          </Button>
        </div>
      )}
      {step < 3 && (
        <button className="text-link center" onClick={() => go("login")}>
          العودة لتسجيل الدخول
        </button>
      )}
    </AuthShell>
  )
}

const cases = [
  {
    id: "SQ-٢٦٠١٨",
    type: "حادث تغيير مسار",
    date: "١٨ جمادى الأولى ١٤٤٨",
    car: "تويوتا كامري ٢٠٢٣",
    status: "قيد المراجعة",
    tone: "progress" as const,
    note: "تم تجهيز التحليل وبانتظار مراجعة الخبير.",
  },
  {
    id: "SQ-٢٥٩٨٤",
    type: "تصادم خلفي",
    date: "٤ جمادى الأولى ١٤٤٨",
    car: "هيونداي سوناتا ٢٠٢٢",
    status: "مكتمل",
    tone: "done" as const,
    note: "النتيجة النهائية المعتمدة متاحة.",
  },
  {
    id: "SQ-٢٦٠٢١",
    type: "تصادم خلفي",
    date: "اليوم، ١٠:٣٢ ص",
    car: "تويوتا كامري ٢٠٢٣",
    status: "قيد الانتظار",
    tone: "wait" as const,
    note: "بانتظار الطرف الآخر لإكمال بياناته.",
  },
]

function CaseCard({
  item,
  go,
}: {
  item: typeof cases[number]
  go: (s: Screen) => void
}) {
  const target =
    item.tone === "done"
      ? "final"
      : item.tone === "wait"
        ? "pending"
        : "processing"
  return (
    <button className="case-card" onClick={() => go(target)}>
      <div className="case-top">
        <span className="case-id">{item.id}</span>
        <Badge tone={item.tone}>{item.status}</Badge>
      </div>
      <div className="case-type">
        <span className="case-icon">
          <Icon name="car" />
        </span>
        <div>
          <h3>{item.type}</h3>
          <p>{item.car}</p>
        </div>
      </div>
      <div className="case-meta">
        <span>
          <Icon name="clock" />
          {item.date}
        </span>
      </div>
      <div className="case-note">
        <span>{item.note}</span>
        <Icon name="chevron" />
      </div>
    </button>
  )
}

function Home({ go }: { go: (s: Screen) => void }) {
  return (
    <>
      <Header onNavigate={go} />
      <main className="app-main shell">
        <section className="welcome">
          <div>
            <span className="eyebrow">صباح الخير</span>
            <h1>مرحبًا، نورة</h1>
            <p>يمكنك بدء بلاغ جديد أو متابعة حالة بلاغاتك الحالية.</p>
          </div>
          <Button icon="plus" onClick={() => go("wizard")}>
            إبلاغ عن حادث
          </Button>
        </section>
        <div className="attention-card">
          <span>
            <Icon name="clock" />
          </span>
          <div>
            <b>لديك حالة بانتظار الطرف الآخر</b>
            <p>سنبدأ تحليل الحالة SQ-٢٦٠٢١ فور إكمال الطرف الآخر لبياناته.</p>
          </div>
          <Button variant="secondary" onClick={() => go("pending")}>
            عرض الحالة
          </Button>
        </div>
        <section className="section-head">
          <div>
            <h2>بلاغاتي</h2>
            <p>آخر الحالات والتحديثات المرتبطة بحسابك</p>
          </div>
          <button className="text-link" onClick={() => go("cases")}>
            عرض الكل
          </button>
        </section>
        <div className="case-grid">
          {cases.map((c) => (
            <CaseCard key={c.id} item={c} go={go} />
          ))}
        </div>
        <section className="help-strip">
          <Icon name="shield" />
          <div>
            <b>هل حالتك مناسبة لسياق؟</b>
            <p>ندعم حاليًا الحوادث البسيطة بدون إصابات، نهارًا وفي طقس واضح.</p>
          </div>
          <button onClick={() => go("wizard")}>
            تحقق من الأهلية <Icon name="chevron" />
          </button>
        </section>
      </main>
    </>
  )
}

function Cases({ go }: { go: (s: Screen) => void }) {
  const [filter, setFilter] = useState("الكل")
  const filters = ["الكل", "قيد الانتظار", "قيد المراجعة", "مكتمل"]
  const visible =
    filter === "الكل" ? cases : cases.filter((item) => item.status === filter)
  return (
    <>
      <Header onNavigate={go} />
      <main className="app-main shell">
        <section className="welcome">
          <div>
            <span className="eyebrow">متابعة الحالات</span>
            <h1>بلاغاتي</h1>
            <p>جميع الحالات المرتبطة بحسابك في مكان واحد.</p>
          </div>
          <Button icon="plus" onClick={() => go("wizard")}>
            إبلاغ عن حادث
          </Button>
        </section>
        <div className="tabs">
          {filters.map((item) => (
            <button
              key={item}
              className={filter === item ? "active" : ""}
              onClick={() => setFilter(item)}
            >
              {item}
              <span>
                {item === "الكل"
                  ? cases.length
                  : cases.filter((entry) => entry.status === item).length}
              </span>
            </button>
          ))}
        </div>
        {visible.length ? (
          <div className="case-grid">
            {visible.map((item) => (
              <CaseCard key={item.id} item={item} go={go} />
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <span>
              <Icon name="file" size={30} />
            </span>
            <h3>لا توجد حالات في هذا التصنيف</h3>
            <p>اختر تصنيفًا آخر أو ابدأ بلاغًا جديدًا.</p>
          </div>
        )}
      </main>
    </>
  )
}

function Stepper({ step, steps }: { step: number steps: string[] }) {
  return (
    <div className="stepper-wrap">
      <div className="mobile-step">
        <span>
          الخطوة {step + 1} من {steps.length}
        </span>
        <b>{steps[step]}</b>
        <div>
          <i style={{ width: `${((step + 1) / steps.length) * 100}%` }} />
        </div>
      </div>
      <div className="stepper">
        {steps.map((s, i) => (
          <div
            className={i === step ? "active" : i < step ? "done" : ""}
            key={s}
          >
            <span>{i < step ? <Icon name="check" /> : i + 1}</span>
            <b>{s}</b>
          </div>
        ))}
      </div>
    </div>
  )
}

function ChoiceCard({
  icon,
  title,
  text,
  selected,
  onClick,
}: {
  icon: IconName
  title: string
  text: string
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      className={`choice-card${selected ? " selected" : ""}`}
      onClick={onClick}
    >
      <span>
        <Icon name={icon} size={28} />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
      <i>{selected && <Icon name="check" />}</i>
    </button>
  )
}

function AccidentPartyFlow({
  go,
  vehicles,
  role,
  shared,
  setShared,
}: {
  go: (s: Screen) => void
  vehicles: Vehicle[]
  role: "A" | "B"
  shared: SharedCaseInfo
  setShared: React.Dispatch<React.SetStateAction<SharedCaseInfo>>
}) {
  const isPartyB = role === "B"
  const steps = isPartyB
    ? [
        "معلومات الحادث",
        "بيانات الطرف",
        "بيانات المركبة",
        "وصف الحادث",
        "رفع الفيديو",
        "المراجعة",
      ]
    : [
        "بيانات الحادث",
        "بيانات الطرف",
        "بيانات المركبة",
        "وصف الحادث",
        "رفع الفيديو",
        "المراجعة",
        "دعوة الطرف الثاني",
      ]
  const [step, setStep] = useState(0)
  const [eligible, setEligible] = useState([true, true, true, true])
  const [vehicle, setVehicle] = useState(
    isPartyB && vehicles.length > 1 ? 1 : 0,
  )
  const [uploaded, setUploaded] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [videoChoice, setVideoChoice] = useState<boolean | null>(
    isPartyB ? null : true,
  )
  const [phone, setPhone] = useState("055 784 3621")
  const [partyPersonal, setPartyPersonal] = useState({
    name: isPartyB ? "سلمان عبدالله القحطاني" : "نورة محمد العتيبي",
    birthDate: isPartyB ? "١٤١٥/٠٤/٢١" : "١٤١٨/٠٨/١٢",
    nationalId: isPartyB ? "١٠٧٦٣٢١٩٤٢" : "١٠٢٣٤٥٦٧٨٩",
    mobile: isPartyB ? "055 784 3621" : "055 321 8421",
  })
  const [description, setDescription] = useState(
    isPartyB
      ? "كنت أسير في المسار الأيسر، وعند الانتقال للمسار الأوسط حدث الاصطدام مع المركبة الأخرى."
      : "كنت أسير في المسار الأوسط، ثم انتقلت المركبة الأخرى من المسار الأيسر أمامي قبل وقوع الاصطدام.",
  )
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState("")
  const [consent, setConsent] = useState(false)
  useEffect(() => {
    if (!uploading) return
    const id = window.setInterval(
      () =>
        setProgress((p) => {
          if (p >= 100) {
            window.clearInterval(id)
            setUploading(false)
            setUploaded(true)
            return 100
          }
          return p + 10
        }),
      80,
    )
    return () => window.clearInterval(id)
  }, [uploading])
  const locate = () => {
    if (!navigator.geolocation) {
      setLocationError("تعذر تحديد موقعك تلقائيًا. يمكنك كتابة الموقع يدويًا.")
      return
    }
    setLocating(true)
    setLocationError("")
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setShared((value) => ({
          ...value,
          location: `طريق الملك فهد، حي العليا، الرياض (${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)})`,
        }))
        setLocating(false)
      },
      () => {
        setLocationError(
          "لم نتمكن من الوصول إلى موقعك. يمكنك كتابة الموقع يدويًا والمتابعة.",
        )
        setLocating(false)
      },
      { enableHighAccuracy: false, timeout: 8000 },
    )
  }
  const selectedVehicle = vehicles[vehicle] || vehicles[0]
  const isRear = shared.type === "rear"
  const myPosition = isPartyB
    ? otherPosition(shared.partyAPosition)
    : shared.partyAPosition
  const cameraNeeded = isRear ? requiredCamera(myPosition) : "الكاميرا الأمامية"
  const sharedComplete =
    shared.location.trim().length >= 4 &&
    !!shared.date &&
    !!shared.time &&
    !!shared.type &&
    (!isRear || !!shared.partyAPosition)
  const canNext =
    step === 0
      ? isPartyB || (eligible.every(Boolean) && sharedComplete)
      : step === 1
        ? partyPersonal.name.trim().length > 2 &&
          partyPersonal.nationalId.length >= 10 &&
          partyPersonal.mobile.replace(/\s/g, "").length >= 10
        : step === 2
          ? vehicles.length > 0
          : step === 3
            ? description.trim().length > 10
            : step === 4
              ? isPartyB
                ? videoChoice !== null && (!videoChoice || uploaded)
                : uploaded
              : step === 5
                ? isPartyB
                  ? !uploaded || consent
                  : consent
                : phone.replace(/\s/g, "").length >= 10
  const next = () => {
    if (!isPartyB && step === 6) return go("pending")
    if (isPartyB && step === 5) return go("processing")
    setStep((current) => current + 1)
  }
  const title = isPartyB ? "إكمال بيانات الحادث" : "إبلاغ عن حادث"
  const partyLabel = isPartyB ? "الطرف الثاني" : "الطرف الأول"
  return (
    <>
      <Header onNavigate={go} />
      <main className="wizard-page">
        <div className="shell wizard-shell">
          {isPartyB && (
            <div className="invited-banner">
              <Icon name="lock" />
              <div>
                <b>أنت تساهم في الحالة SQ-٢٦٠٢١ بصفتك الطرف الثاني</b>
                <span>
                  حالة حادث واحدة · تُجمع بيانات الطرفين في تقرير مشترك
                </span>
              </div>
            </div>
          )}
          <div className="wizard-header">
            <button
              className="back-link"
              onClick={() =>
                step ? setStep(step - 1) : go(isPartyB ? "invite" : "home")
              }
            >
              <Icon name="arrow" /> رجوع
            </button>
            <div>
              <h1>{title}</h1>
              <p>{partyLabel} · سنحفظ تقدمك تلقائيًا أثناء إكمال الخطوات.</p>
            </div>
            <span className="save-state">
              <Icon name="check" /> تم الحفظ
            </span>
          </div>
          <Stepper step={step} steps={steps} />
          <section className="wizard-card">
            {step === 0 && (
              <div className="step-content">
                <div className="step-title">
                  <span className="step-icon">
                    <Icon name="shield" />
                  </span>
                  <div>
                    <h2>
                      {isPartyB ? "معلومات الحادث" : "بيانات الحادث المشتركة"}
                    </h2>
                    <p>
                      {isPartyB
                        ? "أدخل الطرف الأول هذه المعلومات، ويمكنك مراجعتها دون إعادة إدخالها."
                        : "تُدخل مرة واحدة وتصبح مرتبطة بالحالة التي سينضم إليها الطرف الثاني."}
                    </p>
                  </div>
                  <Badge tone="info">
                    {isPartyB ? "للقراءة فقط" : "معلومات مشتركة"}
                  </Badge>
                </div>
                {isPartyB ? (
                  <div className="summary-grid">
                    <div>
                      <span>رقم الحالة</span>
                      <b>SQ-٢٦٠٢١</b>
                    </div>
                    <div>
                      <span>نوع الحادث</span>
                      <b>
                        {shared.type === "lane"
                          ? "حادث تغيير مسار"
                          : "تصادم خلفي"}
                      </b>
                    </div>
                    <div>
                      <span>تاريخ الحادث</span>
                      <b>{formatCaseDate(shared.date)}</b>
                    </div>
                    <div>
                      <span>وقت الحادث</span>
                      <b>{shared.time}</b>
                    </div>
                    <div>
                      <span>موقع الحادث</span>
                      <b>{shared.location}</b>
                    </div>
                    {isRear && (
                      <div>
                        <span>موقع مركبتك</span>
                        <b>{positionLabel(myPosition)}</b>
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="check-list">
                      {[
                        "حادث بسيط بدون إصابات",
                        "الأضرار مادية فقط",
                        "وقع الحادث نهارًا",
                        "الطقس والرؤية واضحان",
                      ].map((x, i) => (
                        <label key={x}>
                          <input
                            type="checkbox"
                            checked={eligible[i]}
                            onChange={() =>
                              setEligible(
                                eligible.map((v, j) => (j === i ? !v : v)),
                              )
                            }
                          />
                          <span>
                            <Icon name="check" />
                          </span>
                          {x}
                        </label>
                      ))}
                    </div>
                    <div className="divider" />
                    <h3 className="subhead">نوع الحادث</h3>
                    <div className="choice-grid">
                      <ChoiceCard
                        icon="car"
                        title="حادث تغيير مسار"
                        text="انتقال إحدى المركبات بين المسارات قبل الاصطدام."
                        selected={shared.type === "lane"}
                        onClick={() =>
                          setShared((value) => ({
                            ...value,
                            type: "lane",
                            partyAPosition: null,
                          }))
                        }
                      />
                      <ChoiceCard
                        icon="car"
                        title="تصادم خلفي"
                        text="اصطدام مقدمة مركبة بمؤخرة مركبة أخرى."
                        selected={shared.type === "rear"}
                        onClick={() =>
                          setShared((value) => ({ ...value, type: "rear" }))
                        }
                      />
                    </div>
                    {isRear && (
                      <div style={{ marginTop: 24 }}>
                        <h3 className="subhead">أي مركبة كنت تقود؟ *</h3>
                        <div className="choice-grid">
                          <ChoiceCard
                            icon="car"
                            title="المركبة الأمامية"
                            text="صُدمت مركبتي من الخلف. سيُطلب منك تسجيل الكاميرا الخلفية."
                            selected={shared.partyAPosition === "front"}
                            onClick={() =>
                              setShared((value) => ({
                                ...value,
                                partyAPosition: "front",
                              }))
                            }
                          />
                          <ChoiceCard
                            icon="car"
                            title="المركبة الخلفية"
                            text="صدمت مقدمة مركبتي المركبة التي أمامي. سيُطلب منك تسجيل الكاميرا الأمامية."
                            selected={shared.partyAPosition === "back"}
                            onClick={() =>
                              setShared((value) => ({
                                ...value,
                                partyAPosition: "back",
                              }))
                            }
                          />
                        </div>
                      </div>
                    )}
                    <div style={{ height: 20 }} />
                    <div className="form-grid">
                      <Field
                        label="تاريخ الحادث"
                        value={shared.date}
                        onChange={(date) =>
                          setShared((value) => ({ ...value, date }))
                        }
                        type="date"
                        hint="تم اختيار تاريخ اليوم تلقائيًا ويمكنك تعديله."
                      />
                      <Field
                        label="وقت الحادث"
                        value={shared.time}
                        onChange={(time) =>
                          setShared((value) => ({ ...value, time }))
                        }
                        type="time"
                      />
                    </div>
                    <label
                      className={`field${locationError ? " field-error" : ""}`}
                    >
                      <span>موقع الحادث</span>
                      <div className="location-row">
                        <input
                          value={shared.location}
                          onChange={(e) => {
                            setShared((value) => ({
                              ...value,
                              location: e.target.value,
                            }))
                            setLocationError("")
                          }}
                          placeholder="مثال: طريق الملك فهد، حي العليا، الرياض"
                        />
                        <Button
                          variant="secondary"
                          icon="pin"
                          onClick={locate}
                          disabled={locating}
                        >
                          {locating ? "جاري التحديد..." : "موقعي الحالي"}
                        </Button>
                      </div>
                      {locationError && <small>{locationError}</small>}
                    </label>
                    {!eligible.every(Boolean) && (
                      <div className="alert warning">
                        <Icon name="alert" />
                        <span>
                          <b>هذه الحالة خارج نطاق سياق حاليًا.</b> يدعم سياق
                          الحوادث البسيطة نهارًا وفي طقس ورؤية واضحين.
                        </span>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
            {step === 1 && (
              <div className="step-content">
                <div className="step-title">
                  <span className="step-icon">
                    <Icon name="user" />
                  </span>
                  <div>
                    <h2>بيانات {partyLabel}</h2>
                    <p>
                      استرجعناها من الحساب. الاسم ورقم الهوية غير قابلين
                      للتعديل.
                    </p>
                  </div>
                  <Badge tone="info">{partyLabel}</Badge>
                </div>
                <div className="prefill">
                  <Icon name="check" /> بيانات مسترجعة من حسابك
                </div>
                <div className="form-grid">
                  <Field
                    label="الاسم الكامل"
                    value={partyPersonal.name}
                    readOnly
                    hint="مسترجع من الهوية ولا يمكن تعديله."
                  />
                  <Field
                    label="تاريخ الميلاد"
                    value={partyPersonal.birthDate}
                    onChange={(birthDate) =>
                      setPartyPersonal((value) => ({ ...value, birthDate }))
                    }
                  />
                  <Field
                    label="رقم الهوية الوطنية"
                    value={partyPersonal.nationalId}
                    readOnly
                    dir="ltr"
                    hint="لا يمكن تعديل رقم الهوية."
                  />
                  <Field
                    label="رقم الجوال"
                    value={partyPersonal.mobile}
                    onChange={(mobile) =>
                      setPartyPersonal((value) => ({ ...value, mobile }))
                    }
                    dir="ltr"
                  />
                </div>
              </div>
            )}
            {step === 2 && (
              <div className="step-content">
                <div className="step-title">
                  <span className="step-icon">
                    <Icon name="car" />
                  </span>
                  <div>
                    <h2>مركبة {partyLabel}</h2>
                    <p>اختر المركبة التي كانت في الحادث.</p>
                  </div>
                </div>
                <div className="vehicle-list">
                  {vehicles.map((item, i) => (
                    <button
                      className={`vehicle-card${
                        vehicle === i ? " selected" : ""
                      }`}
                      onClick={() => setVehicle(i)}
                      key={item.id}
                    >
                      <span>
                        <Icon name="car" size={28} />
                      </span>
                      <div>
                        <h3>
                          {item.make} {item.model} — {item.year}
                        </h3>
                        <p>
                          {item.plate} · {item.color}
                        </p>
                      </div>
                      <i>{vehicle === i && <Icon name="check" />}</i>
                    </button>
                  ))}
                  <button className="add-card" onClick={() => go("profile")}>
                    <Icon name="plus" />
                    <span>إضافة مركبة جديدة من الإعدادات</span>
                  </button>
                </div>
              </div>
            )}
            {step === 3 && (
              <div className="step-content narrow">
                <div className="step-title">
                  <span className="step-icon">
                    <Icon name="file" />
                  </span>
                  <div>
                    <h2>وصف {partyLabel} للحادث</h2>
                    <p>
                      اكتب باختصار ما حدث من وجهة نظرك، وسيظهر الوصف للخبير بشكل
                      منفصل.
                    </p>
                  </div>
                </div>
                <label className="field">
                  <span>وصف الحادث</span>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={7}
                    placeholder="مثال: كنت أسير في مساري..."
                  />
                  <small>{description.length} / ٥٠٠ حرف</small>
                </label>
                <div className="tip-card">
                  <Icon name="spark" />
                  <div>
                    <b>اكتب الوقائع كما شاهدتها</b>
                    <p>
                      اذكر اتجاه الحركة وما حدث قبل الاصطدام، دون الحاجة لتحديد
                      الطرف المخطئ.
                    </p>
                  </div>
                </div>
              </div>
            )}
            {step === 4 && (
              <div className="step-content">
                <div className="step-title">
                  <span className="step-icon">
                    <Icon name="video" />
                  </span>
                  <div>
                    <h2>
                      {isPartyB
                        ? "رفع فيديو كاميرا السيارة (اختياري)"
                        : "رفع فيديو كاميرا السيارة *"}
                    </h2>
                    <p>
                      {isPartyB
                        ? "يمكنك المتابعة دون فيديو إذا لم يكن لديك تسجيل."
                        : "الفيديو مطلوب من الطرف الأول لبدء تحليل الحالة."}
                      {isRear && (
                        <>
                          <br />
                          <b>المطلوب: تسجيل {cameraNeeded}</b> لأنك{" "}
                          {positionLabel(myPosition)}.
                        </>
                      )}
                    </p>
                  </div>
                  <Badge tone="info">{isPartyB ? "اختياري" : "مطلوب"}</Badge>
                </div>
                {isPartyB && (
                  <div className="choice-grid single">
                    <ChoiceCard
                      icon="upload"
                      title="نعم، لدي فيديو"
                      text="ارفع تسجيلًا واحدًا مرتبطًا بالحادث."
                      selected={videoChoice === true}
                      onClick={() => setVideoChoice(true)}
                    />
                    <ChoiceCard
                      icon="video"
                      title="لا يوجد لدي فيديو"
                      text="يمكنك المتابعة دون رفع ملف."
                      selected={videoChoice === false}
                      onClick={() => {
                        setVideoChoice(false)
                        setUploaded(false)
                      }}
                    />
                  </div>
                )}
                {(!isPartyB || videoChoice) && !uploaded && !uploading && (
                  <button
                    className="upload-zone"
                    onClick={() => {
                      setProgress(0)
                      setUploading(true)
                    }}
                  >
                    <span>
                      <Icon name="upload" size={30} />
                    </span>
                    <h3>
                      {isRear
                        ? `اختر تسجيل ${cameraNeeded}`
                        : "اختر فيديو الحادث"}
                    </h3>
                    <p>من تطبيق الصور أو الملفات على جهازك</p>
                    <b>MP4 أو MOV · حتى ٢ جيجابايت</b>
                  </button>
                )}
                {uploading && (
                  <div className="file-card">
                    <span className="file-thumb">
                      <Icon name="video" />
                    </span>
                    <div className="file-info">
                      <div>
                        <b>CAM_2026-11-03_1032.MOV</b>
                        <span>{progress}%</span>
                      </div>
                      <p>جاري رفع الفيديو، لا تغلق الصفحة</p>
                      <div className="progress">
                        <i style={{ width: `${progress}%` }} />
                      </div>
                    </div>
                    <button
                      className="icon-btn"
                      onClick={() => setUploading(false)}
                    >
                      <Icon name="close" />
                    </button>
                  </div>
                )}
                {uploaded && (
                  <div className="file-card success">
                    <span className="file-thumb">
                      <Icon name="video" />
                    </span>
                    <div className="file-info">
                      <div>
                        <b>CAM_2026-11-03_1032.MOV</b>
                        <Badge tone="done">تم التحقق</Badge>
                      </div>
                      <p>١٢٨ ميجابايت · ٠١:٤٢ دقيقة</p>
                    </div>
                    <button
                      className="text-link"
                      onClick={() => setUploaded(false)}
                    >
                      استبدال
                    </button>
                  </div>
                )}
                <div className="tip-card">
                  <Icon name="spark" />
                  <div>
                    <b>أي تسجيل أختار؟</b>
                    <p>
                      {!isRear
                        ? "اختر المقطع المواجه للطريق الذي يُظهر المركبة الأخرى وحركة تغيير المسار بوضوح. لا يلزم رفع تسجيل من كاميرتين."
                        : myPosition === "front"
                          ? "بما أنك المركبة الأمامية، ارفع تسجيل الكاميرا الخلفية الذي يُظهر المركبة القادمة من الخلف حتى لحظة الاصطدام."
                          : "بما أنك المركبة الخلفية، ارفع تسجيل الكاميرا الأمامية الذي يُظهر المركبة التي أمامك حتى لحظة الاصطدام."}
                    </p>
                  </div>
                </div>
              </div>
            )}
            {step === 5 && (
              <div className="step-content narrow">
                <div className="step-title">
                  <span className="step-icon">
                    <Icon name="check" />
                  </span>
                  <div>
                    <h2>راجع معلومات {partyLabel}</h2>
                    <p>
                      تأكد من المعلومات قبل إرسال مساهمتك في الحالة المشتركة.
                    </p>
                  </div>
                </div>
                <div className="review-grid">
                  <div className="review-item">
                    <div>
                      <span>معلومات الحادث المشتركة</span>
                      <p>
                        {shared.type === "lane"
                          ? "حادث تغيير مسار"
                          : "تصادم خلفي"}{" "}
                        · {formatCaseDate(shared.date)} · {shared.time}
                        <br />
                        {shared.location}
                        {isRear && (
                          <>
                            <br />
                            موقع مركبتك: {positionLabel(myPosition)}
                          </>
                        )}
                      </p>
                    </div>
                    {!isPartyB && (
                      <button onClick={() => setStep(0)}>
                        <Icon name="edit" /> تعديل
                      </button>
                    )}
                  </div>
                  <div className="review-item">
                    <div>
                      <span>بيانات {partyLabel}</span>
                      <p>
                        {partyPersonal.name} · {partyPersonal.mobile}
                      </p>
                    </div>
                    <button onClick={() => setStep(1)}>
                      <Icon name="edit" /> تعديل
                    </button>
                  </div>
                  <div className="review-item">
                    <div>
                      <span>مركبة {partyLabel}</span>
                      <p>
                        {selectedVehicle
                          ? `${selectedVehicle.make} ${selectedVehicle.model} ${selectedVehicle.year} · ${selectedVehicle.plate}`
                          : "لم تُحدد مركبة"}
                      </p>
                    </div>
                    <button onClick={() => setStep(2)}>
                      <Icon name="edit" /> تعديل
                    </button>
                  </div>
                  <div className="review-item">
                    <div>
                      <span>وصف {partyLabel}</span>
                      <p>{description}</p>
                    </div>
                    <button onClick={() => setStep(3)}>
                      <Icon name="edit" /> تعديل
                    </button>
                  </div>
                  <div className="review-item">
                    <div>
                      <span>فيديو كاميرا السيارة</span>
                      <p>
                        {uploaded
                          ? isRear
                            ? `تم إرفاق تسجيل ${cameraNeeded}`
                            : "تم إرفاق فيديو صالح"
                          : "لا يوجد فيديو — اختياري للطرف الثاني"}
                      </p>
                    </div>
                    <button onClick={() => setStep(4)}>
                      <Icon name="edit" /> تعديل
                    </button>
                  </div>
                </div>
                {(!isPartyB || uploaded) && (
                  <label className="consent">
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                    />
                    <span>
                      <Icon name="check" />
                    </span>
                    <div>
                      <b>أوافق على معالجة فيديو الحادث</b>
                      <p>
                        سيُستخدم الفيديو لتحليل هذه الحالة فقط، ويقتصر الوصول
                        عليه للمصرح لهم.
                      </p>
                    </div>
                  </label>
                )}
              </div>
            )}
            {!isPartyB && step === 6 && (
              <div className="step-content narrow">
                <div className="step-title">
                  <span className="step-icon">
                    <Icon name="user" />
                  </span>
                  <div>
                    <h2>دعوة الطرف الثاني</h2>
                    <p>
                      اكتملت بيانات الحادث والطرف الأول. سترتبط الدعوة بالحالة
                      SQ-٢٦٠٢١.
                    </p>
                  </div>
                </div>
                <div className="alert info">
                  <Icon name="check" />
                  <span>
                    <b>تمت تهيئة الحالة بنجاح.</b> لن يُطلب من الطرف الثاني إعادة
                    إدخال نوع الحادث أو التاريخ أو الوقت أو الموقع.
                  </span>
                </div>
                <Field
                  label="رقم جوال الطرف الثاني"
                  value={phone}
                  onChange={setPhone}
                  dir="ltr"
                  hint="سنرسل رابطًا آمنًا للانضمام إلى هذه الحالة وإكمال بيانات الطرف الثاني."
                />
                <div className="privacy-note">
                  <Icon name="lock" />
                  <p>
                    سيشاهد الطرف الثاني ملخص معلومات الحادث المشتركة وبيانات
                    المركبة اللازمة للتأكد من الحالة، دون بياناتك الشخصية.
                  </p>
                </div>
              </div>
            )}
            <div className="wizard-actions">
              <Button
                variant="secondary"
                onClick={() =>
                  step ? setStep(step - 1) : go(isPartyB ? "invite" : "home")
                }
              >
                {step ? "السابق" : "إلغاء"}
              </Button>
              <Button
                disabled={!canNext}
                onClick={next}
                icon={
                  (!isPartyB && step === 6) || (isPartyB && step === 5)
                    ? "check"
                    : "arrow"
                }
              >
                {!isPartyB && step === 6
                  ? "إرسال دعوة الطرف الثاني"
                  : isPartyB && step === 5
                    ? "إرسال بيانات الطرف الثاني"
                    : step === 5
                      ? "متابعة لدعوة الطرف الثاني"
                      : "متابعة"}
              </Button>
            </div>
          </section>
        </div>
      </main>
    </>
  )
}

function Wizard({
  go,
  vehicles,
  shared,
  setShared,
}: {
  go: (s: Screen) => void
  vehicles: Vehicle[]
  shared: SharedCaseInfo
  setShared: React.Dispatch<React.SetStateAction<SharedCaseInfo>>
}) {
  return (
    <AccidentPartyFlow
      go={go}
      vehicles={vehicles}
      role="A"
      shared={shared}
      setShared={setShared}
    />
  )
}

function Pending({ go }: { go: (s: Screen) => void }) {
  const [toast, setToast] = useState("")
  const copyCase = async () => {
    try {
      await navigator.clipboard.writeText("SQ-٢٦٠٢١")
      setToast("تم نسخ رقم الحالة.")
    } catch {
      setToast("رقم الحالة: SQ-٢٦٠٢١")
    }
  }
  return (
    <>
      <Header onNavigate={go} />
      <main className="status-page shell">
        <button className="back-link" onClick={() => go("home")}>
          <Icon name="arrow" /> العودة لبلاغاتي
        </button>
        <section className="success-hero">
          <span>
            <Icon name="check" size={32} />
          </span>
          <Badge tone="wait">قيد الانتظار</Badge>
          <h1>تم إنشاء الحالة بنجاح</h1>
          <p>
            تم إرسال رابط للطرف الآخر لإكمال بياناته. سنبدأ التحليل بعد
            استلامها.
          </p>
          <div className="case-number">
            <small>رقم الحالة</small>
            <b>SQ-٢٦٠٢١</b>
            <button onClick={copyCase}>نسخ</button>
          </div>
        </section>
        <section className="journey-card">
          <h2>ما الخطوة التالية؟</h2>
          <div className="vertical-timeline">
            <div className="done">
              <span>
                <Icon name="check" />
              </span>
              <div>
                <b>تم إرسال بياناتك</b>
                <small>اليوم، ١٠:٣٢ ص</small>
              </div>
            </div>
            <div className="active">
              <span>
                <Icon name="clock" />
              </span>
              <div>
                <b>بانتظار الطرف الآخر</b>
                <small>أرسلنا الرابط إلى الرقم المنتهي بـ ٦٢١</small>
              </div>
            </div>
            <div>
              <span>٣</span>
              <div>
                <b>تحليل الحالة</b>
                <small>يبدأ بعد اكتمال بيانات الطرفين</small>
              </div>
            </div>
            <div>
              <span>٤</span>
              <div>
                <b>مراجعة الخبير</b>
                <small>يعتمد المختص النتيجة النهائية</small>
              </div>
            </div>
            <div>
              <span>٥</span>
              <div>
                <b>النتيجة النهائية</b>
                <small>ستصلك عند الاعتماد</small>
              </div>
            </div>
          </div>
          <div className="status-actions">
            <Button
              onClick={() =>
                setToast("تمت إعادة إرسال رابط الدعوة للطرف الآخر.")
              }
            >
              إعادة إرسال الدعوة
            </Button>
            <Button variant="secondary" onClick={() => go("cases")}>
              عرض بلاغاتي
            </Button>
            <Button variant="secondary" onClick={() => go("home")}>
              العودة للرئيسية
            </Button>
          </div>
        </section>
        <div className="demo-bridge">
          <span>مسار العرض التفاعلي</span>
          <p>انتقل إلى تجربة الرابط كما يراه الطرف الآخر.</p>
          <Button variant="secondary" onClick={() => go("invite")}>
            فتح دعوة الطرف الآخر
          </Button>
        </div>
        {toast && (
          <div className="toast">
            <Icon name="check" />
            <span>{toast}</span>
            <button onClick={() => setToast("")}>
              <Icon name="close" />
            </button>
          </div>
        )}
      </main>
    </>
  )
}

function Invite({
  go,
  shared,
}: {
  go: (s: Screen) => void
  shared: SharedCaseInfo
}) {
  return (
    <main className="invite-page">
      <div className="invite-top">
        <Brand compact onClick={() => go("landing")} />
        <Badge tone="info">
          <Icon name="lock" /> رابط آمن
        </Badge>
      </div>
      <section className="invite-card">
        <span className="invite-icon">
          <Icon name="car" size={30} />
        </span>
        <h1>دعوة للانضمام إلى بلاغ حادث</h1>
        <p>تمت دعوتك لإكمال بياناتك كطرف ثانٍ في حادث مسجل مسبقًا.</p>
        <div className="invite-summary">
          <div>
            <span>رقم الحالة</span>
            <b>SQ-٢٦٠٢١</b>
          </div>
          <div>
            <span>تاريخ الحادث</span>
            <b>{formatCaseDate(shared.date)}</b>
          </div>
          <div>
            <span>وقت الحادث</span>
            <b>{shared.time}</b>
          </div>
          <div>
            <span>موقع الحادث</span>
            <b>{shared.location}</b>
          </div>
          <div>
            <span>نوع الحادث</span>
            <b>{shared.type === "lane" ? "حادث تغيير مسار" : "تصادم خلفي"}</b>
          </div>
          {shared.type === "rear" && (
            <div>
              <span>موقع مركبتك</span>
              <b>{positionLabel(otherPosition(shared.partyAPosition))}</b>
            </div>
          )}
          <div>
            <span>مركبة الطرف الأول</span>
            <b>تويوتا كامري ٢٠٢٣ · أ ب ج ٤٨٢١</b>
          </div>
        </div>
        <div className="alert info">
          <Icon name="shield" />
          <span>لا تظهر أي معلومات شخصية عن الطرف الأول في هذه الصفحة.</span>
        </div>
        <Button wide onClick={() => go("party2")}>
          بدء تعبئة البيانات
        </Button>
        <Button variant="secondary" wide onClick={() => go("party2")}>
          تسجيل الدخول بحساب آخر
        </Button>
        <small>
          هذا الرابط مخصص لهذه الحالة فقط ولا يتيح الوصول إلى أي حالة أخرى.
        </small>
      </section>
    </main>
  )
}

function Party2({
  go,
  vehicles,
  shared,
  setShared,
}: {
  go: (s: Screen) => void
  vehicles: Vehicle[]
  shared: SharedCaseInfo
  setShared: React.Dispatch<React.SetStateAction<SharedCaseInfo>>
}) {
  return (
    <AccidentPartyFlow
      go={go}
      vehicles={vehicles}
      role="B"
      shared={shared}
      setShared={setShared}
    />
  )
}

function Processing({ go }: { go: (s: Screen) => void }) {
  // Accident parties see a simple status only — no technical analysis details.
  return (
    <>
      <Header onNavigate={go} />
      <main className="status-page shell">
        <button className="back-link" onClick={() => go("home")}>
          <Icon name="arrow" /> العودة لبلاغاتي
        </button>
        <section className="success-hero">
          <span>
            <Icon name="check" size={32} />
          </span>
          <Badge tone="progress">قيد التحليل</Badge>
          <h1>تم استلام بيانات الطرفين</h1>
          <p>
            حالتك الآن قيد التحليل، ثم يراجعها الخبير المختص. سنُشعرك عند توفر
            النتيجة النهائية المعتمدة.
          </p>
          <div className="case-number">
            <small>رقم الحالة</small>
            <b>SQ-٢٦٠٢١</b>
          </div>
        </section>
        <section className="journey-card">
          <h2>حالة البلاغ</h2>
          <div className="vertical-timeline">
            <div className="done">
              <span>
                <Icon name="check" />
              </span>
              <div>
                <b>تم استلام بيانات الطرفين</b>
                <small>اكتملت بيانات الحالة</small>
              </div>
            </div>
            <div className="active">
              <span>
                <Icon name="clock" />
              </span>
              <div>
                <b>تحليل الفيديو</b>
                <small>جاري الآن</small>
              </div>
            </div>
            <div>
              <span>٣</span>
              <div>
                <b>مراجعة الخبير</b>
                <small>يعتمد الخبير المختص النتيجة النهائية</small>
              </div>
            </div>
            <div>
              <span>٤</span>
              <div>
                <b>النتيجة النهائية</b>
                <small>تظهر هنا بعد اعتمادها</small>
              </div>
            </div>
          </div>
          <div className="status-actions">
            <Button variant="secondary" onClick={() => go("cases")}>
              عرض بلاغاتي
            </Button>
            <Button variant="secondary" onClick={() => go("home")}>
              العودة للرئيسية
            </Button>
          </div>
        </section>
        <div className="demo-bridge">
          <span>مسار العرض التفاعلي</span>
          <p>اكتمل التحليل وأصبحت الحالة جاهزة للخبير.</p>
          <Button onClick={() => go("expert-login")}>
            الانتقال إلى دخول الخبير
          </Button>
        </div>
      </main>
    </>
  )
}

function ExpertLogin({ go }: { go: (s: Screen) => void }) {
  const [identifier, setIdentifier] = useState("EXP-2481")
  const [password, setPassword] = useState("expert123")
  const [error, setError] = useState("")
  return (
    <AuthShell
      title="دخول الخبير المختص"
      subtitle="منطقة مخصصة للمراجعين المصرح لهم."
      go={go}
    >
      <div className="expert-mark">
        <Icon name="shield" />
        <span>وصول مقيد ومراقب</span>
      </div>
      {error && (
        <div className="alert error">
          <Icon name="alert" />
          <span>{error}</span>
        </div>
      )}
      <div className="form-stack">
        <Field
          label="معرّف الخبير"
          value={identifier}
          onChange={setIdentifier}
          dir="ltr"
        />
        <Field
          label="كلمة المرور"
          value={password}
          onChange={setPassword}
          type="password"
        />
        <Button
          wide
          onClick={() =>
            identifier === "EXP-2481" && password.length >= 8
              ? go("expert")
              : setError("تعذر تسجيل الدخول. تحقق من البيانات وحاول مرة أخرى.")
          }
        >
          الدخول لمساحة المراجعة
        </Button>
      </div>
      <div className="auth-switch">
        خبير جديد؟{" "}
        <button onClick={() => go("expert-register")}>تسجيل خبير مصرح</button>
      </div>
    </AuthShell>
  )
}

function ExpertRegister({ go }: { go: (s: Screen) => void }) {
  const [name, setName] = useState("")
  const [identifier, setIdentifier] = useState("")
  const [checked, setChecked] = useState(false)
  const [valid, setValid] = useState(false)
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const verify = () => {
    setChecked(true)
    setValid(identifier === "EXP-2481")
  }
  return (
    <AuthShell
      title="تسجيل خبير مصرح"
      subtitle="يُتاح التسجيل فقط للمراجعين المسجلين في سجلات التفويض."
      go={go}
    >
      <div className="alert info">
        <Icon name="shield" />
        <span>
          تُراجع بيانات التفويض قبل إنشاء الحساب، ولا يتيح هذا النموذج وصولًا عامًا
          لمساحة الخبراء.
        </span>
      </div>
      <div className="form-stack">
        <Field
          label="الاسم الكامل"
          value={name}
          onChange={setName}
          placeholder="الاسم كما يظهر في سجل التفويض"
        />
        <Field
          label="معرّف التفويض"
          value={identifier}
          onChange={(v) => {
            setIdentifier(v)
            setChecked(false)
          }}
          placeholder="EXP-0000"
          dir="ltr"
          error={
            checked && !valid
              ? "لم نتمكن من التحقق من معرّف التفويض."
              : undefined
          }
        />
        {checked && valid && (
          <div className="prefill">
            <Icon name="check" /> تم التحقق من معرّف التفويض
          </div>
        )}
        {!valid && (
          <Button variant="secondary" wide onClick={verify}>
            التحقق من التفويض
          </Button>
        )}
        {valid && (
          <>
            <Field
              label="كلمة المرور"
              value={password}
              onChange={setPassword}
              type="password"
              hint="٨ أحرف على الأقل، وتتضمن حرفًا ورقمًا."
            />
            <Field
              label="تأكيد كلمة المرور"
              value={confirm}
              onChange={setConfirm}
              type="password"
              error={
                confirm && confirm !== password
                  ? "كلمتا المرور غير متطابقتين."
                  : undefined
              }
            />
            {error && (
              <div className="alert error">
                <Icon name="alert" />
                <span>{error}</span>
              </div>
            )}
            <Button
              wide
              onClick={() => {
                if (
                  !name.trim() ||
                  !isStrongPassword(password) ||
                  password !== confirm
                )
                  return setError(
                    "أكمل الاسم واختر كلمة مرور متطابقة من ٨ أحرف على الأقل وتتضمن حرفًا ورقمًا.",
                  )
                go("expert-login")
              }}
            >
              إنشاء حساب الخبير
            </Button>
          </>
        )}
      </div>
      <div className="auth-switch">
        لديك حساب خبير؟{" "}
        <button onClick={() => go("expert-login")}>تسجيل الدخول</button>
      </div>
    </AuthShell>
  )
}

type CaseRow = {
  id: string
  daysAgo: number
  date: string
  status: "جديدة" | "قيد المراجعة" | "مكتملة"
  expert: string
  type: string
}

function Expert({
  go,
  reviewState,
  setReviewState,
}: {
  go: (s: Screen) => void
  reviewState: "new" | "reviewing" | "approved"
  setReviewState: React.Dispatch<React.SetStateAction<"new" | "reviewing" | "approved">>
}) {
  const tabNames = ["جديدة", "قيد المراجعة", "حالاتي", "مكتملة"] as const
  const [tab, setTab] = useState(
    reviewState === "approved" ? 3 : reviewState === "reviewing" ? 2 : 0,
  )
  const current: CaseRow =
    reviewState === "approved"
      ? {
          id: "SQ-٢٦٠٢١",
          daysAgo: 0,
          date: "اليوم",
          status: "مكتملة",
          expert: ME,
          type: "حادث تغيير مسار",
        }
      : reviewState === "reviewing"
        ? {
            id: "SQ-٢٦٠٢١",
            daysAgo: 0,
            date: "اليوم",
            status: "قيد المراجعة",
            expert: ME,
            type: "حادث تغيير مسار",
          }
        : {
            id: "SQ-٢٦٠٢١",
            daysAgo: 0,
            date: "اليوم",
            status: "جديدة",
            expert: "غير معيّن",
            type: "حادث تغيير مسار",
          }
  const rows: CaseRow[] = [
    current,
    {
      id: "SQ-٢٦٠١٨",
      daysAgo: 3,
      date: "١٨ جمادى الأولى",
      status: "قيد المراجعة",
      expert: ME,
      type: "حادث تغيير مسار",
    },
    {
      id: "SQ-٢٦٠١٤",
      daysAgo: 6,
      date: "١٥ جمادى الأولى",
      status: "قيد المراجعة",
      expert: "محمد السالم",
      type: "تصادم خلفي",
    },
    {
      id: "SQ-٢٦٠٠٩",
      daysAgo: 9,
      date: "١٢ جمادى الأولى",
      status: "جديدة",
      expert: "غير معيّن",
      type: "تصادم خلفي",
    },
    {
      id: "SQ-٢٥٩٨٤",
      daysAgo: 17,
      date: "٤ جمادى الأولى",
      status: "مكتملة",
      expert: "محمد السالم",
      type: "تصادم خلفي",
    },
  ]
  const allRows = [...rows].sort((a, b) => a.daysAgo - b.daysAgo) // newest first
  const inTab = (row: CaseRow, i: number) =>
    tabNames[i] === "حالاتي"
      ? row.status === "قيد المراجعة" && row.expert === ME
      : row.status === tabNames[i]
  const visible = allRows.filter((row) => inTab(row, tab))
  const open = (row: CaseRow) => {
    if (row.status === "مكتملة") return go("final")
    if (row.id === "SQ-٢٦٠٢١") setReviewState("reviewing")
    go("review")
  }
  return (
    <>
      <Header onNavigate={go} expert />
      <main className="expert-main shell">
        <section className="expert-welcome">
          <div>
            <span className="eyebrow">مساحة عمل الخبير</span>
            <h1>الحالات</h1>
            <p>راجع الأدلة والتحليل، ثم اعتمد النتيجة النهائية.</p>
          </div>
          <div className="expert-user">
            <span>هـ ع</span>
            <div>
              <b>{ME}</b>
              <small>خبير تقييم معتمد</small>
            </div>
          </div>
        </section>
        <div className="tabs">
          {tabNames.map((x, i) => (
            <button
              className={tab === i ? "active" : ""}
              onClick={() => setTab(i)}
              key={x}
            >
              {x}
              <span>{allRows.filter((row) => inTab(row, i)).length}</span>
            </button>
          ))}
        </div>
        {visible.length ? (
          <div className="expert-list">
            <div className="list-head">
              <span>رقم الحالة</span>
              <span>التاريخ</span>
              <span>الحالة</span>
              <span>الخبير المسؤول</span>
              <span>نوع الحادث</span>
              <span />
            </div>
            {visible.map((row) => {
              const lockedByOther =
                row.status === "قيد المراجعة" && row.expert !== ME
              const cells = [
                row.id,
                row.date,
                row.status,
                row.expert === ME ? `${ME} (أنت)` : row.expert,
                row.type,
              ]
              return (
                <div className="expert-row" key={row.id}>
                  {cells.map((cell, index) => (
                    <span
                      key={index}
                      data-label={
                        ["رقم الحالة", "التاريخ", "الحالة", "الخبير", "النوع"][
                          index
                        ]
                      }
                    >
                      {index === 0 ? <b>{cell}</b> : cell}
                    </span>
                  ))}
                  <span>
                    {lockedByOther ? (
                      <Badge tone="wait">يراجعها خبير آخر</Badge>
                    ) : (
                      <Button variant="secondary" onClick={() => open(row)}>
                        {row.status === "مكتملة"
                          ? "عرض التقرير"
                          : row.status === "جديدة"
                            ? "بدء المراجعة"
                            : "متابعة المراجعة"}
                      </Button>
                    )}
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="empty-state">
            <span>
              <Icon name="file" size={30} />
            </span>
            <h3>
              {tabNames[tab] === "حالاتي"
                ? "لا توجد حالات تحت مراجعتك"
                : "لا توجد حالات في هذا التصنيف"}
            </h3>
            <p>
              {tabNames[tab] === "حالاتي"
                ? "ابدأ مراجعة حالة من تبويب «جديدة»."
                : "اختر تصنيفًا آخر."}
            </p>
          </div>
        )}
      </main>
    </>
  )
}

function ReasonCard({
  n,
  icon,
  title,
  text,
  tag,
}: {
  n: string
  icon: IconName
  title: string
  text: string
  tag: string
}) {
  return (
    <div className="reason-card">
      <span className="reason-n">{n}</span>
      <span className="reason-icon">
        <Icon name={icon} />
      </span>
      <div>
        <small>{tag}</small>
        <h4>{title}</h4>
        <p>{text}</p>
      </div>
    </div>
  )
}

function Review({
  go,
  setReviewState,
  shared,
}: {
  go: (s: Screen) => void
  setReviewState: React.Dispatch<React.SetStateAction<"new" | "reviewing" | "approved">>
  shared: SharedCaseInfo
}) {
  const [modal, setModal] = useState<"approve" | "modify" | "evidence" | null>(
    null,
  )
  const [fault, setFault] = useState(75)
  const [approved, setApproved] = useState(false)
  const [evidenceIndex, setEvidenceIndex] = useState(0)
  const [toast, setToast] = useState("")
  const evidence = [
    {
      time: "٠٠:١٤",
      title: "بداية الحركة الجانبية",
      text: "يُظهر الإطار بداية تحرك المركبة الثانية باتجاه المسار الأوسط.",
    },
    {
      time: "٠٠:١٦",
      title: "عبور حد المسار",
      text: "يوضح الإطار عبور المركبة الثانية حد المسار قبل الاصطدام.",
    },
    {
      time: "٠٠:١٨",
      title: "لحظة الاصطدام",
      text: "يوضح الإطار موضع المركبتين عند وقوع الاصطدام.",
    },
  ]
  const openEvidence = (index: number) => {
    setEvidenceIndex(index)
    setModal("evidence")
  }
  if (approved)
    return (
      <main className="approval-success">
        <Brand compact onClick={() => go("expert")} />
        <div className="success-panel">
          <span>
            <Icon name="check" size={32} />
          </span>
          <h1>تم اعتماد التقرير بنجاح</h1>
          <p>
            أصبحت النتيجة النهائية متاحة لطرفي الحادث، وتم نقل الحالة إلى
            «مكتمل».
          </p>
          <div className="case-number">
            <small>رقم الحالة</small>
            <b>SQ-٢٦٠٢١</b>
          </div>
          <Button onClick={() => go("final")}>معاينة نتيجة طرف الحادث</Button>
          <Button variant="secondary" onClick={() => go("expert")}>
            العودة إلى الحالات
          </Button>
        </div>
      </main>
    )
  return (
    <>
      <Header onNavigate={go} expert />
      <main className="review-page shell">
        <button className="back-link" onClick={() => go("expert")}>
          <Icon name="arrow" /> العودة للحالات
        </button>
        <section className="review-header">
          <div>
            <Badge tone="progress">جاهزة للمراجعة</Badge>
            <h1>الحالة SQ-٢٦٠٢١</h1>
            <p>
              {shared.type === "lane" ? "حادث تغيير مسار" : "تصادم خلفي"} ·{" "}
              {formatCaseDate(shared.date)}، {shared.time}
            </p>
          </div>
          <div className="review-actions">
            <Button
              variant="secondary"
              icon="edit"
              onClick={() => setModal("modify")}
            >
              تعديل النتيجة
            </Button>
            <Button icon="check" onClick={() => setModal("approve")}>
              اعتماد النتيجة
            </Button>
          </div>
        </section>
        <div className="review-layout">
          <aside className="review-nav">
            <b>محتويات المراجعة</b>
            {[
              "ملخص الحالة",
              "الأطراف والمركبات",
              "أوصاف الحادث",
              "الفيديو والأدلة",
              "الأحداث والمخالفات",
              "منطق سياق",
              "قرار الخبير",
            ].map((x, i) => (
              <a
                href={`#review-${i}`}
                key={x}
                className={i === 0 ? "active" : ""}
              >
                <span>{i + 1}</span>
                {x}
              </a>
            ))}
          </aside>
          <div className="review-content">
            <section className="report-section" id="review-0">
              <div className="report-title">
                <span>
                  <Icon name="file" />
                </span>
                <div>
                  <h2>ملخص الحالة</h2>
                  <p>البيانات الأساسية التي قدّمها الطرفان</p>
                </div>
              </div>
              <div className="summary-grid">
                <div>
                  <span>نوع الحادث</span>
                  <b>
                    {shared.type === "lane" ? "حادث تغيير مسار" : "تصادم خلفي"}
                  </b>
                </div>
                <div>
                  <span>تاريخ الحادث</span>
                  <b>{formatCaseDate(shared.date)}</b>
                </div>
                <div>
                  <span>وقت الحادث</span>
                  <b>{shared.time}</b>
                </div>
                <div>
                  <span>موقع الحادث</span>
                  <b>{shared.location}</b>
                </div>
                {shared.type === "rear" && (
                  <div>
                    <span>موقع المركبتين</span>
                    <b>
                      الطرف الأول: {positionLabel(shared.partyAPosition)} ·
                      الطرف الثاني:{" "}
                      {positionLabel(otherPosition(shared.partyAPosition))}
                    </b>
                  </div>
                )}
                <div>
                  <span>التسجيلات المتاحة</span>
                  <b>
                    {shared.type === "rear"
                      ? `الطرف الأول (${requiredCamera(shared.partyAPosition)}) فقط`
                      : "تسجيل الطرف الأول فقط"}
                  </b>
                </div>
                <div>
                  <span>وقت التحليل</span>
                  <b>٦ دقائق و١٢ ثانية</b>
                </div>
              </div>
            </section>
            <section className="report-section" id="review-1">
              <div className="report-title">
                <span>
                  <Icon name="user" />
                </span>
                <div>
                  <h2>الأطراف والمركبات</h2>
                  <p>بيانات مصرح للخبير بمراجعتها</p>
                </div>
              </div>
              <div className="party-grid">
                <div className="party-card">
                  <Badge tone="info">الطرف الأول</Badge>
                  <h3>نورة محمد العتيبي</h3>
                  <p>هوية: ١٠٢٣٤٥٦٧٨٩ · جوال: 055 321 8421</p>
                  <hr />
                  <b>تويوتا كامري ٢٠٢٣</b>
                  <span>أ ب ج ٤٨٢١ · أبيض</span>
                </div>
                <div className="party-card">
                  <Badge tone="wait">الطرف الثاني</Badge>
                  <h3>سلمان عبدالله القحطاني</h3>
                  <p>هوية: ١٠٧٦٣٢١٩٤٢ · جوال: 055 784 3621</p>
                  <hr />
                  <b>هيونداي سوناتا ٢٠٢٢</b>
                  <span>ر س د ٧١٢٩ · رمادي</span>
                </div>
              </div>
            </section>
            <section className="report-section" id="review-2">
              <div className="report-title">
                <span>
                  <Icon name="file" />
                </span>
                <div>
                  <h2>أوصاف الحادث</h2>
                  <p>يعرض كل وصف كما أدخله صاحبه، بشكل منفصل</p>
                </div>
              </div>
              <div className="description-grid">
                <blockquote>
                  <b>وصف الطرف الأول</b>
                  <p>
                    كنت أسير في المسار الأوسط، ثم انتقلت المركبة الأخرى من
                    المسار الأيسر أمامي قبل وقوع الاصطدام.
                  </p>
                </blockquote>
                <blockquote>
                  <b>وصف الطرف الثاني</b>
                  <p>
                    كنت أسير في المسار الأيسر، وعند الانتقال للمسار الأوسط حدث
                    الاصطدام مع المركبة الأخرى.
                  </p>
                </blockquote>
              </div>
            </section>
            <section className="report-section evidence-section" id="review-3">
              <div className="report-title">
                <span>
                  <Icon name="video" />
                </span>
                <div>
                  <h2>الفيديو والأدلة</h2>
                  <p>تم تحليل كل تسجيل متاح بشكل مستقل</p>
                </div>
              </div>
              <div className="video-card">
                <div className="video-preview">
                  <div className="road-lines" />
                  <button onClick={() => openEvidence(2)}>
                    <Icon name="eye" size={28} />
                  </button>
                  <span>٠٠:١٨ / ٠١:٤٢</span>
                </div>
                <div className="video-meta">
                  <Badge tone="info">فيديو الطرف الأول</Badge>
                  <b>CAM_2026-11-03_1032.MOV</b>
                  <small>تم التحقق · ١٢٨ ميجابايت</small>
                </div>
              </div>
              <h3 className="subhead">الإطارات الداعمة</h3>
              <div className="frames">
                {evidence.map((item, i) => (
                  <button onClick={() => openEvidence(i)} key={item.time}>
                    <div className={`frame-art f${i}`}>
                      <span>{item.time}</span>
                    </div>
                    <b>{item.title}</b>
                    <small>إطار من فيديو الطرف الأول</small>
                  </button>
                ))}
              </div>
            </section>
            <section className="report-section" id="review-4">
              <div className="report-title">
                <span>
                  <Icon name="eye" />
                </span>
                <div>
                  <h2>الأحداث والمخالفات المرصودة</h2>
                  <p>كل حدث مرتبط بإطاره الداعم</p>
                </div>
              </div>
              <div className="event-list">
                <div>
                  <span>
                    <Icon name="arrow" />
                  </span>
                  <div>
                    <b>حركة جانبية للمركبة الثانية</b>
                    <p>
                      بدأت المركبة بالتحرك نحو المسار الأوسط قبل الاصطدام بـ ٤
                      ثوانٍ.
                    </p>
                  </div>
                  <button onClick={() => openEvidence(0)}>
                    عرض الدليل ٠٠:١٤
                  </button>
                </div>
                <div>
                  <span>
                    <Icon name="car" />
                  </span>
                  <div>
                    <b>عبور حد المسار</b>
                    <p>
                      عبرت المركبة الثانية حد المسار أثناء وجود المركبة الأولى
                      في المسار المستهدف.
                    </p>
                  </div>
                  <button onClick={() => openEvidence(1)}>
                    عرض الدليل ٠٠:١٦
                  </button>
                </div>
              </div>
              <div className="violation">
                <Icon name="alert" />
                <div>
                  <b>تغيير المسار دون التأكد من خلوه</b>
                  <p>
                    مرصودة وفق الأدلة المتاحة ومرتبطة بقاعدة أولوية المركبة في
                    المسار.
                  </p>
                </div>
              </div>
            </section>
            <section className="report-section reasoning" id="review-5">
              <div className="report-title">
                <span>
                  <Icon name="spark" />
                </span>
                <div>
                  <h2>كيف توصل سياق إلى النتيجة المقترحة؟</h2>
                  <p>مسار قابل للتتبع من الدليل إلى النسبة</p>
                </div>
              </div>
              <div className="reason-flow">
                <ReasonCard
                  n="١"
                  icon="eye"
                  tag="الدليل المرصود"
                  title="عبور حد المسار"
                  text="ظهر في الإطار ٠٠:١٦ من تسجيل الطرف الأول."
                />
                <Icon name="chevron" />
                <ReasonCard
                  n="٢"
                  icon="car"
                  tag="الحدث المرتبط"
                  title="تغيير مسار قبل الاصطدام"
                  text="الحركة الجانبية سبقت الاصطدام بثانيتين."
                />
                <Icon name="chevron" />
                <ReasonCard
                  n="٣"
                  icon="file"
                  tag="القاعدة المطبقة: L2"
                  title="أولوية المركبة في المسار"
                  text="يجب التأكد من إمكانية الانتقال دون تعريض الآخرين للخطر."
                />
                <Icon name="chevron" />
                <ReasonCard
                  n="٤"
                  icon="spark"
                  tag="الناتج"
                  title="المسؤولية الأكبر للطرف الثاني"
                  text="تطابق الأدلة قاعدة تغيير المسار L2."
                />
              </div>
              <div className="decision-actions">
                <Button
                  variant="secondary"
                  icon="file"
                  onClick={() => go("rules")}
                >
                  عرض تفاصيل القاعدة
                </Button>
              </div>
            </section>
            <section className="report-section decision" id="review-6">
              <div className="decision-label">
                <span>
                  <Icon name="spark" />
                </span>
                <div>
                  <small>النسبة المقترحة من سياق</small>
                  <h2>اقتراح لدعم قرارك، وليس قرارًا نهائيًا</h2>
                </div>
              </div>
              <div className="fault-cards">
                <div>
                  <span>الطرف الأول</span>
                  <strong>{100 - fault}٪</strong>
                  <small>نورة · كامري</small>
                </div>
                <div className="fault-bar">
                  <i style={{ width: `${100 - fault}%` }} />
                  <i />
                </div>
                <div>
                  <span>الطرف الثاني</span>
                  <strong>{fault}٪</strong>
                  <small>سلمان · سوناتا</small>
                </div>
              </div>
              <div className="alert info">
                <Icon name="shield" />
                <span>
                  النتيجة المقترحة تهدف إلى دعم قرار الخبير، ولا تصبح نهائية إلا
                  بعد اعتمادها.
                </span>
              </div>
              <div className="decision-actions">
                <Button
                  variant="secondary"
                  icon="edit"
                  onClick={() => setModal("modify")}
                >
                  تعديل النتيجة
                </Button>
                <Button icon="check" onClick={() => setModal("approve")}>
                  اعتماد النتيجة
                </Button>
              </div>
            </section>
          </div>
        </div>
      </main>
      {modal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div
            className={`modal ${modal === "evidence" ? "evidence-modal" : ""}`}
          >
            <button
              className="modal-close icon-btn"
              onClick={() => setModal(null)}
              aria-label="إغلاق"
            >
              <Icon name="close" />
            </button>
            {modal === "approve" && (
              <>
                <span className="modal-icon success">
                  <Icon name="check" />
                </span>
                <h2>اعتماد النتيجة النهائية؟</h2>
                <p>
                  بعد الاعتماد ستصبح النتيجة متاحة لطرفي الحادث، ويمكنهما تحميل
                  التقرير النهائي.
                </p>
                <div className="modal-summary">
                  <span>
                    الطرف الأول <b>{100 - fault}٪</b>
                  </span>
                  <span>
                    الطرف الثاني <b>{fault}٪</b>
                  </span>
                </div>
                <div className="modal-actions">
                  <Button variant="secondary" onClick={() => setModal(null)}>
                    العودة للمراجعة
                  </Button>
                  <Button
                    onClick={() => {
                      setReviewState("approved")
                      setApproved(true)
                    }}
                  >
                    تأكيد الاعتماد
                  </Button>
                </div>
              </>
            )}
            {modal === "modify" && (
              <>
                <span className="modal-icon">
                  <Icon name="edit" />
                </span>
                <h2>تعديل نتيجة الخبير</h2>
                <p>اختر توزيعًا واحدًا متكاملًا لنسبة الخطأ بين الطرفين.</p>
                <div className="original">
                  اقتراح سياق: الطرف الأول ٢٥٪ — الطرف الثاني ٧٥٪
                </div>
                <div className="form-stack">
                  {[100, 75, 50, 25, 0].map((partyTwo) => (
                    <button
                      className={`choice-card${
                        fault === partyTwo ? " selected" : ""
                      }`}
                      onClick={() => setFault(partyTwo)}
                      key={partyTwo}
                    >
                      <span>
                        <Icon name={fault === partyTwo ? "check" : "file"} />
                      </span>
                      <div>
                        <h3>
                          الطرف الأول {100 - partyTwo}٪ — الطرف الثاني{" "}
                          {partyTwo}٪
                        </h3>
                        <p>توزيع متكامل بإجمالي ١٠٠٪</p>
                      </div>
                    </button>
                  ))}
                </div>
                <label className="field">
                  <span>وصف الحادث النهائي</span>
                  <textarea
                    rows={4}
                    defaultValue="غيّرت المركبة الثانية مسارها إلى المسار الأوسط دون التأكد من خلوه، مما أدى إلى الاصطدام."
                  />
                </label>
                <div className="modal-actions">
                  <Button variant="secondary" onClick={() => setModal(null)}>
                    إلغاء
                  </Button>
                  <Button
                    onClick={() => {
                      setModal(null)
                      setToast("تم حفظ تعديلات الخبير.")
                    }}
                  >
                    حفظ التعديلات
                  </Button>
                </div>
              </>
            )}
            {modal === "evidence" && (
              <>
                <div className="large-frame">
                  <div className="road-lines" />
                  <span>{evidence[evidenceIndex].time}</span>
                  <i className="car-box one">المركبة ١</i>
                  <i className="car-box two">المركبة ٢</i>
                </div>
                <h2>{evidence[evidenceIndex].title}</h2>
                <p>{evidence[evidenceIndex].text}</p>
                <div className="modal-actions">
                  <Button variant="secondary" onClick={() => setModal(null)}>
                    إغلاق
                  </Button>
                  <Button
                    icon="arrow"
                    onClick={() =>
                      setEvidenceIndex((evidenceIndex + 1) % evidence.length)
                    }
                  >
                    الإطار التالي
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {toast && (
        <div className="toast">
          <Icon name="check" />
          <span>{toast}</span>
          <button onClick={() => setToast("")}>
            <Icon name="close" />
          </button>
        </div>
      )}
    </>
  )
}

type SiyaqRule = {
  code: string
  title: string
  evidence: string
  provision: string
  ratio: string
  note?: string
}

const REAR_RULES: SiyaqRule[] = [
  {
    code: "R1",
    title:
      "المركبة الخلفية تصدم مركبة أمامية تسير أو تتوقف بشكل طبيعي في المسار نفسه",
    evidence:
      "المركبتان في المسار نفسه قبل الاصطدام؛ لا تغيير مسار ولا توقف مفاجئ من المركبة الأمامية؛ تقلّص المسافة حتى لحظة الاصطدام.",
    provision:
      "الخلفية: 19/2/50 (مسافة أمان تزداد مع السرعة)، 1/9/50 (سرعة تسمح بالتوقف عند الطوارئ)، 3/9/50 (تخفيف السرعة في الازدحام)؛ الجدول 2، البند 11. للمركبة الأمامية الأولوية بصفتها المتقدمة (1/1/1/6/50).",
    ratio: "الخلفية 100% — الأمامية 0%",
  },
  {
    code: "R2",
    title:
      "المركبة الأمامية تتوقف فجأة دون سبب مروري بينما المركبة الخلفية قريبة جدًا",
    evidence:
      "تباطؤ حاد للمركبة الأمامية؛ لا سبب ظاهر أمامها (عائق أو طابور أو إشارة)؛ مسافة قصيرة قبل التوقف. الفرملة المفاجئة مسموحة فقط للضرورة أو السلامة (5/2/50).",
    provision:
      "الأمامية: 5/2/50 و1/1/1/6/50 (عدم التوقف المفاجئ)؛ الجدول 3، البند 5. الخلفية: 19/2/50 و1/2/50 (قواعد المرور لا تعفي السائق من واجب الحيطة).",
    ratio: "الخلفية 75% — الأمامية 25%",
  },
  {
    code: "R3",
    title: "المركبة الأمامية دخلت مسار المركبة الخلفية قبل الاصطدام بوقت قصير",
    evidence: "عبور المركبة الأمامية خط المسار خلال وقت قصير قبل الاصطدام.",
    provision:
      "تُحال الحالة إلى قواعد تغيير المسار؛ على المركبة الداخلة ألا تغيّر اتجاهها فجأة (1/1/1/6/50).",
    ratio: "حسب القاعدة المطابقة من L1 إلى L3",
    note: "تُفحص هذه القاعدة أولًا قبل بقية القواعد.",
  },
]

const LANE_RULES: SiyaqRule[] = [
  {
    code: "L1",
    title: "مركبة تغيّر مسارها إلى مسار تسير فيه مركبة أخرى بشكل مستقيم",
    evidence:
      "عبور خط المسار؛ وجود المركبة الأخرى بجانبها أو خلفها في المسار المستهدف وهي تسير مستقيمًا.",
    provision:
      "المركبة المغيّرة: 2/1/1/6/50 (الأولوية للمركبة السائرة مستقيمًا)، 13/2/50 و1/24/2/50 (التأكد من أمان التغيير)؛ الجدول 4، البند 15.",
    ratio: "المغيّرة 100% — الأخرى 0%",
  },
  {
    code: "L2",
    title: "مثل L1 دون استخدام إشارة الانعطاف",
    evidence: "مثل L1؛ وإشارة الانعطاف غير مفعّلة.",
    provision:
      "إضافةً إلى L1: 1/7/50 و2/24/2/50 (إعطاء الإشارة في وقت كافٍ)؛ الجدول 2، البند 1.",
    ratio: "المغيّرة 100% — الأخرى 0%",
    note: "تُفحص الإشارة خلال فترة قبل عبور الخط. إذا تعذّر رصد حالة الإشارة تُطبَّق L1.",
  },
  {
    code: "L3",
    title: "مثل L1 مع عبور خط مسار متصل",
    evidence: "مثل L1؛ والخط المعبور متصل.",
    provision:
      "إضافةً إلى L1: 9/7/6/2/6/50 (عدم السير على الخطوط الطولية المتصلة أو عبورها)؛ الجدول 3، البند 7 (عدم التقيد بالمسارات المحددة).",
    ratio: "المغيّرة 100% — الأخرى 0%",
  },
  {
    code: "L4",
    title:
      "مركبة تدخل الطريق الرئيسي من طريق الخدمة أو تخرج إليه فتصطدم بمركبة تسير مستقيمًا",
    evidence:
      "الدخول من طريق الخدمة أو الخروج إليه؛ المركبة الأخرى تسير مستقيمًا.",
    provision:
      "3/1/1/6/50 (الأولوية للمركبة السائرة مستقيمًا)؛ لا يوجد بند مخصص في جداول المخالفات.",
    ratio: "الداخلة/الخارجة 100% — الأخرى 0%",
  },
  {
    code: "L5",
    title:
      "المركبة المتجاوَزة تزيد سرعتها أثناء عودة المركبة المتجاوِزة إلى المسار",
    evidence:
      "L5a: أكملت المتجاوِزة التجاوز (مؤخرتها أمام مقدمة الأخرى) عند بدء العودة، ثم زادت المتجاوَزة سرعتها. L5b: عادت المتجاوِزة قبل إكمال التجاوز.",
    provision:
      "المتجاوَزة: 4/2/6/50 (يجب ألا تزيد سرعتها). المتجاوِزة: 5/6/2/6/50 (ترك مسافة جانبية كافية)؛ لا يوجد بند مخصص.",
    ratio:
      "L5a: المتجاوِزة 25% — المتجاوَزة 75% · L5b: المتجاوِزة 75% — المتجاوَزة 25%",
    note: "إذا لم تزد المتجاوَزة سرعتها تُطبَّق L1، وإذا تعذّر تحديد ترتيب الأحداث تكون النتيجة غير محددة (U10).",
  },
  {
    code: "L6",
    title: "مركبتان تنتقلان إلى المسار نفسه في الوقت نفسه",
    evidence: "عبور المركبتين نحو مسار واحد.",
    provision: "كلتا المركبتين: 13/2/50.",
    ratio: "50% — 50%",
  },
]

const UNDETERMINED: [string, string, string, string][] = [
  [
    "U1",
    "خارج النطاق",
    "نوع حادث غير التصادم الخلفي وتغيير المسار (مثل التقاطعات، التصادم الأمامي، حادث مركبة واحدة، ثلاث مركبات فأكثر)",
    "لا توجد قواعد لهذه الأنواع",
  ],
  [
    "U2",
    "خارج النطاق",
    "مسجّل ليلًا أو في طقس سيئ (مطر، ضباب، عاصفة رملية)",
    "خارج النطاق وظروف بيانات التدريب",
  ],
  [
    "U3",
    "خارج النطاق",
    "أي إصابة أو أضرار مادية جسيمة",
    "يغطي سياق الحوادث دون إصابات وبأضرار مادية فقط (2/59، 3/59، 3/3/59)",
  ],
  [
    "U4",
    "الأدلة المرئية",
    "أحداث ما قبل الاصطدام غير موجودة في المقطع",
    "لا يمكن الحكم على تغيير المسار أو الإشارة أو المسافة، فلا تثبت العلاقة السببية (1/60)",
  ],
  [
    "U5",
    "الأدلة المرئية",
    "الاصطدام غير ظاهر (خارج الإطار أو محجوب)",
    "نقطة الاصطدام والمركبات المعنية غير معروفة",
  ],
  [
    "U6",
    "الأدلة المرئية",
    "دقة منخفضة، ضبابية شديدة، إطارات مفقودة أو وهج قوي",
    "لا يمكن الاعتماد على الإطارات كدليل",
  ],
  [
    "U7",
    "الأدلة المرئية",
    "فقدان تتبّع مركبة أو رصدها بثقة منخفضة",
    "مسار المركبة قبل الاصطدام غير مكتمل",
  ],
  [
    "U8",
    "الأدلة المرئية",
    "خطوط المسارات غير ظاهرة",
    "لا يمكن التمييز بين تغيير المسار والحركة داخل المسار؛ قيد تقني في سياق، إذ يعرّف النظام المسار حتى لو لم يكن مخططًا (المادة 2)",
  ],
  [
    "U9",
    "الأدلة المرئية",
    "الفيديوهان المرسلان يقدمان أدلة متعارضة",
    "لا يمكن وضع أحداث الفيديوين في رواية واحدة متسقة، ويُعرض التعارض على الخبير",
  ],
  [
    "U10",
    "لا توجد قاعدة حاسمة",
    "لا توجد قاعدة تطابق الأدلة، أو القاعدة المطابقة بلا نسبة محددة (مثل L5 عند تعذّر تحديد ترتيب الأحداث)",
    "لا توجد قاعدة تعطي اقتراحًا",
  ],
  [
    "U11",
    "لا توجد قاعدة حاسمة",
    "تطابق قاعدتين أو أكثر بنسب مختلفة",
    "لا توجد إجابة واحدة في القواعد",
  ],
  [
    "U12",
    "حالة نظامية خاصة",
    "يبدو الاصطدام متعمدًا",
    "الحادث المتعمد لا يُعد حادثًا مروريًا (1/59) وتحقق فيه الشرطة",
  ],
  [
    "U13",
    "حالة نظامية خاصة",
    "يبدو الحادث مفتعلًا",
    "افتعال الحادث المروري مخالفة (المادة 63، الفقرة 2/ب)",
  ],
  [
    "U14",
    "حالة نظامية خاصة",
    "الحادث بسبب قوة قاهرة خارجة عن إرادة السائق",
    "يُعفى السائق من الحق العام (4/60)",
  ],
  [
    "U15",
    "حالة نظامية خاصة",
    "حيوان طرف في الحادث",
    "يتحمل مالكه أو حائزه المسؤولية إذا ثبت ذلك (5/60)",
  ],
]

const APPLY_STEPS: [string, string][] = [
  [
    "التحقق من النطاق",
    "تُفحص الحالة مقابل U1 إلى U3، وإذا انطبق أي منها تكون النتيجة غير محددة.",
  ],
  [
    "استخراج الأدلة",
    "يُحلَّل كل فيديو مرسل بشكل مستقل: فيديو الطرف الأول الإلزامي وفيديو الطرف الثاني الاختياري.",
  ],
  [
    "فحص الأدلة",
    "إذا أظهرت أحداث الفيديو إحدى الحالات U4 إلى U8 فلا يمكن الاعتماد عليه لتقديم اقتراح.",
  ],
  [
    "جمع الفيديوهات",
    "توضع أحداث الفيديوهات المتاحة في سجل حالة واحد دون دمج الفيديوهات. إذا تعارضت الأدلة تكون النتيجة غير محددة (U9) ويُعرض التعارض على الخبير.",
  ],
  [
    "مطابقة القواعد",
    "تُفحص R3 أولًا، ثم تُقارن شروط كل قاعدة بالأحداث. إذا طابقت قاعدة واحدة لها نسبة فهي الاقتراح؛ وإذا لم تطابق أي قاعدة أو طابقت قواعد بنسب مختلفة تكون النتيجة غير محددة (U10، U11).",
  ],
  [
    "عرض النتيجة على الخبير",
    "تُحفظ النتيجة (النسبة المقترحة مع القاعدة والمادة والتعليل، أو النتيجة غير المحددة مع رمز السبب) وتُعرض على الخبير المعتمد ليراجعها ويعدّلها عند الحاجة ثم يعتمد النتيجة النهائية.",
  ],
]

function RuleCard({ rule }: { rule: SiyaqRule }) {
  return (
    <section className="report-section" id={`rule-${rule.code}`}>
      <div className="report-title">
        <span>
          <b>{rule.code}</b>
        </span>
        <div>
          <h2>{rule.title}</h2>
        </div>
      </div>
      <div className="summary-grid">
        <div>
          <span>الأدلة المطلوبة</span>
          <b>{rule.evidence}</b>
        </div>
        <div>
          <span>المخالفة النظامية</span>
          <b>{rule.provision}</b>
        </div>
        <div>
          <span>النسبة المقترحة</span>
          <b>{rule.ratio}</b>
        </div>
        <div>
          <span>ملاحظة</span>
          <b>{rule.note || "—"}</b>
        </div>
      </div>
    </section>
  )
}

function RulesReference({
  go,
  from,
}: {
  go: (s: Screen) => void
  from: Screen
}) {
  const back: Screen = from === "review" ? "review" : "expert"
  const tabNames = [
    "التصادم الخلفي",
    "تغيير المسار",
    "حالات عدم التحديد",
    "مبدأ النسب وآلية التطبيق",
  ]
  const [tab, setTab] = useState(0)
  const groups = [
    "خارج النطاق",
    "الأدلة المرئية",
    "لا توجد قاعدة حاسمة",
    "حالة نظامية خاصة",
  ]
  return (
    <>
      <Header onNavigate={go} expert />
      <main className="profile-page shell">
        <button className="back-link" onClick={() => go(back)}>
          <Icon name="arrow" />{" "}
          {back === "review" ? "العودة لمراجعة الحالة" : "العودة للحالات"}
        </button>
        <section className="profile-card">
          <div className="report-title">
            <span>
              <Icon name="file" />
            </span>
            <div>
              <h1>قواعد سياق</h1>
              <p>
                القواعد المحددة مسبقًا من نظام المرور ولائحته التنفيذية، والنسب
                المقترحة لكل قاعدة
              </p>
            </div>
          </div>
          <div className="alert info">
            <Icon name="shield" />
            <span>
              النسب المقترحة قرار تصميمي في سياق وليست نسبًا منصوصًا عليها في
              اللائحة، وتبقى خاضعة لمراجعة الخبير المعتمد واعتماده.
            </span>
          </div>
          <div className="tabs">
            {tabNames.map((x, i) => (
              <button
                key={x}
                className={tab === i ? "active" : ""}
                onClick={() => setTab(i)}
              >
                {x}
                <span>
                  {i === 0
                    ? REAR_RULES.length
                    : i === 1
                      ? LANE_RULES.length
                      : i === 2
                        ? UNDETERMINED.length
                        : APPLY_STEPS.length}
                </span>
              </button>
            ))}
          </div>

          {tab === 0 && (
            <div className="form-stack">
              <p className="muted">
                النسبة تُقرأ: المركبة الخلفية — المركبة الأمامية.
              </p>
              {REAR_RULES.map((r) => (
                <RuleCard rule={r} key={r.code} />
              ))}
            </div>
          )}

          {tab === 1 && (
            <div className="form-stack">
              <p className="muted">
                النسبة تُقرأ: المركبة المغيّرة لمسارها — المركبة الأخرى. القاعدتان
                L2 وL3 تضيفان مخالفة إلى L1 دون تغيير النسبة، لأن المركبة
                المغيّرة في L1 هي الطرف الوحيد المخالف. جهة تغيير المسار ليست
                مخالفة بحد ذاتها، إذ يُسمح بالتجاوز من اليمين في الطرق ذات أكثر
                من مسارين في الاتجاه الواحد (5/2/6/50).
              </p>
              {LANE_RULES.map((r) => (
                <RuleCard rule={r} key={r.code} />
              ))}
            </div>
          )}

          {tab === 2 && (
            <div className="form-stack">
              <p className="muted">
                عند انطباق أي حالة مما يلي لا يقترح سياق نسبة خطأ، ويعيد نتيجة
                غير محددة مع رمز السبب والأدلة المتاحة، ويُكمل الخبير المعتمد
                التقييم دون نسبة مقترحة. النتيجة غير المحددة ليست حكمًا نظاميًا
                (6/60).
              </p>
              {groups.map((g) => (
                <section className="report-section" key={g}>
                  <div className="report-title">
                    <span>
                      <Icon name="alert" />
                    </span>
                    <div>
                      <h2>{g}</h2>
                    </div>
                  </div>
                  <div className="review-grid">
                    {UNDETERMINED.filter((u) => u[1] === g).map(
                      ([code, , situation, why]) => (
                        <div className="review-item" key={code}>
                          <div>
                            <span>{code}</span>
                            <h3>{situation}</h3>
                            <p>{why}</p>
                          </div>
                        </div>
                      ),
                    )}
                  </div>
                </section>
              ))}
            </div>
          )}

          {tab === 3 && (
            <div className="form-stack">
              <section className="report-section">
                <div className="report-title">
                  <span>
                    <Icon name="spark" />
                  </span>
                  <div>
                    <h2>مبدأ تحديد النسب</h2>
                    <p>
                      يُطبَّق مرة واحدة عند كتابة كل قاعدة، فلكل قاعدة نسبة ثابتة
                    </p>
                  </div>
                </div>
                <div className="review-grid">
                  <div className="review-item">
                    <div>
                      <span>طرف واحد مخالف</span>
                      <h3>100% — 0%</h3>
                      <p>إذا ارتكب طرف واحد فقط مخالفة سببت الاصطدام.</p>
                    </div>
                  </div>
                  <div className="review-item">
                    <div>
                      <span>مخالفتان وإحداهما السبب الرئيسي</span>
                      <h3>75% — 25%</h3>
                      <p>
                        إذا خالف الطرفان وكانت إحدى المخالفتين هي السبب الرئيسي.
                      </p>
                    </div>
                  </div>
                  <div className="review-item">
                    <div>
                      <span>مخالفتان متساويتان</span>
                      <h3>50% — 50%</h3>
                      <p>إذا خالف الطرفان وأسهمت المخالفتان بالتساوي.</p>
                    </div>
                  </div>
                </div>
                <p className="report-copy">
                  تحدد اللائحة أربع نسب: 100% و75% و50% و25% (2/60)، وتنشأ
                  المسؤولية عند وجود علاقة سببية مباشرة أو غير مباشرة بين الفعل
                  والحادث (1/60). ويستخدم سياق 0% للطرف الذي لا يُنسب إليه خطأ.
                  لأن كل قاعدة مرتبطة بمادة مكتوبة، فأساس المسؤولية المسجّل هو
                  عدم الالتزام بالأنظمة (3/2/60).
                </p>
                <p className="report-copy">
                  قراءة أرقام المواد من اليمين إلى اليسار: الرقم الأخير هو
                  المادة، وكل رقم قبله بند ضمن ما يليه. مثال: 2/1/1/6/50 هو
                  البند 2 من اللائحة 1/1/6/50. و«الجدول» يعني جداول المخالفات
                  والغرامات المرفقة بالنظام.
                </p>
              </section>
              <section className="report-section">
                <div className="report-title">
                  <span>
                    <Icon name="check" />
                  </span>
                  <div>
                    <h2>آلية تطبيق القواعد على الحالة</h2>
                  </div>
                </div>
                <div className="vertical-timeline">
                  {APPLY_STEPS.map(([t, d], i) => (
                    <div key={t}>
                      <span>{["١", "٢", "٣", "٤", "٥", "٦"][i]}</span>
                      <div>
                        <b>{t}</b>
                        <small>{d}</small>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}

          <div
            style={{
              marginTop: 28,
              paddingTop: 20,
              borderTop: "1px solid var(--line)",
            }}
          >
            <Button onClick={() => go(back)}>
              {back === "review" ? "العودة إلى الحالة" : "العودة إلى الحالات"}
            </Button>
          </div>
        </section>
      </main>
    </>
  )
}

function Final({
  go,
  shared,
}: {
  go: (s: Screen) => void
  shared: SharedCaseInfo
}) {
  const [downloaded, setDownloaded] = useState(false)
  const printReport = () => {
    setDownloaded(true)
    window.setTimeout(() => window.print(), 120)
  }
  return (
    <>
      <style media="print">{`
    body::before, .header, .back-link, .final-hero .btn, .toast { display: none !important; }
    body, .final-page { background: white !important; }
    .final-page { width: 100% !important; padding: 0 !important; }
    .final-hero { color: #111 !important; background: white !important; border: 2px solid #006c35 !important; }
    .final-layout { display: block !important; }
    .official-card { position: static !important; margin-top: 16px; page-break-inside: avoid; }
    .report-section { box-shadow: none !important; page-break-inside: avoid; }
  `}</style>
      <Header onNavigate={go} />
      <main className="final-page shell">
        <button className="back-link" onClick={() => go("cases")}>
          <Icon name="arrow" /> العودة لبلاغاتي
        </button>
        <section className="final-hero">
          <div className="seal">
            <Icon name="shield" size={32} />
          </div>
          <Badge tone="done">مكتمل</Badge>
          <h1>النتيجة النهائية المعتمدة</h1>
          <p>
            <Icon name="check" /> تمت مراجعة واعتماد النتيجة من الخبير المختص
          </p>
          <div className="final-case">
            الحالة SQ-٢٦٠٢١ ·{" "}
            {shared.type === "lane" ? "حادث تغيير مسار" : "تصادم خلفي"} ·{" "}
            {formatCaseDate(shared.date)}
          </div>
          <div className="final-fault">
            <div>
              <span>أنت · الطرف الأول</span>
              <strong>٢٥٪</strong>
              <small>تويوتا كامري ٢٠٢٣</small>
            </div>
            <div className="final-bar">
              <i />
              <i />
            </div>
            <div>
              <span>الطرف الثاني</span>
              <strong>٧٥٪</strong>
              <small>هيونداي سوناتا ٢٠٢٢</small>
            </div>
          </div>
          <Button icon="download" onClick={printReport}>
            تحميل التقرير PDF
          </Button>
          {downloaded && (
            <div className="toast">
              <Icon name="check" />
              <span>
                تم فتح نافذة الطباعة. اختر «حفظ كملف PDF» لتنزيل التقرير.
              </span>
              <button onClick={() => setDownloaded(false)}>
                <Icon name="close" />
              </button>
            </div>
          )}
        </section>
        <div className="final-layout">
          <div>
            <section className="report-section">
              <div className="report-title">
                <span>
                  <Icon name="file" />
                </span>
                <div>
                  <h2>ملخص الحادث</h2>
                  <p>الوصف النهائي المعتمد</p>
                </div>
              </div>
              <div className="summary-grid">
                <div>
                  <span>موقع الحادث</span>
                  <b>{shared.location}</b>
                </div>
                <div>
                  <span>تاريخ ووقت الحادث</span>
                  <b>
                    {formatCaseDate(shared.date)} · {shared.time}
                  </b>
                </div>
              </div>
              <p className="report-copy">
                غيّرت المركبة الثانية مسارها إلى المسار الأوسط دون التأكد من
                خلوه، مما أدى إلى الاصطدام بالمركبة الأولى الموجودة في المسار.
              </p>
            </section>
          </div>
          <aside className="official-card">
            <div>
              <img src={logo} alt="سياق" />
              <span>تقرير نتيجة حادث</span>
            </div>
            <hr />
            <dl>
              <dt>رقم الحالة</dt>
              <dd>SQ-٢٦٠٢١</dd>
              <dt>حالة التقرير</dt>
              <dd>
                <Badge tone="done">معتمد</Badge>
              </dd>
              <dt>اسم الطرف الآخر</dt>
              <dd>ســـ****ـــان</dd>
              <dt>رقم الهوية</dt>
              <dd>******١٩٤٢</dd>
              <dt>رقم الجوال</dt>
              <dd>*******٦٢١</dd>
              <dt>المركبة</dt>
              <dd>هيونداي سوناتا ٢٠٢٢</dd>
              <dt>رقم اللوحة</dt>
              <dd>ر س د ٧١٢٩</dd>
            </dl>
            <div className="mask-note">
              <Icon name="lock" /> تم إخفاء البيانات الشخصية للطرف الآخر حفاظًا
              على الخصوصية.
            </div>
          </aside>
        </div>
      </main>
    </>
  )
}

function Profile({
  go,
  vehicles,
  setVehicles,
  personal,
  setPersonal,
}: {
  go: (s: Screen) => void
  vehicles: Vehicle[]
  setVehicles: React.Dispatch<React.SetStateAction<Vehicle[]>>
  personal: PersonalInfo
  setPersonal: React.Dispatch<React.SetStateAction<PersonalInfo>>
}) {
  const [tab, setTab] = useState(0)
  const [toast, setToast] = useState("")
  const [modal, setModal] =
    useState<"vehicle" | "deleteVehicle" | "password" | null>(null)
  const emptyVehicle: Vehicle = {
    id: 0,
    make: "",
    model: "",
    year: "",
    plate: "",
    color: "",
  }
  const [draftVehicle, setDraftVehicle] = useState<Vehicle>(emptyVehicle)
  const [vehicleError, setVehicleError] = useState("")
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [passwords, setPasswords] = useState({
    current: "",
    next: "",
    confirm: "",
  })
  const [showPasswords, setShowPasswords] = useState(false)
  const [passwordError, setPasswordError] = useState("")
  const [notifications, setNotifications] = useState({
    status: true,
    result: true,
  })
  const openVehicle = (vehicle?: Vehicle) => {
    setDraftVehicle(vehicle ? { ...vehicle } : { ...emptyVehicle })
    setVehicleError("")
    setModal("vehicle")
  }
  const saveVehicle = () => {
    if (
      !draftVehicle.make.trim() ||
      !draftVehicle.model.trim() ||
      !/^[0-9٠-٩]{4}$/.test(draftVehicle.year) ||
      !draftVehicle.plate.trim() ||
      !draftVehicle.color.trim()
    ) {
      setVehicleError(
        "أكمل الشركة والموديل والسنة واللوحة واللون. يجب أن تتكون السنة من ٤ أرقام.",
      )
      return
    }
    if (draftVehicle.id) {
      setVehicles((current) =>
        current.map((item) =>
          item.id === draftVehicle.id ? draftVehicle : item,
        ),
      )
      setToast("تم تحديث المركبة بنجاح.")
    } else {
      setVehicles((current) => [
        ...current,
        { ...draftVehicle, id: Date.now() },
      ])
      setToast("تمت إضافة المركبة وأصبحت متاحة في البلاغات الجديدة.")
    }
    setModal(null)
  }
  const savePassword = () => {
    const valid = isStrongPassword(passwords.next)
    if (!passwords.current) return setPasswordError("أدخل كلمة المرور الحالية.")
    if (!valid)
      return setPasswordError(
        "يجب أن تتكون كلمة المرور الجديدة من ٨ أحرف على الأقل وتتضمن حرفًا ورقمًا.",
      )
    if (passwords.next !== passwords.confirm)
      return setPasswordError("كلمتا المرور الجديدتان غير متطابقتين.")
    setModal(null)
    setPasswords({ current: "", next: "", confirm: "" })
    setPasswordError("")
    setToast("تم تغيير كلمة المرور بنجاح.")
  }
  return (
    <>
      <Header onNavigate={go} />
      <main className="profile-page shell">
        <div className="section-head">
          <div>
            <h1>إعدادات الحساب</h1>
            <p>إدارة بياناتك ومركباتك وإعدادات الوصول.</p>
          </div>
        </div>
        <div className="profile-layout">
          <aside>
            {["البيانات الشخصية", "مركباتي", "إعدادات الحساب"].map((x, i) => (
              <button
                className={tab === i ? "active" : ""}
                onClick={() => setTab(i)}
                key={x}
              >
                <Icon name={i === 0 ? "user" : i === 1 ? "car" : "lock"} />
                {x}
                <Icon name="chevron" />
              </button>
            ))}
          </aside>
          <section className="profile-card">
            {tab === 0 && (
              <>
                <h2>البيانات الشخصية</h2>
                <p>تظهر هذه البيانات تلقائيًا عند إنشاء حالة جديدة.</p>
                <div className="form-grid">
                  <Field
                    label="الاسم الكامل"
                    value={personal.name}
                    readOnly
                    hint="لا يمكن تعديل الاسم."
                  />
                  <Field
                    label="البريد الإلكتروني"
                    value={personal.email}
                    onChange={(email) =>
                      setPersonal((value) => ({ ...value, email }))
                    }
                    type="email"
                  />
                  <Field
                    label="رقم الهوية الوطنية"
                    value="١٠٢٣٤٥٦٧٨٩"
                    readOnly
                    dir="ltr"
                    hint="لا يمكن تعديل رقم الهوية."
                  />
                  <Field
                    label="رقم الجوال"
                    value={personal.phone}
                    onChange={(phone) =>
                      setPersonal((value) => ({ ...value, phone }))
                    }
                    dir="ltr"
                  />
                </div>
                <Button
                  onClick={() => setToast("تم حفظ بياناتك الشخصية بنجاح.")}
                >
                  حفظ التغييرات
                </Button>
              </>
            )}
            {tab === 1 && (
              <>
                <div className="section-head compact">
                  <div>
                    <h2>مركباتي</h2>
                    <p>اخترها بسرعة عند إنشاء بلاغ جديد.</p>
                  </div>
                  <Button
                    variant="secondary"
                    icon="plus"
                    onClick={() => openVehicle()}
                  >
                    إضافة مركبة
                  </Button>
                </div>
                {vehicles.length ? (
                  <div className="saved-vehicles">
                    {vehicles.map((vehicle) => (
                      <div key={vehicle.id}>
                        <span>
                          <Icon name="car" />
                        </span>
                        <div>
                          <b>
                            {vehicle.make} {vehicle.model} {vehicle.year}
                          </b>
                          <p>
                            {vehicle.plate} · {vehicle.color}
                          </p>
                        </div>
                        <button
                          className="icon-btn"
                          onClick={() => openVehicle(vehicle)}
                          aria-label={`تعديل ${vehicle.make}`}
                        >
                          <Icon name="edit" />
                        </button>
                        <button
                          className="icon-btn danger"
                          onClick={() => {
                            setDeleteId(vehicle.id)
                            setModal("deleteVehicle")
                          }}
                          aria-label={`حذف ${vehicle.make}`}
                        >
                          <Icon name="trash" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <span>
                      <Icon name="car" size={30} />
                    </span>
                    <h3>لا توجد مركبات محفوظة</h3>
                    <p>أضف مركبة لتظهر في البلاغات الجديدة.</p>
                    <Button icon="plus" onClick={() => openVehicle()}>
                      إضافة مركبة
                    </Button>
                  </div>
                )}
              </>
            )}
            {tab === 2 && (
              <>
                <h2>إعدادات الحساب</h2>
                <p>إدارة كلمة المرور والإشعارات والجلسة الحالية.</p>
                <div className="setting-row">
                  <span>
                    <Icon name="lock" />
                  </span>
                  <div>
                    <b>كلمة المرور</b>
                    <p>آخر تحديث قبل ٤ أشهر</p>
                  </div>
                  <Button
                    variant="secondary"
                    onClick={() => setModal("password")}
                  >
                    تغيير كلمة المرور
                  </Button>
                </div>
                <h3 className="subhead">إعدادات الإشعارات</h3>
                {[
                  [
                    "status",
                    "إشعاري عند تغير حالة البلاغ",
                    "إشعار عند انتقال الحالة إلى خطوة جديدة",
                  ],
                  [
                    "result",
                    "إشعاري عند توفر النتيجة النهائية",
                    "إشعار بعد اعتماد الخبير للتقرير",
                  ],
                ].map(([key, title, text]) => (
                  <label className="setting-row" key={key}>
                    <span>
                      <Icon name="clock" />
                    </span>
                    <div>
                      <b>{title}</b>
                      <p>{text}</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={
                        notifications[(key as keyof typeof notifications)]
                      }
                      onChange={(e) => {
                        setNotifications((value) => ({
                          ...value,
                          [key]: e.target.checked,
                        }))
                        setToast("تم تحديث تفضيلات الإشعارات.")
                      }}
                    />
                  </label>
                ))}
                <div className="setting-row danger-zone">
                  <span>
                    <Icon name="logout" />
                  </span>
                  <div>
                    <b>تسجيل الخروج</b>
                    <p>سيتم إنهاء الجلسة والعودة للصفحة الرئيسية.</p>
                  </div>
                  <Button variant="secondary" onClick={() => go("landing")}>
                    تسجيل الخروج
                  </Button>
                </div>
              </>
            )}
          </section>
        </div>
        {toast && (
          <div className="toast">
            <Icon name="check" />
            <span>{toast}</span>
            <button onClick={() => setToast("")}>
              <Icon name="close" />
            </button>
          </div>
        )}
      </main>
      {modal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal">
            <button
              className="modal-close icon-btn"
              onClick={() => setModal(null)}
              aria-label="إغلاق"
            >
              <Icon name="close" />
            </button>
            {modal === "vehicle" && (
              <>
                <span className="modal-icon">
                  <Icon name="car" />
                </span>
                <h2>{draftVehicle.id ? "تعديل المركبة" : "إضافة مركبة"}</h2>
                <p>ستظهر المركبة في اختيارات البلاغ الجديد.</p>
                {vehicleError && (
                  <div className="alert error">
                    <Icon name="alert" />
                    <span>{vehicleError}</span>
                  </div>
                )}
                <div className="form-grid">
                  <Field
                    label="الشركة المصنعة"
                    value={draftVehicle.make}
                    onChange={(make) =>
                      setDraftVehicle((value) => ({ ...value, make }))
                    }
                    placeholder="تويوتا"
                  />
                  <Field
                    label="الموديل"
                    value={draftVehicle.model}
                    onChange={(model) =>
                      setDraftVehicle((value) => ({ ...value, model }))
                    }
                    placeholder="كامري"
                  />
                  <Field
                    label="سنة الصنع"
                    value={draftVehicle.year}
                    onChange={(year) =>
                      setDraftVehicle((value) => ({ ...value, year }))
                    }
                    placeholder="٢٠٢٤"
                    dir="ltr"
                  />
                  <Field
                    label="رقم اللوحة"
                    value={draftVehicle.plate}
                    onChange={(plate) =>
                      setDraftVehicle((value) => ({ ...value, plate }))
                    }
                    placeholder="أ ب ج ١٢٣٤"
                  />
                  <Field
                    label="اللون"
                    value={draftVehicle.color}
                    onChange={(color) =>
                      setDraftVehicle((value) => ({ ...value, color }))
                    }
                    placeholder="أبيض"
                  />
                </div>
                <div className="modal-actions">
                  <Button variant="secondary" onClick={() => setModal(null)}>
                    إلغاء
                  </Button>
                  <Button onClick={saveVehicle}>حفظ المركبة</Button>
                </div>
              </>
            )}
            {modal === "deleteVehicle" && (
              <>
                <span className="modal-icon">
                  <Icon name="trash" />
                </span>
                <h2>هل تريد حذف هذه المركبة؟</h2>
                <p>
                  ستُحذف من اختيارات البلاغات المستقبلية فقط، ولن تتأثر سجلات
                  الحوادث السابقة.
                </p>
                <div className="modal-actions">
                  <Button variant="secondary" onClick={() => setModal(null)}>
                    إلغاء
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => {
                      setVehicles((current) =>
                        current.filter((item) => item.id !== deleteId),
                      )
                      setModal(null)
                      setToast("تم حذف المركبة من الاختيارات المستقبلية.")
                    }}
                  >
                    تأكيد الحذف
                  </Button>
                </div>
              </>
            )}
            {modal === "password" && (
              <>
                <span className="modal-icon">
                  <Icon name="lock" />
                </span>
                <h2>تغيير كلمة المرور</h2>
                <p>
                  يجب أن تتضمن كلمة المرور الجديدة حرفًا ورقمًا و٨ أحرف على الأقل.
                </p>
                {passwordError && (
                  <div className="alert error">
                    <Icon name="alert" />
                    <span>{passwordError}</span>
                  </div>
                )}
                <div className="form-stack">
                  <Field
                    label="كلمة المرور الحالية"
                    value={passwords.current}
                    onChange={(current) =>
                      setPasswords((value) => ({ ...value, current }))
                    }
                    type={showPasswords ? "text" : "password"}
                  />
                  <Field
                    label="كلمة المرور الجديدة"
                    value={passwords.next}
                    onChange={(next) =>
                      setPasswords((value) => ({ ...value, next }))
                    }
                    type={showPasswords ? "text" : "password"}
                  />
                  <Field
                    label="تأكيد كلمة المرور"
                    value={passwords.confirm}
                    onChange={(confirm) =>
                      setPasswords((value) => ({ ...value, confirm }))
                    }
                    type={showPasswords ? "text" : "password"}
                    error={
                      passwords.confirm && passwords.confirm !== passwords.next
                        ? "كلمتا المرور غير متطابقتين."
                        : undefined
                    }
                  />
                  <Button
                    variant="ghost"
                    icon="eye"
                    onClick={() => setShowPasswords(!showPasswords)}
                  >
                    {showPasswords
                      ? "إخفاء كلمات المرور"
                      : "إظهار كلمات المرور"}
                  </Button>
                </div>
                <div className="modal-actions">
                  <Button variant="secondary" onClick={() => setModal(null)}>
                    إلغاء
                  </Button>
                  <Button onClick={savePassword}>حفظ كلمة المرور</Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}

function Legal({
  go,
  type,
}: {
  go: (s: Screen) => void
  type: "privacy" | "terms"
}) {
  const privacy = type === "privacy"
  return (
    <>
      <Header onNavigate={go} />
      <main className="profile-page shell">
        <button className="back-link" onClick={() => go("landing")}>
          <Icon name="arrow" /> العودة للرئيسية
        </button>
        <section className="profile-card">
          <div className="report-title">
            <span>
              <Icon name={privacy ? "shield" : "file"} />
            </span>
            <div>
              <h1>{privacy ? "سياسة الخصوصية" : "الشروط والأحكام"}</h1>
              <p>آخر تحديث: نوفمبر ٢٠٢٦</p>
            </div>
          </div>
          {privacy ? (
            <>
              <h2>كيف يستخدم سياق بياناتك؟</h2>
              <p className="report-copy">
                تُستخدم معلومات الحالة وفيديو كاميرا المركبة لتحليل الحادث وإعداد
                تقرير يدعم مراجعة الخبير المختص. يقتصر الوصول على المستخدمين
                المصرح لهم.
              </p>
              <h2>حفظ البيانات وحذفها</h2>
              <p className="report-copy">
                تُحفظ الفيديوهات والبيانات المرتبطة لمدة تقارب ٩٠ يومًا بعد إغلاق
                الحالة، ثم تُحذف تلقائيًا وفق سياسة الاحتفاظ.
              </p>
              <h2>إخفاء بيانات الطرف الآخر</h2>
              <p className="report-copy">
                تُخفى البيانات الشخصية للطرف الآخر في التقرير المعروض أو المحمّل،
                مع إبقاء بيانات المركبة اللازمة للتعرّف عليها.
              </p>
            </>
          ) : (
            <>
              <h2>نطاق الخدمة</h2>
              <p className="report-copy">
                يدعم سياق الحوادث البسيطة دون إصابات، والأضرار المادية فقط، في
                النهار عندما يكون الطقس ومدى الرؤية واضحين، ولحالتي التصادم
                الخلفي وتغيير المسار.
              </p>
              <h2>طبيعة النتيجة</h2>
              <p className="report-copy">
                النسبة التي يولدها سياق مقترح لدعم القرار، ولا تصبح نتيجة نهائية
                إلا بعد مراجعة واعتماد الخبير المختص.
              </p>
              <h2>مسؤولية المستخدم</h2>
              <p className="report-copy">
                يلتزم المستخدم بتقديم معلومات صحيحة وفيديو مرتبط مباشرة بالحادث،
                وباستخدام الخدمة ضمن نطاقها المحدد.
              </p>
            </>
          )}
          <Button onClick={() => go("landing")}>فهمت، العودة للرئيسية</Button>
        </section>
      </main>
    </>
  )
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing")
  const [prevScreen, setPrevScreen] = useState<Screen>("landing")
  const [vehicles, setVehicles] = useState<Vehicle[]>([
    {
      id: 1,
      make: "تويوتا",
      model: "كامري",
      year: "٢٠٢٣",
      plate: "أ ب ج ٤٨٢١",
      color: "أبيض لؤلؤي",
    },
    {
      id: 2,
      make: "هيونداي",
      model: "سوناتا",
      year: "٢٠٢٢",
      plate: "ر س د ٧١٢٩",
      color: "رمادي",
    },
  ])
  const [personal, setPersonal] = useState<PersonalInfo>({
    name: "نورة محمد العتيبي",
    phone: "055 321 8421",
    email: "noura@example.sa",
  })
  const [reviewState, setReviewState] =
    useState<"new" | "reviewing" | "approved">("new")
  const [shared, setShared] = useState<SharedCaseInfo>({
    type: "lane",
    date: getTodayValue(),
    time: "10:28",
    location: "طريق الملك فهد، حي العليا، الرياض",
    partyAPosition: null,
  })
  const go = (next: Screen) => {
    setPrevScreen(screen)
    setScreen(next)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }
  const view = useMemo(() => {
    const props = { go }
    switch (screen) {
      case "landing":
        return <Landing {...props} />
      case "login":
        return <Login {...props} />
      case "register":
        return <Register {...props} />
      case "otp":
        return <Otp {...props} />
      case "reset":
        return <Reset {...props} />
      case "home":
        return <Home {...props} />
      case "cases":
        return <Cases {...props} />
      case "wizard":
        return (
          <Wizard
            {...props}
            vehicles={vehicles}
            shared={shared}
            setShared={setShared}
          />
        )
      case "pending":
        return <Pending {...props} />
      case "invite":
        return <Invite {...props} shared={shared} />
      case "party2":
        return (
          <Party2
            {...props}
            vehicles={vehicles}
            shared={shared}
            setShared={setShared}
          />
        )
      case "processing":
        return <Processing {...props} />
      case "expert-login":
        return <ExpertLogin {...props} />
      case "expert-register":
        return <ExpertRegister {...props} />
      case "expert":
        return (
          <Expert
            {...props}
            reviewState={reviewState}
            setReviewState={setReviewState}
          />
        )
      case "review":
        return (
          <Review {...props} setReviewState={setReviewState} shared={shared} />
        )
      case "rules":
        return <RulesReference {...props} from={prevScreen} />
      case "final":
        return <Final {...props} shared={shared} />
      case "profile":
        return (
          <Profile
            {...props}
            vehicles={vehicles}
            setVehicles={setVehicles}
            personal={personal}
            setPersonal={setPersonal}
          />
        )
      case "privacy":
        return <Legal {...props} type="privacy" />
      case "terms":
        return <Legal {...props} type="terms" />
    }
  }, [screen, prevScreen, vehicles, personal, reviewState, shared])
  return <div dir="rtl">{view}</div>
}
