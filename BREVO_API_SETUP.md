# Siyaq — Brevo REST API (OTP + Party Invitations)

1. In Brevo, go to **SMTP & API → API Keys** and generate a new API key. **Do not use your SMTP key**.
2. Open `.env` next to `app.py`, set `BREVO_API_KEY` to the private key and leave `OTP_MODE=api`. Never share or commit the key.
3. Set `BREVO_SENDER_EMAIL` to your **verified/authorized sender**. The sample uses `siyaqProject@hotmail.com` but Brevo may require a different verified sender/domain.
4. If Brevo's API IP restriction is enabled, authorize your current outbound IP in Brevo Security → Authorized IPs. Avoid authorizing broad ranges.
5. Run `python -m pip install -r requirements.txt` and `python app.py`. Test registration OTP, then a party invitation.

## Technical integration

The Flask server sends `POST https://api.brevo.com/v3/smtp/email` with a JSON body and an `api-key` header, using Python's standard library. It handles OTP and case invitations using one REST API function. The API key stays on the server. An HTTP 201 response means Brevo accepted the request, **not** guaranteed inbox delivery. Check Brevo Transactional Logs and the recipient inbox for delivery.

`OTP_MODE=smtp` remains supported as a fallback using existing SMTP settings; `OTP_MODE=demo` is localhost-only and does **not** prove email ownership.

**Note:** For another person to open an invitation, the app needs a publicly accessible HTTPS domain; a `127.0.0.1` invitation link works only on your own computer.

**Security:** Before production, replace the sample SECRET_KEY with a strong random secret, set COOKIE_SECURE=1 on HTTPS, implement rate limiting, and use an authenticated sender. Do not commit `.env`.
