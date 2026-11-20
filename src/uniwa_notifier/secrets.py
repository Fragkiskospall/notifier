"""Ευαίσθητα στοιχεία στην αποθήκη κωδικών του λειτουργικού: Keychain στο Mac,
Credential Manager στα Windows. Στο cloud έρχονται ως env (GitHub Secrets)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SERVICE = "uniwa-notifier"
KEYS = ("ECLASS_USERNAME", "ECLASS_PASSWORD", "SMTP_USER", "SMTP_PASSWORD",
        "MAIL_TO", "NTFY_TOPIC", "NTFY_TOKEN", "HEALTHCHECK_URL", "STATE_KEY")


STORE_NAMES = {"darwin": "Keychain", "win32": "Credential Manager"}
STORE = STORE_NAMES.get(sys.platform, "αποθήκη κωδικών")

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z~]|\x1b[@-Z\\-_]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean(key: str, value: str | None) -> str | None:
    """Αφαιρεί ό,τι μπαίνει κατά λάθος σε κρυφά πεδία: πλήκτρα-βελάκια (ANSI),
    χαρακτήρες ελέγχου, κενά στην αρχή/τέλος. Από το App Password και όλα τα κενά."""
    if value is None:
        return None
    v = _CONTROL.sub("", _ANSI.sub("", value)).strip()
    if key == "SMTP_PASSWORD":
        v = re.sub(r"\s+", "", v)
    return v or None


def _keyring():
    if sys.platform not in STORE_NAMES:
        return None
    try:
        import keyring  # type: ignore

        return keyring
    except ImportError:
        return None


def load_into_env() -> None:
    """Συμπληρώνει από την αποθήκη κωδικών όσα δεν υπάρχουν ήδη ως env."""
    kr = _keyring()
    if kr is None:
        return
    for k in KEYS:
        if os.getenv(k):
            continue
        try:
            v = kr.get_password(SERVICE, k)
        except Exception:
            return
        v = clean(k, v)
        if v:
            os.environ[k] = v


def import_from_env_file(env_path: Path) -> list[str]:
    """Μεταφέρει secrets από .env στην αποθήκη κωδικών και τα αφαιρεί από το αρχείο."""
    from dotenv import dotenv_values

    kr = _keyring()
    if kr is None:
        raise RuntimeError("Η αποθήκη κωδικών υπάρχει μόνο σε macOS και Windows (με το πακέτο keyring)")
    values = dotenv_values(env_path)
    moved = []
    for k in KEYS:
        v = clean(k, values.get(k) or "")
        if not v:
            continue
        kr.set_password(SERVICE, k, v)
        if kr.get_password(SERVICE, k) != v:
            raise RuntimeError(f"Αποτυχία επαλήθευσης για {k}, το .env δεν άλλαξε")
        moved.append(k)
    lines = [ln for ln in env_path.read_text(encoding="utf-8").splitlines()
             if ln.split("=", 1)[0].strip() not in KEYS]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return moved


def get_secret(key: str) -> str | None:
    kr = _keyring()
    if kr is None:
        return None
    try:
        return clean(key, kr.get_password(SERVICE, key))
    except Exception:
        return None


def delete_all() -> list[str]:
    """Σβήνει όλους τους κωδικούς της εφαρμογής από την αποθήκη (απεγκατάσταση)."""
    kr = _keyring()
    if kr is None:
        return []
    removed = []
    for k in KEYS:
        try:
            if kr.get_password(SERVICE, k) is not None:
                kr.delete_password(SERVICE, k)
                removed.append(k)
        except Exception:
            continue
    return removed


def set_secret(key: str, value: str) -> None:
    kr = _keyring()
    if kr is None:
        raise RuntimeError("Η αποθήκη κωδικών υπάρχει μόνο σε macOS και Windows")
    if key not in KEYS:
        raise ValueError(f"Άγνωστο secret: {key}. Επιτρέπονται: {', '.join(KEYS)}")
    cleaned = clean(key, value)
    if not cleaned:
        raise ValueError(f"Κενή τιμή για {key}")
    kr.set_password(SERVICE, key, cleaned)
