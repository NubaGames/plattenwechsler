// Vollsystem-Test: 2x CL42T + 2x DRV8825 + VL53L0X + TF-Luna
//
// Pinbelegung Motoren:
//   CL42T  X:        STEP=27  DIR=14  EN=12  ALM=13
//   CL42T  Y:        STEP=32  DIR=33  EN=25  ALM=26
//   DRV8825 Greifer: STEP=23  DIR=19  EN=18
//   DRV8825 Tür:     STEP=17  DIR=16  EN=15
//
// Pinbelegung Sensoren:
//   I2C SDA = GPIO 21
//   I2C SCL = GPIO 22
//   VL53L0X Adresse: 0x29
//   TF-Luna  Adresse: 0x10  (vorab per Konfig-Pin auf I2C-Mode stellen)
//
// Befehle (Seriell 115200):
//   goto <x_mm> <y_mm>   CL42T X+Y verfahren
//   home all              Alle 4 Motorachsen auf Nullpunkt
//   home x|y|greifer|tuer Einzelne Achse homen
//   greifer ein|aus       Greifer ein-/ausfahren
//   tuer ein|aus          Tür ein-/ausfahren
//   tuer oeffnen          Greifer aus → Schlitten+Greifer ein+Tür auf
//   all go                goto 500/500 + alle 4 Motoren gleichzeitig
//   read                  Beide Sensoren einmal auslesen
//   stream on|off         Sensor-Streaming (100 ms)
//   scan                  I2C-Bus scannen
//   ?                     Status

#include <Arduino.h>
#include <Wire.h>

#include <VL53L0X.h>

// ════════════════════════════════════════════════════════════════════
// CL42T – Konfiguration
// ════════════════════════════════════════════════════════════════════

constexpr uint16_t CL_STEPS_PER_REV  = 800;

constexpr float    STEPS_PER_MM_X    = 160.0f;
constexpr float    STEPS_PER_MM_Y    = 160.0f;

constexpr uint16_t X_MAX_SPEED_RPM   = 300;
constexpr uint16_t X_START_SPEED_RPM = 20;
constexpr uint32_t X_ACCEL_STEPS     = 4000;

constexpr uint16_t Y_MAX_SPEED_RPM   = 300;
constexpr uint16_t Y_START_SPEED_RPM = 20;
constexpr uint32_t Y_ACCEL_STEPS     = 4000;

constexpr uint32_t CL_T_STEP_US      = 3;
constexpr uint32_t CL_T_DIR_US       = 5;

constexpr uint8_t X_STEP = 27, X_DIR = 14, X_EN = 12, X_ALM = 13;
constexpr uint8_t Y_STEP = 32, Y_DIR = 33, Y_EN = 25, Y_ALM = 26;

// ════════════════════════════════════════════════════════════════════
// DRV8825 – Konfiguration
// ════════════════════════════════════════════════════════════════════

constexpr uint16_t DRV_STEPS_PER_REV   = 200;
constexpr uint32_t GREIFER_TRAVEL_STEPS = 800;
constexpr uint32_t TUER_TRAVEL_STEPS    = 800;
constexpr float    TUER_SCHLITTEN_MM    = 50.0f;
constexpr uint32_t DRV_STEP_DELAY_US    = 2000;
constexpr uint32_t DRV_T_STEP_US        = 2;
constexpr uint32_t DRV_T_DIR_US         = 1;

constexpr uint8_t GREIFER_STEP = 23, GREIFER_DIR = 19, GREIFER_EN = 18;
constexpr uint8_t TUER_STEP    = 17, TUER_DIR    = 16, TUER_EN    = 15;

// ════════════════════════════════════════════════════════════════════
// Sensoren – Konfiguration
// ════════════════════════════════════════════════════════════════════

constexpr uint8_t  PIN_SDA          = 21;
constexpr uint8_t  PIN_SCL          = 22;
constexpr uint8_t  TFLUNA_ADDR      = 0x10;
constexpr uint16_t TFLUNA_AMP_MIN   = 100;
constexpr uint32_t STREAM_INTERVAL_MS = 100;

// ════════════════════════════════════════════════════════════════════
// CL42T – Strukturen & Logik
// ════════════════════════════════════════════════════════════════════

constexpr uint32_t rpmToHalfUs(uint16_t rpm) {
    return 30000000UL / ((uint32_t)rpm * CL_STEPS_PER_REV);
}

struct ClMotor {
    uint8_t  pinStep, pinDir, pinEn, pinAlm;
    uint32_t totalSteps, stepsDone;
    bool     forward, enabled;
    float    positionMm;
    uint32_t halfUsCruise, halfUsStart, accelSteps;
    uint16_t maxRpm, startRpm;
};

ClMotor axisX = { X_STEP, X_DIR, X_EN, X_ALM, 0, 0, true, false, 0.0f,
                  rpmToHalfUs(X_MAX_SPEED_RPM), rpmToHalfUs(X_START_SPEED_RPM),
                  X_ACCEL_STEPS, X_MAX_SPEED_RPM, X_START_SPEED_RPM };

ClMotor axisY = { Y_STEP, Y_DIR, Y_EN, Y_ALM, 0, 0, true, false, 0.0f,
                  rpmToHalfUs(Y_MAX_SPEED_RPM), rpmToHalfUs(Y_START_SPEED_RPM),
                  Y_ACCEL_STEPS, Y_MAX_SPEED_RPM, Y_START_SPEED_RPM };

void initClMotor(const ClMotor& m) {
    pinMode(m.pinStep, OUTPUT); pinMode(m.pinDir, OUTPUT);
    pinMode(m.pinEn,   OUTPUT); pinMode(m.pinAlm, INPUT_PULLUP);
    digitalWrite(m.pinStep, LOW); digitalWrite(m.pinDir, LOW); digitalWrite(m.pinEn, HIGH);
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
    if      (m.stepsDone < ramp) t = (float)m.stepsDone / ramp;
    else if (stepsLeft   <= ramp) t = (float)stepsLeft   / ramp;
    else return m.halfUsCruise;
    float inv = (1.0f / m.halfUsStart) + t * (1.0f / m.halfUsCruise - 1.0f / m.halfUsStart);
    return (uint32_t)(1.0f / inv);
}

void runBothAxes(ClMotor& mx, ClMotor& my) {
    bool moveX = mx.totalSteps > 0, moveY = my.totalSteps > 0;
    if (!moveX && !moveY) return;
    if (moveX) { enableClMotor(mx, true); digitalWrite(mx.pinDir, mx.forward ? HIGH : LOW); }
    if (moveY) { enableClMotor(my, true); digitalWrite(my.pinDir, my.forward ? HIGH : LOW); }
    delayMicroseconds(CL_T_DIR_US);
    mx.stepsDone = 0; my.stepsDone = 0;
    uint32_t now = micros(), nxtX = now, nxtY = now;
    while ((moveX && mx.stepsDone < mx.totalSteps) || (moveY && my.stepsDone < my.totalSteps)) {
        now = micros();
        if (moveX && mx.stepsDone < mx.totalSteps && (int32_t)(now - nxtX) >= 0) {
            if (checkAlarm(mx, 'X')) { mx.stepsDone = mx.totalSteps; }
            else { uint32_t d = trapezDelay(mx); digitalWrite(mx.pinStep, HIGH); delayMicroseconds(CL_T_STEP_US); digitalWrite(mx.pinStep, LOW); mx.stepsDone++; nxtX += 2*d; }
        }
        if (moveY && my.stepsDone < my.totalSteps && (int32_t)(now - nxtY) >= 0) {
            if (checkAlarm(my, 'Y')) { my.stepsDone = my.totalSteps; }
            else { uint32_t d = trapezDelay(my); digitalWrite(my.pinStep, HIGH); delayMicroseconds(CL_T_STEP_US); digitalWrite(my.pinStep, LOW); my.stepsDone++; nxtY += 2*d; }
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

Aktor greifer = { "Greifer", GREIFER_STEP, GREIFER_DIR, GREIFER_EN, GREIFER_TRAVEL_STEPS, AktorState::EINGEFAHREN };
Aktor tuer    = { "Tuer",    TUER_STEP,    TUER_DIR,    TUER_EN,    TUER_TRAVEL_STEPS,    AktorState::EINGEFAHREN };

void initAktor(const Aktor& a) {
    pinMode(a.pinStep, OUTPUT); pinMode(a.pinDir, OUTPUT); pinMode(a.pinEn, OUTPUT);
    digitalWrite(a.pinStep, LOW); digitalWrite(a.pinDir, LOW); digitalWrite(a.pinEn, HIGH);
}

void moveAktor(Aktor& a, bool ausfahren) {
    digitalWrite(a.pinEn, LOW);
    digitalWrite(a.pinDir, ausfahren ? HIGH : LOW);
    delayMicroseconds(DRV_T_DIR_US);
    for (uint32_t i = 0; i < a.travelSteps; i++) {
        digitalWrite(a.pinStep, HIGH); delayMicroseconds(DRV_T_STEP_US);
        digitalWrite(a.pinStep, LOW);  delayMicroseconds(DRV_STEP_DELAY_US);
    }
    digitalWrite(a.pinEn, HIGH);
    a.state = ausfahren ? AktorState::AUSGEFAHREN : AktorState::EINGEFAHREN;
    Serial.printf("%s: %s\n", a.name, ausfahren ? "ausgefahren" : "eingefahren");
}

void runAxesAndAktor(ClMotor& mx, ClMotor& my,
                     Aktor& a1, bool a1Aus, uint32_t a1DelayUs,
                     Aktor* a2 = nullptr, bool a2Aus = false, uint32_t a2DelayUs = DRV_STEP_DELAY_US) {
    bool moveX  = mx.totalSteps > 0, moveY  = my.totalSteps > 0;
    bool moveA1 = a1.travelSteps > 0, moveA2 = a2 != nullptr && a2->travelSteps > 0;
    if (!moveX && !moveY && !moveA1 && !moveA2) return;
    if (moveX)  { enableClMotor(mx, true); digitalWrite(mx.pinDir, mx.forward ? HIGH : LOW); }
    if (moveY)  { enableClMotor(my, true); digitalWrite(my.pinDir, my.forward ? HIGH : LOW); }
    if (moveA1) { digitalWrite(a1.pinEn, LOW);    digitalWrite(a1.pinDir,    a1Aus ? HIGH : LOW); }
    if (moveA2) { digitalWrite(a2->pinEn, LOW);   digitalWrite(a2->pinDir,   a2Aus ? HIGH : LOW); }
    delayMicroseconds(CL_T_DIR_US);
    mx.stepsDone = 0; my.stepsDone = 0;
    uint32_t a1Done = 0, a2Done = 0;
    uint32_t now = micros(), nxtX = now, nxtY = now, nxtA1 = now, nxtA2 = now;
    while ((moveX  && mx.stepsDone < mx.totalSteps) || (moveY  && my.stepsDone < my.totalSteps) ||
           (moveA1 && a1Done < a1.travelSteps)      || (moveA2 && a2Done < a2->travelSteps)) {
        now = micros();
        if (moveX && mx.stepsDone < mx.totalSteps && (int32_t)(now - nxtX) >= 0) {
            if (checkAlarm(mx, 'X')) { mx.stepsDone = mx.totalSteps; }
            else { uint32_t d = trapezDelay(mx); digitalWrite(mx.pinStep, HIGH); delayMicroseconds(CL_T_STEP_US); digitalWrite(mx.pinStep, LOW); mx.stepsDone++; nxtX += 2*d; }
        }
        if (moveY && my.stepsDone < my.totalSteps && (int32_t)(now - nxtY) >= 0) {
            if (checkAlarm(my, 'Y')) { my.stepsDone = my.totalSteps; }
            else { uint32_t d = trapezDelay(my); digitalWrite(my.pinStep, HIGH); delayMicroseconds(CL_T_STEP_US); digitalWrite(my.pinStep, LOW); my.stepsDone++; nxtY += 2*d; }
        }
        if (moveA1 && a1Done < a1.travelSteps && (int32_t)(now - nxtA1) >= 0) {
            digitalWrite(a1.pinStep, HIGH); delayMicroseconds(DRV_T_STEP_US); digitalWrite(a1.pinStep, LOW);
            a1Done++; nxtA1 += a1DelayUs;
        }
        if (moveA2 && a2Done < a2->travelSteps && (int32_t)(now - nxtA2) >= 0) {
            digitalWrite(a2->pinStep, HIGH); delayMicroseconds(DRV_T_STEP_US); digitalWrite(a2->pinStep, LOW);
            a2Done++; nxtA2 += a2DelayUs;
        }
    }
    if (moveA1) { digitalWrite(a1.pinEn,  HIGH); a1.state    = a1Aus ? AktorState::AUSGEFAHREN : AktorState::EINGEFAHREN; }
    if (moveA2) { digitalWrite(a2->pinEn, HIGH); a2->state   = a2Aus ? AktorState::AUSGEFAHREN : AktorState::EINGEFAHREN; }
    Serial.println("Zielposition erreicht.");
}

void handleAktor(Aktor& a, const String& arg) {
    if      (arg == "aus") moveAktor(a, true);
    else if (arg == "ein") moveAktor(a, false);
    else Serial.printf("ERR: %s ein|aus\n", a.name);
}

// ════════════════════════════════════════════════════════════════════
// Sensoren – Logik
// ════════════════════════════════════════════════════════════════════

VL53L0X  vl53;
bool     vl53Ok       = false;
bool     tfLunaOk     = false;
bool     streaming    = false;
uint32_t lastStream   = 0;

bool readTFLuna(uint16_t& distCm, uint16_t& amplitude) {
    Wire.beginTransmission(TFLUNA_ADDR);
    Wire.write(0x00);
    if (Wire.endTransmission(false) != 0) return false;  // Repeated-Start
    if (Wire.requestFrom((uint8_t)TFLUNA_ADDR, (uint8_t)6) < 6) return false;
    uint8_t b[6];
    for (uint8_t i = 0; i < 6; i++) b[i] = Wire.read();
    distCm    = (uint16_t)b[0] | ((uint16_t)b[1] << 8);
    amplitude = (uint16_t)b[2] | ((uint16_t)b[3] << 8);
    return true;
}

void debugTFLuna() {
    Serial.println("TF-Luna Debug:");

    // Verbindungstest
    Wire.beginTransmission(TFLUNA_ADDR);
    uint8_t err = Wire.endTransmission(true);
    Serial.printf("  beginTransmission(0x10): err=%u  %s\n", err,
        err == 0 ? "OK" : err == 2 ? "NACK Adresse" : err == 3 ? "NACK Daten" : "Fehler");

    if (err != 0) { Serial.println("  Sensor nicht erreichbar."); return; }

    // Rohe Bytes ausgeben
    Wire.beginTransmission(TFLUNA_ADDR);
    Wire.write(0x00);
    Wire.endTransmission(true);
    delayMicroseconds(200);
    uint8_t n = Wire.requestFrom((uint8_t)TFLUNA_ADDR, (uint8_t)6);
    Serial.printf("  requestFrom: %u Byte erhalten\n", n);
    if (n > 0) {
        Serial.print("  Rohdaten: ");
        for (uint8_t i = 0; i < n; i++) Serial.printf("0x%02X ", Wire.read());
        Serial.println();
    }
    // Versuch ohne Register-Write (manche Firmware-Versionen)
    n = Wire.requestFrom((uint8_t)TFLUNA_ADDR, (uint8_t)6);
    Serial.printf("  requestFrom ohne Register-Write: %u Byte\n", n);
    if (n > 0) {
        uint8_t b[6] = {};
        for (uint8_t i = 0; i < n; i++) b[i] = Wire.read();
        Serial.print("  Rohdaten: ");
        for (uint8_t i = 0; i < n; i++) Serial.printf("0x%02X ", b[i]);
        Serial.println();
        uint16_t d = (uint16_t)b[0] | ((uint16_t)b[1] << 8);
        Serial.printf("  → Distanz (interpretiert): %u cm\n", d);
    }
}

void printReading() {
    if (vl53Ok) {
        uint16_t mm = vl53.readRangeContinuousMillimeters();
        if      (vl53.timeoutOccurred()) Serial.print("VL53L0X: TIMEOUT         ");
        else if (mm > 950)               Serial.print("VL53L0X: außer Reichweite");
        else                             Serial.printf("VL53L0X: %5u mm          ", mm);
    } else {
        Serial.print("VL53L0X: n/a             ");
    }
    Serial.print("   |   ");
    if (tfLunaOk) {
        uint16_t cm, amp;
        if (!readTFLuna(cm, amp))       Serial.print("TF-Luna: FEHLER");
        else if (amp < TFLUNA_AMP_MIN)  Serial.printf("TF-Luna: %4u cm  (Amp %u – schwaches Signal)", cm, amp);
        else                            Serial.printf("TF-Luna: %4u cm  (Amp %u)", cm, amp);
    } else {
        Serial.print("TF-Luna: n/a");
    }
    Serial.println();
}

void scanI2C() {
    Serial.println("I2C-Scan...");
    uint8_t found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("  0x%02X", addr);
            if      (addr == 0x29) Serial.print("  ← VL53L0X");
            else if (addr == 0x10) Serial.print("  ← TF-Luna");
            Serial.println();
            found++;
        }
    }
    Serial.printf(found ? "  %u Gerät(e) gefunden.\n" : "  Keine Geräte gefunden.\n", found);
}

// ════════════════════════════════════════════════════════════════════
// Befehlsverarbeitung & Hauptprogramm
// ════════════════════════════════════════════════════════════════════

void handleTuerOeffnen() {
    Serial.println("Schritt 1: Greifer ausfahren...");
    moveAktor(greifer, true);
    Serial.println("Schritt 2: Schlitten + Greifer ein + Tuer auf...");
    float xZiel = axisX.positionMm + TUER_SCHLITTEN_MM;
    float yZiel = axisY.positionMm + TUER_SCHLITTEN_MM;
    axisX.totalSteps = (uint32_t)(TUER_SCHLITTEN_MM * STEPS_PER_MM_X + 0.5f);
    axisY.totalSteps = (uint32_t)(TUER_SCHLITTEN_MM * STEPS_PER_MM_Y + 0.5f);
    axisX.forward = true; axisY.forward = true;
    runAxesAndAktor(axisX, axisY, greifer, false, DRV_STEP_DELAY_US, &tuer, true, DRV_STEP_DELAY_US * 4);
    axisX.positionMm = xZiel; axisY.positionMm = yZiel;
}

void handleAllGo() {
    float dx = 500.0f - axisX.positionMm, dy = 500.0f - axisY.positionMm;
    axisX.totalSteps = (uint32_t)(fabsf(dx) * STEPS_PER_MM_X + 0.5f);
    axisY.totalSteps = (uint32_t)(fabsf(dy) * STEPS_PER_MM_Y + 0.5f);
    axisX.forward = dx >= 0.0f; axisY.forward = dy >= 0.0f;
    uint32_t sG = greifer.travelSteps; AktorState stG = greifer.state;
    uint32_t sT = tuer.travelSteps;    AktorState stT = tuer.state;
    greifer.travelSteps = 5 * DRV_STEPS_PER_REV;
    tuer.travelSteps    = 5 * DRV_STEPS_PER_REV;
    Serial.println("all go: goto 500/500 + Greifer + Tuer je 5 Umdrehungen...");
    runAxesAndAktor(axisX, axisY, greifer, true, DRV_STEP_DELAY_US, &tuer, true, DRV_STEP_DELAY_US);
    greifer.travelSteps = sG; greifer.state = stG;
    tuer.travelSteps    = sT; tuer.state    = stT;
    axisX.positionMm = 500.0f; axisY.positionMm = 500.0f;
}

void handleGoto(const String& args) {
    int sp = args.indexOf(' ');
    if (sp < 0) { Serial.println("ERR: goto <x_mm> <y_mm>"); return; }
    float xMm = args.substring(0, sp).toFloat();
    float yMm = args.substring(sp + 1).toFloat();
    float dx = xMm - axisX.positionMm, dy = yMm - axisY.positionMm;
    axisX.totalSteps = (uint32_t)(fabsf(dx) * STEPS_PER_MM_X + 0.5f);
    axisY.totalSteps = (uint32_t)(fabsf(dy) * STEPS_PER_MM_Y + 0.5f);
    axisX.forward = dx >= 0.0f; axisY.forward = dy >= 0.0f;
    Serial.printf("X: %.2f → %.2f mm  (%lu Schritte, %s)\n", axisX.positionMm, xMm, axisX.totalSteps, axisX.forward ? ">>" : "<<");
    Serial.printf("Y: %.2f → %.2f mm  (%lu Schritte, %s)\n", axisY.positionMm, yMm, axisY.totalSteps, axisY.forward ? ">>" : "<<");
    runBothAxes(axisX, axisY);
    axisX.positionMm = xMm; axisY.positionMm = yMm;
}

void printStatus() {
    Serial.println("────────────────────────────────────────────────────");
    Serial.println("  goto <x_mm> <y_mm>   CL42T X+Y verfahren");
    Serial.println("  home all              Alle 4 Motorachsen homen");
    Serial.println("  home x|y|greifer|tuer Einzelne Achse homen");
    Serial.println("  greifer ein|aus       Greifer ein-/ausfahren");
    Serial.println("  tuer ein|aus          Tür ein-/ausfahren");
    Serial.println("  tuer oeffnen          Greifer aus → Schlitten+Greifer ein+Tür auf");
    Serial.println("  all go                goto 500/500 + alle 4 Motoren gleichzeitig");
    Serial.println("  read                  Beide Sensoren auslesen");
    Serial.println("  stream on|off         Sensor-Streaming (100 ms)");
    Serial.println("  scan                  I2C-Bus scannen");
    Serial.println("  ?                     Status");
    Serial.println("────────────────────────────────────────────────────");
    Serial.printf("  Pos X: %.2f mm  |  Pos Y: %.2f mm\n", axisX.positionMm, axisY.positionMm);
    Serial.printf("  X – Max: %u RPM  Start: %u RPM  Rampe: %lu Schritte\n", axisX.maxRpm, axisX.startRpm, axisX.accelSteps);
    Serial.printf("  Y – Max: %u RPM  Start: %u RPM  Rampe: %lu Schritte\n", axisY.maxRpm, axisY.startRpm, axisY.accelSteps);
    Serial.printf("  Greifer: %s  |  Tuer: %s\n",
        greifer.state == AktorState::AUSGEFAHREN ? "ausgefahren" : "eingefahren",
        tuer.state    == AktorState::AUSGEFAHREN ? "ausgefahren" : "eingefahren");
    Serial.printf("  ALM X: %s  |  ALM Y: %s\n",
        digitalRead(X_ALM) == LOW ? "FEHLER" : "OK",
        digitalRead(Y_ALM) == LOW ? "FEHLER" : "OK");
    Serial.printf("  VL53L0X (0x29): %s\n", vl53Ok   ? "OK" : "nicht gefunden");
    Serial.printf("  TF-Luna (0x10): %s\n", tfLunaOk ? "OK" : "nicht gefunden");
    Serial.printf("  Streaming:      %s\n", streaming ? "EIN" : "AUS");
    Serial.println("────────────────────────────────────────────────────");
}

void handleCommand(const String& raw) {
    String cmd = raw;
    cmd.trim();
    if (cmd.length() == 0) return;

    if      (cmd.startsWith("goto "))    handleGoto(cmd.substring(5));
    else if (cmd.startsWith("home")) {
        String arg = cmd.substring(4); arg.trim();
        if      (arg == "all" || arg == "") {
            axisX.positionMm = 0.0f; axisY.positionMm = 0.0f;
            greifer.state = AktorState::EINGEFAHREN; tuer.state = AktorState::EINGEFAHREN;
            Serial.println("Nullpunkt gesetzt: X, Y, Greifer, Tuer.");
        }
        else if (arg == "x")       { axisX.positionMm = 0.0f;                    Serial.println("Nullpunkt gesetzt: X."); }
        else if (arg == "y")       { axisY.positionMm = 0.0f;                    Serial.println("Nullpunkt gesetzt: Y."); }
        else if (arg == "greifer") { greifer.state = AktorState::EINGEFAHREN;     Serial.println("Nullpunkt gesetzt: Greifer."); }
        else if (arg == "tuer")    { tuer.state    = AktorState::EINGEFAHREN;     Serial.println("Nullpunkt gesetzt: Tuer."); }
        else                       Serial.println("ERR: home all|x|y|greifer|tuer");
    }
    else if (cmd.startsWith("greifer ")) handleAktor(greifer, cmd.substring(8));
    else if (cmd == "all go")            handleAllGo();
    else if (cmd == "tuer oeffnen")      handleTuerOeffnen();
    else if (cmd.startsWith("tuer "))    handleAktor(tuer, cmd.substring(5));
    else if (cmd == "read")              printReading();
    else if (cmd == "stream on")         { streaming = true;  Serial.println("Streaming EIN."); }
    else if (cmd == "stream off")        { streaming = false; Serial.println("Streaming AUS."); }
    else if (cmd == "scan")              scanI2C();
    else if (cmd == "tfluna debug")      debugTFLuna();
    else if (cmd == "?")                 printStatus();
    else                                 Serial.println("Unbekannt – ? für Hilfe");
}

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    // Motoren
    initClMotor(axisX); initClMotor(axisY);
    initAktor(greifer); initAktor(tuer);

    // Sensoren
    Wire.begin(PIN_SDA, PIN_SCL);
    vl53.setTimeout(500);
    if (vl53.init()) { vl53.startContinuous(); vl53Ok = true; Serial.println("VL53L0X: OK"); }
    else               Serial.println("VL53L0X: nicht gefunden (0x29)");
    // TF-Luna braucht nach Power-On bis zu 500 ms zum Booten
    delay(500);
    Wire.beginTransmission(TFLUNA_ADDR);
    tfLunaOk = (Wire.endTransmission() == 0);
    Serial.printf("TF-Luna: %s\n", tfLunaOk ? "OK" : "nicht gefunden (0x10)");

    Serial.println("\nVollsystem-Test (4 Motoren + 2 Sensoren)");
    printStatus();
}

void loop() {
    if (Serial.available()) {
        handleCommand(Serial.readStringUntil('\n'));
    }
    // TF-Luna nachträglich erkennen falls beim Boot noch nicht bereit
    if (!tfLunaOk && millis() > 2000) {
        Wire.beginTransmission(TFLUNA_ADDR);
        if (Wire.endTransmission() == 0) {
            tfLunaOk = true;
            Serial.println("TF-Luna: nachträglich erkannt (0x10)");
        }
    }
    if (streaming && millis() - lastStream >= STREAM_INTERVAL_MS) {
        lastStream = millis();
        printReading();
    }
}
