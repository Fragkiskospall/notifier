from datetime import datetime

import pytest

from uniwa_notifier.text import clean_text, find_time, find_weekday, parse_dates


@pytest.mark.parametrize("text, expected", [
    ("Δευτέρα 26 Οκτωβρίου 2026 - 8:55 π.μ.", (2026, 10, 26, 8, 55)),
    ("Κυριακή 18 Ιανουαρίου 2026 - 11:55 μ.μ.", (2026, 1, 18, 23, 55)),
    ("Παρασκευή 1 Μαΐου 2026 - 12:00 μ.μ.", (2026, 5, 1, 12, 0)),
    ("Τρίτη 2 Ιουνίου 2026 - 12:30 π.μ.", (2026, 6, 2, 0, 30)),
    ("Πέμπτη 2 Ιουλίου 2026 - 9:00 π.μ.", (2026, 7, 2, 9, 0)),
    ("20/11/2026 18:00", (2026, 11, 20, 18, 0)),
    ("Τετάρτη 13 Νοεμβρίου 2019", (2019, 11, 13, 23, 59)),
])
def test_parse_dates(text, expected, tz):
    assert parse_dates(text, tz) == [datetime(*expected, tzinfo=tz)]


def test_parse_dates_none(tz):
    assert parse_dates("Χωρίς προθεσμία", tz) == []


@pytest.mark.parametrize("text, wd, time", [
    ("Τμήμα 8 Παρασκευή 16.00-17.00", 4, "16:00-17:00"),
    ("Πέμπτη_19:00-21:00_περιττοί", 3, "19:00-21:00"),
    ("2026 Τετάρτη 20:00~21:00", 2, "20:00-21:00"),
    ("ΤΜΗΜΑ 3 ΤΡΙΤΗ 9:00 - 11:00", 1, "09:00-11:00"),
    ("ΠΑΡ 13:00-15:00", 4, "13:00-15:00"),
    ("Γενική ομάδα", None, None),
])
def test_weekday_and_time(text, wd, time):
    assert find_weekday(text) == wd
    assert find_time(text) == time


def test_weekday_not_fooled_by_paradosi():
    # «Παράδοση» αρχίζει από «Παρα» αλλά δεν είναι Παρασκευή
    assert find_weekday("Παράδοση Εργασίας Τρίτη") == 1


def test_clean_text_strips_wordpress_footer():
    raw = "<p>Κείμενο</p><p>The post X first appeared on Y.</p>"
    assert clean_text(raw) == "Κείμενο"
