"""macOS: φάκελος στο Application Support, jobs με launchd, ειδοποιήσεις συστήματος.

Το launchd τρέχει τα jobs ως LaunchAgents του χρήστη (χωρίς κωδικό διαχειριστή).
Αν ο Mac κοιμόταν την ώρα ενός job, το launchd το τρέχει μόλις ξυπνήσει.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from .base import APP_NAME, APP_VENDOR, Backend, Job, Runner, default_runner, launch_command

LABEL_PREFIX = "gr.fragkiskosource.notifier."
LEGACY_LABELS = ("gr.uniwa.notifier",)
PROTECTED = ("Desktop", "Documents", "Downloads")


class MacBackend(Backend):
    name = "macos"

    def __init__(self, home: Path | None = None, runner: Runner | None = None, uid: int | None = None) -> None:
        self.home = Path(home or Path.home())
        self.run = runner or default_runner
        self.uid = os.getuid() if uid is None else uid

    @property
    def app_dir(self) -> Path:
        return self.home / "Library" / "Application Support" / APP_VENDOR / APP_NAME

    @property
    def agents_dir(self) -> Path:
        return self.home / "Library" / "LaunchAgents"

    def label(self, job: Job) -> str:
        return LABEL_PREFIX + job.name

    def plist(self, job: Job, cmd: list[str]) -> dict:
        log = str(self.app_dir / "logs" / f"{job.name}.log")
        d: dict = {
            "Label": self.label(job),
            "ProgramArguments": cmd,
            "WorkingDirectory": str(self.app_dir),
            "ProcessType": "Background",
            "LowPriorityIO": True,
            "StandardOutPath": log,
            "StandardErrorPath": log,
            "EnvironmentVariables": {
                "UNIWA_HOME": str(self.app_dir),
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            },
        }
        if job.every_minutes is not None:
            d["StartInterval"] = job.every_minutes * 60
            d["RunAtLoad"] = True
        else:
            d["StartCalendarInterval"] = [{"Hour": h, "Minute": m} for h, m in job.times()]
        return d

    def check_executable(self, cmd: list[str]) -> None:
        """Το macOS δεν αφήνει διεργασίες παρασκηνίου να διαβάζουν Desktop/Documents/Downloads."""
        exe = Path(cmd[0])
        for folder in PROTECTED:
            if self.home / folder in exe.parents:
                raise RuntimeError(
                    f"Το εκτελέσιμο είναι μέσα στο ~/{folder}, όπου το macOS μπλοκάρει τα jobs παρασκηνίου. "
                    "Εγκατέστησε την εφαρμογή στο /Applications ή το venv εκτός αυτών των φακέλων."
                )

    def _target(self, label: str) -> str:
        return f"gui/{self.uid}/{label}"

    def install(self, jobs: Sequence[Job], command: Callable[[Sequence[str]], list[str]] = launch_command) -> list[str]:
        self.ensure_dirs()
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        for label in LEGACY_LABELS:  # η παλιά εγκατάσταση με το shell script
            self.run(["launchctl", "bootout", self._target(label)])
            (self.agents_dir / f"{label}.plist").unlink(missing_ok=True)
        installed = []
        for job in jobs:
            cmd = command(job.args)
            self.check_executable(cmd)
            path = self.agents_dir / f"{self.label(job)}.plist"
            path.write_bytes(plistlib.dumps(self.plist(job, cmd)))
            self.run(["launchctl", "bootout", self._target(self.label(job))])
            r = self.run(["launchctl", "bootstrap", f"gui/{self.uid}", str(path)])
            if r.returncode != 0:
                raise RuntimeError(f"launchctl bootstrap απέτυχε για {job.name}: {r.stderr.strip()}")
            installed.append(job.name)
        return installed

    def _ours(self) -> list[Path]:
        if not self.agents_dir.exists():
            return []
        return sorted(self.agents_dir.glob(f"{LABEL_PREFIX}*.plist"))

    def uninstall(self) -> list[str]:
        removed = []
        for path in self._ours():
            label = path.stem
            self.run(["launchctl", "bootout", self._target(label)])
            path.unlink(missing_ok=True)
            removed.append(label.removeprefix(LABEL_PREFIX))
        return removed

    def status(self) -> dict[str, bool]:
        out = {}
        for path in self._ours():
            label = path.stem
            out[label.removeprefix(LABEL_PREFIX)] = self.run(["launchctl", "print", self._target(label)]).returncode == 0
        return out

    def notify(self, title: str, text: str, url: str | None = None) -> bool:
        title, text = title[:60], text[:200]
        tn = shutil.which("terminal-notifier") or "/opt/homebrew/bin/terminal-notifier"
        if Path(tn).exists():
            cmd = [tn, "-title", title, "-message", text, "-sound", "default", "-group", "fragkiskosource"]
            if url:
                cmd += ["-open", url]
            return self.run(cmd).returncode == 0
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
        script = f'display notification "{esc(text)}" with title "{esc(title)}" sound name "default"'
        try:
            return self.run(["osascript", "-e", script]).returncode == 0
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
