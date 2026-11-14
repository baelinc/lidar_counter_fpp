#!/bin/bash
# Keeps the Python daemon alive. Started by service.sh (not meant to be run by hand).
PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="${CC_RUN_DIR:-/dev/shm/fpp-car-counter}"
PIDFILE="$RUN_DIR/supervisor.pid"
ERR="${CC_ERR_FILE:-/home/fpp/media/logs/fpp-car-counter.err}"
mkdir -p "$RUN_DIR" "$(dirname "$ERR")" 2>/dev/null
: > "$ERR" 2>/dev/null
echo $$ > "$PIDFILE"

CHILD=""
cleanup() {
    if [ -n "$CHILD" ]; then
        kill -TERM "$CHILD" 2>/dev/null
        wait "$CHILD" 2>/dev/null
    fi
    [ "$(cat "$PIDFILE" 2>/dev/null)" = "$$" ] && rm -f "$PIDFILE"
    exit 0
}
trap cleanup TERM INT

while true; do
    python3 -u "$PLUGIN_DIR/counter/car_counter.py" 2>>"$ERR" &
    CHILD=$!
    wait "$CHILD"
    RC=$?
    CHILD=""
    # 0 = clean stop, 75 = another daemon already holds the lock
    if [ "$RC" -eq 0 ] || [ "$RC" -eq 75 ]; then
        [ "$(cat "$PIDFILE" 2>/dev/null)" = "$$" ] && rm -f "$PIDFILE"
        exit 0
    fi
    echo "$(date '+%F %T') daemon exited with code $RC - restarting in 5 s" >> "$ERR"
    sleep 5
done
