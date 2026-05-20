"""Hauptablauf-Statemachine.

Plattenwechsel-Sequenz (Pi steuert ESP über PICKUP/DEPOSIT/OPEN_DOOR/CLOSE_DOOR/MOVE_TO):

  Phase 1 — Platte aus Drucker holen (Tür bleibt offen):
    1. MOVE_TO (drucker.x, drucker.z_anfahr)       ← Ausgangsposition
    2. OPEN_DOOR (x_approach=pos_x, z_approach=pos_z_tuer, arm_extend, radius, angle)
       → ESP fährt intern zur Tür, öffnet sie per Kreisbogen, kehrt zurück
    3. MOVE_TO (drucker.x, drucker.z_druckbett)    ← Gabel-Bereitschaftspos.
    4. PICKUP (gripper_depth, lift_offset)
    5. MOVE_TO (drucker.x, drucker.z_anfahr)       ← zurück zur Ausgangsposition

  Phase 2 — Platte ablegen:
    6. MOVE_TO ablage
    7. DEPOSIT (gripper_depth, lift_offset)

  Phase 3 — Neue Platte holen:
    8. MOVE_TO magazin
    9. PICKUP (gripper_depth, lift_offset)

  Phase 4 — Platte in Drucker einsetzen, dann Tür schließen:
   10. MOVE_TO (drucker.x, drucker.z_druckbett)
   11. DEPOSIT (gripper_depth, lift_offset)
   12. MOVE_TO (drucker.x, drucker.z_anfahr)
   13. CLOSE_DOOR (x_approach=berechnet, z_approach=pos_z_tuer, ...)
       → ESP schließt Tür per Kreisbogen, kehrt zurück

  Phase 5 — Heimfahrt (nur wenn Queue leer):
   14. MOVE_HOME
"""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from ..config import Config
from ..types import (
    SystemState, EspState, ErrorClass,
    Auftrag, AuftragQuelle, DruckerStatus,
    DruckerConfig,
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
        self._queue_bei_quittierung_leeren = False
        self.stats = _Stats()
        self._aktiver_drucker: Optional[int] = None
        self._pending_nach_service: set = set()  # Drucker-IDs die im Service-Modus gemeldet haben

        self._aktiver_auftrag: Optional[object] = None  # laufender Auftrag für Wiedereinreihung
        self._drucker_status: dict = {}
        self._refresh_drucker_status_keys()

        self.on_state_change: Optional[Callable] = None
        self.on_auftrag_erfolgreich: Optional[Callable] = None
        self.on_auftrag_abgelehnt: Optional[Callable] = None
        self.on_drucker_status_changed: Optional[Callable] = None
        self.on_drucker_config_changed: Optional[Callable] = None
        self.on_fehler_quittiert: Optional[Callable[[bool, Optional[str]], None]] = None  # args: waehrend_plattenwechsel, esp_code

        self._entscheidung_event = threading.Event()
        self._entscheidung: Optional[dict] = None  # {"referenzfahrt": bool, "queue_leeren": bool}

        # Timeouts
        self._move_timeout_s = float(config.get("esp", "move_timeout_s", default=60.0))
        self._home_timeout_s = float(config.get("esp", "home_timeout_s", default=30.0))
        self._mech_timeout_s = float(config.get("esp", "mech_timeout_s", default=10.0))
        self._fehler_dialog_timeout_s = float(config.get("esp", "fehler_dialog_timeout_s", default=300.0))

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
        if self.state == SystemState.SERVICE:
            self._pending_nach_service.add(drucker_id)
            self._set_drucker_status(drucker_id, DruckerStatus.IN_QUEUE)
            logger.info("Drucker %d im Service-Modus gemeldet — wird nach Service eingereiht", drucker_id)
            return
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

    def manueller_stop(self):
        try: self.esp.stop_motors()
        except Exception: pass
        n = self.queue.leeren()
        for did in list(self._drucker_status.keys()):
            self._set_drucker_status(did, DruckerStatus.BEREIT)
        if n:
            logger.info("Warteschlange geleert (%d Aufträge verworfen)", n)
        self.fehler.melde(
            ErrorClass.INTERNER_FEHLER,
            "Manueller Stopp — bitte Schlitten und Anlage prüfen "
            "(Platte auf Schlitten?)")

    def manuelle_referenzfahrt(self):
        if self.fehler.hat_fehler: return
        if self.state == SystemState.PLATTENWECHSEL: return
        self._set_state(SystemState.REFERENZFAHRT)

    def entscheidung_nach_fehler(self, referenzfahrt: bool, queue_leeren: bool):
        self._entscheidung = {"referenzfahrt": referenzfahrt, "queue_leeren": queue_leeren}
        self._entscheidung_event.set()

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
            for did in list(self._pending_nach_service):
                self.auftrag_aufnehmen(did, AuftragQuelle.DRUCKER_FERTIG)
            self._pending_nach_service.clear()

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

    def service_fahre_zu_ablage(self, ablage_id: int) -> bool:
        if self.state != SystemState.SERVICE: return False
        s = self.config.ablage(ablage_id)
        if s is None: return False
        try:
            self.esp.move_to(s.x, s.z, timeout_s=self._move_timeout_s)
            return True
        except PlattenwechslerError as e:
            self.fehler.melde(e.klasse,
                f"Service: Fahrt zu Ablage {ablage_id}: {e.nachricht}", esp_code=e.esp_code)
            return False

    def service_fahre_zu_magazin(self, magazin_id: int) -> bool:
        if self.state != SystemState.SERVICE: return False
        s = self.config.magazin(magazin_id)
        if s is None: return False
        try:
            self.esp.move_to(s.x, s.z, timeout_s=self._move_timeout_s)
            return True
        except PlattenwechslerError as e:
            self.fehler.melde(e.klasse,
                f"Service: Fahrt zu Magazin {magazin_id}: {e.nachricht}", esp_code=e.esp_code)
            return False

    def service_fahre_zu_position(self, x: int, z: int) -> bool:
        if self.state != SystemState.SERVICE: return False
        try:
            self.esp.move_to(x, z, timeout_s=self._move_timeout_s)
            return True
        except PlattenwechslerError as e:
            self.fehler.melde(e.klasse,
                f"Service: Manuelle Fahrt x={x} z={z}: {e.nachricht}", esp_code=e.esp_code)
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
        self.esp._force_referenced = False  # Override aufheben vor echter Referenzfahrt
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
            try: self.esp.stream_on()
            except Exception: logger.warning("STREAM_ON fehlgeschlagen")
            cmd_id = self.esp.home_start()
            # Schalter sofort melden falls Schlitten schon in Homeposition
            for axis in self.gpio.get_pressed_axes():
                logger.info("Endschalter %s bereits aktiv — HOME_SWITCH_HIT", axis)
                try: self.esp.home_switch_hit(axis)
                except Exception as e:
                    logger.warning("HOME_SWITCH_HIT %s: %s", axis, e)
            self.esp.home_wait(cmd_id, timeout_s=self._home_timeout_s)
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
        self._aktiver_auftrag = a
        self._set_drucker_status(a.drucker_id, DruckerStatus.AKTIV)
        self._set_state(SystemState.PLATTENWECHSEL)
        start = time.time()
        erfolg = False
        try:
            self._plattenwechsel(a, d)
            erfolg = True
            self.stats.auftraege_erfolgreich += 1
            self.stats.letzter_auftrag_dauer_s = time.time() - start
            if self.on_auftrag_erfolgreich:
                try: self.on_auftrag_erfolgreich(a)
                except Exception: logger.exception("on_auftrag_erfolgreich")
            self._set_drucker_status(a.drucker_id, DruckerStatus.BEREIT)
        finally:
            if self._aktiver_drucker is not None:
                self._set_drucker_status(self._aktiver_drucker, DruckerStatus.BEREIT)
            self._aktiver_drucker = None
            if erfolg:
                # Nur bei Erfolg direkt aufräumen — bei Fehler übernimmt _fehlerbehandlung_zyklus
                self._aktiver_auftrag = None
                self._set_state(SystemState.BEREITSCHAFT)

    # ============================================================
    # Plattenwechsel
    # ============================================================
    def _plattenwechsel(self, a: Auftrag, d: DruckerConfig):
        logger.info("Plattenwechsel start: %s", a)
        self._queue_bei_quittierung_leeren = True

        ablage = self.config.naechste_freie_ablage()
        if ablage is None:
            raise PlattenwechslerError(ErrorClass.ABLAGE_VOLL,
                "Kein freier Ablage-Platz — bitte Ablagen leeren und als frei markieren")

        magazin = self.config.naechstes_verfuegbares_magazin()
        if magazin is None:
            raise PlattenwechslerError(ErrorClass.MAGAZIN_LEER,
                "Kein Magazin-Platz verfügbar — bitte Platten einlegen und als verfügbar markieren")

        # Phase 1: alte Platte aus Drucker holen — Tür bleibt offen
        self._tuer_oeffnen(d)
        self._fahre(d.pos_x, d.pos_z_druckbett, f"Drucker {d.id} Abholposition")
        self._pickup(d.gripper_depth, d.lift_offset, f"Drucker {d.id}")
        self.esp.status.has_plate = True

        # Phase 2: alte Platte ablegen — Ablage als belegt markieren
        self._fahre(ablage.x, ablage.z, f"Ablage {ablage.id}")
        self._deposit(ablage.gripper_depth, ablage.lift_offset, f"Ablage {ablage.id}")
        self.esp.status.has_plate = False
        self.config.ablage_belegt_setzen(ablage.id, True)
        logger.info("Ablage %d als belegt markiert", ablage.id)

        # Phase 3: neue Platte aus Magazin — Magazin als leer markieren
        self._fahre(magazin.x, magazin.z, f"Magazin {magazin.id}")
        self._pickup(magazin.gripper_depth, magazin.lift_offset, f"Magazin {magazin.id}")
        self.esp.status.has_plate = True
        self.config.magazin_verfuegbar_setzen(magazin.id, False)
        logger.info("Magazin %d als leer markiert", magazin.id)

        # Phase 4: neue Platte einsetzen, dann Tür schließen
        self._fahre(d.pos_x, d.pos_z_druckbett, f"Drucker {d.id} Einlegeposition")
        self._deposit(d.gripper_depth, d.lift_offset, f"Drucker {d.id}")
        self.esp.status.has_plate = False
        self._tuer_schliessen(d)

        # Phase 5: Heim — nur wenn keine weiteren Aufträge warten
        if self.queue.is_empty():
            self._move_home()
        else:
            logger.info("Weitere Aufträge in Queue — Heimfahrt übersprungen")
        self._queue_bei_quittierung_leeren = False
        logger.info("Plattenwechsel %s erfolgreich", a)

    def _tuer_oeffnen(self, d: DruckerConfig):
        self._fahre(d.pos_x, d.pos_z_anfahr, f"Drucker {d.id} Ausgangsposition")
        logger.info("OPEN_DOOR Drucker %d", d.id)
        try:
            self.esp.open_door(
                x_approach=d.pos_x, z_approach=d.pos_z_tuer,
                arm_extend=d.door_arm_hub_mm,
                radius=d.tuer_radius, angle=d.tuer_winkel,
                timeout_s=self._move_timeout_s)
        except EspBefehlAbgelehnt as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Tür öffnen: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Tür öffnen: {e}")

    def _tuer_schliessen(self, d: DruckerConfig):
        x_close = d.pos_x + int(d.tuer_radius * (math.cos(math.radians(d.tuer_winkel)) - 1))
        self._fahre(d.pos_x, d.pos_z_anfahr, f"Drucker {d.id} Ausgangsposition (Schließen)")
        logger.info("CLOSE_DOOR Drucker %d x_approach=%d", d.id, x_close)
        try:
            self.esp.close_door(
                x_approach=x_close, z_approach=d.pos_z_tuer,
                arm_extend=d.door_arm_hub_mm,
                radius=d.tuer_radius, angle=d.tuer_winkel,
                timeout_s=self._move_timeout_s)
        except EspBefehlAbgelehnt as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Tür schließen: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.TUERFEHLER,
                f"Tür schließen: {e}")

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

    def _pickup(self, gripper_depth: int, lift_offset: int, kontext: str):
        logger.info("PICKUP gd=%d lo=%d (%s)", gripper_depth, lift_offset, kontext)
        try:
            self.esp.pickup(gripper_depth, lift_offset,
                            timeout_s=self._mech_timeout_s)
        except EspBefehlAbgelehnt as e:
            klasse = (ErrorClass.TUERFEHLER if e.esp_code == "DOOR_NOT_OPEN"
                      else ErrorClass.ENTNAHMEFEHLER)
            raise PlattenwechslerError(klasse,
                f"PICKUP {kontext}: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.ENTNAHMEFEHLER,
                f"PICKUP {kontext}: {e}")

    def _deposit(self, gripper_depth: int, lift_offset: int, kontext: str):
        logger.info("DEPOSIT gd=%d lo=%d (%s)", gripper_depth, lift_offset, kontext)
        try:
            self.esp.deposit(gripper_depth, lift_offset,
                             timeout_s=self._mech_timeout_s)
        except EspBefehlAbgelehnt as e:
            klasse = (ErrorClass.TUERFEHLER if e.esp_code == "DOOR_NOT_OPEN"
                      else ErrorClass.ENTNAHMEFEHLER)
            raise PlattenwechslerError(klasse,
                f"DEPOSIT {kontext}: {e.esp_code}", esp_code=e.esp_code)
        except (EspTimeoutError, EspKommunikationsError) as e:
            raise PlattenwechslerError(ErrorClass.ENTNAHMEFEHLER,
                f"DEPOSIT {kontext}: {e}")

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

        # UI nach Entscheidung fragen (threadsicher über Callback)
        waehrend_pw = self._queue_bei_quittierung_leeren
        esp_code = self.fehler.aktiver_fehler.esp_code if self.fehler.aktiver_fehler else None
        self._entscheidung = None
        self._entscheidung_event.clear()
        if self.on_fehler_quittiert:
            try: self.on_fehler_quittiert(waehrend_pw, esp_code)
            except Exception: logger.exception("on_fehler_quittiert")
        # Auf Entscheidung warten (max. 5 min, danach Standardverhalten)
        self._entscheidung_event.wait(timeout=self._fehler_dialog_timeout_s)
        entscheidung = self._entscheidung or {"referenzfahrt": True, "queue_leeren": waehrend_pw}

        if entscheidung["queue_leeren"] and self._queue_bei_quittierung_leeren:
            self._queue_bei_quittierung_leeren = False
            n = self.queue.leeren()
            for did in list(self._drucker_status.keys()):
                self._set_drucker_status(did, DruckerStatus.BEREIT)
            self.esp.status.has_plate = False
            logger.warning("Plattenwechsel unterbrochen: Queue geleert (%d Aufträge) "
                           "— bitte Ablage, Magazin und Schlitten prüfen", n)
        elif self._queue_bei_quittierung_leeren:
            self._queue_bei_quittierung_leeren = False

        try:
            if self.esp.is_connected():
                if self.esp.status.state == EspState.ERROR:
                    self.esp.reset_error()
                self.fehler.fehler_loeschen()
                if entscheidung["referenzfahrt"]:
                    self.esp._force_referenced = False
                    self._aktiver_auftrag = None
                    self._set_state(SystemState.REFERENZFAHRT)
                else:
                    self.esp.force_referenced()
                    # Schlitten physisch zurück zu 0/0 fahren (Endschalter bestätigen Position)
                    try:
                        self.esp.move_home(timeout_s=self._home_timeout_s)
                    except Exception as e:
                        logger.warning("MOVE_HOME nach Weitermachen fehlgeschlagen: %s", e)
                    # Fehlgeschlagenen Auftrag wieder vorne einreihen
                    if self._aktiver_auftrag is not None:
                        self.queue.vorne_einreihen(self._aktiver_auftrag)
                        logger.info("Auftrag %s wieder vorne in Queue eingereiht", self._aktiver_auftrag)
                        self._aktiver_auftrag = None
                    self._set_state(SystemState.BEREITSCHAFT)
                return
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
