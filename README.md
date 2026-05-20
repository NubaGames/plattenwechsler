# Plattenwechsler — Raspberry-Pi-Steuerung

**Projekt G6-TWIE23A · DHBW Stuttgart · IoT 2026**

Automatisiertes Bauplatten-Wechselsystem für mehrere 3D-Drucker.

## Mechanik

- **Schlitten** fährt entlang X/Z über zwei Achsen
- **Greifer** klemmt die Bauplatte (Positionen `OPEN`/`CLOSED`)
- **Türarm** öffnet und schließt einzelne Drucker-Türen (Bogenbewegung, konfigurierbar über Radius und Winkel)
- **TF-Luna LiDAR** am Schlitten: Hindernisscan vor jeder Fahrt aus Home
- **VL53L0X** am Schlitten: prüft nach Anfahrt vor dem Drucker, ob die Tür wirklich offen ist (`door_open` im STATUS)
- **Magazin** mit Ersatzplatten (1:1-Tausch, mehrere Slots möglich)
- **Ablage** für fertige Platten (mehrere Slots möglich)

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
│  (Motoren, Greifer, Türarm, Sensoren)        │
└──────────────────────────────────────────────┘
```

## Plattenwechsel-Ablauf

Der Pi orchestriert den gesamten Ablauf über `MOVE_TO`, `PICKUP`, `DEPOSIT`, `OPEN_DOOR`, `CLOSE_DOOR`. Kurzübersicht:

```
Drucker → Anfahrt → Tür auf (OPEN_DOOR)
        → Druckbett → Greifer schließt (PICKUP)
        → raus → Tür zu (CLOSE_DOOR)
        → Ablage → Greifer öffnet (DEPOSIT)
        → Magazin → Greifer schließt (PICKUP)
        → Drucker → Anfahrt → Tür auf (OPEN_DOOR)
        → Druckbett → Greifer öffnet (DEPOSIT)
        → raus → Tür zu (CLOSE_DOOR) → Home
```

Detaillierte Schnittstellenbeschreibung: [`docs/Schnittstellen_Doku.md`](docs/Schnittstellen_Doku.md)

## Drucker-Konfiguration

Drucker werden zur Laufzeit über die UI oder Web-App verwaltet. Pro Drucker:

| Feld | Bedeutung |
|---|---|
| Name | freier Anzeigename |
| Pin Fertig | GPIO-Pin (BCM) des Fertig-Signals |
| X-Position | X-Koordinate vor dem Drucker (mm) |
| Z Anfahrt | sichere Höhe vor dem Drucker (mm) |
| Z Türarm-Höhe | Höhe, auf der der Türarm angreift (mm) |
| Z Druckbett | Höhe für Platte greifen/einsetzen (mm) |
| Türarm-Hub | Ausfahrlänge des Türarms (mm) |
| Türradius | Abstand Türangel–Türarm-Angriffspunkt (mm) |
| Öffnungswinkel | Bogenwinkel beim Öffnen/Schließen (°) |
| Greifer-Tiefe | Einfahrtiefe des Greifers (mm) |
| Lift-Offset | Anhebung nach Pickup / vor Deposit (mm) |

Änderungen werden direkt in `config.yaml` gespeichert.

> **Hinweis:** Jeder GPIO-Pin darf nur einmal als Fertig-Pin vergeben werden. Die UI verhindert Doppelbelegungen.

## Ablage & Magazin

Jeder Slot (Ablage und Magazin) ist einzeln konfigurierbar (X/Z-Position, Greifer-Tiefe, Lift-Offset). Der Ablauf wählt automatisch den ersten passenden Slot (First-Fit). Der Belegungs-/Verfügbarkeitsstatus wird in `config.yaml` persistiert.

Im Service-Modus kann jeder Slot einzeln angefahren werden.

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

| Tab | Funktion |
|---|---|
| **Status** | Übersicht: Systemzustand, Position, Drucker, Queue |
| **Manuell** | Plattenwechsel pro Drucker manuell auslösen |
| **Service** | Schlitten zu Drucker/Ablage/Magazin fahren, Referenzfahrt |
| **Drucker** | Drucker hinzufügen, bearbeiten, entfernen |
| **Fehler** | aktueller Fehler, Quittierung, Fehlerhistorie |

Der **STOP-Button** ist jederzeit erreichbar und hält alle Motorbewegungen sofort an.

## MQTT-Topics

**Status (retained):**

| Topic | Inhalt |
|---|---|
| `plattenwechsler/status/system` | kompletter Pi-Snapshot |
| `plattenwechsler/status/esp` | ESP-Snapshot |
| `plattenwechsler/status/online` | `online` / `offline` |
| `plattenwechsler/status/drucker/<id>` | Status pro Drucker |

**Events:**

| Topic | Auslöser |
|---|---|
| `plattenwechsler/error` | neuer Fehler |
| `plattenwechsler/event/auftrag` | abgeschlossener Plattenwechsel |

**Befehle:**

| Topic | Payload | Wirkung |
|---|---|---|
| `plattenwechsler/cmd/auftrag` | `{"drucker_id": N}` | Plattenwechsel starten |
| `plattenwechsler/cmd/quittieren` | `{}` | Fehler quittieren |
| `plattenwechsler/cmd/referenzfahrt` | `{}` | Referenzfahrt starten |
| `plattenwechsler/cmd/stop` | `{}` | Sofort-Stop |
| `plattenwechsler/cmd/service/modus` | `{"aktiv": true}` | Service-Modus |
| `plattenwechsler/cmd/service/fahre` | `{"ziel": "home"\|"ablage"\|"magazin"}` | Fahrt im Service-Modus |
| `plattenwechsler/cmd/service/drucker` | `{"drucker_id": N}` | zu Drucker fahren |
| `plattenwechsler/cmd/drucker/setzen` | `{"id":..., "pos_x":..., ...}` | Drucker anlegen/aktualisieren |
| `plattenwechsler/cmd/drucker/entfernen` | `{"id": N}` | Drucker entfernen |

## Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

Tests laufen gegen den Mock-ESP (`MockEspClient`) und benötigen keine Hardware.

## Tastatur (Mock-Modus / Entwicklung)

| Taste | Wirkung |
|---|---|
| `1`–`5` | Fertig-Signal für Drucker N simulieren |
| `X` / `Z` | Endschalter X/Z auslösen |
| `Esc` | Programm beenden |

## Fehlerklassen

| Klasse | ESP-Codes / Auslöser |
|---|---|
| Kommunikationsfehler | `INVALID_COMMAND`, `BUSY`, `INVALID_STATE`, kein Heartbeat |
| Fahrfehler | `NOT_REFERENCED`, `MOVE_TIMEOUT`, `HOMING_TIMEOUT`, `POSITION_ERROR`, `DRIVER_FAULT` |
| Hindernis | `OBSTACLE` |
| Sensorfehler | `SENSOR_FAULT_OBSTACLE`, `SENSOR_FAULT_GRIPPER` |
| Türfehler | `door_open=0` nach `OPEN_DOOR`, ESP-Fehler bei OPEN/CLOSE_DOOR |
| Greiferfehler | `PLATE_NOT_DETECTED` nach PICKUP |
| Not-Aus | GPIO-Signal (konfigurierbar) |

Nach jedem behobenen Fehler ist eine **Referenzfahrt** erforderlich.

## Projektstruktur

```
plattenwechsler/
├── plattenwechsler/             # Python-Paket
│   ├── core/
│   │   ├── auftrag_queue.py     # Auftrags-Queue
│   │   ├── fehler.py            # Fehlerverwaltung
│   │   └── hauptablauf.py       # Statemachine & Plattenwechsel-Logik
│   ├── io_/
│   │   ├── esp_client.py        # UART-Schnittstelle zum ESP32
│   │   ├── mock_esp_client.py   # Software-Mock für Tests
│   │   ├── gpio_manager.py      # GPIO (Endschalter, Not-Aus, Fertig-Pins)
│   │   ├── mqtt_client.py       # MQTT-Integration
│   │   └── telegram_client.py   # Telegram-Bot
│   ├── ui/
│   │   └── main_window.py       # PyQt5-Vollbild-HMI
│   ├── config.py                # YAML-Konfiguration, DruckerConfig
│   ├── logger.py                # Logging-Setup
│   ├── main.py                  # Einstiegspunkt (CLI-Argumente)
│   └── types.py                 # Datentypen, Enums, EspState
├── webapp/                      # Flask-Web-App (parallel zur UI)
│   ├── app.py
│   ├── templates/index.html
│   └── static/{style.css,app.js}
├── tests/
│   ├── test_protokoll.py
│   └── test_hauptablauf_mock.py
├── docs/
│   ├── Schnittstellen_Doku.md           # Vollständige Schnittstellendokumentation
│   ├── Plattenwechsler_Doku_Pi.docx     # Projektdokumentation Pi-Seite
│   ├── MQTT_Anleitung.docx
│   ├── generate_doku.py                 # Doku-Generator (python-docx)
│   ├── esp_code/                        # ESP32-Quellcode
│   └── src/                             # Weitere Quellen
├── config.yaml                  # Hauptkonfiguration
├── requirements.txt
├── start.sh
└── README.md
```

## Abhängigkeiten

| Paket | Verwendung |
|---|---|
| `PyQt5` | Touch-UI |
| `pyserial` | UART zum ESP32 |
| `pyyaml` | Konfiguration |
| `paho-mqtt` | MQTT-Integration |
| `gpiozero` | GPIO-Zugriff |
| `flask` | Web-App |
| `python-docx` | Dokumentationsgenerator |
| `matplotlib` | Diagramme in der Doku |
| `pytest` | Tests |
