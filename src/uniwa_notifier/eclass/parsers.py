"""Καθαρές συναρτήσεις HTML → δεδομένα για το Open eClass του ΠΑΔΑ.

Δεν κάνουν δίκτυο, ώστε να ελέγχονται με tests πάνω σε πραγματικές σελίδες
(tests/fixtures). Αν αλλάξει το HTML του eClass, εδώ θα σπάσει και τα tests
θα το δείξουν.
"""
from __future__ import annotations

import re
from datetime import datetime, tzinfo
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Assignment, Group
from ..text import parse_dates, strip_accents

_COURSE_HREF = re.compile(r"/courses/([A-Za-z0-9_\-]+)/?$")


def parse_courses(page_html: str) -> dict[str, str]:
    """{course_code: τίτλος} από τη σελίδα «Τα μαθήματά μου» / portfolio."""
    courses: dict[str, str] = {}
    soup = BeautifulSoup(page_html, "html.parser")
    for a in soup.find_all("a", href=True):
        m = _COURSE_HREF.search(a["href"])
        if m:
            title = a.get_text(" ", strip=True)
            if title and len(title) > len(courses.get(m.group(1), "")):
                courses[m.group(1)] = title
    return courses


def is_logged_in(page_html: str) -> bool:
    return not ('name="pass"' in page_html and "logout" not in page_html)


def find_rss_link(page_html: str, page_url: str) -> str | None:
    soup = BeautifulSoup(page_html, "html.parser")
    href = next((a["href"] for a in soup.find_all("a", href=True) if "rss.php" in a["href"]), None)
    return urljoin(page_url, href) if href else None


def parse_announcement_links(page_html: str, page_url: str) -> list[tuple[str, str, str]]:
    """Fallback όταν δεν υπάρχει RSS: [(an_id, τίτλος, link)]."""
    soup = BeautifulSoup(page_html, "html.parser")
    out: dict[str, tuple[str, str, str]] = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"an_id=(\d+)", a["href"])
        text = a.get_text(" ", strip=True)
        if m and text:
            out.setdefault(m.group(1), (m.group(1), text[:200], urljoin(page_url, a["href"])))
    return list(out.values())


# ---------------------------------------------------------------- εργασίες

def _detect_submitted(cell) -> bool | None:
    for el in cell.find_all(["i", "span"]):
        label = (el.get("aria-label") or el.get("title") or "").strip()
        if label == "Ναι":
            return True
        if label == "Όχι":
            return False
    raw = str(cell).lower()
    if "fa-check" in raw:
        return True
    if "hourglass" in raw or "fa-xmark" in raw or "fa-times" in raw:
        return False
    return None


def parse_assignments(page_html: str, page_url: str, course: str, tz: tzinfo) -> list[Assignment]:
    """Ο πίνακας #assignment_table_* της σελίδας Εργασίες ενός μαθήματος."""
    soup = BeautifulSoup(page_html, "html.parser")
    table = soup.find("table", id=re.compile(r"^assignment_table"))
    if table is None:
        return []  # «Δεν υπάρχουν εργασίες» ή απενεργοποιημένο εργαλείο
    found: dict[str, Assignment] = {}
    for tr in (table.find("tbody") or table).find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        a = tds[0].find("a", href=True)
        if not a:
            continue
        m = re.search(r"[?&]id=(\d+)", a["href"])
        if not m or m.group(1) in found:
            continue
        dl_text = re.sub(r"\s+", " ", tds[1].get_text(" ", strip=True))
        dates = parse_dates(dl_text, tz)
        found[m.group(1)] = Assignment(
            course=course,
            title=a.get_text(" ", strip=True)[:200],
            link=urljoin(page_url, a["href"]),
            deadline=max(dates) if dates else None,
            submitted=_detect_submitted(tds[2]) if len(tds) > 2 else None,
            expired="έχει λήξει" in dl_text,
        )
    return list(found.values())


def has_assignment_table(page_html: str) -> bool:
    return 'id="assignment_table' in page_html or "id='assignment_table" in page_html


def parse_assignment_start(page_html: str, tz: tzinfo) -> datetime | None:
    """«Ημερομηνία Έναρξης» από τη σελίδα μιας εργασίας."""
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup.find_all(["header", "footer", "nav", "script", "style"]):
        tag.decompose()
    main = soup.find(id=re.compile(r"main|content", re.I)) or soup.body or soup
    text = main.get_text(" ", strip=True)
    m = re.search(r"Ημερομηνία\s+Έναρξης(.{0,80})", text)
    dates = parse_dates(m.group(1), tz) if m else []
    if not dates:
        dates = parse_dates(text, tz)
    return min(dates) if dates else None


# ---------------------------------------------------------------- ομάδες χρηστών

def parse_groups(page_html: str) -> list[Group]:
    """Οι ομάδες που φαίνονται στη σελίδα Ομάδες Χρηστών (κάρτες ή λίστα)."""
    soup = BeautifulSoup(page_html, "html.parser")
    out: list[Group] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=re.compile(r"group_space\.php")):
        href = a["href"]
        if "selfReg" in href:  # κουμπί «Εγγραφή», όχι όνομα ομάδας
            continue
        name = a.get_text(" ", strip=True)
        if not name or href in seen:
            continue
        seen.add(href)
        box = a.find_parent(class_=re.compile(r"card-header")) or a.find_parent("tr") or a.parent
        txt = strip_accents(box.get_text(" ", strip=True)) if box else ""
        out.append(Group(name=name, member="η ομαδα μου" in txt or "ειστε μελος" in txt))
    return out
