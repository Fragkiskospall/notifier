from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import Settings

TIMEOUT = 30
log = logging.getLogger(__name__)


def send(cfg: Settings, subject: str, text: str, html_body: str) -> None:
    if not all((cfg.smtp_host, cfg.smtp_user, cfg.smtp_password, cfg.mail_to)):
        log.warning("Λείπουν ρυθμίσεις SMTP, δεν στέλνω email")
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.smtp_user, cfg.mail_to, subject
    msg.set_content(text)
    msg.add_alternative(
        f"<html><body style='font-family:-apple-system,sans-serif'>{html_body}</body></html>", subtype="html"
    )
    if cfg.smtp_port == 465:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT) as smtp:
            smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT) as smtp:
            smtp.starttls()
            smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
