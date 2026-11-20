"""Tests πάνω σε πραγματικές (ανωνυμοποιημένες) σελίδες του eClass ΠΑΔΑ.

Αν σπάσει κάποιο από αυτά μετά από ανανέωση των fixtures, άλλαξε το HTML
του eClass και πρέπει να προσαρμοστεί ο αντίστοιχος parser.
"""
from datetime import datetime

from uniwa_notifier.eclass import parsers

URL = "https://eclass.uniwa.gr/modules/work/index.php?course=ICE264"


def test_courses_from_portfolio(fixture):
    courses = parsers.parse_courses(fixture("portfolio.html"))
    assert len(courses) == 9
    assert courses["ICE243"] == "ΨΗΦΙΑΚΗ ΕΠΕΞΕΡΓΑΣΙΑ ΣΗΜΑΤΟΣ"
    assert "ICE268" in courses


def test_assignments_no_deadline_and_submitted(fixture, tz):
    items = parsers.parse_assignments(fixture("work_ICE264.html"), URL, "ΜΙΚΡΟΥΠΟΛΟΓΙΣΤΕΣ", tz)
    by_title = {a.title: a for a in items}
    assert set(by_title) == {"εργασία 2025", "lab1"}

    undated = by_title["εργασία 2025"]
    assert undated.deadline is None and undated.submitted is False and not undated.expired
    assert undated.link == "https://eclass.uniwa.gr/modules/work/index.php?course=ICE264&id=50974"

    lab1 = by_title["lab1"]
    assert lab1.deadline == datetime(2026, 10, 26, 8, 55, tzinfo=tz)
    assert lab1.submitted is True and lab1.expired is True


def test_assignments_expired_not_submitted(fixture, tz):
    (a,) = parsers.parse_assignments(fixture("work_ICE243.html"), URL, "ΨΕΣ", tz)
    assert a.deadline == datetime(2026, 1, 18, 23, 55, tzinfo=tz)
    assert a.submitted is False and a.expired is True


def test_no_assignments_page(fixture, tz):
    assert parsers.parse_assignments(fixture("work_CS174.html"), URL, "X", tz) == []
    assert not parsers.has_assignment_table(fixture("work_CS174.html"))


def test_disabled_tool_page(fixture, tz):
    assert parsers.parse_assignments(fixture("work_ICE319.html"), URL, "X", tz) == []


def test_assignment_start_date(fixture, tz):
    start = parsers.parse_assignment_start(fixture("assignment_50974.html"), tz)
    assert start == datetime(2025, 12, 17, 10, 56, tzinfo=tz)


def test_groups_member_detection(fixture):
    cases = {
        "group_ICE243.html": "Τμήμα 8 Παρασκευή 16.00-17.00",
        "group_ICE264.html": "Πέμπτη_19:00-21:00_περιττοί",
        "group_ICE316.html": "2026 Τετάρτη 20:00~21:00",
    }
    for name, expected in cases.items():
        mine = [g.name for g in parsers.parse_groups(fixture(name)) if g.member]
        assert mine == [expected], name


def test_groups_empty(fixture):
    assert parsers.parse_groups(fixture("group_CS174.html")) == []


def test_login_detection():
    assert parsers.is_logged_in('<a href="/logout">x</a>')
    assert not parsers.is_logged_in('<input name="pass" type="password">')
