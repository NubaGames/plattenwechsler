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
        case CommandType::SetClamp:      handleSetClamp(cmd);      return;
        case CommandType::SetDoorArm:    handleSetDoorArm(cmd);    return;
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
    if (state_ == AppState::BusyHoming || state_ == AppState::BusyMoving ||
        state_ == AppState::BusyScanning || state_ == AppState::BusyMoveHome) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }

    comm_.sendAck(cmd.id);

    xHomed_           = false;
    zHomed_           = false;
    homingZStarted_   = false;
    pendingHomeCmdId_ = cmd.id;
    homingStartMs_    = millis();
    referenced_       = false;
    error_            = ErrorCode::None;

    axisX_.startHoming(Config::MotionX::HOMING_FORWARD, Config::MotionX::HOMING_RPM);

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
    if (state_ == AppState::BusyHoming || state_ == AppState::BusyMoving ||
        state_ == AppState::BusyScanning || state_ == AppState::BusyMoveHome) {
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
    if (state_ == AppState::BusyHoming || state_ == AppState::BusyMoving ||
        state_ == AppState::BusyScanning || state_ == AppState::BusyMoveHome) {
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

void AppController::handleSetClamp(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming || state_ == AppState::BusyMoving ||
        state_ == AppState::BusyScanning || state_ == AppState::BusyMoveHome) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    comm_.sendAck(cmd.id);
    // TODO: Greifer-Aktor ansteuern wenn Mechanismus feststeht
    String evtName = String("CLAMP_") + toString(cmd.clampPosition);
    reporter_.sendOk(cmd.id, evtName.c_str(), motionSnapshot());
}

void AppController::handleSetDoorArm(const Command &cmd) {
    if (state_ == AppState::Error) {
        comm_.sendResponseError(cmd.id, ErrorCode::InvalidState);
        return;
    }
    if (state_ == AppState::BusyHoming || state_ == AppState::BusyMoving ||
        state_ == AppState::BusyScanning || state_ == AppState::BusyMoveHome) {
        comm_.sendResponseError(cmd.id, ErrorCode::Busy);
        return;
    }
    comm_.sendAck(cmd.id);
    // TODO: Türarm-Aktor ansteuern wenn Mechanismus feststeht
    String evtName = String("DOOR_ARM_") + toString(cmd.doorArmPosition);
    reporter_.sendOk(cmd.id, evtName.c_str(), motionSnapshot());
}

// ─── Zustandsupdates ─────────────────────────────────────────────────────────

void AppController::updateHoming() {
    if (!xHomed_) {
        axisX_.update();
    } else if (!homingZStarted_) {
        axisZ_.startHoming(Config::MotionZ::HOMING_FORWARD, Config::MotionZ::HOMING_RPM);
        homingZStarted_ = true;
    } else {
        axisZ_.update();
    }

    checkDriverAlarms();
    if (state_ != AppState::BusyHoming) return;

    if ((millis() - homingStartMs_) > Config::Timing::HOME_TIMEOUT_MS) {
        axisX_.stop();
        axisZ_.stop();
        enterError(ErrorCode::HomingTimeout);
        return;
    }

    if (xHomed_ && zHomed_) {
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
        axisZ_.startHoming(Config::MotionZ::HOMING_FORWARD, Config::MotionZ::HOMING_RPM);
        homingZStarted_ = true;
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
    m.busy         = (state_ == AppState::BusyHoming   || state_ == AppState::BusyScanning ||
                      state_ == AppState::BusyMoving   || state_ == AppState::BusyMoveHome);
    m.referenced   = referenced_;
    return m;
}

SensorSnapshot AppController::readSensors() {
    SensorSnapshot s = cachedSensors_;

    uint16_t doorMm = 0;
    if (sensors_.readDoorMm(doorMm)) {
        s.doorDistanceMm = doorMm;
        s.doorOpen       = (doorMm < Config::Sensor::DOOR_OPEN_MM);
    }
    cachedSensors_ = s;
    return s;
}

}  // namespace esp_schlitten
