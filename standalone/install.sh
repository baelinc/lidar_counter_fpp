#!/bin/bash
# Car Counter - standalone install for a plain Raspberry Pi (no FPP).
#   sudo ./standalone/install.sh [--port 8080] [--password 'secret'] [--uart] [--no-start]
# Safe to run again: it updates the program and keeps your settings and counts.
set -euo pipefail

PORT=8080; PASSWORD=""; UART=0; START=1
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="${2:?--port needs a number}"; shift 2 ;;
        --password) PASSWORD="${2:?--password needs a value}"; shift 2 ;;
        --uart) UART=1; shift ;;
        --no-start) START=0; shift ;;
        -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
case "$PORT" in ''|*[!0-9]*) echo "--port must be a number" >&2; exit 2 ;; esac

if [ "$(id -u)" != "0" ]; then echo "Run with sudo:  sudo $0" >&2; exit 1; fi
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/car-counter
USER_NAME=carcounter
ETC=/etc/car-counter
DATA=/var/lib/car-counter
LOGDIR=/var/log/car-counter

echo "== Installing packages"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 php-cli sudo ca-certificates >/dev/null
fi
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v php >/dev/null || { echo "php-cli is required (sudo apt install php-cli)" >&2; exit 1; }
SYSTEMCTL="$(command -v systemctl || true)"
[ -n "$SYSTEMCTL" ] || { echo "systemd is required" >&2; exit 1; }

echo "== Program files -> $APP"
mkdir -p "$APP"
rm -rf "$APP/counter" "$APP/standalone" "$APP/scripts"
cp -a "$SRC/counter" "$SRC/standalone" "$APP/"
mkdir -p "$APP/scripts"; cp -a "$SRC/scripts/enable_uart.sh" "$APP/scripts/"
cp -a "$SRC/lib.php" "$SRC/ajax.php" "$SRC/ui.php" "$APP/"
[ -f "$SRC/pluginInfo.json" ] && cp -a "$SRC/pluginInfo.json" "$APP/"
find "$APP" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
chmod +x "$APP"/standalone/*.sh "$APP"/scripts/*.sh "$APP"/counter/*.py 2>/dev/null || true
chown -R root:root "$APP"

echo "== Service account and folders"
id "$USER_NAME" >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin "$USER_NAME"
usermod -a -G dialout "$USER_NAME"
mkdir -p "$ETC" "$DATA" "$LOGDIR"
chown "$USER_NAME:$USER_NAME" "$DATA" "$LOGDIR"; chmod 750 "$DATA"
echo "d /run/car-counter 0775 $USER_NAME $USER_NAME -" > /etc/tmpfiles.d/car-counter.conf
systemd-tmpfiles --create /etc/tmpfiles.d/car-counter.conf

ENVF="$ETC/car-counter.env"
[ -f "$ENVF" ] || : > "$ENVF"
setenv() { grep -q "^$1=" "$ENVF" && sed -i "s|^$1=.*|$1=$2|" "$ENVF" || echo "$1=$2" >> "$ENVF"; }
setenv CC_STANDALONE 1
setenv CC_DATA_DIR "$DATA"
setenv CC_RUN_DIR /run/car-counter
setenv CC_LOG_FILE "$LOGDIR/car-counter.log"
setenv CC_ERR_FILE "$LOGDIR/car-counter.err"
setenv CC_WEB_PASSWORD_FILE "$ETC/web.pass"
setenv CC_WEB_PORT "$PORT"
setenv CC_SYSTEMCTL "$SYSTEMCTL"
chmod 644 "$ENVF"

echo "== Web page password"
install -m 755 "$APP/standalone/set-password.sh" /usr/local/bin/car-counter-passwd
if [ ! -s "$ETC/web.pass" ]; then
    GENERATED=0
    if [ -z "$PASSWORD" ]; then
        if [ -t 0 ]; then
            read -r -s -p "Choose a password for the settings page (Enter = make one up): " PASSWORD; echo
        fi
        if [ -z "$PASSWORD" ]; then PASSWORD="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 12)"; GENERATED=1; fi
    fi
    printf '%s' "$PASSWORD" | /usr/local/bin/car-counter-passwd --stdin
    [ "$GENERATED" = 1 ] && echo "   Generated password: $PASSWORD   (user: admin)   - write it down; change it with: sudo car-counter-passwd"
else
    echo "   Keeping the existing password (change it with: sudo car-counter-passwd)"
fi

echo "== Permission for the web page to restart the counter"
cat > /etc/sudoers.d/car-counter <<SUDO
$USER_NAME ALL=(root) NOPASSWD: $SYSTEMCTL start car-counter, $SYSTEMCTL stop car-counter, $SYSTEMCTL restart car-counter
SUDO
chmod 440 /etc/sudoers.d/car-counter
if command -v visudo >/dev/null 2>&1 && ! visudo -cf /etc/sudoers.d/car-counter >/dev/null; then
    rm -f /etc/sudoers.d/car-counter; echo "sudoers check failed - Restart buttons will not work" >&2
fi

echo "== systemd services"
for u in car-counter car-counter-web; do
    sed "s|@APP@|$APP|g" "$APP/standalone/systemd/$u.service" > "/etc/systemd/system/$u.service"
done
"$SYSTEMCTL" daemon-reload
"$SYSTEMCTL" enable car-counter car-counter-web >/dev/null 2>&1

if [ "$UART" = 1 ]; then
    echo "== Enabling the GPIO serial port"
    "$APP/scripts/enable_uart.sh" || echo "Could not change the serial settings - use raspi-config > Interface Options > Serial Port" >&2
    usermod -a -G dialout "$USER_NAME"
    echo "   Reboot the Pi when this finishes, then pick /dev/serial0 in the settings."
fi

if [ "$START" = 1 ]; then
    "$SYSTEMCTL" restart car-counter car-counter-web
    sleep 2
    for u in car-counter car-counter-web; do
        printf '   %-18s %s\n' "$u" "$("$SYSTEMCTL" is-active "$u" || true)"
    done
fi

TZ_NOW="$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo unknown)"
NTP_OK="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)"
IPS="$(hostname -I 2>/dev/null | tr -s ' ' | sed 's/ $//')"
echo
echo "Done. Open the settings page:"
for ip in $IPS; do echo "   http://$ip:$PORT/"; done
echo "   http://$(hostname).local:$PORT/   (user: admin)"
echo
echo "Check the Pi's clock - show hours use the Pi's own time zone."
echo "   Time zone now: $TZ_NOW   (change: sudo timedatectl set-timezone America/Chicago)   Clock synced: $NTP_OK"
echo "Only one device should upload to your website. If your FPP Pi also uploads car counts, turn its Website Sync off."
