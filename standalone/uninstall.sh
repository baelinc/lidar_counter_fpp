#!/bin/bash
# Remove the standalone Car Counter.  Keeps your counts and settings unless you add --purge.
set -u
if [ "$(id -u)" != "0" ]; then echo "Run with sudo." >&2; exit 1; fi
systemctl disable --now car-counter car-counter-web 2>/dev/null
rm -f /etc/systemd/system/car-counter.service /etc/systemd/system/car-counter-web.service \
      /etc/sudoers.d/car-counter /etc/tmpfiles.d/car-counter.conf /usr/local/bin/car-counter-passwd
systemctl daemon-reload
rm -rf /opt/car-counter
if [ "${1:-}" = "--purge" ]; then
    rm -rf /var/lib/car-counter /var/log/car-counter /etc/car-counter
    id carcounter >/dev/null 2>&1 && userdel carcounter 2>/dev/null
    echo "Removed, including your counts and settings."
else
    echo "Removed. Your counts and settings are still in /var/lib/car-counter (add --purge to delete them)."
fi
