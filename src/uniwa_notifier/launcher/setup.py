"""Η λογική του launcher, χωρίς UI: ό,τι κάνει το κουμπί «Ολοκλήρωση».

Γράφει το config.toml στον φάκελο της εφαρμογής, βάζει τους κωδικούς στην
αποθήκη του λειτουργικού, φτιάχνει κλειδί κρυπτογράφησης και ntfy κανάλι,
και στήνει τα jobs. Η απεγκατάσταση τα σβήνει όλα.
"""
from __future__ import annotations

import datetime as dt
import secrets as pysecrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .. import catalog, runs, system, vault
from .. import secrets as store_mod
from ..eclass.client import EClass, EClassError, new_session

NTFY_SERVER = "https://ntfy.sh"


@dataclass
class Choices:
    """Ό,τι διαλέγει ο χρήστης στις οθόνες του launcher."""

    university: str
    username: str
    password: str
    department: str | None = None
    notify_mobile: bool = True
    notify_desktop: bool = True
    private: bool = True
    every_minutes: int = 30
    digest_at: tuple[str, ...] = ("08:00", "14:00", "21:00")
    ntfy_topic: str = field(default_factory=lambda: new_topic())


class SecretStore:
    """Προσαρμογέας πάνω στο secrets.py, ώστε τα tests να δίνουν δικό τους."""

    def set(self, key: str, value: str) -> None:
        store_mod.set_secret(key, value)

    def get(self, key: str) -> str | None:
        return store_mod.get_secret(key)

    def delete_all(self) -> list[str]:
        return store_mod.delete_all()


def new_topic() -> str:
    """Τυχαίο, μη μαντεύσιμο κανάλι ntfy: 128 bit, μόνο γράμματα/αριθμοί όπως θέλει το ntfy.
    Στο ntfy.sh όποιος ξέρει το όνομα του καναλιού διαβάζει τις ειδοποιήσεις, άρα
    το όνομα λειτουργεί σαν κωδικός."""
    return "fos-" + pysecrets.token_hex(16)


def ntfy_subscribe_url(topic: str, server: str = NTFY_SERVER) -> str:
    return f"{server.rstrip('/')}/{topic}"


@dataclass
class LoginResult:
    ok: bool
    message: str
    courses: int = 0


def verify_login(uni_id: str, username: str, password: str,
                 session: requests.Session | None = None) -> LoginResult:
    """Δοκιμαστική σύνδεση στο eClass του ιδρύματος, για τον έλεγχο «στη στιγμή»."""
    uni = catalog.get(uni_id)
    if not uni.is_supported or uni.eclass is None:
        return LoginResult(False, f"Το {uni.short} δεν υποστηρίζεται ακόμα.")
    if not username.strip() or not password:
        return LoginResult(False, "Συμπλήρωσε όνομα χρήστη και κωδικό.")
    try:
        ec = EClass(username.strip(), password, session=session or new_session(), base=uni.eclass.url)
        ec.login()
        n = len(ec.courses())
    except EClassError as e:
        msg = str(e)
        if "login" in msg.lower():
            msg = "Λάθος όνομα χρήστη ή κωδικός."
        return LoginResult(False, msg)
    except requests.RequestException:
        return LoginResult(False, f"Δεν ήταν δυνατή η σύνδεση με το {uni.eclass.url.split('//')[1]}. Έλεγξε το internet.")
    word = "μάθημα" if n == 1 else "μαθήματα"
    return LoginResult(True, f"Η σύνδεση πέτυχε. Βρέθηκαν {n} {word}.", n)


def jobs_for(choices: Choices) -> list[system.Job]:
    uni = catalog.get(choices.university)
    jobs = system.default_jobs(choices.every_minutes, choices.digest_at)
    if uni.grades is None:
        jobs = [j for j in jobs if j.name != "grades"]
    return jobs


def _toml_str(v: str) -> str:
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_config(c: Choices, today: dt.date | None = None) -> str:
    """Το config.toml που γράφει ο launcher. Χωρίς κανένα ευαίσθητο στοιχείο."""
    uni = catalog.get(c.university)
    today = today or dt.date.today()
    since = dt.date(today.year if today.month >= 9 else today.year - 1, 9, 1)
    lines = [
        "# Δημιουργήθηκε από τον launcher του FragkiskOSource Notifier.",
        "# Οι κωδικοί ΔΕΝ βρίσκονται εδώ: ζουν στην αποθήκη κωδικών του λειτουργικού.",
        "",
        "[general]",
        'timezone = "Europe/Athens"',
        "",
        "[university]",
        f"id = {_toml_str(uni.id)}",
    ]
    if c.department:
        lines.append(f"department = {_toml_str(c.department)}")
    lines += [
        "",
        "[notify]",
        f"private = {str(c.private).lower()}",
        "email = false",
        f"desktop = {str(c.notify_desktop).lower()}",
        f"ntfy_server = {_toml_str(NTFY_SERVER)}",
        "",
        "[announcements]",
        "include_eclass_system = false",
        "",
        "[digest]",
        f"since = {since.isoformat()}",
        "always = false",
        "hide_submitted = false",
        "",
        "[labs]",
        "email = false",
        f"until_hour = {int(sorted(c.digest_at)[0][:2]) + 4}",
        "",
        "[schedule]  # μόνο για την οθόνη Κατάσταση· τα jobs τα έχει το σύστημα",
        f"every_minutes = {c.every_minutes}",
        "digest_at = [" + ", ".join(_toml_str(t) for t in sorted(c.digest_at)) + "]",
        "",
    ]
    return "\n".join(lines)


def apply(c: Choices, backend: system.Backend | None = None, store: SecretStore | None = None,
          install_jobs: bool = True, progress: Callable[[str], None] | None = None) -> list[str]:
    """Εκτελεί την εγκατάσταση. Επιστρέφει τα jobs που ενεργοποιήθηκαν."""
    backend = backend or system.current()
    store = store or SecretStore()
    step = progress or (lambda _msg: None)

    step("Δημιουργία φακέλου εφαρμογής")
    app_dir = backend.ensure_dirs()
    (app_dir / "config.toml").write_text(render_config(c), encoding="utf-8")

    step("Αποθήκευση κωδικών στο " + store_mod.STORE)
    store.set("ECLASS_USERNAME", c.username.strip())
    store.set("ECLASS_PASSWORD", c.password)
    if not store.get("STATE_KEY"):
        store.set("STATE_KEY", vault.generate_key())
    if c.notify_mobile:
        store.set("NTFY_TOPIC", c.ntfy_topic)

    if not install_jobs:
        return []
    step("Ενεργοποίηση αυτόματων ελέγχων")
    return backend.install(jobs_for(c))


def remove_everything(backend: system.Backend | None = None, store: SecretStore | None = None) -> None:
    """Απεγκατάσταση: jobs, κωδικοί, ρυθμίσεις και ιστορικό. Δεν μένει τίποτα."""
    backend = backend or system.current()
    store = store or SecretStore()
    backend.uninstall()
    store.delete_all()
    shutil.rmtree(backend.app_dir, ignore_errors=True)


def is_configured(backend: system.Backend | None = None) -> bool:
    backend = backend or system.current()
    return (backend.app_dir / "config.toml").exists()


@dataclass
class JobStatus:
    name: str
    active: bool
    last_run: dt.datetime | None
    last_ok: bool | None


def status(backend: system.Backend | None = None) -> list[JobStatus]:
    backend = backend or system.current()
    active = backend.status()
    logs_dir = backend.app_dir / "logs"
    out = []
    for name in ("check", "grades", "digest", "labs"):
        if name not in active:
            continue
        last = runs.last(logs_dir, name)
        out.append(JobStatus(name, active[name], last[0] if last else None, last[1] if last else None))
    return out


def configured_schedule(backend: system.Backend | None = None) -> tuple[int, list[str]]:
    backend = backend or system.current()
    import tomllib

    try:
        raw = tomllib.loads((backend.app_dir / "config.toml").read_text(encoding="utf-8")).get("schedule", {})
        return int(raw.get("every_minutes", 30)), list(raw.get("digest_at", ["08:00", "14:00", "21:00"]))
    except (OSError, ValueError):
        return 30, ["08:00", "14:00", "21:00"]


def next_time(times: list[str], now: dt.datetime) -> dt.datetime:
    """Η επόμενη ώρα από μια λίστα ΩΩ:ΛΛ (σήμερα ή αύριο)."""
    candidates = []
    for t in times:
        h, m = int(t[:2]), int(t[3:])
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        candidates.append(at if at > now else at + dt.timedelta(days=1))
    return min(candidates)


def configured_university(backend: system.Backend | None = None) -> catalog.University | None:
    backend = backend or system.current()
    path: Path = backend.app_dir / "config.toml"
    if not path.exists():
        return None
    import tomllib

    try:
        uid = tomllib.loads(path.read_text(encoding="utf-8")).get("university", {}).get("id", "uniwa")
        return catalog.get(uid)
    except (ValueError, KeyError, OSError):
        return None
