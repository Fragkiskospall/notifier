from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from uniwa_notifier import system

FIXTURES = Path(__file__).parent / "fixtures"
ATHENS = ZoneInfo("Europe/Athens")


@pytest.fixture
def tz():
    return ATHENS


@pytest.fixture
def fixture():
    def _read(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")
    return _read


@pytest.fixture(autouse=True)
def _silent_desktop(monkeypatch):
    """Τα tests δεν εμφανίζουν ποτέ πραγματικές ειδοποιήσεις υπολογιστή,
    ούτε αγγίζουν τα jobs του συστήματος (σε κανένα λειτουργικό)."""
    monkeypatch.setattr(system, "_current", system.LinuxBackend())
