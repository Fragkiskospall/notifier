"""Smoke test των οθονών του launcher (χωρίς οθόνη, Qt offscreen)."""
import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("segno")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from uniwa_notifier import system  # noqa: E402
from uniwa_notifier.launcher import setup  # noqa: E402


class FakeBackend(system.Backend):
    name = "macos"

    def __init__(self, root):
        self.root, self.jobs = root, []

    @property
    def app_dir(self):
        return self.root / "Notifier"

    def install(self, jobs, command=system.launch_command):
        self.jobs = list(jobs)
        return [j.name for j in jobs]

    def uninstall(self):
        self.jobs = []
        return []

    def status(self):
        return {j.name: True for j in self.jobs}


@pytest.fixture
def env(tmp_path, monkeypatch):
    backend = FakeBackend(tmp_path)
    monkeypatch.setattr(system, "_current", backend)
    saved: dict[str, str] = {}
    monkeypatch.setattr(setup.SecretStore, "set", lambda self, k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(setup.SecretStore, "get", lambda self, k: saved.get(k))
    monkeypatch.setattr(setup.SecretStore, "delete_all", lambda self: [saved.clear()])
    from uniwa_notifier.launcher import ui

    app = ui.build_app(["test"])
    return ui, app, backend, saved


def test_full_flow_from_wizard_to_dashboard(env):
    ui, app, backend, saved = env
    win = ui.MainWindow()
    wiz = win.current
    assert isinstance(wiz, ui.Wizard)

    wiz.root.setCurrentIndex(1)
    assert wiz.uni.university.id == "uniwa"  # τα υποστηριζόμενα πρώτα
    assert wiz.next.isEnabled()
    wiz._next()

    # Χωρίς επιτυχημένο έλεγχο σύνδεσης δεν προχωράει
    wiz.login.user.setText("ice12345678")
    wiz.login.pw.setText("pw")
    assert not wiz.next.isEnabled()
    wiz.login._show(wiz.login._key(), setup.LoginResult(True, "ok", 3))
    assert wiz.next.isEnabled()
    wiz._next()

    wiz._next()  # ειδοποιήσεις
    assert not wiz.next.isEnabled()  # χρειάζεται συναίνεση
    wiz.run_page.consent.setChecked(True)
    assert wiz.next.isEnabled()
    wiz.run_page.times.setText("8 το πρωί")
    assert not wiz.next.isEnabled()
    wiz.run_page.times.setText("08:00, 21:00")

    choices = wiz.choices()
    assert choices.digest_at == ("08:00", "21:00")
    setup.apply(choices, backend)
    assert saved["ECLASS_USERNAME"] == "ice12345678"
    assert [j.name for j in backend.jobs] == ["check", "grades", "digest", "labs"]

    win.show_dashboard()
    assert isinstance(win.current, ui.Dashboard)
    win.current.status.refresh()
    assert "λειτουργούν" in win.current.status.headline.text()


def test_unsupported_university_blocks_continue(env):
    ui, _app, _backend, _saved = env
    page = ui.UniversityPage()
    ntua = next(i for i in range(page.uni.count()) if page.uni.itemData(i) == "ntua")
    page.uni.setCurrentIndex(ntua)
    assert not page.can_continue()


def test_opens_dashboard_when_already_configured(env):
    ui, _app, backend, _saved = env
    setup.apply(setup.Choices(university="uoa", username="u", password="p"), backend)
    win = ui.MainWindow()
    assert isinstance(win.current, ui.Dashboard)
    assert win.current.status.stats[2][0].text() == "ΕΚΠΑ"
