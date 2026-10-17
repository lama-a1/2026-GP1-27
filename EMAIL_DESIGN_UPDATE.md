# Siyaq — Branded Brevo Email Templates

- Both OTP and second-party invitation emails now include Arabic RTL responsive HTML, green Siyaq branding, and plaintext fallback.
- Invitation emails include a clear action button, reference, expiry, and fallback URL.
- The existing secure invitation system is unchanged: creator sends to a specific email, recipient logs in or registers and verifies email, invitation is single-use and expires after 7 days, recipient is linked to Party B and can complete their statement and video.
- Use `OTP_MODE=api` and `BREVO_API_KEY` in `.env` for Brevo REST API.
- Email delivery and second-party invitations need a publicly accessible HTTPS deployment for other devices. `127.0.0.1` links only work on the host computer.
- The Flask application is a student prototype, not production security audited. Test with synthetic or consented data.
