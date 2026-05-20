# Schnittstellendokumentation — Plattenwechsler

**Projekt G6-TWIE23A · DHBW Stuttgart · IoT 2026**  
**Stand: Mai 2026**

Dieses Dokument beschreibt alle Schnittstellen des Systems:

1. [ESP32 ↔ Pi: UART-Protokoll](#1-esp32--pi-uart-protokoll)
2. [Pi ↔ Außenwelt: MQTT](#2-pi--außenwelt-mqtt)
3. [Pi ↔ Browser: Web-App API](#3-pi--browser-web-app-api)
4. [Pi: GPIO-Belegung](#4-pi-gpio-belegung)
5. [Konfigurationsschnittstelle (config.yaml)](#5-konfigurationsschnittstelle-configyaml)

---

## 1. ESP32 ↔ Pi: UART-Protokoll

### 1.1 Verbindung

| Parameter | Wert |
|---|---|
| Schnittstelle | UART over USB (`/dev/ttyUSB0`) |
| Baudrate | 115200, 8N1 |
| Encoding | ASCII, eine Nachricht pro Zeile (`\n` oder `\r\n`) |
| Feldtrenner | Semikolon `;` |
| Positionsangaben | Immer in **Millimeter** (Ganzzahl) |
| Max. Zeilenlänge | 160 Zeichen |
| Kommando-Queue | 8 Einträge; bei Überlauf: `RSP;<id>;ERR;BUSY` |

---

### 1.2 Pi → ESP: Kommandos

Alle Kommandos folgen dem Schema:

```
CMD;<id>;<befehl>[;<key>=<value>...]
```

`<id>` ist eine vom Pi vergebene Ganzzahl ≥ 0. Der ESP spiegelt sie in allen Antworten zurück.

| Kommando | Syntax | Voraussetzung |
|---|---|---|
| `PING` | `CMD;<id>;PING` | immer |
| `STATUS` | `CMD;<id>;STATUS` | immer |
| `STREAM_ON` | `CMD;<id>;STREAM_ON` | immer |
| `STREAM_OFF` | `CMD;<id>;STREAM_OFF` | immer |
| `STOP` | `CMD;<id>;STOP` | immer |
| `HOME` | `CMD;<id>;HOME` | nicht `ERROR`, nicht busy |
| `MOVE_HOME` | `CMD;<id>;MOVE_HOME` | `READY` oder `STOPPED`, referenziert |
| `MOVE_TO` | `CMD;<id>;MOVE_TO;x=<mm>;z=<mm>` | `READY` oder `STOPPED`, referenziert |
| `RESET_ERROR` | `CMD;<id>;RESET_ERROR` | nur in `ERROR` |
| `HOME_SWITCH_HIT` | `CMD;<id>;HOME_SWITCH_HIT;axis=<X\|Z>` | nur in `BUSY_HOMING` oder `BUSY_MOVE_HOME` |
| `OPEN_DOOR` | `CMD;<id>;OPEN_DOOR;x_approach=<mm>;z_approach=<mm>;arm_extend=<mm>;radius=<mm>;angle=<deg>;hook_drop=<mm>` | `READY` oder `STOPPED`, referenziert |
| `CLOSE_DOOR` | `CMD;<id>;CLOSE_DOOR;x_approach=<mm>;z_approach=<mm>;arm_extend=<mm>;radius=<mm>;angle=<deg>;hook_drop=<mm>` | `READY` oder `STOPPED`, referenziert |
| `PICKUP` | `CMD;<id>;PICKUP;gripper_depth=<mm>;lift_offset=<mm>` | `READY` oder `STOPPED`, referenziert |
| `DEPOSIT` | `CMD;<id>;DEPOSIT;gripper_depth=<mm>;lift_offset=<mm>` | `READY` oder `STOPPED`, referenziert |

---

#### OPEN_DOOR — Parameter

Der Pi berechnet `x_approach` selbst (= `pos_x` des Druckers). Der ESP führt die Bogenbewegung intern aus.

**Geometrie:** `Δx(θ) = radius · (cos(θ) − 1)`

**ESP-interner Ablauf:**
1. Schlitten fährt auf `(x_approach, z_approach)`
2. Türarm fährt `arm_extend` mm aus
3. Z fährt `hook_drop` mm nach oben (einhaken)
4. Kreisbogen öffnen: Arm mit konstanter Geschwindigkeit, X folgt
5. Z fährt `hook_drop` mm nach unten (aushaken)
6. Türarm fährt ein
7. Schlitten kehrt zur Ausgangsposition zurück

| Parameter | Typ | Bedeutung |
|---|---|---|
| `x_approach` | int (mm) | Absolute X-Anfahrposition |
| `z_approach` | int (mm) | Absolute Z-Anfahrposition |
| `arm_extend` | int (mm) | Ausfahrlänge Türarm |
| `radius` | int (mm) | Kreisradius (Scharnier → Greifpunkt) |
| `angle` | int (°) | Öffnungswinkel |
| `hook_drop` | int (mm) | Z-Versatz für Einhakmechanismus; `0` = kein Versatz |

```
CMD;7;OPEN_DOOR;x_approach=370;z_approach=105;arm_extend=30;radius=150;angle=160;hook_drop=15
```

---

#### CLOSE_DOOR — Parameter

Der Pi berechnet die Anfahrposition aus der OPEN_DOOR-Geometrie:

```
x_close_approach = x_open_approach + radius · (cos(angle) − 1)
```

Für angle > 0° ist `cos(angle) < 1`, d.h. `x_close < x_open` (Schlitten näher am Drucker).

**ESP-interner Ablauf:**
1. Schlitten fährt auf `(x_approach, z_approach)`
2. Türarm fährt auf Grifftiefe bei geöffneter Tür: `arm_extend + radius · sin(angle)` mm
3. Z fährt `hook_drop` mm nach oben (einhaken)
4. Kreisbogen schließen (rückwärts)
5. Z fährt `hook_drop` mm nach unten (aushaken)
6. Türarm fährt ein
7. Schlitten kehrt zur Ausgangsposition zurück

Parameter: identisch mit OPEN_DOOR (gleiche Werte).

```
CMD;10;CLOSE_DOOR;x_approach=79;z_approach=105;arm_extend=30;radius=150;angle=160;hook_drop=15
```

*(Beispiel: angle=160°, radius=150, x\_open=370 → x\_close ≈ 79 mm)*

---

#### PICKUP — Parameter

Der Schlitten steht bereits auf der Zielposition (vor Drucker oder Stellplatz).

**ESP-interner Ablauf:**
1. Greifer fährt `gripper_depth` mm aus
2. Z-Achse hebt um `lift_offset` mm → Platte auf der Gabel
3. Greifer fährt ein

| Parameter | Typ | Bedeutung |
|---|---|---|
| `gripper_depth` | int (mm) | Ausfahrtiefe des Greifers |
| `lift_offset` | int (mm) | Anhebung nach dem Ausfahren |

```
CMD;5;PICKUP;gripper_depth=120;lift_offset=8
```

---

#### DEPOSIT — Parameter

Der Schlitten trägt eine Platte und steht auf der Zielposition.

**ESP-interner Ablauf:**
1. Z-Achse hebt um `lift_offset` mm → Platte über Stellfläche
2. Greifer fährt `gripper_depth` mm aus
3. Z-Achse senkt um `lift_offset` mm → Platte liegt auf
4. Greifer fährt ein

| Parameter | Typ | Bedeutung |
|---|---|---|
| `gripper_depth` | int (mm) | Ausfahrtiefe des Greifers |
| `lift_offset` | int (mm) | Anhebung vor dem Ausfahren |

```
CMD;6;DEPOSIT;gripper_depth=120;lift_offset=8
```

---

#### HOME_SWITCH_HIT

Der Pi meldet einen ausgelösten Endschalter. Nur gültig in `BUSY_HOMING` und `BUSY_MOVE_HOME`.

> Die Schlitten-Endschalter (X, Z) sind am Pi angeschlossen. Greifer- und Türarm-Endschalter sitzen am ESP und werden intern ausgewertet.

```
CMD;2;HOME_SWITCH_HIT;axis=X
```

**Homing-Reihenfolge:**
- X-Achse fährt auf Endschalter → `HOME_SWITCH_HIT;axis=X` vom Pi
- Z-Achse fährt auf Endschalter → `HOME_SWITCH_HIT;axis=Z` vom Pi
- Greifer + Türarm referenzieren intern parallel
- `HOME_DONE` erst wenn alle vier Achsen referenziert sind

---

### 1.3 ESP → Pi: Antworten

#### RSP — Sofortantwort

Kommt direkt nach Empfang des Kommandos, bevor die Aktion abgeschlossen ist.

```
RSP;<id>;ACK               # Kommando akzeptiert, Aktion läuft
RSP;<id>;ERR;<fehlercode>  # Kommando abgelehnt, kein Motor gestartet
```

---

#### EVT — Ereignisse

```
EVT;<id>;OK;<event_name>;<felder>     # Aktion abgeschlossen
EVT;0;STATE;<zustand>;ref=<0|1>;x=<mm>;z=<mm>
EVT;0;STATUS;<alle Statusfelder>
EVT;0;ERR;<fehlercode>;x=<mm>;z=<mm>
EVT;0;HEARTBEAT;uptime_ms=<ms>;state=<zustand>;x=<mm>;z=<mm>
```

| event\_name | Auslöser |
|---|---|
| `PONG` | Antwort auf PING |
| `HOME_DONE` | Referenzfahrt abgeschlossen |
| `MOVE_HOME_DONE` | Heimfahrt abgeschlossen |
| `MOVE_DONE` | Zielposition erreicht |
| `STOPPED` | STOP ausgeführt |
| `ERROR_RESET` | RESET\_ERROR ausgeführt |
| `STREAM_ON` / `STREAM_OFF` | Stream-Zustand geändert |
| `DOOR_OPEN_DONE` | Tür geöffnet, Schlitten auf Ausgangsposition |
| `DOOR_CLOSE_DONE` | Tür geschlossen, Türarm eingefahren |
| `PICKUP_DONE` | Plattenentnahme abgeschlossen |
| `DEPOSIT_DONE` | Plattenablage abgeschlossen |

---

#### EVT STATUS — Vollständiger Snapshot

Wird gesendet: auf `STATUS`-Kommando, bei jedem `ERROR`-Eintritt, periodisch wenn Stream aktiv (100 ms).

| Feld | Typ | Bedeutung |
|---|---|---|
| `state` | enum | Aktueller Zustand |
| `error` | string | Aktiver Fehlercode (`NONE` wenn kein Fehler) |
| `ref` | 0/1 | `1` = referenziert |
| `x`, `z` | int (mm) | Ist-Position |
| `target_x`, `target_z` | int (mm) | Soll-Position |
| `busy` | 0/1 | Bewegung aktiv |
| `gripper_home` | 0/1 | Greifer in Heimposition |
| `door_arm_home` | 0/1 | Türarm in Heimposition |
| `obstacle_ok` | 0/1 | Hindernissensor gesund und frei |
| `door_open` | 0/1 | Druckertür offen (VL53L0X-Auswertung) |
| `door_dist_mm` | int (mm) | Rohwert Türsensor (Debugging) |
| `plate_detected` | 0/1 | Plattenerkennungs-Taster aktiv |

---

### 1.4 Zustandscodes

| Code | Bedeutung |
|---|---|
| `NOT_REFERENCED` | Bereit, Referenzfahrt noch nicht durchgeführt |
| `READY` | Referenziert, wartet auf Kommando |
| `BUSY_HOMING` | Referenzfahrt läuft |
| `BUSY_SCANNING` | Z-Scan vor Fahrt aus Home-Position |
| `BUSY_MOVING` | Fahrt zu Zielposition |
| `BUSY_MOVE_HOME` | Heimfahrt läuft |
| `BUSY_PICKUP` | Plattenentnahme läuft |
| `BUSY_DEPOSIT` | Plattenablage läuft |
| `BUSY_OPEN_DOOR` | Türöffnung läuft |
| `BUSY_CLOSE_DOOR` | Türschließung läuft |
| `STOPPED` | Per STOP angehalten |
| `ERROR` | Fehler, alle Motoren gestoppt, wartet auf `RESET_ERROR` |

**Übergänge:**
- `STOP` → `STOPPED` aus jedem Zustand außer `ERROR`
- `STOPPED` verhält sich wie `READY` (HOME, MOVE_TO, MOVE_HOME erlaubt)
- Jeder Fehler aus einem `BUSY_*`-Zustand → sofort `ERROR`
- `RESET_ERROR` → `NOT_REFERENCED`, Referenzierung gelöscht

---

### 1.5 Fehlercodes

| Code | Klasse | Bedeutung |
|---|---|---|
| `INVALID_COMMAND` | Kommunikation | Unbekanntes Kommando oder Syntaxfehler |
| `BUSY` | Kommunikation | Kommando-Queue voll |
| `INVALID_STATE` | Kommunikation | Kommando im aktuellen Zustand nicht erlaubt |
| `NOT_REFERENCED` | Fahrt | MOVE\_TO ohne vorherige Referenzfahrt |
| `MOVE_TIMEOUT` | Fahrt | Zielposition nicht rechtzeitig erreicht |
| `HOMING_TIMEOUT` | Fahrt | Referenzfahrt-Timeout |
| `POSITION_ERROR` | Fahrt | Rücklese-Position außerhalb Toleranz |
| `OBSTACLE` | Hindernis | TF-Luna unterschreitet Stoppabstand |
| `SENSOR_FAULT_OBSTACLE` | Sensor | TF-Luna defekt oder nicht initialisierbar |
| `SENSOR_FAULT_GRIPPER` | Sensor | Greifer-Endschalter antwortet nicht |
| `DRIVER_FAULT` | Motor | Closed-Loop-Treiber meldet Alarm |
| `PLATE_NOT_DETECTED` | Greifer | Nach PICKUP kein Plattenerkennungs-Taster |
| `DOOR_NOT_OPEN` | Tür | Türsensor meldet zu geringe Distanz vor PICKUP/DEPOSIT |

---

### 1.6 Typische Kommunikationssequenzen

#### Referenzfahrt

```
→ CMD;1;HOME
← RSP;1;ACK
← EVT;0;STATE;BUSY_HOMING;ref=0;x=0;z=0
  [X-Achse fährt auf Endschalter]
→ CMD;2;HOME_SWITCH_HIT;axis=X
← RSP;2;ACK
  [Z-Achse fährt auf Endschalter]
→ CMD;3;HOME_SWITCH_HIT;axis=Z
← RSP;3;ACK
← EVT;1;OK;HOME_DONE;x=0;z=0
← EVT;0;STATE;READY;ref=1;x=0;z=0
```

#### Tür öffnen

```
→ CMD;7;OPEN_DOOR;x_approach=370;z_approach=105;arm_extend=30;radius=150;angle=160;hook_drop=15
← RSP;7;ACK
← EVT;0;STATE;BUSY_OPEN_DOOR;ref=1;x=350;z=120
  [Schlitten fährt auf Anfahrposition, Kreisbogen, Rückfahrt]
← EVT;7;OK;DOOR_OPEN_DONE;x=350;z=120
← EVT;0;STATE;READY;ref=1;x=350;z=120
```

#### Plattenentnahme (PICKUP)

```
→ CMD;5;PICKUP;gripper_depth=120;lift_offset=8
← RSP;5;ACK
← EVT;0;STATE;BUSY_PICKUP;ref=1;x=350;z=120
← EVT;5;OK;PICKUP_DONE;x=350;z=128
← EVT;0;STATE;READY;ref=1;x=350;z=128
```

#### Fehlerfall und Quittierung

```
→ CMD;4;MOVE_TO;x=500;z=120
← RSP;4;ACK
← EVT;0;STATE;BUSY_MOVING;ref=1;x=350;z=120
← EVT;0;ERR;OBSTACLE;x=412;z=120
← EVT;0;STATE;ERROR;ref=1;x=412;z=120
← EVT;0;STATUS;state=ERROR;error=OBSTACLE;...
→ CMD;5;RESET_ERROR
← RSP;5;ACK
← EVT;5;OK;ERROR_RESET
← EVT;0;STATE;NOT_REFERENCED;ref=0;x=0;z=0
```

---

### 1.7 Plattenwechsel-Sequenz (Pi-Logik)

Der Pi orchestriert alle 17 Schritte über die o.g. Befehle:

```
Schritt  1: MOVE_TO  (drucker.pos_x, drucker.pos_z_anfahr)
Schritt  2: OPEN_DOOR (x_approach=pos_x, z_approach=pos_z_tuer,
                       arm_extend, radius, angle)
Schritt  3: STATUS → door_open == 1? (sonst TUERFEHLER)
Schritt  4: MOVE_TO  (drucker.pos_x, drucker.pos_z_druckbett)
Schritt  5: PICKUP   (gripper_depth, lift_offset)
Schritt  6: MOVE_TO  (drucker.pos_x, drucker.pos_z_anfahr)
Schritt  7: CLOSE_DOOR (x_approach=x_close, ...)
Schritt  8: MOVE_TO  (ablage.x, ablage.z)
Schritt  9: DEPOSIT  (gripper_depth, lift_offset)   ← alte Platte abgelegt
Schritt 10: MOVE_TO  (magazin.x, magazin.z)
Schritt 11: PICKUP   (gripper_depth, lift_offset)   ← neue Platte
Schritt 12: MOVE_TO  (drucker.pos_x, drucker.pos_z_anfahr)
Schritt 13: OPEN_DOOR (...)
Schritt 14: STATUS → door_open == 1?
Schritt 15: MOVE_TO  (drucker.pos_x, drucker.pos_z_druckbett)
Schritt 16: DEPOSIT  (gripper_depth, lift_offset)   ← neue Platte eingesetzt
Schritt 17: MOVE_TO  (drucker.pos_x, drucker.pos_z_anfahr)
            CLOSE_DOOR (...)
            MOVE_HOME
```

---

## 2. Pi ↔ Außenwelt: MQTT

Broker: Mosquitto (lokal auf dem Pi, `localhost:1883`).  
Alle Topics verwenden den Base-Topic aus `config.yaml` (Standard: `plattenwechsler-g6twie23a`).

### 2.1 Status-Topics (retained)

| Topic | Inhalt | Trigger |
|---|---|---|
| `<base>/status/system` | Vollständiger Pi-Snapshot (JSON) | jede Zustandsänderung |
| `<base>/status/esp` | ESP-Status (JSON) | jedes ESP-STATUS-Event |
| `<base>/status/online` | `online` / `offline` | Verbindung / Will-Message |
| `<base>/status/drucker/<id>` | Drucker-Status (JSON) | Fertig-Pin, Zustandsänderung |

### 2.2 Event-Topics

| Topic | Inhalt | Trigger |
|---|---|---|
| `<base>/error` | Fehlerdetails (JSON) | neuer Fehler |
| `<base>/event/auftrag` | Ergebnis Plattenwechsel (JSON) | abgeschlossener Auftrag |

### 2.3 Befehls-Topics

Alle Befehle werden als JSON-Payload gesendet. Der Pi quittiert nicht per MQTT — Ergebnisse kommen über die Status-Topics.

| Topic | Payload | Wirkung |
|---|---|---|
| `<base>/cmd/auftrag` | `{"drucker_id": N}` | Plattenwechsel für Drucker N starten |
| `<base>/cmd/quittieren` | `{}` | Fehler quittieren (→ Referenzfahrt nötig) |
| `<base>/cmd/referenzfahrt` | `{}` | Referenzfahrt starten |
| `<base>/cmd/stop` | `{}` | Sofort-Stop |
| `<base>/cmd/service/modus` | `{"aktiv": true\|false}` | Service-Modus ein-/ausschalten |
| `<base>/cmd/service/fahre` | `{"ziel": "home"\|"ablage"\|"magazin"}` | Fahrt im Service-Modus |
| `<base>/cmd/service/drucker` | `{"drucker_id": N}` | Zu Drucker N fahren (Service) |
| `<base>/cmd/drucker/setzen` | `{Drucker-Objekt, s.u.}` | Drucker anlegen oder aktualisieren |
| `<base>/cmd/drucker/entfernen` | `{"id": N}` | Drucker entfernen |

**Drucker-Objekt für `drucker/setzen`:**
```json
{
  "id": 1,
  "name": "Drucker 1",
  "pin_fertig": 27,
  "pos_x": 370,
  "pos_z_anfahr": 120,
  "pos_z_tuer": 105,
  "pos_z_druckbett": 50,
  "door_arm_hub_mm": 30,
  "tuer_radius": 150,
  "tuer_winkel": 160,
  "gripper_depth": 120,
  "lift_offset": 8
}
```

---

## 3. Pi ↔ Browser: Web-App API

Die Flask-Web-App läuft auf Port `5000` und stellt eine REST-ähnliche API bereit.

### 3.1 GET

| Endpunkt | Rückgabe |
|---|---|
| `GET /` | HTML-Oberfläche (Single Page) |
| `GET /api/state` | Aktueller System-Snapshot (JSON) |
| `GET /api/events` | Server-Sent Events (SSE-Stream), Content-Type `text/event-stream` |

**SSE-Events:**
- `state` — System-Snapshot bei jeder Zustandsänderung
- `error` — Fehlerdetails

### 3.2 POST

Alle POST-Endpunkte erwarten JSON-Body und geben `{"ok": true}` oder `{"error": "..."}` zurück.

| Endpunkt | Body | Wirkung |
|---|---|---|
| `POST /api/cmd/auftrag` | `{"drucker_id": N}` | Plattenwechsel starten |
| `POST /api/cmd/quittieren` | `{}` | Fehler quittieren |
| `POST /api/cmd/referenzfahrt` | `{}` | Referenzfahrt starten |
| `POST /api/cmd/stop` | `{}` | Sofort-Stop |
| `POST /api/cmd/service/modus` | `{"aktiv": true\|false}` | Service-Modus |
| `POST /api/cmd/service/fahre` | `{"ziel": "home"\|"ablage"\|"magazin"}` | Service-Fahrt |
| `POST /api/cmd/service/drucker` | `{"drucker_id": N}` | Zu Drucker fahren |
| `POST /api/cmd/drucker/setzen` | Drucker-Objekt (s. MQTT) | Drucker anlegen/aktualisieren |
| `POST /api/cmd/drucker/entfernen` | `{"id": N}` | Drucker entfernen |

---

## 4. Pi: GPIO-Belegung

Alle Pins in BCM-Nummerierung. Konfiguriert in `config.yaml`, Abschnitt `gpio`.

### 4.1 Eingänge (Pi ← Hardware)

| Pin (BCM) | Funktion | Auslöser |
|---|---|---|
| 17 | Endschalter X-Achse | Schlitten an Home-Position X |
| 4 | Endschalter Z-Achse | Schlitten an Home-Position Z |
| 26 | Not-Aus | Sicherheitsschalter (konfigurierbar invertiert) |
| pro Drucker | Fertig-Pin | Drucker meldet „Druck fertig" (frei konfigurierbar) |

> Die Endschalter-Pins und der Not-Aus-Pin sind in `config.yaml` konfigurierbar.  
> Fertig-Pins werden pro Drucker in der Konfiguration vergeben und müssen eindeutig sein (keine Doppelbelegung).

### 4.2 Signalverarbeitung

| Signal | Verarbeitung |
|---|---|
| Endschalter X/Z | Pi sendet sofort `HOME_SWITCH_HIT;axis=<X\|Z>` an ESP |
| Not-Aus | Pi sendet `STOP` an ESP, Zustand → GESTOPPT |
| Drucker-Fertig | Pi legt Auftrag in die Queue |

### 4.3 Verbindung ESP

| Verbindung | Detail |
|---|---|
| UART | `/dev/ttyUSB0`, 115200 Baud |
| Richtung | bidirektional, vollduplex |

---

## 5. Konfigurationsschnittstelle (config.yaml)

Die Konfiguration wird beim Start geladen und bei Änderungen über die UI oder MQTT direkt zurückgeschrieben.

### 5.1 Abschnitt `system`

```yaml
system:
  log_level: DEBUG       # DEBUG | INFO | WARNING | ERROR
  log_file: /home/nura/plattenwechsler/plattenwechsler.log
```

### 5.2 Abschnitt `esp`

```yaml
esp:
  port: /dev/ttyUSB0
  baud: 115200
  read_timeout_s: 0.1
  ack_timeout_s: 1.0       # Max. Wartezeit auf RSP;ACK
  move_timeout_s: 60.0     # Timeout für Fahr- und Türbefehle
  home_timeout_s: 30.0     # Timeout für HOME
  mech_timeout_s: 10.0     # Timeout für PICKUP/DEPOSIT
  heartbeat_timeout_s: 5.0 # Verbindungsabbruch ohne Heartbeat
  reconnect_intervall_s: 2.0
  skip_homing: false       # true = Referenzfahrt überspringen (Entwicklung)
```

### 5.3 Abschnitt `gpio`

```yaml
gpio:
  endschalter:
    x: 17    # BCM-Pin Endschalter X
    z: 4     # BCM-Pin Endschalter Z
  not_aus:
    pin: 26
    invert: false  # true = active-high
```

### 5.4 Abschnitt `drucker`

Pro Drucker ein Eintrag:

```yaml
drucker:
  - id: 1
    name: Drucker 1
    pin_fertig: 27       # BCM-Pin (muss eindeutig sein)
    pos_x: 370           # X-Position vor dem Drucker (mm)
    pos_z_anfahr: 120    # Sichere Höhe (mm)
    pos_z_tuer: 105      # Höhe Türarm-Angriff (mm)
    pos_z_druckbett: 50  # Höhe Druckbett (mm)
    door_arm_hub_mm: 30  # Ausfahrlänge Türarm (= arm_extend, mm)
    tuer_radius: 150     # Kreisradius Türbewegung (mm)
    tuer_winkel: 160     # Öffnungswinkel Tür (°)
    gripper_depth: 120   # Greifer-Ausfahrtiefe (mm)
    lift_offset: 8       # Anhebung bei PICKUP/DEPOSIT (mm)
```

### 5.5 Abschnitt `ablagen`

```yaml
ablagen:
  - id: 1
    name: Ablage 1
    x: 20              # X-Position (mm)
    z: 20              # Z-Position (mm)
    gripper_depth: 120
    lift_offset: 8
    belegt: false      # Wird zur Laufzeit aktualisiert
```

### 5.6 Abschnitt `magazine`

```yaml
magazine:
  - id: 1
    name: Magazin 1
    x: 50
    z: 50
    gripper_depth: 120
    lift_offset: 8
    verfuegbar: true   # Wird zur Laufzeit aktualisiert
```

### 5.7 Abschnitt `mqtt`

```yaml
mqtt:
  enabled: true
  broker_host: localhost
  broker_port: 1883
  username: ''
  password: ''
  client_id: plattenwechsler-pi
  base_topic: plattenwechsler-g6twie23a
  qos: 1
  retain_status: true
  reconnect_intervall_s: 5.0
```

### 5.8 Abschnitt `telegram`

```yaml
telegram:
  enabled: true
  bot_token: <token>
  allowed_chat_ids:
    - <chat_id>
  send_status_to_first: true  # Status-Updates an ersten Chat senden
```

### 5.9 Abschnitt `hmi`

```yaml
hmi:
  fullscreen: true
  width: 1280
  height: 720
```

---

## Anhang: Timing-Parameter

| Parameter | Wert |
|---|---|
| UART Baudrate | 115200 Baud |
| Heartbeat-Intervall (ESP → Pi) | 1000 ms |
| Heartbeat-Timeout (Pi) | 5000 ms |
| STATUS-Stream-Intervall | 100 ms |
| Hindernissensor-Abfrageintervall | 50 ms |
| ACK-Timeout (Pi wartet auf RSP) | 1000 ms |
| Fahr-/Türbefehl-Timeout | 60.000 ms |
| HOME-Timeout | 30.000 ms |
| PICKUP/DEPOSIT-Timeout | 10.000 ms |
