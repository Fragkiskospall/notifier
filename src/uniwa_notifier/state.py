"""Μνήμη για το ποιες ανακοινώσεις έχουν ήδη ειδοποιηθεί (SQLite)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Grade, Item


class SeenStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            " uid TEXT PRIMARY KEY, source TEXT, title TEXT, link TEXT,"
            " seen_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS sources (name TEXT PRIMARY KEY)")
        # Μόνο αναγνωριστικό και τιμή, όχι ονόματα μαθημάτων
        self.db.execute("CREATE TABLE IF NOT EXISTS grades (id TEXT PRIMARY KEY, value TEXT)")

    def source_known(self, name: str) -> bool:
        return self.db.execute("SELECT 1 FROM sources WHERE name=?", (name,)).fetchone() is not None

    def mark_source(self, name: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO sources(name) VALUES (?)", (name,))

    def is_seen(self, uid: str) -> bool:
        return self.db.execute("SELECT 1 FROM seen WHERE uid=?", (uid,)).fetchone() is not None

    def mark_seen(self, it: Item) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO seen(uid, source, title, link) VALUES (?,?,?,?)",
            (it.uid, it.source, it.title, it.link),
        )

    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> SeenStore:
        return self

    def __exit__(self, *exc) -> None:
        # Κλείνει πάντα τη βάση, ώστε το vault να μπορεί να σβήσει το προσωρινό
        # αρχείο (στα Windows ένα ανοιχτό αρχείο δεν διαγράφεται).
        self.close()

    def diff(self, collected: dict[str, list[Item]], record: bool = True) -> tuple[list[Item], list[str]]:
        """Επιστρέφει (νέες ανακοινώσεις, πηγές που είδαμε πρώτη φορά).

        Την πρώτη φορά που εμφανίζεται μια πηγή, οι υπάρχουσες ανακοινώσεις της
        καταγράφονται χωρίς ειδοποίηση, ώστε να μη γίνει «πλημμύρα».
        """
        new_items: list[Item] = []
        first_seen: list[str] = []
        for src, items in collected.items():
            first_time = not self.source_known(src)
            if first_time:
                first_seen.append(src)
            for it in items:
                if self.is_seen(it.uid):
                    continue
                if not first_time:
                    new_items.append(it)
                if record:
                    self.mark_seen(it)
            if record:
                self.mark_source(src)
        return new_items, first_seen

    def grade_changes(self, grades: list[Grade], record: bool = True
                      ) -> tuple[list[tuple[Grade, str | None]], bool]:
        """([(βαθμός, προηγούμενη τιμή ή None)], πρώτη φορά).

        Αναφέρει νέες προσπάθειες και αλλαγές βαθμού. Την πρώτη φορά καταγράφει
        τα πάντα χωρίς ειδοποίηση.
        """
        first_time = not self.source_known("grades")
        changes: list[tuple[Grade, str | None]] = []
        for g in grades:
            value = "" if g.value is None else repr(g.value)
            row = self.db.execute("SELECT value FROM grades WHERE id=?", (g.id,)).fetchone()
            if row is not None and row[0] == value:
                continue
            if not first_time and (row is not None or g.value is not None):
                changes.append((g, row[0] if row else None))
            if record:
                self.db.execute("INSERT OR REPLACE INTO grades(id, value) VALUES (?,?)", (g.id, value))
        if record:
            self.mark_source("grades")
        return changes, first_time


class StoreScope:
    """Κλείνει όποια SeenStore ανοίξει ένα job, ό,τι κι αν συμβεί. Χρειάζεται για
    τα Windows, όπου το vault δεν μπορεί να σβήσει ανοιχτό προσωρινό αρχείο."""

    def __init__(self) -> None:
        self._open: list[SeenStore] = []

    def open(self, path: Path) -> SeenStore:
        store = SeenStore(path)
        self._open.append(store)
        return store

    def __enter__(self) -> StoreScope:
        return self

    def __exit__(self, *exc) -> None:
        for store in self._open:
            store.close()
