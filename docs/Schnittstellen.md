# Schnittstelle ESP32 ↔ Raspberry Pi

**Stand: Mai 2026** — entspricht der finalen Spezifikation des ESP-Teams.

## Verbindung
- USB-UART, 115200 8N1
- ASCII-Protokoll, eine Nachricht pro Zeile (`\n`)
- Feldtrenner `;`, Parameter als `key=value`

## Pi → ESP

| Befehl | Parameter | Bedeutung |
|---|---|---|
| `PING` | – | Verbindungstest |
| `STATUS` | – | Vollstatus anfordern |
| `STREAM_ON` / `STREAM_OFF` | – | periodisches STATUS-Streaming |
| `HOME` | – | Referenzfahrt X+Z (X zuerst, dann Z) |
| `MOVE_HOME` | – | Heimfahrt zu (0,0) per Endschalter |
| `MOVE_TO` | `x=mm; z=mm` | Zielposition (Z-Scan beim Start aus Home) |
| `STOP` | – | Sofortiger Stopp |
| `RESET_ERROR` | – | Fehlerzustand verlassen, Referenzierung verworfen |
| `HOME_SWITCH_HIT` | `axis=X\|Z` | Pi meldet GPIO-Endschalter-Trigger |
| `SET_CLAMP` | `position=OPEN\|CLOSED\|SERVICE` | Halteservo (Klemme) |
| `SET_DOOR_ARM` | `position=OPEN\|CLOSED` | Türarm-Hebel |

Format: `CMD;<id>;<befehl>[;key=value;...]`

## ESP → Pi

```
RSP;<id>;ACK                     # Befehl angenommen
RSP;<id>;ERR;<errcode>           # Befehl abgelehnt
EVT;<id>;OK;<event>              # Aktion abgeschlossen
EVT;0;STATE;<state>;ref=...;x=...;z=...
EVT;0;STATUS;state=...;error=...;ref=...;x=...;z=...;
            target_x=...;target_z=...;busy=...;
            gripper_home=...;door_arm_home=...;
            obstacle_ok=...;door_open=...;door_dist_mm=...
EVT;0;ERR;<errcode>              # asynchroner Fehler
EVT;0;HEARTBEAT;uptime_ms=...    # alle 1s
```

### Events nach Befehlen

| Befehl | erwartetes Event |
|---|---|
| `HOME` | `HOME_DONE` |
| `MOVE_HOME` | `MOVE_HOME_DONE` |
| `MOVE_TO` | `MOVE_DONE` |
| `RESET_ERROR` | `ERROR_RESET` |
| `STOP` | `STOPPED` |
| `SET_CLAMP OPEN/CLOSED/SERVICE` | `CLAMP_OPEN`/`CLAMP_CLOSED`/`CLAMP_SERVICE` |
| `SET_DOOR_ARM OPEN/CLOSED` | `DOOR_ARM_OPEN`/`DOOR_ARM_CLOSED` |
| `PING` | `PONG` |

### ESP-States

| State | Bedeutung |
|---|---|
| `NOT_REFERENCED` | nach Power-On oder RESET_ERROR |
| `READY` | bereit für Befehle |
| `BUSY_HOMING` | Referenzfahrt läuft |
| `BUSY_SCANNING` | TF-Luna scannt Z-Achse vor Fahrt aus Home |
| `BUSY_MOVING` | normale Fahrt läuft |
| `BUSY_MOVE_HOME` | Heimfahrt läuft |
| `STOPPED` | manuell gestoppt — RESET_ERROR nötig |
| `ERROR` | Fehler — RESET_ERROR nötig |

### Fehlercodes

| Code | Klasse |
|---|---|
| `INVALID_COMMAND` | Kommunikationsfehler |
| `BUSY` | Kommunikationsfehler (ESP gerade beschäftigt) |
| `INVALID_STATE` | Kommunikationsfehler (Befehl im aktuellen Zustand nicht erlaubt) |
| `NOT_REFERENCED` | Fahrfehler (MOVE_TO ohne Ref) |
| `MOVE_TIMEOUT` | Fahrfehler |
| `HOMING_TIMEOUT` | Fahrfehler |
| `OBSTACLE` | Hindernis (TF-Luna) |
| `POSITION_ERROR` | Fahrfehler |
| `SENSOR_FAULT_OBSTACLE` | Sensorfehler (TF-Luna defekt/keine Daten) |
| `SENSOR_FAULT_GRIPPER` | Sensorfehler (Halteservo-Endschalter) |
| `DRIVER_FAULT` | Fahrfehler (Motortreiber) |

### Status-Felder

| Feld | Typ | Beschreibung |
|---|---|---|
| `state` | enum | aktueller ESP-State |
| `error` | string | letzter Fehler oder `NONE` |
| `ref` | 0/1 | referenziert |
| `x`, `z` | int (mm) | aktuelle Position |
| `target_x`, `target_z` | int (mm) | aktuelles Ziel |
| `busy` | 0/1 | aktuell beschäftigt |
| `gripper_home` | 0/1 | Halteservo in Heimposition |
| `door_arm_home` | 0/1 | Türarm in Heimposition |
| `obstacle_ok` | 0/1 | TF-Luna gesund + frei |
| `door_open` | 0/1 | Drucker-Tür offen (VL53L0X-Auswertung) |
| `door_dist_mm` | int | VL53L0X-Rohwert |

## Plattenwechsel-Sequenz (Pi-Logik)

Der Pi orchestriert den Plattenwechsel über die o.g. Befehle:

```
Phase 1: alte Platte holen
  MOVE_TO  (drucker.x, drucker.z_anfahr)
  MOVE_TO  (drucker.x, drucker.z_tuer)
  SET_DOOR_ARM OPEN
  STATUS   → door_open == 1?    (sonst TUERFEHLER)
  MOVE_TO  (drucker.x, drucker.z_druckbett)
  SET_CLAMP CLOSED                (Platte greifen)
  MOVE_TO  (drucker.x, drucker.z_tuer)
  SET_DOOR_ARM CLOSED

Phase 2: ablegen
  MOVE_TO  (ablage.x, ablage.z)
  SET_CLAMP OPEN

Phase 3: neue Platte
  MOVE_TO  (magazin.x, magazin.z)
  SET_CLAMP CLOSED

Phase 4: einsetzen (analog Phase 1, aber SET_CLAMP OPEN am Bett)

Phase 5: Heimfahrt
  MOVE_HOME
```

## Zeitintervalle

| Was | Periode |
|---|---|
| HEARTBEAT | 1 s |
| STATUS-Stream (wenn an) | 100 ms |
| Hindernissensor-Auswertung | 50 ms |
| Heartbeat-Timeout im Pi | 5 s |
