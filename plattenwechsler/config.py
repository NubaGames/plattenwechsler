"""Lädt config.yaml und stellt Werte typisiert bereit.

Drucker können zur Laufzeit hinzugefügt/entfernt/geändert werden — die
Änderungen werden automatisch in die config.yaml zurückgeschrieben.
"""
from __future__ import annotations
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, List, Dict

import yaml

from .types import DruckerConfig, AblageConfig, MagazinConfig

logger = logging.getLogger(__name__)


@dataclass
class Position:
    x: int
    z: int
    gripper_depth: int = 120
    lift_offset: int = 8


class Config:
    def __init__(self, data: dict, source_path: Optional[Path] = None):
        self._data = data
        self._source_path = source_path
        self._lock = threading.RLock()
        self._save_listeners: list = []

    def get(self, *keys, default=None) -> Any:
        with self._lock:
            node = self._data
            for k in keys:
                if not isinstance(node, dict) or k not in node:
                    return default
                node = node[k]
            return node

    @property
    def log_level(self) -> str:
        return str(self.get("system", "log_level", default="INFO"))

    @property
    def log_file(self) -> str:
        return str(self.get("system", "log_file", default="plattenwechsler.log"))

    def position(self, name: str) -> Optional[Position]:
        p = self.get("positionen", name)
        if not p:
            return None
        return Position(
            x=int(p["x"]), z=int(p["z"]),
            gripper_depth=int(p.get("gripper_depth", 120)),
            lift_offset=int(p.get("lift_offset", 8)),
        )

    # ---------- Drucker-Liste ----------
    def drucker_liste(self) -> List[DruckerConfig]:
        with self._lock:
            liste = self._data.get("drucker", []) or []
            return [DruckerConfig.from_dict(d) for d in liste]

    @property
    def num_drucker(self) -> int:
        return len(self.drucker_liste())

    def drucker(self, drucker_id: int) -> Optional[DruckerConfig]:
        for d in self.drucker_liste():
            if d.id == drucker_id:
                return d
        return None

    def drucker_setzen(self, dc: DruckerConfig) -> None:
        with self._lock:
            liste = self._data.setdefault("drucker", [])
            d_dict = dc.to_dict()
            for i, alt in enumerate(liste):
                if int(alt.get("id", 0)) == dc.id:
                    liste[i] = d_dict
                    self._save()
                    return
            liste.append(d_dict)
            liste.sort(key=lambda x: int(x["id"]))
            self._save()

    def drucker_entfernen(self, drucker_id: int) -> bool:
        with self._lock:
            liste = self._data.get("drucker", [])
            for i, d in enumerate(liste):
                if int(d.get("id", 0)) == drucker_id:
                    liste.pop(i)
                    self._save()
                    return True
            return False

    def naechste_freie_drucker_id(self) -> int:
        used = {d.id for d in self.drucker_liste()}
        i = 1
        while i in used:
            i += 1
        return i

    def position_setzen(self, name: str, pos: "Position") -> None:
        with self._lock:
            self._data.setdefault("positionen", {})[name] = {
                "x": pos.x, "z": pos.z,
                "gripper_depth": pos.gripper_depth,
                "lift_offset": pos.lift_offset,
            }
            self._save()

    # ---------- Ablagen ----------
    def ablage_liste(self) -> list:
        with self._lock:
            return [AblageConfig.from_dict(d)
                    for d in (self._data.get("ablagen") or [])]

    def ablage(self, ablage_id: int) -> "Optional[AblageConfig]":
        for a in self.ablage_liste():
            if a.id == ablage_id:
                return a
        return None

    def ablage_setzen(self, ac: AblageConfig) -> None:
        with self._lock:
            liste = self._data.setdefault("ablagen", [])
            for i, d in enumerate(liste):
                if int(d.get("id", 0)) == ac.id:
                    liste[i] = ac.to_dict(); self._save(); return
            liste.append(ac.to_dict())
            liste.sort(key=lambda x: int(x["id"]))
            self._save()

    def ablage_entfernen(self, ablage_id: int) -> bool:
        with self._lock:
            liste = self._data.get("ablagen", [])
            for i, d in enumerate(liste):
                if int(d.get("id", 0)) == ablage_id:
                    liste.pop(i); self._save(); return True
        return False

    def ablage_belegt_setzen(self, ablage_id: int, belegt: bool) -> None:
        with self._lock:
            for d in (self._data.get("ablagen") or []):
                if int(d.get("id", 0)) == ablage_id:
                    d["belegt"] = belegt; self._save(); return

    def naechste_freie_ablage(self) -> "Optional[AblageConfig]":
        for a in self.ablage_liste():
            if not a.belegt:
                return a
        return None

    def naechste_freie_ablage_id(self) -> int:
        used = {a.id for a in self.ablage_liste()}
        i = 1
        while i in used:
            i += 1
        return i

    # ---------- Magazin ----------
    def magazin_liste(self) -> list:
        with self._lock:
            return [MagazinConfig.from_dict(d)
                    for d in (self._data.get("magazine") or [])]

    def magazin(self, magazin_id: int) -> "Optional[MagazinConfig]":
        for m in self.magazin_liste():
            if m.id == magazin_id:
                return m
        return None

    def magazin_setzen(self, mc: MagazinConfig) -> None:
        with self._lock:
            liste = self._data.setdefault("magazine", [])
            for i, d in enumerate(liste):
                if int(d.get("id", 0)) == mc.id:
                    liste[i] = mc.to_dict(); self._save(); return
            liste.append(mc.to_dict())
            liste.sort(key=lambda x: int(x["id"]))
            self._save()

    def magazin_entfernen(self, magazin_id: int) -> bool:
        with self._lock:
            liste = self._data.get("magazine", [])
            for i, d in enumerate(liste):
                if int(d.get("id", 0)) == magazin_id:
                    liste.pop(i); self._save(); return True
        return False

    def magazin_verfuegbar_setzen(self, magazin_id: int, verfuegbar: bool) -> None:
        with self._lock:
            for d in (self._data.get("magazine") or []):
                if int(d.get("id", 0)) == magazin_id:
                    d["verfuegbar"] = verfuegbar; self._save(); return

    def naechstes_verfuegbares_magazin(self) -> "Optional[MagazinConfig]":
        for m in self.magazin_liste():
            if m.verfuegbar:
                return m
        return None

    def naechste_freie_magazin_id(self) -> int:
        used = {m.id for m in self.magazin_liste()}
        i = 1
        while i in used:
            i += 1
        return i

    # ---------- GPIO ----------
    def gpio_drucker_fertig(self) -> Dict[int, int]:
        return {d.id: d.pin_fertig
                for d in self.drucker_liste() if d.pin_fertig > 0}

    def gpio_endschalter(self) -> Dict[str, int]:
        es = self.get("gpio", "endschalter", default={})
        return {k: int(v) for k, v in es.items()}

    def gpio_not_aus(self) -> Optional[dict]:
        return self.get("gpio", "not_aus")

    # ---------- Speichern ----------
    def _save(self) -> None:
        if not self._source_path:
            return
        try:
            with self._source_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(self._data, f, allow_unicode=True,
                               default_flow_style=False, sort_keys=False)
            logger.info("Konfiguration gespeichert")
        except Exception as e:
            logger.error("Konfig nicht gespeichert: %s", e)
            return
        for cb in list(self._save_listeners):
            try: cb()
            except Exception: logger.exception("save-listener")

    def on_save(self, callback) -> None:
        self._save_listeners.append(callback)


def load_config(path: Optional[str] = None) -> Config:
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates += [
        Path.cwd() / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
        Path("/etc/plattenwechsler/config.yaml"),
    ]
    for p in candidates:
        if p.is_file():
            logger.info("Lade Konfiguration aus %s", p)
            with p.open("r", encoding="utf-8") as f:
                return Config(yaml.safe_load(f), source_path=p)
    raise FileNotFoundError(
        f"Keine config.yaml gefunden. Gesucht: {[str(p) for p in candidates]}")
