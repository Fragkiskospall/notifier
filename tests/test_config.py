from datetime import date
from pathlib import Path

from uniwa_notifier import config

REPO_CONFIG = Path(__file__).parents[1] / "config.toml"


def test_repo_config_loads(monkeypatch, tmp_path):
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    for k in ("NOTIFY_EMAIL", "DIGEST_SINCE", "DIGEST_ALWAYS"):
        monkeypatch.delenv(k, raising=False)
    cfg = config.load(REPO_CONFIG)
    assert cfg.digest_since == date(2026, 1, 1)
    assert cfg.labs_courses["ICE101"]["every_weeks"] == 2
    assert cfg.notify_email is False  # το παράδειγμα δεν έχει email


def test_env_overrides_and_empty_secret_means_default(monkeypatch, tmp_path):
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    monkeypatch.setenv("NOTIFY_EMAIL", "0")
    monkeypatch.setenv("DIGEST_ALWAYS", "")  # GitHub secret που δεν ορίστηκε
    monkeypatch.setenv("DIGEST_SINCE", "2026-09-01")
    cfg = config.load(REPO_CONFIG)
    assert cfg.notify_email is False
    assert cfg.digest_always is False
    assert cfg.digest_since == date(2026, 9, 1)


def test_secret_values_are_cleaned(monkeypatch, tmp_path):
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    monkeypatch.setenv("SMTP_USER", "student@example.com\x1b[C ")  # δεξί βελάκι + κενό
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop\n")         # όπως το δείχνει η Google
    monkeypatch.setenv("NTFY_TOPIC", "  ")
    cfg = config.load(REPO_CONFIG)
    assert cfg.smtp_user == "student@example.com"
    assert cfg.smtp_password == "abcdefghijklmnop"
    assert cfg.ntfy_topic is None


def test_clean_keeps_spaces_inside_other_secrets():
    from uniwa_notifier.secrets import clean
    assert clean("ECLASS_PASSWORD", " pass word ") == "pass word"
    assert clean("SMTP_PASSWORD", "ab cd") == "abcd"
    assert clean("SMTP_USER", "\x1b[D\x1b[Cuser@x.gr\x7f") == "user@x.gr"
