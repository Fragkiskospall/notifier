from __future__ import annotations

import requests

from ..config import Settings

TIMEOUT = 30


def send(cfg: Settings, title: str, message: str, click: str = "", tags: list[str] | None = None) -> None:
    payload = {"topic": cfg.ntfy_topic, "title": title[:100], "message": message[:3900],
               "tags": tags or ["mortar_board"]}
    if click:
        payload["click"] = click
    headers = {"Authorization": f"Bearer {cfg.ntfy_token}"} if cfg.ntfy_token else {}
    r = requests.post(cfg.ntfy_server, json=payload, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
