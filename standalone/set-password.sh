#!/bin/bash
# Set the password for the Car Counter settings page (user: admin).
#   sudo car-counter-passwd            (asks twice)
#   printf 'secret' | sudo car-counter-passwd --stdin
set -euo pipefail
if [ "$(id -u)" != "0" ]; then echo "Run with sudo." >&2; exit 1; fi
FILE="${CC_WEB_PASSWORD_FILE:-/etc/car-counter/web.pass}"
if [ "${1:-}" = "--stdin" ]; then
    IFS= read -r PW || true
else
    read -r -s -p "New password: " PW; echo
    read -r -s -p "Again: " PW2; echo
    [ "$PW" = "$PW2" ] || { echo "Passwords differ." >&2; exit 1; }
fi
[ "${#PW}" -ge 6 ] || { echo "Use at least 6 characters." >&2; exit 1; }
mkdir -p "$(dirname "$FILE")"
printf '%s' "$PW" | php -r 'echo password_hash(stream_get_contents(STDIN), PASSWORD_DEFAULT);' > "$FILE.tmp"
chown root:carcounter "$FILE.tmp" 2>/dev/null || true
chmod 640 "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
echo "Password saved."
