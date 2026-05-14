"""GPIO-Manager: Drucker-fertig-Taster, Endschalter, Not-Aus.

Pins kommen dynamisch aus der Drucker-Konfig (pin_fertig pro Drucker).
Bei Konfig-Änderungen werden die Buttons neu eingerichtet.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Dict

logger = logging.getLogger(__name__)

try:
    from gpiozero import Button  # type: ignore
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False
    logger.info("gpiozero nicht verfügbar — Mock-Modus")


class GpioManager:
    def __init__(self,
                 drucker_fertig_pins: Dict[int, int],
                 endschalter_pins: Dict[str, int],
                 not_aus_cfg: Optional[dict] = None,
                 force_mock: bool = False):
        self.drucker_fertig_pins = dict(drucker_fertig_pins)
        self.endschalter_pins = dict(endschalter_pins)
        self.not_aus_cfg = not_aus_cfg or {}

        self.on_drucker_fertig: Optional[Callable[[int], None]] = None
        self.on_endschalter: Optional[Callable[[str], None]] = None
        self.on_not_aus: Optional[Callable[[], None]] = None

        self._devices: dict = {}
        self._mock_states: dict = {}
        self._mock_mode = force_mock or not GPIO_AVAILABLE
        self._lock = threading.Lock()
        self._setup_done = False

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    def setup(self) -> None:
        with self._lock:
            self._setup_internal()
            self._setup_done = True

    def aktualisiere_drucker_pins(self, neue_pins: Dict[int, int]) -> None:
        """Drucker-Pins haben sich geändert — Buttons neu einrichten."""
        with self._lock:
            self.drucker_fertig_pins = dict(neue_pins)
            if self._setup_done:
                self._teardown_drucker()
                self._setup_drucker_pins()

    def _setup_internal(self):
        if self._mock_mode:
            logger.info("GPIO Mock-Modus")
            for did in self.drucker_fertig_pins:
                self._mock_states[f"drucker_{did}"] = False
            self._mock_states["es_X"] = False
            self._mock_states["es_Z"] = False
            self._mock_states["not_aus"] = False
            return

        self._setup_drucker_pins()

        for axis, pin in self.endschalter_pins.items():
            btn = Button(pin, pull_up=True, bounce_time=0.02)
            btn.when_pressed = lambda a=axis.upper(): self._fire_endschalter(a)
            self._devices[f"es_{axis.upper()}"] = btn

        if self.not_aus_cfg.get("pin") is not None:
            pin = int(self.not_aus_cfg["pin"])
            invert = bool(self.not_aus_cfg.get("invert", False))
            btn = Button(pin, pull_up=not invert, bounce_time=0.05)
            btn.when_pressed = self._fire_not_aus
            self._devices["not_aus"] = btn
            logger.info("Not-Aus an Pin %d aktiv", pin)

    def _setup_drucker_pins(self):
        if self._mock_mode:
            return
        for did, pin in self.drucker_fertig_pins.items():
            try:
                btn = Button(pin, pull_up=True, bounce_time=0.1)
                btn.when_pressed = lambda d=did: self._fire_drucker_fertig(d)
                self._devices[f"drucker_{did}"] = btn
            except Exception as e:
                logger.error("GPIO-Pin %d für Drucker %d nicht verfügbar: %s",
                             pin, did, e)
        logger.info("GPIO bereit (%d Drucker-Taster)", len(self.drucker_fertig_pins))

    def _teardown_drucker(self):
        for k in list(self._devices):
            if k.startswith("drucker_"):
                try: self._devices[k].close()
                except Exception: pass
                del self._devices[k]

    def teardown(self):
        for d in self._devices.values():
            try: d.close()
            except Exception: pass
        self._devices.clear()

    def _fire_drucker_fertig(self, did: int):
        logger.info("Drucker %d meldet 'fertig'", did)
        if self.on_drucker_fertig:
            try: self.on_drucker_fertig(did)
            except Exception: logger.exception("on_drucker_fertig")

    def _fire_endschalter(self, axis: str):
        logger.info("Endschalter %s ausgelöst", axis)
        if self.on_endschalter:
            try: self.on_endschalter(axis)
            except Exception: logger.exception("on_endschalter")

    def _fire_not_aus(self):
        logger.critical("NOT-AUS!")
        if self.on_not_aus:
            try: self.on_not_aus()
            except Exception: logger.exception("on_not_aus")

    def get_pressed_axes(self) -> list:
        """Gibt aktuell gedrückte Endschalter-Achsen zurück."""
        if self._mock_mode:
            return [a for a in ("X", "Z") if self._mock_states.get(f"es_{a}")]
        return [a for a in ("X", "Z")
                if (d := self._devices.get(f"es_{a}")) and d.is_pressed]

    # ---- Mock-Trigger ----
    def mock_drucker_fertig(self, did: int):
        if not self._mock_mode: return
        self._mock_states[f"drucker_{did}"] = True
        self._fire_drucker_fertig(did)
        threading.Timer(2.0, lambda: self._mock_states.update(
            {f"drucker_{did}": False})).start()

    def mock_endschalter(self, axis: str):
        if not self._mock_mode: return
        axis = axis.upper()
        self._mock_states[f"es_{axis}"] = True
        self._fire_endschalter(axis)

    def mock_not_aus(self):
        if not self._mock_mode: return
        self._fire_not_aus()
