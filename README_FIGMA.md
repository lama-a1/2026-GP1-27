# Siyaq — Figma-inspired Flask Release 1

This edition uses the uploaded Figma Make source as the design reference. The homepage reproduces the final centered hero, national-green palette, Tajawal typography, 8-point geometric background, original logo and workflow panel. Existing Release 1 Flask routes, SQLite schema, and submission flows are retained.

Run on Windows:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```
Open http://127.0.0.1:5000

This is an HTML/CSS/JavaScript + Python Flask + SQLite implementation; it does not require React or Node. Figma-only expert review/AI features are not implemented in Release 1. The visual matching is strongest on the homepage; other forms retain their Flask layout but share the Figma theme.
