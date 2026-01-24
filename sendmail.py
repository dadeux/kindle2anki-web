!/usr/bin/env python3
import os
import smtplib
import argparse
from email.message import EmailMessage
from typing import Optional
from dotenv import load_dotenv

# load_dotenv()
# SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
# SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
# SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
# SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
# DEFAULT_FROM_EMAIL = os.getenv("FROM_EMAIL", "")

def _validate_config(config: dict) -> None:
    missing = [
        name for name, value in {
            "SMTP_HOST": config.get("SMTP_HOST"),
            "SMTP_USERNAME": config.get("SMTP_USERNAME"),
            "SMTP_PASSWORD": config.get("SMTP_PASSWORD"),
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

def send_email(recipient: str, subject: str, body: str, 
               from_email: Optional[str] = None, 
               reply_to: Optional[str] = None) -> None:
    """
    Send an email with customizable From and Reply-To addresses.
    
    Args:
        recipient: Recipient email address
        subject: Email subject
        body: Email body
        from_email: Custom From address (defaults to FROM_EMAIL from env)
        reply_to: Optional Reply-To address
    """
    # Load environment variables
    load_dotenv()
    config = {
        'SMTP_HOST': os.getenv("SMTP_HOST", "localhost"),
        'SMTP_PORT': int(os.getenv("SMTP_PORT", 587)),
        'SMTP_USERNAME': os.getenv("SMTP_USERNAME", ""),
        'SMTP_PASSWORD': os.getenv("SMTP_PASSWORD", ""),
        'DEFAULT_FROM_EMAIL': os.getenv("FROM_EMAIL", ""),
    }

    _validate_config(config)

    # Use custom from_email if provided, otherwise use default
    actual_from_email = from_email if from_email else config['DEFAULT_FROM_EMAIL']

    if not actual_from_email:
        raise ValueError("From email address must be specified")
    
    msg = EmailMessage()
    msg["From"] = actual_from_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Sender"] = config.get("SMTP_USERNAME", "")
    
    # Add Reply-To header if specified
    if reply_to:
        msg["Reply-To"] = reply_to
    
    msg.set_content(body)
    
    with smtplib.SMTP(config['SMTP_HOST'], config['SMTP_PORT']) as server:
        server.starttls()
        server.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
        server.send_message(msg)

def main():
    parser = argparse.ArgumentParser(description="Send an email")
    parser.add_argument("recipient", help="Recipient email address")
    parser.add_argument("subject", help="Email subject")
    parser.add_argument("body", help="Email body")
    parser.add_argument("--from", dest="from_email", 
                       help="Custom From email address")
    parser.add_argument("--reply-to", dest="reply_to",
                       help="Reply-To email address")
    
    args = parser.parse_args()
    send_email(args.recipient, args.subject, args.body,
               args.from_email, args.reply_to)

if __name__ == "__main__":
    main()