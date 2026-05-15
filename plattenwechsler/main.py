"""Einstiegspunkt.

Aufruf:
  python -m plattenwechsler.main                 # echte Hardware
  python -m plattenwechsler.main --mock          # Mock-ESP, Mock-GPIO
  python -m plattenwechsler.main --no-gui        # ohne UI
  python -m plattenwechsler.main --no-mqtt       # ohne MQTT
"""
from __future__ import annotations

import argparse
import atexit
import logging
import signal
import sys
from typing import Optional

from .config import load_config
from .logger import setup_logging
from .core.fehler import FehlerBehandlung
from .core.hauptablauf import Hauptablauf
from .io_.gpio_manager import GpioManager
from .types import AuftragQuelle, DruckerConfig

logger = logging.getLogger("main")


def main() -> int:
    p = argparse.ArgumentParser(prog="plattenwechsler")
    p.add_argument("-c", "--config", default=None)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--no-gui", action="store_true")
    p.add_argument("--no-mqtt", action="store_true")
    p.add_argument("--no-telegram", action="store_true")
    p.add_argument("--no-fullscreen", action="store_true")
    args = p.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg.log_level, cfg.log_file)
    logger.info("=== Plattenwechsler startet ===")

    # ESP
    if args.mock:
        from .io_.mock_esp_client import MockEspClient
        esp = MockEspClient()
    else:
        from .io_.esp_client import EspClient
        esp = EspClient(
            port=cfg.get("esp", "port", default="/dev/ttyUSB0"),
            baud=cfg.get("esp", "baud", default=115200),
            read_timeout_s=cfg.get("esp", "read_timeout_s", default=0.1),
            heartbeat_timeout_s=cfg.get("esp", "heartbeat_timeout_s", default=5.0),
            reconnect_intervall_s=cfg.get("esp", "reconnect_intervall_s", default=2.0),
        )

    # GPIO
    gpio = GpioManager(
        drucker_fertig_pins=cfg.gpio_drucker_fertig(),
        endschalter_pins=cfg.gpio_endschalter(),
        not_aus_cfg=cfg.gpio_not_aus(),
        force_mock=args.mock,
    )

    fehler = FehlerBehandlung()
    hauptablauf = Hauptablauf(cfg, esp, gpio, fehler)

    # MQTT
    mqtt_client = None
    if cfg.get("mqtt", "enabled", default=True) and not args.no_mqtt:
        try:
            from .io_.mqtt_client import MqttClient
            mqtt_client = MqttClient(
                host=cfg.get("mqtt", "broker_host", default=""),
                port=cfg.get("mqtt", "broker_port", default=1883),
                username=cfg.get("mqtt", "username", default=""),
                password=cfg.get("mqtt", "password", default=""),
                client_id=cfg.get("mqtt", "client_id", default="plattenwechsler-pi"),
                base_topic=cfg.get("mqtt", "base_topic", default="plattenwechsler"),
                qos=cfg.get("mqtt", "qos", default=1),
                retain_status=cfg.get("mqtt", "retain_status", default=True),
            )
            def _on_auftrag_mqtt(did):
                ok = hauptablauf.auftrag_aufnehmen(did, AuftragQuelle.MQTT)
                mqtt_client.publish_response(
                    "auftrag", ok,
                    f"Drucker {did} in Queue" if ok
                    else f"Drucker {did}: abgelehnt (bereits in Queue oder System nicht bereit)")
            mqtt_client.on_befehl_auftrag = _on_auftrag_mqtt
            mqtt_client.on_befehl_quittieren = fehler.quittieren
            mqtt_client.on_befehl_referenzfahrt = hauptablauf.manuelle_referenzfahrt
            mqtt_client.on_befehl_stop = lambda: _safe(esp.stop_motors)
            mqtt_client.on_befehl_status_request = \
                lambda: _force_mqtt_publish(mqtt_client, hauptablauf)

            def _modus(aktiv):
                if aktiv: hauptablauf.service_modus_aktivieren()
                else: hauptablauf.service_modus_verlassen()
            mqtt_client.on_befehl_service_modus = _modus
            mqtt_client.on_befehl_service_fahre = hauptablauf.service_fahre_zu_position
            mqtt_client.on_befehl_service_drucker = hauptablauf.service_fahre_zu_drucker

            def _drucker_setzen(d: dict):
                try:
                    if "id" not in d:
                        d["id"] = cfg.naechste_freie_drucker_id()
                    cfg.drucker_setzen(DruckerConfig.from_dict(d))
                except Exception:
                    logger.exception("drucker_setzen via MQTT")
            mqtt_client.on_befehl_drucker_setzen = _drucker_setzen
            mqtt_client.on_befehl_drucker_entfernen = cfg.drucker_entfernen

            _start_mqtt_publisher(mqtt_client, hauptablauf)
        except Exception:
            logger.exception("MQTT konnte nicht gestartet werden")
            mqtt_client = None

    # Telegram
    tg_client = None
    if cfg.get("telegram", "enabled", default=False) and not args.no_telegram:
        try:
            from .io_.telegram_client import TelegramClient
            tg_client = TelegramClient(
                bot_token=cfg.get("telegram", "bot_token", default=""),
                allowed_chat_ids=cfg.get("telegram", "allowed_chat_ids", default=[]),
                send_status_to_first=cfg.get("telegram", "send_status_to_first",
                                              default=True),
            )
            tg_client.on_befehl_status = lambda: _telegram_status_text(hauptablauf)
            tg_client.on_befehl_auftrag = lambda did: hauptablauf.auftrag_aufnehmen(
                did, AuftragQuelle.TELEGRAM)
            tg_client.on_befehl_quittieren = fehler.quittieren
            tg_client.on_befehl_home = hauptablauf.manuelle_referenzfahrt
            tg_client.on_befehl_stop = lambda: _safe(esp.stop_motors)
        except Exception:
            logger.exception("Telegram konnte nicht gestartet werden")
            tg_client = None

    # Fehler / Auftragserfolg auch nach MQTT/Telegram
    def _broadcast_fehler(f):
        if mqtt_client:
            mqtt_client.publish_error({
                "klasse": f.klasse.value, "nachricht": f.nachricht,
                "esp_code": f.esp_code, "ts": f.timestamp,
            })
        if tg_client:
            tg_client.broadcast(f"🚨 *Fehler*: {f.klasse.value}\n{f.nachricht}")
    fehler.on_fehler_neu = _wrap_chain(fehler.on_fehler_neu, _broadcast_fehler)

    def _broadcast_ok(a):
        if mqtt_client:
            mqtt_client.publish_auftrag_event({
                "auftrag_id": a.auftrag_id, "drucker": a.drucker_id,
                "quelle": a.quelle.value, "ts": a.timestamp,
            })
        if tg_client:
            tg_client.broadcast(f"✅ Drucker {a.drucker_id} fertig gewechselt")
    hauptablauf.on_auftrag_erfolgreich = _wrap_chain(
        hauptablauf.on_auftrag_erfolgreich, _broadcast_ok)

    # Lifecycle
    gpio.setup()
    esp.start()
    if mqtt_client: mqtt_client.start()
    if tg_client:   tg_client.start()
    hauptablauf.start()

    _shutdown_done = False
    def _shutdown(*_):
        nonlocal _shutdown_done
        if _shutdown_done:
            return
        _shutdown_done = True
        logger.info("Shutdown")
        try: hauptablauf.stop()
        except Exception: pass
        try: gpio.teardown()
        except Exception: pass
        try: esp.stop()
        except Exception: pass
        if mqtt_client:
            try: mqtt_client.stop()
            except Exception: pass
        if tg_client:
            try: tg_client.stop()
            except Exception: pass
    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGHUP,  _shutdown)  # Terminal geschlossen
    atexit.register(_shutdown)                 # Sicherheitsnetz für normale Exits

    if args.no_gui:
        try: signal.pause()
        except Exception: pass
        _shutdown()
        return 0

    from PyQt5 import QtWidgets
    from .ui.main_window import MainWindow
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(
        hauptablauf,
        fullscreen=(cfg.get("hmi", "fullscreen", default=True)
                    and not args.no_fullscreen),
        width=cfg.get("hmi", "width", default=1280),
        height=cfg.get("hmi", "height", default=720),
    )
    win.show()
    rc = app.exec_()
    _shutdown()
    return rc


def _safe(fn, *a, **k):
    try: return fn(*a, **k)
    except Exception as e: logger.warning("safe-call: %s", e)


def _wrap_chain(orig, neu):
    if orig is None: return neu
    def chained(*a, **k):
        try: orig(*a, **k)
        except Exception: logger.exception("chained orig")
        try: neu(*a, **k)
        except Exception: logger.exception("chained neu")
    return chained


def _telegram_status_text(ha: Hauptablauf) -> str:
    s = ha.status_snapshot()
    f = s["fehler"]
    txt = (
        f"*Plattenwechsler*\n"
        f"System: `{s['system_state']}`\n"
        f"ESP: `{s['esp']['state']}` (ref={'1' if s['esp']['referenced'] else '0'})\n"
        f"Position: X={s['esp']['x_mm']} Z={s['esp']['z_mm']}\n"
        f"Queue: {s['queue_length']}\n"
        f"Erfolg/Abgelehnt/Fehler: "
        f"{s['stats']['erfolg']}/{s['stats']['abgelehnt']}/{s['stats']['fehler']}"
    )
    if f:
        txt += f"\n🚨 {f['klasse']} – {f['nachricht']}"
    return txt


def _force_mqtt_publish(mqtt_client, hauptablauf: Hauptablauf):
    try:
        snap = hauptablauf.status_snapshot()
        mqtt_client.publish_status(snap)
        mqtt_client.publish_esp_status(snap["esp"])
        for did, status in snap["drucker_status"].items():
            mqtt_client.publish_drucker_status(did, {"drucker_id": did, "status": status})
    except Exception:
        logger.exception("force_mqtt_publish")


def _start_mqtt_publisher(mqtt_client, hauptablauf: Hauptablauf,
                          intervall_s: float = 2.0):
    import threading, time as _t
    def loop():
        while True:
            try:
                if mqtt_client.is_connected():
                    snap = hauptablauf.status_snapshot()
                    mqtt_client.publish_status(snap)
                    mqtt_client.publish_esp_status(snap["esp"])
                    for did, status in snap["drucker_status"].items():
                        mqtt_client.publish_drucker_status(did, {
                            "drucker_id": did, "status": status,
                        })
            except Exception:
                logger.exception("MQTT-Publisher")
            _t.sleep(intervall_s)
    threading.Thread(target=loop, name="MqttPublisher", daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
