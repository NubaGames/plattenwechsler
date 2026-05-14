# Pinbelegung ESP32

Dies ist die zentrale Referenz für alle GPIO-Zuweisungen des ESP32-Schlittens.  
Andere Dokumente verweisen auf diese Datei.

## Statuslegende

| Symbol | Bedeutung |
|---|---|
| ✅ | Festgelegt |
| ⚠️ | Noch offen |

---

## ✅ Festgelegte Pins

| Funktion | Pin | Hinweis |
|---|---|---|
| UART zum Pi / Laptop | USB / UART0 | 115200 Baud |
| I2C SDA | GPIO 21 | 100 kHz; Bus für Türsensor + Hindernissensor |
| I2C SCL | GPIO 22 | 100 kHz; Bus für Türsensor + Hindernissensor |
| Türsensor XSHUT | GPIO 16 | VL53L0X, I²C-Adresse nach Init: 0x30 |
| Hindernissensor (TF-Luna) | GPIO 21 / 22 (I2C) | I²C-Adresse: 0x10 (noch zu bestätigen) |

---

## ⚠️ Noch offene Pins

### Achssteuerung (CL42T-V41 Closed-Loop-Treiber)

Pro Achse werden 4 Signale benötigt (3 Ausgänge ESP → Treiber, 1 Eingang Treiber → ESP):

| Funktion | Pin | Richtung | Hinweis |
|---|---|---|---|
| Stepper X – STEP (PUL+) | noch offen | ESP → CL42T | Schritt-Impuls, ≥2,5 µs Pulsbreite, max. 200 kHz |
| Stepper X – DIR (DIR+) | noch offen | ESP → CL42T | Richtung, vor STEP mindestens 5 µs stabil |
| Stepper X – ENA (ENA+) | noch offen | ESP → CL42T | Enable, active-low (LOW = Treiber aktiv) |
| Stepper X – ALM | noch offen | CL42T → ESP | Alarm-Ausgang des Treibers (active-low); löst DRIVER_FAULT aus |
| Stepper Z – STEP (PUL+) | noch offen | ESP → CL42T | wie X |
| Stepper Z – DIR (DIR+) | noch offen | ESP → CL42T | wie X |
| Stepper Z – ENA (ENA+) | noch offen | ESP → CL42T | wie X |
| Stepper Z – ALM | noch offen | CL42T → ESP | wie X |

> **Hinweis Spannungspegel:** Der ESP32 liefert 3,3 V; die CL42T-Eingänge sind optoentkoppelt und akzeptieren Einzelendsignale (PUL+/DIR+/ENA+ auf Signal, PUL−/DIR−/ENA− auf GND). 3,3 V sind kompatibel.

### Sonstige Aktoren und Sensoren

| Funktion | Pin | Hinweis |
|---|---|---|
| Home-Taster X | noch offen | active-low |
| Home-Taster Z | noch offen | active-low |
| Servo PWM (Clamp) | noch offen | LEDC, 50 Hz – ob überhaupt Servo, noch offen |
| Greifer-Taster | noch offen | active-low |
| Türarm-Aktor | noch offen | Stepper oder Servo, noch nicht entschieden |

