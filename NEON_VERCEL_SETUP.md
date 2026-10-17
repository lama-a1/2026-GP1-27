# Siyaq: Neon PostgreSQL + Vercel

This package adds PostgreSQL support while keeping SQLite for local development.

1. Create a Neon PostgreSQL project at https://neon.tech/ and copy its **connection string** (use the pooled connection string if offered).
2. In Vercel > Project > Settings > Environment Variables add `DATABASE_URL` as a **sensitive** value for Production. Do not put it in Git or screenshots.
3. Keep your existing `BREVO_API_KEY`, `OTP_MODE=api`, `BREVO_SENDER_EMAIL`, `BREVO_SMS_SENDER`, and `SECRET_KEY` variables in Vercel. Set `COOKIE_SECURE=1` and `PUBLIC_BASE_URL=https://siyaq-plum.vercel.app`.
4. Push these files to the same private GitHub repository and redeploy Vercel.
5. Register a NEW test account and create a test case. Old accounts in temporary Vercel SQLite are NOT migrated.

**Warning:** This release does not implement durable video storage. Video upload is explicitly blocked on Vercel until a private object-storage backend is configured. Local SQLite and local video upload still work.

**Security:** Do not upload real IDs, videos or accident details while testing. Protect the Neon connection string. Rotate previously exposed Flask `SECRET_KEY` in both local and Vercel settings.

**Testing:** `python -m pytest -q` (requires pytest). Tests are for local SQLite; PostgreSQL must be tested against your own Neon database after configuration.
