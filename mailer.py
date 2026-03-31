import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_reset_email(to_email: str, reset_link: str) -> None:
    """
    Send a password reset email.

    Required environment variables:
        MAIL_FROM     — sender address shown to the user  e.g. noreply@yourapp.com
        MAIL_USER     — SMTP login username               e.g. your Gmail address
        MAIL_PASSWORD — SMTP login password / app password
        MAIL_HOST     — SMTP host (default: smtp.gmail.com)
        MAIL_PORT     — SMTP port (default: 465  → SSL)
    """
    mail_from     = os.environ["MAIL_FROM"]
    mail_user     = os.environ["MAIL_USER"]
    mail_password = os.environ["MAIL_PASSWORD"]
    mail_host     = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    mail_port     = int(os.environ.get("MAIL_PORT", 465))

    # ── Plain-text body ───────────────────────────────────────────────────────
    plain = f"""Hi,

You requested a password reset for your account.

Click the link below to set a new password (valid for 1 hour):

{reset_link}

If you didn't request this, you can safely ignore this email.

– The Team
"""

    # ── HTML body ─────────────────────────────────────────────────────────────
    html = f"""
<html>
  <body style="font-family:sans-serif;color:#333;max-width:480px;margin:auto;padding:24px;">
    <h2 style="color:#c8922a;">Reset your password</h2>
    <p>You requested a password reset for your account.</p>
    <p>Click the button below to set a new password. This link is valid for <strong>1 hour</strong>.</p>
    <a href="{reset_link}"
       style="display:inline-block;padding:12px 24px;background:#c8922a;color:#fff;
              text-decoration:none;border-radius:6px;font-weight:bold;margin:16px 0;">
      Reset Password →
    </a>
    <p style="font-size:0.85rem;color:#888;">
      If the button doesn't work, copy and paste this link into your browser:<br>
      <a href="{reset_link}" style="color:#c8922a;">{reset_link}</a>
    </p>
    <hr style="border:none;border-top:1px solid #eee;margin-top:32px;">
    <p style="font-size:0.8rem;color:#aaa;">
      If you didn't request this, you can safely ignore this email.
    </p>
  </body>
</html>
"""

    # ── Build message ─────────────────────────────────────────────────────────
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your password"
    msg["From"]    = mail_from
    msg["To"]      = to_email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    # ── Send ──────────────────────────────────────────────────────────────────
    with smtplib.SMTP_SSL(mail_host, mail_port) as server:
        server.login(mail_user, mail_password)
        server.sendmail(mail_from, [to_email], msg.as_string())