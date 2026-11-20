import datetime as dt
import tomllib
from pathlib import Path

import pytest
import requests

from uniwa_notifier import config, runs, system
from uniwa_notifier.eclass.client import EClass, EClassError
from uniwa_notifier.launcher import setup


class FakeStore(setup.SecretStore):
    def __init__(self):
        self.data: dict[str, str] = {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def delete_all(self):
        keys = list(self.data)
        self.data.clear()
        return keys


class FakeBackend(system.Backend):
    name = "fake"

    def __init__(self, root: Path):
        self.root = root
        self.installed: list[system.Job] = []

    @property
    def app_dir(self):
        return self.root / "Notifier"

    def install(self, jobs, command=system.launch_command):
        self.installed = list(jobs)
        return [j.name for j in jobs]

    def uninstall(self):
        names = [j.name for j in self.installed]
        self.installed = []
        return names

    def status(self):
        return {j.name: True for j in self.installed}


def _choices(**over):
    c = setup.Choices(university="uniwa", username=" ice12345678 ", password="pw", department="ice")
    for k, v in over.items():
        setattr(c, k, v)
    return c


def test_topic_is_random_and_ntfy_safe():
    a, b = setup.new_topic(), setup.new_topic()
    assert a != b and a.startswith("fos-") and a.replace("-", "").isalnum() and len(a) >= 20
    assert setup.ntfy_subscribe_url(a) == f"https://ntfy.sh/{a}"


def test_render_config_has_no_secrets_and_loads(tmp_path, monkeypatch):
    c = _choices(password="SuperSecret!")
    text = setup.render_config(c, today=dt.date(2026, 11, 20))
    assert "SuperSecret" not in text and "ice12345678" not in text and c.ntfy_topic not in text
    raw = tomllib.loads(text)
    assert raw["university"] == {"id": "uniwa", "department": "ice"}
    assert raw["digest"]["since"] == dt.date(2026, 9, 1)  # αρχή ακαδημαϊκού έτους
    (tmp_path / "config.toml").write_text(text, encoding="utf-8")
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    cfg = config.load(tmp_path / "config.toml")
    assert cfg.eclass_url == "https://eclass.uniwa.gr"
    assert cfg.department_feed == "https://ice.uniwa.gr/feed/"
    assert cfg.grades_supported and cfg.notify_desktop


def test_config_for_other_university(tmp_path, monkeypatch):
    text = setup.render_config(_choices(university="uoa", department=None))
    (tmp_path / "config.toml").write_text(text, encoding="utf-8")
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    cfg = config.load(tmp_path / "config.toml")
    assert cfg.eclass_url == "https://eclass.uoa.gr"
    assert cfg.portal_url == "https://eclass.uoa.gr/main/portfolio.php"
    assert cfg.department_feed == ""
    assert not cfg.grades_supported


def test_unsupported_university_is_refused(tmp_path):
    (tmp_path / "config.toml").write_text('[university]\nid = "ntua"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="δεν υποστηρίζεται"):
        config.load(tmp_path / "config.toml")


def test_apply_writes_config_secrets_and_jobs(tmp_path):
    backend, store = FakeBackend(tmp_path), FakeStore()
    steps: list[str] = []
    c = _choices()
    installed = setup.apply(c, backend, store, progress=steps.append)
    assert installed == ["check", "grades", "digest", "labs"]
    assert (backend.app_dir / "config.toml").exists()
    assert store.data["ECLASS_USERNAME"] == "ice12345678"
    assert store.data["ECLASS_PASSWORD"] == "pw"
    assert store.data["NTFY_TOPIC"] == c.ntfy_topic
    assert len(store.data["STATE_KEY"]) == 44
    assert steps and setup.is_configured(backend)


def test_apply_keeps_existing_state_key(tmp_path):
    store = FakeStore()
    store.data["STATE_KEY"] = "existing"
    setup.apply(_choices(), FakeBackend(tmp_path), store)
    assert store.data["STATE_KEY"] == "existing"


def test_no_grades_job_where_unsupported_and_no_topic_without_mobile(tmp_path):
    backend, store = FakeBackend(tmp_path), FakeStore()
    assert setup.apply(_choices(university="uoa", department=None, notify_mobile=False), backend, store) == [
        "check", "digest", "labs"]
    assert "NTFY_TOPIC" not in store.data


def test_remove_everything_leaves_nothing(tmp_path):
    backend, store = FakeBackend(tmp_path), FakeStore()
    setup.apply(_choices(), backend, store)
    setup.remove_everything(backend, store)
    assert not backend.app_dir.exists()
    assert store.data == {}
    assert backend.installed == []


def test_status_reports_last_runs(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # στο CI είναι πάντα ορισμένο
    backend = FakeBackend(tmp_path)
    setup.apply(_choices(), backend, FakeStore())
    when = dt.datetime(2026, 11, 20, 11, 30, tzinfo=dt.UTC)
    runs.record(backend.app_dir / "logs", "check", True, now=when)
    st = {s.name: s for s in setup.status(backend)}
    assert st["check"].last_run == when and st["check"].last_ok is True
    assert st["digest"].last_run is None


def test_runs_not_recorded_in_github_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    runs.record(tmp_path, "check", True)
    assert not (tmp_path / runs.FILE).exists()


@pytest.mark.parametrize(
    "login, courses, ok, text",
    [
        (None, {"A": "a", "B": "b"}, True, "2 μαθήματα"),
        (EClassError("Αποτυχία login στο eClass (λάθος στοιχεία;)"), None, False, "Λάθος όνομα χρήστη"),
        (requests.ConnectionError(), None, False, "internet"),
    ],
)
def test_verify_login(monkeypatch, login, courses, ok, text):
    def fake_login(self):
        assert self.base == "https://eclass.uoa.gr"
        if login:
            raise login

    monkeypatch.setattr(EClass, "login", fake_login)
    monkeypatch.setattr(EClass, "courses", lambda self: courses)
    r = setup.verify_login("uoa", "user", "pw")
    assert r.ok is ok and text in r.message


def test_verify_login_rejects_empty_and_unsupported():
    assert not setup.verify_login("uniwa", "", "x").ok
    assert "δεν υποστηρίζεται" in setup.verify_login("ntua", "u", "p").message
