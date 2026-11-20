"""Job: νέοι ή αλλαγμένοι βαθμοί από την πύλη φοιτητολογίου (services.uniwa.gr)."""
from __future__ import annotations

import html
import logging

import requests

from .. import notify
from ..config import Settings
from ..models import Grade
from ..notify import Message
from ..services import Services, ServicesError
from ..services.client import BASE
from ..services.parsers import fmt_value
from ..state import StoreScope

log = logging.getLogger(__name__)
GRADES_URL = f"{BASE}/student/grades/list"


def describe(g: Grade, previous: str | None) -> str:
    mark = "✅" if g.passed else ("❌" if g.value is not None else "⏳")
    line = f"{mark} {g.title}: {fmt_value(g.value)}"
    if previous not in (None, ""):
        line += f" (ήταν {fmt_value(float(previous))})"
    return line + (f"\n    {g.period}" if g.period else "")


def build_message(changes: list[tuple[Grade, str | None]]) -> Message:
    title = "📝 Νέος βαθμός" if len(changes) == 1 else f"📝 {len(changes)} νέοι βαθμοί"
    text = "\n".join(describe(g, prev) for g, prev in changes)
    body = (f"<h2 style='font-size:18px'>{html.escape(title)}</h2>"
            + "".join(f"<p>{html.escape(describe(g, p)).replace(chr(10), '<br>')}</p>" for g, p in changes)
            + f"<p><a href='{GRADES_URL}'>Άνοιγμα στην πύλη φοιτητολογίου</a></p>")
    return Message(title, text, body, GRADES_URL, ["memo"],
                   title, "Πάτα για να τον δεις στην πύλη φοιτητολογίου.", GRADES_URL)


def run(cfg: Settings, dry_run: bool = False) -> int:
    if not cfg.grades_supported:
        log.info("Οι βαθμοί δεν υποστηρίζονται ακόμα για αυτό το πανεπιστήμιο")
        return 0
    with StoreScope() as stores:
        return _run(cfg, dry_run, stores)


def _run(cfg: Settings, dry_run: bool, stores: StoreScope) -> int:
    try:
        svc = Services(cfg.eclass_username, cfg.eclass_password, profile=cfg.services_profile)
        svc.login()
        grades = svc.grades()
    except (ServicesError, requests.RequestException) as e:
        log.error("Βαθμοί: %s", e)
        return 1
    log.info("Πύλη φοιτητολογίου: %d εγγραφές βαθμών", len(grades))

    store = stores.open(cfg.seen_db)
    changes, first = store.grade_changes(grades, record=not dry_run)
    if first:
        log.info("Πρώτη φορά: καταγράφω τους υπάρχοντες βαθμούς χωρίς ειδοποίηση")
    if not changes:
        log.info("Κανένας νέος βαθμός")
        store.commit()
        return 0

    # Στα logs μόνο πλήθος, όχι βαθμοί (τα logs του Actions μένουν αποθηκευμένα)
    log.info("%d νέοι/αλλαγμένοι βαθμοί", len(changes))
    msg = build_message(changes)
    if dry_run:
        print(msg.text)
        return 0
    try:
        notify.summary(cfg, msg, send_email=True)
    except Exception as e:
        log.error("Αποτυχία αποστολής: %s", e)
        store.rollback()
        return 1
    store.commit()
    return 0
