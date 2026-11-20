"""Κοινά κομμάτια των backends: τα jobs και η εντολή που τα τρέχει."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

Runner = Callable[[list[str]], subprocess.CompletedProcess]
APP_VENDOR = "FragkiskOSource"
APP_NAME = "Notifier"
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class UnsupportedPlatform(RuntimeError):
    """Το λειτουργικό δεν υποστηρίζει αυτόματα jobs από την εφαρμογή."""


@dataclass(frozen=True)
class Job:
    """Μία αυτόματη εργασία: είτε κάθε Ν λεπτά, είτε σε συγκεκριμένες ώρες."""

    name: str
    args: tuple[str, ...]
    every_minutes: int | None = None
    at: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (self.every_minutes is None) == (not self.at):
            raise ValueError(f"{self.name}: όρισε ή every_minutes ή at, όχι και τα δύο")
        if self.every_minutes is not None and not 5 <= self.every_minutes <= 24 * 60:
            raise ValueError(f"{self.name}: το every_minutes πρέπει να είναι 5 έως 1440")
        for t in self.at:
            if not _HHMM.match(t):
                raise ValueError(f"{self.name}: λάθος ώρα '{t}' (μορφή ΩΩ:ΛΛ)")

    def times(self) -> list[tuple[int, int]]:
        return [(int(t[:2]), int(t[3:])) for t in self.at]


def default_jobs(every_minutes: int = 30, digest_at: Sequence[str] = ("08:00", "14:00", "21:00")) -> list[Job]:
    """Ίδιο πρόγραμμα με το cloud: έλεγχος και βαθμοί ανά Ν λεπτά, σύνοψη σε ώρες,
    εργαστήρια στην πρώτη πρωινή σύνοψη."""
    digest_at = tuple(sorted(digest_at))
    if not digest_at:
        raise ValueError("Χρειάζεται τουλάχιστον μία ώρα για τη σύνοψη")
    return [
        Job("check", ("check",), every_minutes=every_minutes),
        Job("grades", ("grades",), every_minutes=every_minutes),
        Job("digest", ("digest",), at=digest_at),
        Job("labs", ("labs",), at=(digest_at[0],)),
    ]


def launch_command(
    args: Sequence[str],
    executable: str | None = None,
    frozen: bool | None = None,
    windows: bool | None = None,
) -> list[str]:
    """Η εντολή που καλεί το job. Στο πακεταρισμένο app (.exe/.app) είναι το ίδιο
    το εκτελέσιμο. Αλλιώς ο Python interpreter, και στα Windows ο pythonw.exe
    ώστε να μην ανοίγει ποτέ παράθυρο κονσόλας."""
    exe = executable or sys.executable
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    windows = (os.name == "nt") if windows is None else windows
    if frozen:
        return [exe, *args]
    if windows:
        pythonw = Path(exe).with_name("pythonw.exe")
        if pythonw.name != Path(exe).name and (pythonw.exists() or executable is not None):
            exe = str(pythonw)
    return [exe, "-m", "uniwa_notifier", *args]


def default_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    kwargs: dict = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(cmd, **kwargs)


class Backend:
    """Ό,τι διαφέρει ανά λειτουργικό. Τα υπόλοιπα του Notifier είναι κοινά."""

    name = "base"

    @property
    def app_dir(self) -> Path:
        raise NotImplementedError

    def install(self, jobs: Sequence[Job], command: Callable[[Sequence[str]], list[str]] = launch_command) -> list[str]:
        raise UnsupportedPlatform(f"Αυτόματα jobs δεν υποστηρίζονται σε {self.name}")

    def uninstall(self) -> list[str]:
        return []

    def status(self) -> dict[str, bool]:
        return {}

    def notify(self, title: str, text: str, url: str | None = None) -> bool:
        """Ειδοποίηση στον υπολογιστή. Επιστρέφει False αν δεν εμφανίστηκε."""
        return False

    def ensure_dirs(self) -> Path:
        d = self.app_dir
        (d / "logs").mkdir(parents=True, exist_ok=True)
        (d / "state").mkdir(parents=True, exist_ok=True)
        return d
