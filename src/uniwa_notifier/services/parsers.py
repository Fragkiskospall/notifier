"""Καθαρές συναρτήσεις για το SSO (CAS) και το JSON των βαθμών."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import Grade


def parse_cas_form(page_html: str, page_url: str) -> tuple[str, dict[str, str]]:
    """(action URL, κρυφά πεδία) της φόρμας σύνδεσης του sso.uniwa.gr."""
    soup = BeautifulSoup(page_html, "html.parser")
    form = soup.find("form", attrs={"method": lambda m: (m or "").lower() == "post"}) or soup.find("form")
    if form is None or not form.find("input", attrs={"name": "password"}):
        raise ValueError("Δεν βρέθηκε η φόρμα σύνδεσης του SSO")
    hidden = {i["name"]: i.get("value", "") for i in form.find_all("input", type="hidden") if i.get("name")}
    return urljoin(page_url, form.get("action") or page_url), hidden


def cas_error(page_html: str) -> str | None:
    """Το μήνυμα λάθους του SSO (π.χ. λάθος κωδικός), αν υπάρχει."""
    soup = BeautifulSoup(page_html, "html.parser")
    el = soup.find(id="msg") or soup.find(class_="errors") or soup.find(class_="alert-danger")
    return el.get_text(" ", strip=True) if el else None


def portal_context(page_html: str, page_url: str) -> dict[str, str]:
    """Headers που στέλνει η ίδια η πύλη σε κάθε κλήση API (βλ. custom.js της ILYDA):
    X-Profile = η παράμετρος p του URL, και το CSRF token του Spring Security."""
    headers: dict[str, str] = {}
    profile = (parse_qs(urlparse(page_url).query).get("p") or [None])[0]
    if not profile:
        m = re.search(r"[?&](?:amp;)?p=([0-9A-Fa-f]{16,})", page_html)
        profile = m.group(1) if m else None
    if profile:
        headers["X-Profile"] = profile
    soup = BeautifulSoup(page_html, "html.parser")
    token = soup.find("meta", attrs={"name": "_csrf"})
    header = soup.find("meta", attrs={"name": "_csrf_header"})
    if token and header and token.get("content") and header.get("content"):
        headers[header["content"]] = token["content"]
    return headers


def pick_profile(data: dict | list, prefer: str | None = None) -> str | None:
    """Διαλέγει προφίλ φοιτητή από το /api/person/profiles.

    prefer: αριθμός μητρώου ή κωδικός τμήματος, αν υπάρχουν πολλά προφίλ.
    Αλλιώς προτιμά ενεργό φοιτητή (studentStatusId == "1"), μετά το πρώτο.
    """
    profiles = data.get("studentProfiles", []) if isinstance(data, dict) else list(data or [])
    profiles = [p for p in profiles if isinstance(p, dict) and p.get("id")]
    if not profiles:
        return None
    if prefer:
        for p in profiles:
            if prefer in (str(p.get("studentNo")), str(p.get("departmentCode")), str(p.get("academicId"))):
                return str(p["id"])
    active = [p for p in profiles if str(p.get("studentStatusId")) == "1"]
    return str((active or profiles)[0]["id"])


def _flag(v) -> bool:
    return str(v).lower() == "true"


def _value(raw, base) -> float | None:
    """Η πύλη δίνει τους βαθμούς σε κλίμακα 0-1 όταν η βάση είναι 0.5 (0.35 → 3.5)."""
    if raw in (None, ""):
        return None
    try:
        v = float(str(raw).replace(",", "."))
        b = float(str(base).replace(",", ".")) if base not in (None, "") else 5.0
    except ValueError:
        return None
    return round(v * 10, 2) if b < 1 else v


def parse_grades(data: list[dict]) -> list[Grade]:
    out = []
    for r in data:
        if not r.get("id"):
            continue
        exam = r.get("examPeriodId") or {}
        out.append(Grade(
            id=str(r["id"]),
            code=str(r.get("courseCode") or ""),
            title=str(r.get("title") or (r.get("courseId") or {}).get("title") or "").strip(),
            value=_value(r.get("grade"), r.get("baseGrade")),
            passed=_flag(r.get("isPassed")),
            period=str(exam.get("title") or r.get("periodTitle") or "").strip(),
            modified=int(r.get("dateModified") or r.get("dateAdded") or 0),
        ))
    return out


def fmt_value(v: float | None) -> str:
    if v is None:
        return "-"
    return (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", ",")
