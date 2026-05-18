#!/bin/bash
# Laufende Instanz beenden
EXISTING=$(pgrep -f "python.*webapp.app" | grep -v $$)
if [ -n "$EXISTING" ]; then
    kill -TERM $EXISTING 2>/dev/null
    sleep 1
    kill -KILL $EXISTING 2>/dev/null || true
fi

cd /home/nura/plattenwechsler
exec python3 -m webapp.app
