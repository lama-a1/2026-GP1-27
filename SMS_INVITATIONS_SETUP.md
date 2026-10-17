# Siyaq: SMS invitations + Email OTP

## How it works
- Email registration OTP remains Brevo transactional **email**.
- The case creator enters Party B’s Saudi mobile number and sends an SMS through Brevo transactional SMS API.
- Party B opens the one-time invitation link, signs up or signs in with the **same phone number** and verifies their email through OTP if registering.
- Party B accepts the invitation and is attached to the same case as Party B. The token expires in 7 days and prior unclaimed invitations are revoked on successful resend.

## Setup
1. Copy your existing private `.env` file into the extracted project folder (the ZIP intentionally does **not** contain secrets).
2. Ensure `OTP_MODE=api`, `BREVO_API_KEY=...`, and `BREVO_SENDER_EMAIL=...` are configured.
3. Add `BREVO_SMS_SENDER=SIYAQ` (the sender name may need registration/approval).
4. Add `PUBLIC_BASE_URL=https://YOUR-PUBLIC-SIYAQ-DOMAIN` with no trailing slash; deploy the site over HTTPS before sending links.
5. In Brevo, grant transactional email and transactional SMS permissions to the key; confirm SMS credits and any sender-ID registration for Saudi Arabia.
6. Install requirements and start with `python app.py`. Test with your own consented phone number.

## Important security / delivery limits
- Email OTP verifies the email address, **not** ownership of the phone number. This version matches the phone number saved in the user's account and requires possession of the invitation link; this is **not** SMS OTP phone verification. Add SMS OTP if verified phone ownership is required.
- Brevo accepting an SMS request does not guarantee handset delivery. Review Brevo SMS logs and delivery status.
- Keep the `.env` private and never commit API keys.
- Without a public HTTPS domain, local `localhost` invitation URLs cannot be opened from another phone.
- The app stores phone numbers as personal information; collect consent and follow applicable privacy rules.

API endpoint: POST https://api.brevo.com/v3/transactionalSMS/send
