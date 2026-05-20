#pragma once

#include <Arduino.h>
#include <Wire.h>
#include <math.h>

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
    void handleOpenDoor(const Command &cmd);
    void handleCloseDoor(const Command &cmd);
    void handlePickup(const Command &cmd);
    void handleDeposit(const Command &cmd);

    // ── Zustandsupdates (während Bewegung) ───────────────────────────────────
    void updateHoming();
    void updateScanning();
    void updateMoving();
    void updateMoveHome();
    void updatePickup();
    void updateDeposit();
    void updateOpenDoor();
    void updateCloseDoor();
    void checkDriverAlarms();

    // ── Zustandsmaschine ─────────────────────────────────────────────────────
    void setState(AppState next);
    void enterError(ErrorCode error);
    void stopAllMotors();

    // ── Status-Reporting ─────────────────────────────────────────────────────
    void           publishStatus();
    MotionSnapshot motionSnapshot() const;
    SensorSnapshot readSensors();
    bool           motorsRunning()  const;

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
    bool     gripperHomed_        = false;
    bool     doorArmHomed_        = false;
    bool     homingZStarted_      = false;

    uint32_t moveHomeStartMs_     = 0;
    uint32_t pendingMoveHomeCmdId_ = 0;

    // Scanning
    uint32_t scanStartMs_         = 0;
    uint8_t  scanPhase_           = 0;  // 0 = Messung Home, 1 = Z fährt auf 200mm, Messung folgt

    // Moving
    uint32_t moveStartMs_         = 0;
    uint32_t pendingMoveCmdId_    = 0;

    // Pickup / Deposit
    uint8_t  actionPhase_         = 0;
    int32_t  gripperSteps_        = 0;
    int32_t  liftOffsetMm_        = 0;
    int32_t  actionBaseZ_         = 0;
    uint32_t pendingActionCmdId_  = 0;
    uint32_t actionStartMs_       = 0;

    // Open / Close Door (Kreisbogen)
    uint8_t  doorPhase_           = 0;
    int      doorArcStep_         = 0;   // aktueller Sub-Schritt (CLOSE_DOOR)
    int      doorArcTotalSteps_   = 0;   // Gesamtzahl Sub-Schritte (CLOSE_DOOR)
    float    doorRadiusMm_        = 0.0f;
    float    doorTargetAngleRad_  = 0.0f;
    int32_t  doorArmExtendSteps_  = 0;   // Grifftiefe in Schritten
    float    doorOrigStartX_      = 0.0f; // X bei Befehlsempfang → Rückfahrtziel
    float    doorOrigStartZ_      = 0.0f; // Z bei Befehlsempfang → Rückfahrtziel
    float    doorArcStartX_       = 0.0f; // X nach Anfahrposition → Bogenmittelpunkt-Referenz
    float    doorHookDropMm_      = 0.0f; // Z-Versatz zum Einhaken
    float    doorXApproachMm_     = 0.0f; // absolute X-Anfahrposition
    float    doorZApproachMm_     = 0.0f; // absolute Z-Anfahrposition
    uint32_t pendingDoorCmdId_    = 0;
    uint32_t doorStartMs_         = 0;

    // Sensoren (gecacht)
    SensorSnapshot cachedSensors_;

    // Streaming / Heartbeat
    bool     streamEnabled_     = false;
    uint32_t lastStreamMs_      = 0;
    uint32_t lastHeartbeatMs_   = 0;
};

}  // namespace esp_schlitten
