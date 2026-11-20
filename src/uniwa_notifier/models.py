"""Δομές δεδομένων που μοιράζονται όλα τα modules."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Item:
    """Μία ανακοίνωση (τμήμα ή eClass)."""

    uid: str  # μοναδικό κλειδί για το state
    source: str  # π.χ. "Τμήμα ΜΠΥ" ή "eClass · ΦΥΣΙΚΗ"
    title: str
    link: str
    summary: str = ""


@dataclass
class Assignment:
    course: str
    title: str
    link: str
    deadline: datetime | None
    submitted: bool | None  # None = άγνωστο
    expired: bool = False
    start: datetime | None = None


@dataclass
class Group:
    name: str
    member: bool


@dataclass
class LabSlot:
    code: str
    course: str
    group: str
    weekday: int | None  # 0 = Δευτέρα
    time: str | None  # "16:00-17:00"


@dataclass
class Grade:
    """Μία προσπάθεια εξέτασης από την πύλη φοιτητολογίου."""

    id: str
    code: str
    title: str
    value: float | None  # κλίμακα 0-10
    passed: bool
    period: str
    modified: int  # epoch ms
