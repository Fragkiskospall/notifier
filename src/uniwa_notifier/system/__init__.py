"""Ό,τι εξαρτάται από το λειτουργικό: φάκελος εφαρμογής, αυτόματα jobs, ειδοποιήσεις.

Υπάρχουν δύο υλοποιήσεις με την ίδια διεπαφή, μία για Windows (Task Scheduler)
και μία για macOS (launchd). Η ``current()`` διαλέγει μόνη της τη σωστή, οπότε ο
χρήστης δεν βλέπει ποτέ τη διαφορά.

Σε Linux (π.χ. GitHub Actions) υπάρχει μόνο ο φάκελος· τα jobs τα κάνει το cloud.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .base import APP_NAME, APP_VENDOR, Backend, Job, UnsupportedPlatform, default_jobs, launch_command

__all__ = ["Backend", "Job", "UnsupportedPlatform", "current", "default_jobs", "launch_command"]


class LinuxBackend(Backend):
    """Χωρίς αυτόματα jobs: σε Linux το Notifier τρέχει από GitHub Actions ή cron."""

    name = "linux"

    @property
    def app_dir(self) -> Path:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        return Path(base) / APP_VENDOR.lower() / APP_NAME.lower()


def for_platform(platform: str) -> Backend:
    if platform == "darwin":
        from .macos import MacBackend

        return MacBackend()
    if platform == "win32":
        from .windows import WindowsBackend

        return WindowsBackend()
    return LinuxBackend()


_current: Backend | None = None


def current() -> Backend:
    global _current
    if _current is None:
        _current = for_platform(sys.platform)
    return _current
