"""Προαιρετικό heartbeat (π.χ. healthchecks.io): ping στην αρχή και στο τέλος κάθε job.

Αν το URL δεν έχει οριστεί, δεν κάνει τίποτα. Αποτυχία του ping δεν ρίχνει ποτέ το job.
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


def ping(base_url: str | None, suffix: str = "") -> None:
    if not base_url:
        return
    try:
        requests.get(base_url.rstrip("/") + suffix, timeout=10)
    except requests.RequestException as e:
        log.warning("Healthcheck ping απέτυχε: %s", e)
