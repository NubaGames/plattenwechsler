"""Hauptablauf-Statemachine.

Plattenwechsel-Sequenz (Pi steuert ESP über SET_CLAMP/SET_DOOR_ARM/MOVE_TO):

  Phase 1 — Platte aus Drucker holen:
    1. MOVE_TO (drucker.x, drucker.z_anfahr)
    2. MOVE_TO (drucker.x, drucker.z_tuer)
    3. SET_DOOR_ARM OPEN
    4. STATUS-Check: door_open == True (VL53L0X am Schlitten misst)
    5. MOVE_TO (drucker.x, drucker.z_druckbett)
    6. SET_CLAMP CLOSED  → Platte gegriffen
    7. MOVE_TO (drucker.x, drucker.z_anfahr)
    8. MOVE_TO (drucker.x, drucker.z_tuer)
    9. SET_DOOR_ARM CLOSED

  Phase 2 — Platte ablegen:
   10. MOVE_TO ablage
   11. SET_CLAMP OPEN

  Phase 3 — Neue Platte holen:
   12. MOVE_TO magazin
   13. SET_CLAMP CLOSED

  Phase 4 — Platte in Drucker einsetzen (analog Phase 1, aber mit OPEN am Bett):
   14-22. wie Phase 1, Schritt 6 ist SET_CLAMP OPEN

  Phase 5 — Heimfahrt:
   23. MOVE_HOME
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from ..config import Config, Position
from ..types import (
    SystemState, EspState, ErrorClass,
    Auftrag, AuftragQuelle, DruckerStatus,
    ClampPosition, DoorArmPosition, DruckerConfig,
    PlattenwechslerError, EspKommunikationsError, EspBefehlAbgelehnt,
    EspTimeoutError,
)
from ..io_.esp_client import BaseEspClient
from ..io_.gpio_manager import GpioManager
from .auftrag_queue import AuftragsQueue
from .fehler import FehlerBehandlung

logger = logging.getLogger(__name__)


@dataclass
class _Stats:
    auftraege_erfolgreich: int = 0
    auftraege_abgelehnt: int = 0
    fehler_total: int = 0
    letzter_auftrag_dauer_s: float = 0.0


class Hauptablauf:
    def __init__(self, config: Config, esp: BaseEspClient,
                 gpio: GpioManager, fehler_handler: FehlerBehandlung):
        self.config = config
        self.esp = esp
        self.gpio = gpio
        self.fehler = fehler_handler

        self.queue = AuftragsQueue()
        self._state: SystemState = SystemState.INIT
        self._state_lock = threading.RLock()
        self._stop_flag = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._not_aus_aktiv = False
        self.stats = _Stats()
        self._aktiver_drucker: Optional[int] = None

        self._drucker_status: dict = {}
        self._refresh_drucker_status_keys()

        self.on_state_change: Optional[Callable] = None
        self.on_auftrag_erfolgreich: Optional[Callable] = None
        self.on_auftrag_abgelehnt: Optional[Callable] = None
        self.on_drucker_status_changed: Optional[Callable] = None
        self.on_drucker_config_changed: Optional[Callable] = None

        # Timeouts
        self._move_timeout_s = float(config.get("esp", "move_timeout_s", default=60.0))
        self._home_timeout_s = float(config.get("esp", "home_timeout_s", default=30.0))
        self._mech_timeout_s = float(config.get("esp", "mech_timeout_s", default=10.0))

        # GPIO-Callbacks
        self.gpio.on_drucker_fertig = self._on_drucker_fertig
        self.gpio.on_endschalter = self._on_endschalter
        self.gpio.on_not_aus = self._on_not_aus

        # ESP-Callbacks
        self.esp.on_error = self._on_esp_error
        self.esp.on_connection_lost = self._on_esp_disconnect

        self.config.on_save(self._on_config_saved)

    # ============================================================
    # Druckerstatus-Map
    # ============================================================
    def _refresh_drucker_status_keys(self):
        ids = {d.id for d in self.config.drucker_liste()}
        for did in ids:
            self._drucker_status.setdefault(did, DruckerStatus.BEREIT)
        for did in list(self._drucker_status.keys()):
            if did not in ids:
                del self._drucker_status[did]

    def _on_config_saved(self):
        self._refresh_drucker_status_keys()
        # GPIO-Pins ggf. neu einrichten
        try:
            self.gpio.aktualisiere_drucker_pins(self.config.gpio_drucker_fertig())
        except Exception:
            logger.exception("GPIO neu einrichten")
        if self.on_drucker_config_changed:
            try: self.on_drucker_config_changed()
            except Exception: logger.exception("on_drucker_config_changed")

    # ============================================================
    # State
    # ============================================================
    @property
    def state(self) -> SystemState:
        with self._state_lock:
            return self._state

    def _set_state(self, neu: SystemState):
        with self._state_lock:
            if self._state == neu: return
            alt = self._state
            self._state = neu
        logger.info("Systemzustand: %s → %s", alt.value, neu.value)
        if self.on_state_change:
            try: self.on_state_change(neu)
            except Exception: logger.exception("on_state_change")

    @property
    def aktiver_drucker(self) -> Optional[int]:
        return self._aktiver_drucker

    def get_drucker_status(self, drucker_id: int) -> DruckerStatus:
        return self._drucker_status.get(drucker_id, DruckerStatus.BEREIT)

    def _set_drucker_status(self, drucker_id: int, status: DruckerStatus):
        if self._drucker_status.get(drucker_id) == status: return
        self._drucker_status[drucker_id] = status
        if self.on_drucker_status_changed:
            try: self.on_drucker_status_changed(drucker_id, status)
            except Exception: logger.exception("on_drucker_status_changed")

    def start(self):
        logger.info("Hauptablauf gestartet")
        self._stop_flag.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="Hauptablauf", daemon=True)
        self._worker_thread.start()

    def stop(self):
        logger.info("Hauptablauf wird gestoppt")
        self._stop_flag.set()
        try: self.esp.stop_motors()
        except Exception: pass
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)

    # ============================================================
    # Trigger
    # ============================================================
    def _on_drucker_fertig(self, drucker_id: int):
        self._set_drucker_status(drucker_id, DruckerStatus.IN_QUEUE)
        self.auftrag_aufnehmen(drucker_id, AuftragQuelle.DRUCKER_FERTIG)

    def _on_endschalter(self, axis: str):
        if not self.esp.is_connected(): return
        try: self.esp.home_switch_hit(axis)
        except Exception as e: logger.error("HOME_SWITCH_HIT %s: %s", axis, e)

    def _on_not_aus(self):
        logger.critical("NOT-AUS")
        self._not_aus_aktiv = True
        try: self.esp.stop_motors()
        except Exception: pass
        self.fehler.melde(ErrorClass.NOT_AUS, "Not-Aus betätigt.")
        self._set_state(SystemState.NOT_AUS)

    def _on_esp_error(self, esp_code: str, status):
        self.fehler.melde_aus_esp_code(esp_code,
            nachricht_extra=f"x={status.x_mm}, z={status.z_mm}")

    def _on_esp_disconnect(self):
        if not self.fehler.hat_fehler:
            self.fehler.melde(ErrorClass.KOMMUNIKATIONSFEHLER,
                              "Verbindung zum ESP verloren")

    # ============================================================
    # Auftrags-API
    # ============================================================
    def auftrag_aufnehmen(self, drucker_id: int,
                          quelle: AuftragQuelle = AuftragQuelle.HMI) -> bool:
        d = self.config.drucker(drucker_id)
        if d is None:
            self._melde_ablehnung(drucker_id, quelle,
                f"Drucker {drucker_id} nicht konfiguriert")
            return False
        if self.fehler.hat_fehler:
            self._melde_ablehnung(drucker_id, quelle, "System im Fehlerzustand")
            return False
        if self._not_aus_aktiv:
            self._melde_ablehnung(drucker_id, quelle, "Not-Aus aktiv"); return False
        if self.state == SystemState.SERVICE:
            self._melde_ablehnung(drucker_id, quelle, "Service-Modus aktiv")
            return False
        a = Auftrag(drucker_id=drucker_id, quelle=quelle)
        if not self.queue.einreihen(a):
            self._melde_ablehnung(drucker_id, quelle,
                f"Drucker {drucker_id} bereits in Queue")
            return False
        self._set_drucker_status(drucker_id, DruckerStatus.IN_QUEUE)
        return True

    def _melde_ablehnung(self, did: int, quelle: AuftragQuelle, grund: str):
        self.stats.auftraege_abgelehnt += 1
        if self.on_auftrag_abgelehnt:
            try: self.on_auftrag_abgelehnt(Auftrag(drucker_id=did, quelle=quelle), grund)
            except Exception: logger.exception("on_auftrag_abgelehnt")

    def manuelle_referenzfahrt(self):
        if self.fehler.hat_fehler: return
        if self.state == SystemState.PLATTENWECHSEL: return
        self._set_state(SystemState.REFERENZFAHRT)

    # ============================================================
    # Service
    # ============================================================
    def service_modus_aktivieren(self) -> bool:
        if self.state not in (SystemState.BEREITSCHAFT, SystemState.SERVICE):
            return False
        self._set_state(SystemState.SERVICE)
        return True

    def service_modus_verlassen(self):
        if self.state == SystemState.SERVICE:
            self._set_state(SystemState.BEREITSCHAFT)

    def service_fahre_zu_drucker(self, drucker_id: int) -> bool:
        if self.state != SystemState.SERVICE: return False
        d = self.config.drucker(drucker_id)
        if d is None: return False
        try:
            self.esp.move_to(d.pos_x, d.pos_z_anfahr,
                             timeout_s=self._move_timeout_s)
            return True
        except PlattenwechslerError as e:
            self.fehler.melde(e.klasse,
                f"Service: Fahrt zu Drucker {drucker_id}: {e.nachricht}",
                esp_code=e.esp_code)
            return False

    def service_fahre_zu_position(self, ziel_name: str) -> bool:
        if self.state != SystemState.SERVICE: return False
        if ziel_name == "home":
            try:
                self.esp.move_home(timeout_s=self._home_timeout_s)
                return True
            except PlattenwechslerError as e:
                self.fehler.melde(e.klasse, f"Service: MOVE_HOME: {e.nachricht}",
                                   esp_code=e.esp_code)
                return False
        pos = self.config.position(ziel_name)
        if pos is None: return False
        try:
            self.esp.move_to(pos.x, pos.z, timeout_s=self._move_timeout_s)
            return True
        except PlattenwechslerError as e:
            self.fehler.melde(e.klasse, f"Service: Fahrt zu {ziel_name}: {e.nachricht}",
                               esp_code=e.esp_code)
            return False

    # ============================================================
    # Worker
    # ============================================================
    def _worker_loop(self):
        self._set_state(SystemState.INIT)
        if not self._initialisieren():
            self._set_state(SystemState.FEHLER)

        while not self._stop_flag.is_set():
            try:
                if self.fehler.hat_fehler or self.state == SystemState.NOT_AUS:
                    self._fehlerbehandlung_zyklus(); continue
                if self.state == SystemState.REFERENZFAHRT:
                    self._referenzfahrt(); continue
                if self.state == SystemState.SERVICE:
                    time.sleep(0.1); continue
                if self.state == SystemState.BEREITSCHAFT:
                    self._bereitschaft_zyklus(); continue
                self._set_state(SystemState.BEREITSCHAFT)
            except PlattenwechslerError as e:
                self.fehler.melde(e.klasse, e.nachricht, esp_code=e.esp_code)
                self.stats.fehler_total += 1
            except Exception as e:
                logger.exception("Unerwartet")
                self.fehler.melde(ErrorClass.INTERNER_FEHLER, f"Interner Fehler: {e}")
                self.stats.fehler_total += 1
            time.sleep(0.05)

    def _initialisieren(self) -> bool:
        logger.info("Init: warte auf ESP …")
        for _ in range(50):
            if self.esp.is_connected(): break
            time.sleep(0.1)
        if not self.esp.is_connected():
            self.fehler.melde(ErrorClass.KOMMUNIKATIONSFEHLER, "ESP nicht erreichbar")
            return False
        # ESP braucht beim Boot ~1s für VL53L0X + TF-Luna init
        time.sleep(1.0)
        if not self.esp.ping(ack_timeout_s=3.0):
            self.fehler.melde(ErrorClass.KOMMUNIKATIONSFEHLER, "ESP antwortet nicht")
            return False
        self._set_state(SystemState.REFERENZFAHRT)
        return True

    def _referenzfahrt(self):
        # skip_homing: solange Endschalter noch nicht verdrahtet sind,
        # können wir die Referenzfahrt überspringen und den ESP direkt auf
        # READY/referenziert setzen (nur für Tests ohne Hardware-Endschalter).
        if self.config.get("esp", "skip_homing", default=False):
            logger.warning("skip_homing=true — Referenzfahrt übersprungen, "
                           "ESP wird als referenziert angenommen")
            self._set_state(SystemState.BEREITSCHAFT)
            return

        logger.info("Referenzfahrt")
        try:
            self.esp.home(timeout_s=self._home_timeout_s)
        except EspBefehlAbgelehnt as e:
            raise PlattenwechslerError(ErrorClass.FAHRFEHLER,
                f"Referenzfahrt abgelehnt: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.FAHRFEHLER,
                f"Referenzfahrt: {e}")
        self._set_state(SystemState.BEREITSCHAFT)

    def _bereitschaft_zyklus(self):
        if self.queue.is_empty():
            time.sleep(0.1); return
        a = self.queue.naechsten()
        if a is None: return
        d = self.config.drucker(a.drucker_id)
        if d is None:
            logger.warning("Drucker %d nicht mehr in Konfig", a.drucker_id)
            return
        self._aktiver_drucker = a.drucker_id
        self._set_drucker_status(a.drucker_id, DruckerStatus.AKTIV)
        self._set_state(SystemState.PLATTENWECHSEL)
        start = time.time()
        try:
            self._plattenwechsel(a, d)
            self.stats.auftraege_erfolgreich += 1
            self.stats.letzter_auftrag_dauer_s = time.time() - start
            if self.on_auftrag_erfolgreich:
                try: self.on_auftrag_erfolgreich(a)
                except Exception: logger.exception("on_auftrag_erfolgreich")
            self._set_drucker_status(a.drucker_id, DruckerStatus.BEREIT)
        finally:
            self._aktiver_drucker = None
            if not self.fehler.hat_fehler:
                self._set_state(SystemState.BEREITSCHAFT)

    # ============================================================
    # Plattenwechsel
    # ============================================================
    def _plattenwechsel(self, a: Auftrag, d: DruckerConfig):
        logger.info("Plattenwechsel start: %s", a)
        ablage = self.config.position("ablage")
        magazin = self.config.position("magazin")
        if not (ablage and magazin):
            raise PlattenwechslerError(ErrorClass.INTERNER_FEHLER,
                "Konfig: Ablage oder Magazin nicht definiert")

        # Phase 1: alte Platte aus Drucker holen
        self._tuer_oeffnen(d)
        self._fahre(d.pos_x, d.pos_z_druckbett, f"Drucker {d.id} Druckbett")
        self._clamp(ClampPosition.CLOSED, "Platte greifen")
        self.esp.status.has_plate = True
        self._fahre(d.pos_x, d.pos_z_tuer, f"Drucker {d.id} Tür-Höhe (raus)")
        self._tuer_schliessen()

        # Phase 2: alte Platte ablegen
        self._fahre(ablage.x, ablage.z, "Ablage")
        self._clamp(ClampPosition.OPEN, "Platte ablegen")
        self.esp.status.has_plate = False

        # Phase 3: neue Platte aus Magazin
        self._fahre(magazin.x, magazin.z, "Magazin")
        self._clamp(ClampPosition.CLOSED, "Platte aus Magazin")
        self.esp.status.has_plate = True

        # Phase 4: neue Platte in Drucker einsetzen
        self._tuer_oeffnen(d)
        self._fahre(d.pos_x, d.pos_z_druckbett, f"Drucker {d.id} Druckbett")
        self._clamp(ClampPosition.OPEN, "Platte einsetzen")
        self.esp.status.has_plate = False
        self._fahre(d.pos_x, d.pos_z_tuer, f"Drucker {d.id} Tür-Höhe (raus)")
        self._tuer_schliessen()

        # Phase 5: Heim
        self._move_home()
        logger.info("Plattenwechsel %s erfolgreich", a)

    def _tuer_oeffnen(self, d: DruckerConfig):
        self._fahre(d.pos_x, d.pos_z_anfahr, f"Drucker {d.id} Anfahrt")
        self._fahre(d.pos_x, d.pos_z_tuer, f"Drucker {d.id} Tür-Höhe")
        try:
            self.esp.set_door_arm(DoorArmPosition.OPEN,
                                   timeout_s=self._mech_timeout_s)
        except EspBefehlAbgelehnt as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Türarm öffnen: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Türarm öffnen: {e}")
        # VL53L0X-Check: ist die Tür wirklich offen?
        time.sleep(0.3)
        try: self.esp.request_status()
        except Exception: pass
        if not self.esp.status.door_open:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Tür Drucker {d.id} öffnete nicht "
                f"(door_dist_mm={self.esp.status.door_dist_mm})")

    def _tuer_schliessen(self):
        try:
            self.esp.set_door_arm(DoorArmPosition.CLOSED,
                                   timeout_s=self._mech_timeout_s)
        except EspBefehlAbgelehnt as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Türarm schließen: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Türarm schließen: {e}")

    def _fahre(self, x: int, z: int, kontext: str):
        logger.info("MOVE_TO %s (x=%d z=%d)", kontext, x, z)
        try:
            self.esp.move_to(x, z, timeout_s=self._move_timeout_s)
        except EspBefehlAbgelehnt as e:
            klasse = (ErrorClass.HINDERNIS if e.esp_code == "OBSTACLE"
                      else ErrorClass.FAHRFEHLER)
            raise PlattenwechslerError(klasse,
                f"MOVE_TO {kontext}: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.FAHRFEHLER,
                f"MOVE_TO {kontext}: {e}")

    def _clamp(self, pos: ClampPosition, kontext: str):
        logger.info("SET_CLAMP %s (%s)", pos.value, kontext)
        try:
            self.esp.set_clamp(pos, timeout_s=self._mech_timeout_s)
        except EspBefehlAbgelehnt as e:
            raise PlattenwechslerError(ErrorClass.ENTNAHMEFEHLER,
                f"Halteservo {pos.value}: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.ENTNAHMEFEHLER,
                f"Halteservo {pos.value}: {e}")

    def _move_home(self):
        try:
            self.esp.move_home(timeout_s=self._home_timeout_s)
        except EspBefehlAbgelehnt as e:
            raise PlattenwechslerError(ErrorClass.FAHRFEHLER,
                f"MOVE_HOME: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.FAHRFEHLER, f"MOVE_HOME: {e}")

    # ============================================================
    # Fehlerbehandlung
    # ============================================================
    def _fehlerbehandlung_zyklus(self):
        try: self.esp.stop_motors()
        except Exception: pass
        if self.state not in (SystemState.FEHLER, SystemState.NOT_AUS):
            self._set_state(SystemState.FEHLER)
        if self._aktiver_drucker:
            self._set_drucker_status(self._aktiver_drucker, DruckerStatus.BEREIT)
        if not self.fehler.warte_auf_quittierung(timeout_s=1.0):
            return
        if self._not_aus_aktiv:
            self._not_aus_aktiv = False
        try:
            if self.esp.is_connected():
                if self.esp.status.state in (EspState.ERROR, EspState.STOPPED):
                    self.esp.reset_error()
                self.fehler.fehler_loeschen()
                self._set_state(SystemState.REFERENZFAHRT); return
            else:
                time.sleep(2.0); return
        except PlattenwechslerError as e:
            self.fehler.melde(e.klasse, f"Reset: {e.nachricht}", esp_code=e.esp_code)
        except Exception as e:
            self.fehler.melde(ErrorClass.INTERNER_FEHLER, f"Reset: {e}")

    # ============================================================
    # Snapshot
    # ============================================================
    def status_snapshot(self) -> dict:
        f = self.fehler.aktiver_fehler
        return {
            "system_state": self.state.value,
            "queue_length": len(self.queue),
            "queue": [
                {"id": a.auftrag_id, "drucker": a.drucker_id,
                 "quelle": a.quelle.value, "ts": a.timestamp}
                for a in self.queue.snapshot()
            ],
            "aktiver_drucker": self._aktiver_drucker,
            "drucker_status": {
                did: status.value
                for did, status in self._drucker_status.items()
            },
            "drucker_config": [d.to_dict() for d in self.config.drucker_liste()],
            "fehler": (None if f is None else {
                "klasse": f.klasse.value, "nachricht": f.nachricht,
                "esp_code": f.esp_code, "timestamp": f.timestamp,
                "quittiert": f.quittiert,
            }),
            "esp": {
                "connected": self.esp.is_connected(),
                "state": self.esp.status.state.value,
                "referenced": self.esp.status.referenced,
                "x_mm": self.esp.status.x_mm,
                "z_mm": self.esp.status.z_mm,
                "busy": self.esp.status.busy,
                "has_plate": self.esp.status.has_plate,
                "door_open": self.esp.status.door_open,
                "door_dist_mm": self.esp.status.door_dist_mm,
                "obstacle_ok": self.esp.status.obstacle_ok,
                "error": self.esp.status.error,
            },
            "stats": {
                "erfolg": self.stats.auftraege_erfolgreich,
                "abgelehnt": self.stats.auftraege_abgelehnt,
                "fehler": self.stats.fehler_total,
                "letzter_dauer_s": round(self.stats.letzter_auftrag_dauer_s, 1),
            },
        }
