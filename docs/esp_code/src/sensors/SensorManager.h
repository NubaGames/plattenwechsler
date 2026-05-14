#pragma once
#include <Arduino.h>
#include <VL53L0X.h>

// Wrapper für VL53L0X (Türsensor) und TF-Luna (Hindernissensor, I2C).
// Wire.begin() muss vor begin() aufgerufen worden sein.

namespace esp_schlitten {

class SensorManager {
public:
    void begin();

    // VL53L0X: Türabstand in mm. false = Sensor nicht verfügbar oder Timeout.
    bool readDoorMm(uint16_t &mm);

    // TF-Luna: Hindernis-Distanz in cm und Signalstärke.
    // false = Sensor nicht verfügbar oder Lesefehler.
    bool readObstacleCm(uint16_t &distCm, uint16_t &amplitude);

    bool isDoorSensorOk()      const { return _vl53Ok; }
    bool isObstacleSensorOk()  const { return _tfLunaOk; }

private:
    VL53L0X _vl53;
    bool    _vl53Ok    = false;
    bool    _tfLunaOk  = false;
};

}  // namespace esp_schlitten
