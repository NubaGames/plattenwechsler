#pragma once
#include <Arduino.h>

// Non-blocking DRV8825 Stepper Actuator Driver.
// Ansteuerung in Schritten; keine Positionsregelung.
// update() muss jeden Loop-Durchlauf aufgerufen werden.

namespace esp_schlitten {

class DrvActuator {
public:
    DrvActuator(uint8_t pinStep, uint8_t pinDir, uint8_t pinEn,
                uint32_t stepPulseUs, uint32_t dirSetupUs, uint32_t stepDelayUs);

    void begin();

    // Bewegung starten. steps > 0 = vorwärts, steps < 0 = rückwärts.
    void move(int32_t steps);

    // Einen Schritt ausführen falls fällig. true = Bewegung abgeschlossen.
    bool update();

    void stop();
    bool    isMoving()      const { return _moving; }
    int32_t stepPosition()  const { return _stepPosition; }
    void    resetPosition()       { _stepPosition = 0; }

private:
    uint8_t  _pinStep, _pinDir, _pinEn;
    uint32_t _stepPulseUs, _dirSetupUs, _stepDelayUs;

    int32_t  _stepPosition = 0;
    uint32_t _stepsLeft    = 0;
    bool     _forward      = true;
    bool     _moving       = false;
    uint32_t _nextStepUs   = 0;
};

}  // namespace esp_schlitten
