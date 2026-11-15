#!/bin/bash
# One-time helper: free the Raspberry Pi's GPIO serial port (pins 8/10) for the lidar.
# Run once over SSH:  sudo ./enable_uart.sh   then reboot.
# Not needed if you use a USB-to-serial adapter (/dev/ttyUSB0).
set -e
if [ "$(id -u)" != "0" ]; then echo "Run with sudo." >&2; exit 1; fi

CONFIG=/boot/firmware/config.txt; [ -f "$CONFIG" ] || CONFIG=/boot/config.txt
CMDLINE=/boot/firmware/cmdline.txt; [ -f "$CMDLINE" ] || CMDLINE=/boot/cmdline.txt
STAMP=$(date +%Y%m%d%H%M%S)

if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$CONFIG.bak.$STAMP"
    if grep -q '^enable_uart=' "$CONFIG"; then
        sed -i 's/^enable_uart=.*/enable_uart=1/' "$CONFIG"
    else
        printf '\n# Added by Car Counter\nenable_uart=1\n' >> "$CONFIG"
    fi
    echo "Updated $CONFIG (backup: $CONFIG.bak.$STAMP)"
else
    echo "Could not find config.txt - enable the serial port manually with raspi-config." >&2
fi

if [ -f "$CMDLINE" ]; then
    cp "$CMDLINE" "$CMDLINE.bak.$STAMP"
    sed -i -E 's/ ?console=(serial0|ttyAMA0|ttyS0),[0-9]+//g' "$CMDLINE"
    echo "Removed serial console from $CMDLINE (backup: $CMDLINE.bak.$STAMP)"
fi

systemctl disable --now serial-getty@ttyS0.service serial-getty@ttyAMA0.service 2>/dev/null || true
usermod -a -G dialout fpp 2>/dev/null || true
usermod -a -G dialout carcounter 2>/dev/null || true
echo "Done. Reboot the Pi, then pick /dev/serial0 as the serial port in the Car Counter settings."
