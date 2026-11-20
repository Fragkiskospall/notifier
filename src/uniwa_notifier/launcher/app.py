"""Σημείο εκκίνησης του .exe / .app.

Το ίδιο εκτελέσιμο κάνει δύο δουλειές:
- χωρίς ορίσματα ανοίγει τον launcher (παράθυρα),
- με ορίσματα (π.χ. ``check``) τρέχει σιωπηλά ένα job, όπως το καλούν το
  launchd ή το Task Scheduler στο παρασκήνιο.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from ..cli import main as cli_main

        return cli_main(sys.argv[1:])
    from .ui import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
