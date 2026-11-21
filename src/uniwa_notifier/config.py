"""Ρυθμίσεις: config.toml (μη ευαίσθητα) + env (override) + secrets (Keychain/Credential Manager/env)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from . import catalog, secrets


def root_dir() -> Path:
    """Φάκελος με config.toml, .env και state/.

    Σειρά: UNIWA_HOME, ο τρέχων φάκελος αν έχει config.toml (ανάπτυξη, CI),
    ο φάκελος της εφαρμογής του λειτουργικού αν έχει config.toml (launcher),
    αλλιώς ο τρέχων φάκελος."""
    if os.getenv("UNIWA_HOME"):
        return Path(os.environ["UNIWA_HOME"])
    cwd = Path.cwd()
    if (cwd / "config.toml").exists():
        return cwd
    from . import system

    app = system.current().app_dir
    return app if (app / "config.toml").exists() else cwd


def _env_flag(name: str, default: bool) -> bool:
    """Κενή τιμή (π.χ. GitHub secret που δεν ορίστηκε) = default."""
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _secret(name: str) -> str | None:
    return secrets.lookup(name)


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


@dataclass
class Settings:
    tz: ZoneInfo
    state_dir: Path
    # notify
    notify_email: bool
    notify_desktop: bool  # ειδοποιήσεις υπολογιστή (Mac ή Windows)
    ntfy_server: str
    # announcements
    department_feed: str  # κενό = το τμήμα δεν έχει RSS
    include_eclass_system: bool
    # digest
    digest_since: date
    digest_always: bool
    digest_hide_submitted: bool
    # labs
    labs_email: bool
    labs_until_hour: int
    labs_courses: dict[str, dict] = field(default_factory=dict)

    # secrets (ποτέ σε αρχείο του repo)
    eclass_username: str | None = None
    eclass_password: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_to: str | None = None
    ntfy_topic: str | None = None
    ntfy_token: str | None = None
    healthcheck_url: str | None = None
    state_key: str | None = None
    notify_private: bool = True
    services_profile: str | None = None
    db_path: Path | None = None  # ορίζεται από το vault όσο τρέχει ένα job
    # πανεπιστήμιο (από τον κατάλογο)
    university: str = "uniwa"
    eclass_url: str = "https://eclass.uniwa.gr"
    department_name: str = "Τμήμα"
    grades_supported: bool = True

    @property
    def portal_url(self) -> str:
        return f"{self.eclass_url}/main/portfolio.php"

    @property
    def seen_db(self) -> Path:
        return self.db_path or self.state_dir / "seen.db"


def load(config_path: Path | None = None) -> Settings:
    try:
        from dotenv import load_dotenv

        load_dotenv(root_dir() / ".env")
    except ImportError:
        pass

    path = config_path or Path(os.getenv("UNIWA_CONFIG") or root_dir() / "config.toml")
    raw: dict = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    g, n, a, d, lb = (raw.get(k, {}) for k in ("general", "notify", "announcements", "digest", "labs"))
    uni_raw = raw.get("university", {})
    uni = catalog.get(os.getenv("UNIVERSITY") or uni_raw.get("id", "uniwa"))
    if not uni.is_supported or uni.eclass is None:
        raise ValueError(f"Το {uni.name} δεν υποστηρίζεται ακόμα ({uni.platform})")
    dept = uni.department(uni_raw.get("department", "")) or (uni.departments[0] if uni.departments else None)
    default_feed = dept.rss if dept and dept.rss else ""

    return Settings(
        tz=ZoneInfo(g.get("timezone", "Europe/Athens")),
        state_dir=Path(os.getenv("STATE_DIR") or root_dir() / "state"),
        notify_email=_env_flag("NOTIFY_EMAIL", n.get("email", True)),
        notify_desktop=_env_flag("NOTIFY_DESKTOP", _env_flag("NOTIFY_MAC", n.get("desktop", n.get("macos", True)))),
        ntfy_server=(os.getenv("NTFY_SERVER") or n.get("ntfy_server", "https://ntfy.sh")).rstrip("/"),
        department_feed=a.get("department_feed", default_feed),
        include_eclass_system=_env_flag("INCLUDE_ECLASS_SYSTEM", a.get("include_eclass_system", False)),
        digest_since=_as_date(os.getenv("DIGEST_SINCE") or d.get("since", "2026-01-01")),
        digest_always=_env_flag("DIGEST_ALWAYS", d.get("always", False)),
        digest_hide_submitted=_env_flag("DIGEST_HIDE_SUBMITTED", d.get("hide_submitted", False)),
        labs_email=_env_flag("LABS_EMAIL", lb.get("email", False)),
        labs_until_hour=int(os.getenv("LABS_UNTIL_HOUR") or lb.get("until_hour", 12)),
        labs_courses=lb.get("courses", {}),
        eclass_username=_secret("ECLASS_USERNAME"),
        eclass_password=_secret("ECLASS_PASSWORD"),
        smtp_host=_secret("SMTP_HOST"),
        smtp_port=int(_secret("SMTP_PORT") or 465),
        smtp_user=_secret("SMTP_USER"),
        smtp_password=_secret("SMTP_PASSWORD"),
        mail_to=_secret("MAIL_TO"),
        ntfy_topic=_secret("NTFY_TOPIC"),
        ntfy_token=_secret("NTFY_TOKEN"),
        healthcheck_url=_secret("HEALTHCHECK_URL"),
        state_key=_secret("STATE_KEY"),
        services_profile=str(raw.get("services", {}).get("profile") or "") or None,
        notify_private=_env_flag("NOTIFY_PRIVATE", n.get("private", True)),
        university=uni.id,
        eclass_url=uni.eclass.url,
        department_name=f"Τμήμα {dept.name}" if dept else "Τμήμα",
        grades_supported=uni.grades is not None and uni.grades.adapter == "ilyda",
    )
