"""Web-App für den Plattenwechsler.

  Browser  ──HTTP──>  Flask  ──MQTT──>  Pi-Hauptprogramm
  Browser  <─SSE──    Flask  <─MQTT─    Pi-Hauptprogramm

Aufruf:
    python3 -m webapp.app

Dann: http://<pi-ip>:5000
"""
from __future__ import annotations

import json
import logging
import threading
import time
from queue import Queue, Empty

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template, request, Response

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("webapp")


MQTT_HOST = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "plattenwechsler"
WEB_PORT = 5000


class StateStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.system = {}
        self.esp = {}
        self.online = False
        self.event_queues: list = []
        self.eq_lock = threading.Lock()

    def update_system(self, snap: dict):
        with self.lock:
            self.system = snap
        self._broadcast({"type": "system", "data": snap})

    def update_esp(self, esp: dict):
        with self.lock:
            self.esp = esp
        self._broadcast({"type": "esp", "data": esp})

    def update_online(self, online: bool):
        with self.lock:
            self.online = online
        self._broadcast({"type": "online", "data": online})

    def update_error(self, fehler: dict):
        self._broadcast({"type": "error", "data": fehler})

    def update_event(self, event: dict):
        self._broadcast({"type": "event", "data": event})

    def _broadcast(self, msg: dict):
        with self.eq_lock:
            for q in list(self.event_queues):
                try: q.put_nowait(msg)
                except Exception: pass

    def register_listener(self) -> Queue:
        q: Queue = Queue(maxsize=20)
        with self.eq_lock:
            self.event_queues.append(q)
        with self.lock:
            if self.system: q.put_nowait({"type": "system", "data": self.system})
            if self.esp: q.put_nowait({"type": "esp", "data": self.esp})
            q.put_nowait({"type": "online", "data": self.online})
        return q

    def unregister_listener(self, q: Queue):
        with self.eq_lock:
            if q in self.event_queues:
                self.event_queues.remove(q)


state = StateStore()


class MqttBridge:
    def __init__(self):
        self.client = mqtt.Client(client_id="plattenwechsler-webapp",
                                   clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self._connected = False

    def start(self):
        try:
            self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            self.client.loop_start()
            logger.info("MQTT-Bridge gestartet")
        except Exception as e:
            logger.error("MQTT: %s", e)

    def stop(self):
        try: self.client.loop_stop(); self.client.disconnect()
        except Exception: pass

    def is_connected(self) -> bool:
        return self._connected

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logger.info("MQTT verbunden")
            for t in [
                f"{BASE_TOPIC}/status/system",
                f"{BASE_TOPIC}/status/esp",
                f"{BASE_TOPIC}/status/online",
                f"{BASE_TOPIC}/error",
                f"{BASE_TOPIC}/event/auftrag",
            ]:
                client.subscribe(t, qos=1)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try: payload = msg.payload.decode("utf-8", errors="replace")
        except Exception: return
        try:
            if topic.endswith("/status/online"):
                state.update_online(payload == "online"); return
            data = json.loads(payload) if payload else {}
            if topic.endswith("/status/system"): state.update_system(data)
            elif topic.endswith("/status/esp"): state.update_esp(data)
            elif topic.endswith("/error"): state.update_error(data)
            elif topic.endswith("/event/auftrag"): state.update_event(data)
        except Exception:
            logger.exception("MQTT msg")

    def _publish(self, suffix: str, payload: dict) -> bool:
        if not self._connected: return False
        try:
            self.client.publish(f"{BASE_TOPIC}/{suffix}",
                                json.dumps(payload), qos=1)
            return True
        except Exception:
            logger.exception("publish")
            return False

    def cmd_auftrag(self, did): return self._publish("cmd/auftrag", {"drucker_id": did})
    def cmd_quittieren(self): return self._publish("cmd/quittieren", {})
    def cmd_referenzfahrt(self): return self._publish("cmd/referenzfahrt", {})
    def cmd_stop(self): return self._publish("cmd/stop", {})
    def cmd_service_modus(self, aktiv): return self._publish("cmd/service/modus", {"aktiv": aktiv})
    def cmd_service_fahre(self, ziel): return self._publish("cmd/service/fahre", {"ziel": ziel})
    def cmd_service_drucker(self, did): return self._publish("cmd/service/drucker", {"drucker_id": did})
    def cmd_drucker_setzen(self, dc): return self._publish("cmd/drucker/setzen", dc)
    def cmd_drucker_entfernen(self, did): return self._publish("cmd/drucker/entfernen", {"id": did})


bridge = MqttBridge()
app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    with state.lock:
        return jsonify({
            "online": state.online,
            "mqtt_connected": bridge.is_connected(),
            "system": state.system,
            "esp": state.esp,
        })


@app.route("/api/events")
def api_events():
    def stream():
        q = state.register_listener()
        try:
            yield ":connected\n\n"
            while True:
                try:
                    msg = q.get(timeout=15.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except Empty:
                    yield ": ping\n\n"
        finally:
            state.unregister_listener(q)
    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/api/cmd/auftrag", methods=["POST"])
def cmd_auftrag():
    did = int(request.json.get("drucker_id", 0))
    if did <= 0: return jsonify(error="ungültige drucker_id"), 400
    return jsonify(ok=bridge.cmd_auftrag(did))

@app.route("/api/cmd/quittieren", methods=["POST"])
def cmd_quittieren():
    return jsonify(ok=bridge.cmd_quittieren())

@app.route("/api/cmd/referenzfahrt", methods=["POST"])
def cmd_referenzfahrt():
    return jsonify(ok=bridge.cmd_referenzfahrt())

@app.route("/api/cmd/stop", methods=["POST"])
def cmd_stop():
    return jsonify(ok=bridge.cmd_stop())

@app.route("/api/cmd/service/modus", methods=["POST"])
def cmd_service_modus():
    return jsonify(ok=bridge.cmd_service_modus(bool(request.json.get("aktiv", False))))

@app.route("/api/cmd/service/fahre", methods=["POST"])
def cmd_service_fahre():
    ziel = str(request.json.get("ziel", ""))
    if not ziel: return jsonify(error="ziel fehlt"), 400
    return jsonify(ok=bridge.cmd_service_fahre(ziel))

@app.route("/api/cmd/service/drucker", methods=["POST"])
def cmd_service_drucker():
    did = int(request.json.get("drucker_id", 0))
    if did <= 0: return jsonify(error="ungültige drucker_id"), 400
    return jsonify(ok=bridge.cmd_service_drucker(did))

@app.route("/api/cmd/drucker/setzen", methods=["POST"])
def cmd_drucker_setzen():
    return jsonify(ok=bridge.cmd_drucker_setzen(request.json or {}))

@app.route("/api/cmd/drucker/entfernen", methods=["POST"])
def cmd_drucker_entfernen():
    did = int(request.json.get("id", 0))
    if did <= 0: return jsonify(error="ungültige id"), 400
    return jsonify(ok=bridge.cmd_drucker_entfernen(did))


def main():
    bridge.start()
    try:
        app.run(host="0.0.0.0", port=WEB_PORT, threaded=True,
                debug=False, use_reloader=False)
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()
