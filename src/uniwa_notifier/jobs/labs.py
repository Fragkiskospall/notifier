"""Job: ειδοποίηση το πρωί αν έχεις εργαστήριο σήμερα (από τις ομάδες χρηστών)."""
from __future__ import annotations

import html
import logging
from datetime import date, datetime

from .. import notify
from ..config import Settings
from ..eclass import EClass, EClassError, parsers
from ..eclass.client import BASE
from ..models import LabSlot
from ..notify import Message
from ..text import WEEKDAY_NAMES, find_time, find_weekday

log = logging.getLogger(__name__)
PORTAL = f"{BASE}/main/portfolio.php"


def slots_for_course(code: str, title: str, groups_html: str, conf: dict) -> list[LabSlot]:
    name = conf.get("name", title)
    if "weekday" in conf:  # χειροκίνητη ρύθμιση υπερισχύει
        return [LabSlot(code, name, conf.get("group", ""), WEEKDAY_NAMES.index(conf["weekday"]), conf.get("time"))]
    out = []
    for g in parsers.parse_groups(groups_html):
        if not g.member:
            continue
        wd = find_weekday(g.name)
        if wd is not None:
            out.append(LabSlot(code, name, g.name, wd, conf.get("time") or find_time(g.name)))
    return out


def is_today(slot: LabSlot, today: date, conf: dict) -> bool:
    if slot.weekday != today.weekday():
        return False
    anchor = conf.get("anchor")
    if anchor is not None:
        anchor = anchor if isinstance(anchor, date) else date.fromisoformat(str(anchor))
        if today < anchor:
            return False
        every = int(conf.get("every_weeks", 1))
        return ((today - anchor).days // 7) % every == 0
    return True


def build_message(todays: list[LabSlot], portal: str = PORTAL) -> Message:
    lines = [f"• {sl.course}" + (f" · {sl.time.replace('-', '–')}" if sl.time else "") for sl in todays]
    title = "🧪 Σήμερα έχεις εργαστήριο" if len(todays) == 1 else f"🧪 Σήμερα έχεις {len(todays)} εργαστήρια"
    text = "\n".join(lines)
    body = f"<h2 style='font-size:18px'>{html.escape(title)}</h2><p>{html.escape(text).replace(chr(10), '<br>')}</p>"
    return Message(title, text, body, portal, ["test_tube"],
                   title, "Δες το πρόγραμμά σου στο eClass.", portal)


def run(cfg: Settings, dry_run: bool = False, dump: bool = False) -> int:
    now = datetime.now(cfg.tz)
    today = now.date()
    if now.hour >= cfg.labs_until_hour and not dry_run:
        # Το digest τρέχει πολλές φορές τη μέρα· η υπενθύμιση εργαστηρίου μόνο το πρωί
        log.info("Εργαστήρια: στέλνονται μόνο πριν τις %02d:00, παραλείπεται", cfg.labs_until_hour)
        return 0
    try:
        ec = EClass(cfg.eclass_username, cfg.eclass_password, base=cfg.eclass_url,
                    dump_dir=cfg.state_dir / "debug" if dump else None)
        ec.login()
        courses = ec.courses()
    except EClassError as e:
        log.error("Labs: %s", e)
        return 1

    slots: list[LabSlot] = []
    for code, title in courses.items():
        conf = cfg.labs_courses.get(code, {})
        if conf.get("ignore"):
            continue
        try:
            page = ec.groups_page(code).text if "weekday" not in conf else ""
        except Exception as e:
            log.warning("Ομάδες %s: %s", code, e)
            continue
        found = slots_for_course(code, title, page, conf)
        if dry_run:
            for sl in found:
                print(f"Εντόπισα: {sl.course} · {WEEKDAY_NAMES[sl.weekday]} {sl.time or ''} · ομάδα «{sl.group}»")
        slots.extend(found)
    log.info("Εντοπίστηκαν %d εργαστήρια", len(slots))

    todays = sorted((sl for sl in slots if is_today(sl, today, cfg.labs_courses.get(sl.code, {}))),
                    key=lambda x: x.time or "")
    if not todays:
        log.info("Κανένα εργαστήριο σήμερα (%s), δεν στέλνω τίποτα", WEEKDAY_NAMES[today.weekday()])
        return 0
    msg = build_message(todays, portal=cfg.portal_url)
    log.info("Εργαστήρια σήμερα: %d", len(todays))
    if dry_run:
        print(f"{msg.title}\n{msg.text}")
        return 0
    notify.summary(cfg, msg, send_email=cfg.labs_email)
    return 0
