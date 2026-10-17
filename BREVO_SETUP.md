# Siyaq — Brevo real email OTP setup

Your Flask code already supports authenticated SMTP. This version points it at Brevo.

## Finish in 3 steps

1. In Brevo, create an **SMTP key** (not an API key). Save it privately; never share it in chat, screenshots, or GitHub.
2. Open `.env` next to `app.py`. Fill in only these two blank lines:

   ```dotenv
   SMTP_USER=YOUR_BREVO_SMTP_LOGIN
   SMTP_PASSWORD=YOUR_BREVO_SMTP_KEY
   ```

   Copy **SMTP_USER** from the **Login** shown in Brevo > Transactional > Email > Real time > SMTP settings. It is **not** your Hotmail login. Paste the generated SMTP key into **SMTP_PASSWORD**. Do not include quotes or extra spaces. The other lines are preconfigured:

   ```dotenv
   OTP_MODE=smtp
   SMTP_HOST=smtp-relay.brevo.com
   SMTP_PORT=587
   SMTP_FROM=siyaqProject@hotmail.com
   ```

3. In Brevo, make sure the sender `siyaqProject@hotmail.com` is verified and approved for transactional sending. Brevo may restrict free-mail senders such as Hotmail or require a domain you control and have authenticated. If it refuses the sender, you must use an eligible verified sender; changing the From field alone will not bypass sender verification. Your account may also need transactional-email activation.

Restart Flask in VS Code PowerShell:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000/register and register with an **email inbox you can check**. The six-digit code should arrive by email (check Spam/Junk). The orange demo-code banner should **not** appear. If delivery fails, the app should show an error rather than creating an unverified account.

## Important

- No SMTP key or password is included in this ZIP. The sender and SMTP login are not the same thing.
- Your `.env` is excluded from Git by `.gitignore`; keep it secret and don't upload it to a public repository.
- The code expires in 10 minutes, limits guesses to five, and allows resend after one minute. Email verifies only email ownership, **not** the mobile phone number.
- This is a local prototype. Before putting it on a public server, use HTTPS, secure session cookies, a persistent strong `SECRET_KEY`, and server-side rate limiting.
- If you need to switch temporarily back to the on-screen test code, set `OTP_MODE=demo`, but it must not be used to verify real users.
