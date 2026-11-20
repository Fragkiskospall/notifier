"""Κατάλογος πανεπιστημίων: ένα αρχείο TOML ανά ίδρυμα στο ``universities/``.

Κάθε αρχείο λέει πού βρίσκεται το eClass του ιδρύματος, πώς γίνεται η σύνδεση
και τι υποστηρίζουμε. Ο launcher τον διαβάζει για να γεμίσει τη λίστα
«Πού σπουδάζεις;» και για να ρυθμίσει μόνος του τις διευθύνσεις.

Επίπεδα υποστήριξης:
    full         ανακοινώσεις, εργασίες, εργαστήρια και βαθμοί (δοκιμασμένο)
    eclass       ανακοινώσεις και εργασίες, γιατί το Open eClass είναι ίδιο παντού
    unsupported  άλλη πλατφόρμα (π.χ. Moodle), δεν υποστηρίζεται ακόμα
"""

from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from urllib.parse import urlparse

SUPPORT_LEVELS = ("full", "eclass", "unsupported")
PLATFORMS = ("openeclass", "moodle", "other")
AUTH_MODES = ("form", "cas", "auto")

SUPPORT_LABELS = {
    "full": "Πλήρης υποστήριξη",
    "eclass": "Ανακοινώσεις και εργασίες",
    "unsupported": "Δεν υποστηρίζεται ακόμα",
}


class CatalogError(ValueError):
    """Λάθος σε αρχείο του καταλόγου."""


@dataclass(frozen=True)
class EClassInstance:
    url: str
    auth: str = "auto"
    department: str | None = None
    unverified: str | None = None


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    rss: str | None = None


@dataclass(frozen=True)
class Grades:
    portal: str
    adapter: str
    sso: str | None = None


@dataclass(frozen=True)
class University:
    id: str
    name: str
    short: str
    platform: str
    support: str
    verified: dt.date
    source: str
    eclass: EClassInstance | None = None
    extra_eclass: tuple[EClassInstance, ...] = ()
    lms_url: str | None = None
    grades: Grades | None = None
    departments: tuple[Department, ...] = field(default_factory=tuple)

    @property
    def support_label(self) -> str:
        return SUPPORT_LABELS[self.support]

    @property
    def is_supported(self) -> bool:
        return self.support != "unsupported"

    def department(self, dept_id: str) -> Department | None:
        return next((d for d in self.departments if d.id == dept_id), None)


def _https(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{where}: λείπει URL")
    p = urlparse(value)
    if p.scheme != "https" or not p.netloc:
        raise CatalogError(f"{where}: το URL πρέπει να είναι https:// ({value})")
    return value.rstrip("/") + ("/" if value.endswith("/") and p.path not in ("", "/") else "")


def _instance(raw: dict, where: str) -> EClassInstance:
    auth = raw.get("auth", "auto")
    if auth not in AUTH_MODES:
        raise CatalogError(f"{where}: άγνωστο auth '{auth}'")
    return EClassInstance(
        url=_https(raw.get("url"), where),
        auth=auth,
        department=raw.get("department"),
        unverified=raw.get("unverified"),
    )


def parse(raw: dict, origin: str = "<toml>") -> University:
    """Μετατρέπει ένα αρχείο του καταλόγου σε ``University``, με έλεγχο."""
    for key in ("id", "name", "short", "platform", "support", "verified", "source"):
        if key not in raw:
            raise CatalogError(f"{origin}: λείπει το πεδίο '{key}'")
    if raw["platform"] not in PLATFORMS:
        raise CatalogError(f"{origin}: άγνωστη πλατφόρμα '{raw['platform']}'")
    if raw["support"] not in SUPPORT_LEVELS:
        raise CatalogError(f"{origin}: άγνωστο επίπεδο υποστήριξης '{raw['support']}'")
    if not isinstance(raw["verified"], dt.date):
        raise CatalogError(f"{origin}: το 'verified' πρέπει να είναι ημερομηνία (π.χ. 2026-11-20)")

    eclass = extra = None
    if "eclass" in raw:
        ec = dict(raw["eclass"])
        extra = tuple(_instance(x, f"{origin} [eclass.extra]") for x in ec.pop("extra", []))
        eclass = _instance(ec, f"{origin} [eclass]")

    if raw["platform"] == "openeclass" and eclass is None:
        raise CatalogError(f"{origin}: Open eClass χωρίς ενότητα [eclass]")
    if raw["support"] != "unsupported" and raw["platform"] != "openeclass":
        raise CatalogError(f"{origin}: υποστηρίζουμε μόνο Open eClass προς το παρόν")

    grades = None
    if "grades" in raw:
        g = raw["grades"]
        grades = Grades(
            portal=_https(g.get("portal"), f"{origin} [grades]"),
            adapter=g.get("adapter", ""),
            sso=_https(g["sso"], f"{origin} [grades]") if "sso" in g else None,
        )
        if not grades.adapter:
            raise CatalogError(f"{origin}: [grades] χωρίς adapter")
    if raw["support"] == "full" and grades is None:
        raise CatalogError(f"{origin}: 'full' σημαίνει και βαθμούς, λείπει [grades]")

    departments = tuple(
        Department(
            id=d["id"],
            name=d["name"],
            rss=_https(d["rss"], f"{origin} [[departments]]") if "rss" in d else None,
        )
        for d in raw.get("departments", [])
    )

    lms = raw.get("lms", {}).get("url")
    return University(
        id=raw["id"],
        name=raw["name"],
        short=raw["short"],
        platform=raw["platform"],
        support=raw["support"],
        verified=raw["verified"],
        source=_https(raw["source"], f"{origin} source"),
        eclass=eclass,
        extra_eclass=extra or (),
        lms_url=_https(lms, f"{origin} [lms]") if lms else None,
        grades=grades,
        departments=departments,
    )


@cache
def load_all() -> tuple[University, ...]:
    """Όλα τα πανεπιστήμια: πρώτα τα υποστηριζόμενα, μετά αλφαβητικά."""
    folder = resources.files(__package__) / "universities"
    unis: list[University] = []
    for entry in folder.iterdir():
        if not entry.name.endswith(".toml"):
            continue
        uni = parse(tomllib.loads(entry.read_text(encoding="utf-8")), entry.name)
        if uni.id != entry.name.removesuffix(".toml"):
            raise CatalogError(f"{entry.name}: το id '{uni.id}' πρέπει να ταιριάζει με το όνομα αρχείου")
        unis.append(uni)
    order = {level: i for i, level in enumerate(SUPPORT_LEVELS)}
    unis.sort(key=lambda u: (order[u.support], u.name))
    return tuple(unis)


def get(uni_id: str) -> University:
    for u in load_all():
        if u.id == uni_id:
            return u
    raise KeyError(uni_id)
