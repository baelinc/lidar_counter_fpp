#!/bin/bash
# Start / stop the car counter daemon.   Usage: service.sh start|stop|restart|status
# Safe to call repeatedly (e.g. from FPP's postStart hook and from the web UI).

# FPP may run plugin hooks as root; the daemon and the web UI must share one user.
if [ "$(id -u)" = "0" ] && id fpp >/dev/null 2>&1; then
    if command -v runuser >/dev/null 2>&1; then
        exec runuser -u fpp -- "$0" "$@"
    fi
    exec sudo -u fpp -H "$0" "$@"
fi

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="${CC_RUN_DIR:-/dev/shm/fpp-car-counter}"
PIDFILE="$RUN_DIR/supervisor.pid"

mkdir -p "$RUN_DIR/cmd" 2>/dev/null
chmod 777 "$RUN_DIR" "$RUN_DIR/cmd" 2>/dev/null

is_running() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null
}

case "$1" in
    start)
        if is_running; then echo "already running"; exit 0; fi
        setsid nohup "$PLUGIN_DIR/scripts/supervisor.sh" >/dev/null 2>&1 </dev/null &
        sleep 1
        if is_running; then echo "started"; else echo "failed to start" >&2; exit 1; fi
        ;;
    stop)
        if ! is_running; then echo "not running"; rm -f "$PIDFILE"; exit 0; fi
        PID="$(cat "$PIDFILE")"
        kill -TERM "$PID" 2>/dev/null
        for _ in $(seq 1 30); do
            kill -0 "$PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -0 "$PID" 2>/dev/null && kill -KILL "$PID" 2>/dev/null
        rm -f "$PIDFILE"
        echo "stopped"
        ;;
    restart)
        "$0" stop
        "$0" start
        ;;
    status)
        if is_running; then echo "running"; else echo "stopped"; exit 3; fi
        ;;
    *)
        echo "usage: $0 start|stop|restart|status" >&2
        exit 2
        ;;
esac
