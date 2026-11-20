"""HTTP client: σύνδεση μέσω sso.uniwa.gr (CAS) και λήψη βαθμών."""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

from ..eclass.client import USER_AGENT
from ..models import Grade
from . import parsers

BASE = "https://services.uniwa.gr"
TIMEOUT = 30
log = logging.getLogger(__name__)


class ServicesError(RuntimeError):
    pass


class Services:
    def __init__(self, username: str | None, password: str | None, session: requests.Session | None = None,
                 profile: str | None = None):
        if not username or not password:
            raise ServicesError("Λείπουν ECLASS_USERNAME/ECLASS_PASSWORD (ίδια στοιχεία με το SSO)")
        self.username, self.password = username, password
        self.s = session or requests.Session()
        self.s.headers.setdefault("User-Agent", USER_AGENT)
        self.api_headers: dict[str, str] = {}
        self.profile = profile  # προαιρετικά: ΑΜ ή κωδικός τμήματος, αν έχεις πολλά προφίλ

    def login(self) -> None:
        # Η πύλη ανακατευθύνει στο sso.uniwa.gr/login?service=...
        r = self.s.get(BASE + "/", timeout=TIMEOUT)
        r.raise_for_status()
        if urlparse(r.url).hostname == urlparse(BASE).hostname:
            log.info("Ήδη συνδεδεμένος στην πύλη φοιτητολογίου")
            self._set_context(r.text, r.url)
            return
        try:
            action, hidden = parsers.parse_cas_form(r.text, r.url)
        except ValueError as e:
            raise ServicesError(str(e)) from e
        data = {**hidden, "username": self.username, "password": self.password}
        data.setdefault("_eventId", "submit")
        r = self.s.post(action, data=data, timeout=TIMEOUT)  # → services.uniwa.gr/login/cas?ticket=...
        r.raise_for_status()
        if urlparse(r.url).hostname != urlparse(BASE).hostname:
            raise ServicesError("Αποτυχία σύνδεσης στο SSO: " + (parsers.cas_error(r.text) or "άγνωστο σφάλμα"))
        self._set_context(r.text, r.url)
        log.info("Login στην πύλη φοιτητολογίου OK")

    def _set_context(self, page_html: str, page_url: str) -> None:
        ctx = parsers.portal_context(page_html, page_url)
        if "X-Profile" not in ctx:
            # Ο browser το παίρνει με JavaScript από το /api/person/profiles
            r = self.s.get(BASE + "/api/person/profiles", timeout=TIMEOUT,
                           headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest", **ctx})
            r.raise_for_status()
            try:
                profile = parsers.pick_profile(r.json(), self.profile)
            except ValueError:
                profile = None
            if not profile:
                raise ServicesError(f"Δεν βρέθηκε προφίλ φοιτητή μετά το login (σελίδα {urlparse(page_url).path})")
            ctx["X-Profile"] = profile
        # Ενεργοποίηση του προφίλ στη συνεδρία, όπως κάνει ο browser με το /?p=...
        r = self.s.get(f"{BASE}/?p={ctx['X-Profile']}", timeout=TIMEOUT)
        r.raise_for_status()
        fresh = parsers.portal_context(r.text, r.url)
        self.api_headers = {**ctx, **fresh}
        log.debug("Headers πύλης: %s", sorted(self.api_headers))

    def grades(self) -> list[Grade]:
        r = self.s.get(BASE + "/feign/student/grades/all", timeout=TIMEOUT,
                       headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
                                **self.api_headers})
        r.raise_for_status()
        if "json" not in r.headers.get("content-type", ""):
            m = re.search(r"<title>(.*?)</title>", r.text or "", re.S | re.I)
            raise ServicesError(f"Η πύλη δεν επέστρεψε JSON (HTTP {r.status_code}, {r.headers.get('content-type')}, "
                                f"σελίδα {urlparse(r.url).path}, τίτλος «{(m.group(1).strip() if m else '-')[:60]}»)")
        data = r.json()
        if not isinstance(data, list):
            raise ServicesError("Μη αναμενόμενη μορφή βαθμών (άλλαξε το API;)")
        return parsers.parse_grades(data)
