"""Πότε έτρεξε τελευταία φορά κάθε job, για την οθόνη «Κατάσταση» του launcher.

Μόνο ώρα και επιτυχία, ποτέ περιεχόμενο. Ζει στο logs/, όχι στο state/, ώστε
ο φάκελος του state να έχει πάντα μόνο το κρυπτογραφημένο αρχείο. Δεν γράφεται
στο GitHub Actions.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
from pathlib import Path

FILE = "runs.json"


def record(folder: Path, job: str, ok: bool, now: dt.datetime | None = None) -> None:
    if os.getenv("GITHUB_ACTIONS"):
        return
    path = folder / FILE
    data = load(folder)
    data[job] = {"at": (now or dt.datetime.now().astimezone()).isoformat(timespec="seconds"), "ok": ok}
    with contextlib.suppress(OSError):
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def load(folder: Path) -> dict[str, dict]:
    try:
        data = json.loads((folder / FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def last(folder: Path, job: str) -> tuple[dt.datetime, bool] | None:
    entry = load(folder).get(job)
    if not entry:
        return None
    try:
        return dt.datetime.fromisoformat(entry["at"]), bool(entry["ok"])
    except (KeyError, ValueError, TypeError):
        return None
