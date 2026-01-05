#!/usr/bin/env python3

import argparse
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
load_dotenv()



# ---------- Configuration ----------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USERNAME)


def _validate_config():
    missing = [
        name for name, value in {
            "SMTP_HOST": SMTP_HOST,
            "SMTP_USERNAME": SMTP_USERNAME,
            "SMTP_PASSWORD": SMTP_PASSWORD,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


# ---------- Reusable Function ----------
def send_email(recipient: str, subject: str, body: str) -> None:
    """
    Send an email.

    Safe to import and use in a Flask app.
    """
    _validate_config()

    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


# ---------- CLI Entry Point ----------
def main():
    parser = argparse.ArgumentParser(description="Send an email")
    parser.add_argument("recipient", help="Recipient email address")
    parser.add_argument("subject", help="Email subject")
    parser.add_argument("body", help="Email body")

    args = parser.parse_args()
    send_email(args.recipient, args.subject, args.body)


if __name__ == "__main__":
    main()