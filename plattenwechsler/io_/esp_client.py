"""ESP-Client (UART) — Pi ↔ ESP32 nach Schnittstellen-Spezifikation Mai 2026.

Befehle: PING, STATUS, STREAM_ON/OFF, HOME, MOVE_HOME, MOVE_TO, STOP,
RESET_ERROR, HOME_SWITCH_HIT, SET_CLAMP, SET_DOOR_ARM.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Callable, Optional

from ..types import (
    EspKommunikationsError, EspBefehlAbgelehnt, EspTimeoutError,
    EspState, EspStatus, ClampPosition, DoorArmPosition,
)

logger = logging.getLogger(__name__)

try:
    import serial  # type: ignore
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


@dataclass
class EspMessage:
    raw: str
    kind: str
    msg_id: int
    payload: list
    fields: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, line: str):
        line = line.strip()
        if not line:
            return None
        parts = line.split(";")
        if len(parts) < 3:
            return None
        kind = parts[0]
        if kind not in ("RSP", "EVT"):
            return None
        try:
            msg_id = int(parts[1])
        except ValueError:
            return None
        payload = parts[2:]
        fields = {}
        for p in payload:
            if "=" in p:
                k, _, v = p.partition("=")
                fields[k.strip()] = v.strip()
        return cls(raw=line, kind=kind, msg_id=msg_id,
                   payload=payload, fields=fields)


@dataclass
class _Pending:
    cmd_id: int
    sent_at: float
    event: threading.Event = field(default_factory=threading.Event)
    response: Optional[EspMessage] = None


class BaseEspClient:
    def __init__(self):
        self.status = EspStatus()
        self._lock = threading.RLock()
        self.on_state_change: Optional[Callable] = None
        self.on_status_update: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_event_ok: Optional[Callable] = None
        self.on_heartbeat: Optional[Callable] = None
        self.on_connection_lost: Optional[Callable] = None
        self.on_connection_restored: Optional[Callable] = None

    def start(self): raise NotImplementedError
    def stop(self):  raise NotImplementedError
    def is_connected(self) -> bool: raise NotImplementedError
    def send_and_wait(self, befehl: str, ack_timeout_s: float = 1.0,
                      **params) -> EspMessage: raise NotImplementedError
    def wait_for_event(self, cmd_id: int, event_name: str,
                       timeout_s: float) -> EspMessage: raise NotImplementedError

    # ---------- High-Level ----------
    def ping(self, ack_timeout_s: float = 1.0) -> bool:
        try:
            self.send_and_wait("PING", ack_timeout_s=ack_timeout_s)
            return True
        except Exception as e:
            logger.debug("PING fehl: %s", e)
            return False

    def request_status(self) -> EspStatus:
        self.send_and_wait("STATUS")
        time.sleep(0.05)
        return self.status

    def stream_on(self):  self.send_and_wait("STREAM_ON")
    def stream_off(self): self.send_and_wait("STREAM_OFF")

    def stop_motors(self):
        self.send_and_wait("STOP")

    def home_start(self) -> int:
        msg = self.send_and_wait("HOME")
        return msg.msg_id

    def home_wait(self, cmd_id: int, timeout_s: float = 30.0):
        self.wait_for_event(cmd_id, "HOME_DONE", timeout_s=timeout_s)

    def home(self, timeout_s: float = 30.0):
        self.home_wait(self.home_start(), timeout_s)

    def move_home(self, timeout_s: float = 30.0):
        msg = self.send_and_wait("MOVE_HOME")
        self.wait_for_event(msg.msg_id, "MOVE_HOME_DONE", timeout_s=timeout_s)

    def move_to(self, x_mm: int, z_mm: int, timeout_s: float = 60.0):
        msg = self.send_and_wait("MOVE_TO", x=x_mm, z=z_mm)
        self.wait_for_event(msg.msg_id, "MOVE_DONE", timeout_s=timeout_s)

    def reset_error(self):
        msg = self.send_and_wait("RESET_ERROR")
        self.wait_for_event(msg.msg_id, "ERROR_RESET", timeout_s=5.0)

    def home_switch_hit(self, axis: str):
        if axis not in ("X", "Z"):
            raise ValueError(f"Achse: {axis}")
        self.send_and_wait("HOME_SWITCH_HIT", axis=axis)

    def set_clamp(self, position: ClampPosition, timeout_s: float = 10.0):
        msg = self.send_and_wait("SET_CLAMP", position=position.value)
        self.wait_for_event(msg.msg_id, {
            ClampPosition.OPEN: "CLAMP_OPEN",
            ClampPosition.CLOSED: "CLAMP_CLOSED",
            ClampPosition.SERVICE: "CLAMP_SERVICE",
        }[position], timeout_s=timeout_s)

    def set_door_arm(self, position: DoorArmPosition,
                     timeout_s: float = 10.0):
        msg = self.send_and_wait("SET_DOOR_ARM", position=position.value)
        self.wait_for_event(msg.msg_id, {
            DoorArmPosition.OPEN: "DOOR_ARM_OPEN",
            DoorArmPosition.CLOSED: "DOOR_ARM_CLOSED",
        }[position], timeout_s=timeout_s)


# ============================================================
# Echter ESP-Client
# ============================================================
class EspClient(BaseEspClient):
    def __init__(self, port: str, baud: int = 115200,
                 read_timeout_s: float = 0.1,
                 heartbeat_timeout_s: float = 5.0,
                 reconnect_intervall_s: float = 2.0):
        super().__init__()
        if not SERIAL_AVAILABLE:
            raise RuntimeError("pyserial nicht installiert")
        self._port = port
        self._baud = baud
        self._read_timeout_s = read_timeout_s
        self._heartbeat_timeout_s = heartbeat_timeout_s
        self._reconnect_intervall_s = reconnect_intervall_s

        self._ser = None
        self._next_id = 1
        self._pending: dict = {}
        self._event_queues: dict = {}
        self._stop_flag = threading.Event()
        self._reader_thread = None
        self._watchdog_thread = None
        self._connected = False
        self._last_heartbeat = 0.0

    def is_connected(self) -> bool:
        return self._connected

    def start(self):
        self._stop_flag.clear()
        self._open_serial()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="EspReader", daemon=True)
        self._reader_thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="EspWatchdog", daemon=True)
        self._watchdog_thread.start()

    def stop(self):
        self._stop_flag.set()
        if self._ser:
            try: self._ser.close()
            except Exception: pass
        if self._reader_thread:
            self._reader_thread.join(timeout=2.0)
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=2.0)

    def stop_motors(self):
        msg = self.send_and_wait("STOP")
        _stop_err = EspMessage(
            raw="EVT;0;ERR;STOPPED", kind="EVT",
            msg_id=0, payload=["ERR", "STOPPED"], fields={})
        with self._lock:
            self._event_queues.pop(msg.msg_id, None)
            for q in list(self._event_queues.values()):
                try: q.put_nowait(("__ERR__", _stop_err))
                except Exception: pass
            self._event_queues.clear()

    def _open_serial(self) -> bool:
        try:
            self._ser = serial.Serial(
                self._port, self._baud, timeout=self._read_timeout_s,
                write_timeout=1.0)
            time.sleep(0.5)
            self._ser.reset_input_buffer()
            # ESP-Eingangs-Buffer leeren: ein leeres Newline schickt jeden
            # noch hängenden Müll als kompletten "Befehl" durch den Parser
            # (der ihn dann als InvalidCommand abweist), und macht den
            # Buffer für unseren ersten echten Befehl frei.
            self._ser.write(b"\n\n")
            self._ser.flush()
            time.sleep(0.2)
            self._ser.reset_input_buffer()
            self._connected = True
            self._last_heartbeat = time.time()
            logger.info("ESP verbunden: %s @ %d", self._port, self._baud)
            return True
        except Exception as e:
            logger.error("ESP nicht erreichbar (%s): %s", self._port, e)
            self._ser = None
            self._connected = False
            return False

    def _reader_loop(self):
        buf = b""
        while not self._stop_flag.is_set():
            if not self._ser:
                time.sleep(self._reconnect_intervall_s)
                self._open_serial()
                continue
            try:
                chunk = self._ser.read(256)
            except Exception as e:
                logger.warning("Lesefehler: %s", e)
                self._mark_disconnected()
                continue
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                try:
                    self._handle_line(line.decode("ascii", errors="replace"))
                except Exception:
                    logger.exception("handle_line")

    def _mark_disconnected(self):
        if self._connected:
            self._connected = False
            logger.error("ESP-Verbindung verloren")
            if self.on_connection_lost:
                try: self.on_connection_lost()
                except Exception: logger.exception("on_connection_lost")
        try:
            if self._ser: self._ser.close()
        except Exception: pass
        self._ser = None
        time.sleep(self._reconnect_intervall_s)

    def _watchdog_loop(self):
        while not self._stop_flag.is_set():
            time.sleep(0.5)
            if not self._connected: continue
            if self._last_heartbeat <= 0: continue
            if time.time() - self._last_heartbeat > self._heartbeat_timeout_s:
                logger.warning("Heartbeat ausgeblieben")
                self._mark_disconnected()

    def _handle_line(self, raw: str):
        msg = EspMessage.parse(raw)
        if not msg:
            if raw.strip(): logger.debug("Verworfen: %r", raw)
            return
        logger.debug("← %s", msg.raw)
        if msg.kind == "RSP":
            self._handle_rsp(msg)
        else:
            self._handle_evt(msg)

    def _handle_rsp(self, msg: EspMessage):
        with self._lock:
            pending = self._pending.pop(msg.msg_id, None)
        if not pending:
            # ID 0 = spontanes ESP-Startup-Event (kein ausstehender Befehl) — ignorieren
            if msg.msg_id != 0:
                logger.warning("RSP für unbekannte ID %d", msg.msg_id)
            return
        pending.response = msg
        pending.event.set()

    def _handle_evt(self, msg: EspMessage):
        evt_type = msg.payload[0] if msg.payload else ""
        if evt_type == "STATE":
            code = msg.payload[1] if len(msg.payload) > 1 else "UNKNOWN"
            self._update_state(code, msg.fields)
        elif evt_type == "STATUS":
            self._update_full_status(msg.fields)
        elif evt_type == "ERR":
            err_code = msg.payload[1] if len(msg.payload) > 1 else "UNKNOWN"
            with self._lock:
                self.status.state = EspState.ERROR
                self.status.error = err_code
                for q in self._event_queues.values():
                    q.put(("__ERR__", msg))
            logger.error("ESP-Fehler: %s", err_code)
            if self.on_error:
                try: self.on_error(err_code, self.status)
                except Exception: logger.exception("on_error")
        elif evt_type == "HEARTBEAT":
            self._last_heartbeat = time.time()
            try: uptime = int(msg.fields.get("uptime_ms", "0"))
            except ValueError: uptime = 0
            if self.on_heartbeat:
                try: self.on_heartbeat(uptime)
                except Exception: logger.exception("on_heartbeat")
        elif evt_type == "OK":
            event_name = msg.payload[1] if len(msg.payload) > 1 else ""
            with self._lock:
                q = self._event_queues.get(msg.msg_id)
            if q is not None:
                q.put((event_name, msg))
            if self.on_event_ok:
                try: self.on_event_ok(msg.msg_id, event_name, msg.fields)
                except Exception: logger.exception("on_event_ok")

    def _update_state(self, state_code: str, fields: dict):
        try: new_state = EspState(state_code)
        except ValueError: new_state = EspState.UNKNOWN
        with self._lock:
            self.status.state = new_state
            self.status.referenced = fields.get("ref", "0") == "1"
            self._set_int(fields, "x", "x_mm")
            self._set_int(fields, "z", "z_mm")
            self.status.last_update = time.time()
        if self.on_state_change:
            try: self.on_state_change(new_state)
            except Exception: logger.exception("on_state_change")

    def _update_full_status(self, f: dict):
        with self._lock:
            try: self.status.state = EspState(f.get("state", "UNKNOWN"))
            except ValueError: self.status.state = EspState.UNKNOWN
            self.status.error = f.get("error", "NONE")
            self.status.referenced = f.get("ref", "0") == "1"
            self._set_int(f, "x", "x_mm")
            self._set_int(f, "z", "z_mm")
            self._set_int(f, "target_x", "target_x_mm")
            self._set_int(f, "target_z", "target_z_mm")
            self.status.busy = f.get("busy", "0") == "1"
            self.status.gripper_home = f.get("gripper_home", "0") == "1"
            self.status.door_arm_home = f.get("door_arm_home", "0") == "1"
            self.status.obstacle_ok = f.get("obstacle_ok", "1") == "1"
            self.status.door_open = f.get("door_open", "0") == "1"
            self._set_int(f, "door_dist_mm", "door_dist_mm")
            self.status.last_update = time.time()
        if self.on_status_update:
            try: self.on_status_update(self.status)
            except Exception: logger.exception("on_status_update")

    def _set_int(self, fields: dict, key: str, attr: str):
        try: setattr(self.status, attr, int(fields.get(key, "0")))
        except (ValueError, TypeError): pass

    def _next_cmd_id(self) -> int:
        with self._lock:
            cid = self._next_id
            self._next_id = (self._next_id + 1) % 1_000_000
            if self._next_id == 0: self._next_id = 1
            return cid

    def send_and_wait(self, befehl: str, ack_timeout_s: float = 1.0,
                      **params) -> EspMessage:
        if not self._connected or not self._ser:
            raise EspKommunikationsError("ESP nicht verbunden")
        cmd_id = self._next_cmd_id()
        line = ";".join(["CMD", str(cmd_id), befehl] +
                        [f"{k}={v}" for k, v in params.items()])
        pending = _Pending(cmd_id=cmd_id, sent_at=time.time())
        eq: Queue = Queue()
        with self._lock:
            self._pending[cmd_id] = pending
            self._event_queues[cmd_id] = eq

        try:
            with self._lock:
                self._ser.write((line + "\n").encode("ascii"))
                self._ser.flush()
            logger.debug("→ %s", line)
        except Exception as e:
            with self._lock:
                self._pending.pop(cmd_id, None)
                self._event_queues.pop(cmd_id, None)
            self._mark_disconnected()
            raise EspKommunikationsError(f"Schreibfehler: {e}")

        if not pending.event.wait(timeout=ack_timeout_s):
            with self._lock:
                self._pending.pop(cmd_id, None)
            raise EspTimeoutError(
                f"Kein RSP für CMD;{cmd_id};{befehl} in {ack_timeout_s}s")

        rsp = pending.response
        if rsp.payload and rsp.payload[0] == "ACK":
            return rsp
        elif rsp.payload and rsp.payload[0] == "ERR":
            err_code = rsp.payload[1] if len(rsp.payload) > 1 else "UNKNOWN"
            with self._lock:
                self._event_queues.pop(cmd_id, None)
            raise EspBefehlAbgelehnt(err_code,
                f"ESP lehnte {befehl} ab: {err_code}")
        else:
            raise EspKommunikationsError(f"Unerwartet: {rsp.raw}")

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
                    raise EspTimeoutError(
                        f"Event {event_name} (ID {cmd_id}) nicht in {timeout_s}s")
                try:
                    name, msg = q.get(timeout=rest)
                except Empty:
                    continue
                if name == event_name:
                    return msg
                if name == "__ERR__":
                    err = msg.payload[1] if len(msg.payload) > 1 else "UNKNOWN"
                    raise EspBefehlAbgelehnt(err,
                        f"ESP-Fehler {err} während Warten auf {event_name}")
                logger.warning("Erwartet %s, bekam %s — ignoriert",
                               event_name, name)
        finally:
            with self._lock:
                self._event_queues.pop(cmd_id, None)
