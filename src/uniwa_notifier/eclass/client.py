"""HTTP client για το eClass: login, μαθήματα και λήψη σελίδων."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from . import parsers

BASE = "https://eclass.uniwa.gr"
USER_AGENT = "uniwa-notifier/2.0 (personal announcement watcher)"
TIMEOUT = 30

log = logging.getLogger(__name__)


class EClassError(RuntimeError):
    pass


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


class EClass:
    def __init__(self, username: str | None, password: str | None,
                 session: requests.Session | None = None, dump_dir: Path | None = None,
                 base: str = BASE):
        if not username or not password:
            raise EClassError("Λείπουν ECLASS_USERNAME/ECLASS_PASSWORD")
        self.username, self.password = username, password
        self.base = base.rstrip("/")
        self.s = session or new_session()
        self.dump_dir = dump_dir
        self._courses: dict[str, str] | None = None

    # -- low level
    def get(self, path_or_url: str, dump_as: str | None = None) -> requests.Response:
        url = path_or_url if path_or_url.startswith("http") else self.base + path_or_url
        r = self.s.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        if self.dump_dir and dump_as:
            self.dump_dir.mkdir(parents=True, exist_ok=True)
            (self.dump_dir / f"{dump_as}.html").write_text(r.text, encoding="utf-8")
        return r

    # -- session
    def login(self) -> None:
        self.s.get(f"{self.base}/main/login_form.php", timeout=TIMEOUT)  # cookies
        r = self.s.post(
            f"{self.base}/?login_page=1",
            data={"uname": self.username, "pass": self.password, "submit": "Είσοδος"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        if not parsers.is_logged_in(r.text):
            raise EClassError("Αποτυχία login στο eClass (λάθος στοιχεία;)")
        log.info("Login στο eClass OK")

    def courses(self) -> dict[str, str]:
        if self._courses is None:
            found: dict[str, str] = {}
            for page in ("/main/my_courses.php", "/main/portfolio.php"):
                try:
                    found = parsers.parse_courses(self.get(page).text)
                except requests.HTTPError:
                    continue
                if found:
                    break
            if not found:
                # Αν το login πέτυχε αλλά δεν βρίσκουμε κανένα μάθημα, κάτι άλλαξε στο eClass.
                raise EClassError("Δεν βρέθηκε κανένα μάθημα (άλλαξε η σελίδα του eClass;)")
            log.info("Βρέθηκαν %d μαθήματα στο eClass", len(found))
            self._courses = found
        return self._courses

    # -- pages
    def announcements_page(self, code: str) -> requests.Response:
        return self.get(f"/modules/announcements/index.php?course={code}", dump_as=f"announcements_{code}")

    def work_page(self, code: str) -> requests.Response:
        return self.get(f"/modules/work/index.php?course={code}", dump_as=f"work_{code}")

    def groups_page(self, code: str) -> requests.Response:
        return self.get(f"/modules/group/index.php?course={code}", dump_as=f"group_{code}")
