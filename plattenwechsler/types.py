"""Datentypen, Enums und Konstanten für den Plattenwechsler.

Schnittstellen-Stand: Mai 2026 (TF-Luna Hindernissensor + VL53L0X Türsensor
am Schlitten, Türarm-Hebel; PICKUP/DEPOSIT steuern Greifer+Z-Hub intern).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class SystemState(Enum):
    INIT = "INIT"
    REFERENZFAHRT = "REFERENZFAHRT"
    BEREITSCHAFT = "BEREITSCHAFT"
    PLATTENWECHSEL = "PLATTENWECHSEL"
    SERVICE = "SERVICE"
    FEHLER = "FEHLER"
    NOT_AUS = "NOT_AUS"


class EspState(Enum):
    NOT_REFERENCED = "NOT_REFERENCED"
    READY = "READY"
    BUSY_HOMING = "BUSY_HOMING"
    BUSY_SCANNING = "BUSY_SCANNING"
    BUSY_MOVING = "BUSY_MOVING"
    BUSY_MOVE_HOME = "BUSY_MOVE_HOME"
    BUSY_PICKUP = "BUSY_PICKUP"
    BUSY_DEPOSIT = "BUSY_DEPOSIT"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class DoorArmPosition(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ErrorClass(Enum):
    KOMMUNIKATIONSFEHLER = "Kommunikationsfehler"
    FAHRFEHLER = "Fahrfehler"
    HINDERNIS = "Hindernis"
    SENSORFEHLER = "Sensorfehler"
    TUERFEHLER = "Tuerfehler"
    ENTNAHMEFEHLER = "Entnahmefehler"
    NOT_AUS = "Not-Aus"
    INTERNER_FEHLER = "Interner Fehler"
    ABLAGE_VOLL = "Ablage voll"
    MAGAZIN_LEER = "Magazin leer"


ESP_ERROR_TO_CLASS = {
    "INVALID_COMMAND":       ErrorClass.KOMMUNIKATIONSFEHLER,
    "BUSY":                  ErrorClass.KOMMUNIKATIONSFEHLER,
    "INVALID_STATE":         ErrorClass.KOMMUNIKATIONSFEHLER,
    "NOT_REFERENCED":        ErrorClass.FAHRFEHLER,
    "MOVE_TIMEOUT":          ErrorClass.FAHRFEHLER,
    "HOMING_TIMEOUT":        ErrorClass.FAHRFEHLER,
    "OBSTACLE":              ErrorClass.HINDERNIS,
    "POSITION_ERROR":        ErrorClass.FAHRFEHLER,
    "SENSOR_FAULT_OBSTACLE": ErrorClass.SENSORFEHLER,
    "SENSOR_FAULT_GRIPPER":  ErrorClass.SENSORFEHLER,
    "DRIVER_FAULT":          ErrorClass.FAHRFEHLER,
    "PLATE_NOT_DETECTED":    ErrorClass.ENTNAHMEFEHLER,
    "DOOR_NOT_OPEN":         ErrorClass.TUERFEHLER,
}


class AuftragQuelle(Enum):
    DRUCKER_FERTIG = "Druckerstatus"
    HMI = "Touchdisplay"
    MQTT = "MQTT"
    TELEGRAM = "Telegram"


class DruckerStatus(Enum):
    BEREIT = "bereit"
    DRUCKT = "druckt"
    IN_QUEUE = "in_queue"
    AKTIV = "aktiv"


@dataclass
class Auftrag:
    drucker_id: int
    quelle: AuftragQuelle
    timestamp: float = field(default_factory=time.time)
    auftrag_id: int = 0

    def __str__(self) -> str:
        return (f"Auftrag#{self.auftrag_id}(Drucker={self.drucker_id}, "
                f"Quelle={self.quelle.value})")


@dataclass
class DruckerConfig:
    """Konfiguration eines Druckers — alle Werte über UI änderbar."""
    id: int
    name: str = ""
    pin_fertig: int = 0
    pos_x: int = 0
    pos_z_anfahr: int = 0
    pos_z_tuer: int = 0
    pos_z_druckbett: int = 0
    door_arm_hub_mm: int = 50
    gripper_depth: int = 120
    lift_offset: int = 8

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "pin_fertig": self.pin_fertig,
            "pos_x": self.pos_x, "pos_z_anfahr": self.pos_z_anfahr,
            "pos_z_tuer": self.pos_z_tuer, "pos_z_druckbett": self.pos_z_druckbett,
            "door_arm_hub_mm": self.door_arm_hub_mm,
            "gripper_depth": self.gripper_depth, "lift_offset": self.lift_offset,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DruckerConfig":
        return cls(
            id=int(d["id"]),
            name=str(d.get("name", "") or f"Drucker {d['id']}"),
            pin_fertig=int(d.get("pin_fertig", 0)),
            pos_x=int(d.get("pos_x", 0)),
            pos_z_anfahr=int(d.get("pos_z_anfahr", 0)),
            pos_z_tuer=int(d.get("pos_z_tuer", 0)),
            pos_z_druckbett=int(d.get("pos_z_druckbett", 0)),
            door_arm_hub_mm=int(d.get("door_arm_hub_mm", 50)),
            gripper_depth=int(d.get("gripper_depth", 120)),
            lift_offset=int(d.get("lift_offset", 8)),
        )


@dataclass
class EspStatus:
    state: EspState = EspState.UNKNOWN
    error: str = "NONE"
    referenced: bool = False
    x_mm: int = 0
    z_mm: int = 0
    target_x_mm: int = 0
    target_z_mm: int = 0
    busy: bool = False

    # Mechanik-Sensoren am Schlitten
    gripper_home: bool = False
    door_arm_home: bool = False
    obstacle_ok: bool = True
    door_open: bool = False        # einzelner Bool — Tür des angefahrenen Druckers
    door_dist_mm: int = 0           # Rohwert VL53L0X (Debug)

    plate_detected: bool = False     # ESP-Sensor: Platte liegt auf der Gabel
    last_update: float = 0.0
    has_plate: bool = False         # Pi-intern (während Plattenwechsel)


@dataclass
class AblageConfig:
    id: int
    name: str = ""
    x: int = 0
    z: int = 0
    gripper_depth: int = 120
    lift_offset: int = 8
    belegt: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "x": self.x, "z": self.z,
                "gripper_depth": self.gripper_depth, "lift_offset": self.lift_offset,
                "belegt": self.belegt}

    @classmethod
    def from_dict(cls, d: dict) -> "AblageConfig":
        return cls(id=int(d["id"]),
                   name=str(d.get("name", "") or f"Ablage {d['id']}"),
                   x=int(d.get("x", 0)), z=int(d.get("z", 0)),
                   gripper_depth=int(d.get("gripper_depth", 120)),
                   lift_offset=int(d.get("lift_offset", 8)),
                   belegt=bool(d.get("belegt", False)))


@dataclass
class MagazinConfig:
    id: int
    name: str = ""
    x: int = 0
    z: int = 0
    gripper_depth: int = 120
    lift_offset: int = 8
    verfuegbar: bool = True

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "x": self.x, "z": self.z,
                "gripper_depth": self.gripper_depth, "lift_offset": self.lift_offset,
                "verfuegbar": self.verfuegbar}

    @classmethod
    def from_dict(cls, d: dict) -> "MagazinConfig":
        return cls(id=int(d["id"]),
                   name=str(d.get("name", "") or f"Magazin {d['id']}"),
                   x=int(d.get("x", 0)), z=int(d.get("z", 0)),
                   gripper_depth=int(d.get("gripper_depth", 120)),
                   lift_offset=int(d.get("lift_offset", 8)),
                   verfuegbar=bool(d.get("verfuegbar", True)))


@dataclass
class Fehler:
    klasse: ErrorClass
    nachricht: str
    esp_code: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    quittiert: bool = False

    def __str__(self) -> str:
        c = f" [{self.esp_code}]" if self.esp_code else ""
        return f"{self.klasse.value}{c}: {self.nachricht}"


class PlattenwechslerError(Exception):
    def __init__(self, klasse: ErrorClass, nachricht: str,
                 esp_code: Optional[str] = None):
        super().__init__(nachricht)
        self.klasse = klasse
        self.nachricht = nachricht
        self.esp_code = esp_code


class EspKommunikationsError(PlattenwechslerError):
    def __init__(self, nachricht: str, esp_code: Optional[str] = None):
        super().__init__(ErrorClass.KOMMUNIKATIONSFEHLER, nachricht, esp_code)


class EspTimeoutError(PlattenwechslerError):
    def __init__(self, nachricht: str):
        super().__init__(ErrorClass.KOMMUNIKATIONSFEHLER, nachricht)


class EspBefehlAbgelehnt(PlattenwechslerError):
    def __init__(self, esp_code: str, nachricht: str = ""):
        super().__init__(
            ESP_ERROR_TO_CLASS.get(esp_code, ErrorClass.KOMMUNIKATIONSFEHLER),
            nachricht or f"ESP lehnte Kommando ab: {esp_code}",
            esp_code=esp_code)
