"""Job: πρωινή σύνοψη εργασιών με ανοιχτή προθεσμία."""
from __future__ import annotations

import html
import logging
from datetime import datetime

from .. import notify
from ..config import Settings
from ..eclass import EClass, EClassError, parsers
from ..eclass.client import BASE
from ..models import Assignment
from ..notify import Message
from ..text import GREEK_DAYS_SHORT

log = logging.getLogger(__name__)
PORTAL = f"{BASE}/main/portfolio.php"


def collect(ec: EClass, tz) -> list[Assignment]:
    result: list[Assignment] = []
    for code, title in ec.courses().items():
        try:
            r = ec.work_page(code)
        except Exception as e:
            log.warning("Εργασίες %s: %s", code, e)
            continue
        items = parsers.parse_assignments(r.text, r.url, title, tz)
        if parsers.has_assignment_table(r.text) and not items:
            log.warning("%s: υπάρχει πίνακας εργασιών αλλά δεν διαβάστηκε καμία (άλλαξε το eClass;)", code)
        log.info("%s: %d εργασίες", code, len(items))
        result.extend(items)
    return result


def fill_start(ec: EClass, a: Assignment, tz) -> None:
    try:
        r = ec.get(a.link, dump_as=f"assignment_{a.link.rsplit('=', 1)[-1]}")
        a.start = parsers.parse_assignment_start(r.text, tz)
    except Exception as e:
        log.warning("Σελίδα εργασίας %s: %s", a.link, e)


def fmt_deadline(dl: datetime | None, now: datetime) -> tuple[str, bool]:
    """(κείμενο, επείγον)"""
    if dl is None:
        return "χωρίς προθεσμία", False
    left = dl - now
    hours = left.total_seconds() / 3600
    when = f"{GREEK_DAYS_SHORT[dl.weekday()]} {dl:%d/%m %H:%M}"
    if hours < 24:
        rel = f"σε {max(int(hours), 0)} ώρες"
    else:
        rel = f"σε {left.days} μέρες" if left.days != 1 else "αύριο"
    return f"{when} ({rel})", hours < 48


def select(items: list[Assignment], now: datetime, since: datetime, hide_submitted: bool
           ) -> tuple[list[Assignment], list[Assignment]]:
    """(με ανοιχτή προθεσμία, χωρίς προθεσμία που χρειάζονται έλεγχο ημερομηνίας έναρξης)"""
    active = [a for a in items
              if not a.expired and a.deadline is not None and a.deadline > now and a.deadline >= since]
    if hide_submitted:
        active = [a for a in active if a.submitted is not True]
    active.sort(key=lambda a: (a.submitted is True, a.deadline))
    undated = [a for a in items if a.deadline is None and not a.expired and a.submitted is not True]
    return active, undated


def build_message(active: list[Assignment], no_deadline: list[Assignment], now: datetime, portal: str = PORTAL) -> Message:
    pending = [a for a in active if a.submitted is not True]
    lines, rows = [], []
    for a in active:
        when, urgent = fmt_deadline(a.deadline, now)
        mark = "✅" if a.submitted else ("🔴" if urgent else "⏳")
        lines.append(f"{mark} {a.title}\n    {a.course} · {when}")
        color = "#2e7d32" if a.submitted else ("#c62828" if urgent else "#333")
        rows.append(
            f'<tr><td style="padding:6px 8px">{mark}</td>'
            f'<td style="padding:6px 8px"><a href="{html.escape(a.link)}" style="font-weight:600">{html.escape(a.title)}</a>'
            f'<div style="color:#666;font-size:12px">{html.escape(a.course)}</div></td>'
            f'<td style="padding:6px 8px;color:{color};white-space:nowrap">{html.escape(when)}</td></tr>'
        )
    extra = ""
    if no_deadline:
        lines.append("\nΧωρίς προθεσμία:")
        lines += [f"• {a.title} ({a.course}, από {a.start:%d/%m/%Y})" for a in no_deadline]
        extra = ('<h3 style="font-size:14px;color:#666">Χωρίς προθεσμία</h3><ul>'
                 + "".join(f'<li><a href="{html.escape(a.link)}">{html.escape(a.title)}</a> '
                           f'<span style="color:#666">({html.escape(a.course)})</span></li>' for a in no_deadline)
                 + "</ul>")
    if pending:
        title = "📚 1 εργασία σε εκκρεμότητα" if len(pending) == 1 else f"📚 {len(pending)} εργασίες σε εκκρεμότητα"
    elif active:
        title = "📚 Όλες οι ενεργές εργασίες έχουν υποβληθεί"
    else:
        title = "📚 Καμία ενεργή εργασία"
    text = "\n".join(lines) or "Δεν υπάρχουν εργασίες με ανοιχτή προθεσμία."
    body = (f'<h2 style="font-size:18px">{html.escape(title)}</h2>'
            f'<table style="border-collapse:collapse">{"".join(rows)}</table>{extra}'
            f'<p style="color:#888;font-size:12px">🔴 λήγει σε λιγότερο από 48 ώρες · ✅ έχει υποβληθεί</p>')
    urgent = sum(1 for a in pending if fmt_deadline(a.deadline, now)[1])
    private_text = (f"{urgent} λήγουν σε λιγότερο από 48 ώρες. " if urgent else "") + "Άνοιξε το eClass για λεπτομέρειες."
    return Message(title, text, body, portal, ["calendar"],
                   ("🔴 " if urgent else "") + title, private_text, portal)


def run(cfg: Settings, dry_run: bool = False, dump: bool = False) -> int:
    tz = cfg.tz
    now = datetime.now(tz)
    since = datetime.combine(cfg.digest_since, datetime.min.time(), tzinfo=tz)
    try:
        ec = EClass(cfg.eclass_username, cfg.eclass_password, base=cfg.eclass_url,
                    dump_dir=cfg.state_dir / "debug" if dump else None)
        ec.login()
        items = collect(ec, tz)
    except EClassError as e:
        log.error("Digest: %s", e)
        return 1

    active, undated = select(items, now, since, cfg.digest_hide_submitted)
    no_deadline = []
    for a in undated:
        fill_start(ec, a, tz)
        if a.start and a.start >= since:
            no_deadline.append(a)
    if len(undated) > len(no_deadline):
        log.info("Παραλείπονται %d παλιές εργασίες χωρίς προθεσμία", len(undated) - len(no_deadline))

    if not active and not cfg.digest_always:
        log.info("Καμία εργασία με ανοιχτή προθεσμία, δεν στέλνω τίποτα (%d χωρίς προθεσμία)", len(no_deadline))
        return 0

    msg = build_message(active, no_deadline, now, portal=cfg.portal_url)
    log.info("Digest: %d ενεργές εργασίες, %d χωρίς προθεσμία", len(active), len(no_deadline))
    if dry_run:
        print(f"{msg.title}\n{msg.text}")
        return 0
    notify.summary(cfg, msg, send_email=True)
    return 0
