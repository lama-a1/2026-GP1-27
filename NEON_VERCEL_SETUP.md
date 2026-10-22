# Siyaq deployment: Neon and Vercel

## Database and server settings

1. Create a Neon PostgreSQL database and copy its connection string.
2. Add `DATABASE_URL` to the Vercel project's environment settings.
3. Set a stable `SECRET_KEY`, `COOKIE_SECURE=1` and `PUBLIC_BASE_URL` to the site's HTTPS address.
4. Add `BREVO_API_KEY`, `BREVO_SENDER_EMAIL` and `OTP_MODE=api` for email verification and invitations.
5. Redeploy after changing environment settings.

Keep these values in the server environment. Do not commit `.env` or copy secrets into frontend files. Existing SQLite records are not automatically copied to PostgreSQL.

## Expert registration

Set `EXPERT_REGISTRATION_CODE` to enable authorized expert registration. Share it privately with the intended experts and change it after registration. Removing the code disables new registrations without removing existing accounts.

## Video uploads

Configure Cloudinary with `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET`. Uploads go directly from the browser to Cloudinary and use authenticated delivery.

S3 is also supported through `S3_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Keep the bucket private, allow PUT requests from the site's origin in CORS and grant the app permission to upload, read and delete its video objects.

Cloudinary takes priority when both services are configured. Without either service, video uploads are unavailable on Vercel because local files are temporary. Face blurring currently works only with local development uploads.

## Check the deployment

Use test data to check registration, email verification, password reset, case creation, video upload and download, and the second-party invitation. Check that another account cannot open a private case or download its videos.

Run `python -m pytest -q` locally after installing the app dependencies and `pytest`. The tests use SQLite and mocked external services. Check Neon and the configured email and video services separately on the deployed site.
