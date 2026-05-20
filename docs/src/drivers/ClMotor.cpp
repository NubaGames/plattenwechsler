#include "drivers/ClMotor.h"
#include "config/Config.h"
#include <Arduino.h>

namespace esp_schlitten {

ClMotor::ClMotor(uint8_t pinStep, uint8_t pinDir, uint8_t pinEn, uint8_t pinAlm,
                 float stepsPerMm, uint32_t stepsPerRev,
                 uint16_t maxRpm, uint16_t startRpm, uint32_t accelSteps,
                 uint32_t stepPulseUs, uint32_t dirSetupUs)
    : _pinStep(pinStep), _pinDir(pinDir), _pinEn(pinEn), _pinAlm(pinAlm)
    , _stepsPerMm(stepsPerMm), _stepsPerRev(stepsPerRev)
    , _stepPulseUs(stepPulseUs), _dirSetupUs(dirSetupUs)
    , _dfltAccelSteps(accelSteps)
{
    static_assert(Config::MotionX::MAX_RPM   > 0, "MAX_RPM muss > 0 sein");
    static_assert(Config::MotionX::START_RPM > 0, "START_RPM muss > 0 sein");
    static_assert(Config::MotionZ::MAX_RPM   > 0, "MAX_RPM muss > 0 sein");
    static_assert(Config::MotionZ::START_RPM > 0, "START_RPM muss > 0 sein");

    _dfltHalfUsCruise = rpmToHalfUs(maxRpm);
    _dfltHalfUsStart  = rpmToHalfUs(startRpm);
}

uint32_t ClMotor::rpmToHalfUs(uint16_t rpm) const {
    if (rpm == 0) return 0xFFFFFFFFUL;
    return 30000000UL / ((uint32_t)rpm * _stepsPerRev);
}

void ClMotor::begin() {
    pinMode(_pinStep, OUTPUT);
    pinMode(_pinDir,  OUTPUT);
    pinMode(_pinEn,   OUTPUT);
    pinMode(_pinAlm,  INPUT_PULLUP);
    digitalWrite(_pinStep, LOW);
    digitalWrite(_pinDir,  LOW);
    digitalWrite(_pinEn,   HIGH);  // active-low: HIGH = deaktiviert
}

void ClMotor::enable(bool on) {
    digitalWrite(_pinEn, on ? LOW : HIGH);
}

bool ClMotor::moveTo(float targetMm) {
    return moveTo(targetMm, 0);
}

bool ClMotor::moveTo(float targetMm, uint16_t maxRpm) {
    if (_moving) return false;

    int32_t targetSteps = (int32_t)(targetMm * _stepsPerMm + (targetMm >= 0 ? 0.5f : -0.5f));
    int32_t delta       = targetSteps - _positionSteps;
    if (delta == 0) return true;

    _totalSteps    = (uint32_t)abs(delta);
    _forward       = delta > 0;
    _homingMode    = false;
    _stepsDone     = 0;
    _halfUsCruise  = (maxRpm > 0) ? rpmToHalfUs(maxRpm) : _dfltHalfUsCruise;
    _halfUsStart   = _dfltHalfUsStart;
    _accelSteps    = _dfltAccelSteps;

    enable(true);
    digitalWrite(_pinDir, _forward ? HIGH : LOW);
    delayMicroseconds(_dirSetupUs);

    _moving     = true;
    _nextStepUs = micros();
    return true;
}

void ClMotor::startHoming(bool forward, uint16_t homingRpm) {
    if (_moving) stop();

    _forward      = forward;
    _homingMode   = true;
    _totalSteps   = 0xFFFFFFFFUL;
    _stepsDone    = 0;
    _halfUsCruise = rpmToHalfUs(homingRpm);
    _halfUsStart  = _halfUsCruise;
    _accelSteps   = 0;

    enable(true);
    digitalWrite(_pinDir, _forward ? HIGH : LOW);
    delayMicroseconds(_dirSetupUs);

    _moving     = true;
    _nextStepUs = micros();
}

bool ClMotor::update() {
    if (!_moving) return true;

    const uint32_t now = micros();
    if ((int32_t)(now - _nextStepUs) < 0) return false;

    // ALM-Check: Alarm → sofort stoppen, Caller prüft alarmActive()
    if (alarmActive()) {
        stop();
        return true;
    }

    const uint32_t d = trapezDelay();
    digitalWrite(_pinStep, HIGH);
    delayMicroseconds(_stepPulseUs);
    digitalWrite(_pinStep, LOW);

    _positionSteps += _forward ? 1 : -1;
    _stepsDone++;
    _nextStepUs = now + 2 * d;

    if (!_homingMode && _stepsDone >= _totalSteps) {
        _moving = false;
        return true;
    }
    return false;
}

void ClMotor::stop() {
    _moving     = false;
    _homingMode = false;
}

void ClMotor::setPositionMm(float mm) {
    _positionSteps = (int32_t)(mm * _stepsPerMm + (mm >= 0 ? 0.5f : -0.5f));
}

float ClMotor::positionMm() const {
    return _positionSteps / _stepsPerMm;
}

bool ClMotor::alarmActive() const {
    return digitalRead(_pinAlm) == LOW;
}

uint32_t ClMotor::trapezDelay() const {
    if (_homingMode || _accelSteps == 0) return _halfUsCruise;

    const uint32_t ramp      = min(_accelSteps, _totalSteps / 2);
    const uint32_t stepsLeft = _totalSteps - _stepsDone;

    float t;
    if      (_stepsDone < ramp)  t = (float)_stepsDone / ramp;
    else if (stepsLeft  <= ramp) t = (float)stepsLeft   / ramp;
    else return _halfUsCruise;

    const float inv = (1.0f / _halfUsStart) + t * (1.0f / _halfUsCruise - 1.0f / _halfUsStart);
    return (uint32_t)(1.0f / inv);
}

}  // namespace esp_schlitten
