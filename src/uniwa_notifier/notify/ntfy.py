from __future__ import annotations

from urllib.parse import urlsplit

import requests

from ..config import Settings

TIMEOUT = 30
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def check_server(url: str) -> None:
    """Μόνο HTTPS, ώστε ούτε το μήνυμα ούτε το token να ταξιδεύουν ανοιχτά.
    Εξαίρεση ένας ntfy server στον ίδιο υπολογιστή."""
    parts = urlsplit(url)
    if parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS):
        return
    raise ValueError("Ο ntfy server πρέπει να είναι https://")


def send(cfg: Settings, title: str, message: str, click: str = "", tags: list[str] | None = None) -> None:
    check_server(cfg.ntfy_server)
    payload = {"topic": cfg.ntfy_topic, "title": title[:100], "message": message[:3900],
               "tags": tags or ["mortar_board"]}
    if click:
        payload["click"] = click
    headers = {"Authorization": f"Bearer {cfg.ntfy_token}"} if cfg.ntfy_token else {}
    r = requests.post(cfg.ntfy_server, json=payload, headers=headers, timeout=TIMEOUT, allow_redirects=False)
    if r.is_redirect:
        raise ValueError("Ο ntfy server απάντησε με ανακατεύθυνση: δεν στάλθηκε τίποτα")
    r.raise_for_status()
