from datetime import date, datetime

from uniwa_notifier.jobs import digest, labs
from uniwa_notifier.models import Assignment, Item, LabSlot
from uniwa_notifier.state import SeenStore

# ---------------------------------------------------------------- state

def _items(*ids):
    return [Item(f"dept:{i}", "Τμήμα", f"Τίτλος {i}", f"https://x/{i}") for i in ids]


def test_first_run_seeds_without_notifying(tmp_path):
    store = SeenStore(tmp_path / "seen.db")
    new, first = store.diff({"dept": _items(1, 2)})
    assert new == [] and first == ["dept"]


def test_new_item_reported_once(tmp_path):
    store = SeenStore(tmp_path / "seen.db")
    store.diff({"dept": _items(1, 2)})
    new, _ = store.diff({"dept": _items(1, 2, 3)})
    assert [i.uid for i in new] == ["dept:3"]
    new, _ = store.diff({"dept": _items(1, 2, 3)})
    assert new == []


def test_dry_run_does_not_record(tmp_path):
    store = SeenStore(tmp_path / "seen.db")
    store.diff({"dept": _items(1)})
    store.diff({"dept": _items(1, 2)}, record=False)
    new, _ = store.diff({"dept": _items(1, 2)})
    assert [i.uid for i in new] == ["dept:2"]


def test_rollback_keeps_item_for_retry(tmp_path):
    path = tmp_path / "seen.db"
    store = SeenStore(path)
    store.diff({"dept": _items(1)})
    store.commit()
    store.diff({"dept": _items(1, 2)})
    store.rollback()  # π.χ. αποτυχία αποστολής
    new, _ = SeenStore(path).diff({"dept": _items(1, 2)})
    assert [i.uid for i in new] == ["dept:2"]


# ---------------------------------------------------------------- digest

def test_digest_selection(tz):
    now = datetime(2026, 11, 10, 9, 0, tzinfo=tz)
    since = datetime(2026, 1, 1, tzinfo=tz)
    def mk(title, dl, sub=False, exp=False):
        return Assignment("Μάθημα", title, "https://x", dl, sub, exp)
    items = [
        mk("ανοιχτή", datetime(2026, 11, 20, 23, 59, tzinfo=tz)),
        mk("υποβλήθηκε", datetime(2026, 11, 12, 23, 59, tzinfo=tz), sub=True),
        mk("έληξε", datetime(2026, 10, 1, tzinfo=tz), exp=True),
        mk("χωρίς προθεσμία", None),
    ]
    active, undated = digest.select(items, now, since, hide_submitted=False)
    assert [a.title for a in active] == ["ανοιχτή", "υποβλήθηκε"]  # οι υποβληθείσες στο τέλος
    assert [a.title for a in undated] == ["χωρίς προθεσμία"]

    active, _ = digest.select(items, now, since, hide_submitted=True)
    assert [a.title for a in active] == ["ανοιχτή"]


def test_digest_message(tz):
    now = datetime(2026, 11, 10, 9, 0, tzinfo=tz)
    a = Assignment("ΨΕΣ", "Άσκηση 1", "https://x", datetime(2026, 11, 11, 8, 0, tzinfo=tz), False)
    msg = digest.build_message([a], [], now)
    assert msg.title == "📚 1 εργασία σε εκκρεμότητα"
    assert "🔴 Άσκηση 1" in msg.text  # λήγει σε < 48 ώρες
    # η ιδιωτική εκδοχή δεν έχει τίτλους ή μαθήματα
    assert msg.private_title == "🔴 📚 1 εργασία σε εκκρεμότητα"
    assert "Άσκηση" not in msg.private_text and "ΨΕΣ" not in msg.private_text


# ---------------------------------------------------------------- labs

PSES = {"name": "ΨΕΣ", "every_weeks": 2, "anchor": date(2026, 11, 13)}


def test_labs_biweekly():
    slot = LabSlot("ICE243", "ΨΕΣ", "Τμήμα 8", 4, "16:00-17:00")
    expected = {date(2026, 11, 6): False, date(2026, 11, 13): True, date(2026, 11, 20): False,
                date(2026, 11, 27): True, date(2026, 12, 4): False, date(2026, 12, 11): True,
                date(2026, 11, 12): False}
    assert {d: labs.is_today(slot, d, PSES) for d in expected} == expected


def test_labs_weekly_default():
    slot = LabSlot("ICE316", "ΣΣΧΥ", "x", 2, None)
    assert labs.is_today(slot, date(2026, 11, 18), {})
    assert not labs.is_today(slot, date(2026, 11, 19), {})


def test_labs_slots_from_real_groups(fixture):
    slots = labs.slots_for_course("ICE243", "ΨΗΦΙΑΚΗ ΕΠΕΞΕΡΓΑΣΙΑ ΣΗΜΑΤΟΣ", fixture("group_ICE243.html"), PSES)
    assert [(s.course, s.weekday, s.time) for s in slots] == [("ΨΕΣ", 4, "16:00-17:00")]


def test_labs_manual_override():
    slots = labs.slots_for_course("X1", "Μάθημα", "", {"weekday": "Δευτέρα", "time": "10:00-12:00"})
    assert [(s.weekday, s.time) for s in slots] == [(0, "10:00-12:00")]


def test_labs_message():
    msg = labs.build_message([LabSlot("ICE243", "ΨΕΣ", "x", 4, "16:00-17:00")])
    assert msg.title == "🧪 Σήμερα έχεις εργαστήριο"
    assert msg.text == "• ΨΕΣ · 16:00–17:00"
    assert "ΨΕΣ" not in msg.private_text


def test_labs_only_in_the_morning(monkeypatch, tmp_path):
    from datetime import datetime as real_dt

    from uniwa_notifier import config

    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    cfg = config.load()
    called = []

    class FakeEClass:
        def __init__(self, *a, **k):
            called.append("login")

    class FD(real_dt):
        @classmethod
        def now(cls, tz=None):
            return real_dt(2026, 11, 13, 21, 0, tzinfo=tz)

    monkeypatch.setattr(labs, "EClass", FakeEClass)
    monkeypatch.setattr(labs, "datetime", FD)
    assert labs.run(cfg) == 0
    assert called == []  # στις 21:00 δεν κάνει καν login
