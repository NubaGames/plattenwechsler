#!/bin/bash
# Plattenwechsler — Startskript
# Beendet eine laufende Instanz sauber bevor neu gestartet wird.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGFILE="$SCRIPT_DIR/plattenwechsler.log"

# ── Laufende Instanz beenden ──────────────────────────────────────────────────
EXISTING=$(pgrep -f "python.*plattenwechsler.main" | grep -v $$)
if [ -n "$EXISTING" ]; then
    echo "Beende laufende Instanz (PID $EXISTING)..."
    kill -TERM $EXISTING 2>/dev/null
    # Bis zu 5 Sekunden auf sauberes Ende warten
    for i in $(seq 1 10); do
        sleep 0.5
        kill -0 $EXISTING 2>/dev/null || break
    done
    # Notfalls hart killen
    kill -KILL $EXISTING 2>/dev/null || true
    sleep 0.5
fi

# ── Starten ───────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"
exec python3 -m plattenwechsler.main "$@"
