"""MQTT-Client.

Topics:
  Status (retained):
    plattenwechsler/status/online            "online"/"offline"
    plattenwechsler/status/system            JSON Pi-Snapshot
    plattenwechsler/status/esp               JSON ESP-Snapshot
    plattenwechsler/status/drucker/<id>      JSON pro Drucker

  Events:
    plattenwechsler/error                    JSON
    plattenwechsler/event/auftrag            JSON

  Befehle:
    plattenwechsler/cmd/auftrag              {"drucker_id": N}
    plattenwechsler/cmd/quittieren           (leer)
    plattenwechsler/cmd/referenzfahrt        (leer)
    plattenwechsler/cmd/stop                 (leer)
    plattenwechsler/cmd/service/modus        {"aktiv": true}
    plattenwechsler/cmd/service/fahre        {"ziel": "home"|"ablage"|"magazin"}
    plattenwechsler/cmd/service/drucker      {"drucker_id": N}
    plattenwechsler/cmd/drucker/setzen       {"id":..., "pos_x":..., ...}
    plattenwechsler/cmd/drucker/entfernen    {"id": N}
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt  # type: ignore
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False


class MqttClient:
    def __init__(self, host: str, port: int = 1883,
                 username: str = "", password: str = "",
                 client_id: str = "plattenwechsler-pi",
                 base_topic: str = "plattenwechsler",
                 qos: int = 1, retain_status: bool = True,
                 reconnect_intervall_s: float = 5.0):
        if not PAHO_AVAILABLE:
            raise RuntimeError("paho-mqtt nicht installiert")
        self._host = host
        self._port = port
        self._base = base_topic.rstrip("/")
        self._qos = int(qos)
        self._retain_status = bool(retain_status)

        self.on_befehl_auftrag: Optional[Callable[[int], None]] = None
        self.on_befehl_quittieren: Optional[Callable[[], None]] = None
        self.on_befehl_referenzfahrt: Optional[Callable[[], None]] = None
        self.on_befehl_stop: Optional[Callable[[], None]] = None
        self.on_befehl_service_modus: Optional[Callable[[bool], None]] = None
        self.on_befehl_service_fahre: Optional[Callable[[str], None]] = None
        self.on_befehl_service_drucker: Optional[Callable[[int], None]] = None
        self.on_befehl_drucker_setzen: Optional[Callable[[dict], None]] = None
        self.on_befehl_drucker_entfernen: Optional[Callable[[int], None]] = None

        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        if username:
            self._client.username_pw_set(username, password)
        self._client.will_set(f"{self._base}/status/online",
                              payload="offline", qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._connected = False
        self._stop_flag = threading.Event()

    @property
    def base(self) -> str:
        return self._base

    def start(self):
        if not self._host or self._host.startswith("BROKER"):
            logger.warning("Kein gültiger MQTT-Broker — MQTT inaktiv")
            return
        try:
            self._client.connect(self._host, self._port, keepalive=30)
            self._client.loop_start()
            logger.info("MQTT verbinde mit %s:%d", self._host, self._port)
        except Exception as e:
            logger.error("MQTT: %s", e)

    def stop(self):
        self._stop_flag.set()
        try:
            self._publish_safe(f"{self._base}/status/online", "offline", retain=True)
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass

    def is_connected(self) -> bool:
        return self._connected

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logger.info("MQTT verbunden")
            self._publish_safe(f"{self._base}/status/online", "online", retain=True)
            for t in [
                f"{self._base}/cmd/auftrag",
                f"{self._base}/cmd/quittieren",
                f"{self._base}/cmd/referenzfahrt",
                f"{self._base}/cmd/stop",
                f"{self._base}/cmd/service/modus",
                f"{self._base}/cmd/service/fahre",
                f"{self._base}/cmd/service/drucker",
                f"{self._base}/cmd/drucker/setzen",
                f"{self._base}/cmd/drucker/entfernen",
            ]:
                client.subscribe(t, qos=self._qos)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        logger.warning("MQTT getrennt (rc=%d)", rc)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try: payload = msg.payload.decode("utf-8", errors="replace")
        except Exception: payload = ""
        logger.info("MQTT %s: %s", topic, payload)
        try:
            data = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            data = {}
        try:
            if topic.endswith("/cmd/auftrag"):
                if self.on_befehl_auftrag and int(data.get("drucker_id", 0)) > 0:
                    self.on_befehl_auftrag(int(data["drucker_id"]))
            elif topic.endswith("/cmd/quittieren") and self.on_befehl_quittieren:
                self.on_befehl_quittieren()
            elif topic.endswith("/cmd/referenzfahrt") and self.on_befehl_referenzfahrt:
                self.on_befehl_referenzfahrt()
            elif topic.endswith("/cmd/stop") and self.on_befehl_stop:
                self.on_befehl_stop()
            elif topic.endswith("/cmd/service/modus") and self.on_befehl_service_modus:
                self.on_befehl_service_modus(bool(data.get("aktiv", False)))
            elif topic.endswith("/cmd/service/fahre") and self.on_befehl_service_fahre:
                if data.get("ziel"):
                    self.on_befehl_service_fahre(str(data["ziel"]))
            elif topic.endswith("/cmd/service/drucker") and self.on_befehl_service_drucker:
                if int(data.get("drucker_id", 0)) > 0:
                    self.on_befehl_service_drucker(int(data["drucker_id"]))
            elif topic.endswith("/cmd/drucker/setzen") and self.on_befehl_drucker_setzen:
                self.on_befehl_drucker_setzen(data)
            elif topic.endswith("/cmd/drucker/entfernen") and self.on_befehl_drucker_entfernen:
                if int(data.get("id", 0)) > 0:
                    self.on_befehl_drucker_entfernen(int(data["id"]))
        except Exception:
            logger.exception("MQTT-Befehl")

    def _publish_safe(self, topic: str, payload, retain: bool = False):
        if not self._connected:
            return
        try:
            if not isinstance(payload, (str, bytes, bytearray)):
                payload = json.dumps(payload, ensure_ascii=False)
            self._client.publish(topic, payload, qos=self._qos, retain=retain)
        except Exception:
            logger.exception("publish")

    def publish_status(self, snap: dict):
        self._publish_safe(f"{self._base}/status/system", snap,
                           retain=self._retain_status)

    def publish_esp_status(self, esp: dict):
        self._publish_safe(f"{self._base}/status/esp", esp,
                           retain=self._retain_status)

    def publish_drucker_status(self, drucker_id: int, dct: dict):
        self._publish_safe(f"{self._base}/status/drucker/{drucker_id}", dct,
                           retain=self._retain_status)

    def publish_error(self, fehler_dict: dict):
        self._publish_safe(f"{self._base}/error", fehler_dict, retain=False)

    def publish_auftrag_event(self, event_dict: dict):
        self._publish_safe(f"{self._base}/event/auftrag", event_dict, retain=False)
