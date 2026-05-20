#include "status/StatusReporter.h"

namespace esp_schlitten {

void StatusReporter::begin(CommandInterface &comm) {
  comm_ = &comm;
}

void StatusReporter::sendState(AppState state, const MotionSnapshot &motion) {
  if (!comm_) return;
  comm_->sendLine(
    String("EVT;0;STATE;") + toString(state) +
    ";ref=" + (motion.referenced ? "1" : "0") +
    posFields(motion));
}

void StatusReporter::sendStatus(const StatusSnapshot &s) {
  if (!comm_) return;
  comm_->sendLine(
    String("EVT;0;STATUS;state=")   + toString(s.state) +
    ";error="                        + toString(s.error) +
    ";ref="                          + (s.motion.referenced ? "1" : "0") +
    ";x="                            + s.motion.current.x_mm +
    ";z="                            + s.motion.current.z_mm +
    ";target_x="                     + s.motion.target.x_mm +
    ";target_z="                     + s.motion.target.z_mm +
    ";busy="                         + (s.motion.busy ? "1" : "0") +
    ";gripper_home="                 + (s.sensors.gripperHome ? "1" : "0") +
    ";door_arm_home="                + (s.sensors.doorArmHome ? "1" : "0") +
    ";obstacle_ok="                  + (s.sensors.obstacleOk ? "1" : "0") +
    ";door_open="                    + (s.sensors.doorOpen ? "1" : "0") +
    ";door_dist_mm="                 + s.sensors.doorDistanceMm +
    ";plate_detected="               + (s.sensors.plateDetected ? "1" : "0"));
}

void StatusReporter::sendOk(uint32_t id, const char *eventName, const MotionSnapshot &motion) {
  if (!comm_) return;
  comm_->sendLine(
    String("EVT;") + id + ";OK;" + eventName +
    posFields(motion));
}

void StatusReporter::sendError(ErrorCode error, const MotionSnapshot &motion) {
  if (!comm_) return;
  comm_->sendLine(
    String("EVT;0;ERR;") + toString(error) +
    posFields(motion));
}

void StatusReporter::sendHeartbeat(AppState state, const MotionSnapshot &motion) {
  if (!comm_) return;
  comm_->sendLine(
    String("EVT;0;HEARTBEAT;uptime_ms=") + millis() +
    ";state="                             + toString(state) +
    posFields(motion));
}

String StatusReporter::posFields(const MotionSnapshot &motion) const {
  return String(";x=") + motion.current.x_mm + ";z=" + motion.current.z_mm;
}

}  // namespace esp_schlitten
