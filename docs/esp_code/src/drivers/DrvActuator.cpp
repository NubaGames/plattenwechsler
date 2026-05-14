#include "drivers/DrvActuator.h"
#include <Arduino.h>

namespace esp_schlitten {

DrvActuator::DrvActuator(uint8_t pinStep, uint8_t pinDir, uint8_t pinEn,
                          uint32_t stepPulseUs, uint32_t dirSetupUs, uint32_t stepDelayUs)
    : _pinStep(pinStep), _pinDir(pinDir), _pinEn(pinEn)
    , _stepPulseUs(stepPulseUs), _dirSetupUs(dirSetupUs), _stepDelayUs(stepDelayUs)
{}

void DrvActuator::begin() {
    pinMode(_pinStep, OUTPUT);
    pinMode(_pinDir,  OUTPUT);
    pinMode(_pinEn,   OUTPUT);
    digitalWrite(_pinStep, LOW);
    digitalWrite(_pinDir,  LOW);
    digitalWrite(_pinEn,   HIGH);  // deaktiviert
}

void DrvActuator::move(int32_t steps) {
    if (steps == 0) return;
    if (_moving) stop();

    _forward   = steps > 0;
    _stepsLeft = (uint32_t)abs(steps);

    digitalWrite(_pinEn,  LOW);
    digitalWrite(_pinDir, _forward ? HIGH : LOW);
    delayMicroseconds(_dirSetupUs);

    _moving     = true;
    _nextStepUs = micros();
}

bool DrvActuator::update() {
    if (!_moving) return true;

    const uint32_t now = micros();
    if ((int32_t)(now - _nextStepUs) < 0) return false;

    digitalWrite(_pinStep, HIGH);
    delayMicroseconds(_stepPulseUs);
    digitalWrite(_pinStep, LOW);

    _stepPosition += _forward ? 1 : -1;
    _nextStepUs   += _stepDelayUs;

    if (--_stepsLeft == 0) {
        digitalWrite(_pinEn, HIGH);  // nach Fahrt deaktivieren (spart Wärme)
        _moving = false;
        return true;
    }
    return false;
}

void DrvActuator::stop() {
    _moving    = false;
    _stepsLeft = 0;
    digitalWrite(_pinEn, HIGH);
}

}  // namespace esp_schlitten
