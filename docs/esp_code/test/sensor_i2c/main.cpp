// I2C-Sensor-Test: VL53L0X + TF-Luna am selben Bus
//
// Verdrahtung:
//   SDA = GPIO 21
//   SCL = GPIO 22
//   VCC = 3.3V, GND = GND (beide Sensoren)
//
//   TF-Luna muss vorab per Konfig-Pin auf I2C-Mode gestellt werden.
//   VL53L0X I2C-Adresse: 0x29
//   TF-Luna  I2C-Adresse: 0x10 (Default)
//
// Befehle (Seriell 115200):
//   read          Einmaliges Auslesen beider Sensoren
//   stream on|off Kontinuierliches Auslesen (alle 100 ms)
//   scan          I2C-Bus nach Geräten absuchen
//   ?             Hilfe & Status

#include <Arduino.h>
#include <Wire.h>
#include <VL53L0X.h>

// ── I2C-Pins ────────────────────────────────────────────────────────
constexpr uint8_t PIN_SDA = 21;
constexpr uint8_t PIN_SCL = 22;

// ── TF-Luna Konfiguration ───────────────────────────────────────────
constexpr uint8_t  TFLUNA_ADDR     = 0x10;
constexpr uint8_t  TFLUNA_REG_DIST = 0x00;  // 2 Byte, Little-Endian, Einheit: cm
constexpr uint8_t  TFLUNA_REG_AMP  = 0x02;  // 2 Byte, Signalstärke
constexpr uint16_t TFLUNA_AMP_MIN  = 100;   // unter diesem Wert → Messung unzuverlässig

// ── Streaming ───────────────────────────────────────────────────────
constexpr uint32_t STREAM_INTERVAL_MS = 100;

// ════════════════════════════════════════════════════════════════════

VL53L0X vl53;
bool     vl53Ok     = false;
bool     tfLunaOk   = false;
bool     streaming  = false;
uint32_t lastStream = 0;

// ── TF-Luna: 6 Byte ab Register 0x00 lesen (dist + amplitude + temp) ─
bool readTFLuna(uint16_t& distCm, uint16_t& amplitude) {
    Wire.beginTransmission(TFLUNA_ADDR);
    Wire.write(TFLUNA_REG_DIST);
    if (Wire.endTransmission(false) != 0) return false;

    if (Wire.requestFrom((uint8_t)TFLUNA_ADDR, (uint8_t)6) < 6) return false;

    uint8_t b[6];
    for (uint8_t i = 0; i < 6; i++) b[i] = Wire.read();

    distCm    = (uint16_t)b[0] | ((uint16_t)b[1] << 8);
    amplitude = (uint16_t)b[2] | ((uint16_t)b[3] << 8);
    return true;
}

void printReading() {
    // VL53L0X
    if (vl53Ok) {
        uint16_t mm = vl53.readRangeSingleMillimeters();
        if (vl53.timeoutOccurred()) {
            Serial.print("VL53L0X: TIMEOUT        ");
        } else if (mm > 950) {
            Serial.print("VL53L0X: außer Reichweite");
        } else {
            Serial.printf("VL53L0X: %5u mm         ", mm);
        }
    } else {
        Serial.print("VL53L0X: n/a     ");
    }

    Serial.print("   |   ");

    // TF-Luna
    if (tfLunaOk) {
        uint16_t cm, amp;
        if (!readTFLuna(cm, amp)) {
            Serial.print("TF-Luna: FEHLER");
        } else if (amp < TFLUNA_AMP_MIN) {
            Serial.printf("TF-Luna: %4u cm  (Amp %u – schwaches Signal)", cm, amp);
        } else {
            Serial.printf("TF-Luna: %4u cm  (Amp %u)", cm, amp);
        }
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
            Serial.printf("  Gerät gefunden: 0x%02X", addr);
            if (addr == 0x29)       Serial.print("  ← VL53L0X");
            else if (addr == 0x10)  Serial.print("  ← TF-Luna");
            Serial.println();
            found++;
        }
    }
    if (found == 0) Serial.println("  Keine Geräte gefunden.");
    else Serial.printf("  %u Gerät(e) gefunden.\n", found);
}

void printStatus() {
    Serial.println("───────────────────────────────────────");
    Serial.println("  read          Beide Sensoren auslesen");
    Serial.println("  stream on|off Kontinuierlich (100 ms)");
    Serial.println("  scan          I2C-Bus scannen");
    Serial.println("  ?             Status");
    Serial.println("───────────────────────────────────────");
    Serial.printf("  VL53L0X (0x29): %s\n", vl53Ok    ? "OK" : "nicht gefunden");
    Serial.printf("  TF-Luna (0x10): %s\n", tfLunaOk  ? "OK" : "nicht gefunden");
    Serial.printf("  Streaming:      %s\n", streaming  ? "EIN" : "AUS");
    Serial.println("───────────────────────────────────────");
}

void handleCommand(const String& raw) {
    String cmd = raw;
    cmd.trim();
    if (cmd.length() == 0) return;

    if (cmd == "read") {
        printReading();
    } else if (cmd == "stream on") {
        streaming = true;
        Serial.println("Streaming EIN.");
    } else if (cmd == "stream off") {
        streaming = false;
        Serial.println("Streaming AUS.");
    } else if (cmd == "scan") {
        scanI2C();
    } else if (cmd == "?") {
        printStatus();
    } else {
        Serial.println("Unbekannt – ? für Hilfe");
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    Wire.begin(PIN_SDA, PIN_SCL);

    // VL53L0X initialisieren
    vl53.setTimeout(500);
    if (vl53.init()) {
        vl53.startContinuous();
        vl53Ok = true;
        Serial.println("VL53L0X: OK");
    } else {
        Serial.println("VL53L0X: nicht gefunden (Adresse 0x29)");
    }

    // TF-Luna: Verbindung prüfen (kurzes Read)
    uint16_t cm, amp;
    tfLunaOk = readTFLuna(cm, amp);
    Serial.printf("TF-Luna: %s\n", tfLunaOk ? "OK" : "nicht gefunden (Adresse 0x10)");

    Serial.println("\nI2C Sensor-Test");
    printStatus();
}

void loop() {
    if (Serial.available()) {
        handleCommand(Serial.readStringUntil('\n'));
    }

    if (streaming && millis() - lastStream >= STREAM_INTERVAL_MS) {
        lastStream = millis();
        printReading();
    }
}
