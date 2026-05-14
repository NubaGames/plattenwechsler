# Konzept fuer den ESP32 auf dem Schlitten

## Ausgangslage aus der Doku

Das Blockschaltbild definiert eine klare Aufteilung:

- Der ESP32 auf dem Schlitten ist `"THE MUSCLE"` und steuert die lokale Echtzeit-Hardware.
- Der Raspberry Pi auf der Basis ist `"THE BRAIN"` und uebernimmt HMI, Auftragslogik, MQTT, Telegram und die Drucker-/Tuerschnittstellen.
- Zwischen Pi und ESP gibt es nur eine schmale Verbindung ueber `UART via USB`.
- Auf dem Schlitten haengen direkt am ESP:
  - Stepper-Controller fuer die Achsen des Schlittens bzw. Greifers
  - Servo fuer den Plattenhalter
  - 2x Time-of-Flight-Sensor ueber `I2C`
  - Taster fuer Plattenerkennung
- Die Ablaufplaene fuer den ESP nennen genau vier Kommandos:
  - `STATUS`
  - `STOP`
  - `HOME`
  - `MOVE_TO`

Daraus folgt: Der ESP32 darf keine hohe Auftragslogik enthalten, sondern muss eine robuste, zustandsorientierte Bewegungssteuerung mit sauberer Rueckmeldung an den Raspberry Pi bereitstellen.

## Zielbild

Der ESP32 wird als echtzeitnaher Motion-Controller fuer den Schlitten ausgelegt.

Seine Aufgaben:

- Hardware initialisieren und in einen sicheren Grundzustand bringen
- Sensoren zyklisch erfassen und plausibilisieren
- Achsen und Servo lokal und deterministisch ansteuern
- Referenzfahrt lokal ausfuehren
- Zielpositionen lokal anfahren
- Hindernisse, Timeouts und Sensorfehler sofort behandeln
- Status, Ist-Position und Fehler ueber ein einfaches Protokoll an den Raspberry Pi melden

Nicht seine Aufgaben:

- Auftragsannahme aus MQTT, Telegram oder Touch-HMI
- Drucker- oder Tuerlogik
- Warteschlangenverwaltung
- Fehlerquittierung auf Systemebene

## Architekturempfehlung

### 1. Software-Struktur

Empfohlene Module:

- `AppController`
  - Startet das System
  - verbindet alle Module
  - enthaelt den Hauptzustand des ESP
- `CommandInterface`
  - UART-Protokoll zum Raspberry Pi
  - validiert Kommandos
  - legt Befehle in eine Queue
- `MotionController`
  - kapselt alle Bewegungsablaufe
  - kennt Zielposition, Richtung, Timeout und Rueckmeldebedingungen
- `AxisController`
  - Low-Level fuer Step/Dir/Enable
  - optional je Achse eine Instanz
- `ServoController`
  - Positionen fuer Plattenhalter, Greifen, Ablegen
- `SensorManager`
  - ToF-Sensoren ueber I2C
  - Greifer-/Plattentaster
  - digitale Diagnose und Entprellung
- `HomingManager`
  - Referenzfahrt mit Endbedingungen
  - setzt internen Positionszaehler
- `SafetyManager`
  - Hinderniserkennung
  - Watchdog
  - Fahrfreigabe
  - Sofort-Stopp
- `StatusReporter`
  - sendet Status-Telegramme, Fehler und Heartbeats
- `PersistentData`
  - optionale Ablage fuer Konfiguration
  - keine Prozesspositionen persistent halten, solange keine sichere Referenzierung vorliegt

### 2. Laufzeitmodell

Fuer den ESP32 passt ein ereignisgetriebenes Modell mit wenigen klaren Tasks besser als eine blockierende `loop()`.

Empfohlene Tasks:

- `task_comm`
  - liest UART
  - dekodiert Nachrichten
  - schreibt Befehle in eine Queue
- `task_control`
  - fuehrt die Hauptzustandsmaschine aus
  - ruft Homing- und Move-Sequenzen zyklisch auf
- `task_sensors`
  - liest ToF und Taster
  - aktualisiert ein gemeinsames, thread-sicheres Sensorabbild
- `task_status`
  - sendet Heartbeat und Zustandsaenderungen

Wenn das Projekt klein bleiben soll, kann dieselbe Logik auch in einer einzigen nicht-blockierenden `loop()` umgesetzt werden. Wichtig ist nur:

- keine langen `delay()`-Bloecke
- jede Bewegung zyklisch pruefen
- jeder Fehlerpfad muss unmittelbar abbrechen koennen

## Zustaende des ESP32

Aus dem Ablaufplan ergibt sich folgende lokale Zustandsmaschine:

- `BOOT`
  - Motorsteuerung und Motormodul initialisieren
  - ToF-Sensoren ueber I2C initialisieren
  - Status auf `NOT_REFERENCED` setzen
- `IDLE_WAIT_FOR_COMMAND`
  - auf Befehl vom Raspberry Pi warten
- `HOMING`
  - Referenzfahrt ausfuehren
  - bei Erfolg Position auf Home setzen und Status `READY`
- `MOVING`
  - Zielposition uebernehmen
  - Fahrtrichtung bestimmen
  - Fahrt starten
  - Hindernis, Timeout und Zielerreichung ueberwachen
- `STOPPED`
  - Bewegung angehalten, wartet auf naechsten gueltigen Befehl
- `ERROR`
  - alle Ausgaenge in sicheren Zustand
  - Fehlerstatus gesetzt und an Pi gemeldet
  - Rueckkehr nur ueber Quittierung plus erneute Referenzfahrt

Empfohlene Statuscodes:

- `BOOTING`
- `NOT_REFERENCED`
- `READY`
- `BUSY_HOMING`
- `BUSY_MOVING`
- `STOPPED`
- `ERROR`

## Kommando-Schnittstelle zum Raspberry Pi

Das Protokoll sollte einfach, textbasiert und robust debuggbar sein. JSON waere moeglich, fuer eine serielle Punkt-zu-Punkt-Verbindung ist aber ein kompaktes Zeilenprotokoll meist einfacher.

Vorschlag:

- Eine Nachricht pro Zeile
- UTF-8/ASCII
- Felder mit Semikolon getrennt
- Jede Nachricht hat `type`, `id`, `cmd/status`, `payload`, `crc` optional

Beispiele:

```text
CMD;42;STATUS
CMD;43;STOP
CMD;44;HOME
CMD;45;MOVE_TO;axis=Z;pos=125000;speed=800;acc=200
RSP;45;ACK
EVT;0;STATE;BUSY_MOVING
EVT;0;POS;axis=Z;steps=98420
EVT;0;OK;MOVE_DONE;pos=125003
EVT;0;ERR;OBSTACLE;axis=Z;distance=37
```

Minimale Befehle gemaess Ablaufplan:

- `STATUS`
  - liefert Status, Positionswert und Sensorstatus
- `STOP`
  - stoppt alle Motoren sofort
  - meldet `STOPPED`
- `HOME`
  - startet Referenzfahrt, nur wenn kein anderer Fahrauftrag aktiv ist
- `MOVE_TO`
  - startet eine Fahrt zu einer Zielposition
  - nur erlaubt, wenn `READY` oder `STOPPED`

Zusaetzlich sinnvoll:

- `RESET_ERROR`
  - loescht nur den quittierten Fehlerstatus
  - versetzt den ESP aber noch nicht in `READY`
- `PING`
  - Kommunikations-Watchdog fuer den Pi
- `SET_SERVO`
  - falls der Servo wirklich direkt anfahrbar sein soll

## Bewegungslogik

### Referenzfahrt `HOME`

Die Doku beschreibt:

- Referenzfahrt starten
- Home erkannt?
- Hindernis erkannt?
- Timeout?
- bei Erfolg Positionszaehler auf Home setzen
- Erfolg an Raspberry Pi senden

Daraus ergibt sich dieser technische Ablauf:

1. Bewegungsparameter fuer Homing laden
2. Achse in sichere Homing-Richtung fahren
3. In jedem Zyklus pruefen:
   - Home-Bedingung erreicht?
   - Hindernis durch ToF erkannt?
   - Timeout ueberschritten?
   - Stepper-/Treiberfehler erkannt?
4. Bei Home:
   - Motor stoppen
   - Positionszaehler auf `0` oder konfigurierten Offset setzen
   - Status `READY`
   - `HOME_DONE` senden
5. Bei Fehler:
   - Motor stoppen
   - Fehlerstatus setzen
   - `ERROR` senden

### Zielposition anfahren `MOVE_TO`

Die Doku beschreibt:

- Zielposition uebernehmen
- Fahrtrichtung bestimmen
- Fahrt starten
- Hindernis in Fahrtrichtung?
- Zielposition laut Motormodul erreicht?
- Ist-Position lesen
- Position innerhalb Toleranz?

Empfohlene technische Regeln:

- `MOVE_TO` nur nach erfolgreicher Referenzfahrt
- Positionen intern in Schritten fuehren, Umrechnung nach Millimeter nur in der Pi- oder HMI-Ebene
- pro Bewegung eine Sollposition, Startzeit und Toleranz speichern
- Ziel erreicht erst dann melden, wenn:
  - Motormodul `target reached` meldet oder die Schrittkette fertig ist
  - die Rueckleseposition innerhalb der Toleranz liegt
- bei Abweichung ausserhalb Toleranz:
  - Fehler `POSITION_ERROR`
  - erneute Freigabe erst nach Reset und Homing

## Sensorik und Sicherheitslogik

### ToF-Sensoren

Laut Blockschaltbild haengen 2 ToF-Sensoren am ESP. Im Ablaufplan werden sie funktional als Hinderniserkennung benutzt.

Empfehlung:

- Sensor vorne und hinten bzw. in Fahrtrichtung logisch abbilden
- fuer jede Bewegungsrichtung die passende Sperrzone definieren
- Messwerte mitteln oder medianfiltern
- feste Schwellwerte pro Betriebsphase
  - `warn_distance_mm`
  - `stop_distance_mm`
- Sensorfehler separat erkennen
  - Timeout auf I2C
  - unplausibler Messwert
  - dauerhaft gleicher Wert

### Taster Plattenerkennung

Der Taster wird im Blockschaltbild als `Plattenerkennung` benoetigt. Im Plattenwechsel-Ablauf dient er als Greifer-Rueckmeldung:

- Platte aufgenommen?
- Platte abgelegt?
- Neue Platte aufgenommen?
- Platte eingesetzt?

Empfehlung:

- digital entprellen
- Zustandswechsel mit Zeitstempel erfassen
- als harte Prozessbedingung in die Sequenz einbauen
- bei ausbleibender erwarteter Umschaltung Fehler `GRIPPER_PICK_FAIL` oder `GRIPPER_RELEASE_FAIL`

### Servo Plattenhalter

Der Servo sollte nicht frei aus der HMI angesteuert werden, sondern nur ueber definierte logische Positionen:

- `HOLDER_OPEN`
- `HOLDER_CLOSED`
- `HOLDER_SERVICE`

So bleibt die Mechanik reproduzierbar und das Risiko von Fehlbedienung sinkt.

## Fehlerkonzept

Der Fehlerablauf trennt mehrere Fehlerklassen. Fuer den ESP sollten diese in zwei Ebenen aufgeteilt werden.

### A. Niedrige ESP-Fehler

Diese erkennt und behandelt der ESP direkt:

- `OBSTACLE_DETECTED`
- `MOVE_TIMEOUT`
- `HOMING_TIMEOUT`
- `POSITION_ERROR`
- `SENSOR_FAULT_TOF`
- `SENSOR_FAULT_GRIPPER`
- `DRIVER_FAULT`
- `COMM_TIMEOUT_PI`

Reaktion:

- alle Bewegungen sofort stoppen
- Aktoren in sicheren Zustand
- Fehlercode latched speichern
- `ERROR` an Pi senden

### B. Systemfehler oberhalb des ESP

Diese bewertet der Raspberry Pi:

- Tuerfehler
- Magazin leer
- Kommunikationsfehler nach mehrfachen Retries
- Not-Aus
- Service erforderlich

Wichtig: Der ESP kann rohe Ereignisse liefern, die fachliche Fehlerklasse bildet aber besser der Pi.

## Sequenz fuer den Plattenwechsel

Der detaillierte Plattenwechsel liegt gemaess Doku im Hauptsystem, nutzt aber den ESP fuer jeden lokalen Bewegungs- und Greifschritt.

Sinnvolle Aufteilung:

- Raspberry Pi:
  - waehlt Drucker
  - oeffnet Tuer
  - prueft Druckerstatus
  - ruft Schrittketten des Prozesses in richtiger Reihenfolge auf
- ESP32:
  - faehrt Druckerposition an
  - steuert Entnahmebewegung
  - prueft Greifer-Taster auf Aufnahme
  - faehrt Ablageposition an
  - prueft Ablegen
  - faehrt Magazinposition an
  - prueft Aufnahme neuer Platte
  - faehrt zurueck zur Druckerposition
  - prueft Einsetzen
  - faehrt Home an

Fuer die Firmware bedeutet das: Neben `MOVE_TO` braucht der ESP intern wahrscheinlich vordefinierte Positionen oder eine kleine Sequenz-API. Zwei Varianten sind sinnvoll.

### Variante A: Raspberry Pi orchestriert jeden Einzelschritt

Beispiele:

- `MOVE_TO printer_load`
- `SET_SERVO holder_open`
- `MOVE_TO dropoff_used`
- `MOVE_TO magazine_pick`

Vorteile:

- maximale Transparenz
- einfache Testbarkeit
- Logik bleibt im Pi

Nachteile:

- mehr serielle Nachrichten
- mehr Zustandsverantwortung beim Pi

### Variante B: ESP bietet Makrobefehle fuer Teilsequenzen

Beispiele:

- `RUN_SEQUENCE pickup_used_plate`
- `RUN_SEQUENCE place_used_plate`
- `RUN_SEQUENCE pickup_new_plate`
- `RUN_SEQUENCE insert_new_plate`

Vorteile:

- lokale Reaktionszeit besser
- weniger Kommunikationsaufwand

Nachteile:

- mehr Prozesslogik im ESP
- aenderungsintensiver

Empfehlung fuer dieses Projekt:

- Start mit Variante A
- Sequenzen nur dann in den ESP ziehen, wenn die serielle Orchestrierung praktisch zu traege oder zu fehleranfaellig ist

## Datenmodell und Konfiguration

Empfohlene Konfigurationsdaten:

- Pinbelegung fuer Step, Dir, Enable, Servo, Taster, I2C
- Achsparameter:
  - `steps_per_mm`
  - `max_speed`
  - `acceleration`
  - `homing_speed`
  - `homing_timeout_ms`
- Positionsdaten:
  - `home`
  - `printer_position`
  - `dropoff_used`
  - `magazine_pick`
- ToF-Grenzen
- Toleranzen fuer Zielerreichung
- Servopositionen

Sinnvoll ist eine zentrale `config.h` oder spaeter eine kleine JSON-/NVS-Konfiguration.

## Konkreter Firmware-Zuschnitt fuer dieses Repository

Da `src/main.cpp` aktuell noch das PlatformIO-Stub ist, bietet sich folgender Startschnitt an:

```text
src/
  main.cpp
  app/AppController.h
  app/AppController.cpp
  comm/CommandInterface.h
  comm/CommandInterface.cpp
  motion/MotionController.h
  motion/MotionController.cpp
  motion/AxisController.h
  motion/AxisController.cpp
  io/SensorManager.h
  io/SensorManager.cpp
  io/ServoController.h
  io/ServoController.cpp
  safety/SafetyManager.h
  safety/SafetyManager.cpp
  status/StatusReporter.h
  status/StatusReporter.cpp
  config/Pins.h
  config/Config.h
```

Minimaler Implementierungsplan:

1. Serielle Schnittstelle und Status-Telegramme aufbauen
2. Zustandsmaschine `BOOT -> NOT_REFERENCED -> READY/ERROR` implementieren
3. `STATUS`, `STOP`, `HOME`, `MOVE_TO` implementieren
4. ToF-Sensoren und Plattentaster anbinden
5. Timeout- und Fehlerlogik absichern
6. Servo-Positionen und benoetigte Prozesspositionen einfuehren
7. Integration mit Raspberry Pi testen

## Offene Punkte vor der Umsetzung

Die Doku ist fuer ein Konzept ausreichend, fuer die Firmware fehlen aber noch konkrete Festlegungen:

- Wie viele Achsen haengen tatsaechlich am ESP und welche davon muessen in dieser Firmware zuerst laufen?
- Welcher Stepper-Treiber bzw. welches Motormodul wird verwendet?
- Gibt es echte Home-Sensoren am Schlitten oder wird Home ueber Motor-/Strom-/ToF-Kriterien erkannt?
- Welche Zielpositionen sind fest, welche muessen parametrierbar sein?
- Soll der Servo im ersten Schritt schon integriert werden oder spaeter?
- Welches Format erwartet der Raspberry Pi wirklich auf der USB-UART?

## Empfehlung

Fuer den ersten lauffaehigen Stand sollte der ESP32 bewusst klein bleiben:

- nur lokale Motion-, Sensor- und Safety-Logik
- nur vier Kernbefehle plus `RESET_ERROR` und `PING`
- keine Auftragswarteschlange auf dem ESP
- keine blockierenden Ablaufe
- jeder Fehler fuehrt in einen klaren `ERROR`-Zustand mit anschliessender neuer Referenzfahrt

Damit passt die Firmware sauber zu deiner Doku: Der Raspberry Pi bleibt der Prozessfuehrer, der ESP32 ist der robuste und deterministische Ausfuehrer auf dem Schlitten.
