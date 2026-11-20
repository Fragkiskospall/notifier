import datetime as dt

import pytest

from uniwa_notifier import catalog
from uniwa_notifier.catalog import CatalogError, parse


def _base(**over):
    raw = {
        "id": "x",
        "name": "Πανεπιστήμιο Χ",
        "short": "ΠΧ",
        "platform": "openeclass",
        "support": "eclass",
        "verified": dt.date(2026, 11, 20),
        "source": "https://example.gr/",
        "eclass": {"url": "https://eclass.example.gr", "auth": "auto"},
    }
    raw.update(over)
    return raw


def test_all_entries_load_and_are_unique():
    unis = catalog.load_all()
    assert len(unis) >= 15
    ids = [u.id for u in unis]
    assert len(ids) == len(set(ids))
    hosts = [u.eclass.url for u in unis if u.eclass]
    assert len(hosts) == len(set(hosts))


def test_supported_first_then_alphabetical():
    unis = catalog.load_all()
    levels = [catalog.SUPPORT_LEVELS.index(u.support) for u in unis]
    assert levels == sorted(levels)
    assert unis[0].id == "uniwa"


def test_uniwa_is_full_with_grades_and_ice_feed():
    u = catalog.get("uniwa")
    assert u.support == "full"
    assert u.eclass.url == "https://eclass.uniwa.gr"
    assert u.eclass.auth == "form"
    assert u.grades.adapter == "ilyda"
    assert u.grades.sso == "https://sso.uniwa.gr"
    assert u.department("ice").rss == "https://ice.uniwa.gr/feed/"


def test_every_supported_entry_has_https_eclass():
    for u in catalog.load_all():
        if u.is_supported:
            assert u.platform == "openeclass"
            assert u.eclass.url.startswith("https://")
        else:
            assert u.eclass is None


def test_extra_instances_parse():
    unipi = catalog.get("unipi")
    depts = {i.department for i in unipi.extra_eclass}
    assert "Πληροφορικής" in depts


def test_labels_are_greek():
    assert catalog.get("ntua").support_label == "Δεν υποστηρίζεται ακόμα"


@pytest.mark.parametrize(
    "over, msg",
    [
        ({"support": "maybe"}, "επίπεδο υποστήριξης"),
        ({"platform": "blackboard"}, "πλατφόρμα"),
        ({"verified": "χθες"}, "ημερομηνία"),
        ({"eclass": {"url": "http://eclass.example.gr"}}, "https"),
        ({"eclass": {"url": "https://e.gr", "auth": "magic"}}, "auth"),
        ({"support": "full"}, "βαθμούς"),
        ({"platform": "moodle", "support": "eclass"}, "μόνο Open eClass"),
    ],
)
def test_invalid_entries_are_rejected(over, msg):
    with pytest.raises(CatalogError, match=msg):
        parse(_base(**over))


def test_missing_field_is_reported():
    raw = _base()
    del raw["source"]
    with pytest.raises(CatalogError, match="source"):
        parse(raw)
