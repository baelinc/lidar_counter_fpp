# Car Counter – standalone (a plain Raspberry Pi, no Falcon Player)

Use this when the lidar has to sit somewhere your FPP Pi can't reach – for example at the **entrance of your street**,
so every car passes it. It's the same counter as the FPP plugin, on its own small Pi (a **Pi Zero 2 W** is plenty), with its
own web page you open from any phone or computer.

It can still follow your show: enter the address of your **master Falcon Player** and cars are only counted while a show is
playing (if the Pi can't reach it, it uses your show hours instead). It can also read your **BaldrickSignals** board, and it
uploads to your website exactly like the FPP version.

## What you need
* Raspberry Pi Zero 2 W (or any Pi) with a power supply, in a weatherproof box
* The lidar (TFmini / TF‑Luna) – connect it with a **USB‑to‑serial adapter** (CP2102), or to the GPIO pins (wiring is shown on the page)
* Power and Wi‑Fi at the spot (or a long network/power run)

## Install (about 10 minutes)
1. **Put Raspberry Pi OS Lite on the SD card** with *Raspberry Pi Imager*. In the Imager's settings (gear icon) set a hostname
   (e.g. `roadcounter`), a username and password, your **Wi‑Fi**, your **time zone** and **enable SSH**.
2. Start the Pi, then from your computer: `ssh <user>@roadcounter.local`
3. Get this code onto the Pi and install it:
   ```
   sudo apt update && sudo apt install -y git
   git clone https://github.com/baelinc/lidar_counter_fpp
   cd lidar_counter_fpp
   sudo ./standalone/install.sh
   ```
   It asks you to choose a password for the settings page (or makes one up and shows it). Add `--uart` if the lidar is wired to
   the GPIO pins instead of a USB adapter (then reboot).
4. Open **http://roadcounter.local:8080/** (or the address the installer prints), log in as **admin**, and follow the
   *Let's get you set up* list on the Dashboard.

**Update later:** `cd lidar_counter_fpp && git pull && sudo ./standalone/install.sh` (your settings and counts are kept).
**Change the password:** `sudo car-counter-passwd`. **Remove:** `sudo ./standalone/uninstall.sh` (add `--purge` to delete counts too).

## Set up, in this order
1. **Sensor** – *Sensor & Schedule* tab: pick how the lidar is connected. The Dashboard pill turns green: *Sensor: OK*.
2. **Show hours** – the same tab. Add one entry per set of days with the same hours.
3. **Follow your show (optional)** – set *Count cars* to *Only while FPP is playing* and enter your master Falcon Player's address.
   The schedule stays as the backup.
4. **Count one lane (optional)** – see below.
5. **Website** – *Website Sync* tab: paste your site address and secret from the WordPress plugin, press *Test connection*.
6. **Crowd board (optional)** – *Crowd (phones)* tab (the Pi must be on the same network as the board).

## Counting each car once on a two‑way road
At the entrance of a dead‑end street every car passes twice – arriving and leaving. Mount the sensor on the show side of the
road, looking straight across. Arriving cars use the far lane; leaving cars use the near lane. In *Sensor & Schedule* use
**Count only one lane**: put a car (or yourself) in the near lane and press *Record near lane*, then the far lane and press
*Record far lane*, then *Use these settings*. Leaving cars are now ignored and each car is counted once. Drive a car through
each way to check. Cars that U‑turn or drive down the middle can still be missed or miscounted.

## Good to know
* **The Pi's clock matters** – show hours use the Pi's own time zone. The installer shows it; fix with
  `sudo timedatectl set-timezone America/Chicago`. A Pi has no clock battery, so it needs Wi‑Fi to set the time after power‑ups.
* **Only one device should upload to your website.** If this Pi counts the cars, turn *Website Sync* off in the FPP plugin,
  otherwise the FPP's zero counts can overwrite the real ones.
* **Security** – the page asks for a password (user `admin`). Keep it on your home network; don't forward the port to the internet.
* Logs: *Log* tab, or `journalctl -u car-counter -u car-counter-web`. Services: `systemctl status car-counter car-counter-web`.
* Settings and counts live in `/var/lib/car-counter`. Back that folder up if you care about the history.
