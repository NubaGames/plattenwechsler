#pragma once

#include <Arduino.h>
#include <Stream.h>

#include "core/Types.h"

namespace esp_schlitten {

class CommandInterface {
 public:
  void begin(Stream &serial);
  void poll();

  bool hasPendingCommand() const;
  Command popCommand();

  void sendLine(const String &line);
  void sendAck(uint32_t id);
  void sendResponseError(uint32_t id, ErrorCode error);

 private:
  static constexpr uint8_t  kQueueCapacity = 8;
  static constexpr uint16_t kMaxLineLength  = 160;

  Command parseLine(String line) const;
  bool    enqueue(const Command &cmd);
  bool    parseKeyValue(const String &fragment, String &key, String &value) const;

  Stream *serial_      = nullptr;
  String  inputBuffer_;
  Command queue_[kQueueCapacity];
  uint8_t head_  = 0;
  uint8_t tail_  = 0;
  uint8_t count_ = 0;
};

}  // namespace esp_schlitten
