#pragma once

#include <Arduino.h>
#include <Wire.h>

#include "comm/CommandInterface.h"
#include "config/Config.h"
#include "config/Pins.h"
#include "core/Types.h"
#include "drivers/ClMotor.h"
#include "drivers/DrvActuator.h"
#include "sensors/SensorManager.h"
#include "status/StatusReporter.h"

namespace esp_schlitten {

class AppController {
public:
    AppController();
    void begin();
    void update();

private:
    // ── Kommandoverarbeitung ─────────────────────────────────────────────────
    void processCommands();
    void dispatchCommand(const Command &cmd);
    void handlePing(const Command &cmd);
    void handleStatus(const Command &cmd);
    void handleStop(const Command &cmd);
    void handleHome(const Command &cmd);
    void handleHomeSwitchHit(const Command &cmd);
    void handleMoveTo(const Command &cmd);
    void handleMoveHome(const Command &cmd);
    void handleResetError(const Command &cmd);
    void handleSetClamp(const Command &cmd);
    void handleSetDoorArm(const Command &cmd);

    // ── Zustandsupdates (während Bewegung) ───────────────────────────────────
    void updateHoming();
    void updateScanning();
    void updateMoving();
    void updateMoveHome();
    void checkDriverAlarms();

    // ── Zustandsmaschine ─────────────────────────────────────────────────────
    void setState(AppState next);
    void enterError(ErrorCode error);
    void stopAllMotors();

    // ── Status-Reporting ─────────────────────────────────────────────────────
    void           publishStatus();
    MotionSnapshot motionSnapshot() const;
    SensorSnapshot readSensors();

    // ── Hardware ─────────────────────────────────────────────────────────────
    CommandInterface comm_;
    StatusReporter   reporter_;
    SensorManager    sensors_;

    ClMotor axisX_;
    ClMotor axisZ_;
    DrvActuator gripper_;
    DrvActuator doorArm_;

    // ── Zustand ──────────────────────────────────────────────────────────────
    AppState  state_      = AppState::NotReferenced;
    ErrorCode error_      = ErrorCode::None;
    bool      referenced_ = false;
    Position  current_;
    Position  target_;

    // Homing / MoveHome
    uint32_t homingStartMs_       = 0;
    uint32_t pendingHomeCmdId_    = 0;
    bool     xHomed_              = false;
    bool     zHomed_              = false;
    bool     homingZStarted_      = false;

    uint32_t moveHomeStartMs_     = 0;
    uint32_t pendingMoveHomeCmdId_ = 0;

    // Scanning
    uint32_t scanStartMs_         = 0;
    uint8_t  scanPhase_           = 0;  // 0 = Messung Home, 1 = Z fährt auf 200mm, Messung folgt

    // Moving
    uint32_t moveStartMs_         = 0;
    uint32_t pendingMoveCmdId_    = 0;

    // Sensoren (gecacht)
    SensorSnapshot cachedSensors_;

    // Streaming / Heartbeat
    bool     streamEnabled_     = false;
    uint32_t lastStreamMs_      = 0;
    uint32_t lastHeartbeatMs_   = 0;
};

}  // namespace esp_schlitten
