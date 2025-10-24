"""Minimal emailer used in documentation tests."""

from email.message import EmailMessage
import os
import smtplib


def send_email(to_addrs, subject, html_body, text_body=None, attachments=None):
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("SMTP_FROM", "no-reply@example.com")
    message["To"] = ", ".join(to_addrs)
    message.set_content(text_body or subject)
    message.add_alternative(html_body, subtype="html")
    for filename, content in attachments or []:
        message.add_attachment(content, maintype="application", subtype="octet-stream", filename=filename)

    host = os.getenv("SMTP_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT", "1025"))
    with smtplib.SMTP(host, port) as smtp:
        smtp.send_message(message)


__all__ = ["send_email"]
