# Erste Test-Inbetriebnahme am Laptop

## Zweck

Der aktuelle ESP-Stand ist nur ein einfacher Test fuer:

- USB-Serial zum Laptop
- 1x VL53L1X ueber I2C
- 1x Taster an GPIO mit `INPUT_PULLUP`

Keine Motoren, keine Ablaufsteuerung.

## Verdrahtung

### Laptop <-> ESP32

- Verbindung per USB
- Baudrate: `115200`
- typische Ports unter macOS:
  - `/dev/cu.usbserial-*`
  - `/dev/cu.usbmodem*`

### Pinbelegung

→ siehe [Pinbelegung_ESP32.md](Pinbelegung_ESP32.md) (Abschnitt "Testaufbau")

## Was das Terminal senden kann

Alle Befehle als Textzeile mit Newline:

- `PING`
- `STATUS`
- `STREAM ON`
- `STREAM OFF`
- `REINIT`
- `I2C_SCAN`
- `HELP`

## Was der ESP sendet

### Beim Start

```text
SENSOR_INIT;name=tof_1;ok=1;addr=0x30
READY;fw=esp32_component_test
INFO;commands=PING,STATUS,STREAM ON,STREAM OFF,REINIT,I2C_SCAN,HELP
STATUS;reason=boot;...
```

### Auf `PING`

```text
PONG;uptime_ms=12345
```

### Auf `I2C_SCAN`

```text
I2C_SCAN;found=0x30
```

### Zyklischer Status

```text
STATUS;reason=stream;uptime_ms=...;tof_1_ok=1;tof_1_mm=...;tof_1_timeout=0;btn_1=0
```

Bedeutung:

- `tof_x_ok=1` Sensor initialisiert
- `tof_x_mm` Distanz in mm
- `tof_x_timeout=1` Timeout beim Lesen
- `btn_1=1` Taster gedrueckt

### Taster-Events

```text
EVENT;type=button;name=btn_1;pressed=1
EVENT;type=button;name=btn_1;pressed=0
```

### Sensor-Timeout-Events

```text
EVENT;type=tof_timeout;name=tof_1;active=1
EVENT;type=tof_timeout;name=tof_1;active=0
```

## Kurzer Testablauf

### 1. Port am Laptop finden

```bash
ls /dev/cu.usbserial-* /dev/cu.usbmodem*
```

### 2. Verbinden

Zum Beispiel:

```bash
screen /dev/cu.usbmodemXXXX 115200
```

Alternativ mit PlatformIO:

```bash
/Users/christiantroschel/.platformio/penv/bin/pio device monitor -b 115200
```

### 3. Kommunikation pruefen

Im Terminal senden:

```text
PING
```

Erwartet:

```text
PONG;uptime_ms=...
```

### 4. I2C pruefen

Im Terminal senden:

```text
I2C_SCAN
```

Erwartet:

```text
I2C_SCAN;found=0x30
```

### 5. Sensoren pruefen

Im Terminal senden:

```text
STREAM ON
```

Dann pruefen:

- aendert sich `tof_1_mm`?
- bleibt `tof_1_timeout=0`?

### 6. Taster pruefen

Dann pruefen:

- offen = `btn_x=0`
- gedrueckt = `btn_x=1`
- zusaetzlich kommen Event-Zeilen beim Umschalten

## Wichtig

- gebaut wird aktuell nur `src/main.cpp`
- `platformio.ini` nutzt dafuer `build_src_filter = +<main.cpp>`
- die Pinbelegung oben ist der aktuelle Teststand

## Erfolgskriterium

Der erste Test ist erfolgreich, wenn:

- `PING` beantwortet wird
- `I2C_SCAN` den Sensor findet
- der VL53L1X Werte liefert
- alle Taster sauber schalten
