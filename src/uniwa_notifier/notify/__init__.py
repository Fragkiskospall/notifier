"""Κανάλια ειδοποιήσεων: ntfy (push), email, ειδοποίηση υπολογιστή (Mac/Windows).

Ιδιωτική λειτουργία (notify.private, προεπιλογή): ό,τι φεύγει από τη συσκευή
(ntfy, email) δεν περιέχει τίτλους, μαθήματα ή βαθμούς, μόνο το είδος της
ειδοποίησης και ένα γενικό link. Οι ειδοποιήσεις υπολογιστή μένουν τοπικές και
κρατούν το πλήρες περιεχόμενο.
"""
from __future__ import annotations

import html
import logging
from collections.abc import Callable
from dataclasses import dataclass

from .. import system
from ..config import Settings
from ..models import Item
from . import email, ntfy

log = logging.getLogger(__name__)
MAX_INDIVIDUAL = 5


@dataclass
class Message:
    """Πλήρες περιεχόμενο + η «άδεια» εκδοχή για την ιδιωτική λειτουργία."""

    title: str
    text: str
    html: str | None
    click: str
    tags: list[str]
    private_title: str
    private_text: str
    private_click: str


def _fan_out(items: list[Item], send: Callable[[Item], None]) -> None:
    for it in items[:MAX_INDIVIDUAL]:
        send(it)
    if len(items) > MAX_INDIVIDUAL:
        send(Item("more", "UNIWA", f"+{len(items) - MAX_INDIVIDUAL} ακόμα ανακοινώσεις (δες το email)", ""))


def _desktop(it: Item) -> None:
    """Τοπική ειδοποίηση μέσω του backend του λειτουργικού (σε Linux/CI: τίποτα)."""
    system.current().notify(it.source, it.title, it.link or None)


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many.format(n=n)


def announcements(cfg: Settings, items: list[Item]) -> None:
    if cfg.notify_desktop:
        _fan_out(items, _desktop)

    n = len(items)
    if cfg.notify_private:
        title = _plural(n, "📢 Νέα ανακοίνωση", "📢 {n} νέες ανακοινώσεις")
        dept = sum(1 for i in items if i.uid.startswith("dept:"))
        parts = [p for p in (f"{dept} από το τμήμα" if dept else "",
                             f"{n - dept} από το eClass" if n - dept else "") if p]
        text = " · ".join(parts) + "\nΆνοιξέ το για να τις δεις."
        click = cfg.portal_url
        if cfg.ntfy_topic:
            ntfy.send(cfg, title, text, click)
        if cfg.notify_email:
            email.send(cfg, "[UNIWA] Νέες ειδοποιήσεις", text,
                       f"<p>{html.escape(text).replace(chr(10), '<br>')}</p>"
                       f"<p><a href='{cfg.portal_url}'>eClass</a></p>")
        log.info("Στάλθηκαν ειδοποιήσεις (ιδιωτική λειτουργία)")
        return

    if cfg.ntfy_topic:
        _fan_out(items, lambda it: ntfy.send(cfg, it.source, it.title, it.link))
    if cfg.notify_email:
        subject = f"[UNIWA] {items[0].title}" if n == 1 else f"[UNIWA] {n} νέες ανακοινώσεις"
        text = "\n\n".join(f"{i.source}\n{i.title}\n{i.link}\n{i.summary}".strip() for i in items)
        body = "".join(
            f'<div style="margin:0 0 18px"><div style="color:#666;font-size:12px">{html.escape(i.source)}</div>'
            f'<a href="{html.escape(i.link)}" style="font-size:16px;font-weight:600">{html.escape(i.title)}</a>'
            f'<div style="color:#333;margin-top:4px">{html.escape(i.summary)}</div></div>'
            for i in items
        )
        email.send(cfg, subject, text, body)
    log.info("Στάλθηκαν ειδοποιήσεις για %d ανακοινώσεις", n)


def summary(cfg: Settings, msg: Message, send_email: bool) -> None:
    """Μία συγκεντρωτική ειδοποίηση (digest, εργαστήρια, βαθμοί)."""
    if cfg.notify_desktop:
        _desktop(Item("summary", msg.title, msg.text.split("\n")[0], msg.click))
    if cfg.notify_private:
        title, text, click = msg.private_title, msg.private_text, msg.private_click
        body = f"<p>{html.escape(text).replace(chr(10), '<br>')}</p><p><a href='{click}'>Άνοιγμα</a></p>"
    else:
        title, text, click, body = msg.title, msg.text, msg.click, msg.html
    if cfg.ntfy_topic:
        ntfy.send(cfg, title, text, click, msg.tags)
    if send_email and cfg.notify_email and body is not None:
        email.send(cfg, f"[UNIWA] {title}", text, body)
