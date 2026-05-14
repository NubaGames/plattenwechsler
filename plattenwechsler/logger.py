"""Logging-Setup."""
from __future__ import annotations
import logging
import sys
from logging.handlers import RotatingFileHandler


def setup_logging(level: str = "INFO", log_file: str = "plattenwechsler.log") -> None:
    fmt = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(sh)

    # Datei (best-effort, fällt zurück auf cwd)
    try:
        fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
        fh.setFormatter(logging.Formatter(fmt, datefmt))
        root.addHandler(fh)
    except Exception as e:
        try:
            fallback = "plattenwechsler.log"
            fh = RotatingFileHandler(fallback, maxBytes=2_000_000, backupCount=3)
            fh.setFormatter(logging.Formatter(fmt, datefmt))
            root.addHandler(fh)
            print(f"WARN: Konnte Log nicht in {log_file} öffnen ({e}). "
                  f"Schreibe stattdessen nach {fallback}.")
        except Exception:
            print(f"WARN: Logging nur auf Konsole ({e})")
