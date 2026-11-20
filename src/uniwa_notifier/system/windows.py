"""Windows: φάκελος στο %LOCALAPPDATA%, jobs στο Task Scheduler, toast ειδοποιήσεις.

Τα tasks ανήκουν στον χρήστη (χωρίς δικαιώματα διαχειριστή), είναι κρυφά και
τρέχουν με pythonw.exe ή το .exe χωρίς κονσόλα, οπότε δεν ανοίγει ποτέ παράθυρο.
Με το StartWhenAvailable, ένα job που χάθηκε επειδή ο υπολογιστής ήταν κλειστός
ή σε αναστολή τρέχει μόλις ανοίξει.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from xml.sax.saxutils import escape

from .base import APP_NAME, APP_VENDOR, Backend, Job, Runner, default_runner, launch_command

log = logging.getLogger(__name__)
TASK_FOLDER = "\\" + APP_VENDOR + "\\"
KNOWN_JOBS = ("check", "grades", "digest", "labs")


class WindowsBackend(Backend):
    name = "windows"

    def __init__(self, local_appdata: Path | None = None, runner: Runner | None = None,
                 today: dt.date | None = None) -> None:
        base = local_appdata or os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        self.local_appdata = Path(base)
        self.run = runner or default_runner
        self.today = today

    @property
    def app_dir(self) -> Path:
        return self.local_appdata / APP_VENDOR / APP_NAME

    def task_name(self, job_name: str) -> str:
        return f"{TASK_FOLDER}{APP_NAME} {job_name}"

    def _triggers(self, job: Job) -> str:
        day = (self.today or dt.date.today()).isoformat()
        if job.every_minutes is not None:
            return (
                "<TimeTrigger>"
                f"<Repetition><Interval>PT{job.every_minutes}M</Interval>"
                "<StopAtDurationEnd>false</StopAtDurationEnd></Repetition>"
                f"<StartBoundary>{day}T00:00:00</StartBoundary><Enabled>true</Enabled>"
                "</TimeTrigger>"
            )
        return "".join(
            "<CalendarTrigger>"
            f"<StartBoundary>{day}T{h:02d}:{m:02d}:00</StartBoundary><Enabled>true</Enabled>"
            "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
            "</CalendarTrigger>"
            for h, m in job.times()
        )

    def task_xml(self, job: Job, cmd: list[str]) -> str:
        exe, args = cmd[0], subprocess.list2cmdline(cmd[1:])
        return (
            '<?xml version="1.0" encoding="UTF-16"?>\n'
            '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
            "<RegistrationInfo>"
            f"<Author>{APP_VENDOR}</Author>"
            f"<Description>{escape(APP_NAME)}: {escape(job.name)}</Description>"
            "</RegistrationInfo>"
            f"<Triggers>{self._triggers(job)}</Triggers>"
            '<Principals><Principal id="Author">'
            "<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel>"
            "</Principal></Principals>"
            "<Settings>"
            "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
            "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
            "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
            "<StartWhenAvailable>true</StartWhenAvailable>"
            "<RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>"
            "<IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>"
            "<AllowStartOnDemand>true</AllowStartOnDemand>"
            "<Enabled>true</Enabled>"
            "<Hidden>true</Hidden>"
            "<ExecutionTimeLimit>PT10M</ExecutionTimeLimit>"
            "<Priority>7</Priority>"
            "</Settings>"
            '<Actions Context="Author"><Exec>'
            f"<Command>{escape(exe)}</Command>"
            f"<Arguments>{escape(args)}</Arguments>"
            f"<WorkingDirectory>{escape(str(self.app_dir))}</WorkingDirectory>"
            "</Exec></Actions>"
            "</Task>"
        )

    def install(self, jobs: Sequence[Job], command: Callable[[Sequence[str]], list[str]] = launch_command) -> list[str]:
        self.ensure_dirs()
        tasks_dir = self.app_dir / "tasks"
        tasks_dir.mkdir(exist_ok=True)
        installed = []
        for job in jobs:
            path = tasks_dir / f"{job.name}.xml"
            path.write_text(self.task_xml(job, command(job.args)), encoding="utf-16")
            r = self.run(["schtasks", "/Create", "/TN", self.task_name(job.name), "/XML", str(path), "/F"])
            if r.returncode != 0:
                raise RuntimeError(f"schtasks απέτυχε για {job.name}: {(r.stderr or r.stdout).strip()}")
            installed.append(job.name)
        return installed

    def uninstall(self) -> list[str]:
        removed = []
        for name in KNOWN_JOBS:
            if self.run(["schtasks", "/Delete", "/TN", self.task_name(name), "/F"]).returncode == 0:
                removed.append(name)
        return removed

    def status(self) -> dict[str, bool]:
        out = {}
        for name in KNOWN_JOBS:
            if self.run(["schtasks", "/Query", "/TN", self.task_name(name)]).returncode == 0:
                out[name] = True
        return out

    def notify(self, title: str, text: str, url: str | None = None) -> bool:
        try:
            from desktop_notifier import DesktopNotifierSync  # type: ignore
        except ImportError:
            log.debug("Το desktop-notifier δεν είναι εγκατεστημένο")
            return False
        try:
            notifier = DesktopNotifierSync(app_name=f"{APP_VENDOR} {APP_NAME}")
            kwargs = {}
            if url:
                import webbrowser

                kwargs["on_clicked"] = lambda: webbrowser.open(url)
            notifier.send(title=title[:60], message=text[:200], **kwargs)
            return True
        except Exception:
            log.debug("Αποτυχία toast ειδοποίησης", exc_info=True)
            return False
