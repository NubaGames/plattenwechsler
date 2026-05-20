#include "sensors/SensorManager.h"
#include "config/Config.h"
#include "config/Pins.h"
#include <Wire.h>

namespace esp_schlitten {

void SensorManager::begin() {
    _pinGripperHome = Pins::GRIPPER_HOME_SW;
    _pinDoorArmHome = Pins::DOOR_ARM_HOME_SW;
    _pinPlateSensor = Pins::PLATE_SENSOR;
    pinMode(_pinGripperHome, INPUT);
    pinMode(_pinDoorArmHome, INPUT);
    pinMode(_pinPlateSensor, INPUT);
    // VL53L0X init
    _vl53.setTimeout(500);
    if (_vl53.init()) {
        _vl53.startContinuous();
        _vl53Ok = true;
    }

    // TF-Luna: 500 ms Bootzeit abwarten, dann Erreichbarkeit prüfen
    delay(500);
    Wire.beginTransmission(Config::Sensor::TFLUNA_ADDR);
    _tfLunaOk = (Wire.endTransmission() == 0);
}

bool SensorManager::readDoorMm(uint16_t &mm) {
    if (!_vl53Ok) return false;

    mm = _vl53.readRangeContinuousMillimeters();
    if (_vl53.timeoutOccurred()) return false;
    return true;
}

bool SensorManager::readObstacleCm(uint16_t &distCm, uint16_t &amplitude) {
    if (!_tfLunaOk) {
        // Nachträgliche Erkennung versuchen
        Wire.beginTransmission(Config::Sensor::TFLUNA_ADDR);
        if (Wire.endTransmission() == 0) _tfLunaOk = true;
        else return false;
    }

    Wire.beginTransmission(Config::Sensor::TFLUNA_ADDR);
    Wire.write(0x00);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom((uint8_t)Config::Sensor::TFLUNA_ADDR, (uint8_t)6) < 6) return false;

    uint8_t b[6];
    for (uint8_t i = 0; i < 6; i++) b[i] = Wire.read();
    distCm    = (uint16_t)b[0] | ((uint16_t)b[1] << 8);
    amplitude = (uint16_t)b[2] | ((uint16_t)b[3] << 8);
    return true;
}

}  // namespace esp_schlitten
