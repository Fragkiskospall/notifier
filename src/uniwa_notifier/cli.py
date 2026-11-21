"""Γραμμή εντολών.

    python -m uniwa_notifier check            # νέες ανακοινώσεις
    python -m uniwa_notifier digest           # πρωινή σύνοψη εργασιών
    python -m uniwa_notifier labs             # εργαστήριο σήμερα;
    python -m uniwa_notifier grades           # νέοι βαθμοί (services.uniwa.gr)
    python -m uniwa_notifier test             # δοκιμαστική ειδοποίηση
    python -m uniwa_notifier secrets import   # .env → Keychain / Credential Manager
    python -m uniwa_notifier secrets set KEY  # αλλαγή ενός secret
    python -m uniwa_notifier schedule install # αυτόματα jobs (launchd ή Task Scheduler)
    python -m uniwa_notifier schedule remove  # αφαίρεση όλων των jobs
    python -m uniwa_notifier schedule status  # ποια jobs είναι ενεργά

Κοινές επιλογές: --dry-run (χωρίς αποστολή/αποθήκευση), --dump-html, -v
"""
from __future__ import annotations

import argparse
import getpass
import logging
import shutil
import sys
from pathlib import Path

from . import config, health, notify, runs, secrets, system, vault
from .jobs import announcements, digest, grades, labs
from .models import Item


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", help="χωρίς αποστολή και χωρίς αποθήκευση state")
    common.add_argument("--dump-html", action="store_true", help="αποθηκεύει τις σελίδες του eClass στο state/debug")
    common.add_argument("-v", "--verbose", action="store_true")

    ap = argparse.ArgumentParser(prog="uniwa-notifier", description="Ειδοποιήσεις eClass ΠΑΔΑ")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", parents=[common], help="νέες ανακοινώσεις")
    sub.add_parser("digest", parents=[common], help="πρωινή σύνοψη εργασιών")
    sub.add_parser("labs", parents=[common], help="ειδοποίηση αν έχεις εργαστήριο σήμερα")
    sub.add_parser("grades", parents=[common], help="νέοι βαθμοί από την πύλη φοιτητολογίου")
    sub.add_parser("test", parents=[common], help="δοκιμαστική ειδοποίηση σε όλα τα κανάλια")
    sp = sub.add_parser("secrets", parents=[common], help="διαχείριση κωδικών στην αποθήκη του συστήματος")
    sp.add_argument("action", choices=["import", "set", "genkey"])
    sp.add_argument("key", nargs="?")
    sp.add_argument("--stdin", action="store_true", help="διάβασε την τιμή από stdin (για scripts)")
    sc = sub.add_parser("schedule", parents=[common], help="αυτόματα jobs στο παρασκήνιο (Mac/Windows)")
    sc.add_argument("action", choices=["install", "remove", "status"])
    sc.add_argument("--every", type=int, default=30, help="λεπτά ανάμεσα στους ελέγχους (default 30)")
    sc.add_argument("--digest", default="08:00,14:00,21:00", help="ώρες σύνοψης, χωρισμένες με κόμμα")
    return ap


def _schedule(args) -> int:
    backend = system.current()
    if args.action == "status":
        state = backend.status()
        print(f"Λειτουργικό: {backend.name} · Φάκελος: {backend.app_dir}")
        for name, ok in state.items():
            print(f"  {'✓' if ok else '✗'} {name}")
        if not state:
            print("  Κανένα αυτόματο job.")
        return 0
    if args.action == "remove":
        removed = backend.uninstall()
        print(f"✅ Αφαιρέθηκαν: {', '.join(removed) or 'κανένα'}")
        return 0
    jobs = system.default_jobs(args.every, [t.strip() for t in args.digest.split(",") if t.strip()])
    if args.dry_run:
        print(f"Λειτουργικό: {backend.name} · Φάκελος: {backend.app_dir}")
        for job in jobs:
            when = f"κάθε {job.every_minutes}′" if job.every_minutes else " · ".join(job.at)
            print(f"  {job.name:7} {when:22} {' '.join(system.launch_command(job.args))}")
        return 0
    app_dir = backend.ensure_dirs()
    src_cfg = Path.cwd() / "config.toml"
    if not (app_dir / "config.toml").exists() and src_cfg.exists():
        shutil.copy2(src_cfg, app_dir / "config.toml")
    try:
        installed = backend.install(jobs)
    except system.UnsupportedPlatform as e:
        print(f"ℹ️  {e}. Χρησιμοποίησε τη λειτουργία cloud (GitHub Actions).")
        return 2
    print(f"✅ Ενεργά στο παρασκήνιο ({backend.name}): {', '.join(installed)}")
    print(f"   Φάκελος: {app_dir}")
    return 0


def _utf8_console() -> None:
    """Η κονσόλα των Windows είναι cp1252 και δεν τυπώνει ελληνικά. Με pythonw
    (jobs παρασκηνίου) δεν υπάρχει καθόλου stdout/stderr."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    args = _parser().parse_args(argv)
    log_kwargs: dict = {}
    if sys.stderr is None:  # pythonw / .exe χωρίς κονσόλα: logs σε αρχείο (μόνο πλήθη, ποτέ περιεχόμενο)
        log_dir = config.root_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_kwargs["filename"] = str(log_dir / f"{args.cmd}.log")
        log_kwargs["encoding"] = "utf-8"
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        **log_kwargs,
    )
    if args.cmd == "schedule":
        return _schedule(args)
    if args.cmd == "secrets":
        root = config.root_dir()
        if args.action == "import":
            moved = secrets.import_from_env_file(root / ".env")
            print(f"✅ {len(moved)} στοιχεία στο {secrets.STORE}: {', '.join(moved) or '-'}")
        elif args.action == "genkey":
            # Τυπώνει νέο κλειδί μόνο στο stdout, για να γίνει pipe (δεν γράφεται πουθενά)
            sys.stdout.write(vault.generate_key())
        else:
            if not args.key:
                print("Δώσε όνομα, π.χ.: secrets set ECLASS_PASSWORD")
                return 2
            value = sys.stdin.read().strip() if args.stdin else getpass.getpass(f"{args.key}: ")
            secrets.set_secret(args.key, value)
            print(f"✅ {args.key} αποθηκεύτηκε στο {secrets.STORE}", file=sys.stderr)
        return 0

    cfg = config.load()
    if args.cmd == "test":
        notify.announcements(cfg, [Item("test", "uniwa-notifier", "Δοκιμαστική ειδοποίηση ✅",
                                        cfg.portal_url, "Αν το βλέπεις, οι ειδοποιήσεις δουλεύουν.")])
        return 0

    jobs = {
        "check": lambda: announcements.run(cfg, args.dry_run),
        "digest": lambda: digest.run(cfg, args.dry_run, args.dump_html),
        "labs": lambda: labs.run(cfg, args.dry_run, args.dump_html),
        "grades": lambda: grades.run(cfg, args.dry_run),
    }
    stateful = args.cmd in ("check", "grades")
    health.ping(cfg.healthcheck_url, "/start")
    try:
        if stateful:
            with vault.open_state(cfg.state_dir, cfg.state_key, secrets.state_counter()) as db:
                cfg.db_path = db
                rc = jobs[args.cmd]()
        else:
            rc = jobs[args.cmd]()
    except Exception:
        health.ping(cfg.healthcheck_url, "/fail")
        if not args.dry_run:
            runs.record(cfg.state_dir.parent / "logs", args.cmd, False)
        raise
    health.ping(cfg.healthcheck_url, "" if rc == 0 else "/fail")
    if not args.dry_run:
        runs.record(cfg.state_dir.parent / "logs", args.cmd, rc == 0)
    return rc


if __name__ == "__main__":
    sys.exit(main())
