"""Κρυπτογραφημένο state και ειδοποιήσεις/logs χωρίς περιεχόμενο."""
import logging
import sqlite3

import pytest

from uniwa_notifier import cli, notify, vault
from uniwa_notifier.jobs import announcements
from uniwa_notifier.models import Item

SECRET_TITLE = "Μυστική ανακοίνωση για εξέταση ΨΕΣ"
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # σταθερό κλειδί μόνο για tests


# ---------------------------------------------------------------- vault

def test_roundtrip_and_tamper():
    key = vault.generate_key()
    blob = vault.encrypt(b"hello", key)
    assert b"hello" not in blob
    assert vault.decrypt(blob, key) == b"hello"
    with pytest.raises(vault.VaultError):
        vault.decrypt(blob, vault.generate_key())          # λάθος κλειδί
    with pytest.raises(vault.VaultError):
        vault.decrypt(blob[:-1] + bytes([blob[-1] ^ 1]), key)  # αλλοιωμένο αρχείο


def test_bad_key():
    with pytest.raises(vault.VaultError):
        vault.encrypt(b"x", "not-base64!")


def _write_db(path, title):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE t (x TEXT)")
    db.execute("INSERT INTO t VALUES (?)", (title,))
    db.commit()
    db.close()


def test_state_never_plain_on_disk(tmp_path):
    key = vault.generate_key()
    with vault.open_state(tmp_path, key) as db:
        assert tmp_path not in db.parents  # δουλεύει σε temp, όχι στο state/
        _write_db(db, SECRET_TITLE)
    assert [p.name for p in tmp_path.iterdir()] == ["seen.db.enc"]
    assert SECRET_TITLE.encode() not in (tmp_path / "seen.db.enc").read_bytes()
    assert not db.exists()  # το προσωρινό σβήστηκε

    with vault.open_state(tmp_path, key) as db2:
        assert sqlite3.connect(db2).execute("SELECT x FROM t").fetchone()[0] == SECRET_TITLE


def test_unchanged_state_is_not_rewritten(tmp_path):
    key = vault.generate_key()
    with vault.open_state(tmp_path, key) as db:
        _write_db(db, "a")
    before = (tmp_path / "seen.db.enc").read_bytes()
    with vault.open_state(tmp_path, key):
        pass
    assert (tmp_path / "seen.db.enc").read_bytes() == before  # → κανένα push


def test_migrates_legacy_plaintext(tmp_path):
    _write_db(tmp_path / "seen.db", SECRET_TITLE)
    key = vault.generate_key()
    with vault.open_state(tmp_path, key) as db:
        assert sqlite3.connect(db).execute("SELECT x FROM t").fetchone()[0] == SECRET_TITLE
    assert not (tmp_path / "seen.db").exists()
    assert (tmp_path / "seen.db.enc").exists()


def test_failed_job_keeps_previous_state(tmp_path):
    key = vault.generate_key()
    with vault.open_state(tmp_path, key) as db:
        _write_db(db, "a")
    before = (tmp_path / "seen.db.enc").read_bytes()
    with pytest.raises(RuntimeError), vault.open_state(tmp_path, key) as db:
        sqlite3.connect(db).execute("INSERT INTO t VALUES ('b')").connection.commit()
        raise RuntimeError("crash")
    assert (tmp_path / "seen.db.enc").read_bytes() == before


class _MemCounter:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_old_format_still_readable():
    key = vault.generate_key()
    nonce = b"\0" * 12
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    old = vault.MAGIC_V1 + nonce + AESGCM(vault._key(key)).encrypt(nonce, b"legacy", vault.AAD)
    assert vault.unseal(old, key) == (0, b"legacy")


def test_counter_goes_up_on_every_change(tmp_path):
    key, counter = vault.generate_key(), _MemCounter()
    with vault.open_state(tmp_path, key, counter) as db:
        _write_db(db, "a")
    with vault.open_state(tmp_path, key, counter) as db:
        sqlite3.connect(db).execute("INSERT INTO t VALUES ('b')").connection.commit()
    assert counter.value == 2
    assert vault.unseal((tmp_path / "seen.db.enc").read_bytes(), key)[0] == 2


def test_rollback_to_older_copy_is_rejected(tmp_path):
    key, counter = vault.generate_key(), _MemCounter()
    with vault.open_state(tmp_path, key, counter) as db:
        _write_db(db, "παλιό")
    old_copy = (tmp_path / "seen.db.enc").read_bytes()
    with vault.open_state(tmp_path, key, counter) as db:
        sqlite3.connect(db).execute("INSERT INTO t VALUES ('νέο')").connection.commit()

    (tmp_path / "seen.db.enc").write_bytes(old_copy)  # επαναφορά παλιού, έγκυρου αρχείου
    with vault.open_state(tmp_path, key, counter) as db:
        assert not db.exists()  # δεν φορτώθηκε: το state ξεκινά από την αρχή
        _write_db(db, "ξανά")
    assert vault.unseal((tmp_path / "seen.db.enc").read_bytes(), key)[0] == 3


def test_counter_failure_does_not_break_jobs(tmp_path):
    class Broken:
        def get(self):
            raise OSError("keychain locked")

        def set(self, value):
            raise OSError("keychain locked")

    key = vault.generate_key()
    with vault.open_state(tmp_path, key, Broken()) as db:
        _write_db(db, "a")
    assert vault.decrypt((tmp_path / "seen.db.enc").read_bytes(), key)


def test_keychain_secrets_never_enter_environment(monkeypatch, tmp_path):
    from uniwa_notifier import config, secrets

    class FakeKeyring:
        def get_password(self, service, key):
            return {"ECLASS_PASSWORD": "s3cret", "STATE_KEY": KEY}.get(key)

    monkeypatch.setattr(secrets, "_keyring", lambda: FakeKeyring())
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    monkeypatch.delenv("ECLASS_PASSWORD", raising=False)
    monkeypatch.delenv("STATE_KEY", raising=False)
    cfg = config.load()
    assert cfg.eclass_password == "s3cret" and cfg.state_key == KEY
    import os
    assert "ECLASS_PASSWORD" not in os.environ and "STATE_KEY" not in os.environ


def test_env_still_wins_over_keychain(monkeypatch, tmp_path):
    from uniwa_notifier import config, secrets

    class FakeKeyring:
        def get_password(self, service, key):
            return "from-keychain"

    monkeypatch.setattr(secrets, "_keyring", lambda: FakeKeyring())
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    monkeypatch.setenv("ECLASS_USERNAME", "from-env")
    assert config.load().eclass_username == "from-env"


@pytest.mark.parametrize("url", ["http://ntfy.sh", "ftp://x", "ntfy.sh"])
def test_ntfy_refuses_plain_http(url):
    with pytest.raises(ValueError):
        notify.ntfy.check_server(url)


@pytest.mark.parametrize("url", ["https://ntfy.sh", "https://ntfy.example.org/", "http://localhost:8080"])
def test_ntfy_accepts_https_and_local(url):
    notify.ntfy.check_server(url)


# ---------------------------------------------------------------- ειδοποιήσεις & logs

def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(notify.ntfy, "send", lambda cfg, title, text, click="", tags=None: sent.append((title, text, click)))
    monkeypatch.setattr(notify.email, "send", lambda cfg, subject, text, body: sent.append((subject, text, body)))
    return sent


def _run_check(monkeypatch, tmp_path, items, private):
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    monkeypatch.setenv("STATE_KEY", KEY)
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("NOTIFY_MAC", "0")
    monkeypatch.setenv("NOTIFY_PRIVATE", "1" if private else "0")
    monkeypatch.setattr(announcements, "fetch_department", lambda cfg, s: {"dept": list(items)})
    monkeypatch.setattr(announcements, "fetch_eclass", lambda cfg, s: {})
    return cli.main(["check"])


def test_private_mode_leaks_nothing(monkeypatch, tmp_path, caplog):
    sent = _capture(monkeypatch)
    items = [Item("dept:1", "Τμήμα ΜΠΥ", "παλιά", "https://ice.uniwa.gr/old")]
    _run_check(monkeypatch, tmp_path, items, private=True)  # seed
    items.append(Item("dept:2", "Τμήμα ΜΠΥ", SECRET_TITLE, "https://ice.uniwa.gr/mystiki-anakoinosi"))
    caplog.set_level(logging.DEBUG)
    assert _run_check(monkeypatch, tmp_path, items, private=True) == 0

    blob = repr(sent) + caplog.text
    assert sent, "θα έπρεπε να σταλεί ειδοποίηση"
    assert "ΨΕΣ" not in blob and "Μυστική" not in blob and "mystiki" not in blob
    assert any("1 από το τμήμα" in s[1] for s in sent)
    # και το state στο δίσκο είναι μόνο κρυπτογραφημένο
    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == ["seen.db.enc"]


def test_full_mode_still_available(monkeypatch, tmp_path):
    sent = _capture(monkeypatch)
    items = [Item("dept:1", "Τμήμα ΜΠΥ", "παλιά", "https://x/1")]
    _run_check(monkeypatch, tmp_path, items, private=False)
    items.append(Item("dept:2", "Τμήμα ΜΠΥ", SECRET_TITLE, "https://x/2"))
    _run_check(monkeypatch, tmp_path, items, private=False)
    assert any(SECRET_TITLE in str(s) for s in sent)
