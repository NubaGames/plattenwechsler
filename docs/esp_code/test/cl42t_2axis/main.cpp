// CL42T-V41 – Zwei-Achsen-Positioniertest mit Trapezrampe
//
// Pinbelegung:
//   Achse X: STEP=17  DIR=14  EN=12  ALM=13
//   Achse Y: STEP=32  DIR=33  EN=25  ALM=26
//   (PUL-/DIR-/ENA- jeweils an GND, Einzelendsignal optoentkoppelt)
//
// Befehle (Seriell 115200):
//   goto <x_mm> <y_mm>   Beide Achsen gleichzeitig verfahren
//   home                  Aktuelle Position als Nullpunkt setzen
//   ?                     Status anzeigen

#include <Arduino.h>

// ── Schritte pro Umdrehung (muss mit DIP-Schalter am CL42T übereinstimmen) ──
constexpr uint16_t STEPS_PER_REV = 800;

// ── Schritte pro Millimeter ─────────────────────────────────────────
// Formel: STEPS_PER_REV / (Steigung_mm_pro_Umdrehung)
// Beispiel: 800 steps/rev, 5 mm/rev Kugelgewindetrieb → 160 steps/mm
constexpr float STEPS_PER_MM_X = 160.0f;
constexpr float STEPS_PER_MM_Y = 160.0f;

// ── Geschwindigkeit & Rampe – Achse X ──────────────────────────────
constexpr uint16_t X_MAX_SPEED_RPM   = 300;  // Höchstdrehzahl [U/min]
constexpr uint16_t X_START_SPEED_RPM = 20;   // Anfahrdrehzahl [U/min]
constexpr uint32_t X_ACCEL_STEPS     = 4000;  // Rampenlänge [Schritte]

// ── Geschwindigkeit & Rampe – Achse Y ──────────────────────────────
constexpr uint16_t Y_MAX_SPEED_RPM   = 300;  // Höchstdrehzahl [U/min]
constexpr uint16_t Y_START_SPEED_RPM = 20;   // Anfahrdrehzahl [U/min]
constexpr uint32_t Y_ACCEL_STEPS     = 4000;  // Rampenlänge [Schritte]

// ── CL42T Timing-Minima laut Datenblatt ────────────────────────────
constexpr uint32_t T_STEP_US = 3;  // PUL-Pulsbreite ≥ 2,5 µs
constexpr uint32_t T_DIR_US  = 5;  // DIR-Setup vor erstem Schritt

// ── Pins ────────────────────────────────────────────────────────────
constexpr uint8_t X_STEP = 27, X_DIR = 14, X_EN = 12, X_ALM = 13;
constexpr uint8_t Y_STEP = 32, Y_DIR = 33, Y_EN = 25, Y_ALM = 26;

// ── Hilfsfunktion: RPM → Halbperiode [µs] ──────────────────────────
constexpr uint32_t rpmToHalfUs(uint16_t rpm) {
    return 30000000UL / ((uint32_t)rpm * STEPS_PER_REV);
}

// ── Motorstatus ─────────────────────────────────────────────────────
struct Motor {
    uint8_t  pinStep, pinDir, pinEn, pinAlm;
    uint32_t totalSteps;
    uint32_t stepsDone;
    bool     forward;
    bool     enabled;
    float    positionMm;
    // Trapezprofil – pro Achse individuell
    uint32_t halfUsCruise;  // Halbperiode bei Höchstdrehzahl
    uint32_t halfUsStart;   // Halbperiode bei Anfahrdrehzahl
    uint32_t accelSteps;    // Rampenlänge
    uint16_t maxRpm;        // nur für Statusausgabe
    uint16_t startRpm;      // nur für Statusausgabe
};

Motor axisX = { X_STEP, X_DIR, X_EN, X_ALM, 0, 0, true, false, 0.0f,
                rpmToHalfUs(X_MAX_SPEED_RPM), rpmToHalfUs(X_START_SPEED_RPM),
                X_ACCEL_STEPS, X_MAX_SPEED_RPM, X_START_SPEED_RPM };

Motor axisY = { Y_STEP, Y_DIR, Y_EN, Y_ALM, 0, 0, true, false, 0.0f,
                rpmToHalfUs(Y_MAX_SPEED_RPM), rpmToHalfUs(Y_START_SPEED_RPM),
                Y_ACCEL_STEPS, Y_MAX_SPEED_RPM, Y_START_SPEED_RPM };

// ────────────────────────────────────────────────────────────────────

void initMotor(const Motor& m) {
    pinMode(m.pinStep, OUTPUT);
    pinMode(m.pinDir,  OUTPUT);
    pinMode(m.pinEn,   OUTPUT);
    pinMode(m.pinAlm,  INPUT_PULLUP);
    digitalWrite(m.pinStep, LOW);
    digitalWrite(m.pinDir,  LOW);
    digitalWrite(m.pinEn,   HIGH);  // Treiber deaktiviert (active-low)
}

void enableMotor(Motor& m, bool on) {
    m.enabled = on;
    digitalWrite(m.pinEn, on ? LOW : HIGH);
}

bool checkAlarm(const Motor& m, char axis) {
    if (digitalRead(m.pinAlm) == LOW) {
        Serial.printf("!! ALARM Achse %c: CL42T meldet Fehler !!\n", axis);
        return true;
    }
    return false;
}

// Gibt Halbperiode [µs] für den aktuellen Schritt nach Trapezprofil zurück.
// Interpolation in Geschwindigkeit (1/Delay), nicht in Delay → konstante Beschleunigung.
uint32_t trapezDelay(const Motor& m) {
    uint32_t ramp      = min(m.accelSteps, m.totalSteps / 2);
    uint32_t stepsLeft = m.totalSteps - m.stepsDone;

    float t;
    if (m.stepsDone < ramp) {
        t = (float)m.stepsDone / ramp;   // 0 → 1 (Beschleunigung)
    } else if (stepsLeft <= ramp) {
        t = (float)stepsLeft / ramp;     // 1 → 0 (Bremsung)
    } else {
        return m.halfUsCruise;           // Konstantfahrt
    }
    // Lineare Interpolation in Geschwindigkeit (inv. Delay) → gleichmäßige Beschleunigung
    float invSpeed = (1.0f / m.halfUsStart) + t * (1.0f / m.halfUsCruise - 1.0f / m.halfUsStart);
    return (uint32_t)(1.0f / invSpeed);
}

// Führt beide Achsen gleichzeitig aus; jede mit eigenem Trapezprofil.
void runBothAxes(Motor& mx, Motor& mz) {
    bool moveX = mx.totalSteps > 0;
    bool moveZ = mz.totalSteps > 0;
    if (!moveX && !moveZ) return;

    if (moveX) {
        enableMotor(mx, true);
        digitalWrite(mx.pinDir, mx.forward ? HIGH : LOW);
    }
    if (moveZ) {
        enableMotor(mz, true);
        digitalWrite(mz.pinDir, mz.forward ? HIGH : LOW);
    }
    delayMicroseconds(T_DIR_US);

    mx.stepsDone = 0;
    mz.stepsDone = 0;

    uint32_t now  = micros();
    uint32_t nxtX = now;
    uint32_t nztZ = now;

    while ((moveX && mx.stepsDone < mx.totalSteps) ||
           (moveZ && mz.stepsDone < mz.totalSteps)) {

        now = micros();

        if (moveX && mx.stepsDone < mx.totalSteps && (int32_t)(now - nxtX) >= 0) {
            if (checkAlarm(mx, 'X')) {
                mx.stepsDone = mx.totalSteps;
            } else {
                uint32_t d = trapezDelay(mx);
                digitalWrite(mx.pinStep, HIGH);
                delayMicroseconds(T_STEP_US);
                digitalWrite(mx.pinStep, LOW);
                mx.stepsDone++;
                nxtX += 2 * d;
            }
        }

        if (moveZ && mz.stepsDone < mz.totalSteps && (int32_t)(now - nztZ) >= 0) {
            if (checkAlarm(mz, 'Z')) {
                mz.stepsDone = mz.totalSteps;
            } else {
                uint32_t d = trapezDelay(mz);
                digitalWrite(mz.pinStep, HIGH);
                delayMicroseconds(T_STEP_US);
                digitalWrite(mz.pinStep, LOW);
                mz.stepsDone++;
                nztZ += 2 * d;
            }
        }
    }

    Serial.println("Zielposition erreicht.");
}

void handleGoto(const String& args) {
    int sp = args.indexOf(' ');
    if (sp < 0) {
        Serial.println("ERR: goto <x_mm> <z_mm>");
        return;
    }
    float xMm = args.substring(0, sp).toFloat();
    float yMm = args.substring(sp + 1).toFloat();

    float dx = xMm - axisX.positionMm;
    float dy = yMm - axisY.positionMm;

    axisX.totalSteps = (uint32_t)(fabsf(dx) * STEPS_PER_MM_X + 0.5f);
    axisY.totalSteps = (uint32_t)(fabsf(dy) * STEPS_PER_MM_Y + 0.5f);
    axisX.forward    = dx >= 0.0f;
    axisY.forward    = dy >= 0.0f;

    Serial.printf("X: %.2f → %.2f mm  (%lu Schritte, %s)\n",
        axisX.positionMm, xMm, axisX.totalSteps, axisX.forward ? ">>" : "<<");
    Serial.printf("Y: %.2f → %.2f mm  (%lu Schritte, %s)\n",
        axisY.positionMm, yMm, axisY.totalSteps, axisY.forward ? ">>" : "<<");

    runBothAxes(axisX, axisY);

    axisX.positionMm = xMm;
    axisY.positionMm = yMm;
}

void printStatus() {
    Serial.println("───────────────────────────────────────");
    Serial.println("  goto <x_mm> <y_mm>   Positionieren");
    Serial.println("  home                  Nullpunkt setzen");
    Serial.println("  ?                     Status");
    Serial.println("───────────────────────────────────────");
    Serial.printf("  Pos X: %.2f mm  |  Pos Y: %.2f mm\n",
                  axisX.positionMm, axisY.positionMm);
    Serial.printf("  X – Max: %u RPM  Start: %u RPM  Rampe: %lu Schritte\n",
                  axisX.maxRpm, axisX.startRpm, axisX.accelSteps);
    Serial.printf("  Y – Max: %u RPM  Start: %u RPM  Rampe: %lu Schritte\n",
                  axisY.maxRpm, axisY.startRpm, axisY.accelSteps);
    Serial.printf("  Steps/mm X: %.1f  |  Steps/mm Y: %.1f\n",
                  STEPS_PER_MM_X, STEPS_PER_MM_Y);
    Serial.printf("  ALM X: %s  |  ALM Y: %s\n",
        digitalRead(X_ALM) == LOW ? "FEHLER" : "OK",
        digitalRead(Y_ALM) == LOW ? "FEHLER" : "OK");
    Serial.println("───────────────────────────────────────");
}

void handleCommand(const String& raw) {
    String cmd = raw;
    cmd.trim();
    if (cmd.length() == 0) return;

    if (cmd.startsWith("goto ")) {
        handleGoto(cmd.substring(5));
    } else if (cmd == "home") {
        axisX.positionMm = 0.0f;
        axisY.positionMm = 0.0f;
        Serial.println("Nullpunkt gesetzt.");
    } else if (cmd == "?") {
        printStatus();
    } else {
        Serial.println("Unbekannt – ? für Hilfe");
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    initMotor(axisX);
    initMotor(axisY);

    Serial.println("\nCL42T Zwei-Achsen-Test");
    printStatus();
}

void loop() {
    if (Serial.available()) {
        handleCommand(Serial.readStringUntil('\n'));
    }
}
