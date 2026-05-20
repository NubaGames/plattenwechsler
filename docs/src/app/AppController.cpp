#include "app/AppController.h"

namespace esp_schlitten {

AppController::AppController()
    : axisX_(Pins::X_STEP, Pins::X_DIR, Pins::X_EN, Pins::X_ALM,
             Config::MotionX::STEPS_PER_MM, Config::MotionX::STEPS_PER_REV,
             Config::MotionX::MAX_RPM, Config::MotionX::START_RPM, Config::MotionX::ACCEL_STEPS,
             Config::MotionX::STEP_US, Config::MotionX::DIR_US)
    , axisZ_(Pins::Z_STEP, Pins::Z_DIR, Pins::Z_EN, Pins::Z_ALM,
             Config::MotionZ::STEPS_PER_MM, Config::MotionZ::STEPS_PER_REV,
             Config::MotionZ::MAX_RPM, Config::MotionZ::START_RPM, Config::MotionZ::ACCEL_STEPS,
             Config::MotionZ::STEP_US, Config::MotionZ::DIR_US)
    , gripper_(Pins::GRIPPER_STEP, Pins::GRIPPER_DIR, Pins::GRIPPER_EN,
               Config::Gripper::STEP_US, Config::Gripper::DIR_US, Config::Gripper::STEP_DELAY_US)
    , doorArm_(Pins::DOOR_STEP, Pins::DOOR_DIR, Pins::DOOR_EN,
               Config::DoorArm::STEP_US, Config::DoorArm::DIR_US, Config::DoorArm::STEP_DELAY_US)
{}

void AppController::begin() {
    Serial.begin(Config::Serial::BAUD_RATE);

    Wire.begin(Pins::SDA, Pins::SCL);
    sensors_.begin();

    axisX_.begin();
    axisZ_.begin();
    gripper_.begin();
    doorArm_.begin();

    comm_.begin(Serial);
    reporter_.begin(comm_);

    setState(AppState::NotReferenced);
    publishStatus();
}

void AppController::update() {
    const uint32_t now = millis();

    comm_.poll();
    processCommands();

    switch (state_) {
        case AppState::BusyHoming:   updateHoming();   break;
        case AppState::BusyScanning: updateScanning(); break;
        case AppState::BusyMoving:   updateMoving();   break;
        case AppState::BusyMoveHome: updateMoveHome(); break;
        case AppState::BusyPickup:    updatePickup();    break;
        case AppState::BusyDeposit:   updateDeposit();   break;
        case AppState::BusyOpenDoor:  updateOpenDoor();  break;
        case AppState::BusyCloseDoor: updateCloseDoor(); break;
        default: break;
    }

    gripper_.update();
    doorArm_.update();

    if (streamEnabled_ && (now - lastStreamMs_) >= Config::Timing::STREAM_MS) {
        lastStreamMs_ = now;
        publishStatus();
    }

    if ((now - lastHeartbeatMs_) >= Config::Timing::HEARTBEAT_MS) {
        lastHeartbeatMs_ = now;
        reporter_.sendHeartbeat(state_, motionSnapshot());
    }
}

// ─── Kommandoverarbeitung ─────────────────────────────────────────────────────

void AppController::processCommands() {
    while (comm_.hasPendingCommand()) {
        dispatchCommand(comm_.popCommand());
    }
}

void AppController::dispatchCommand(const Command &cmd) {
    if (!cmd.valid) {
        comm_.sendResponseError(cmd.id, cmd.parseError);
        return;
    }

    switch (cmd.type) {
        case CommandType::Ping:          handlePing(cmd);          return;
        case CommandType::Status:        handleStatus(cmd);        return;
        case CommandType::StreamOn:
            streamEnabled_ = true;
            lastStreamMs_  = millis();
            comm_.sendAck(cmd.id);
            reporter_.sendOk(cmd.id, "STREAM_ON", motionSnapshot());
            return;
        case CommandType::StreamOff:
            streamEnabled_ = false;
            comm_.sendAck(cmd.id);
            reporter_.sendOk(cmd.id, "STREAM_OFF", motionSnapshot());
            return;
        case CommandType::Stop:          handleStop(cmd);          return;
        case CommandType::Home:          handleHome(cmd);          return;
        case CommandType::HomeSwitchHit: handleHomeSwitchHit(cmd); return;
        case CommandType::MoveTo:        handleMoveTo(cmd);        return;
        case CommandType::MoveHome:      handleMoveHome(cmd);      return;
        case CommandType::ResetError:    handleResetError(cmd);    return;
        case CommandType::OpenDoor:      handleOpenDoor(cmd);      return;
        case CommandType::CloseDoor:     handleCloseDoor(cmd);     return;
        case CommandType::Pickup:        handlePickup(cmd);        return;
        case CommandType::Deposit:       handleDeposit(cmd);       return;
        default:
            comm_.sendResponseError(cmd.id, ErrorCode::InvalidCommand);
    }
}

void AppController::handlePing(const Command &cmd) {
    comm_.sendAck(cmd.id);
    reporter_.sendOk(cmd.id, "PONG", motionSnapshot());
}

void AppController::handleStatus(const Command &cmd) {
    comm_.sendAck(cmd.id);
    publishStatus();
}

void AppController::handleStop(const Command &cmd) {
    comm_.sendAck(cmd.id);
    if (state_ != AppState::Error) {
        stopAllMotors();
        error_ = ErrorCode::None;
        setState(AppState::Stopped);
        reporter_.sendOk(cmd.id, "STOPPED", motionSnapshot());
    }
}

void AppController::handleHome(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming    || state_ == AppState::BusyMoving   ||
        state_ == AppState::BusyScanning  || state_ == AppState::BusyMoveHome ||
        state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit  ||
        state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }

    comm_.sendAck(cmd.id);

    xHomed_           = false;
    zHomed_           = false;
    gripperHomed_     = false;
    doorArmHomed_     = false;
    homingZStarted_   = false;
    pendingHomeCmdId_ = cmd.id;
    homingStartMs_    = millis();
    referenced_       = false;
    error_            = ErrorCode::None;

    axisX_.startHoming(Config::MotionX::HOMING_FORWARD, Config::MotionX::HOMING_RPM);
    gripper_.startHoming(false, Config::Gripper::HOMING_STEP_DELAY_US);
    doorArm_.startHoming(false, Config::DoorArm::HOMING_STEP_DELAY_US);

    setState(AppState::BusyHoming);
}

void AppController::handleHomeSwitchHit(const Command &cmd) {
    if (state_ != AppState::BusyHoming && state_ != AppState::BusyMoveHome) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    comm_.sendAck(cmd.id);

    if (cmd.axis == HomingAxis::X && !xHomed_) {
        axisX_.stop();
        axisX_.setPositionMm(0.0f);
        xHomed_ = true;
    } else if (cmd.axis == HomingAxis::Z && !zHomed_) {
        axisZ_.stop();
        axisZ_.setPositionMm(0.0f);
        zHomed_ = true;
    }
}

void AppController::handleMoveTo(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming    || state_ == AppState::BusyMoving   ||
        state_ == AppState::BusyScanning  || state_ == AppState::BusyMoveHome ||
        state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit  ||
        state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    if (!referenced_) {
        comm_.sendResponseError(cmd.id, ErrorCode::NotReferenced);
        return;
    }

    target_           = cmd.target;
    pendingMoveCmdId_ = cmd.id;
    error_            = ErrorCode::None;

    comm_.sendAck(cmd.id);

    if (current_.x_mm == 0 && current_.z_mm == 0) {
        scanStartMs_ = millis();
        scanPhase_   = 0;
        setState(AppState::BusyScanning);
    } else {
        moveStartMs_ = millis();
        axisX_.moveTo((float)target_.x_mm);
        axisZ_.moveTo((float)target_.z_mm);
        setState(AppState::BusyMoving);
    }
}

void AppController::handleMoveHome(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming    || state_ == AppState::BusyMoving   ||
        state_ == AppState::BusyScanning  || state_ == AppState::BusyMoveHome ||
        state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit  ||
        state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    if (!referenced_) {
        comm_.sendResponseError(cmd.id, ErrorCode::NotReferenced);
        return;
    }

    comm_.sendAck(cmd.id);

    xHomed_              = false;
    zHomed_              = false;
    homingZStarted_      = false;
    pendingMoveHomeCmdId_ = cmd.id;
    moveHomeStartMs_     = millis();
    error_               = ErrorCode::None;

    axisX_.startHoming(Config::MotionX::HOMING_FORWARD, Config::MotionX::HOMING_RPM);
    setState(AppState::BusyMoveHome);
}

void AppController::handleResetError(const Command &cmd) {
    if (state_ != AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    error_      = ErrorCode::None;
    referenced_ = false;
    current_    = Position{};
    target_     = Position{};
    comm_.sendAck(cmd.id);
    setState(AppState::NotReferenced);
    reporter_.sendOk(cmd.id, "ERROR_RESET", motionSnapshot());
}

void AppController::handleOpenDoor(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming    || state_ == AppState::BusyMoving   ||
        state_ == AppState::BusyScanning  || state_ == AppState::BusyMoveHome ||
        state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit  ||
        state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    if (!referenced_) {
        comm_.sendResponseError(cmd.id, ErrorCode::NotReferenced);
        return;
    }

    comm_.sendAck(cmd.id);

    doorOrigStartX_      = axisX_.positionMm();
    doorOrigStartZ_      = axisZ_.positionMm();
    doorHookDropMm_      = (float)cmd.hookDropMm;
    doorXApproachMm_     = (float)cmd.xApproachMm;
    doorZApproachMm_     = (float)cmd.zApproachMm;
    doorArmExtendSteps_  = (int32_t)(cmd.armExtendMm * Config::DoorArm::STEPS_PER_MM);
    doorRadiusMm_        = (float)cmd.radiusMm;
    doorTargetAngleRad_  = (float)cmd.openAngleDeg * (float)M_PI / 180.0f;
    doorArcTotalSteps_   = max(cmd.openAngleDeg * (int32_t)Config::DoorArm::ARC_STEPS_PER_DEG, 4);
    doorPhase_           = 0;
    pendingDoorCmdId_    = cmd.id;
    doorStartMs_         = millis();

    // Phase 0: XZ-Anfahrposition ansteuern
    axisX_.moveTo(doorXApproachMm_);
    axisZ_.moveTo(doorZApproachMm_);
    setState(AppState::BusyOpenDoor);
}

void AppController::handleCloseDoor(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming    || state_ == AppState::BusyMoving   ||
        state_ == AppState::BusyScanning  || state_ == AppState::BusyMoveHome ||
        state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit  ||
        state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    if (!referenced_) {
        comm_.sendResponseError(cmd.id, ErrorCode::NotReferenced);
        return;
    }

    comm_.sendAck(cmd.id);

    doorOrigStartX_      = axisX_.positionMm();
    doorOrigStartZ_      = axisZ_.positionMm();
    doorHookDropMm_      = (float)cmd.hookDropMm;
    doorXApproachMm_     = (float)cmd.xApproachMm;
    doorZApproachMm_     = (float)cmd.zApproachMm;
    doorArmExtendSteps_  = (int32_t)(cmd.armExtendMm * Config::DoorArm::STEPS_PER_MM);
    doorRadiusMm_        = (float)cmd.radiusMm;
    doorTargetAngleRad_  = (float)cmd.openAngleDeg * (float)M_PI / 180.0f;
    doorArcTotalSteps_   = max(cmd.openAngleDeg * (int32_t)Config::DoorArm::ARC_STEPS_PER_DEG, 4);
    doorPhase_           = 0;
    pendingDoorCmdId_    = cmd.id;
    doorStartMs_         = millis();

    // Phase 0: XZ-Anfahrposition ansteuern
    axisX_.moveTo(doorXApproachMm_);
    axisZ_.moveTo(doorZApproachMm_);
    setState(AppState::BusyCloseDoor);
}

void AppController::handlePickup(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming    || state_ == AppState::BusyMoving   ||
        state_ == AppState::BusyScanning  || state_ == AppState::BusyMoveHome ||
        state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit  ||
        state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    if (!referenced_) {
        comm_.sendResponseError(cmd.id, ErrorCode::NotReferenced);
        return;
    }

    uint16_t doorMm = 0;
    if (!sensors_.readDoorMm(doorMm) || doorMm <= Config::Sensor::DOOR_ENTRY_CLEARANCE_MM) {
        comm_.sendResponseError(cmd.id, ErrorCode::DoorNotOpen);
        return;
    }

    comm_.sendAck(cmd.id);

    gripperSteps_       = (int32_t)(cmd.gripperDepthMm * Config::Gripper::STEPS_PER_MM);
    liftOffsetMm_       = cmd.liftOffsetMm;
    actionBaseZ_        = (int32_t)axisZ_.positionMm();
    pendingActionCmdId_ = cmd.id;
    actionStartMs_      = millis();
    actionPhase_        = 0;

    gripper_.move(gripperSteps_);
    setState(AppState::BusyPickup);
}

void AppController::handleDeposit(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming    || state_ == AppState::BusyMoving   ||
        state_ == AppState::BusyScanning  || state_ == AppState::BusyMoveHome ||
        state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit  ||
        state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    if (!referenced_) {
        comm_.sendResponseError(cmd.id, ErrorCode::NotReferenced);
        return;
    }

    uint16_t doorMm = 0;
    if (!sensors_.readDoorMm(doorMm) || doorMm <= Config::Sensor::DOOR_ENTRY_CLEARANCE_MM) {
        comm_.sendResponseError(cmd.id, ErrorCode::DoorNotOpen);
        return;
    }

    comm_.sendAck(cmd.id);

    gripperSteps_       = (int32_t)(cmd.gripperDepthMm * Config::Gripper::STEPS_PER_MM);
    liftOffsetMm_       = cmd.liftOffsetMm;
    actionBaseZ_        = (int32_t)axisZ_.positionMm();
    pendingActionCmdId_ = cmd.id;
    actionStartMs_      = millis();
    actionPhase_        = 0;

    axisZ_.moveTo((float)(actionBaseZ_ + liftOffsetMm_));
    setState(AppState::BusyDeposit);
}

// ─── Zustandsupdates ─────────────────────────────────────────────────────────

void AppController::updateHoming() {
    // X- und Z-Achse sequenziell (X zuerst, dann Z)
    if (!xHomed_) {
        axisX_.update();
    } else if (!homingZStarted_) {
        homingZStarted_ = true;
        if (!zHomed_) {
            axisZ_.startHoming(Config::MotionZ::HOMING_FORWARD, Config::MotionZ::HOMING_RPM);
        }
    } else {
        axisZ_.update();
    }

    // Greifer und Türarm: update() läuft im Haupt-Loop, hier nur Endschalter auswerten
    if (!gripperHomed_ && sensors_.isGripperHome()) {
        gripper_.stop();
        gripper_.resetPosition();
        gripperHomed_ = true;
    }
    if (!doorArmHomed_ && sensors_.isDoorArmHome()) {
        doorArm_.stop();
        doorArm_.resetPosition();
        doorArmHomed_ = true;
    }

    checkDriverAlarms();
    if (state_ != AppState::BusyHoming) return;

    if ((millis() - homingStartMs_) > Config::Timing::HOME_TIMEOUT_MS) {
        axisX_.stop();
        axisZ_.stop();
        gripper_.stop();
        doorArm_.stop();
        enterError(ErrorCode::HomingTimeout);
        return;
    }

    if (xHomed_ && zHomed_ && gripperHomed_ && doorArmHomed_) {
        axisZ_.stop();
        current_    = Position{};
        target_     = Position{};
        referenced_ = true;
        reporter_.sendOk(pendingHomeCmdId_, "HOME_DONE", motionSnapshot());
        setState(AppState::Ready);
    }
}

void AppController::updateScanning() {
    const bool zDone = axisZ_.update();

    checkDriverAlarms();
    if (state_ != AppState::BusyScanning) return;

    if ((millis() - scanStartMs_) > Config::Timing::MOVE_TIMEOUT_MS) {
        axisZ_.stop();
        enterError(ErrorCode::MoveTimeout);
        return;
    }

    if (scanPhase_ == 0) {
        // Messung in Home-Position
        uint16_t cm, amp;
        if (!sensors_.isObstacleSensorOk() || !sensors_.readObstacleCm(cm, amp)) {
            enterError(ErrorCode::SensorFaultObstacle);
            return;
        }
        if ((uint32_t)cm * 10 < Config::Sensor::SCAN_OBSTACLE_STOP_MM) {
            enterError(ErrorCode::ObstacleDetected);
            return;
        }
        axisZ_.moveTo(Config::MotionZ::SCAN_Z_PROBE_MM);
        scanPhase_ = 1;
        return;
    }

    if (!zDone) return;

    // Phase 1 abgeschlossen: Z auf 200 mm – zweite Messung
    uint16_t cm, amp;
    if (!sensors_.isObstacleSensorOk() || !sensors_.readObstacleCm(cm, amp)) {
        enterError(ErrorCode::SensorFaultObstacle);
        return;
    }
    if ((uint32_t)cm * 10 < Config::Sensor::SCAN_OBSTACLE_STOP_MM) {
        enterError(ErrorCode::ObstacleDetected);
        return;
    }
    moveStartMs_ = millis();
    axisX_.moveTo((float)target_.x_mm);
    axisZ_.moveTo((float)target_.z_mm);
    setState(AppState::BusyMoving);
}

void AppController::updateMoveHome() {
    if (!xHomed_) {
        axisX_.update();
    } else if (!homingZStarted_) {
        homingZStarted_ = true;
        if (!zHomed_) {
            axisZ_.startHoming(Config::MotionZ::HOMING_FORWARD, Config::MotionZ::HOMING_RPM);
        }
    } else {
        axisZ_.update();
    }

    checkDriverAlarms();
    if (state_ != AppState::BusyMoveHome) return;

    if ((millis() - moveHomeStartMs_) > Config::Timing::HOME_TIMEOUT_MS) {
        axisX_.stop();
        axisZ_.stop();
        enterError(ErrorCode::HomingTimeout);
        return;
    }

    if (xHomed_ && zHomed_) {
        axisZ_.stop();
        current_ = Position{};
        target_  = Position{};
        reporter_.sendOk(pendingMoveHomeCmdId_, "MOVE_HOME_DONE", motionSnapshot());
        setState(AppState::Ready);
    }
}

void AppController::updateMoving() {
    const bool xDone = axisX_.update();
    const bool zDone = axisZ_.update();

    checkDriverAlarms();
    if (state_ != AppState::BusyMoving) return;

    const uint32_t now = millis();
    if ((now - moveStartMs_) > Config::Timing::MOVE_TIMEOUT_MS) {
        axisX_.stop();
        axisZ_.stop();
        enterError(ErrorCode::MoveTimeout);
        return;
    }

    if (xDone && zDone) {
        current_.x_mm = (int32_t)axisX_.positionMm();
        current_.z_mm = (int32_t)axisZ_.positionMm();
        reporter_.sendOk(pendingMoveCmdId_, "MOVE_DONE", motionSnapshot());
        setState(AppState::Ready);
    }
}

void AppController::updatePickup() {
    if ((millis() - actionStartMs_) > Config::Timing::MOVE_TIMEOUT_MS) {
        gripper_.stop();
        axisZ_.stop();
        enterError(ErrorCode::MoveTimeout);
        return;
    }

    switch (actionPhase_) {
        case 0: // Greifer fährt aus – gripper_.update() läuft im Haupt-Loop
            if (!gripper_.isMoving()) {
                axisZ_.moveTo((float)(actionBaseZ_ + liftOffsetMm_));
                actionPhase_ = 1;
            }
            break;
        case 1: // Z hebt an
            if (axisZ_.update()) {
                // TODO: Plattendetektierung wieder aktivieren
                // if (!sensors_.isPlateDetected()) {
                //     gripper_.stop();
                //     enterError(ErrorCode::PlateNotDetected);
                //     return;
                // }
                gripper_.move(-gripperSteps_);
                actionPhase_ = 2;
            }
            break;
        case 2: // Greifer fährt ein
            if (!gripper_.isMoving()) {
                current_.x_mm = (int32_t)axisX_.positionMm();
                current_.z_mm = (int32_t)axisZ_.positionMm();
                target_       = current_;
                reporter_.sendOk(pendingActionCmdId_, "PICKUP_DONE", motionSnapshot());
                setState(AppState::Ready);
            }
            break;
    }
}

void AppController::updateDeposit() {
    if ((millis() - actionStartMs_) > Config::Timing::MOVE_TIMEOUT_MS) {
        gripper_.stop();
        axisZ_.stop();
        enterError(ErrorCode::MoveTimeout);
        return;
    }

    switch (actionPhase_) {
        case 0: // Z hebt an (gestartet in handleDeposit)
            if (axisZ_.update()) {
                gripper_.move(gripperSteps_);
                actionPhase_ = 1;
            }
            break;
        case 1: // Greifer fährt aus
            if (!gripper_.isMoving()) {
                axisZ_.moveTo((float)actionBaseZ_);
                actionPhase_ = 2;
            }
            break;
        case 2: // Z senkt ab
            if (axisZ_.update()) {
                gripper_.move(-gripperSteps_);
                actionPhase_ = 3;
            }
            break;
        case 3: // Greifer fährt ein
            if (!gripper_.isMoving()) {
                current_.x_mm = (int32_t)axisX_.positionMm();
                current_.z_mm = (int32_t)axisZ_.positionMm();
                target_       = current_;
                reporter_.sendOk(pendingActionCmdId_, "DEPOSIT_DONE", motionSnapshot());
                setState(AppState::Ready);
            }
            break;
    }
}

void AppController::updateOpenDoor() {
    if ((millis() - doorStartMs_) > Config::Timing::MOVE_TIMEOUT_MS) {
        doorArm_.stop();
        axisX_.stop();
        axisZ_.stop();
        enterError(ErrorCode::MoveTimeout);
        return;
    }

    checkDriverAlarms();
    if (state_ != AppState::BusyOpenDoor) return;

    switch (doorPhase_) {
        case 0: { // XZ-Anfahrposition (gestartet in handleOpenDoor)
            const bool xDone = axisX_.update();
            const bool zDone = axisZ_.update();
            if (xDone && zDone) {
                doorArcStartX_ = axisX_.positionMm();
                doorArm_.move(doorArmExtendSteps_);
                doorPhase_ = 1;
            }
            break;
        }
        case 1: // Türarm ausfahren
            if (!doorArm_.isMoving()) {
                axisZ_.moveTo(doorZApproachMm_ + doorHookDropMm_);
                doorPhase_ = 2;
            }
            break;
        case 2: // Z anheben → Mechanismus einhaken
            if (axisZ_.update()) {
                doorArcStep_ = 0;
                doorPhase_   = 3;
            }
            break;
        case 3: { // Kreisbogen öffnen: Waypoints 0 → doorArcTotalSteps_
            if (doorArm_.isMoving() || axisX_.isMoving()) {
                axisX_.update();
                break;
            }
            if (doorArcStep_ > doorArcTotalSteps_) {
                axisZ_.moveTo(doorZApproachMm_);
                doorPhase_ = 4;
                break;
            }
            const float   theta     = (float)doorArcStep_ / (float)doorArcTotalSteps_ * doorTargetAngleRad_;
            const int32_t armTarget = doorArmExtendSteps_ +
                (int32_t)(doorRadiusMm_ * sinf(theta) * Config::DoorArm::STEPS_PER_MM);
            const float   xTarget   = doorArcStartX_ + doorRadiusMm_ * (cosf(theta) - 1.0f);
            const int32_t armDelta  = armTarget - doorArm_.stepPosition();
            if (armDelta != 0) doorArm_.move(armDelta, Config::DoorArm::ARC_STEP_DELAY_US);
            axisX_.moveTo(xTarget, Config::MotionX::DOOR_ARC_MAX_RPM);
            axisX_.update();
            doorArcStep_++;
            break;
        }
        case 4: // Z absenken → Mechanismus aushaken
            if (axisZ_.update()) {
                doorArm_.move(-doorArm_.stepPosition());
                doorPhase_ = 5;
            }
            break;
        case 5: // Türarm einfahren
            if (!doorArm_.isMoving()) {
                axisX_.moveTo(doorOrigStartX_);
                axisZ_.moveTo(doorOrigStartZ_);
                doorPhase_ = 6;
            }
            break;
        case 6: { // Rückfahrt zur Ausgangsposition (X und Z gleichzeitig)
            const bool xDone = axisX_.update();
            const bool zDone = axisZ_.update();
            if (xDone && zDone) {
                current_.x_mm = (int32_t)axisX_.positionMm();
                current_.z_mm = (int32_t)axisZ_.positionMm();
                target_       = current_;
                reporter_.sendOk(pendingDoorCmdId_, "DOOR_OPEN_DONE", motionSnapshot());
                setState(AppState::Ready);
            }
            break;
        }
    }
}

void AppController::updateCloseDoor() {
    if ((millis() - doorStartMs_) > Config::Timing::MOVE_TIMEOUT_MS) {
        doorArm_.stop();
        axisX_.stop();
        axisZ_.stop();
        enterError(ErrorCode::MoveTimeout);
        return;
    }

    checkDriverAlarms();
    if (state_ != AppState::BusyCloseDoor) return;

    switch (doorPhase_) {
        case 0: { // XZ-Anfahrposition (gestartet in handleCloseDoor)
            const bool xDone = axisX_.update();
            const bool zDone = axisZ_.update();
            if (xDone && zDone) {
                doorArcStartX_ = axisX_.positionMm();
                // Arm auf Grifftiefe bei geöffneter Tür: arm_extend + R·sin(angle)
                const int32_t fullGripSteps = doorArmExtendSteps_ +
                    (int32_t)(doorRadiusMm_ * sinf(doorTargetAngleRad_) * Config::DoorArm::STEPS_PER_MM);
                doorArm_.move(fullGripSteps);
                doorPhase_ = 1;
            }
            break;
        }
        case 1: // Türarm auf Grifftiefe der geöffneten Tür ausfahren
            if (!doorArm_.isMoving()) {
                axisZ_.moveTo(doorZApproachMm_ + doorHookDropMm_);
                doorPhase_ = 2;
            }
            break;
        case 2: // Z anheben → Mechanismus einhaken
            if (axisZ_.update()) {
                doorArcStep_ = doorArcTotalSteps_;
                doorPhase_   = 3;
            }
            break;
        case 3: { // Kreisbogen schließen: Waypoints doorArcTotalSteps_ → 0
            if (doorArm_.isMoving() || axisX_.isMoving()) {
                axisX_.update();
                break;
            }
            if (doorArcStep_ < 0) {
                axisZ_.moveTo(doorZApproachMm_);
                doorPhase_ = 4;
                break;
            }
            const float   theta     = (float)doorArcStep_ / (float)doorArcTotalSteps_ * doorTargetAngleRad_;
            const int32_t armTarget = doorArmExtendSteps_ +
                (int32_t)(doorRadiusMm_ * sinf(theta) * Config::DoorArm::STEPS_PER_MM);
            const float   xTarget   = doorArcStartX_ +
                doorRadiusMm_ * (cosf(theta) - cosf(doorTargetAngleRad_));
            const int32_t armDelta  = armTarget - doorArm_.stepPosition();
            if (armDelta != 0) doorArm_.move(armDelta, Config::DoorArm::ARC_STEP_DELAY_US);
            axisX_.moveTo(xTarget, Config::MotionX::DOOR_ARC_MAX_RPM);
            axisX_.update();
            doorArcStep_--;
            break;
        }
        case 4: // Z absenken → Mechanismus aushaken
            if (axisZ_.update()) {
                doorArm_.move(-doorArm_.stepPosition());
                doorPhase_ = 5;
            }
            break;
        case 5: // Türarm einfahren
            if (!doorArm_.isMoving()) {
                axisX_.moveTo(doorOrigStartX_);
                axisZ_.moveTo(doorOrigStartZ_);
                doorPhase_ = 6;
            }
            break;
        case 6: { // Rückfahrt zur Ausgangsposition (X und Z gleichzeitig)
            const bool xDone = axisX_.update();
            const bool zDone = axisZ_.update();
            if (xDone && zDone) {
                current_.x_mm = (int32_t)axisX_.positionMm();
                current_.z_mm = (int32_t)axisZ_.positionMm();
                target_       = current_;
                reporter_.sendOk(pendingDoorCmdId_, "DOOR_CLOSE_DONE", motionSnapshot());
                setState(AppState::Ready);
            }
            break;
        }
    }
}

void AppController::checkDriverAlarms() {
    if (axisX_.alarmActive() || axisZ_.alarmActive()) {
        axisX_.stop();
        axisZ_.stop();
        enterError(ErrorCode::DriverFault);
    }
}

// ─── Zustandsmaschine ─────────────────────────────────────────────────────────

void AppController::setState(AppState next) {
    if (state_ == next) return;
    state_ = next;

    if (next == AppState::Ready && current_.x_mm == 0 && current_.z_mm == 0) {
        axisX_.enable(false);
        axisZ_.enable(false);
    }

    reporter_.sendState(state_, motionSnapshot());
}

void AppController::enterError(ErrorCode error) {
    error_ = error;
    reporter_.sendError(error, motionSnapshot());
    setState(AppState::Error);
    publishStatus();
}

void AppController::stopAllMotors() {
    axisX_.stop();
    axisZ_.stop();
    gripper_.stop();
    doorArm_.stop();
    // Position aus tatsächlicher Motorposition übernehmen
    current_.x_mm = (int32_t)axisX_.positionMm();
    current_.z_mm = (int32_t)axisZ_.positionMm();
}

// ─── Status-Reporting ─────────────────────────────────────────────────────────

void AppController::publishStatus() {
    StatusSnapshot s;
    s.state   = state_;
    s.error   = error_;
    s.motion  = motionSnapshot();
    s.sensors = readSensors();
    reporter_.sendStatus(s);
}

MotionSnapshot AppController::motionSnapshot() const {
    MotionSnapshot m;
    m.current.x_mm = (int32_t)axisX_.positionMm();
    m.current.z_mm = (int32_t)axisZ_.positionMm();
    m.target       = target_;
    m.busy         = (state_ == AppState::BusyHoming    || state_ == AppState::BusyScanning  ||
                      state_ == AppState::BusyMoving    || state_ == AppState::BusyMoveHome  ||
                      state_ == AppState::BusyPickup    || state_ == AppState::BusyDeposit   ||
                      state_ == AppState::BusyOpenDoor  || state_ == AppState::BusyCloseDoor);
    m.referenced   = referenced_;
    return m;
}

SensorSnapshot AppController::readSensors() {
    SensorSnapshot s = cachedSensors_;

    // I2C-Reads nur wenn kein Motor läuft – verhindert Timing-Störungen
    if (!motorsRunning()) {
        uint16_t doorMm = 0;
        if (sensors_.readDoorMm(doorMm)) {
            s.doorDistanceMm = doorMm;
            s.doorOpen       = (doorMm < Config::Sensor::DOOR_OPEN_MM);
        }
    }

    // Digitale Reads sind µs-schnell, immer erlaubt
    s.gripperHome   = sensors_.isGripperHome();
    s.doorArmHome   = sensors_.isDoorArmHome();
    s.plateDetected = sensors_.isPlateDetected();

    cachedSensors_ = s;
    return s;
}

bool AppController::motorsRunning() const {
    return axisX_.isMoving() || axisZ_.isMoving() ||
           gripper_.isMoving() || doorArm_.isMoving();
}

}  // namespace esp_schlitten
