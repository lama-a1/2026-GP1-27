<p align="center">
  <img src="docs/images/siyaq-logo.png" alt="Siyaq logo" width="240">
</p>

# Siyaq | سياق

## About Siyaq

Siyaq is a graduation project developed by Information Technology students at King Saud University. It aims to support the analysis of minor traffic accidents using dashcam footage, accident details, and accounts from the involved parties.

The planned system combines video processing, vehicle detection and tracking, traffic-event analysis, and rule-based fault estimation based on relevant Saudi traffic regulations. Its intended output is a suggested fault percentage supported by evidence and reasoning, followed by review by an authorized expert.

The current implementation provides the Arabic web application for collecting and managing accident cases. Automated accident analysis, fault estimation, report generation, and expert approval are planned for later development.

## Supported Accident Scenarios

- Rear-end collisions.
- Lane-change accidents.

The project scope covers minor, two-vehicle accidents with no injuries, with clear weather and visibility. Party A must provide one dashcam video; Party B may provide one additional video. The planned analysis treats each video independently.

## Current Features

- Accident-party registration with a required national ID and email verification.
- Login, logout, password changes, and email-based password recovery; login stops for 15 minutes after 5 wrong attempts.
- Case creation with accident details, location selection, vehicle information, and an accident description.
- Selection of saved vehicles and management of vehicles through profile settings.
- Email-address changes after verification of the new address.
- Video upload, download, and deletion with access checks; one video per party, up to 200 MB.
- Targeted email invitations allowing the second party to join the same case.
- Case lists and progress statuses for accident parties.
- Authorized expert registration and login with read-only case lists and a rules page.
- Local face-blurring support through the optional OpenCV dependency.

Expert case review, editing, and approval are not yet available. Case-status emails are sent to users who turn them on; final-result emails are not implemented yet. Local face blurring requires manual review and does not include license-plate blurring or cloud-video processing. Automatic retention cleanup is also pending.

## Planned Features

- Vehicle detection and tracking from dashcam recordings.
- Movement, traffic-event, and violation analysis.
- Rule-based suggested fault percentages of 0%, 25%, 50%, 75%, or 100%.
- Evidence frames and explanations accompanying the suggested result.
- Expert review, modification, and approval of reports.
- Final approved results for accident parties.
- Extended privacy processing and automatic retention cleanup.

The suggested assessment is intended to support expert review. It does not independently issue a legally binding fault decision.

## Technologies

| Component | Technology |
| --- | --- |
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript, Jinja templates |
| Database design | Tables follow the Siyaq EER diagram (`schema.py`) |
| Local database | SQLite |
| Hosted database support | PostgreSQL, including Neon |
| Verification and invitation email | Brevo API or SMTP |
| Video storage | Local storage, Cloudinary, or Amazon S3 |
| Location selection | Leaflet, OpenStreetMap, Nominatim |
| Optional local face blurring | OpenCV |
| Deployment workflow | Vercel |
| Development environment | Visual Studio Code |
| Project management | Jira and Confluence |
| Version control | Git and GitHub |
| Planned vehicle detection | YOLO |

## Repository Structure

| Path | Purpose |
| --- | --- |
| `app.py` | Flask routes, authentication, case workflows, and storage integration |
| `schema.py` | Database tables from the EER diagram, plus supporting tables |
| `db_backend.py` | Additional database connection helpers |
| `privacy.py` | Local face-blurring function |
| `database/` | EER mapping document and SQL scripts for SQLite and PostgreSQL |
| `templates/` | Arabic interface templates |
| `static/` | Stylesheets, browser scripts, and logos |
| `tests/` | Application tests |
| `docs/sprints/sprint-1/` | Sprint 1 report and files |
| `docs/deployment/` | Neon and Vercel deployment settings |
| `docs/images/` | Images used in the documentation |
| `.env.example` | Environment-variable template |
| `requirements.txt` | Main Python dependencies |
| `requirements-privacy.txt` | Optional local video-processing dependency |
| `AUTHORS` | Project team and supervisor |

`siyaq.db` and `uploads/` are created locally when needed and are excluded from Git.

## Run Locally

Use Python 3.11 or later for development. Open a terminal in the repository root.

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

To enable the optional local face-blurring function:

```bash
python -m pip install -r requirements-privacy.txt
```

### 3. Create the environment file

Copy `.env.example` to `.env` using your editor. Set `SECRET_KEY` to a long random value. For local development, leave `PUBLIC_BASE_URL` empty; when it is set, it must be the site's public HTTPS address. Leave `DATABASE_URL` unset to use SQLite.

For real verification and invitation emails, configure:

```dotenv
OTP_MODE=api
BREVO_API_KEY=your-brevo-api-key
BREVO_SENDER_EMAIL=your-verified-sender-address
BREVO_SENDER_NAME=Siyaq
COOKIE_SECURE=0
```

Alternatively, use `OTP_MODE=smtp` with the SMTP variables shown in `.env.example`.

For a local demonstration without email delivery, set `OTP_MODE=demo` and `INVITE_MODE=demo`. Demo mode displays verification codes and invitation links locally and only works from a loopback address. Use real email delivery on a hosted site.

Set a private `EXPERT_REGISTRATION_CODE` in `.env` to enable expert registration. Do not place the actual code in repository files.

### 4. Start the application

```bash
python -m flask --app app run
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The application initializes the local database on startup. The `/health` route checks application and database availability.

## Deployment

See [Neon and Vercel setup](docs/deployment/NEON_VERCEL_SETUP.md). Configure PostgreSQL for persistent hosted data and Cloudinary or S3 for video uploads on Vercel. Cloudinary takes priority when both storage providers are configured. Vercel's local filesystem is temporary.

Set a stable `SECRET_KEY`, `COOKIE_SECURE=1`, and the site's HTTPS address as `PUBLIC_BASE_URL` in the deployment environment. Keep service credentials in environment settings. Existing SQLite records are not automatically migrated to PostgreSQL. The database tables are created on startup; see [EER mapping](database/EER_MAPPING.md).

## Tests

Install and run the existing test suite:

```bash
python -m pip install pytest
python -m pytest -q
```

The tests use SQLite and mocked external services. Live email delivery, hosted databases, and cloud storage require separate deployment checks.

## Siyaq Team

Developed at King Saud University, College of Computer and Information Sciences.

- Raneem Alraoini
- Jana Almengash
- Lama Almubarak
- Waad Alghamdi

**Supervisor:** Dr. Hessah Alsaaran

See [AUTHORS](AUTHORS).

## Project Status

Siyaq is under development as part of the IT496 graduation project and follows an incremental Scrum process. Sprint 1 files are in [docs/sprints/sprint-1](docs/sprints/sprint-1/).
