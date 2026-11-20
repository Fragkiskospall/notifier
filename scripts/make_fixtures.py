"""Φτιάχνει ανωνυμοποιημένα fixtures για τα tests από σελίδες που αποθήκευσε το --dump-html.

    python scripts/make_fixtures.py state/debug tests/fixtures

Κρατά μόνο το κομμάτι της σελίδας που διαβάζουν οι parsers και αφαιρεί
ονόματα, links προφίλ, tokens και εικόνες.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

FRAGMENTS = {
    "work_": lambda s: s.find("table", id=re.compile("^assignment_table")) or s.find(class_=re.compile("alert")),
    "assignment_": lambda s: s.find(id="main"),
    "group_": lambda s: (s.find(class_=re.compile(r"row-cols")) or s.find("table", class_=re.compile("table-default"))),
    "portfolio": lambda s: s.find("table", id="portfolio_lessons"),
}


def scrub(soup_fragment) -> str:
    for el in soup_fragment.find_all(["img", "script", "style", "button", "svg"]):
        el.decompose()
    for a in soup_fragment.find_all("a", href=re.compile(r"display_profile|profile")):
        a.replace_with("ΟΝΟΜΑ ΧΡΗΣΤΗ")
    # ονόματα διδασκόντων/υπευθύνων
    for el in soup_fragment.find_all(class_=re.compile(r"vsmall-text")):
        el.string = "ΟΝΟΜΑ ΧΡΗΣΤΗ"
    for el in soup_fragment.find_all(class_=re.compile(r"small-text")):
        if el.get_text(strip=True).isupper():
            el.string = "ΟΝΟΜΑ ΧΡΗΣΤΗ"
    for el in soup_fragment.find_all(class_=re.compile(r"modal")):
        el.decompose()
    html = str(soup_fragment)
    html = re.sub(r"(token|uid)=[^&'\" ]+", r"\1=REDACTED", html)
    # «ICE1-7201 - ΟΝΟΜΑ ΔΙΔΑΣΚΟΝΤΑ» στην κεφαλίδα μαθήματος
    html = re.sub(r"([A-Z]{2,4}\d?-\d{3,5})\s*-\s*[^<]+", r"\1 - ΟΝΟΜΑ ΧΡΗΣΤΗ", html)
    html = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "user@example.com", html)
    html = re.sub(r"\n\s*\n+", "\n", html)
    return html


def main(src: str, dst: str) -> None:
    out = Path(dst)
    out.mkdir(parents=True, exist_ok=True)
    for f in sorted(Path(src).glob("*.html")):
        key = next((k for k in FRAGMENTS if f.name.startswith(k)), None)
        if key is None:
            continue
        soup = BeautifulSoup(f.read_text(encoding="utf-8"), "html.parser")
        frag = FRAGMENTS[key](soup)
        if frag is None:
            continue
        (out / f.name).write_text(scrub(frag), encoding="utf-8")
        print("✓", f.name)


if __name__ == "__main__":
    main(*sys.argv[1:3])
