// CL42T-V41 Closed-Loop Treiber – Testprogramm
//
// Verkabelung (Einzelendsignal, optoentkoppelt):
//   GPIO 16  -> PUL+   (STEP)     PUL- an GND
//   GPIO 17  -> DIR+   (DIR)      DIR- an GND
//   GPIO 18  -> ENA+   (EN)       ENA- an GND   (active-low: LOW = aktiv)
//   GPIO 19  <- ALM                              (active-low: LOW = Fehler)
//   3,3V kompatibel laut Datenblatt
//
// Schritte/Umdrehung per DIP-Schalter am Treiber einstellen (z.B. 200 = Vollschritt)
//
// CL42T Timing-Minima laut Datenblatt:
//   PUL-Pulsbreite: ≥ 2,5 µs
//   DIR setup vor PUL-Flanke: ≥ 5 µs
//
// Befehle:
//   f <n>   Vorwärts N Schritte
//   b <n>   Rückwärts N Schritte
//   r <n>   N Umdrehungen vorwärts
//   s <us>  Schrittverzögerung µs (min. 3)
//   e       Treiber ein/aus
//   dir 0|1 DIR-Pin manuell setzen
//   ?       Status

#include <Arduino.h>

// Pins
constexpr uint8_t PIN_STEP = 16;
constexpr uint8_t PIN_DIR  = 17;
constexpr uint8_t PIN_EN   = 18;
constexpr uint8_t PIN_ALM  = 19;

// CL42T Timing-Minima laut Datenblatt
constexpr uint32_t T_STEP_MIN_US  = 3;   // PUL-Pulsbreite ≥ 2,5 µs → 3 µs
constexpr uint32_t T_DIR_SETUP_US = 5;   // DIR setup vor PUL-Flanke ≥ 5 µs

// Schritte/Umdrehung – muss mit DIP-Schalter am Treiber übereinstimmen
constexpr uint16_t STEPS_PER_REV = 800;

// Zustand
uint32_t stepDelayUs = 2000;
bool     driverOn    = false;

void enableDriver(bool on) {
    driverOn = on;
    digitalWrite(PIN_EN, on ? LOW : HIGH);
    Serial.printf("Treiber: %s\n", on ? "EIN" : "AUS");
}

bool checkAlarm() {
    if (digitalRead(PIN_ALM) == LOW) {
        Serial.println("!! ALARM: CL42T meldet Fehler (ALM low) !!");
        return true;
    }
    return false;
}

void step(bool forward, uint32_t n) {
    if (checkAlarm()) return;
    if (!driverOn) enableDriver(true);

    digitalWrite(PIN_DIR, forward ? HIGH : LOW);
    delayMicroseconds(T_DIR_SETUP_US);

    for (uint32_t i = 0; i < n; i++) {
        if (i % 100 == 0 && checkAlarm()) return;  // Alarm alle 100 Schritte prüfen

        digitalWrite(PIN_STEP, HIGH);
        delayMicroseconds(stepDelayUs);
        digitalWrite(PIN_STEP, LOW);
        delayMicroseconds(stepDelayUs);
    }
    Serial.printf("%s %lu Schritte fertig.\n", forward ? ">>" : "<<", n);
}

void printStatus() {
    Serial.println("-------------------------");
    Serial.println("  f <n>   Vorwärts");
    Serial.println("  b <n>   Rückwärts");
    Serial.println("  r <n>   Umdrehungen");
    Serial.println("  s <us>  Schrittverzögerung");
    Serial.println("  e       Treiber ein/aus");
    Serial.println("  dir 0|1 DIR-Pin setzen");
    Serial.println("  ?       Status");
    Serial.println("-------------------------");
    Serial.printf("  Delay: %lu µs | Treiber: %s | ALM: %s\n",
                  stepDelayUs, driverOn ? "EIN" : "AUS",
                  digitalRead(PIN_ALM) == LOW ? "FEHLER" : "OK");
    Serial.println("-------------------------");
}

void handleCommand(const String& raw) {
    String cmd = raw;
    cmd.trim();
    if (cmd.length() == 0) return;

    if (cmd.startsWith("dir ")) {
        bool high = cmd.substring(4).toInt() != 0;
        digitalWrite(PIN_DIR, high ? HIGH : LOW);
        Serial.printf("DIR: %s\n", high ? "HIGH" : "LOW");
        return;
    }

    char op  = cmd.charAt(0);
    long arg = cmd.length() > 1 ? cmd.substring(2).toInt() : 0;

    switch (op) {
        case 'f':
            if (arg <= 0) { Serial.println("ERR: f <n>"); return; }
            step(true, (uint32_t)arg);
            break;
        case 'b':
            if (arg <= 0) { Serial.println("ERR: b <n>"); return; }
            step(false, (uint32_t)arg);
            break;
        case 'r':
            if (arg <= 0) { Serial.println("ERR: r <n>"); return; }
            step(true, (uint32_t)arg * STEPS_PER_REV);
            break;
        case 's':
            if (arg < (long)T_STEP_MIN_US) {
                Serial.printf("ERR: Minimum %lu µs\n", T_STEP_MIN_US);
                return;
            }
            stepDelayUs = (uint32_t)arg;
            Serial.printf("Delay: %lu µs\n", stepDelayUs);
            break;
        case 'e':
            enableDriver(!driverOn);
            break;
        case '?':
            printStatus();
            break;
        default:
            Serial.printf("Unbekannt: '%c' – ? für Hilfe\n", op);
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    pinMode(PIN_STEP, OUTPUT);
    pinMode(PIN_DIR,  OUTPUT);
    pinMode(PIN_EN,   OUTPUT);
    pinMode(PIN_ALM,  INPUT_PULLUP);

    digitalWrite(PIN_STEP, LOW);
    digitalWrite(PIN_DIR,  LOW);
    digitalWrite(PIN_EN,   HIGH);

    Serial.println("\nCL42T-V41 Test");
    printStatus();
}

void loop() {
    if (Serial.available()) {
        handleCommand(Serial.readStringUntil('\n'));
    }
}
