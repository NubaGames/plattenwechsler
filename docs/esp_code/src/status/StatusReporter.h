#pragma once

#include <Arduino.h>

#include "comm/CommandInterface.h"
#include "core/Types.h"

namespace esp_schlitten {

class StatusReporter {
 public:
  void begin(CommandInterface &comm);

  void sendState(AppState state, const MotionSnapshot &motion);
  void sendStatus(const StatusSnapshot &snapshot);
  void sendOk(uint32_t id, const char *eventName, const MotionSnapshot &motion);
  void sendError(ErrorCode error, const MotionSnapshot &motion);
  void sendHeartbeat(AppState state, const MotionSnapshot &motion);

 private:
  String posFields(const MotionSnapshot &motion) const;

  CommandInterface *comm_ = nullptr;
};

}  // namespace esp_schlitten
