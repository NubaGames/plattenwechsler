// DRV8825 Testprogramm
//
// Verkabelung:
//   GPIO 25  -> STEP
//   GPIO 32  -> DIR
//   GPIO 27  -> EN    (active-low)
//   3.3V     -> VDD, RST, SLP
//   GND      -> GND
//   ext. 12V -> VMOT
//   M0/M1/M2 offen = Vollschritt
//
// Befehle:
//   f <n>   Vorwärts N Schritte
//   b <n>   Rückwärts N Schritte
//   r <n>   N Umdrehungen vorwärts
//   s <us>  Schrittverzögerung µs (min. 2)
//   e       Treiber ein/aus
//   dir 0|1 DIR-Pin manuell setzen
//   ?       Status

#include <Arduino.h>

// Pins
constexpr uint8_t PIN_STEP = 25;
constexpr uint8_t PIN_DIR  = 32;
constexpr uint8_t PIN_EN   = 27;

// DRV8825 Timing-Minima laut Datenblatt
constexpr uint32_t T_STEP_MIN_US  = 2;   // min. Pulsbreite HIGH oder LOW: 1,9 µs
constexpr uint32_t T_DIR_SETUP_US = 1;   // DIR setup vor STEP-Flanke: 650 ns

// Vollschritt: 1,8°-Motor = 200 Schritte/Umdrehung
constexpr uint16_t STEPS_PER_REV = 200;

// Zustand
uint32_t stepDelayUs = 2000;
bool     driverOn    = false;

void enableDriver(bool on) {
    driverOn = on;
    digitalWrite(PIN_EN, on ? LOW : HIGH);
    Serial.printf("Treiber: %s\n", on ? "EIN" : "AUS");
}

void step(bool forward, uint32_t n) {
    if (!driverOn) enableDriver(true);

    digitalWrite(PIN_DIR, forward ? HIGH : LOW);
    delayMicroseconds(T_DIR_SETUP_US);

    for (uint32_t i = 0; i < n; i++) {
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
    Serial.printf("  Delay: %lu µs | Treiber: %s\n", stepDelayUs, driverOn ? "EIN" : "AUS");
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
    digitalWrite(PIN_STEP, LOW);
    digitalWrite(PIN_DIR,  LOW);
    digitalWrite(PIN_EN,   HIGH);

    Serial.println("\nDRV8825 Test");
    printStatus();
}

void loop() {
    if (Serial.available()) {
        handleCommand(Serial.readStringUntil('\n'));
    }
}
