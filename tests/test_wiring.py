"""Ελέγχει ότι τα jobs δένουν σωστά: fetch → state → notify, χωρίς δίκτυο."""
from uniwa_notifier import cli
from uniwa_notifier.jobs import announcements
from uniwa_notifier.models import Item


def _setup(monkeypatch, tmp_path, items, sent, fail=False):
    monkeypatch.setenv("UNIWA_HOME", str(tmp_path))
    monkeypatch.setattr(announcements, "fetch_department", lambda cfg, s: {"dept": list(items)})
    monkeypatch.setattr(announcements, "fetch_eclass", lambda cfg, s: {})

    def fake_notify(cfg, new):
        if fail:
            raise RuntimeError("SMTP down")
        sent.extend(new)
    monkeypatch.setattr(announcements.notify, "announcements", fake_notify)


def test_check_end_to_end(monkeypatch, tmp_path):
    sent: list[Item] = []
    items = [Item("dept:1", "Τμήμα", "Α", "https://x/1")]
    _setup(monkeypatch, tmp_path, items, sent)
    assert cli.main(["check"]) == 0 and sent == []          # πρώτη φορά: seed

    items.append(Item("dept:2", "Τμήμα", "Β", "https://x/2"))
    assert cli.main(["check", "--dry-run"]) == 0 and sent == []  # dry-run: τίποτα
    assert cli.main(["check"]) == 0 and [i.uid for i in sent] == ["dept:2"]
    assert cli.main(["check"]) == 0 and len(sent) == 1      # όχι διπλό


def test_failed_send_is_retried(monkeypatch, tmp_path):
    sent: list[Item] = []
    items = [Item("dept:1", "Τμήμα", "Α", "https://x/1")]
    _setup(monkeypatch, tmp_path, items, sent)
    cli.main(["check"])
    items.append(Item("dept:2", "Τμήμα", "Β", "https://x/2"))

    _setup(monkeypatch, tmp_path, items, sent, fail=True)
    assert cli.main(["check"]) == 1

    _setup(monkeypatch, tmp_path, items, sent)
    assert cli.main(["check"]) == 0 and [i.uid for i in sent] == ["dept:2"]
