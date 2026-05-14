"""HMI / Touch-Display.

Layout im Web-App-Look:
  - Header (Titel, ESP-Status, Uhr)
  - Sidebar links: 5 Tabs + STOP-Button
  - Inhalt rechts: scrollbar

Die UI wird in einem QTimer alle 250ms aus status_snapshot() gespeist.
Alle ESP/Hauptablauf-Callbacks landen über Qt-Signals threadsicher in der UI.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from ..core.hauptablauf import Hauptablauf
from ..types import (
    SystemState, AuftragQuelle, DruckerStatus, DruckerConfig,
)

logger = logging.getLogger(__name__)


# ============================================================
# DHBW-Farben
# ============================================================
COL_BG          = "#2B2D33"
COL_BG_DARK     = "#1F2024"
COL_BG_CARD     = "#34363C"
COL_BG_SUNK     = "#1F2024"
COL_BORDER      = "#44464C"
COL_DHBW_RED    = "#C8102E"
COL_DHBW_RED_HV = "#A60D26"
COL_TEXT        = "#FFFFFF"
COL_TEXT_DIM    = "#C5C7CB"
COL_TEXT_MUTED  = "#9A9CA0"
COL_OK          = "#16A34A"
COL_OK_DIM      = "#4ADE80"
COL_WARN        = "#F59E0B"
COL_INFO        = "#3478F6"
COL_SERVICE     = "#7C3AED"

STATE_FARBE = {
    SystemState.INIT:           "#5A5C62",
    SystemState.REFERENZFAHRT:  COL_INFO,
    SystemState.BEREITSCHAFT:   COL_OK,
    SystemState.PLATTENWECHSEL: COL_DHBW_RED,
    SystemState.SERVICE:        COL_SERVICE,
    SystemState.FEHLER:         COL_DHBW_RED,
    SystemState.NOT_AUS:        COL_DHBW_RED,
}
STATE_TEXT = {
    SystemState.INIT:           "INITIALISIERUNG",
    SystemState.REFERENZFAHRT:  "REFERENZFAHRT",
    SystemState.BEREITSCHAFT:   "BEREITSCHAFT",
    SystemState.PLATTENWECHSEL: "PLATTENWECHSEL LÄUFT",
    SystemState.SERVICE:        "SERVICE-MODUS",
    SystemState.FEHLER:         "FEHLER",
    SystemState.NOT_AUS:        "NOT-AUS AKTIV",
}
DRUCKER_STATUS_TEXT = {
    "bereit":   "bereit",
    "druckt":   "druckt",
    "in_queue": "in Queue",
    "aktiv":    "wird gewechselt",
}


# ============================================================
# Stylesheet
# ============================================================
STYLESHEET = f"""
QMainWindow, QWidget {{
    background: {COL_BG}; color: {COL_TEXT};
    font-family: 'DejaVu Sans', 'Segoe UI', sans-serif;
}}
QPushButton {{
    background: {COL_BG_CARD}; color: {COL_TEXT};
    border: 1px solid {COL_BORDER}; border-radius: 8px;
    padding: 10px 14px; font-size: 14px; font-weight: 500;
    min-height: 38px;
}}
QPushButton:hover  {{ background: #3F4148; }}
QPushButton:pressed{{ background: #2A2C32; }}
QPushButton:disabled {{ background: #28282E; color: #66676B; border-color: #38393E; }}

QPushButton#primary {{ background: {COL_DHBW_RED}; color: white; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {COL_DHBW_RED_HV}; }}
QPushButton#stopBtn {{ background: {COL_DHBW_RED}; color: white; border: none;
    font-size: 17px; font-weight: 700; min-height: 56px;
    border-radius: 10px; letter-spacing: 1px; }}
QPushButton#success {{ background: {COL_OK}; color: white; border: none; font-weight: 600; }}
QPushButton#service {{ background: {COL_SERVICE}; color: white; border: none; font-weight: 600; }}
QPushButton#danger  {{ background: #5A2A2A; color: white; border: 1px solid {COL_DHBW_RED}; }}

QLineEdit, QSpinBox {{
    background: {COL_BG_SUNK}; color: {COL_TEXT};
    border: 1px solid {COL_BORDER}; border-radius: 6px;
    padding: 6px 10px; font-size: 14px; min-height: 28px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 22px; }}

QLabel {{ background: transparent; }}

QListWidget {{
    background: {COL_BG_SUNK}; border: 1px solid {COL_BORDER};
    border-radius: 6px; font-size: 13px; padding: 4px;
}}
QListWidget::item {{ padding: 7px 10px; border-bottom: 1px solid {COL_BORDER}; }}
QListWidget::item:last-child {{ border-bottom: none; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: {COL_BG_DARK}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {COL_BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #5A5C62; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QFrame#card {{ background: {COL_BG_CARD}; border: 1px solid {COL_BORDER}; border-radius: 10px; }}
"""


# ============================================================
# Signal-Bridge (threadsicher)
# ============================================================
class _Signals(QtCore.QObject):
    state_changed = QtCore.pyqtSignal(object)
    auftrag_ok = QtCore.pyqtSignal(object)
    auftrag_abgelehnt = QtCore.pyqtSignal(object, str)
    fehler_neu = QtCore.pyqtSignal(object)
    fehler_geloescht = QtCore.pyqtSignal()
    drucker_status_changed = QtCore.pyqtSignal(int, object)
    drucker_config_changed = QtCore.pyqtSignal()
    toast = QtCore.pyqtSignal(str, str)


# ============================================================
# Sidebar-Button
# ============================================================
class SidebarButton(QtWidgets.QPushButton):
    def __init__(self, label: str):
        super().__init__()
        self._active = False
        self.setText(label)
        self.setMinimumHeight(54)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._update()

    def setActive(self, a: bool):
        if self._active == a: return
        self._active = a
        self._update()

    def _update(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{ background: {COL_DHBW_RED}; color: white;
                    text-align: left; padding-left: 14px;
                    border: none; border-left: 4px solid white;
                    font-size: 15px; font-weight: 600; min-height: 54px; }}""")
        else:
            self.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {COL_TEXT_DIM};
                    text-align: left; padding-left: 14px;
                    border: none; border-left: 4px solid transparent;
                    font-size: 15px; min-height: 54px; }}
                QPushButton:hover {{ background: #2A2C32; color: {COL_TEXT}; }}""")


# ============================================================
# Drucker-Kachel (Manuell-Tab)
# ============================================================
class DruckerKachel(QtWidgets.QFrame):
    clicked = QtCore.pyqtSignal(int)

    def __init__(self, dc: DruckerConfig):
        super().__init__()
        self.drucker_id = dc.id
        self._status = DruckerStatus.BEREIT
        self._enabled = True
        self.setMinimumHeight(110)

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10); v.setSpacing(5)

        top = QtWidgets.QHBoxLayout()
        self.lbl_name = QtWidgets.QLabel(dc.name or f"Drucker {dc.id}")
        self.lbl_name.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; font-weight: 600;")
        top.addWidget(self.lbl_name)
        top.addStretch()
        self.lbl_badge = QtWidgets.QLabel("BEREIT")
        self.lbl_badge.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_badge.setMinimumWidth(58)
        top.addWidget(self.lbl_badge)
        v.addLayout(top)

        self.lbl_state = QtWidgets.QLabel("bereit für Auftrag")
        self.lbl_state.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 11px;")
        v.addWidget(self.lbl_state)
        v.addStretch()

        self.btn = QtWidgets.QPushButton("Plattenwechsel starten")
        self.btn.setObjectName("primary")
        self.btn.setMinimumHeight(32)
        self.btn.clicked.connect(lambda: self.clicked.emit(self.drucker_id))
        v.addWidget(self.btn)

        self._refresh()

    def setStatus(self, s: DruckerStatus):
        if self._status == s: return
        self._status = s
        self._refresh()

    def setClickEnabled(self, e: bool):
        self._enabled = e
        self._refresh()

    def _refresh(self):
        border = COL_BORDER
        badge_bg = "#44464C"; badge_fg = COL_TEXT_DIM
        badge = "BEREIT"; sub = "bereit für Auftrag"; sub_col = COL_TEXT_MUTED
        btn_text = "Plattenwechsel starten"; btn_enabled = self._enabled

        if self._status == DruckerStatus.IN_QUEUE:
            border = COL_WARN; badge_bg = COL_WARN; badge_fg = "#1F2024"
            badge = "WARTET"; sub = "in Warteschlange"; sub_col = COL_WARN
            btn_text = "In der Queue"; btn_enabled = False
        elif self._status == DruckerStatus.AKTIV:
            border = COL_DHBW_RED; badge_bg = COL_DHBW_RED; badge_fg = "white"
            badge = "AKTIV"; sub = "wird gewechselt"; sub_col = COL_DHBW_RED
            btn_text = "Wird gewechselt …"; btn_enabled = False

        self.setStyleSheet(f"""DruckerKachel {{
            background: {COL_BG_CARD}; border: 2px solid {border};
            border-radius: 10px; }}""")
        self.lbl_badge.setStyleSheet(f"""
            background: {badge_bg}; color: {badge_fg};
            border-radius: 4px; padding: 2px 6px;
            font-size: 9px; font-weight: 600; letter-spacing: 0.5px;""")
        self.lbl_state.setStyleSheet(f"color: {sub_col}; font-size: 12px;")
        self.lbl_state.setText(sub)
        self.lbl_badge.setText(badge)
        self.btn.setText(btn_text)
        self.btn.setEnabled(btn_enabled)


# ============================================================
# Drucker-Editor-Karte (im Drucker-Tab)
# ============================================================
class DruckerEditor(QtWidgets.QFrame):
    saved = QtCore.pyqtSignal(object)
    deleted = QtCore.pyqtSignal(int)

    def __init__(self, dc: DruckerConfig, hide_delete: bool = False):
        super().__init__()
        self._dc = dc

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18); v.setSpacing(10)

        title = QtWidgets.QLabel(f"Drucker {dc.id}")
        title.setStyleSheet(f"color: {COL_TEXT}; font-size: 15px; font-weight: 600;")
        v.addWidget(title)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10); form.setVerticalSpacing(7)
        form.setColumnStretch(1, 1); form.setColumnStretch(3, 1)

        def lbl(t):
            l = QtWidgets.QLabel(t)
            l.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 12px;")
            return l

        # Name — volle Breite
        self.f_name = QtWidgets.QLineEdit(dc.name)
        form.addWidget(lbl("Name"), 0, 0)
        form.addWidget(self.f_name, 0, 1, 1, 3)

        # Pin + X
        self.f_pin = QtWidgets.QSpinBox()
        self.f_pin.setRange(0, 40); self.f_pin.setValue(dc.pin_fertig)
        self.f_pin.setSuffix(" BCM")
        self.f_pos_x = QtWidgets.QSpinBox()
        self.f_pos_x.setRange(0, 5000); self.f_pos_x.setValue(dc.pos_x)
        self.f_pos_x.setSuffix(" mm")
        form.addWidget(lbl("Pin Fertig"), 1, 0); form.addWidget(self.f_pin, 1, 1)
        form.addWidget(lbl("X-Position"), 1, 2); form.addWidget(self.f_pos_x, 1, 3)

        # Z Anfahr + Z Tür
        self.f_anfahr = QtWidgets.QSpinBox()
        self.f_anfahr.setRange(0, 2000); self.f_anfahr.setValue(dc.pos_z_anfahr)
        self.f_anfahr.setSuffix(" mm")
        self.f_tuer = QtWidgets.QSpinBox()
        self.f_tuer.setRange(0, 2000); self.f_tuer.setValue(dc.pos_z_tuer)
        self.f_tuer.setSuffix(" mm")
        form.addWidget(lbl("Z Anfahrt"), 2, 0); form.addWidget(self.f_anfahr, 2, 1)
        form.addWidget(lbl("Z Türarm"),  2, 2); form.addWidget(self.f_tuer,   2, 3)

        # Z Bett + Türarm-Hub
        self.f_bett = QtWidgets.QSpinBox()
        self.f_bett.setRange(0, 2000); self.f_bett.setValue(dc.pos_z_druckbett)
        self.f_bett.setSuffix(" mm")
        self.f_hub = QtWidgets.QSpinBox()
        self.f_hub.setRange(0, 500); self.f_hub.setValue(dc.door_arm_hub_mm)
        self.f_hub.setSuffix(" mm")
        form.addWidget(lbl("Z Druckbett"),  3, 0); form.addWidget(self.f_bett, 3, 1)
        form.addWidget(lbl("Türarm-Hub"),   3, 2); form.addWidget(self.f_hub,  3, 3)

        # Greifer + Hub-Offset
        self.f_gd = QtWidgets.QSpinBox()
        self.f_gd.setRange(0, 500); self.f_gd.setValue(dc.gripper_depth)
        self.f_gd.setSuffix(" mm")
        self.f_lo = QtWidgets.QSpinBox()
        self.f_lo.setRange(0, 100); self.f_lo.setValue(dc.lift_offset)
        self.f_lo.setSuffix(" mm")
        form.addWidget(lbl("Greifer-Tiefe"), 4, 0); form.addWidget(self.f_gd, 4, 1)
        form.addWidget(lbl("Hub-Offset"),    4, 2); form.addWidget(self.f_lo, 4, 3)

        v.addLayout(form)

        row = QtWidgets.QHBoxLayout()
        bs = QtWidgets.QPushButton("Speichern")
        bs.setObjectName("primary")
        bs.clicked.connect(self._save)
        row.addWidget(bs)

        if not hide_delete:
            bd = QtWidgets.QPushButton("Drucker entfernen")
            bd.setObjectName("danger")
            bd.clicked.connect(self._del)
            row.addWidget(bd)
        v.addLayout(row)

    def _save(self):
        new_dc = DruckerConfig(
            id=self._dc.id,
            name=self.f_name.text().strip() or f"Drucker {self._dc.id}",
            pin_fertig=self.f_pin.value(),
            pos_x=self.f_pos_x.value(),
            pos_z_anfahr=self.f_anfahr.value(),
            pos_z_tuer=self.f_tuer.value(),
            pos_z_druckbett=self.f_bett.value(),
            door_arm_hub_mm=self.f_hub.value(),
            gripper_depth=self.f_gd.value(),
            lift_offset=self.f_lo.value(),
        )
        self.saved.emit(new_dc)

    def _del(self):
        confirm = QtWidgets.QMessageBox.question(
            self, "Drucker entfernen",
            f"Drucker {self._dc.id} ({self._dc.name}) wirklich entfernen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if confirm == QtWidgets.QMessageBox.Yes:
            self.deleted.emit(self._dc.id)


# ============================================================
# On-Screen-Tastatur (QWERTZ, einbettbar, kein Fokusraub)
# ============================================================
class OnScreenKeyboard(QtWidgets.QWidget):
    _ROWS: list = [
        ["1","2","3","4","5","6","7","8","9","0","⌫"],
        ["Q","W","E","R","T","Z","U","I","O","P"],
        ["A","S","D","F","G","H","J","K","L","↵"],
        ["⇧","Y","X","C","V","B","N","M","-","_","✕"],
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._upper = True
        self._letter_btns: list = []
        self._build()

    def _build(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: {COL_BG_CARD}; color: {COL_TEXT};
                border: 1px solid {COL_BORDER}; border-radius: 7px;
                font-size: 17px; font-weight: 500;
            }}
            QPushButton:pressed {{ background: {COL_DHBW_RED}; border-color: {COL_DHBW_RED}; }}
            QPushButton#spec {{ background: {COL_BG_SUNK}; font-size: 15px; }}
        """)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10); v.setSpacing(7)

        for row in self._ROWS:
            h = QtWidgets.QHBoxLayout(); h.setSpacing(7)
            for key in row:
                btn = QtWidgets.QPushButton(key)
                btn.setFocusPolicy(QtCore.Qt.NoFocus)
                btn.setFixedHeight(48)
                is_spec = key in ("⌫", "↵", "⇧", "✕")
                if is_spec:
                    btn.setObjectName("spec")
                btn.clicked.connect(lambda _, k=key: self._press(k))
                if key.isalpha() and len(key) == 1:
                    self._letter_btns.append((btn, key.upper()))
                h.addWidget(btn, 2 if is_spec else 1)
            v.addLayout(h)

        # Leerzeichen
        h_sp = QtWidgets.QHBoxLayout(); h_sp.setSpacing(7)
        sp = QtWidgets.QPushButton("Leerzeichen")
        sp.setFocusPolicy(QtCore.Qt.NoFocus)
        sp.setFixedHeight(48)
        sp.clicked.connect(lambda: self._press(" "))
        h_sp.addWidget(sp)
        v.addLayout(h_sp)

    def _press(self, key: str):
        w = QtWidgets.QApplication.focusWidget()
        if key == "⇧":
            self._toggle_case(); return
        if key in ("↵", "✕"):
            self.hide(); return
        if w is None: return
        if key == " ":
            ev = QtGui.QKeyEvent(QtCore.QEvent.KeyPress,
                QtCore.Qt.Key_Space, QtCore.Qt.NoModifier, " ")
        elif key == "⌫":
            ev = QtGui.QKeyEvent(QtCore.QEvent.KeyPress,
                QtCore.Qt.Key_Backspace, QtCore.Qt.NoModifier)
        else:
            char = key if (self._upper or not key.isalpha()) else key.lower()
            ev = QtGui.QKeyEvent(QtCore.QEvent.KeyPress,
                QtCore.Qt.Key_unknown, QtCore.Qt.NoModifier, char)
        QtWidgets.QApplication.postEvent(w, ev)

    def _toggle_case(self):
        self._upper = not self._upper
        for btn, base in self._letter_btns:
            btn.setText(base if self._upper else base.lower())

# ============================================================
# Drucker-Konfig-Kachel (Drucker-Tab)
# ============================================================
class DruckerKonfigKachel(QtWidgets.QFrame):
    clicked = QtCore.pyqtSignal(int)

    def __init__(self, dc: DruckerConfig):
        super().__init__()
        self.drucker_id = dc.id
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumHeight(110)
        self._apply_style(False)

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10); v.setSpacing(4)

        top = QtWidgets.QHBoxLayout()
        lbl_name = QtWidgets.QLabel(dc.name or f"Drucker {dc.id}")
        lbl_name.setStyleSheet(f"color: {COL_TEXT}; font-size: 14px; font-weight: 600;")
        top.addWidget(lbl_name, stretch=1)
        badge = QtWidgets.QLabel(f"#{dc.id}")
        badge.setStyleSheet(f"background: {COL_DHBW_RED}; color: white; "
                            "border-radius: 4px; padding: 2px 7px; "
                            "font-size: 10px; font-weight: 600;")
        top.addWidget(badge)
        v.addLayout(top)

        v.addWidget(self._dim(f"X: {dc.pos_x} mm"))
        v.addWidget(self._dim(f"Z Anfahr: {dc.pos_z_anfahr} mm  ·  Tür: {dc.pos_z_tuer} mm"))
        v.addWidget(self._dim(f"Pin Fertig: {dc.pin_fertig}"))
        v.addStretch()

        hint = QtWidgets.QLabel("✎ antippen zum Bearbeiten")
        hint.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 10px;")
        v.addWidget(hint)

    def _dim(self, text: str) -> QtWidgets.QLabel:
        l = QtWidgets.QLabel(text)
        l.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 11px;")
        return l

    def _apply_style(self, hover: bool):
        bg = "#3F4148" if hover else COL_BG_CARD
        self.setStyleSheet(f"DruckerKonfigKachel {{ background: {bg}; "
                           f"border: 1px solid {COL_BORDER}; border-radius: 10px; }}")

    def enterEvent(self, ev):
        self._apply_style(True); super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._apply_style(False); super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.drucker_id)
        super().mousePressEvent(ev)


# ============================================================
# Hauptfenster
# ============================================================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, hauptablauf: Hauptablauf,
                 fullscreen: bool = True,
                 width: int = 1280, height: int = 720):
        super().__init__()
        self.hauptablauf = hauptablauf
        self.signals = _Signals()

        self.setWindowTitle("Plattenwechsler")
        self.setStyleSheet(STYLESHEET)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self.stack = QtWidgets.QStackedWidget()
        self.page_status  = self._wrap_scroll(self._build_status())
        self.page_manuell = self._wrap_scroll(self._build_manuell())
        self.page_service = self._wrap_scroll(self._build_service())
        self.page_drucker = self._wrap_scroll(self._build_drucker())
        self.page_fehler  = self._wrap_scroll(self._build_fehler())
        for p in (self.page_status, self.page_manuell, self.page_service,
                  self.page_drucker, self.page_fehler):
            self.stack.addWidget(p)
        body.addWidget(self.stack, stretch=1)

        body_w = QtWidgets.QWidget(); body_w.setLayout(body)
        root.addWidget(body_w, stretch=1)

        self.setMinimumSize(width, height)
        self.resize(width, height)
        if fullscreen:
            self.showFullScreen()

        # Signals → UI (threadsicher)
        self.signals.state_changed.connect(lambda *_: self._refresh())
        self.signals.auftrag_ok.connect(self._on_auftrag_ok)
        self.signals.auftrag_abgelehnt.connect(self._on_auftrag_abgelehnt)
        self.signals.fehler_neu.connect(self._on_fehler_neu)
        self.signals.fehler_geloescht.connect(
            lambda: self._toast("System bereit", "Fehler behoben"))
        self.signals.drucker_status_changed.connect(lambda *_: self._refresh())
        self.signals.drucker_config_changed.connect(self._on_config_changed)
        self.signals.toast.connect(self._toast)

        # Hauptablauf → Signals
        self.hauptablauf.on_state_change = lambda s: self.signals.state_changed.emit(s)
        self.hauptablauf.on_auftrag_erfolgreich = \
            lambda a: self.signals.auftrag_ok.emit(a)
        self.hauptablauf.on_auftrag_abgelehnt = \
            lambda a, g: self.signals.auftrag_abgelehnt.emit(a, g)
        self.hauptablauf.on_drucker_status_changed = \
            lambda d, s: self.signals.drucker_status_changed.emit(d, s)
        self.hauptablauf.on_drucker_config_changed = \
            lambda: self.signals.drucker_config_changed.emit()
        self.hauptablauf.fehler.on_fehler_neu = \
            lambda f: self.signals.fehler_neu.emit(f)
        self.hauptablauf.fehler.on_fehler_geloescht = \
            lambda: self.signals.fehler_geloescht.emit()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(250)


        self._aktive_seite = "status"
        self._kacheln: dict = {}
        self._drucker_kacheln: dict = {}
        self._service_drucker_btns: list = []
        self._service_busy = False
        self._switch("status")
        self._rebuild_drucker_kacheln()
        self._rebuild_kacheln()
        self._rebuild_service_drucker_btns()
        self._refresh()

    def _wrap_scroll(self, content: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        sa = QtWidgets.QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(content)
        sa.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        return sa

    def _make_card(self, title: str = "") -> QtWidgets.QFrame:
        c = QtWidgets.QFrame()
        c.setObjectName("card")
        v = QtWidgets.QVBoxLayout(c)
        v.setContentsMargins(16, 14, 16, 14); v.setSpacing(10)
        if title:
            t = QtWidgets.QLabel(title)
            t.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 11px; "
                            "font-weight: 600; letter-spacing: 1px;")
            v.addWidget(t)
        return c

    def _section_lbl(self, text: str) -> QtWidgets.QLabel:
        l = QtWidgets.QLabel(text)
        l.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 11px; "
                        "font-weight: 600; letter-spacing: 1px;")
        return l

    def _kv(self, label: str, value: str = "—") -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(6)
        l = QtWidgets.QLabel(label)
        l.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 12px;")
        v = QtWidgets.QLabel(value); v.setObjectName("kv_value")
        v.setStyleSheet(f"color: {COL_TEXT}; font-size: 13px; font-weight: 500;")
        h.addWidget(l); h.addWidget(v)
        return w

    def _set_kv(self, kv_widget: QtWidgets.QWidget, value: str, color: str):
        for child in kv_widget.findChildren(QtWidgets.QLabel):
            if child.objectName() == "kv_value":
                child.setText(value)
                child.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 500;")

    # ============================================================
    # Header
    # ============================================================
    def _build_header(self) -> QtWidgets.QWidget:
        h = QtWidgets.QFrame()
        h.setFixedHeight(58)
        h.setStyleSheet(f"QFrame {{ background: {COL_BG_DARK}; "
                        f"border-bottom: 2px solid {COL_DHBW_RED}; }}")
        lay = QtWidgets.QHBoxLayout(h)
        lay.setContentsMargins(18, 0, 18, 0); lay.setSpacing(12)

        logo = QtWidgets.QLabel("P"); logo.setFixedSize(36, 36)
        logo.setAlignment(QtCore.Qt.AlignCenter)
        logo.setStyleSheet(f"background: {COL_DHBW_RED}; color: white;"
                           "border-radius: 6px; font-size: 20px; font-weight: 700;")
        lay.addWidget(logo)

        box = QtWidgets.QVBoxLayout(); box.setSpacing(0)
        t1 = QtWidgets.QLabel("Plattenwechsler")
        t1.setStyleSheet(f"color: {COL_TEXT}; font-size: 15px; font-weight: 600;")
        t2 = QtWidgets.QLabel("G6-TWIE23A · DHBW Stuttgart")
        t2.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 10px;")
        box.addWidget(t1); box.addWidget(t2)
        lay.addLayout(box)
        lay.addStretch()

        self.lbl_esp_dot = QtWidgets.QLabel("●")
        self.lbl_esp_dot.setStyleSheet(f"color: #888; font-size: 13px;")
        lt = QtWidgets.QLabel("ESP")
        lt.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 12px;")
        lay.addWidget(self.lbl_esp_dot); lay.addWidget(lt); lay.addSpacing(10)

        self.lbl_uhr = QtWidgets.QLabel("--:--:--")
        self.lbl_uhr.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 13px; "
                                    "font-family: monospace;")
        lay.addWidget(self.lbl_uhr)
        return h

    # ============================================================
    # Sidebar
    # ============================================================
    def _build_sidebar(self) -> QtWidgets.QWidget:
        s = QtWidgets.QFrame()
        s.setFixedWidth(190)
        s.setStyleSheet(f"QFrame {{ background: {COL_BG_DARK}; "
                        f"border-right: 1px solid {COL_BORDER}; }}")
        lay = QtWidgets.QVBoxLayout(s)
        lay.setContentsMargins(0, 12, 0, 12); lay.setSpacing(2)

        self.btn_status  = SidebarButton("Status")
        self.btn_manuell = SidebarButton("Manuell")
        self.btn_service = SidebarButton("Service")
        self.btn_drucker = SidebarButton("Drucker")
        self.btn_fehler  = SidebarButton("Fehler")

        self.btn_status.clicked.connect(lambda: self._switch("status"))
        self.btn_manuell.clicked.connect(lambda: self._switch("manuell"))
        self.btn_service.clicked.connect(lambda: self._switch("service"))
        self.btn_drucker.clicked.connect(lambda: self._switch("drucker"))
        self.btn_fehler.clicked.connect(lambda: self._switch("fehler"))

        for b in (self.btn_status, self.btn_manuell, self.btn_service,
                  self.btn_drucker, self.btn_fehler):
            lay.addWidget(b)
        lay.addStretch()

        wrap = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(wrap); sl.setContentsMargins(10, 0, 10, 0)
        self.btn_stop = QtWidgets.QPushButton("STOP")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.clicked.connect(self._on_stop)
        sl.addWidget(self.btn_stop)
        lay.addWidget(wrap)
        return s

    def _switch(self, name: str):
        # Kein Tab-Wechsel weg vom Service während eine Fahrt läuft
        if name != "service" and self._service_busy:
            self._toast("Fahrt läuft noch", "Bitte warten bis der Schlitten steht")
            return

        m = {
            "status":  (self.btn_status,  self.page_status),
            "manuell": (self.btn_manuell, self.page_manuell),
            "service": (self.btn_service, self.page_service),
            "drucker": (self.btn_drucker, self.page_drucker),
            "fehler":  (self.btn_fehler,  self.page_fehler),
        }
        for n, (btn, _) in m.items():
            btn.setActive(n == name)
        self.stack.setCurrentWidget(m[name][1])
        self._aktive_seite = name

        # Service-Modus auto
        if name == "service":
            self.hauptablauf.service_modus_aktivieren()
        elif self.hauptablauf.state == SystemState.SERVICE:
            self.hauptablauf.service_modus_verlassen()

    # ============================================================
    # Status-Seite
    # ============================================================
    def _build_status(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        self.banner = QtWidgets.QFrame()
        self.banner.setFixedHeight(70)
        bl = QtWidgets.QHBoxLayout(self.banner)
        bl.setContentsMargins(24, 0, 24, 0)
        self.banner_text = QtWidgets.QLabel("INITIALISIERUNG")
        self.banner_text.setStyleSheet("color: white; font-size: 22px; "
                                        "font-weight: 600; letter-spacing: 0.5px;")
        bl.addWidget(self.banner_text); bl.addStretch()
        self.banner_sub = QtWidgets.QLabel("")
        self.banner_sub.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 13px;")
        bl.addWidget(self.banner_sub)
        v.addWidget(self.banner)

        body = QtWidgets.QWidget()
        bl2 = QtWidgets.QVBoxLayout(body)
        bl2.setContentsMargins(18, 18, 18, 18); bl2.setSpacing(12)

        # Position
        pc = self._make_card("SCHLITTEN-POSITION")
        pl = pc.layout()
        pos_row = QtWidgets.QHBoxLayout(); pos_row.setSpacing(20)
        self.lbl_x = QtWidgets.QLabel("0 mm")
        self.lbl_x.setStyleSheet(f"color: {COL_TEXT}; font-size: 24px; font-weight: 600;")
        self.lbl_z = QtWidgets.QLabel("0 mm")
        self.lbl_z.setStyleSheet(f"color: {COL_TEXT}; font-size: 24px; font-weight: 600;")
        for label, w in [("X", self.lbl_x), ("Z", self.lbl_z)]:
            box = QtWidgets.QVBoxLayout(); box.setSpacing(2)
            l = QtWidgets.QLabel(label)
            l.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 11px;")
            box.addWidget(l); box.addWidget(w)
            pos_row.addLayout(box)
        pos_row.addStretch()
        pl.addLayout(pos_row)

        kv = QtWidgets.QHBoxLayout(); kv.setSpacing(20)
        self.lbl_ref = self._kv("Referenziert")
        self.lbl_plate = self._kv("Platte am Schlitten")
        self.lbl_obst = self._kv("Hindernissensor")
        kv.addWidget(self.lbl_ref); kv.addWidget(self.lbl_plate); kv.addWidget(self.lbl_obst)
        kv.addStretch()
        pl.addLayout(kv)
        bl2.addWidget(pc)

        # Drucker
        self.printers_card = self._make_card("DRUCKER")
        bl2.addWidget(self.printers_card)

        # Queue
        qc = self._make_card("AUFTRAGSWARTESCHLANGE")
        ql = qc.layout()
        self.queue_list = QtWidgets.QListWidget()
        self.queue_list.setMinimumHeight(140)
        ql.addWidget(self.queue_list)
        bl2.addWidget(qc)

        bl2.addStretch()
        v.addWidget(body, stretch=1)
        return page

    # ============================================================
    # Manuell-Seite
    # ============================================================
    def _build_manuell(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(20, 18, 20, 20); v.setSpacing(12)

        title = QtWidgets.QLabel("Manueller Plattenwechsel")
        title.setStyleSheet(f"color: {COL_TEXT}; font-size: 20px; font-weight: 600;")
        sub = QtWidgets.QLabel("Drucker antippen um einen Plattenwechsel zu starten")
        sub.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 12px;")
        v.addWidget(title); v.addWidget(sub)

        self.manuell_grid_w = QtWidgets.QWidget()
        self.manuell_grid = QtWidgets.QGridLayout(self.manuell_grid_w)
        self.manuell_grid.setSpacing(12)
        v.addWidget(self.manuell_grid_w, stretch=1)
        return page

    # ============================================================
    # Service-Seite
    # ============================================================
    def _build_service(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(20, 18, 20, 20); v.setSpacing(12)

        title = QtWidgets.QLabel("Service-Funktionen")
        title.setStyleSheet(f"color: {COL_TEXT}; font-size: 20px; font-weight: 600;")
        v.addWidget(title)

        self.service_banner = QtWidgets.QLabel(
            "Service-Modus inaktiv. Wechsle in den Service-Tab zur Aktivierung.")
        self.service_banner.setWordWrap(True)
        v.addWidget(self.service_banner)

        # Schlitten zu Drucker fahren
        v.addWidget(self._section_lbl("SCHLITTEN ZU DRUCKER FAHREN"))
        self.fahre_drucker_w = QtWidgets.QWidget()
        _flay = QtWidgets.QVBoxLayout(self.fahre_drucker_w)
        _flay.setContentsMargins(0, 0, 0, 0); _flay.setSpacing(8)
        v.addWidget(self.fahre_drucker_w)

        # Schlitten zu Sonderpositionen
        v.addWidget(self._section_lbl("WEITERE POSITIONEN"))
        sp_row = QtWidgets.QGridLayout(); sp_row.setSpacing(8)
        for i, (label, key) in enumerate([
            ("Home", "home"), ("Ablage", "ablage"), ("Magazin", "magazin")
        ]):
            btn = QtWidgets.QPushButton(label); btn.setMinimumHeight(40)
            btn.clicked.connect(lambda _, k=key, n=label: self._on_service_pos(k, n))
            sp_row.addWidget(btn, 0, i)
            sp_row.setColumnStretch(i, 1)
            setattr(self, f"btn_pos_{key}", btn)
        sp_w = QtWidgets.QWidget(); sp_w.setLayout(sp_row)
        v.addWidget(sp_w)

        # Referenzfahrt
        v.addWidget(self._section_lbl("REFERENZFAHRT"))
        self.btn_referenz = QtWidgets.QPushButton("Referenzfahrt durchführen")
        self.btn_referenz.setObjectName("primary")
        self.btn_referenz.clicked.connect(self._on_referenzfahrt)
        v.addWidget(self.btn_referenz)

        v.addStretch()
        return page

    # ============================================================
    # Drucker-Seite
    # ============================================================
    def _build_drucker(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(20, 18, 20, 20); v.setSpacing(12)

        title = QtWidgets.QLabel("Drucker-Konfiguration")
        title.setStyleSheet(f"color: {COL_TEXT}; font-size: 20px; font-weight: 600;")
        v.addWidget(title)
        sub = QtWidgets.QLabel("Kachel antippen um Drucker zu bearbeiten oder zu löschen. "
                                "Änderungen werden direkt in die config.yaml gespeichert.")
        sub.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 12px;")
        sub.setWordWrap(True)
        v.addWidget(sub)

        btn_add = QtWidgets.QPushButton("➕  Neuen Drucker hinzufügen")
        btn_add.setObjectName("primary"); btn_add.setMinimumHeight(44)
        btn_add.clicked.connect(self._on_drucker_add)
        v.addWidget(btn_add)

        self.drucker_kacheln_w = QtWidgets.QWidget()
        self.drucker_kacheln_grid = QtWidgets.QGridLayout(self.drucker_kacheln_w)
        self.drucker_kacheln_grid.setSpacing(12)
        self.drucker_kacheln_grid.setAlignment(QtCore.Qt.AlignTop)
        v.addWidget(self.drucker_kacheln_w, stretch=1)
        v.addStretch()
        return page

    # ============================================================
    # Fehler-Seite
    # ============================================================
    def _build_fehler(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(20, 18, 20, 20); v.setSpacing(12)

        title = QtWidgets.QLabel("Fehler & Quittierung")
        title.setStyleSheet(f"color: {COL_TEXT}; font-size: 20px; font-weight: 600;")
        v.addWidget(title)

        self.fehler_box = QtWidgets.QFrame()
        self.fehler_box.setObjectName("card")
        fl = QtWidgets.QVBoxLayout(self.fehler_box)
        fl.setContentsMargins(20, 18, 20, 18); fl.setSpacing(8)

        self.lbl_fehler_klasse = QtWidgets.QLabel("Kein aktiver Fehler")
        self.lbl_fehler_klasse.setStyleSheet(
            f"color: {COL_OK_DIM}; font-size: 20px; font-weight: 600;")
        fl.addWidget(self.lbl_fehler_klasse)

        self.lbl_fehler_msg = QtWidgets.QLabel("Das System läuft normal.")
        self.lbl_fehler_msg.setWordWrap(True)
        self.lbl_fehler_msg.setStyleSheet(f"color: {COL_TEXT_DIM}; font-size: 14px;")
        fl.addWidget(self.lbl_fehler_msg)

        self.lbl_fehler_meta = QtWidgets.QLabel("")
        self.lbl_fehler_meta.setStyleSheet(f"color: {COL_TEXT_MUTED}; font-size: 11px;")
        fl.addWidget(self.lbl_fehler_meta)

        fl.addSpacing(8)
        self.btn_quittieren = QtWidgets.QPushButton("Fehler quittieren")
        self.btn_quittieren.setObjectName("success")
        self.btn_quittieren.setMinimumHeight(46)
        self.btn_quittieren.setEnabled(False)
        self.btn_quittieren.clicked.connect(self._on_quittieren)
        fl.addWidget(self.btn_quittieren)
        v.addWidget(self.fehler_box)

        hist = self._make_card("FEHLER-HISTORIE")
        hl = hist.layout()
        self.fehler_list = QtWidgets.QListWidget()
        self.fehler_list.setMinimumHeight(180)
        hl.addWidget(self.fehler_list)
        v.addWidget(hist)

        v.addStretch()
        return page

    # ============================================================
    # Refresh
    # ============================================================
    def _refresh(self):
        snap = self.hauptablauf.status_snapshot()

        self.lbl_uhr.setText(time.strftime("%H:%M:%S"))
        connected = snap["esp"]["connected"]
        self.lbl_esp_dot.setStyleSheet(
            f"color: {COL_OK_DIM if connected else '#888'}; font-size: 13px;")

        try: sys_state = SystemState(snap["system_state"])
        except ValueError: sys_state = SystemState.INIT
        self.banner.setStyleSheet(
            f"QFrame {{ background: {STATE_FARBE.get(sys_state, '#666')}; }}")
        self.banner_text.setText(STATE_TEXT.get(sys_state, sys_state.value))
        self.banner_sub.setText(self._banner_sub(sys_state, snap))

        # Position
        self.lbl_x.setText(f"{snap['esp']['x_mm']} mm")
        self.lbl_z.setText(f"{snap['esp']['z_mm']} mm")
        self._set_kv(self.lbl_ref,
            "ja" if snap["esp"]["referenced"] else "nein",
            COL_OK_DIM if snap["esp"]["referenced"] else COL_TEXT_MUTED)
        self._set_kv(self.lbl_plate,
            "ja" if snap["esp"]["has_plate"] else "nein",
            COL_INFO if snap["esp"]["has_plate"] else COL_TEXT_MUTED)
        self._set_kv(self.lbl_obst,
            "frei" if snap["esp"]["obstacle_ok"] else "ALARM",
            COL_OK_DIM if snap["esp"]["obstacle_ok"] else COL_DHBW_RED)

        self._refresh_drucker_status_list(snap)

        self.queue_list.clear()
        for a in snap["queue"]:
            self.queue_list.addItem(
                f"#{a['id']:>3}   Drucker {a['drucker']}   ({a['quelle']})")
        if not snap["queue"]:
            self.queue_list.addItem("— keine Aufträge —")

        self._refresh_manuell(snap)
        self._refresh_service(snap, sys_state, connected)
        self._refresh_fehler(snap)

    def _banner_sub(self, sys_state, snap) -> str:
        if sys_state == SystemState.PLATTENWECHSEL and snap.get("aktiver_drucker"):
            return f"Drucker {snap['aktiver_drucker']} wird gewechselt"
        if sys_state == SystemState.BEREITSCHAFT:
            q = snap["queue_length"]
            return ("System bereit" if q == 0
                    else f"{q} Auftrag in Queue" if q == 1
                    else f"{q} Aufträge in Queue")
        if sys_state == SystemState.FEHLER and snap["fehler"]:
            return snap["fehler"]["klasse"]
        return ""

    def _refresh_drucker_status_list(self, snap):
        layout = self.printers_card.layout()
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item.widget(): item.widget().deleteLater()

        ds = snap["drucker_status"]
        druckers = snap["drucker_config"]
        if not druckers:
            l = QtWidgets.QLabel("— kein Drucker konfiguriert —")
            l.setStyleSheet(f"color: {COL_TEXT_MUTED}; padding: 12px;")
            l.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(l)
            return

        grid_w = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_w)
        grid.setSpacing(8); grid.setContentsMargins(0, 0, 0, 0)

        for idx, dc in enumerate(druckers):
            did = dc["id"]
            status = ds.get(did, "bereit")
            color = self._d_color(status)

            card = QtWidgets.QFrame()
            card.setStyleSheet(f"""QFrame {{ background: {COL_BG_SUNK};
                border: none; border-left: 3px solid {color};
                border-radius: 4px; }}""")
            h = QtWidgets.QHBoxLayout(card)
            h.setContentsMargins(10, 8, 10, 8); h.setSpacing(8)

            n = QtWidgets.QLabel(dc.get("name") or f"Drucker {did}")
            n.setStyleSheet(f"color: {COL_TEXT}; font-size: 13px; font-weight: 500;")
            h.addWidget(n, stretch=1)

            st = QtWidgets.QLabel(DRUCKER_STATUS_TEXT.get(status, status))
            st.setStyleSheet(f"color: {color}; font-size: 11px;")
            h.addWidget(st)

            grid.addWidget(card, idx // 4, idx % 4)

        for col in range(4):
            grid.setColumnStretch(col, 1)
        layout.addWidget(grid_w)

    def _rebuild_kacheln(self):
        while self.manuell_grid.count():
            item = self.manuell_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._kacheln.clear()

        druckers = self.hauptablauf.config.drucker_liste()
        if not druckers:
            l = QtWidgets.QLabel(
                "Noch kein Drucker konfiguriert.\n"
                "Geh zum Drucker-Tab um einen hinzuzufügen.")
            l.setAlignment(QtCore.Qt.AlignCenter)
            l.setStyleSheet(f"color: {COL_TEXT_MUTED}; padding: 30px;")
            self.manuell_grid.addWidget(l, 0, 0)
            return

        for idx, dc in enumerate(druckers):
            kachel = DruckerKachel(dc)
            kachel.clicked.connect(self._on_kachel_clicked)
            self.manuell_grid.addWidget(kachel, idx // 4, idx % 4)
            self._kacheln[dc.id] = kachel
        for col in range(4):
            self.manuell_grid.setColumnStretch(col, 1)

    def _refresh_manuell(self, snap):
        ds = snap["drucker_status"]
        try: sys_state = SystemState(snap["system_state"])
        except ValueError: sys_state = SystemState.INIT
        kann_klicken = (snap["fehler"] is None and snap["esp"]["connected"]
                        and sys_state in (SystemState.BEREITSCHAFT,
                                           SystemState.PLATTENWECHSEL))

        for did, kachel in self._kacheln.items():
            try: ds_enum = DruckerStatus(ds.get(did, "bereit"))
            except ValueError: ds_enum = DruckerStatus.BEREIT
            kachel.setStatus(ds_enum)
            kachel.setClickEnabled(kann_klicken and ds_enum == DruckerStatus.BEREIT)

    def _refresh_service(self, snap, sys_state, connected):
        service_active = sys_state == SystemState.SERVICE and connected and not self._service_busy

        if sys_state == SystemState.SERVICE:
            self.service_banner.setText(
                "Service-Modus aktiv. Verlasse den Tab um zu beenden.")
            self.service_banner.setStyleSheet(
                f"color: #C4B5FD; background: rgba(124, 58, 237, 0.15); "
                f"border: 1px solid {COL_SERVICE}; border-radius: 8px; "
                "padding: 10px 14px; font-size: 12px;")
        elif sys_state == SystemState.BEREITSCHAFT:
            self.service_banner.setText(
                "Service-Modus wird beim Wechsel automatisch aktiviert.")
            self.service_banner.setStyleSheet(
                f"color: {COL_TEXT_DIM}; background: {COL_BG_CARD}; "
                f"border: 1px solid {COL_BORDER}; border-radius: 8px; "
                "padding: 10px 14px; font-size: 12px;")
        else:
            self.service_banner.setText(
                f"Service nicht möglich — System: {sys_state.value}")
            self.service_banner.setStyleSheet(
                f"color: #FF6B6B; background: {COL_BG_CARD}; "
                f"border: 1px solid {COL_DHBW_RED}; border-radius: 8px; "
                "padding: 10px 14px; font-size: 12px;")

        # Sonderpositionen
        for key in ("home", "ablage", "magazin"):
            btn = getattr(self, f"btn_pos_{key}")
            btn.setEnabled(service_active)

        # Drucker-Buttons — nur enabled-Zustand aktualisieren
        for btn in self._service_drucker_btns:
            btn.setEnabled(service_active)

    def _refresh_fehler(self, snap):
        f = snap["fehler"]
        if f:
            self.fehler_box.setStyleSheet(
                f"QFrame#card {{ background: #2A1A1A; "
                f"border: 2px solid {COL_DHBW_RED}; border-radius: 10px; }}")
            self.lbl_fehler_klasse.setText(f["klasse"])
            self.lbl_fehler_klasse.setStyleSheet(
                f"color: #FF6B6B; font-size: 20px; font-weight: 600;")
            self.lbl_fehler_msg.setText(f["nachricht"])
            meta = f"Zeit: {time.strftime('%H:%M:%S', time.localtime(f['timestamp']))}"
            if f["esp_code"]: meta += f"  ·  ESP-Code: {f['esp_code']}"
            if f["quittiert"]: meta += "  ·  ✓ quittiert"
            self.lbl_fehler_meta.setText(meta)
            self.btn_quittieren.setEnabled(not f["quittiert"])
        else:
            self.fehler_box.setStyleSheet(
                f"QFrame#card {{ background: {COL_BG_CARD}; "
                f"border: 1px solid {COL_BORDER}; border-radius: 10px; }}")
            self.lbl_fehler_klasse.setText("Kein aktiver Fehler")
            self.lbl_fehler_klasse.setStyleSheet(
                f"color: {COL_OK_DIM}; font-size: 20px; font-weight: 600;")
            self.lbl_fehler_msg.setText("Das System läuft normal.")
            self.lbl_fehler_meta.setText("")
            self.btn_quittieren.setEnabled(False)

        self.fehler_list.clear()
        for hf in self.hauptablauf.fehler.historie(20):
            ts = time.strftime("%H:%M:%S", time.localtime(hf.timestamp))
            self.fehler_list.addItem(f"[{ts}]  {hf}")

    def _d_color(self, s: str) -> str:
        return {"bereit": COL_TEXT_MUTED, "druckt": COL_TEXT_DIM,
                "in_queue": COL_WARN, "aktiv": COL_DHBW_RED}.get(s, COL_TEXT_MUTED)

    # ============================================================
    # Service-Drucker-Buttons (einmalig aufbauen)
    # ============================================================
    def _rebuild_service_drucker_btns(self):
        lay = self.fahre_drucker_w.layout()
        while lay.count():
            item = lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._service_drucker_btns.clear()

        druckers = self.hauptablauf.config.drucker_liste()
        if not druckers:
            l = QtWidgets.QLabel("— kein Drucker konfiguriert —")
            l.setStyleSheet(f"color: {COL_TEXT_MUTED};")
            l.setAlignment(QtCore.Qt.AlignCenter)
            lay.addWidget(l)
            return

        grid_w = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(8)
        for i, d in enumerate(druckers):
            btn = QtWidgets.QPushButton(d.name or f"Drucker {d.id}")
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda _, did=d.id: self._on_service_drucker(did))
            grid.addWidget(btn, i // 4, i % 4)
            self._service_drucker_btns.append(btn)
        for col in range(4):
            grid.setColumnStretch(col, 1)
        lay.addWidget(grid_w)

    # ============================================================
    # Drucker-Kacheln (Drucker-Tab)
    # ============================================================
    def _rebuild_drucker_kacheln(self):
        while self.drucker_kacheln_grid.count():
            item = self.drucker_kacheln_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._drucker_kacheln.clear()

        druckers = self.hauptablauf.config.drucker_liste()
        if not druckers:
            l = QtWidgets.QLabel(
                "Noch kein Drucker konfiguriert.\n"
                "Oben '+' drücken um einen anzulegen.")
            l.setAlignment(QtCore.Qt.AlignCenter)
            l.setStyleSheet(f"color: {COL_TEXT_MUTED}; padding: 30px;")
            self.drucker_kacheln_grid.addWidget(l, 0, 0)
            return

        for idx, dc in enumerate(druckers):
            kachel = DruckerKonfigKachel(dc)
            kachel.clicked.connect(self._on_drucker_kachel_clicked)
            self.drucker_kacheln_grid.addWidget(kachel, idx // 4, idx % 4)
            self._drucker_kacheln[dc.id] = kachel
        for col in range(4):
            self.drucker_kacheln_grid.setColumnStretch(col, 1)

    def _on_drucker_kachel_clicked(self, drucker_id: int):
        dc = self.hauptablauf.config.drucker(drucker_id)
        if dc is None: return
        self._open_drucker_editor(dc)

    def _open_drucker_editor(self, dc: DruckerConfig, hide_delete: bool = False):
        mw = self.geometry()

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Drucker {dc.id} — {dc.name or f'Drucker {dc.id}'}")
        dlg.setModal(True)
        dlg.setFixedSize(mw.width(), mw.height())
        dlg.move(mw.x(), mw.y())
        dlg.setStyleSheet(STYLESHEET)

        v = QtWidgets.QVBoxLayout(dlg)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        # ── Formular-Bereich ──────────────────────────────────────
        editor = DruckerEditor(dc, hide_delete=hide_delete)
        v.addWidget(editor)

        # ── Trennlinie ────────────────────────────────────────────
        sep = QtWidgets.QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {COL_BORDER};")
        v.addWidget(sep)

        # ── Tastatur ──────────────────────────────────────────────
        kbd = OnScreenKeyboard()
        v.addWidget(kbd, stretch=1)

        # ── Abbrechen — flacher Streifen am unteren Rand ──────────
        sep2 = QtWidgets.QFrame(); sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {COL_BORDER};")
        v.addWidget(sep2)

        btn_cancel = QtWidgets.QPushButton("✕  Abbrechen")
        btn_cancel.setFixedHeight(40)
        btn_cancel.setFocusPolicy(QtCore.Qt.NoFocus)
        btn_cancel.setStyleSheet(
            f"QPushButton {{ background: {COL_BG_DARK}; color: {COL_TEXT_DIM}; "
            "border: none; border-radius: 0; font-size: 13px; }}"
            f"QPushButton:pressed {{ background: #2A2C32; color: {COL_TEXT}; }}"
        )
        btn_cancel.clicked.connect(dlg.reject)
        v.addWidget(btn_cancel)

        def on_saved(new_dc):
            self.hauptablauf.config.drucker_setzen(new_dc)
            self._toast("Gespeichert", f"Drucker {new_dc.id}")
            dlg.accept()

        def on_deleted(did):
            if self.hauptablauf.config.drucker_entfernen(did):
                self._toast("Entfernt", f"Drucker {did}")
            dlg.accept()

        editor.saved.connect(on_saved)
        editor.deleted.connect(on_deleted)
        dlg.exec_()

    def _on_config_changed(self):
        self._rebuild_drucker_kacheln()
        self._rebuild_kacheln()
        self._rebuild_service_drucker_btns()
        self._refresh()

    def _on_drucker_add(self):
        new_id = self.hauptablauf.config.naechste_freie_drucker_id()
        new_dc = DruckerConfig(id=new_id, name=f"Drucker {new_id}")
        self._open_drucker_editor(new_dc, hide_delete=True)

    # ============================================================
    # Action-Handler
    # ============================================================
    def _on_kachel_clicked(self, drucker_id: int):
        ok = self.hauptablauf.auftrag_aufnehmen(drucker_id, AuftragQuelle.HMI)
        self._toast("Auftrag " + ("angenommen" if ok else "abgelehnt"),
                    f"Drucker {drucker_id}")

    def _on_referenzfahrt(self):
        confirm = QtWidgets.QMessageBox.question(
            self, "Referenzfahrt", "Referenzfahrt jetzt durchführen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if confirm == QtWidgets.QMessageBox.Yes:
            if self.hauptablauf.state == SystemState.SERVICE:
                self.hauptablauf.service_modus_verlassen()
            self.hauptablauf.manuelle_referenzfahrt()
            self._switch("status")

    def _on_stop(self):
        self.hauptablauf.manueller_stop()

    def _on_quittieren(self):
        self.hauptablauf.fehler.quittieren()

    def _on_service_drucker(self, did: int):
        self._run_service_cmd(
            lambda: self.hauptablauf.service_fahre_zu_drucker(did),
            f"→ Drucker {did}")

    def _on_service_pos(self, ziel: str, label: str):
        self._run_service_cmd(
            lambda: self.hauptablauf.service_fahre_zu_position(ziel),
            f"→ {label}")

    def _run_service_cmd(self, fn, ok_label: str):
        if self._service_busy:
            return
        self._service_busy = True
        def run():
            ok = fn()
            self.signals.toast.emit("Schlitten", ok_label if ok else "Fehler")
            self._service_busy = False
        threading.Thread(target=run, daemon=True).start()

    # ============================================================
    # Slots
    # ============================================================
    def _on_auftrag_ok(self, a):
        self._toast("Wechsel abgeschlossen", f"Drucker {a.drucker_id}")

    def _on_auftrag_abgelehnt(self, a, grund):
        self._toast("Auftrag abgelehnt", grund)

    def _on_fehler_neu(self, f):
        self._switch("fehler")

    def _toast(self, titel: str, text: str, ms: int = 2500):
        t = QtWidgets.QLabel(f"{titel}\n{text}", self)
        t.setStyleSheet(f"""background: {COL_DHBW_RED}; color: white;
            padding: 12px 20px; border-radius: 8px;
            font-size: 13px; font-weight: 600;""")
        t.setAlignment(QtCore.Qt.AlignCenter)
        t.adjustSize()
        t.move((self.width() - t.width()) // 2, self.height() - t.height() - 30)
        t.show()
        QtCore.QTimer.singleShot(ms, t.deleteLater)

    # ============================================================
    # Tastatur
    # ============================================================
    def keyPressEvent(self, ev: QtGui.QKeyEvent):
        key = ev.key()
        if key in (QtCore.Qt.Key_1, QtCore.Qt.Key_2, QtCore.Qt.Key_3,
                   QtCore.Qt.Key_4, QtCore.Qt.Key_5):
            did = key - QtCore.Qt.Key_1 + 1
            if self.hauptablauf.gpio.mock_mode:
                self.hauptablauf.gpio.mock_drucker_fertig(did)
        elif key == QtCore.Qt.Key_X:
            if self.hauptablauf.gpio.mock_mode:
                self.hauptablauf.gpio.mock_endschalter("X")
        elif key == QtCore.Qt.Key_Z:
            if self.hauptablauf.gpio.mock_mode:
                self.hauptablauf.gpio.mock_endschalter("Z")
        elif key == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)
