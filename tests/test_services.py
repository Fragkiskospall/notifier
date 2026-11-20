import json

import pytest

from uniwa_notifier.jobs import grades as grades_job
from uniwa_notifier.models import Grade
from uniwa_notifier.services import Services, ServicesError, parsers
from uniwa_notifier.state import SeenStore

SSO = "https://sso.uniwa.gr/login?service=https%3A%2F%2Fservices.uniwa.gr%2Flogin%2Fcas"


# ---------------------------------------------------------------- SSO

def test_cas_form(fixture):
    action, hidden = parsers.parse_cas_form(fixture("sso_login.html"), SSO)
    assert action == SSO
    assert hidden == {"lt": "LT-000000-EXAMPLE", "execution": "e1s1", "_eventId": "submit"}


def test_cas_error_message(fixture):
    assert "cannot be determined" in parsers.cas_error(fixture("sso_error.html"))


def test_cas_form_missing():
    with pytest.raises(ValueError):
        parsers.parse_cas_form("<html>maintenance</html>", SSO)


class _Resp:
    def __init__(self, url, text="", data=None, ctype="text/html"):
        self.url, self.text, self._data = url, text, data
        self.headers = {"content-type": ctype}
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeSession:
    """Μιμείται τη ροή: πύλη → SSO → (σωστός κωδικός) πίσω στην πύλη."""

    def __init__(self, sso_html, grades_data, portal_html="", password_ok=True, error_html="",
                 landing="https://services.uniwa.gr/?p=ABCDEF0123456789ABCDEF0123456789", profiles=None):
        self.landing, self.profiles = landing, profiles or {}
        self.headers, self.posted, self.api_headers = {}, None, None
        self.sso_html, self.grades_data, self.portal_html = sso_html, grades_data, portal_html
        self.ok, self.error_html = password_ok, error_html

    def get(self, url, headers=None, **kw):
        if url.endswith("/grades/all"):
            self.api_headers = headers
            if "X-Profile" not in (headers or {}):  # όπως η πραγματική πύλη
                return _Resp("https://services.uniwa.gr/", "<html>login</html>")
            return _Resp(url, data=self.grades_data, ctype="application/json")
        if url.endswith("/api/person/profiles"):
            return _Resp(url, data=self.profiles, ctype="application/json")
        if "?p=" in url:
            self.activated = url
            return _Resp(url, self.portal_html)
        return _Resp(SSO, self.sso_html)

    def post(self, url, data=None, **kw):
        self.posted = (url, data)
        if self.ok:
            return _Resp(self.landing, self.portal_html if "?p=" in self.landing else "<html><head></head></html>")
        return _Resp(SSO, self.error_html)


def test_login_and_fetch(fixture):
    data = json.loads(fixture("grades.json"))
    fake = _FakeSession(fixture("sso_login.html"), data, fixture("portal_home.html"))
    svc = Services("user", "pw", session=fake)
    svc.login()
    url, form = fake.posted
    assert url == SSO
    assert form == {"lt": "LT-000000-EXAMPLE", "execution": "e1s1", "_eventId": "submit",
                    "username": "user", "password": "pw"}
    assert [g.id for g in svc.grades()] == ["A1", "A2", "A3", "A4"]
    assert fake.api_headers["X-Profile"] == "ABCDEF0123456789ABCDEF0123456789"
    assert fake.api_headers["X-CSRF-TOKEN"] == "00000000-1111-2222-3333-444444444444"
    assert fake.activated == "https://services.uniwa.gr/?p=ABCDEF0123456789ABCDEF0123456789"


def test_portal_context_from_links_when_url_has_no_p(fixture):
    h = parsers.portal_context(fixture("portal_home.html"), "https://services.uniwa.gr/")
    assert h == {"X-Profile": "ABCDEF0123456789ABCDEF0123456789",
                 "X-CSRF-TOKEN": "00000000-1111-2222-3333-444444444444"}


def test_login_wrong_password(fixture):
    fake = _FakeSession(fixture("sso_login.html"), [], password_ok=False, error_html=fixture("sso_error.html"))
    with pytest.raises(ServicesError, match="cannot be determined"):
        Services("user", "bad", session=fake).login()


# ---------------------------------------------------------------- βαθμοί

def test_parse_grades_scale(fixture):
    g = {x.id: x for x in parsers.parse_grades(json.loads(fixture("grades.json")))}
    assert g["A1"].value == 3.5 and g["A1"].passed is False
    assert g["A2"].value == 7.0 and g["A2"].passed is True
    assert g["A3"].value == 6.0  # παλιά κλίμακα, βάση 5
    assert g["A4"].value is None
    assert g["A1"].period == "ΕΞΕΤΑΣΤΙΚΗ ΧΕΙΜΕΡΙΝΟΥ ΕΞΑΜΗΝΟΥ 2025-2026"
    assert g["A3"].period == "Εαρινή"


@pytest.mark.parametrize("v, s", [(3.5, "3,5"), (7.0, "7"), (8.25, "8,25"), (None, "-")])
def test_fmt_value(v, s):
    assert parsers.fmt_value(v) == s


def _g(id_, value, passed=False):
    return Grade(id_, "C", f"Μάθημα {id_}", value, passed, "Εξεταστική", 0)


def test_grade_changes(tmp_path):
    store = SeenStore(tmp_path / "seen.db")
    changes, first = store.grade_changes([_g("1", 3.5), _g("2", None)])
    assert first and changes == []  # πρώτη φορά: χωρίς ειδοποίηση

    # βγήκε βαθμός σε εγγραφή που δεν είχε + νέα προσπάθεια με βαθμό + νέα χωρίς βαθμό
    changes, first = store.grade_changes([_g("1", 3.5), _g("2", 6.0, True), _g("3", 8.0, True), _g("4", None)])
    assert not first
    assert [(g.id, prev) for g, prev in changes] == [("2", ""), ("3", None)]

    # διόρθωση βαθμού
    changes, _ = store.grade_changes([_g("1", 4.0), _g("2", 6.0, True), _g("3", 8.0, True), _g("4", None)])
    assert [(g.id, prev) for g, prev in changes] == [("1", "3.5")]

    changes, _ = store.grade_changes([_g("1", 4.0), _g("2", 6.0, True), _g("3", 8.0, True)])
    assert changes == []


def test_grades_message():
    msg = grades_job.build_message([(_g("1", 4.0), "3.5"), (_g("2", 7.0, True), None)])
    assert msg.title == "📝 2 νέοι βαθμοί"
    assert "❌ Μάθημα 1: 4 (ήταν 3,5)" in msg.text
    assert "✅ Μάθημα 2: 7" in msg.text
    assert "Μάθημα" not in msg.private_text and "4" not in msg.private_text


def test_login_lands_without_profile_uses_profiles_api(fixture):
    profiles = {"teacherProfiles": [], "studentProfiles": [
        {"id": "OLD" * 8, "studentNo": "111", "departmentCode": "100", "studentStatusId": "3"},
        {"id": "ABCDEF0123456789ABCDEF0123456789", "studentNo": "222", "departmentCode": "ICE",
         "studentStatusId": "1"},
    ]}
    data = json.loads(fixture("grades.json"))
    fake = _FakeSession(fixture("sso_login.html"), data, fixture("portal_home.html"),
                        landing="https://services.uniwa.gr/", profiles=profiles)
    svc = Services("user", "pw", session=fake)
    svc.login()
    assert fake.activated == "https://services.uniwa.gr/?p=ABCDEF0123456789ABCDEF0123456789"
    assert len(svc.grades()) == 4


@pytest.mark.parametrize("prefer, expected", [(None, "B" * 20), ("111", "A" * 20), ("100", "A" * 20)])
def test_pick_profile(prefer, expected):
    data = {"studentProfiles": [
        {"id": "A" * 20, "studentNo": "111", "departmentCode": "100", "studentStatusId": "3"},
        {"id": "B" * 20, "studentNo": "222", "departmentCode": "ICE", "studentStatusId": "1"},
    ]}
    assert parsers.pick_profile(data, prefer) == expected


def test_pick_profile_none():
    assert parsers.pick_profile({"studentProfiles": []}) is None
