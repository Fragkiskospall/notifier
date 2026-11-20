"""Οι οθόνες του launcher (PySide6), όπως στο mockup του FragkiskOSource.

Ροή: Καλωσόρισμα → Πανεπιστήμιο → Σύνδεση → Ειδοποιήσεις → Εκτέλεση →
εγκατάσταση → Κατάσταση. Όλη η λογική είναι στο ``setup``· εδώ μόνο οθόνες.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
import threading
from collections.abc import Callable

import requests
from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import catalog, system
from .. import secrets as store_mod
from . import setup, theme

APP_TITLE = "FragkiskOSource Notifier"
STEPS = ("Πανεπιστήμιο", "Σύνδεση", "Ειδοποιήσεις", "Εκτέλεση")
JOB_LABELS = {"check": "Ανακοινώσεις", "grades": "Βαθμοί", "digest": "Σύνοψη εργασιών", "labs": "Εργαστήρια"}


# ---------------------------------------------------------------- βοηθητικά

def label(text: str, role: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse if role == "mono"
                               else Qt.TextInteractionFlag.NoTextInteraction)
    return lb


def button(text: str, kind: str | None = None, on_click: Callable | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        b.clicked.connect(on_click)
    return b


def card(role: str = "card") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setProperty("role", role)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(6)
    return f, lay


def restyle(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


def logo_pixmap(size: int = 44) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PySide6.QtGui import QColor, QPen

    p.setPen(QPen(QColor(theme.TEXT), max(1.2, size / 18)))
    r = size * 0.43
    c = size / 2
    p.drawEllipse(int(c - r), int(c - r), int(2 * r), int(2 * r))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.ACCENT))
    s = size * 0.32
    p.drawEllipse(int(c - s / 2), int(c - s / 2), int(s), int(s))
    p.end()
    return pm


def qr_pixmap(data: str, px: int = 168) -> QPixmap:
    import io

    import segno

    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=8, border=2, dark=theme.BG, light=theme.TEXT)
    pm = QPixmap()
    pm.loadFromData(buf.getvalue(), "PNG")
    return pm.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class _Relay(QObject):
    done = Signal(object)
    failed = Signal(str)


_running: set[_Relay] = set()


def run_async(fn: Callable[[], object], on_done: Callable[[object], None],
              on_error: Callable[[str], None] | None = None) -> None:
    """Τρέχει κάτι αργό (δίκτυο, εγκατάσταση) χωρίς να «παγώνει» το παράθυρο."""
    relay = _Relay()
    _running.add(relay)

    def finish_ok(v):
        _running.discard(relay)
        on_done(v)

    def finish_err(m):
        _running.discard(relay)
        (on_error or (lambda _m: None))(m)

    relay.done.connect(finish_ok)
    relay.failed.connect(finish_err)

    def work():
        try:
            relay.done.emit(fn())
        except Exception as e:  # εμφανίζεται στον χρήστη, όχι traceback
            relay.failed.emit(str(e) or e.__class__.__name__)

    threading.Thread(target=work, daemon=True).start()


def spawn_job(args: list[str]) -> None:
    """Ξεκινά ένα job στο παρασκήνιο, χωρίς παράθυρο κονσόλας."""
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(system.launch_command(args), cwd=str(system.current().app_dir), **kwargs)


# ---------------------------------------------------------------- σκελετός

class Sidebar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 28, 16, 24)
        lay.setSpacing(4)
        self.items: list[tuple[QLabel, QLabel]] = []
        for i, name in enumerate(STEPS, 1):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 12, 8)
            h.setSpacing(12)
            dot = QLabel(str(i))
            dot.setFixedSize(24, 24)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt = QLabel(name)
            h.addWidget(dot)
            h.addWidget(txt, 1)
            lay.addWidget(row)
            self.items.append((dot, txt))
            row.setObjectName(f"step{i}")
        lay.addStretch(1)
        note = label("Οι κωδικοί σου δεν περνάνε ποτέ από δικό μας server.", "faint", wrap=True)
        note.setContentsMargins(12, 0, 12, 0)
        lay.addWidget(note)

    def set_step(self, index: int) -> None:
        for i, (dot, txt) in enumerate(self.items):
            if i < index:
                dot.setText("✓")
                dot.setStyleSheet(f"border:1px solid {theme.ACCENT}; color:{theme.ACCENT}; border-radius:12px;")
                txt.setStyleSheet(f"color:{theme.MUTED};")
            elif i == index:
                dot.setText(str(i + 1))
                dot.setStyleSheet(f"background:{theme.ACCENT}; color:{theme.BG}; border-radius:12px; font-weight:600;")
                txt.setStyleSheet(f"color:{theme.TEXT}; font-weight:600;")
            else:
                dot.setText(str(i + 1))
                dot.setStyleSheet(f"border:1px solid #3a3a40; color:{theme.FAINT}; border-radius:12px;")
                txt.setStyleSheet(f"color:{theme.FAINT};")


class StepPage(QWidget):
    """Μία οθόνη του οδηγού: τίτλος, περιεχόμενο, και αν μπορεί να συνεχίσει."""

    changed = Signal()

    def __init__(self, number: int, title: str, subtitle: str) -> None:
        super().__init__()
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(48, 36, 48, 0)
        self.body.setSpacing(0)
        self.body.addWidget(label(f"ΒΗΜΑ {number} ΑΠΟ {len(STEPS)}", "eyebrow"))
        self.body.addSpacing(8)
        self.body.addWidget(label(title, "h1"))
        self.body.addSpacing(6)
        self.body.addWidget(label(subtitle, "muted", wrap=True))
        self.body.addSpacing(22)

    def can_continue(self) -> bool:
        return True

    def on_enter(self) -> None:  # noqa: B027 (προαιρετικό hook)
        pass


# ---------------------------------------------------------------- οθόνες οδηγού

class WelcomePage(QWidget):
    start = Signal()

    def __init__(self) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(56, 64, 56, 56)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(44))
        lv.addWidget(logo)
        lv.addSpacing(32)
        lv.addWidget(label("Μην ξαναχάσεις\nανακοίνωση.", "display"))
        lv.addSpacing(20)
        lv.addWidget(label("Ο Notifier ελέγχει το eClass και την πύλη φοιτητών για σένα. "
                           "Ρυθμίζεται μία φορά, χωρίς να ανοίξεις κανένα αρχείο.", "muted", wrap=True))
        lv.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(button("Ξεκίνα τη ρύθμιση  →", "primary", self.start.emit))
        row.addSpacing(16)
        row.addWidget(label("περίπου 2 λεπτά", "faint"))
        row.addStretch(1)
        lv.addLayout(row)

        right = QWidget()
        right.setObjectName("Sidebar")
        right.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(44, 56, 44, 56)
        rv.addStretch(1)
        for title, text in (
            ("Ανακοινώσεις και βαθμοί", "Μόλις αναρτηθούν, στο κινητό σου."),
            ("Εργασίες και εργαστήρια", "Σύνοψη προθεσμιών και υπενθύμιση το πρωί."),
            ("Οι κωδικοί μένουν δικοί σου", "Δεν περνάνε ποτέ από δικό μας server."),
        ):
            rv.addWidget(label(title, "h2"))
            rv.addSpacing(4)
            rv.addWidget(label(text, "muted", wrap=True))
            rv.addSpacing(26)
        rv.addStretch(1)

        outer.addWidget(left, 11)
        outer.addWidget(right, 9)


class UniversityPage(StepPage):
    def __init__(self) -> None:
        super().__init__(1, "Πού σπουδάζεις;", "Τα υπόλοιπα τα βρίσκουμε μόνοι μας.")
        self.unis = catalog.load_all()
        self.body.addWidget(label("Πανεπιστήμιο", "muted"))
        self.body.addSpacing(6)
        self.uni = QComboBox()
        for u in self.unis:
            suffix = "" if u.is_supported else "  (δεν υποστηρίζεται ακόμα)"
            self.uni.addItem(f"{u.name} ({u.short}){suffix}", u.id)
            if not u.is_supported:
                item = self.uni.model().item(self.uni.count() - 1)
                item.setEnabled(False)
        self.body.addWidget(self.uni)
        self.body.addSpacing(14)
        self.body.addWidget(label("Τμήμα", "muted"))
        self.body.addSpacing(6)
        self.dept = QComboBox()
        self.body.addWidget(self.dept)
        self.body.addSpacing(16)

        self.info, info_lay = card()
        self.info_title = label("✓  Βρέθηκαν αυτόματα", "accent")
        info_lay.addWidget(self.info_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        self.cells: dict[str, QLabel] = {}
        for i, key in enumerate(("eClass", "Ανακοινώσεις τμήματος", "Βαθμοί", "Υποστήριξη")):
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.addWidget(label(key, "faint"))
            val = label("", "mono")
            cell.addWidget(val)
            self.cells[key] = val
            grid.addLayout(cell, i // 2, i % 2)
        info_lay.addSpacing(6)
        info_lay.addLayout(grid)
        self.body.addWidget(self.info)
        self.body.addStretch(1)

        self.uni.currentIndexChanged.connect(self._refresh)
        self.dept.currentIndexChanged.connect(self._refresh_dept)
        self._refresh()

    @property
    def university(self) -> catalog.University:
        return catalog.get(self.uni.currentData())

    @property
    def department(self) -> str | None:
        return self.dept.currentData()

    def _refresh(self) -> None:
        u = self.university
        self.dept.blockSignals(True)
        self.dept.clear()
        for d in u.departments:
            self.dept.addItem(d.name, d.id)
        self.dept.addItem("Άλλο τμήμα" if u.departments else "Όλα τα τμήματα", None)
        self.dept.blockSignals(False)
        self.cells["eClass"].setText(u.eclass.url.removeprefix("https://") if u.eclass else "-")
        self.cells["Βαθμοί"].setText("Υποστηρίζονται" if u.grades else "Όχι ακόμα")
        self.cells["Υποστήριξη"].setText(u.support_label)
        self._refresh_dept()
        self.changed.emit()

    def _refresh_dept(self) -> None:
        d = self.university.department(self.department or "")
        self.cells["Ανακοινώσεις τμήματος"].setText(d.rss.split("//")[1].split("/")[0] if d and d.rss else "Μόνο eClass")

    def can_continue(self) -> bool:
        return self.university.is_supported


class LoginPage(StepPage):
    def __init__(self, uni_page: UniversityPage) -> None:
        super().__init__(2, "Σύνδεση", "Τα ίδια στοιχεία που βάζεις στο eClass.")
        self.uni_page = uni_page
        self.verified_for: tuple[str, str, str] | None = None

        self.body.addWidget(label("Όνομα χρήστη", "muted"))
        self.body.addSpacing(6)
        self.user = QLineEdit()
        self.user.setPlaceholderText("π.χ. ice12345678")
        self.user.setMaximumWidth(460)
        self.body.addWidget(self.user)
        self.body.addSpacing(14)
        self.body.addWidget(label("Κωδικός", "muted"))
        self.body.addSpacing(6)
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setMaximumWidth(460)
        self.body.addWidget(self.pw)
        self.body.addSpacing(14)
        row = QHBoxLayout()
        self.check_btn = button("Έλεγχος σύνδεσης", None, self.verify)
        row.addWidget(self.check_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.body.addSpacing(16)

        self.result, rl = card("success")
        self.result_text = label("", None, wrap=True)
        rl.addWidget(self.result_text)
        self.result.setMaximumWidth(460)
        self.result.hide()
        self.body.addWidget(self.result)
        self.body.addSpacing(14)
        self.body.addWidget(label(f"🔒  Αποθηκεύεται με ασφάλεια στον υπολογιστή σου ({store_mod.STORE}), "
                                  "όχι σε αρχείο.", "faint"))
        self.body.addStretch(1)

        self.user.textChanged.connect(lambda *_: self.changed.emit())
        self.pw.textChanged.connect(lambda *_: self.changed.emit())
        self.pw.returnPressed.connect(self.verify)

    def _key(self) -> tuple[str, str, str]:
        return (self.uni_page.university.id, self.user.text().strip(), self.pw.text())

    def verify(self) -> None:
        key = self._key()
        if not key[1] or not key[2]:
            return
        self.check_btn.setEnabled(False)
        self.check_btn.setText("Έλεγχος…")
        self.result.hide()
        run_async(lambda: setup.verify_login(*key), lambda r: self._show(key, r),
                  lambda m: self._show(key, setup.LoginResult(False, m)))

    def _show(self, key, r: setup.LoginResult) -> None:
        self.check_btn.setEnabled(True)
        self.check_btn.setText("Έλεγχος σύνδεσης")
        self.result.setProperty("role", "success" if r.ok else "error")
        restyle(self.result)
        self.result_text.setText(("✓  " if r.ok else "✗  ") + r.message)
        self.result.show()
        self.verified_for = key if r.ok else None
        self.changed.emit()

    def can_continue(self) -> bool:
        return self.verified_for == self._key()


class NotifyPage(StepPage):
    def __init__(self, topic: str) -> None:
        super().__init__(3, "Πού να σε ειδοποιώ;", "Μπορείς να τα αλλάξεις όποτε θες.")
        self.topic = topic
        cols = QHBoxLayout()
        cols.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(10)

        self.mobile = QCheckBox("Κινητό")
        self.desktop = QCheckBox("Αυτός ο υπολογιστής")
        self.private = QCheckBox("Ιδιωτικά στο κινητό")
        for cb, desc in (
            (self.mobile, "Push μέσω της δωρεάν εφαρμογής ntfy. Σκάναρε το QR."),
            (self.desktop, "Ειδοποίηση συστήματος, με όλο το περιεχόμενο."),
            (self.private, "Στο κινητό μόνο «Νέα ανακοίνωση», χωρίς κείμενο."),
        ):
            cb.setChecked(True)
            left.addWidget(cb)
            d = label(desc, "faint", wrap=True)
            d.setContentsMargins(28, 0, 0, 6)
            left.addWidget(d)
            cb.toggled.connect(lambda *_: self.changed.emit())
        left.addSpacing(8)
        tests = QHBoxLayout()
        tests.addWidget(button("Δοκιμή στον υπολογιστή", None, self.test_desktop))
        tests.addStretch(1)
        left.addLayout(tests)
        self.test_note = label("", "faint", wrap=True)
        left.addWidget(self.test_note)
        left.addStretch(1)

        self.qr_card, ql = card()
        self.qr_card.setFixedWidth(232)
        qr = QLabel()
        qr.setPixmap(qr_pixmap(setup.ntfy_subscribe_url(topic)))
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ql.addWidget(qr)
        ql.addSpacing(6)
        hint = label("Άνοιξε το ntfy στο κινητό και σκάναρε. Το κανάλι φτιάχτηκε μόνο για σένα.", "faint", wrap=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ql.addWidget(hint)
        ql.addSpacing(6)
        ql.addWidget(button("Στείλε δοκιμή", None, self.test_mobile))

        cols.addLayout(left, 1)
        cols.addWidget(self.qr_card)
        self.body.addLayout(cols)
        self.body.addStretch(1)
        self.mobile.toggled.connect(self.qr_card.setVisible)

    def test_desktop(self) -> None:
        ok = system.current().notify("FragkiskOSource Notifier", "Δοκιμαστική ειδοποίηση ✓")
        self.test_note.setText("Στάλθηκε." if ok else "Δεν εμφανίστηκε ειδοποίηση. Έλεγξε τις ρυθμίσεις ειδοποιήσεων.")

    def test_mobile(self) -> None:
        url = setup.ntfy_subscribe_url(self.topic)

        def send():
            requests.post(url, data="Δοκιμαστική ειδοποίηση ✓".encode(), timeout=15,
                          headers={"Title": "FragkiskOSource Notifier"}).raise_for_status()
            return True

        self.test_note.setText("Αποστολή…")
        run_async(send, lambda _r: self.test_note.setText("Στάλθηκε στο κινητό."),
                  lambda m: self.test_note.setText(f"Δεν στάλθηκε: {m}"))


class RunPage(StepPage):
    def __init__(self) -> None:
        super().__init__(4, "Πού θα τρέχει;", "Μπορείς να το αλλάξεις αργότερα.")
        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.group = QButtonGroup(self)
        self.local = QRadioButton("Μόνο σε αυτόν τον υπολογιστή")
        self.cloud = QRadioButton("24/7 στο cloud")
        self.local.setChecked(True)
        self.cloud.setEnabled(False)
        for rb, text, tag in (
            (self.local, "Χωρίς λογαριασμό. Ελέγχει όσο ο υπολογιστής είναι ανοιχτός "
                         "και καλύπτει ό,τι έχασε μόλις ξυπνήσει.", None),
            (self.cloud, "Τρέχει και με κλειστό υπολογιστή, στο δικό σου δωρεάν GitHub.", "σύντομα"),
        ):
            f, lay = card()
            f.setProperty("selected", "true" if rb is self.local else "false")
            top = QHBoxLayout()
            top.addWidget(rb)
            top.addStretch(1)
            if tag:
                top.addWidget(label(tag, "faint"))
            lay.addLayout(top)
            lay.addWidget(label(text, "muted", wrap=True))
            cards.addWidget(f, 1)
            self.group.addButton(rb)
        self.body.addLayout(cards)
        self.body.addSpacing(18)

        row = QHBoxLayout()
        row.setSpacing(24)
        col1 = QVBoxLayout()
        col1.addWidget(label("Έλεγχος για νέα", "muted"))
        self.every = QComboBox()
        for minutes, text in ((30, "Κάθε 30 λεπτά"), (60, "Κάθε ώρα"), (120, "Κάθε 2 ώρες")):
            self.every.addItem(text, minutes)
        col1.addWidget(self.every)
        col2 = QVBoxLayout()
        col2.addWidget(label("Σύνοψη εργασιών (ώρες, με κόμμα)", "muted"))
        self.times = QLineEdit("08:00, 14:00, 21:00")
        col2.addWidget(self.times)
        row.addLayout(col1, 1)
        row.addLayout(col2, 2)
        self.body.addLayout(row)
        self.times_error = label("", "faint")
        self.body.addWidget(self.times_error)
        self.body.addSpacing(10)
        self.consent = QCheckBox("Επιτρέπω στον Notifier να δημιουργήσει αυτόματους ελέγχους στο παρασκήνιο.")
        self.body.addWidget(self.consent)
        self.body.addStretch(1)
        self.consent.toggled.connect(lambda *_: self.changed.emit())
        self.times.textChanged.connect(lambda *_: self.changed.emit())

    def digest_times(self) -> tuple[str, ...] | None:
        parts = tuple(p.strip() for p in self.times.text().split(",") if p.strip())
        try:
            system.Job("digest", ("digest",), at=parts)
        except ValueError:
            return None
        return parts

    def can_continue(self) -> bool:
        ok_times = self.digest_times() is not None
        self.times_error.setText("" if ok_times else "Γράψε ώρες σε μορφή ΩΩ:ΛΛ, π.χ. 08:00, 21:00")
        return ok_times and self.consent.isChecked()


class InstallPage(QWidget):
    finished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(56, 64, 56, 56)
        lay.addWidget(label("ΕΓΚΑΤΑΣΤΑΣΗ", "eyebrow"))
        lay.addSpacing(8)
        self.title = label("Στήνω τον Notifier…", "h1")
        lay.addWidget(self.title)
        lay.addSpacing(24)
        self.lines = QVBoxLayout()
        self.lines.setSpacing(12)
        lay.addLayout(self.lines)
        lay.addStretch(1)
        self.retry = button("Πίσω", None)
        self.retry.hide()
        lay.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignLeft)

    def add_line(self, text: str) -> None:
        self.lines.addWidget(label("✓  " + text, "muted"))

    def run(self, choices: setup.Choices) -> None:
        relay = _Relay()

        def progress(msg: str) -> None:
            relay.done.emit(("step", msg))

        def on_step(v):
            if isinstance(v, tuple) and v[0] == "step":
                self.add_line(v[1])

        relay.done.connect(on_step)
        _running.add(relay)

        def done(_installed):
            _running.discard(relay)
            self.finished.emit(True, "")

        def failed(msg):
            _running.discard(relay)
            self.title.setText("Η εγκατάσταση δεν ολοκληρώθηκε")
            self.lines.addWidget(label("✗  " + msg, None, wrap=True))
            self.retry.show()
            self.finished.emit(False, msg)

        run_async(lambda: setup.apply(choices, progress=progress), done, failed)


class Wizard(QWidget):
    completed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.topic = setup.new_topic()
        root = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        self.welcome = WelcomePage()
        self.welcome.start.connect(lambda: root.setCurrentIndex(1))
        root.addWidget(self.welcome)

        steps_box = QWidget()
        h = QHBoxLayout(steps_box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = Sidebar()
        h.addWidget(self.sidebar)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.stack = QStackedWidget()
        self.uni = UniversityPage()
        self.login = LoginPage(self.uni)
        self.notify = NotifyPage(self.topic)
        self.run_page = RunPage()
        self.pages: list[StepPage] = [self.uni, self.login, self.notify, self.run_page]
        for p in self.pages:
            self.stack.addWidget(p)
            p.changed.connect(self._update_buttons)
        right.addWidget(self.stack, 1)

        footer = QWidget()
        footer.setObjectName("Footer")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(48, 16, 48, 22)
        self.back = button("Πίσω", "ghost", self._back)
        self.next = button("Συνέχεια", "primary", self._next)
        fl.addWidget(self.back)
        fl.addStretch(1)
        fl.addWidget(self.next)
        right.addWidget(footer)
        h.addLayout(right, 1)
        root.addWidget(steps_box)

        self.install = InstallPage()
        self.install.finished.connect(self._installed)
        self.install.retry.clicked.connect(lambda: root.setCurrentIndex(1))
        root.addWidget(self.install)
        self.root = root
        self._go(0)

    def _go(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        self.sidebar.set_step(i)
        self.pages[i].on_enter()
        self.next.setText("Ολοκλήρωση" if i == len(self.pages) - 1 else "Συνέχεια")
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.next.setEnabled(self.pages[self.stack.currentIndex()].can_continue())

    def _back(self) -> None:
        i = self.stack.currentIndex()
        if i == 0:
            self.root.setCurrentIndex(0)
        else:
            self._go(i - 1)

    def _next(self) -> None:
        i = self.stack.currentIndex()
        if i == 1 and not self.login.can_continue():
            self.login.verify()
            return
        if i < len(self.pages) - 1:
            self._go(i + 1)
            return
        self.root.setCurrentIndex(2)
        self.install.run(self.choices())

    def choices(self) -> setup.Choices:
        return setup.Choices(
            university=self.uni.university.id,
            department=self.uni.department,
            username=self.login.user.text().strip(),
            password=self.login.pw.text(),
            notify_mobile=self.notify.mobile.isChecked(),
            notify_desktop=self.notify.desktop.isChecked(),
            private=self.notify.private.isChecked(),
            every_minutes=self.run_page.every.currentData(),
            digest_at=self.run_page.digest_times() or ("08:00",),
            ntfy_topic=self.topic,
        )

    def _installed(self, ok: bool, _msg: str) -> None:
        if ok:
            QTimer.singleShot(600, self.completed.emit)


# ---------------------------------------------------------------- κατάσταση & απόρρητο

def _when(t: dt.datetime | None) -> str:
    if t is None:
        return "δεν έχει τρέξει"
    now = dt.datetime.now(t.tzinfo)
    if t.date() == now.date():
        return t.strftime("%H:%M")
    if t.date() == (now - dt.timedelta(days=1)).date():
        return "χθες " + t.strftime("%H:%M")
    return t.strftime("%d/%m %H:%M")


class StatusPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(0)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        self.eyebrow = label("", "eyebrow")
        self.headline = label("", "display")
        titles.addWidget(self.eyebrow)
        titles.addSpacing(8)
        titles.addWidget(self.headline)
        top.addLayout(titles, 1)
        top.addWidget(button("Στείλε δοκιμή", None, lambda: spawn_job(["test"])), 0, Qt.AlignmentFlag.AlignTop)
        top.addSpacing(8)
        self.check_now = button("Έλεγξε τώρα", "primary", self._check_now)
        top.addWidget(self.check_now, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(top)
        lay.addSpacing(24)

        grid = QHBoxLayout()
        grid.setSpacing(10)
        self.stats: list[tuple[QLabel, QLabel]] = []
        for title in ("Τελευταίος έλεγχος", "Επόμενη σύνοψη", "Πανεπιστήμιο"):
            f, fl = card()
            fl.addWidget(label(title, "muted"))
            big, sub = label("", "big"), label("", "faint")
            fl.addWidget(big)
            fl.addWidget(sub)
            grid.addWidget(f, 1)
            self.stats.append((big, sub))
        lay.addLayout(grid)
        lay.addSpacing(24)
        lay.addWidget(label("Αυτόματοι έλεγχοι", "h2"))
        lay.addSpacing(8)
        self.jobs = QVBoxLayout()
        self.jobs.setSpacing(0)
        lay.addLayout(self.jobs)
        lay.addStretch(1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30_000)
        self.refresh()

    def _check_now(self) -> None:
        spawn_job(["check"])
        self.check_now.setText("Ελέγχει…")
        self.check_now.setEnabled(False)
        QTimer.singleShot(20_000, self._reset_check)

    def _reset_check(self) -> None:
        self.check_now.setText("Έλεγξε τώρα")
        self.check_now.setEnabled(True)
        self.refresh()

    def refresh(self) -> None:
        jobs = setup.status()
        healthy = bool(jobs) and all(j.active and j.last_ok is not False for j in jobs)
        self.eyebrow.setText(("●  ΕΝΕΡΓΟ · " if jobs else "○  ") + "ΣΤΟΝ ΥΠΟΛΟΓΙΣΤΗ")
        self.eyebrow.setStyleSheet(f"color:{theme.ACCENT if healthy else theme.DANGER};")
        self.headline.setText("Όλα λειτουργούν." if healthy else
                              ("Κάτι δεν πήγε καλά." if jobs else "Οι έλεγχοι δεν τρέχουν."))
        check = next((j for j in jobs if j.name == "check"), None)
        every, times = setup.configured_schedule()
        now = dt.datetime.now().astimezone()
        self.stats[0][0].setText(_when(check.last_run if check else None))
        self.stats[0][1].setText(f"κάθε {every}′")
        nxt = setup.next_time(times, now) if times else None
        self.stats[1][0].setText(nxt.strftime("%H:%M") if nxt else "-")
        self.stats[1][1].setText(" · ".join(times))
        uni = setup.configured_university()
        self.stats[2][0].setText(uni.short if uni else "-")
        self.stats[2][1].setText(uni.support_label if uni else "")

        while self.jobs.count():
            item = self.jobs.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for j in jobs:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 10, 0, 10)
            ok = j.active and j.last_ok is not False
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{theme.ACCENT if ok else theme.DANGER};")
            h.addWidget(dot)
            h.addSpacing(8)
            h.addWidget(QLabel(JOB_LABELS.get(j.name, j.name)), 1)
            h.addWidget(label(_when(j.last_run) + ("" if j.last_ok is not False else " · απέτυχε"), "faint"))
            self.jobs.addWidget(row)
            sep = QFrame()
            sep.setProperty("role", "line")
            self.jobs.addWidget(sep)


class PrivacyPage(QWidget):
    removed = Signal()

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(0)
        title = QLabel(f'Τι ξέρουμε για σένα; <span style="color:{theme.ACCENT}">Τίποτα.</span>')
        title.setProperty("role", "h1")
        title.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(title)
        lay.addSpacing(20)

        rows = [
            ("Κωδικοί", store_mod.STORE, "Από το λειτουργικό", "Μόνο εσύ"),
            ("Ρυθμίσεις, ιστορικό", "Φάκελος εφαρμογής", "AES-256-GCM", "Μόνο εσύ"),
            ("Push στο κινητό", "Περνά από το ntfy.sh", "Χωρίς περιεχόμενο", "Κανείς το κείμενο"),
            ("FragkiskOSource", "Δεν υπάρχει server", "Χωρίς analytics", "Τίποτα"),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(0)
        for c, head in enumerate(("ΔΕΔΟΜΕΝΟ", "ΠΟΥ ΖΕΙ", "ΠΡΟΣΤΑΣΙΑ", "ΠΟΙΟΣ ΤΟ ΒΛΕΠΕΙ")):
            grid.addWidget(label(head, "eyebrow"), 0, c)
        for r, row in enumerate(rows, 1):
            for c, text in enumerate(row):
                lb = label(text, "h2" if c == 0 else ("accent" if text == "Τίποτα" else "muted"), wrap=True)
                lb.setContentsMargins(0, 10, 0, 10)
                grid.addWidget(lb, r, c)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        lay.addLayout(grid)
        lay.addSpacing(28)

        actions = QHBoxLayout()
        actions.addWidget(button("Άνοιξε τον φάκελο", None, self._open_folder))
        actions.addStretch(1)
        actions.addWidget(button("Διαγραφή όλων", "danger", self._remove))
        lay.addLayout(actions)
        lay.addSpacing(12)
        lay.addWidget(label("Η διαγραφή σβήνει αυτόματους ελέγχους, κωδικούς, ρυθμίσεις και ιστορικό.", "faint"))
        lay.addStretch(1)

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(system.current().app_dir)))

    def _remove(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Διαγραφή όλων")
        box.setText("Να σβηστούν όλα;")
        box.setInformativeText("Οι αυτόματοι έλεγχοι, οι κωδικοί, οι ρυθμίσεις και το ιστορικό θα διαγραφούν. "
                               "Δεν αναιρείται.")
        yes = box.addButton("Διαγραφή", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Άκυρο", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            setup.remove_everything()
            self.removed.emit()


class Dashboard(QWidget):
    removed = Signal()

    def __init__(self) -> None:
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        nav = QWidget()
        nav.setObjectName("Sidebar")
        nav.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nav.setFixedWidth(200)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(12, 24, 12, 24)
        nl.setSpacing(2)
        self.stack = QStackedWidget()
        self.status = StatusPage()
        self.privacy = PrivacyPage()
        self.privacy.removed.connect(self.removed.emit)
        self.stack.addWidget(self.status)
        self.stack.addWidget(self.privacy)
        group = QButtonGroup(self)
        for i, name in enumerate(("Κατάσταση", "Απόρρητο")):
            b = button(name, "nav", lambda _c=False, i=i: self._show(i))
            b.setCheckable(True)
            b.setChecked(i == 0)
            group.addButton(b)
            nl.addWidget(b)
        nl.addStretch(1)
        os_name = {"macos": "macOS", "windows": "Windows"}.get(system.current().name, system.current().name)
        nl.addWidget(label(f"v{_version()} · {os_name}", "faint"))
        h.addWidget(nav)
        h.addWidget(self.stack, 1)

    def _show(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        if i == 0:
            self.status.refresh()


def _version() -> str:
    from .. import __version__

    return __version__


# ---------------------------------------------------------------- παράθυρο

class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(960, 640)
        self.setWindowIcon(QIcon(logo_pixmap(64)))
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.current: QWidget | None = None
        if setup.is_configured():
            self.show_dashboard()
        else:
            self.show_wizard()

    def _swap(self, w: QWidget) -> None:
        if self.current is not None:
            self.lay.removeWidget(self.current)
            self.current.deleteLater()
        self.current = w
        self.lay.addWidget(w)

    def show_wizard(self) -> None:
        wiz = Wizard()
        wiz.completed.connect(self.show_dashboard)
        self._swap(wiz)

    def show_dashboard(self) -> None:
        dash = Dashboard()
        dash.removed.connect(self.show_wizard)
        self._swap(dash)


def build_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyleSheet(theme.QSS)
    font = QFont()
    font.setFamilies(["Inter Tight", "Segoe UI Variable", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial"])
    font.setPointSize(10 if sys.platform == "win32" else 13)
    app.setFont(font)
    return app


def run() -> int:
    app = build_app()
    win = MainWindow()
    win.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    win.show()
    return app.exec()
