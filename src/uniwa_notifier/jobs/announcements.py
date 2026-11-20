"""Job: νέες ανακοινώσεις από το site του τμήματος και τα μαθήματα του eClass."""
from __future__ import annotations

import logging
import re

import requests

from .. import notify
from ..config import Settings
from ..eclass import EClass, EClassError, new_session, parsers
from ..feeds import parse_feed
from ..models import Item
from ..state import StoreScope

log = logging.getLogger(__name__)
TIMEOUT = 30


def fetch_department(cfg: Settings, s: requests.Session) -> dict[str, list[Item]]:
    r = s.get(cfg.department_feed, timeout=TIMEOUT)
    r.raise_for_status()
    return {"dept": parse_feed(r.content, cfg.department_name, "dept")}


def course_items(ec: EClass, code: str, title: str) -> list[Item]:
    source = f"eClass · {title}"
    page = ec.announcements_page(code)
    rss = parsers.find_rss_link(page.text, page.url)
    if rss:
        fr = ec.s.get(rss, timeout=TIMEOUT)
        if fr.ok and b"<rss" in fr.content[:2000]:
            items = parse_feed(fr.content, source, f"eclass:{code}")
            for it in items:  # σταθερό uid από το an_id
                m = re.search(r"an_id=(\d+)", it.link)
                if m:
                    it.uid = f"eclass:{code}:{m.group(1)}"
            return items
    return [Item(uid=f"eclass:{code}:{an_id}", source=source, title=t, link=link)
            for an_id, t, link in parsers.parse_announcement_links(page.text, page.url)]


def fetch_eclass(cfg: Settings, s: requests.Session) -> dict[str, list[Item]]:
    ec = EClass(cfg.eclass_username, cfg.eclass_password, base=cfg.eclass_url, session=s)
    ec.login()
    out: dict[str, list[Item]] = {}
    for code, title in ec.courses().items():
        try:
            out[f"eclass:{code}"] = course_items(ec, code, title)
        except Exception as e:  # ένα μάθημα δεν ρίχνει όλο το run
            log.warning("Μάθημα %s: %s", code, e)
    if cfg.include_eclass_system:
        r = s.get(f"{cfg.eclass_url}/rss.php", timeout=TIMEOUT)
        if r.ok:
            out["eclass:system"] = parse_feed(r.content, "eClass · Πλατφόρμα", "eclass:system")
    return out


def run(cfg: Settings, dry_run: bool = False) -> int:
    with StoreScope() as stores:
        return _run(cfg, dry_run, stores)


def _run(cfg: Settings, dry_run: bool, stores: StoreScope) -> int:
    store = stores.open(cfg.seen_db)
    s = new_session()
    collected: dict[str, list[Item]] = {}
    errors = 0
    sources = (("τμήμα", fetch_department), ("eClass", fetch_eclass)) if cfg.department_feed else (("eClass", fetch_eclass),)
    for name, fetch in sources:
        try:
            collected.update(fetch(cfg, s))
        except (requests.RequestException, EClassError) as e:
            errors += 1
            log.error("%s: %s", name, e)

    new_items, first_seen = store.diff(collected, record=not dry_run)
    if first_seen:
        log.info("Πρώτη φορά για %d πηγές: καταγράφονται χωρίς ειδοποίηση", len(first_seen))

    if not new_items:
        log.info("Τίποτα καινούργιο")
        store.commit()
        return 1 if errors else 0

    # Στα logs μόνο πλήθος (τα logs του Actions κρατιούνται)
    log.info("%d νέες ανακοινώσεις", len(new_items))
    if dry_run:
        for it in new_items:
            print(f"  [{it.source}] {it.title}")
        return 0
    try:
        notify.announcements(cfg, new_items)
    except Exception as e:
        # Δεν κάνουμε commit, ώστε να ξαναδοκιμάσει στο επόμενο run
        log.error("Αποτυχία αποστολής: %s", e)
        store.rollback()
        return 1
    store.commit()
    return 1 if errors else 0
