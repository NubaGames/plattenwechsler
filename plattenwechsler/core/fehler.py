"""Zentrale Fehlerbehandlung mit Quittierung und Historie."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable, List, Optional

from ..types import Fehler, ErrorClass, ESP_ERROR_TO_CLASS

logger = logging.getLogger(__name__)


class FehlerBehandlung:
    def __init__(self, historien_groesse: int = 100):
        self._aktiv: Optional[Fehler] = None
        self._lock = threading.RLock()
        self._historie: deque = deque(maxlen=historien_groesse)
        self._quittier_event = threading.Event()
        self.on_fehler_neu: Optional[Callable[[Fehler], None]] = None
        self.on_fehler_geloescht: Optional[Callable[[], None]] = None

    @property
    def hat_fehler(self) -> bool:
        with self._lock:
            return self._aktiv is not None

    @property
    def aktiver_fehler(self) -> Optional[Fehler]:
        with self._lock:
            return self._aktiv

    def melde(self, klasse: ErrorClass, nachricht: str,
              esp_code: Optional[str] = None) -> Optional[Fehler]:
        with self._lock:
            # Folgefehler unterdrücken (gleiche Klasse innerhalb von 2s)
            if self._aktiv and self._aktiv.klasse == klasse and \
               (time.time() - self._aktiv.timestamp) < 2.0:
                logger.debug("Folgefehler unterdrückt: %s", nachricht)
                return None
            f = Fehler(klasse=klasse, nachricht=nachricht, esp_code=esp_code)
            self._aktiv = f
            self._historie.append(f)
            self._quittier_event.clear()
        logger.error("Fehler: %s", f)
        if self.on_fehler_neu:
            try: self.on_fehler_neu(f)
            except Exception: logger.exception("on_fehler_neu")
        return f

    def melde_aus_esp_code(self, esp_code: str,
                           nachricht_extra: str = "") -> Optional[Fehler]:
        klasse = ESP_ERROR_TO_CLASS.get(esp_code, ErrorClass.INTERNER_FEHLER)
        msg = f"ESP: {esp_code}"
        if nachricht_extra:
            msg += f" ({nachricht_extra})"
        return self.melde(klasse, msg, esp_code=esp_code)

    def quittieren(self) -> bool:
        with self._lock:
            if not self._aktiv:
                return False
            self._aktiv.quittiert = True
            self._quittier_event.set()
        logger.info("Fehler quittiert")
        return True

    def warte_auf_quittierung(self, timeout_s: float = 1.0) -> bool:
        return self._quittier_event.wait(timeout=timeout_s)

    def fehler_loeschen(self) -> None:
        with self._lock:
            self._aktiv = None
            self._quittier_event.clear()
        if self.on_fehler_geloescht:
            try: self.on_fehler_geloescht()
            except Exception: logger.exception("on_fehler_geloescht")

    def historie(self, anzahl: int = 20) -> List[Fehler]:
        with self._lock:
            return list(self._historie)[-anzahl:][::-1]
