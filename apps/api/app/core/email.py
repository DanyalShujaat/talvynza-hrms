"""Email adapter. `console` logs messages, `memory` captures them (tests), `smtp` sends for real."""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("talvynza.email")


@dataclass
class OutboundEmail:
    to: str
    subject: str
    body: str


OUTBOX: list[OutboundEmail] = []  # populated only by the memory backend


def send_email(to: str, subject: str, body: str) -> None:
    s = get_settings()
    mail = OutboundEmail(to, subject, body)
    if s.email_backend == "memory":
        OUTBOX.append(mail)
    elif s.email_backend == "smtp":
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
    else:
        # Dev console backend. Bodies contain one-time links, so never enable in production.
        log.info("EMAIL to=%s subject=%s\n%s", to, subject, body)
