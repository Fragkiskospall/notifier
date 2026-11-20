import datetime as dt
import plistlib
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from uniwa_notifier import notify, system
from uniwa_notifier.models import Item
from uniwa_notifier.system import Job, default_jobs, launch_command
from uniwa_notifier.system.macos import LABEL_PREFIX, MacBackend
from uniwa_notifier.system.windows import WindowsBackend

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


class FakeRunner:
    def __init__(self, fail=()):
        self.calls: list[list[str]] = []
        self.fail = set(fail)

    def __call__(self, cmd):
        self.calls.append(cmd)
        rc = 1 if any(f in " ".join(cmd) for f in self.fail) else 0
        return subprocess.CompletedProcess(cmd, rc, "", "boom" if rc else "")


# --- επιλογή backend -------------------------------------------------------

@pytest.mark.parametrize("plat, name", [("darwin", "macos"), ("win32", "windows"), ("linux", "linux")])
def test_backend_is_chosen_automatically(plat, name, monkeypatch):
    if plat == "darwin":
        monkeypatch.setattr("os.getuid", lambda: 501, raising=False)
    assert system.for_platform(plat).name == name


def test_linux_has_no_scheduler():
    with pytest.raises(system.UnsupportedPlatform):
        system.LinuxBackend().install(default_jobs())


# --- jobs --------------------------------------------------------------------

def test_default_jobs_match_cloud_schedule():
    jobs = {j.name: j for j in default_jobs()}
    assert jobs["check"].every_minutes == 30
    assert jobs["grades"].every_minutes == 30
    assert jobs["digest"].at == ("08:00", "14:00", "21:00")
    assert jobs["labs"].at == ("08:00",)


@pytest.mark.parametrize("kwargs", [{}, {"every_minutes": 30, "at": ("08:00",)}, {"every_minutes": 1}, {"at": ("25:00",)}])
def test_invalid_jobs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Job("x", ("x",), **kwargs)


def test_launch_command_frozen_app_calls_itself():
    assert launch_command(["check"], executable="/Applications/Notifier.app/Contents/MacOS/Notifier", frozen=True) == [
        "/Applications/Notifier.app/Contents/MacOS/Notifier", "check"]


def test_launch_command_windows_uses_pythonw_so_no_console_opens():
    cmd = launch_command(["digest"], executable=r"C:\Py\python.exe", frozen=False, windows=True)
    assert Path(cmd[0]).name == "pythonw.exe"
    assert cmd[1:] == ["-m", "uniwa_notifier", "digest"]


def test_launch_command_mac_uses_python_module():
    cmd = launch_command(["check"], executable="/opt/app/bin/python3", frozen=False, windows=False)
    assert cmd == ["/opt/app/bin/python3", "-m", "uniwa_notifier", "check"]


# --- macOS ------------------------------------------------------------------

def _mac(tmp_path, runner=None):
    return MacBackend(home=tmp_path, runner=runner or FakeRunner(), uid=501)


def _cmd(args):
    return ["/Applications/Notifier.app/Contents/MacOS/Notifier", *args]


def test_mac_app_dir(tmp_path):
    assert _mac(tmp_path).app_dir == tmp_path / "Library/Application Support/FragkiskOSource/Notifier"


def test_mac_plist_interval_job_runs_in_background(tmp_path):
    mac = _mac(tmp_path)
    p = mac.plist(Job("check", ("check",), every_minutes=30), _cmd(["check"]))
    assert p["StartInterval"] == 1800
    assert p["RunAtLoad"] is True
    assert p["ProcessType"] == "Background"
    assert p["WorkingDirectory"] == str(mac.app_dir)
    assert p["EnvironmentVariables"]["UNIWA_HOME"] == str(mac.app_dir)


def test_mac_plist_calendar_job(tmp_path):
    p = _mac(tmp_path).plist(Job("digest", ("digest",), at=("08:00", "21:30")), _cmd(["digest"]))
    assert p["StartCalendarInterval"] == [{"Hour": 8, "Minute": 0}, {"Hour": 21, "Minute": 30}]
    assert "StartInterval" not in p


def test_mac_install_writes_agents_and_bootstraps(tmp_path):
    runner = FakeRunner()
    mac = _mac(tmp_path, runner)
    assert mac.install(default_jobs(), command=_cmd) == ["check", "grades", "digest", "labs"]
    plists = sorted(p.name for p in (tmp_path / "Library/LaunchAgents").iterdir())
    assert plists == sorted(f"{LABEL_PREFIX}{n}.plist" for n in ("check", "grades", "digest", "labs"))
    data = plistlib.loads((tmp_path / f"Library/LaunchAgents/{LABEL_PREFIX}check.plist").read_bytes())
    assert data["ProgramArguments"] == _cmd(["check"])
    assert ["launchctl", "bootout", "gui/501/gr.uniwa.notifier"] in runner.calls  # παλιά εγκατάσταση
    assert sum(c[:2] == ["launchctl", "bootstrap"] for c in runner.calls) == 4


def test_mac_refuses_executable_in_protected_folder(tmp_path):
    mac = _mac(tmp_path)
    bad = lambda args: [str(tmp_path / "Desktop/proj/.venv/bin/python"), "-m", "uniwa_notifier", *args]  # noqa: E731
    with pytest.raises(RuntimeError, match="Desktop"):
        mac.install(default_jobs(), command=bad)


def test_mac_install_reports_launchctl_failure(tmp_path):
    with pytest.raises(RuntimeError, match="bootstrap"):
        _mac(tmp_path, FakeRunner(fail=["bootstrap"])).install(default_jobs(), command=_cmd)


def test_mac_uninstall_and_status(tmp_path):
    runner = FakeRunner()
    mac = _mac(tmp_path, runner)
    mac.install(default_jobs(), command=_cmd)
    assert mac.status() == {"check": True, "digest": True, "grades": True, "labs": True}
    assert sorted(mac.uninstall()) == ["check", "digest", "grades", "labs"]
    assert not list((tmp_path / "Library/LaunchAgents").glob(f"{LABEL_PREFIX}*"))


# --- Windows ----------------------------------------------------------------

def _win(tmp_path, runner=None):
    return WindowsBackend(local_appdata=tmp_path, runner=runner or FakeRunner(), today=dt.date(2026, 11, 20))


EXE = r"C:\Program Files\FragkiskOSource\Notifier.exe"


def test_windows_app_dir(tmp_path):
    assert _win(tmp_path).app_dir == tmp_path / "FragkiskOSource" / "Notifier"


def _parse(xml: str):
    return ET.fromstring(xml.split("\n", 1)[1])


def test_windows_task_is_hidden_and_catches_up_after_sleep(tmp_path):
    win = _win(tmp_path)
    root = _parse(win.task_xml(Job("check", ("check",), every_minutes=30), [EXE, "check"]))
    s = root.find("t:Settings", NS)
    assert s.find("t:Hidden", NS).text == "true"
    assert s.find("t:StartWhenAvailable", NS).text == "true"
    assert s.find("t:DisallowStartIfOnBatteries", NS).text == "false"
    assert s.find("t:MultipleInstancesPolicy", NS).text == "IgnoreNew"
    assert root.find(".//t:RunLevel", NS).text == "LeastPrivilege"
    trig = root.find("t:Triggers/t:TimeTrigger", NS)
    assert trig.find("t:Repetition/t:Interval", NS).text == "PT30M"
    assert trig.find("t:StartBoundary", NS).text == "2026-11-20T00:00:00"


def test_windows_task_daily_times_and_action(tmp_path):
    win = _win(tmp_path)
    root = _parse(win.task_xml(Job("digest", ("digest",), at=("08:00", "14:00", "21:00")), [EXE, "digest"]))
    starts = [t.find("t:StartBoundary", NS).text for t in root.findall("t:Triggers/t:CalendarTrigger", NS)]
    assert starts == ["2026-11-20T08:00:00", "2026-11-20T14:00:00", "2026-11-20T21:00:00"]
    ex = root.find("t:Actions/t:Exec", NS)
    assert ex.find("t:Command", NS).text == EXE
    assert ex.find("t:Arguments", NS).text == "digest"
    assert ex.find("t:WorkingDirectory", NS).text == str(win.app_dir)


def test_windows_install_uses_schtasks_with_xml(tmp_path):
    runner = FakeRunner()
    win = _win(tmp_path, runner)
    assert win.install(default_jobs(), command=lambda a: [EXE, *a]) == ["check", "grades", "digest", "labs"]
    creates = [c for c in runner.calls if c[:2] == ["schtasks", "/Create"]]
    assert [c[3] for c in creates] == [r"\FragkiskOSource\Notifier " + n for n in ("check", "grades", "digest", "labs")]
    xml_path = Path(creates[0][5])
    assert xml_path.read_text(encoding="utf-16").startswith('<?xml version="1.0" encoding="UTF-16"?>')
    assert all(c[-1] == "/F" for c in creates)


def test_windows_install_reports_failure(tmp_path):
    with pytest.raises(RuntimeError, match="schtasks"):
        _win(tmp_path, FakeRunner(fail=["/Create"])).install(default_jobs(), command=lambda a: [EXE, *a])


def test_windows_uninstall_and_status(tmp_path):
    runner = FakeRunner(fail=["Notifier labs"])
    win = _win(tmp_path, runner)
    assert win.status() == {"check": True, "grades": True, "digest": True}
    assert win.uninstall() == ["check", "grades", "digest"]


# --- ειδοποιήσεις μέσω backend -----------------------------------------------

class SpyBackend(system.Backend):
    name = "spy"

    def __init__(self):
        self.sent = []

    @property
    def app_dir(self):
        return Path("/tmp/spy")

    def notify(self, title, text, url=None):
        self.sent.append((title, text, url))
        return True


def test_desktop_notifications_go_through_current_backend(monkeypatch):
    spy = SpyBackend()
    monkeypatch.setattr(system, "current", lambda: spy)
    notify._desktop(Item("x", "ΨΕΣ", "Νέα ανακοίνωση", "https://eclass.uniwa.gr/x"))
    assert spy.sent == [("ΨΕΣ", "Νέα ανακοίνωση", "https://eclass.uniwa.gr/x")]
