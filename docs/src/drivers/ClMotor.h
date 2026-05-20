#pragma once
#include <Arduino.h>

// Non-blocking CL42T Closed-Loop Stepper Driver.
// Positionsangabe in mm; Umrechnung in Schritte intern.
// update() muss jeden Loop-Durchlauf aufgerufen werden.

namespace esp_schlitten {

class ClMotor {
public:
    ClMotor(uint8_t pinStep, uint8_t pinDir, uint8_t pinEn, uint8_t pinAlm,
            float stepsPerMm, uint32_t stepsPerRev,
            uint16_t maxRpm, uint16_t startRpm, uint32_t accelSteps,
            uint32_t stepPulseUs, uint32_t dirSetupUs);

    void begin();
    void enable(bool on);

    // Absolute Zielposition in mm anfahren. false = Motor bereits in Bewegung.
    bool moveTo(float targetMm);
    // Wie moveTo(), aber mit explizitem maxRpm (überschreibt Konstruktorwert für diese Bewegung).
    bool moveTo(float targetMm, uint16_t maxRpm);

    // Homing starten: Motor fährt mit homingRpm in 'forward'-Richtung bis stop().
    void startHoming(bool forward, uint16_t homingRpm);

    // Einen Schritt ausführen falls fällig. true = Bewegung abgeschlossen.
    // Muss jeden Loop-Durchlauf aufgerufen werden.
    bool update();

    void  stop();
    void  setPositionMm(float mm);   // nach Homing: Position auf Sollwert setzen

    float positionMm()  const;
    bool  isMoving()    const { return _moving; }
    bool  alarmActive() const;       // CL42T ALM-Pin: LOW = Treiberfehler

private:
    uint32_t trapezDelay() const;
    uint32_t rpmToHalfUs(uint16_t rpm) const;

    // Konfiguration (unveränderlich)
    uint8_t  _pinStep, _pinDir, _pinEn, _pinAlm;
    float    _stepsPerMm;
    uint32_t _stepsPerRev;
    uint32_t _stepPulseUs, _dirSetupUs;
    uint32_t _dfltHalfUsCruise, _dfltHalfUsStart, _dfltAccelSteps;

    // Aktive Bewegungsparameter (werden pro Bewegung gesetzt)
    uint32_t _halfUsCruise = 0;
    uint32_t _halfUsStart  = 0;
    uint32_t _accelSteps   = 0;

    // Bewegungszustand
    int32_t  _positionSteps = 0;
    uint32_t _totalSteps    = 0;
    uint32_t _stepsDone     = 0;
    bool     _forward       = true;
    bool     _moving        = false;
    bool     _homingMode    = false;
    uint32_t _nextStepUs    = 0;
};

}  // namespace esp_schlitten
