"""Tests für ESP-Protokoll und Fehlerklassifikation."""
from plattenwechsler.io_.esp_client import EspMessage
from plattenwechsler.types import ErrorClass, ESP_ERROR_TO_CLASS


class TestParser:
    def test_ack(self):
        m = EspMessage.parse("RSP;5;ACK")
        assert m.kind == "RSP" and m.msg_id == 5
        assert m.payload == ["ACK"]

    def test_err(self):
        m = EspMessage.parse("RSP;7;ERR;OBSTACLE")
        assert m.payload == ["ERR", "OBSTACLE"]

    def test_state(self):
        m = EspMessage.parse("EVT;0;STATE;READY;ref=1;x=100;z=200")
        assert m.payload[0] == "STATE"
        assert m.fields["x"] == "100"

    def test_status_alle_felder(self):
        line = ("EVT;0;STATUS;state=READY;error=NONE;ref=1;x=100;z=200;"
                "target_x=100;target_z=200;busy=0;gripper_home=1;"
                "door_arm_home=1;obstacle_ok=1;door_open=0;door_dist_mm=350")
        m = EspMessage.parse(line)
        assert m.fields["gripper_home"] == "1"
        assert m.fields["door_open"] == "0"
        assert m.fields["door_dist_mm"] == "350"

    def test_clamp_event(self):
        m = EspMessage.parse("EVT;7;OK;CLAMP_CLOSED")
        assert m.payload[1] == "CLAMP_CLOSED"

    def test_door_arm_event(self):
        m = EspMessage.parse("EVT;8;OK;DOOR_ARM_OPEN")
        assert m.payload[1] == "DOOR_ARM_OPEN"

    def test_move_done(self):
        m = EspMessage.parse("EVT;3;OK;MOVE_DONE")
        assert m.payload == ["OK", "MOVE_DONE"]

    def test_heartbeat(self):
        m = EspMessage.parse("EVT;0;HEARTBEAT;uptime_ms=12345")
        assert m.fields["uptime_ms"] == "12345"

    def test_leer(self):
        assert EspMessage.parse("") is None
        assert EspMessage.parse("\n") is None

    def test_unbekannter_typ(self):
        assert EspMessage.parse("FOO;1;BAR") is None

    def test_ungueltige_id(self):
        assert EspMessage.parse("RSP;abc;ACK") is None


class TestFehlerklassen:
    def test_obstacle_ist_hindernis(self):
        assert ESP_ERROR_TO_CLASS["OBSTACLE"] == ErrorClass.HINDERNIS

    def test_sensor_fault_ist_sensorfehler(self):
        assert ESP_ERROR_TO_CLASS["SENSOR_FAULT_OBSTACLE"] == ErrorClass.SENSORFEHLER
        assert ESP_ERROR_TO_CLASS["SENSOR_FAULT_GRIPPER"] == ErrorClass.SENSORFEHLER

    def test_invalid_command_ist_kommunikationsfehler(self):
        assert ESP_ERROR_TO_CLASS["INVALID_COMMAND"] == ErrorClass.KOMMUNIKATIONSFEHLER

    def test_move_timeout_ist_fahrfehler(self):
        assert ESP_ERROR_TO_CLASS["MOVE_TIMEOUT"] == ErrorClass.FAHRFEHLER
