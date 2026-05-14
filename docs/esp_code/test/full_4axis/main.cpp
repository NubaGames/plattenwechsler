// Vier-Achsen-Test: 2x CL42T (X/Y, Trapezrampe) + 2x DRV8825 (Greifer/Tür, ein/aus)
//
// Pinbelegung:
//   CL42T  X:       STEP=27  DIR=14  EN=12  ALM=13
//   CL42T  Y:       STEP=32  DIR=33  EN=25  ALM=26
//   DRV8825 Greifer: STEP=23  DIR=19  EN=18
//   DRV8825 Tür:     STEP=17  DIR=16  EN=15
//   (CL42T: PUL-/DIR-/ENA- an GND, Einzelendsignal optoentkoppelt)
//   (DRV8825: 3.3V an VDD/RST/SLP, ext. 12V an VMOT)
//
// Befehle (Seriell 115200):
//   goto <x_mm> <y_mm>   CL42T-Achsen X und Y gleichzeitig verfahren
//   home all              Alle 4 Achsen auf Nullpunkt setzen
//   home x|y|greifer|tuer Einzelne Achse auf Nullpunkt setzen
//   greifer ein|aus       Greifer ein- oder ausfahren
//   tuer ein|aus          Tür ein- oder ausfahren
//   tuer oeffnen          Greifer aus → Schlitten+Greifer ein+Tür auf (gleichzeitig)
//   all go                goto 500/500 + Greifer+Tür je 5 Umdrehungen (gleichzeitig)
//   ?                     Status anzeigen

#include <Arduino.h>

// ════════════════════════════════════════════════════════════════════
// CL42T – Konfiguration
// ════════════════════════════════════════════════════════════════════

// ── Schritte pro Umdrehung (DIP-Schalter am CL42T) ─────────────────
constexpr uint16_t CL_STEPS_PER_REV = 800;

// ── Schritte pro Millimeter ─────────────────────────────────────────
constexpr float STEPS_PER_MM_X = 160.0f;
constexpr float STEPS_PER_MM_Y = 160.0f;

// ── Geschwindigkeit & Rampe – Achse X ──────────────────────────────
constexpr uint16_t X_MAX_SPEED_RPM   = 300;
constexpr uint16_t X_START_SPEED_RPM = 20;
constexpr uint32_t X_ACCEL_STEPS     = 4000;

// ── Geschwindigkeit & Rampe – Achse Y ──────────────────────────────
constexpr uint16_t Y_MAX_SPEED_RPM   = 300;
constexpr uint16_t Y_START_SPEED_RPM = 20;
constexpr uint32_t Y_ACCEL_STEPS     = 4000;

// ── CL42T Timing-Minima ─────────────────────────────────────────────
constexpr uint32_t CL_T_STEP_US = 3;
constexpr uint32_t CL_T_DIR_US  = 5;

// ── CL42T Pins ──────────────────────────────────────────────────────
constexpr uint8_t X_STEP = 27, X_DIR = 14, X_EN = 12, X_ALM = 13;
constexpr uint8_t Y_STEP = 32, Y_DIR = 33, Y_EN = 25, Y_ALM = 26;

// ════════════════════════════════════════════════════════════════════
// DRV8825 – Konfiguration
// ════════════════════════════════════════════════════════════════════

// ── Schritte pro Umdrehung (abhängig von Mikroschritt-Einstellung) ──
constexpr uint16_t DRV_STEPS_PER_REV = 200;

// ── Schritte für "ausgefahren" (eine Richtung ab Nullpunkt) ─────────
constexpr uint32_t GREIFER_TRAVEL_STEPS = 800;  // anpassen
constexpr uint32_t TUER_TRAVEL_STEPS    = 800;  // anpassen

// ── Schlitten-Verfahrweg beim Türöffnen [mm] ─────────────────────────
constexpr float TUER_SCHLITTEN_MM = 50.0f;

// ── Schrittgeschwindigkeit DRV8825 (fester Wert, kein Rampe nötig) ──
constexpr uint32_t DRV_STEP_DELAY_US = 2000;  // Halbperiode [µs]

// ── DRV8825 Timing-Minimum laut Datenblatt ──────────────────────────
constexpr uint32_t DRV_T_STEP_US = 2;
constexpr uint32_t DRV_T_DIR_US  = 1;

// ── DRV8825 Pins ────────────────────────────────────────────────────
constexpr uint8_t GREIFER_STEP = 23, GREIFER_DIR = 19, GREIFER_EN = 18;
constexpr uint8_t TUER_STEP    = 17, TUER_DIR    = 16, TUER_EN    = 15;

// ════════════════════════════════════════════════════════════════════
// CL42T – Strukturen & Logik
// ════════════════════════════════════════════════════════════════════

constexpr uint32_t rpmToHalfUs(uint16_t rpm) {
    return 30000000UL / ((uint32_t)rpm * CL_STEPS_PER_REV);
}

struct ClMotor {
    uint8_t  pinStep, pinDir, pinEn, pinAlm;
    uint32_t totalSteps;
    uint32_t stepsDone;
    bool     forward;
    bool     enabled;
    float    positionMm;
    uint32_t halfUsCruise;
    uint32_t halfUsStart;
    uint32_t accelSteps;
    uint16_t maxRpm;
    uint16_t startRpm;
};

ClMotor axisX = { X_STEP, X_DIR, X_EN, X_ALM, 0, 0, true, false, 0.0f,
                  rpmToHalfUs(X_MAX_SPEED_RPM), rpmToHalfUs(X_START_SPEED_RPM),
                  X_ACCEL_STEPS, X_MAX_SPEED_RPM, X_START_SPEED_RPM };

ClMotor axisY = { Y_STEP, Y_DIR, Y_EN, Y_ALM, 0, 0, true, false, 0.0f,
                  rpmToHalfUs(Y_MAX_SPEED_RPM), rpmToHalfUs(Y_START_SPEED_RPM),
                  Y_ACCEL_STEPS, Y_MAX_SPEED_RPM, Y_START_SPEED_RPM };

void initClMotor(const ClMotor& m) {
    pinMode(m.pinStep, OUTPUT);
    pinMode(m.pinDir,  OUTPUT);
    pinMode(m.pinEn,   OUTPUT);
    pinMode(m.pinAlm,  INPUT_PULLUP);
    digitalWrite(m.pinStep, LOW);
    digitalWrite(m.pinDir,  LOW);
    digitalWrite(m.pinEn,   HIGH);
}

void enableClMotor(ClMotor& m, bool on) {
    m.enabled = on;
    digitalWrite(m.pinEn, on ? LOW : HIGH);
}

bool checkAlarm(const ClMotor& m, char axis) {
    if (digitalRead(m.pinAlm) == LOW) {
        Serial.printf("!! ALARM Achse %c: CL42T meldet Fehler !!\n", axis);
        return true;
    }
    return false;
}

uint32_t trapezDelay(const ClMotor& m) {
    uint32_t ramp      = min(m.accelSteps, m.totalSteps / 2);
    uint32_t stepsLeft = m.totalSteps - m.stepsDone;

    float t;
    if (m.stepsDone < ramp) {
        t = (float)m.stepsDone / ramp;
    } else if (stepsLeft <= ramp) {
        t = (float)stepsLeft / ramp;
    } else {
        return m.halfUsCruise;
    }
    float invSpeed = (1.0f / m.halfUsStart) + t * (1.0f / m.halfUsCruise - 1.0f / m.halfUsStart);
    return (uint32_t)(1.0f / invSpeed);
}

void runBothAxes(ClMotor& mx, ClMotor& my) {
    bool moveX = mx.totalSteps > 0;
    bool moveY = my.totalSteps > 0;
    if (!moveX && !moveY) return;

    if (moveX) {
        enableClMotor(mx, true);
        digitalWrite(mx.pinDir, mx.forward ? HIGH : LOW);
    }
    if (moveY) {
        enableClMotor(my, true);
        digitalWrite(my.pinDir, my.forward ? HIGH : LOW);
    }
    delayMicroseconds(CL_T_DIR_US);

    mx.stepsDone = 0;
    my.stepsDone = 0;

    uint32_t now  = micros();
    uint32_t nxtX = now;
    uint32_t nxtY = now;

    while ((moveX && mx.stepsDone < mx.totalSteps) ||
           (moveY && my.stepsDone < my.totalSteps)) {

        now = micros();

        if (moveX && mx.stepsDone < mx.totalSteps && (int32_t)(now - nxtX) >= 0) {
            if (checkAlarm(mx, 'X')) {
                mx.stepsDone = mx.totalSteps;
            } else {
                uint32_t d = trapezDelay(mx);
                digitalWrite(mx.pinStep, HIGH);
                delayMicroseconds(CL_T_STEP_US);
                digitalWrite(mx.pinStep, LOW);
                mx.stepsDone++;
                nxtX += 2 * d;
            }
        }

        if (moveY && my.stepsDone < my.totalSteps && (int32_t)(now - nxtY) >= 0) {
            if (checkAlarm(my, 'Y')) {
                my.stepsDone = my.totalSteps;
            } else {
                uint32_t d = trapezDelay(my);
                digitalWrite(my.pinStep, HIGH);
                delayMicroseconds(CL_T_STEP_US);
                digitalWrite(my.pinStep, LOW);
                my.stepsDone++;
                nxtY += 2 * d;
            }
        }
    }
    Serial.println("Zielposition erreicht.");
}

// ════════════════════════════════════════════════════════════════════
// DRV8825 – Strukturen & Logik
// ════════════════════════════════════════════════════════════════════

enum class AktorState { EINGEFAHREN, AUSGEFAHREN };

struct Aktor {
    const char* name;
    uint8_t     pinStep, pinDir, pinEn;
    uint32_t    travelSteps;
    AktorState  state;
};

Aktor greifer = { "Greifer", GREIFER_STEP, GREIFER_DIR, GREIFER_EN,
                  GREIFER_TRAVEL_STEPS, AktorState::EINGEFAHREN };

Aktor tuer    = { "Tuer",    TUER_STEP,    TUER_DIR,    TUER_EN,
                  TUER_TRAVEL_STEPS,    AktorState::EINGEFAHREN };

void initAktor(const Aktor& a) {
    pinMode(a.pinStep, OUTPUT);
    pinMode(a.pinDir,  OUTPUT);
    pinMode(a.pinEn,   OUTPUT);
    digitalWrite(a.pinStep, LOW);
    digitalWrite(a.pinDir,  LOW);
    digitalWrite(a.pinEn,   HIGH);  // deaktiviert
}

void moveAktor(Aktor& a, bool ausfahren) {
    digitalWrite(a.pinEn,  LOW);
    digitalWrite(a.pinDir, ausfahren ? HIGH : LOW);
    delayMicroseconds(DRV_T_DIR_US);

    for (uint32_t i = 0; i < a.travelSteps; i++) {
        digitalWrite(a.pinStep, HIGH);
        delayMicroseconds(DRV_T_STEP_US);
        digitalWrite(a.pinStep, LOW);
        delayMicroseconds(DRV_STEP_DELAY_US);
    }

    digitalWrite(a.pinEn, HIGH);  // Treiber nach Fahrt deaktivieren
    a.state = ausfahren ? AktorState::AUSGEFAHREN : AktorState::EINGEFAHREN;
    Serial.printf("%s: %s\n", a.name, ausfahren ? "ausgefahren" : "eingefahren");
}

// CL42T-Achsen + bis zu zwei DRV8825-Aktoren gleichzeitig fahren.
// a2/a2Aus/a2DelayUs sind optional (a2 = nullptr → kein zweiter Aktor).
void runAxesAndAktor(ClMotor& mx, ClMotor& my,
                     Aktor& a1, bool a1Aus, uint32_t a1DelayUs,
                     Aktor* a2 = nullptr, bool a2Aus = false, uint32_t a2DelayUs = DRV_STEP_DELAY_US) {
    bool moveX  = mx.totalSteps > 0;
    bool moveY  = my.totalSteps > 0;
    bool moveA1 = a1.travelSteps > 0;
    bool moveA2 = a2 != nullptr && a2->travelSteps > 0;
    if (!moveX && !moveY && !moveA1 && !moveA2) return;

    if (moveX)  { enableClMotor(mx, true); digitalWrite(mx.pinDir, mx.forward ? HIGH : LOW); }
    if (moveY)  { enableClMotor(my, true); digitalWrite(my.pinDir, my.forward ? HIGH : LOW); }
    if (moveA1) { digitalWrite(a1.pinEn, LOW); digitalWrite(a1.pinDir, a1Aus ? HIGH : LOW); }
    if (moveA2) { digitalWrite(a2->pinEn, LOW); digitalWrite(a2->pinDir, a2Aus ? HIGH : LOW); }
    delayMicroseconds(CL_T_DIR_US);

    mx.stepsDone = 0;
    my.stepsDone = 0;
    uint32_t a1Done = 0, a2Done = 0;

    uint32_t now  = micros();
    uint32_t nxtX = now, nxtY = now, nxtA1 = now, nxtA2 = now;

    while ((moveX  && mx.stepsDone < mx.totalSteps) ||
           (moveY  && my.stepsDone < my.totalSteps) ||
           (moveA1 && a1Done < a1.travelSteps)      ||
           (moveA2 && a2Done < a2->travelSteps)) {

        now = micros();

        if (moveX && mx.stepsDone < mx.totalSteps && (int32_t)(now - nxtX) >= 0) {
            if (checkAlarm(mx, 'X')) { mx.stepsDone = mx.totalSteps; }
            else {
                uint32_t d = trapezDelay(mx);
                digitalWrite(mx.pinStep, HIGH); delayMicroseconds(CL_T_STEP_US); digitalWrite(mx.pinStep, LOW);
                mx.stepsDone++;
                nxtX += 2 * d;
            }
        }

        if (moveY && my.stepsDone < my.totalSteps && (int32_t)(now - nxtY) >= 0) {
            if (checkAlarm(my, 'Y')) { my.stepsDone = my.totalSteps; }
            else {
                uint32_t d = trapezDelay(my);
                digitalWrite(my.pinStep, HIGH); delayMicroseconds(CL_T_STEP_US); digitalWrite(my.pinStep, LOW);
                my.stepsDone++;
                nxtY += 2 * d;
            }
        }

        if (moveA1 && a1Done < a1.travelSteps && (int32_t)(now - nxtA1) >= 0) {
            digitalWrite(a1.pinStep, HIGH); delayMicroseconds(DRV_T_STEP_US); digitalWrite(a1.pinStep, LOW);
            a1Done++;
            nxtA1 += a1DelayUs;
        }

        if (moveA2 && a2Done < a2->travelSteps && (int32_t)(now - nxtA2) >= 0) {
            digitalWrite(a2->pinStep, HIGH); delayMicroseconds(DRV_T_STEP_US); digitalWrite(a2->pinStep, LOW);
            a2Done++;
            nxtA2 += a2DelayUs;
        }
    }

    if (moveA1) { digitalWrite(a1.pinEn, HIGH); a1.state = a1Aus ? AktorState::AUSGEFAHREN : AktorState::EINGEFAHREN; }
    if (moveA2) { digitalWrite(a2->pinEn, HIGH); a2->state = a2Aus ? AktorState::AUSGEFAHREN : AktorState::EINGEFAHREN; }
    Serial.println("Zielposition erreicht.");
}

void handleAktor(Aktor& a, const String& arg) {
    if (arg == "aus") {
        moveAktor(a, true);
    } else if (arg == "ein") {
        moveAktor(a, false);
    } else {
        Serial.printf("ERR: %s ein|aus\n", a.name);
    }
}

// ════════════════════════════════════════════════════════════════════
// Befehlsverarbeitung & Hauptprogramm
// ════════════════════════════════════════════════════════════════════

void handleTuerOeffnen() {
    // Schritt 1: Greifer ausfahren
    Serial.println("Schritt 1: Greifer ausfahren...");
    moveAktor(greifer, true);

    // Schritt 2: Schlitten +50mm, Greifer einfahren + Türmotor ausfahren (1/4 Geschwindigkeit)
    Serial.println("Schritt 2: Schlitten verfahren + Greifer ein + Tuer auf...");
    float xZiel = axisX.positionMm + TUER_SCHLITTEN_MM;
    float yZiel = axisY.positionMm + TUER_SCHLITTEN_MM;

    axisX.totalSteps = (uint32_t)(TUER_SCHLITTEN_MM * STEPS_PER_MM_X + 0.5f);
    axisY.totalSteps = (uint32_t)(TUER_SCHLITTEN_MM * STEPS_PER_MM_Y + 0.5f);
    axisX.forward    = true;
    axisY.forward    = true;

    runAxesAndAktor(axisX, axisY,
                    greifer, false, DRV_STEP_DELAY_US,
                    &tuer,   true,  DRV_STEP_DELAY_US * 4);

    axisX.positionMm = xZiel;
    axisY.positionMm = yZiel;
}

void handleAllGo() {
    float dx = 500.0f - axisX.positionMm;
    float dy = 500.0f - axisY.positionMm;
    axisX.totalSteps = (uint32_t)(fabsf(dx) * STEPS_PER_MM_X + 0.5f);
    axisY.totalSteps = (uint32_t)(fabsf(dy) * STEPS_PER_MM_Y + 0.5f);
    axisX.forward    = dx >= 0.0f;
    axisY.forward    = dy >= 0.0f;

    // DRV8825: 5 Umdrehungen – travelSteps und State temporär überschreiben,
    // da dies keine definierte Ein/Aus-Position ist.
    uint32_t   savedGSteps = greifer.travelSteps; AktorState savedGState = greifer.state;
    uint32_t   savedTSteps = tuer.travelSteps;    AktorState savedTState = tuer.state;
    greifer.travelSteps = 5 * DRV_STEPS_PER_REV;
    tuer.travelSteps    = 5 * DRV_STEPS_PER_REV;

    Serial.println("all go: goto 500/500 + Greifer + Tuer je 5 Umdrehungen...");
    runAxesAndAktor(axisX, axisY,
                    greifer, true, DRV_STEP_DELAY_US,
                    &tuer,   true, DRV_STEP_DELAY_US);

    greifer.travelSteps = savedGSteps; greifer.state = savedGState;
    tuer.travelSteps    = savedTSteps; tuer.state    = savedTState;

    axisX.positionMm = 500.0f;
    axisY.positionMm = 500.0f;
}

void handleGoto(const String& args) {
    int sp = args.indexOf(' ');
    if (sp < 0) { Serial.println("ERR: goto <x_mm> <y_mm>"); return; }

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
    Serial.println("───────────────────────────────────────────────");
    Serial.println("  goto <x_mm> <y_mm>   CL42T X+Y verfahren");
    Serial.println("  home all              Alle 4 Achsen homen");
    Serial.println("  home x|y|greifer|tuer Einzelne Achse homen");
    Serial.println("  greifer ein|aus       Greifer ein-/ausfahren");
    Serial.println("  tuer ein|aus          Tür ein-/ausfahren");
    Serial.println("  tuer oeffnen          Greifer aus → Schlitten+Greifer ein");
    Serial.println("  all go                goto 500/500 + alle 4 Motoren gleichzeitig");
    Serial.println("  ?                     Status");
    Serial.println("───────────────────────────────────────────────");
    Serial.printf("  Pos X: %.2f mm  |  Pos Y: %.2f mm\n",
                  axisX.positionMm, axisY.positionMm);
    Serial.printf("  X – Max: %u RPM  Start: %u RPM  Rampe: %lu Schritte\n",
                  axisX.maxRpm, axisX.startRpm, axisX.accelSteps);
    Serial.printf("  Y – Max: %u RPM  Start: %u RPM  Rampe: %lu Schritte\n",
                  axisY.maxRpm, axisY.startRpm, axisY.accelSteps);
    Serial.printf("  Greifer: %s  |  Tuer: %s\n",
        greifer.state == AktorState::AUSGEFAHREN ? "ausgefahren" : "eingefahren",
        tuer.state    == AktorState::AUSGEFAHREN ? "ausgefahren" : "eingefahren");
    Serial.printf("  ALM X: %s  |  ALM Y: %s\n",
        digitalRead(X_ALM) == LOW ? "FEHLER" : "OK",
        digitalRead(Y_ALM) == LOW ? "FEHLER" : "OK");
    Serial.println("───────────────────────────────────────────────");
}

void handleCommand(const String& raw) {
    String cmd = raw;
    cmd.trim();
    if (cmd.length() == 0) return;

    if (cmd.startsWith("goto ")) {
        handleGoto(cmd.substring(5));
    } else if (cmd.startsWith("home")) {
        String arg = cmd.substring(4);
        arg.trim();
        if (arg == "all" || arg == "") {
            axisX.positionMm = 0.0f;
            axisY.positionMm = 0.0f;
            greifer.state    = AktorState::EINGEFAHREN;
            tuer.state       = AktorState::EINGEFAHREN;
            Serial.println("Nullpunkt gesetzt: X, Y, Greifer, Tuer.");
        } else if (arg == "x") {
            axisX.positionMm = 0.0f;
            Serial.println("Nullpunkt gesetzt: X.");
        } else if (arg == "y") {
            axisY.positionMm = 0.0f;
            Serial.println("Nullpunkt gesetzt: Y.");
        } else if (arg == "greifer") {
            greifer.state = AktorState::EINGEFAHREN;
            Serial.println("Nullpunkt gesetzt: Greifer.");
        } else if (arg == "tuer") {
            tuer.state = AktorState::EINGEFAHREN;
            Serial.println("Nullpunkt gesetzt: Tuer.");
        } else {
            Serial.println("ERR: home all|x|y|greifer|tuer");
        }
    } else if (cmd.startsWith("greifer ")) {
        handleAktor(greifer, cmd.substring(8));
    } else if (cmd == "all go") {
        handleAllGo();
    } else if (cmd == "tuer oeffnen") {
        handleTuerOeffnen();
    } else if (cmd.startsWith("tuer ")) {
        handleAktor(tuer, cmd.substring(5));
    } else if (cmd == "?") {
        printStatus();
    } else {
        Serial.println("Unbekannt – ? für Hilfe");
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    initClMotor(axisX);
    initClMotor(axisY);
    initAktor(greifer);
    initAktor(tuer);

    Serial.println("\nVier-Achsen-Test (CL42T x2 + DRV8825 x2)");
    printStatus();
}

void loop() {
    if (Serial.available()) {
        handleCommand(Serial.readStringUntil('\n'));
    }
}
