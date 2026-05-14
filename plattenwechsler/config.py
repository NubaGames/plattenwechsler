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

from .types import DruckerConfig

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
