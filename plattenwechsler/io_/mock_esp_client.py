"""Mock-ESP für Tests ohne Hardware. Implementiert die komplette Schnittstelle."""
from __future__ import annotations

import logging
import threading
import time
from queue import Queue
from typing import Optional

from .esp_client import BaseEspClient, EspMessage
from ..types import (
    EspState, EspStatus,
    EspKommunikationsError, EspTimeoutError, EspBefehlAbgelehnt,
)

logger = logging.getLogger(__name__)


class MockEspClient(BaseEspClient):
    def __init__(self, move_dauer_s: float = 0.4, home_dauer_s: float = 0.8,
                 mech_dauer_s: float = 0.3):
        super().__init__()
        self._move_dauer_s = move_dauer_s
        self._home_dauer_s = home_dauer_s
        self._mech_dauer_s = mech_dauer_s
        self._next_id = 1
        self._lock = threading.RLock()
        self._stop_flag = threading.Event()
        self._connected = False
        self._heartbeat_thread = None
        self._event_queues: dict = {}

        # Fehler-Injection
        self.simuliere_fehler: Optional[str] = None
        # Wenn False: OPEN_DOOR setzt door_open nicht auf True
        # (simuliert Tür die sich nicht geöffnet hat)
        self.tuer_offen_wenn_arm_aus = True

        # door_open startet True (offener Raum, kein Drucker davor)
        self.status = EspStatus(state=EspState.NOT_REFERENCED,
                                gripper_home=True, door_arm_home=True,
                                obstacle_ok=True, door_open=True)

    def is_connected(self) -> bool:
        return self._connected

    def start(self):
        self._connected = True
        self._stop_flag.clear()
        self._fire_state(EspState.NOT_REFERENCED)
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info("MockEspClient gestartet")

    def stop(self):
        self._stop_flag.set()
        self._connected = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)

    def _heartbeat_loop(self):
        uptime = 0
        while not self._stop_flag.is_set():
            time.sleep(1.0)
            uptime += 1000
            if self.on_heartbeat and self._connected:
                try: self.on_heartbeat(uptime)
                except Exception: pass

    def _next_cmd_id(self) -> int:
        with self._lock:
            cid = self._next_id
            self._next_id += 1
            return cid

    def _fire_state(self, neu: EspState):
        with self._lock:
            self.status.state = neu
        if self.on_state_change:
            try: self.on_state_change(neu)
            except Exception: pass

    def _fire_event_ok(self, cmd_id: int, name: str, **fields):
        with self._lock:
            q = self._event_queues.get(cmd_id)
        msg = EspMessage(raw=f"EVT;{cmd_id};OK;{name}", kind="EVT",
                         msg_id=cmd_id, payload=["OK", name], fields=fields)
        if q: q.put((name, msg))
        if self.on_event_ok:
            try: self.on_event_ok(cmd_id, name, fields)
            except Exception: pass

    def _fire_error(self, code: str):
        with self._lock:
            self.status.state = EspState.ERROR
            self.status.error = code
            err_msg = EspMessage(raw=f"EVT;0;ERR;{code}", kind="EVT",
                                 msg_id=0, payload=["ERR", code], fields={})
            for q in self._event_queues.values():
                q.put(("__ERR__", err_msg))
        if self.on_error:
            try: self.on_error(code, self.status)
            except Exception: pass

    def send_and_wait(self, befehl: str, ack_timeout_s: float = 1.0,
                      **params) -> EspMessage:
        if not self._connected:
            raise EspKommunikationsError("Mock-ESP nicht verbunden")
        cmd_id = self._next_cmd_id()
        with self._lock:
            self._event_queues[cmd_id] = Queue()
        ack = EspMessage(raw=f"RSP;{cmd_id};ACK", kind="RSP",
                         msg_id=cmd_id, payload=["ACK"], fields={})

        if befehl == "PING":
            self._fire_event_ok(cmd_id, "PONG"); return ack
        if befehl == "STATUS":
            if self.on_status_update:
                try: self.on_status_update(self.status)
                except Exception: pass
            return ack
        if befehl in ("STREAM_ON", "STREAM_OFF"):
            self._fire_event_ok(cmd_id, befehl); return ack
        if befehl == "STOP":
            self._fire_state(EspState.STOPPED)
            self._fire_event_ok(cmd_id, "STOPPED"); return ack

        if befehl == "HOME":
            if self.status.state == EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            self._fire_state(EspState.BUSY_HOMING)
            threading.Thread(target=self._async_home,
                             args=(cmd_id,), daemon=True).start()
            return ack

        if befehl == "MOVE_HOME":
            if not self.status.referenced:
                raise EspBefehlAbgelehnt("NOT_REFERENCED")
            if self.status.state == EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            self._fire_state(EspState.BUSY_MOVE_HOME)
            threading.Thread(target=self._async_move_home,
                             args=(cmd_id,), daemon=True).start()
            return ack

        if befehl == "MOVE_TO":
            if not self.status.referenced:
                raise EspBefehlAbgelehnt("NOT_REFERENCED")
            if self.status.state == EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            x = int(params.get("x", 0))
            z = int(params.get("z", 0))
            with self._lock:
                self.status.target_x_mm = x
                self.status.target_z_mm = z
                self.status.busy = True
            self._fire_state(EspState.BUSY_MOVING)
            threading.Thread(target=self._async_move,
                             args=(cmd_id, x, z),
                             daemon=True).start()
            return ack

        if befehl == "RESET_ERROR":
            if self.status.state != EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            with self._lock:
                self.status.error = "NONE"
                self.status.referenced = False
            self._fire_state(EspState.NOT_REFERENCED)
            self._fire_event_ok(cmd_id, "ERROR_RESET"); return ack

        if befehl == "HOME_SWITCH_HIT":
            return ack

        if befehl == "PICKUP":
            if not self.status.referenced:
                raise EspBefehlAbgelehnt("NOT_REFERENCED")
            if self.status.state == EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            if not self.status.door_open:
                raise EspBefehlAbgelehnt("DOOR_NOT_OPEN")
            lo = int(params.get("lift_offset", 8))
            self._fire_state(EspState.BUSY_PICKUP)
            threading.Thread(target=self._async_pickup,
                             args=(cmd_id, lo), daemon=True).start()
            return ack

        if befehl == "DEPOSIT":
            if not self.status.referenced:
                raise EspBefehlAbgelehnt("NOT_REFERENCED")
            if self.status.state == EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            if not self.status.door_open:
                raise EspBefehlAbgelehnt("DOOR_NOT_OPEN")
            lo = int(params.get("lift_offset", 8))
            self._fire_state(EspState.BUSY_DEPOSIT)
            threading.Thread(target=self._async_deposit,
                             args=(cmd_id, lo), daemon=True).start()
            return ack

        if befehl == "OPEN_DOOR":
            if not self.status.referenced or self.status.state == EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            self._fire_state(EspState.BUSY_OPEN_DOOR)
            threading.Thread(target=self._async_open_door,
                             args=(cmd_id,), daemon=True).start()
            return ack

        if befehl == "CLOSE_DOOR":
            if not self.status.referenced or self.status.state == EspState.ERROR:
                raise EspBefehlAbgelehnt("INVALID_STATE")
            self._fire_state(EspState.BUSY_CLOSE_DOOR)
            threading.Thread(target=self._async_close_door,
                             args=(cmd_id,), daemon=True).start()
            return ack

        raise EspBefehlAbgelehnt("INVALID_COMMAND")

    def stop_motors(self):
        super().stop_motors()
        _stop_err = EspMessage(
            raw="EVT;0;ERR;STOPPED", kind="EVT",
            msg_id=0, payload=["ERR", "STOPPED"], fields={})
        with self._lock:
            for q in list(self._event_queues.values()):
                try: q.put_nowait(("__ERR__", _stop_err))
                except Exception: pass
            self._event_queues.clear()

    def wait_for_event(self, cmd_id: int, event_name: str,
                       timeout_s: float) -> EspMessage:
        with self._lock:
            q = self._event_queues.get(cmd_id)
        if q is None:
            raise EspKommunikationsError(f"Keine Queue für {cmd_id}")
        deadline = time.time() + timeout_s
        try:
            while True:
                rest = deadline - time.time()
                if rest <= 0:
                    raise EspTimeoutError(f"Event {event_name} nicht erhalten")
                try:
                    name, msg = q.get(timeout=rest)
                except Exception:
                    continue
                if name == event_name:
                    return msg
                if name == "__ERR__":
                    err = msg.payload[1] if len(msg.payload) > 1 else "UNKNOWN"
                    raise EspBefehlAbgelehnt(err)
        finally:
            with self._lock:
                self._event_queues.pop(cmd_id, None)

    # ---------- Async ----------
    def _async_home(self, cmd_id: int):
        time.sleep(self._home_dauer_s)
        with self._lock:
            if self.status.state != EspState.BUSY_HOMING:
                return
        if self.simuliere_fehler == "HOMING_TIMEOUT":
            self._fire_error("HOMING_TIMEOUT"); return
        with self._lock:
            self.status.x_mm = 0; self.status.z_mm = 0
            self.status.referenced = True
        self._fire_event_ok(cmd_id, "HOME_DONE")
        self._fire_state(EspState.READY)

    def _async_move_home(self, cmd_id: int):
        time.sleep(self._home_dauer_s)
        with self._lock:
            if self.status.state != EspState.BUSY_MOVE_HOME:
                return
        if self.simuliere_fehler in ("HOMING_TIMEOUT", "MOVE_TIMEOUT"):
            self._fire_error(self.simuliere_fehler); return
        with self._lock:
            self.status.x_mm = 0; self.status.z_mm = 0
        self._fire_event_ok(cmd_id, "MOVE_HOME_DONE")
        self._fire_state(EspState.READY)

    def _async_move(self, cmd_id: int, x: int, z: int):
        time.sleep(self._move_dauer_s)
        with self._lock:
            if self.status.state != EspState.BUSY_MOVING:
                return
        if self.simuliere_fehler in ("OBSTACLE", "MOVE_TIMEOUT", "POSITION_ERROR"):
            self._fire_error(self.simuliere_fehler); return
        with self._lock:
            self.status.x_mm = x; self.status.z_mm = z
            self.status.busy = False
        self._fire_event_ok(cmd_id, "MOVE_DONE")
        self._fire_state(EspState.READY)

    def _async_pickup(self, cmd_id: int, lift_offset: int):
        time.sleep(self._mech_dauer_s)
        with self._lock:
            if self.status.state != EspState.BUSY_PICKUP:
                return
        if self.simuliere_fehler == "SENSOR_FAULT_GRIPPER":
            self._fire_error("SENSOR_FAULT_GRIPPER"); return
        if self.simuliere_fehler == "PLATE_NOT_DETECTED":
            self._fire_error("PLATE_NOT_DETECTED"); return
        with self._lock:
            self.status.z_mm += lift_offset
            self.status.plate_detected = True
            self.status.gripper_home = True
        self._fire_event_ok(cmd_id, "PICKUP_DONE")
        self._fire_state(EspState.READY)

    def _async_deposit(self, cmd_id: int, lift_offset: int):
        time.sleep(self._mech_dauer_s)
        with self._lock:
            if self.status.state != EspState.BUSY_DEPOSIT:
                return
        if self.simuliere_fehler == "SENSOR_FAULT_GRIPPER":
            self._fire_error("SENSOR_FAULT_GRIPPER"); return
        with self._lock:
            self.status.plate_detected = False
            self.status.gripper_home = True
        self._fire_event_ok(cmd_id, "DEPOSIT_DONE")
        self._fire_state(EspState.READY)

    def _async_open_door(self, cmd_id: int):
        time.sleep(self._mech_dauer_s)
        with self._lock:
            if self.status.state != EspState.BUSY_OPEN_DOOR:
                return
            self.status.door_arm_home = False
            self.status.door_open = self.tuer_offen_wenn_arm_aus
        self._fire_event_ok(cmd_id, "DOOR_OPEN_DONE")
        self._fire_state(EspState.READY)

    def _async_close_door(self, cmd_id: int):
        time.sleep(self._mech_dauer_s)
        with self._lock:
            if self.status.state != EspState.BUSY_CLOSE_DOOR:
                return
            self.status.door_arm_home = True
        self._fire_event_ok(cmd_id, "DOOR_CLOSE_DONE")
        self._fire_state(EspState.READY)
