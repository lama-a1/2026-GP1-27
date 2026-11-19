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
- Sprint 2 automatic video analysis (`siyaq_cv/`, no PyTorch): vehicle detection (YOLOv8s ONNX + onnxruntime; YOLOv8n with `SIYAQ_DETECTOR=yolov8n`) and tracking, Farneback optical-flow motion, and detected events (collision, lane change, sudden stop, following distance, overtaking) with their measures, shown on a demo page with a tracking overlay. Details in `siyaq_cv/README_AR.md`.

Expert case review, editing, and approval are not yet available. Case-status emails are sent to users who turn them on; final-result emails are not implemented yet. Local face blurring requires manual review and does not include license-plate blurring or cloud-video processing. Automatic retention cleanup is also pending.

## Planned Features

- Violation analysis on top of the Sprint 2 events.
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
| Vehicle detection | YOLOv8s (COCO weights, ONNX, onnxruntime) |

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
| `siyaq_cv/` | Video-analysis engine: detection, tracking, optical flow, measures and events (`threshold_grid.py`: candidate thresholds and their published sources) |
| `video_analysis.py` | Routes and page that run the engine on an uploaded video |
| `data/dataset/` | Final dataset index (136 clips), train/validation/test splits, excluded clips, CVAT job map |
| `data/ground_truth/` | Labels extracted from CVAT (`cvat_labels.json`) and the team-reviewed clips |
| `tools/cvat_labels.py` | Extracts the CVAT project export into `data/ground_truth/cvat_labels.json` |
| `tools/cross_validate.py` | Repeated stratified 5-fold cross-validation of the event rules against the CVAT labels |
| `tools/rule_variants.py` | Cross-validated comparison of the rule variants reported in Section 5.1 |
| `tools/scoring.py` | Evaluation rules (collision within 0.5 s, Vehicle B box IoU, lane-change temporal IoU, ...) |
| `tests/` | Application and engine tests |
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

## Evaluating the Video Analysis

```bash
python -m pip install -r requirements-eval.txt
# 1. labels: export the CVAT project as "Datumaro 1.0" (without images), then
python tools/cvat_labels.py --export Siyaq_Datumaro.zip
# 2. cross-validation: --videos is the folder with dataset_index.csv and the clip videos
python tools/cross_validate.py --videos /path/to/Siyaq_Part1/dataset --out cv_output
```

`cv_output/cv_results.xlsx` holds the mean, standard deviation and 95% confidence interval of each measure over the folds, the same for the default thresholds and a simple baseline, how often each threshold value was chosen, and the thresholds chosen on all clips (to copy into `siyaq_cv/config.py`). The engine output of each clip is cached in `.cv_cache/`. The lane-change, sudden-stop and following-distance settings are chosen separately for each accident type of the report (`LANE_BY_TYPE` in `siyaq_cv/config.py`; which stages are per type: `STAGES` in `siyaq_cv/threshold_grid.py`); `lane_change_vehicle` scores the lane change without its timing (reported only). The "default thresholds" column uses the settings before cross-validation (`DEFAULTS` in `tools/cross_validate.py`). `--fix KEY=VALUE` keeps one setting at one value, e.g. `--fix LANE_FALLBACK_S=0` scores the engine without the lane change inferred from the report type.

The rule variants compared in the report (shared thresholds, lateral-speed check, minimum-TTC option, per-type thresholds) can be repeated with `python tools/rule_variants.py . <variant> <out.json>` after a cross-validation run has filled `.cv_cache/`.

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
