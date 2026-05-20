#include "drivers/DrvActuator.h"
#include <Arduino.h>

namespace esp_schlitten {

DrvActuator::DrvActuator(uint8_t pinStep, uint8_t pinDir, uint8_t pinEn,
                          uint32_t stepPulseUs, uint32_t dirSetupUs, uint32_t stepDelayUs)
    : _pinStep(pinStep), _pinDir(pinDir), _pinEn(pinEn)
    , _stepPulseUs(stepPulseUs), _dirSetupUs(dirSetupUs)
    , _stepDelayUs(stepDelayUs), _activeStepDelayUs(stepDelayUs)
{}

void DrvActuator::begin() {
    pinMode(_pinStep, OUTPUT);
    pinMode(_pinDir,  OUTPUT);
    pinMode(_pinEn,   OUTPUT);
    digitalWrite(_pinStep, LOW);
    digitalWrite(_pinDir,  LOW);
    digitalWrite(_pinEn,   HIGH);  // deaktiviert
}

void DrvActuator::startHoming(bool forward, uint32_t stepDelayUs) {
    if (_moving) stop();

    _forward           = forward;
    _homingMode        = true;
    _activeStepDelayUs = (stepDelayUs > 0) ? stepDelayUs : _stepDelayUs;

    digitalWrite(_pinEn,  LOW);
    digitalWrite(_pinDir, _forward ? HIGH : LOW);
    delayMicroseconds(_dirSetupUs);

    _moving     = true;
    _nextStepUs = micros();
}

void DrvActuator::move(int32_t steps) {
    move(steps, _stepDelayUs);
}

void DrvActuator::move(int32_t steps, uint32_t stepDelayUs) {
    if (steps == 0) return;
    if (_moving) stop();

    _forward           = steps > 0;
    _stepsLeft         = (uint32_t)abs(steps);
    _activeStepDelayUs = stepDelayUs;

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
    _nextStepUs    = now + _activeStepDelayUs;

    if (!_homingMode && --_stepsLeft == 0) {
        digitalWrite(_pinEn, HIGH);
        _moving = false;
        return true;
    }
    return false;
}

void DrvActuator::stop() {
    _moving     = false;
    _homingMode = false;
    _stepsLeft  = 0;
    digitalWrite(_pinEn, HIGH);
}

}  // namespace esp_schlitten
