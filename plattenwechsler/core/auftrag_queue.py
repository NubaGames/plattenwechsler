"""FIFO-Auftrags-Queue mit Dedup pro Drucker."""
from __future__ import annotations
import threading
from collections import deque
from typing import List, Optional

from ..types import Auftrag


class AuftragsQueue:
    def __init__(self):
        self._q: deque = deque()
        self._lock = threading.RLock()
        self._counter = 0

    def __len__(self) -> int:
        with self._lock: return len(self._q)

    def is_empty(self) -> bool:
        with self._lock: return len(self._q) == 0

    def einreihen(self, a: Auftrag) -> bool:
        with self._lock:
            if any(x.drucker_id == a.drucker_id for x in self._q):
                return False
            self._counter += 1
            a.auftrag_id = self._counter
            self._q.append(a)
            return True

    def naechsten(self) -> Optional[Auftrag]:
        with self._lock:
            return self._q.popleft() if self._q else None

    def vorne_einreihen(self, a: Auftrag) -> None:
        with self._lock:
            self._q.appendleft(a)

    def snapshot(self) -> List[Auftrag]:
        with self._lock:
            return list(self._q)

    def leeren(self) -> int:
        with self._lock:
            n = len(self._q)
            self._q.clear()
            return n

    def enthaelt_drucker(self, drucker_id: int) -> bool:
        with self._lock:
            return any(a.drucker_id == drucker_id for a in self._q)
