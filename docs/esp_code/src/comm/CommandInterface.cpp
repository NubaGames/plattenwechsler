#include "comm/CommandInterface.h"

namespace esp_schlitten {

void CommandInterface::begin(Stream &serial) {
  serial_ = &serial;
  inputBuffer_.reserve(kMaxLineLength);
}

void CommandInterface::poll() {
  if (serial_ == nullptr) return;

  while (serial_->available() > 0) {
    const char next = static_cast<char>(serial_->read());

    if (next == '\r' || next == '\n') {
      if (inputBuffer_.length() > 0) {
        const Command cmd = parseLine(inputBuffer_);
        if (!enqueue(cmd)) {
          sendResponseError(cmd.id, ErrorCode::Busy);
        }
        inputBuffer_ = "";
        inputBuffer_.reserve(kMaxLineLength);
      }
      continue;
    }

    if (inputBuffer_.length() >= kMaxLineLength) {
      inputBuffer_ = "";
      inputBuffer_.reserve(kMaxLineLength);
      sendResponseError(0, ErrorCode::InvalidCommand);
      continue;
    }

    inputBuffer_ += next;
  }
}

bool CommandInterface::hasPendingCommand() const {
  return count_ > 0;
}

Command CommandInterface::popCommand() {
  if (count_ == 0) return {};
  const Command cmd = queue_[head_];
  head_ = static_cast<uint8_t>((head_ + 1U) % kQueueCapacity);
  --count_;
  return cmd;
}

void CommandInterface::sendLine(const String &line) {
  if (serial_ == nullptr) return;
  serial_->println(line);
}

void CommandInterface::sendAck(uint32_t id) {
  sendLine(String("RSP;") + id + ";ACK");
}

void CommandInterface::sendResponseError(uint32_t id, ErrorCode error) {
  sendLine(String("RSP;") + id + ";ERR;" + toString(error));
}

// ---------------------------------------------------------------------------

Command CommandInterface::parseLine(String line) const {
  line.trim();

  Command cmd;
  if (line.length() == 0) {
    cmd.parseError = ErrorCode::InvalidCommand;
    return cmd;
  }

  // Zeile in bis zu 8 Felder zerlegen
  String fields[8];
  uint8_t fieldCount = 0;
  int start = 0;
  while (start <= static_cast<int>(line.length()) && fieldCount < 8) {
    int delim = line.indexOf(';', start);
    if (delim < 0) {
      fields[fieldCount++] = line.substring(start);
      break;
    }
    fields[fieldCount++] = line.substring(start, delim);
    start = delim + 1;
  }

  if (fieldCount < 3) {
    cmd.parseError = ErrorCode::InvalidCommand;
    return cmd;
  }

  fields[0].trim();
  if (!fields[0].equalsIgnoreCase("CMD")) {
    cmd.parseError = ErrorCode::InvalidCommand;
    return cmd;
  }

  fields[1].trim();
  const long idVal = fields[1].toInt();
  if (idVal < 0) {
    cmd.parseError = ErrorCode::InvalidCommand;
    return cmd;
  }
  cmd.id = static_cast<uint32_t>(idVal);

  fields[2].trim();
  fields[2].toUpperCase();
  const String &verb = fields[2];

  // --- Einfache Kommandos ohne Parameter ---
  if (verb == "PING")        { cmd.type = CommandType::Ping;      cmd.valid = true; return cmd; }
  if (verb == "STATUS")      { cmd.type = CommandType::Status;    cmd.valid = true; return cmd; }
  if (verb == "STREAM_ON")   { cmd.type = CommandType::StreamOn;  cmd.valid = true; return cmd; }
  if (verb == "STREAM_OFF")  { cmd.type = CommandType::StreamOff; cmd.valid = true; return cmd; }
  if (verb == "STOP")        { cmd.type = CommandType::Stop;      cmd.valid = true; return cmd; }
  if (verb == "HOME")        { cmd.type = CommandType::Home;      cmd.valid = true; return cmd; }
  if (verb == "MOVE_HOME")   { cmd.type = CommandType::MoveHome;  cmd.valid = true; return cmd; }
  if (verb == "RESET_ERROR") { cmd.type = CommandType::ResetError; cmd.valid = true; return cmd; }

  // --- HOME_SWITCH_HIT;axis=<X|Z> ---
  if (verb == "HOME_SWITCH_HIT") {
    cmd.type = CommandType::HomeSwitchHit;
    for (uint8_t i = 3; i < fieldCount; ++i) {
      String key, value;
      if (!parseKeyValue(fields[i], key, value)) {
        cmd.parseError = ErrorCode::InvalidCommand;
        return cmd;
      }
      key.toLowerCase();
      value.toUpperCase();
      if (key != "axis") { cmd.parseError = ErrorCode::InvalidCommand; return cmd; }
      if      (value == "X") cmd.axis = HomingAxis::X;
      else if (value == "Z") cmd.axis = HomingAxis::Z;
      else { cmd.parseError = ErrorCode::InvalidCommand; return cmd; }
    }
    if (cmd.axis == HomingAxis::None) {
      cmd.parseError = ErrorCode::InvalidCommand;
      return cmd;
    }
    cmd.valid = true;
    return cmd;
  }

  // --- MOVE_TO;x=<mm>;z=<mm> ---
  if (verb == "MOVE_TO") {
    cmd.type = CommandType::MoveTo;
    bool hasX = false;
    bool hasZ = false;

    for (uint8_t i = 3; i < fieldCount; ++i) {
      String key, value;
      if (!parseKeyValue(fields[i], key, value)) {
        cmd.parseError = ErrorCode::InvalidCommand;
        return cmd;
      }
      key.toLowerCase();
      if      (key == "x") { cmd.target.x_mm = value.toInt(); hasX = true; }
      else if (key == "z") { cmd.target.z_mm = value.toInt(); hasZ = true; }
      else { cmd.parseError = ErrorCode::InvalidCommand; return cmd; }
    }

    if (!hasX || !hasZ) {
      cmd.parseError = ErrorCode::InvalidCommand;
      return cmd;
    }
    cmd.valid = true;
    return cmd;
  }

  // --- SET_CLAMP;position=<OPEN|CLOSED|SERVICE> ---
  if (verb == "SET_CLAMP") {
    cmd.type = CommandType::SetClamp;
    for (uint8_t i = 3; i < fieldCount; ++i) {
      String key, value;
      if (!parseKeyValue(fields[i], key, value)) {
        cmd.parseError = ErrorCode::InvalidCommand;
        return cmd;
      }
      key.toLowerCase();
      value.toUpperCase();
      if (key != "position") { cmd.parseError = ErrorCode::InvalidCommand; return cmd; }
      if      (value == "OPEN")    cmd.clampPosition = ClampPosition::Open;
      else if (value == "CLOSED")  cmd.clampPosition = ClampPosition::Closed;
      else if (value == "SERVICE") cmd.clampPosition = ClampPosition::Service;
      else { cmd.parseError = ErrorCode::InvalidCommand; return cmd; }
    }
    if (cmd.clampPosition == ClampPosition::Unknown) {
      cmd.parseError = ErrorCode::InvalidCommand;
      return cmd;
    }
    cmd.valid = true;
    return cmd;
  }

  // --- SET_DOOR_ARM;position=<OPEN|CLOSED> ---
  if (verb == "SET_DOOR_ARM") {
    cmd.type = CommandType::SetDoorArm;
    for (uint8_t i = 3; i < fieldCount; ++i) {
      String key, value;
      if (!parseKeyValue(fields[i], key, value)) {
        cmd.parseError = ErrorCode::InvalidCommand;
        return cmd;
      }
      key.toLowerCase();
      value.toUpperCase();
      if (key != "position") { cmd.parseError = ErrorCode::InvalidCommand; return cmd; }
      if      (value == "OPEN")   cmd.doorArmPosition = DoorArmPosition::Open;
      else if (value == "CLOSED") cmd.doorArmPosition = DoorArmPosition::Closed;
      else { cmd.parseError = ErrorCode::InvalidCommand; return cmd; }
    }
    if (cmd.doorArmPosition == DoorArmPosition::Unknown) {
      cmd.parseError = ErrorCode::InvalidCommand;
      return cmd;
    }
    cmd.valid = true;
    return cmd;
  }

  cmd.parseError = ErrorCode::InvalidCommand;
  return cmd;
}

bool CommandInterface::enqueue(const Command &cmd) {
  if (count_ >= kQueueCapacity) return false;
  queue_[tail_] = cmd;
  tail_ = static_cast<uint8_t>((tail_ + 1U) % kQueueCapacity);
  ++count_;
  return true;
}

bool CommandInterface::parseKeyValue(const String &fragment, String &key, String &value) const {
  const int sep = fragment.indexOf('=');
  if (sep < 1 || sep >= static_cast<int>(fragment.length()) - 1) return false;
  key   = fragment.substring(0, sep);
  value = fragment.substring(sep + 1);
  key.trim();
  value.trim();
  return key.length() > 0 && value.length() > 0;
}

}  // namespace esp_schlitten
