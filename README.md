# Plattenwechsler — Raspberry-Pi-Steuerung

**Projekt G6-TWIE23A · DHBW Stuttgart · IoT 2026**

Automatisiertes Bauplatten-Wechselsystem für mehrere 3D-Drucker.

## Mechanik

- **Schlitten** mit Halteservo (Klemme) und Türarm-Hebel — fährt entlang X/Z
- **Halteservo** klemmt die Platte (Positionen `OPEN`/`CLOSED`/`SERVICE`)
- **Türarm** drückt einzelne Drucker-Türen auf (`OPEN`/`CLOSED`)
- **TF-Luna LiDAR** am Schlitten: Hindernisscan vor jeder Fahrt aus Home
- **VL53L0X** am Schlitten: prüft nach Anfahrt vor dem Drucker, ob die Tür
  wirklich offen ist (`door_open` im STATUS)
- **Magazin** mit einer Ersatzplatte (1:1-Tausch)
- **Ablage** für die fertige Platte

## Architektur

```
┌──────────────────────────────────────────────┐
│ Raspberry Pi 4                               │
│  ├─ Touch-UI (PyQt5, Wayland)                │
│  ├─ Web-App (Flask + SSE)                    │
│  ├─ MQTT-Broker (Mosquitto)                  │
│  ├─ Telegram-Bot                             │
│  └─ Hauptprogramm (Statemachine)             │
└────────────┬─────────────────────────────────┘
             │ UART (115200 8N1)
┌────────────┴─────────────────────────────────┐
│ ESP32 auf dem Schlitten                      │
└──────────────────────────────────────────────┘
```

## Plattenwechsel-Ablauf

Pi orchestriert über `MOVE_TO`, `SET_CLAMP`, `SET_DOOR_ARM`. Der genaue
Ablauf siehe [`docs/Schnittstellen.md`](docs/Schnittstellen.md). Kurz:

```
Drucker → Anfahrt → Tür auf → Druckbett → Klemme zu → raus → Tür zu
       → Ablage → Klemme auf
       → Magazin → Klemme zu
       → Drucker → Anfahrt → Tür auf → Druckbett → Klemme auf → raus → Tür zu
       → Home
```

## Drucker-Konfiguration

Drucker werden zur Laufzeit über die UI oder Web-App verwaltet. Pro Drucker:

| Feld | Bedeutung |
|---|---|
| Name | freier Anzeigename |
| Pin Fertig-Taster | GPIO-Pin (BCM) |
| X-Position | mm |
| Z Anfahrt | sichere Höhe vor dem Drucker (mm) |
| Z Türarm-Höhe | Höhe an der der Türarm angreift (mm) |
| Z Druckbett | Höhe für Platte greifen/einsetzen (mm) |
| Türarm-Hub | Info-Wert (mm) |

Änderungen werden direkt in `config.yaml` gespeichert.

## Installation auf dem Pi

```bash
# System-Pakete
sudo apt install python3-pyqt5 python3-pip python3-venv \
                 mosquitto mosquitto-clients git unzip -y

# Projekt entpacken
cd ~ && unzip plattenwechsler.zip
cd plattenwechsler

# venv und Pakete
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt

# Mosquitto
sudo systemctl enable --now mosquitto
```

## Display-Rotation (Pi Touch Display 2)

In `~/.config/labwc/autostart`:
```bash
wlr-randr --output DSI-1 --transform 90 &
```

## Starten

Alias einmalig setzen (Wayland-Display):
```bash
echo 'alias platte="cd /home/nura/plattenwechsler && QT_QPA_PLATFORM=wayland WAYLAND_DISPLAY=wayland-0 venv/bin/python3 -m plattenwechsler.main"' >> ~/.bashrc
source ~/.bashrc
```

**Hauptprogramm:**
```bash
platte                    # echte Hardware, Vollbild
platte --mock             # Mock-ESP, ohne Hardware
platte --no-fullscreen    # im Fenster
platte --no-mqtt --no-telegram --no-gui   # nur Logik
```

**Web-App** (parallel):
```bash
cd ~/plattenwechsler && venv/bin/python3 -m webapp.app
```
Erreichbar unter `http://<pi-ip>:5000`

## Bedienung

5 Tabs in UI und Web-App:

- **Status** — Übersicht: Systemzustand, Position, Drucker, Queue
- **Manuell** — Plattenwechsel pro Drucker auslösen
- **Service** — Schlitten zu Drucker/Position fahren, Referenzfahrt
- **Drucker** — Drucker hinzufügen, bearbeiten, entfernen
- **Fehler** — aktueller Fehler, Quittierung, Historie

Der **STOP-Button** ist immer erreichbar.

## MQTT-Topics

**Status (retained):**
- `plattenwechsler/status/system` — kompletter Pi-Snapshot
- `plattenwechsler/status/esp` — ESP-Snapshot
- `plattenwechsler/status/online` — `online`/`offline`
- `plattenwechsler/status/drucker/<id>` — pro Drucker

**Events:**
- `plattenwechsler/error` — bei neuem Fehler
- `plattenwechsler/event/auftrag` — bei abgeschlossenem Plattenwechsel

**Befehle:**
- `plattenwechsler/cmd/auftrag` `{"drucker_id": N}`
- `plattenwechsler/cmd/quittieren` / `referenzfahrt` / `stop`
- `plattenwechsler/cmd/service/modus` `{"aktiv": true}`
- `plattenwechsler/cmd/service/fahre` `{"ziel": "home"|"ablage"|"magazin"}`
- `plattenwechsler/cmd/service/drucker` `{"drucker_id": N}`
- `plattenwechsler/cmd/drucker/setzen` `{"id":..., "pos_x":..., ...}`
- `plattenwechsler/cmd/drucker/entfernen` `{"id": N}`

## Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

## Tastatur (Mock-Modus)

| Taste | Wirkung |
|---|---|
| 1–5 | Drucker-fertig-Signal für Drucker N |
| X / Z | Endschalter X/Z auslösen |
| Esc | Programm beenden |

## Fehlerklassen

| Klasse | ESP-Codes / Auslöser |
|---|---|
| Kommunikationsfehler | `INVALID_COMMAND`, `BUSY`, `INVALID_STATE`, kein Heartbeat |
| Fahrfehler | `NOT_REFERENCED`, `MOVE_TIMEOUT`, `HOMING_TIMEOUT`, `POSITION_ERROR`, `DRIVER_FAULT` |
| Hindernis | `OBSTACLE` |
| Sensorfehler | `SENSOR_FAULT_OBSTACLE`, `SENSOR_FAULT_GRIPPER` |
| Türfehler | `door_open=0` nach `SET_DOOR_ARM OPEN` |
| Entnahmefehler | Pi-intern bei Clamp-Sequenz |
| Not-Aus | manuell per GPIO |

## Projektstruktur

```
plattenwechsler/
├── plattenwechsler/         # Python-Paket
│   ├── core/
│   │   ├── auftrag_queue.py
│   │   ├── fehler.py
│   │   └── hauptablauf.py   # Statemachine
│   ├── io_/
│   │   ├── esp_client.py    # UART zum ESP
│   │   ├── mock_esp_client.py
│   │   ├── gpio_manager.py
│   │   ├── mqtt_client.py
│   │   └── telegram_client.py
│   ├── ui/
│   │   └── main_window.py   # PyQt5-UI
│   ├── config.py            # YAML + dyn. Drucker
│   ├── logger.py
│   ├── main.py              # Einstiegspunkt
│   └── types.py             # Datentypen, Enums
├── webapp/                  # Flask-App
│   ├── app.py
│   ├── templates/index.html
│   └── static/{style.css,app.js}
├── tests/
│   ├── test_protokoll.py
│   └── test_hauptablauf_mock.py
├── docs/
│   └── Schnittstellen.md
├── config.yaml
├── requirements.txt
└── README.md
```
