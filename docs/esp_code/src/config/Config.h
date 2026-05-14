#pragma once

// Alle anpassbaren Parameter an einem Ort.
// Achsen-Geometrie, Geschwindigkeiten und Timeouts hier eintragen.

namespace Config {

namespace Serial {
    constexpr uint32_t BAUD_RATE = 115200;
}

// ─── CL42T X-Achse (Schlitten horizontal) ────────────────────────────────────
namespace MotionX {
    constexpr float    STEPS_PER_MM   = 160.0f;  // Schritte/mm (abhängig von Spindel + DIP-Schalter)
    constexpr uint32_t STEPS_PER_REV  = 800;      // Mikroschritte/Umdrehung (DIP am CL42T)
    constexpr uint16_t MAX_RPM        = 300;       // Maximalgeschwindigkeit
    constexpr uint16_t START_RPM      = 20;        // Startgeschwindigkeit (Fuß der Rampe)
    constexpr uint16_t HOMING_RPM     = 30;        // Geschwindigkeit während Referenzfahrt
    constexpr uint32_t ACCEL_STEPS    = 4000;      // Rampenlänge in Schritten
    constexpr uint32_t STEP_US        = 3;         // STEP-Pulsbreite µs (CL42T min. 2,5 µs)
    constexpr uint32_t DIR_US         = 5;         // DIR-Setup vor erstem STEP µs
    constexpr bool     HOMING_FORWARD = false;     // Richtung Referenzposition (false = rückwärts)
}

// ─── CL42T Z-Achse (Schlitten vertikal) ──────────────────────────────────────
namespace MotionZ {
    constexpr float    STEPS_PER_MM   = 160.0f;
    constexpr uint32_t STEPS_PER_REV  = 800;
    constexpr uint16_t MAX_RPM        = 300;
    constexpr uint16_t START_RPM      = 20;
    constexpr uint16_t HOMING_RPM     = 30;
    constexpr uint32_t ACCEL_STEPS    = 4000;
    constexpr uint32_t STEP_US        = 3;
    constexpr uint32_t DIR_US         = 5;
    constexpr bool     HOMING_FORWARD = false;
    constexpr float    MAX_TRAVEL_MM   = 500.0f;   // maximale Z-Verfahrlänge
    constexpr float    SCAN_Z_PROBE_MM = 200.0f;   // Z-Position der zweiten TF-Luna-Messung beim Scan
}

// ─── DRV8825 Greifer ──────────────────────────────────────────────────────────
namespace Gripper {
    constexpr uint32_t STEPS_PER_REV = 200;       // Vollschritte/Umdrehung (DRV8825 ohne Mikroschritt)
    constexpr uint32_t TRAVEL_STEPS  = 800;        // Schritte für vollständige Ein-/Ausfahrt
    constexpr uint32_t STEP_DELAY_US = 2000;       // Zeit zwischen zwei Schritten µs
    constexpr uint32_t STEP_US       = 2;          // STEP-Pulsbreite µs
    constexpr uint32_t DIR_US        = 1;          // DIR-Setup µs
}

// ─── DRV8825 Türarm ───────────────────────────────────────────────────────────
namespace DoorArm {
    constexpr uint32_t STEPS_PER_REV = 200;
    constexpr uint32_t TRAVEL_STEPS  = 800;
    constexpr uint32_t STEP_DELAY_US = 2000;
    constexpr uint32_t STEP_US       = 2;
    constexpr uint32_t DIR_US        = 1;
}

// ─── Timing ───────────────────────────────────────────────────────────────────
namespace Timing {
    constexpr uint32_t HEARTBEAT_MS    = 1000;
    constexpr uint32_t STREAM_MS       = 100;
    constexpr uint32_t MOVE_TIMEOUT_MS = 100000;
    constexpr uint32_t HOME_TIMEOUT_MS = 35000;
    constexpr uint32_t SENSOR_POLL_MS  = 50;      // Hindernissensor-Abfrageintervall während Fahrt
}

// ─── Sensoren ─────────────────────────────────────────────────────────────────
namespace Sensor {
    constexpr uint16_t DOOR_OPEN_MM          = 200;  // VL53L0X: unter diesem Wert = Tür offen
    constexpr uint16_t OBSTACLE_STOP_MM      = 60;   // TF-Luna: Stopp-Abstand (Normalbetrieb)
    constexpr uint16_t OBSTACLE_WARN_MM      = 120;  // TF-Luna: Warnabstand
    constexpr uint16_t SCAN_OBSTACLE_STOP_MM = 1000; // TF-Luna: Stopp-Abstand während Scanfahrt
    constexpr uint16_t TFLUNA_AMP_MIN        = 100;  // Mindestsignalstärke TF-Luna
    constexpr uint8_t  TFLUNA_ADDR           = 0x10;
    constexpr uint8_t  MAX_OBSTACLE_FAULTS   = 3;    // aufeinanderfolgende I2C-Fehler bis Notstopp
}

}  // namespace Config
