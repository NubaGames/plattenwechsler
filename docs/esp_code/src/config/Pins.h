#pragma once
#include <stdint.h>

// Pinbelegung ESP32 – aus full_system Test übernommen.

namespace Pins {

// I2C (VL53L0X Türsensor + TF-Luna Hindernissensor)
constexpr uint8_t SDA = 21;
constexpr uint8_t SCL = 22;

// CL42T – X-Achse (Schlitten horizontal)
constexpr uint8_t X_STEP = 27;
constexpr uint8_t X_DIR  = 14;
constexpr uint8_t X_EN   = 12;
constexpr uint8_t X_ALM  = 13;  // Alarm: active-LOW bei Treiberfehler

// CL42T – Z-Achse (Schlitten vertikal)
constexpr uint8_t Z_STEP = 32;
constexpr uint8_t Z_DIR  = 33;
constexpr uint8_t Z_EN   = 25;
constexpr uint8_t Z_ALM  = 26;

// DRV8825 – Greifer
constexpr uint8_t GRIPPER_STEP = 23;
constexpr uint8_t GRIPPER_DIR  = 19;
constexpr uint8_t GRIPPER_EN   = 18;

// DRV8825 – Türarm
constexpr uint8_t DOOR_STEP = 17;
constexpr uint8_t DOOR_DIR  = 16;
constexpr uint8_t DOOR_EN   = 15;

}  // namespace Pins
