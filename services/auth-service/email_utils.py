#!/usr/bin/env python3
"""
Email delivery for the Auth Service.

Sends welcome and password-reset emails over SMTP. When ``SMTP_HOST`` is empty
the message (including any action link) is logged to the console instead, so
development and CI work without an SMTP server.
"""

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

logger = logging.getLogger("auth")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@congress.local")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")


def _send_sync(to: str, subject: str, body: str) -> None:
    """Blocking SMTP send (run in a worker thread)."""
    message = EmailMessage()
    message["From"] = EMAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USERNAME:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


async def send_email(to: str, subject: str, body: str) -> None:
    """Send an email, or log it when SMTP is not configured."""
    if not SMTP_HOST:
        logger.info(
            "EMAIL (dev mode, SMTP not configured)\n  To: %s\n  Subject: %s\n%s",
            to,
            subject,
            body,
        )
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
        logger.info("Email sent to %s (subject=%s)", to, subject)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.error("Failed to send email to %s: %s", to, exc)


def welcome_email_body(username: str, token: str) -> str:
    """Body for the account-created / set-password email."""
    link = (
        f"{APP_BASE_URL}/reset-password"
        f"?token={token}&purpose=welcome&username={quote(username)}"
    )
    return (
        f"Hello {username},\n\n"
        "An account has been created for you on the Congressional Disclosure "
        "Analytics platform. To activate it, set your password using the link "
        "below:\n\n"
        f"{link}\n\n"
        "You will be asked to set up two-factor authentication on first login.\n\n"
        "If you did not expect this email, please contact your administrator.\n"
    )


def reset_email_body(username: str, token: str) -> str:
    """Body for the self-service password-reset email."""
    link = (
        f"{APP_BASE_URL}/reset-password"
        f"?token={token}&username={quote(username)}"
    )
    return (
        f"Hello {username},\n\n"
        "A password reset was requested for your account. Use the link below to "
        "choose a new password:\n\n"
        f"{link}\n\n"
        "This link expires in 60 minutes. If you did not request a reset, you can "
        "safely ignore this email.\n"
    )
