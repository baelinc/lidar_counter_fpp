#!/bin/bash
# Called by FPP's Plugin Manager after install / update.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
SUDO=""
[ "$(id -u)" != "0" ] && SUDO="sudo -n"

chmod +x "$DIR"/scripts/*.sh "$DIR"/counter/*.py 2>/dev/null
mkdir -p /home/fpp/media/config/fpp-car-counter /home/fpp/media/logs 2>/dev/null
if id fpp >/dev/null 2>&1; then
    $SUDO chown -R fpp:fpp /home/fpp/media/config/fpp-car-counter 2>/dev/null
    # the fpp user needs access to /dev/ttyAMA0, /dev/ttyS0, /dev/ttyUSB0 ...
    $SUDO usermod -a -G dialout fpp 2>/dev/null
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found - the car counter needs it." >&2
    exit 1
fi

"$DIR/scripts/service.sh" restart
echo "Car Counter installed. Open Status/Control > Car Counter to configure it."
echo "If you use the Pi's GPIO serial pins, run:  sudo $DIR/scripts/enable_uart.sh  (then reboot)"
exit 0
