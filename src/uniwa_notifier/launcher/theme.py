"""Χρώματα και στυλ του launcher, ίδια με το site και το mockup του FragkiskOSource."""

BG = "#0a0a0b"
PANEL = "#0f0f11"
CARD = "#111113"
LINE = "#1c1c1f"
LINE_STRONG = "#2a2a2e"
TEXT = "#ededed"
MUTED = "#a1a1a6"
FAINT = "#8b8b91"
ACCENT = "#d4ff3f"
DANGER = "#ff8a80"

SANS = '"Inter Tight", "Segoe UI Variable", "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial'
MONO = '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace'

QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: {SANS}; font-size: 14px; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {LINE_STRONG}; padding: 6px; }}

#Sidebar {{ background: {PANEL}; border-right: 1px solid {LINE}; }}
#Sidebar QWidget {{ background: transparent; }}
#Footer {{ border-top: 1px solid {LINE}; }}

QLabel {{ background: transparent; }}
QLabel[role="eyebrow"] {{ color: {FAINT}; font-family: {MONO}; font-size: 11px; letter-spacing: 1px; }}
QLabel[role="display"] {{ font-size: 46px; font-weight: 300; }}
QLabel[role="h1"] {{ font-size: 28px; font-weight: 400; }}
QLabel[role="h2"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="faint"] {{ color: {FAINT}; font-size: 12px; }}
QLabel[role="mono"] {{ font-family: {MONO}; font-size: 13px; }}
QLabel[role="big"] {{ font-family: {MONO}; font-size: 22px; }}
QLabel[role="accent"] {{ color: {ACCENT}; }}

QPushButton {{
    min-height: 40px; padding: 0 20px; border-radius: 20px;
    border: 1px solid {LINE_STRONG}; background: transparent; color: {TEXT};
}}
QPushButton:hover {{ border-color: #4a4a50; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {LINE}; }}
QPushButton[kind="primary"] {{ background: {ACCENT}; color: {BG}; border: none; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: #e0ff70; }}
QPushButton[kind="primary"]:disabled {{ background: #2a2a2e; color: {FAINT}; }}
QPushButton[kind="ghost"] {{ border: none; color: {MUTED}; }}
QPushButton[kind="ghost"]:hover {{ color: {TEXT}; }}
QPushButton[kind="danger"] {{ border-color: #5a2a2a; color: {DANGER}; }}
QPushButton[kind="nav"] {{
    border: none; border-radius: 10px; text-align: left; padding: 0 12px; color: {MUTED}; min-height: 38px;
}}
QPushButton[kind="nav"]:checked {{ background: #1a1a1d; color: {TEXT}; font-weight: 600; }}

QLineEdit, QComboBox {{
    min-height: 42px; padding: 0 14px; border-radius: 10px;
    background: {CARD}; border: 1px solid {LINE_STRONG}; color: {TEXT};
    selection-background-color: {ACCENT}; selection-color: {BG};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 30px; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {LINE_STRONG}; outline: none;
    selection-background-color: #1a1a1d; selection-color: {TEXT}; padding: 4px;
}}

QCheckBox, QRadioButton {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; }}
QCheckBox::indicator {{ border-radius: 5px; border: 1px solid #4a4a50; background: {CARD}; }}
QCheckBox::indicator:checked {{ border: 1px solid {ACCENT}; background: {ACCENT}; }}
QRadioButton::indicator {{ border-radius: 9px; border: 1px solid #4a4a50; background: {CARD}; }}
QRadioButton::indicator:checked {{ border: 1px solid {ACCENT}; background: {ACCENT}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {FAINT}; }}

QFrame[role="card"] {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
QFrame[role="card"] QWidget {{ background: transparent; }}
QFrame[role="card"][selected="true"] {{ border-color: {ACCENT}; }}
QFrame[role="success"] {{ background: #151a07; border: 1px solid #5b6b1e; border-radius: 12px; }}
QFrame[role="success"] QWidget {{ background: transparent; }}
QFrame[role="error"] {{ background: #1c1110; border: 1px solid #6b2f2a; border-radius: 12px; }}
QFrame[role="error"] QWidget {{ background: transparent; }}
QFrame[role="line"] {{ background: {LINE}; max-height: 1px; min-height: 1px; border: none; }}

QTableWidget {{ background: transparent; border: none; gridline-color: {LINE}; }}
QTableWidget::item {{ padding: 8px 4px; border-bottom: 1px solid {LINE}; }}
QHeaderView::section {{
    background: transparent; color: {FAINT}; border: none; border-bottom: 1px solid {LINE_STRONG};
    font-family: {MONO}; font-size: 11px; padding: 6px 4px; text-align: left;
}}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {LINE_STRONG}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMessageBox {{ background: {PANEL}; }}
"""
