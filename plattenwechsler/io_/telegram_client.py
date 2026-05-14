"""Telegram-Bot via Long-Polling. Sendet Status-Pushes und nimmt Befehle entgegen.

Befehle:
  /status            aktueller Systemstatus
  /wechsel <id>      Plattenwechsel für Drucker N starten
  /quittieren        Fehler quittieren
  /home              Referenzfahrt
  /stop              Stopp
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional, List

import urllib.parse
import urllib.request
import json

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, bot_token: str, allowed_chat_ids: List[int],
                 send_status_to_first: bool = True):
        self._token = bot_token
        self._allowed = set(int(x) for x in (allowed_chat_ids or []) if int(x) != 0)
        self._send_first = send_status_to_first
        self._stop_flag = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._last_update_id = 0
        self._bot_username = None

        self.on_befehl_status: Optional[Callable[[], str]] = None
        self.on_befehl_auftrag: Optional[Callable[[int], None]] = None
        self.on_befehl_quittieren: Optional[Callable[[], None]] = None
        self.on_befehl_home: Optional[Callable[[], None]] = None
        self.on_befehl_stop: Optional[Callable[[], None]] = None

    def is_active(self) -> bool:
        return bool(self._token) and not self._token.startswith("TOKEN")

    def start(self):
        if not self.is_active():
            logger.warning("Telegram inaktiv (kein gültiges Token)")
            return
        # Bot-Info holen
        info = self._call("getMe")
        if info and info.get("ok"):
            self._bot_username = info["result"].get("username", "?")
            logger.info("Telegram-Bot @%s verbunden", self._bot_username)
        self._stop_flag.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="TgPoll", daemon=True)
        self._poll_thread.start()

    def stop(self):
        self._stop_flag.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)

    def broadcast(self, text: str):
        if not self.is_active():
            return
        for chat_id in self._allowed:
            self._send(chat_id, text)

    def _poll_loop(self):
        while not self._stop_flag.is_set():
            try:
                upd = self._call("getUpdates", offset=self._last_update_id + 1,
                                  timeout=20)
                if not upd or not upd.get("ok"):
                    time.sleep(2.0); continue
                for u in upd["result"]:
                    self._last_update_id = max(self._last_update_id, u["update_id"])
                    msg = u.get("message") or {}
                    chat = msg.get("chat") or {}
                    chat_id = chat.get("id")
                    text = (msg.get("text") or "").strip()
                    if not chat_id or not text:
                        continue
                    if self._allowed and chat_id not in self._allowed:
                        logger.warning("Telegram: chat_id %s nicht erlaubt", chat_id)
                        continue
                    self._handle(chat_id, text)
            except Exception:
                logger.exception("Telegram poll")
                time.sleep(2.0)

    def _handle(self, chat_id: int, text: str):
        cmd = text.split()[0].lower().lstrip("/").split("@")[0]
        rest = text.split()[1:]
        try:
            if cmd in ("status", "start"):
                if self.on_befehl_status:
                    self._send(chat_id, self.on_befehl_status())
                else:
                    self._send(chat_id, "Status nicht verfügbar")
            elif cmd in ("wechsel", "auftrag"):
                if not rest:
                    self._send(chat_id, "Nutzung: /wechsel <drucker_id>")
                    return
                try:
                    did = int(rest[0])
                except ValueError:
                    self._send(chat_id, "Ungültige Drucker-ID")
                    return
                if self.on_befehl_auftrag:
                    self.on_befehl_auftrag(did)
                    self._send(chat_id, f"Auftrag für Drucker {did} angenommen")
            elif cmd == "quittieren":
                if self.on_befehl_quittieren:
                    self.on_befehl_quittieren()
                    self._send(chat_id, "Fehler quittiert")
            elif cmd == "home":
                if self.on_befehl_home:
                    self.on_befehl_home()
                    self._send(chat_id, "Referenzfahrt gestartet")
            elif cmd == "stop":
                if self.on_befehl_stop:
                    self.on_befehl_stop()
                    self._send(chat_id, "STOP gesendet")
            else:
                self._send(chat_id,
                    "Befehle: /status /wechsel <id> /quittieren /home /stop")
        except Exception as e:
            logger.exception("Telegram-Befehl")
            self._send(chat_id, f"Fehler: {e}")

    def _send(self, chat_id: int, text: str):
        try:
            self._call("sendMessage", chat_id=chat_id, text=text,
                       parse_mode="Markdown")
        except Exception:
            logger.exception("Telegram send")

    def _call(self, method: str, **params):
        if not self._token:
            return None
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        data = urllib.parse.urlencode(params).encode("ascii")
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug("Telegram %s: %s", method, e)
            return None
