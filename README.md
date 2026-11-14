# FPP Car Counter (lidar_counter_fpp)

Counts the cars that visit your display using a **TFmini / TFmini‑S / TFmini Plus / TF‑Luna** lidar on a Raspberry Pi
serial port, keeps nightly and hourly totals, and uploads them to your WordPress site every night
(companion plugin: *Light Show Car Counter*).

Runs happily next to an LED sign on the same Pi. Python standard library only – nothing to `pip install`.

## Features
* Live dashboard in FPP: tonight / last night / season totals, live distance bar, hourly and nightly charts, CSV export
* **Test mode** (cars shown but not recorded) for aiming and tuning, one‑click **Calibrate empty road**
* Smart counting: a car counts once when it has been in the beam for *confirm time*; slow, stopped or bumper‑to‑bumper cars are not double counted; single glitch frames are ignored
* Counting schedule: any number of schedule entries, each with its own days and start/end time (e.g. Sun–Thu 5:30–10:00 PM **and** Fri–Sat 5:30–11:00 PM). An entry that ends before it starts runs past midnight and belongs to the day it started. Or count only while FPP is playing (+grace period), or always. Detections outside the schedule are kept as **off‑hours** and never added to totals
* "Show night" rollover (default 6 am) so cars after midnight belong to the right night
* Manual +1 / −1 / reset tonight (reset is recoverable – events are voided, not deleted)
* Warnings: sensor silent, beam blocked for too long, last website upload failed
* **Website sync**: nightly upload (with catch‑up after a power cut or site outage and automatic retries), optional live updates every N minutes, HMAC‑signed so only your Pi can write to your site
* Survives crashes (supervisor restarts the counter) and reboots; status files live in RAM (`/dev/shm`) to spare the SD card

## Install
**Option A – copy the folder (no GitHub needed)**
```
# from your computer:
scp -r lidar_counter_fpp fpp@<your-fpp-address>:/home/fpp/media/plugins/
# on the Pi (ssh fpp@<address>):
sudo /home/fpp/media/plugins/lidar_counter_fpp/scripts/fpp_install.sh
```
Then reload the FPP page: **Status/Control → Car Counter**.

**Option B – FPP Plugin Manager (recommended)**: in *Content Setup → Plugin Manager* paste
`https://raw.githubusercontent.com/baelinc/lidar_counter_fpp/main/pluginInfo.json` and click *Retrieve Plugin Info*, then *Install*.

## Wiring – choose one
In the plugin's **Sensor & Schedule** tab, set *How is the lidar connected?* to match. The page shows the matching wiring table.

### Option 1 – USB-to-serial adapter (CP2102 etc.) – easiest, recommended
No serial-port setup, no reboot, and no conflict with LED-panel HATs. Plug the adapter into any USB port on the Pi.

| Lidar wire | Adapter pin |
|---|---|
| Red (5 V) | 5V |
| Black (GND) | GND |
| Green (lidar TX) | RXD |
| White (lidar RX) | TXD |

The data wires **cross over** (lidar TX → adapter RXD). Power the lidar from the adapter's 5V pin; the data signals are 3.3 V, so if your adapter has a 3.3V/5V logic selector, choose 3.3V. The plugin auto-detects the adapter (a CP210x is preferred if several USB serial devices are plugged in) and recovers by itself if it is unplugged and plugged back in.

### Option 2 – Pi GPIO header pins
| Lidar wire | Pi pin |
|---|---|
| Red (5 V) | 2 (5 V) |
| Black (GND) | 6 (GND) |
| Green (lidar TX) | 10 (GPIO15 / RXD) |
| White (lidar RX) | 8 (GPIO14 / TXD) |

First time using the GPIO serial port? Run once and reboot:
`sudo /home/fpp/media/plugins/lidar_counter_fpp/scripts/enable_uart.sh`
(backs up `config.txt`/`cmdline.txt`, enables the UART and frees it from the login console).
If an LED-panel HAT/bonnet uses those GPIO pins, use Option 1 instead.

*Wire colours vary between sensor models – check your sensor's datasheet.* *Custom serial port* (advanced) lets you type any device path.

## Set‑up
1. **Sensor & Schedule tab** – pick how the lidar is connected and check the baud rate (115200 is the factory default), build your show schedule (one entry per set of days with the same hours; *Every day / Weekdays / Weekends* shortcuts help) and save.
2. Aim the sensor across the lane the cars use at about bumper height, so an empty road reads *no return* (or something far away).
3. Dashboard → **Test mode**, drive/walk past, watch the live bar and the *test cars* counter. Adjust *Confirm time* (raise it to ignore people/animals).
4. With the road clear, press **Calibrate empty road** – it sets *Farthest distance* just inside whatever the sensor sees as background.
5. Turn test mode off. Done.
6. **Website Sync tab** – paste the website address and secret from the WordPress plugin, press **Test connection**, tick *Upload to website*, choose the nightly time.

## How counting works
```
IDLE ──reading between Nearest and Farthest──▶ CONFIRMING ──stays for Confirm time──▶ PRESENT  (+1 car)
PRESENT ──beam empty for Clear time──▶ IDLE
```
Distances are centimetres (switch to mm in settings only if you changed the sensor's output mode).
Typical vehicle speeds: a 4.5 m car at 15 mph is in the beam ≈ 0.7 s, at 5 mph ≈ 2 s, so the 250 ms default confirm time is comfortable for a drive‑through display.

## Files and data
| What | Where |
|---|---|
| Settings (contains the secret, mode 600) | `/home/fpp/media/config/fpp-car-counter/config.json` |
| Every counted event (SQLite) | `/home/fpp/media/config/fpp-car-counter/counter.db` – **back this up with your FPP config** |
| Log | `/home/fpp/media/logs/fpp-car-counter.log` (also in the plugin's Log tab) |
| Live status (RAM) | `/dev/shm/fpp-car-counter/` |

Uninstalling the plugin keeps your counts; delete the config folder to remove them.

## Troubleshooting
* **"Service: not running"** – Log tab → Start. Crash output appears under the log.
* **"no USB serial adapter found"** – plug the adapter into the Pi (try another port or cable), then reload the page; the plugin picks it up within seconds.
* **"cannot open /dev/serial0: No such file"** (GPIO option) – run `enable_uart.sh` and reboot.
* **"Permission denied"** – the `fpp` user must be in group `dialout` (the installer does this; reboot or re‑login after).
* **"no data from sensor"** – wiring TX/RX swapped, wrong baud, or sensor not powered (it needs 5 V).
* **Counts in the dark but not in daylight** – sunlight can blind these sensors; shade the lens.
* **Website says clock mismatch** – the Pi's clock is off by more than 15 minutes; fix FPP's time/NTP.
* **Website upload "not found"** – is the WordPress plugin active? Try opening `https://yoursite/?rest_route=/lscc/v1/public`.

## Tests
`python3 -m unittest discover -s tests -v` (uses a fake lidar on a pseudo‑terminal and a fake website).
