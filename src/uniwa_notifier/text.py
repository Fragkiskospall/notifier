"""Καθαρισμός κειμένου και ανάγνωση ελληνικών ημερομηνιών/ημερών/ωρών."""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, tzinfo

from bs4 import BeautifulSoup

GREEK_DAYS_SHORT = ["Δευ", "Τρι", "Τετ", "Πεμ", "Παρ", "Σαβ", "Κυρ"]
WEEKDAY_NAMES = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]

# πρώτα 4 γράμματα της γενικής, χωρίς τόνους
_MONTHS = {"ιανο": 1, "φεβρ": 2, "μαρτ": 3, "απρι": 4, "μαιο": 5, "μαι": 5, "ιουν": 6,
           "ιουλ": 7, "αυγο": 8, "σεπτ": 9, "οκτω": 10, "νοεμ": 11, "δεκε": 12}
_WEEKDAY_PREFIXES = {"δευτερ": 0, "τριτη": 1, "τεταρτ": 2, "πεμπτ": 3, "παρασκ": 4, "σαββατ": 5, "κυριακ": 6}
_WEEKDAY_ABBR = {"δευ": 0, "τρι": 1, "τετ": 2, "πεμ": 3, "παρ": 4, "σαβ": 5, "κυρ": 6}

_GREEK_DATE_RE = re.compile(
    r"(\d{1,2})\s+([^\W\d_]+)\s+(\d{4})(?:\s*[-,]?\s*(\d{1,2}):(\d{2})\s*(π\.?\s?μ\.?|μ\.?\s?μ\.?)?)?"
)
_NUM_DATE_RE = re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:\D{1,12}?(\d{1,2}):(\d{2}))?")
_TIME_RANGE_RE = re.compile(r"(\d{1,2})[.:](\d{2})\s*[-–~]\s*(\d{1,2})[.:](\d{2})")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()


def clean_text(raw: str, limit: int = 500) -> str:
    text = BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    # Το WordPress προσθέτει "The post ... first appeared on ..." στο τέλος
    text = re.sub(r"The post .* first appeared on .*$", "", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def parse_dates(text: str, tz: tzinfo) -> list[datetime]:
    """Βρίσκει ημερομηνίες τύπου «Δευτέρα 26 Οκτωβρίου 2026 - 8:55 π.μ.» ή «20/11/2026 18:00»."""
    out: list[datetime] = []
    for d, mon, y, hh, mm, ampm in _GREEK_DATE_RE.findall(text):
        key = strip_accents(mon)
        month = _MONTHS.get(key[:4]) or _MONTHS.get(key[:3])
        if not month:
            continue
        h, m = (int(hh), int(mm)) if hh else (23, 59)
        if ampm:
            pm = strip_accents(ampm).replace(".", "").replace(" ", "") == "μμ"
            h = (h % 12) + (12 if pm else 0)
        try:
            out.append(datetime(int(y), month, int(d), h, m, tzinfo=tz))
        except ValueError:
            pass
    if out:
        return out
    for d, mo, y, hh, mm in _NUM_DATE_RE.findall(text):
        try:
            out.append(datetime(int(y), int(mo), int(d), int(hh or 23), int(mm or 59), tzinfo=tz))
        except ValueError:
            pass
    return out


def find_weekday(text: str) -> int | None:
    for word in re.findall(r"[^\W\d_]+", strip_accents(text)):
        if word in _WEEKDAY_ABBR:
            return _WEEKDAY_ABBR[word]
        for prefix, wd in _WEEKDAY_PREFIXES.items():
            if word.startswith(prefix):
                return wd
    return None


def find_time(text: str) -> str | None:
    m = _TIME_RANGE_RE.search(text)
    return f"{int(m[1]):02d}:{m[2]}-{int(m[3]):02d}:{m[4]}" if m else None
