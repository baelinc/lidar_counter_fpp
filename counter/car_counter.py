#!/usr/bin/env python3
"""
FPP Car Counter daemon.

Reads a Benewake TFmini / TFmini-S / TFmini Plus / TF-Luna lidar over UART,
counts vehicles passing the sensor, stores every event in SQLite and
(optionally) uploads nightly totals to a WordPress site.

Standard library only - nothing to pip install on the Pi.
Written for Python 3.7+ (FPP images ship 3.9 - 3.11).
"""
import csv
import datetime
import fcntl
import glob
import hashlib
import hmac
import io
import json
import logging
import logging.handlers
import os
import queue
import random
import re
import select
import signal
import sqlite3
import ssl
import sys
import termios
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.2.0"
USER_AGENT = "fpp-car-counter/" + VERSION

log = logging.getLogger("car-counter")


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
# Set by the standalone install (a plain Raspberry Pi, no FPP): there is no FPP to ask whether a show is playing.
STANDALONE = os.environ.get("CC_STANDALONE", "") == "1"


def get_paths():
    data = os.environ.get("CC_DATA_DIR", "/home/fpp/media/config/fpp-car-counter")
    run = os.environ.get("CC_RUN_DIR", "/dev/shm/fpp-car-counter")
    logf = os.environ.get("CC_LOG_FILE", "/home/fpp/media/logs/fpp-car-counter.log")
    return {
        "data": data,
        "run": run,
        "config": os.path.join(data, "config.json"),
        "db": os.path.join(data, "counter.db"),
        "log": logf,
        "status": os.path.join(run, "status.json"),
        "stats": os.path.join(run, "stats.json"),
        "cmd": os.path.join(run, "cmd"),
        "lock": os.path.join(run, "daemon.lock"),
    }


def ensure_dir(path, mode=0o775):
    try:
        os.makedirs(path, mode, exist_ok=True)
    except OSError:
        pass


def atomic_write_json(path, obj, mode=0o644):
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    os.chmod(tmp, mode)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BAUDS = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
    230400: termios.B230400,
}

# key: (kind, default, a, b)   int/float -> (min, max); choice -> (choices,);
# str -> (maxlen,)
SCHEMA = {
    "show_name": ("str", "My Light Show", 80),
    "connection": ("choice", "usb", ["usb", "gpio", "custom"]),   # how the lidar is wired to the Pi
    "usb_device": ("str", "", 120),                                # "" = auto-detect the USB adapter
    "serial_port": ("str", "", 120),                               # only used when connection == "custom"
    "baud": ("choice", 115200, list(BAUDS.keys())),
    "unit": ("choice", "cm", ["cm", "mm"]),
    "min_cm": ("int", 30, 1, 5000),
    "max_cm": ("int", 1200, 2, 20000),
    "min_strength": ("int", 0, 0, 65534),
    "confirm_ms": ("int", 250, 20, 5000),
    "clear_ms": ("int", 800, 100, 30000),
    "max_dwell_s": ("int", 120, 5, 3600),
    "schedule_mode": ("choice", "window", ["always", "window", "playing"]),
    "fpp_host": ("str", "", 120),                    # master Falcon Player to ask "is a show playing?" ("" = this Pi)
    "window_start": ("time", "17:00"),
    "window_end": ("time", "22:00"),
    "grace_min": ("int", 10, 0, 240),
    "rollover_hour": ("int", 6, 0, 12),
    "sync_enabled": ("bool", False),
    "wp_url": ("str", "", 300),
    "secret": ("str", "", 200),
    "sync_time": ("time", "23:00"),
    "sync_days": ("int", 7, 1, 60),
    "live_interval_min": ("int", 0, 0, 240),
    "verify_tls": ("bool", True),
    # BaldrickSignals crowd board (counts phones/devices; reported separately from cars)
    "people_enabled": ("bool", False),
    "people_host": ("str", "", 120),                 # IP address or hostname of the board
    "people_interval_min": ("int", 5, 1, 120),       # how often to check the board
    "people_clock": ("choice", "local", ["local", "utc"]),   # time zone of the timestamps in the board's CSV
    "people_time_col": ("int", 0, 0, 40),            # 0 = auto-detect (1 = first column)
    "people_count_col": ("int", 0, 0, 40),           # 0 = auto-detect
}


def parse_hhmm(text):
    try:
        hh, mm = str(text).strip().split(":")
        hh, mm = int(hh), int(mm)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh * 60 + mm
    except (ValueError, AttributeError):
        pass
    return None


def coerce(key, value):
    spec = SCHEMA[key]
    kind, default = spec[0], spec[1]
    try:
        if kind == "str":
            return str(value).strip()[: spec[2]]
        if kind == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if kind == "int":
            return max(spec[2], min(spec[3], int(float(value))))
        if kind == "choice":
            if isinstance(spec[2][0], int):
                value = int(value)
            return value if value in spec[2] else default
        if kind == "time":
            return value if parse_hhmm(value) is not None else default
    except (ValueError, TypeError):
        pass
    return default


def coerce_schedules(value):
    """Validate a list of {"days":[0-6 (0=Sunday)], "start":"HH:MM", "end":"HH:MM"} entries."""
    out = []
    if not isinstance(value, list):
        return out
    for entry in value[:28]:
        if not isinstance(entry, dict):
            continue
        days = set()
        raw_days = entry.get("days")
        for d in (raw_days if isinstance(raw_days, list) else []):
            try:
                if 0 <= int(d) <= 6:
                    days.add(int(d))
            except (TypeError, ValueError):
                pass
        start, end = str(entry.get("start", "")).strip(), str(entry.get("end", "")).strip()
        if not days or parse_hhmm(start) is None or parse_hhmm(end) is None:
            continue
        out.append({"days": sorted(days), "start": start, "end": end})
    return out


def list_usb_ports(root="/dev"):
    """USB serial adapters, best first. Prefers the stable /dev/serial/by-id names and
    puts Silicon Labs CP210x (CP2102) adapters ahead of any other USB serial device."""
    ports = sorted(glob.glob(os.path.join(root, "serial", "by-id", "*")))
    if not ports:
        ports = sorted(glob.glob(os.path.join(root, "ttyUSB*"))) + sorted(glob.glob(os.path.join(root, "ttyACM*")))
    ports.sort(key=lambda p: 0 if ("cp210" in p.lower() or "silicon_labs" in p.lower()) else 1)
    return ports


def resolve_port(cfg, root="/dev"):
    """Serial device to open for this configuration, or None if there is nothing to open yet."""
    mode = cfg["connection"]
    if mode == "gpio":
        return "/dev/serial0"
    if mode == "usb":
        found = list_usb_ports(root)
        if cfg["usb_device"] and (cfg["usb_device"] in found or os.path.exists(cfg["usb_device"])):
            return cfg["usb_device"]
        return found[0] if found else None
    return cfg["serial_port"] or None


def infer_connection(raw):
    """Configs saved before the connection option existed only had serial_port."""
    port = str(raw.get("serial_port", "")).strip()
    if not port:
        return "usb", ""
    if port == "/dev/serial0":
        return "gpio", ""
    if port.startswith(("/dev/ttyUSB", "/dev/ttyACM", "/dev/serial/by-id")):
        return "usb", port
    return "custom", ""


def normalize_config(raw):
    cfg = {}
    for key, spec in SCHEMA.items():
        cfg[key] = coerce(key, raw[key]) if key in raw else spec[1]
    if "connection" not in raw:
        cfg["connection"], guessed = infer_connection(raw)
        if guessed and "usb_device" not in raw:
            cfg["usb_device"] = guessed
    if isinstance(raw.get("schedules"), list):
        cfg["schedules"] = coerce_schedules(raw["schedules"])
    else:  # older config (single window) or fresh install: one entry for every day
        cfg["schedules"] = [{"days": list(range(7)), "start": cfg["window_start"], "end": cfg["window_end"]}]
    if cfg["max_cm"] <= cfg["min_cm"]:
        cfg["max_cm"] = cfg["min_cm"] + 10
    cfg["wp_url"] = cfg["wp_url"].rstrip("/")
    cfg["people_host"] = normalize_board_host(cfg["people_host"])
    cfg["fpp_host"] = normalize_board_host(cfg["fpp_host"])
    if STANDALONE and cfg["schedule_mode"] == "playing" and not cfg["fpp_host"]:
        cfg["schedule_mode"] = "window"          # nothing to ask without the Falcon Player's address
    return cfg


class Config:
    def __init__(self, path):
        self.path = path
        self.values = normalize_config({})
        self._mtime = None
        self.reload_if_changed(force=True)

    def reload_if_changed(self, force=False):
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            mtime = None
        if not force and mtime == self._mtime:
            return False
        self._mtime = mtime
        raw = {}
        if mtime is not None:
            try:
                with open(self.path) as fh:
                    raw = json.load(fh)
                if not isinstance(raw, dict):
                    raw = {}
            except (OSError, ValueError) as exc:
                log.error("Could not read config: %s", exc)
        self.values = normalize_config(raw)
        return True

    def update(self, changes):
        merged = dict(self.values)
        for key, val in changes.items():
            if key in SCHEMA:
                merged[key] = val
        self.values = normalize_config(merged)
        atomic_write_json(self.path, self.values, 0o600)
        try:
            self._mtime = os.stat(self.path).st_mtime
        except OSError:
            pass

    def __getitem__(self, key):
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)


# --------------------------------------------------------------------------
# Sensor protocol
# --------------------------------------------------------------------------
class TFParser:
    """Parses the 9 byte frame used by TFmini / TFmini-S / TFmini Plus / TF-Luna.

    0x59 0x59 distL distH strengthL strengthH tempL tempH checksum
    """

    def __init__(self):
        self.buf = bytearray()
        self.bad_frames = 0

    def feed(self, data):
        buf = self.buf
        buf.extend(data)
        out = []
        n = len(buf)
        i = 0
        while i + 9 <= n:
            if buf[i] == 0x59 and buf[i + 1] == 0x59:
                if (sum(buf[i:i + 8]) & 0xFF) == buf[i + 8]:
                    dist = buf[i + 2] | (buf[i + 3] << 8)
                    strength = buf[i + 4] | (buf[i + 5] << 8)
                    out.append((dist, strength))
                    i += 9
                    continue
                self.bad_frames += 1
            i += 1
        del buf[:i]
        return out


def open_serial(port, baud):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attrs = termios.tcgetattr(fd)
        speed = BAUDS[baud]
        attrs[0] = 0                                    # iflag
        attrs[1] = 0                                    # oflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0                                    # lflag (raw)
        attrs[4] = speed
        attrs[5] = speed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)
    except Exception:
        os.close(fd)
        raise
    return fd


# --------------------------------------------------------------------------
# Vehicle detection state machine (pure logic, no I/O -> unit testable)
# --------------------------------------------------------------------------
IDLE, CONFIRMING, PRESENT = "idle", "confirming", "present"


class Detector:
    """
    A reading is "in zone" when min_cm <= distance <= max_cm (and strong enough).
    Aim the sensor across the road so an empty road reads 0 / out of range (or
    farther than max_cm) and a car in the beam reads closer.

      IDLE --in zone--> CONFIRMING --in zone for confirm_ms--> PRESENT (COUNT!)
      PRESENT --out of zone for clear_ms--> IDLE

    A car is counted once, as soon as it has been in the beam for confirm_ms.
    It cannot be counted again until the beam has been clear for clear_ms,
    so a slow or stopped car (or one with windows the beam passes through)
    is still a single vehicle.
    """
    GLITCH_S = 0.05  # single bad frames shorter than this are ignored while confirming

    def __init__(self):
        self.state = IDLE
        self.in_zone = False
        self.stuck = False
        self.t_first_in = None
        self.t_last_in = None
        self.t_present = None
        self.t_out = None
        self.set_params(30, 1200, 0, 250, 800, 120)

    def set_params(self, min_cm, max_cm, min_strength, confirm_ms, clear_ms, max_dwell_s):
        self.min_cm = min_cm
        self.max_cm = max_cm
        self.min_strength = min_strength
        self.confirm_s = confirm_ms / 1000.0
        self.clear_s = clear_ms / 1000.0
        self.max_dwell_s = max_dwell_s

    def reset(self):
        self.state = IDLE
        self.in_zone = False
        self.stuck = False
        self.t_first_in = self.t_last_in = self.t_present = self.t_out = None

    def _zone(self, dist_cm, strength):
        if dist_cm is None or dist_cm <= 0:
            return False
        if strength < self.min_strength:
            return False
        return self.min_cm <= dist_cm <= self.max_cm

    def feed(self, now, dist_cm, strength=0):
        """Returns "car" when a new vehicle has just been counted, else None."""
        inz = self._zone(dist_cm, strength)
        self.in_zone = inz
        event = None
        if self.state == IDLE:
            if inz:
                self.state = CONFIRMING
                self.t_first_in = self.t_last_in = now
        elif self.state == CONFIRMING:
            if inz:
                self.t_last_in = now
                if now - self.t_first_in >= self.confirm_s:
                    self.state = PRESENT
                    self.t_present = now
                    self.t_out = None
                    self.stuck = False
                    event = "car"
            elif now - self.t_last_in > self.GLITCH_S:
                self.state = IDLE
        else:  # PRESENT
            if inz:
                self.t_out = None
            elif self.t_out is None:
                self.t_out = now
            elif now - self.t_out >= self.clear_s:
                self.state = IDLE
                self.t_out = None
                self.stuck = False
            if self.state == PRESENT:
                self.stuck = (now - self.t_present) > self.max_dwell_s
        return event

    def present_seconds(self, now):
        if self.state == PRESENT and self.t_present is not None:
            return now - self.t_present
        return 0.0


# --------------------------------------------------------------------------
# Schedule
# --------------------------------------------------------------------------
def show_date_for(dt, rollover_hour):
    """The 'show night' an event belongs to; nights roll over at rollover_hour."""
    return (dt - datetime.timedelta(hours=rollover_hour)).date().isoformat()


def schedule_active(entries, dt):
    """True if dt falls inside any entry. An entry whose end is earlier than its start runs
    past midnight and belongs to the day it started on (Friday 17:00-01:00 covers Sat 00:30).
    start == end means the whole day."""
    weekday = (dt.weekday() + 1) % 7          # 0 = Sunday
    yesterday = (weekday - 1) % 7
    minute = dt.hour * 60 + dt.minute
    for entry in entries:
        start, end = parse_hhmm(entry["start"]), parse_hhmm(entry["end"])
        days = entry["days"]
        if start == end:
            if weekday in days:
                return True
        elif start < end:
            if weekday in days and start <= minute < end:
                return True
        else:
            if (weekday in days and minute >= start) or (yesterday in days and minute < end):
                return True
    return False


def counting_state(cfg, dt, fpp_playing, fpp_last_playing_ts, now_ts, fpp_known=True):
    """Returns (counting_active, reason)."""
    mode = cfg["schedule_mode"]
    if mode == "always":
        return True, "always on"
    if mode == "playing" and cfg.get("fpp_host") and not fpp_known and cfg["schedules"]:
        # A remote Falcon Player cannot be reached (Wi-Fi drop, FPP rebooting): rather than count nothing, use the schedule.
        inside = schedule_active(cfg["schedules"], dt)
        return inside, "FPP unreachable - using schedule (" + ("inside" if inside else "outside") + " show hours)"
    if mode == "window":
        inside = schedule_active(cfg["schedules"], dt)
        if not cfg["schedules"]:
            return False, "no schedule entries"
        return inside, ("inside show hours" if inside else "outside show hours")
    # mode == "playing"
    if fpp_playing:
        return True, "FPP is playing"
    if fpp_last_playing_ts and now_ts - fpp_last_playing_ts <= cfg["grace_min"] * 60:
        return True, "grace period after show"
    return False, "FPP is idle"


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
COUNTED = "('car','manual')"


class Store:
    def __init__(self, path):
        self.path = path
        self._local = threading.local()
        self._lock = threading.Lock()
        self.version = 0
        db = self._db()
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                show_date TEXT NOT NULL,
                hour INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                kind TEXT NOT NULL,
                void INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_events_date ON events(show_date);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS people_samples (
                ts INTEGER PRIMARY KEY,
                show_date TEXT NOT NULL,
                count INTEGER NOT NULL,
                counted INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_people_date ON people_samples(show_date);
            """
        )

    def _db(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
            self._local.conn = conn
        return conn

    def _bump(self):
        with self._lock:
            self.version += 1

    def add_event(self, ts, show_date, hour, delta, kind):
        self._db().execute(
            "INSERT INTO events (ts, show_date, hour, delta, kind) VALUES (?,?,?,?,?)",
            (int(ts), show_date, int(hour), int(delta), kind),
        )
        self._bump()

    def void_day(self, show_date):
        cur = self._db().execute(
            "UPDATE events SET void=1 WHERE show_date=? AND void=0", (show_date,)
        )
        self._bump()
        return cur.rowcount

    def day(self, show_date):
        rows = self.days(show_date, show_date)
        if rows:
            return rows[0]
        return {"date": show_date, "total": 0, "offhours": 0, "hours": [0] * 24,
                "first_ts": None, "last_ts": None}

    def days(self, since_date, until_date=None):
        db = self._db()
        until = until_date or "9999-12-31"
        base = {}
        for sd, total, off, first, last in db.execute(
            "SELECT show_date,"
            " SUM(CASE WHEN kind IN " + COUNTED + " AND void=0 THEN delta ELSE 0 END),"
            " SUM(CASE WHEN kind='offhours' AND void=0 THEN delta ELSE 0 END),"
            " MIN(CASE WHEN kind='car' AND void=0 THEN ts END),"
            " MAX(CASE WHEN kind='car' AND void=0 THEN ts END)"
            " FROM events WHERE show_date>=? AND show_date<=? GROUP BY show_date ORDER BY show_date",
            (since_date, until),
        ):
            base[sd] = {"date": sd, "total": max(0, int(total or 0)), "offhours": int(off or 0),
                        "hours": [0] * 24, "first_ts": first, "last_ts": last}
        for sd, hour, n in db.execute(
            "SELECT show_date, hour, SUM(delta) FROM events"
            " WHERE kind IN " + COUNTED + " AND void=0 AND show_date>=? AND show_date<=?"
            " GROUP BY show_date, hour",
            (since_date, until),
        ):
            if sd in base and 0 <= hour <= 23:
                base[sd]["hours"][hour] = max(0, int(n or 0))
        return [base[k] for k in sorted(base)]

    def season_total(self):
        row = self._db().execute(
            "SELECT COALESCE(SUM(delta),0) FROM events WHERE kind IN " + COUNTED + " AND void=0"
        ).fetchone()
        return max(0, int(row[0]))

    # ---- crowd (BaldrickSignals) samples ---------------------------------
    def add_people_samples(self, rows):
        """rows: (ts, show_date, count, counted). Returns how many were new."""
        if not rows:
            return 0
        db = self._db()
        before = db.execute("SELECT COUNT(*) FROM people_samples").fetchone()[0]
        db.execute("BEGIN")
        try:
            db.executemany("INSERT OR IGNORE INTO people_samples (ts, show_date, count, counted) VALUES (?,?,?,?)",
                           [(int(t), sd, max(0, int(c)), 1 if k else 0) for t, sd, c, k in rows])
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        added = db.execute("SELECT COUNT(*) FROM people_samples").fetchone()[0] - before
        if added:
            self._bump()
        return added

    def people_days(self, since_date, until_date=None):
        """{date: {"people": estimated visitors, "people_peak": busiest moment, "samples": n}} (show hours only)."""
        until = until_date or "9999-12-31"
        out, cur_date, cur = {}, None, []
        for sd, ts, count in self._db().execute(
            "SELECT show_date, ts, count FROM people_samples WHERE counted=1 AND show_date>=? AND show_date<=?"
            " ORDER BY show_date, ts", (since_date, until)):
            if sd != cur_date:
                if cur_date is not None:
                    out[cur_date] = estimate_people(cur)
                cur_date, cur = sd, []
            cur.append((ts, count))
        if cur_date is not None:
            out[cur_date] = estimate_people(cur)
        return out

    def people_latest(self):
        row = self._db().execute("SELECT ts, count FROM people_samples ORDER BY ts DESC LIMIT 1").fetchone()
        return {"ts": row[0], "count": row[1]} if row else None

    def people_prune(self, keep_days=500):
        cutoff = int(time.time()) - keep_days * 86400
        self._db().execute("DELETE FROM people_samples WHERE ts<?", (cutoff,))

    def meta_get(self, key, default=None):
        row = self._db().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def meta_set(self, key, value):
        self._db().execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, str(value)))


# --------------------------------------------------------------------------
# BaldrickSignals crowd board
#
# The board estimates how many phones/devices are nearby (every 30 s) and serves its history as
# CSV at http://<board>/csv.  The column layout is not documented, so the reader auto-detects the
# timestamp and count columns (and lets the user override them).
# --------------------------------------------------------------------------
def normalize_board_host(text):
    """'http://192.168.1.50/csv' -> '192.168.1.50'.  Returns '' for anything that is not a host."""
    t = str(text or "").strip()
    t = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", t)
    t = t.split("/")[0].split("?")[0].strip()
    return t if re.match(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?(:\d{1,5})?$", t) else ""


def board_urls(host, since=None):
    """Addresses to try, newest firmware first.  The board's log endpoint accepts a `from` time (epoch
    seconds) so only new readings are downloaded; the older /csv endpoint returns the whole history."""
    host = normalize_board_host(host)
    if not host:
        return []
    q = "format=csv&mark_discontinuities=0"
    if since is not None:
        q += "&from=%d" % max(0, int(since))
    return ["http://%s/turnip_data_log/data?%s" % (host, q), "http://%s/csv" % host]


def fetch_board_csv(host, since=None, timeout=12, max_bytes=16 << 20):
    """Download the board's readings as CSV.  Returns (ok, text-or-error-message, url used)."""
    urls = board_urls(host, since)
    if not urls:
        return False, "Enter the board's IP address (for example 192.168.1.50).", ""
    error = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,text/plain,*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            error = "The board answered HTTP %d for %s." % (exc.code, urllib.parse.urlsplit(url).path)
            if exc.code == 404:
                continue                               # older firmware: try the next address
            return False, error, url
        except (OSError, urllib.error.URLError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            return False, "Could not reach the board at %s (%s)." % (normalize_board_host(host), reason), url
        if len(raw) > max_bytes:
            raw = raw[-max_bytes:]                      # keep the newest part; the oldest rows are the least useful
            raw = raw[raw.find(b"\n") + 1:] if b"\n" in raw else raw
        return True, raw.decode("utf-8", "replace"), url
    return False, error or "The board did not answer.", urls[-1]


_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_DATE_FORMATS_ISO = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")
_DATE_ONLY = ("%Y-%m-%d", "%Y/%m/%d")


def _slash_formats(dayfirst):
    order = ("%d/%m", "%m/%d") if dayfirst else ("%m/%d", "%d/%m")
    out = []
    for dm in order[:1]:
        for year in ("%Y", "%y"):
            for tm in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
                out.append("%s/%s %s" % (dm, year, tm))
    return out


def parse_time_cell(cell, clock="local", dayfirst=False):
    """Timestamp text -> epoch seconds (float) or None."""
    c = str(cell).strip().strip('"')
    if not c:
        return None
    if _NUMBER.match(c):
        v = float(c)
        if 1e9 <= v < 1e11:
            return v
        if 1e12 <= v < 1e14:
            return v / 1000.0
        return None
    dt = None
    if re.search(r"(Z|[+-]\d\d:?\d\d)$", c) and "T" in c.replace(" ", "T", 1):
        try:
            dt = datetime.datetime.fromisoformat(c.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is None:
        for fmt in _DATE_FORMATS_ISO + tuple(_slash_formats(dayfirst)):
            try:
                dt = datetime.datetime.strptime(c, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        if clock == "utc":
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            return dt.timestamp()                       # naive = the Pi's local time
    return dt.timestamp()


def _looks_like_date_only(cell):
    c = str(cell).strip()
    for fmt in _DATE_ONLY:
        try:
            datetime.datetime.strptime(c, fmt)
            return True
        except ValueError:
            pass
    return bool(re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", c))


def _looks_like_time_only(cell):
    return bool(re.match(r"^\d{1,2}:\d{2}(:\d{2})?(\s?[AaPp][Mm])?$", str(cell).strip()))


def _infer_dayfirst(values):
    a_big = b_big = False
    for v in values:
        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/\d{2,4}", str(v))
        if m:
            a_big = a_big or int(m.group(1)) > 12
            b_big = b_big or int(m.group(2)) > 12
    return a_big and not b_big


def parse_board_csv(text, time_col=0, count_col=0, clock="local"):
    """Parse the board's CSV.  time_col / count_col are 1-based overrides (0 = auto-detect).
    Returns a dict: ok, error, header, delimiter, time_col, count_col (0-based or None),
    combined (date+time in two columns), rows [(epoch, count)], lines (a few raw lines), total_rows."""
    res = {"ok": False, "error": "", "header": None, "delimiter": ",", "time_col": None, "count_col": None,
           "combined": False, "rows": [], "lines": [], "total_rows": 0}
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    if not lines:
        res["error"] = "The board returned an empty CSV."
        return res
    res["lines"] = lines[:4] + (["…"] + lines[-2:] if len(lines) > 7 else lines[4:])
    sample = "\n".join(lines[:20])
    delim = max([",", ";", "\t", "|"], key=lambda d: sample.count(d))
    res["delimiter"] = delim
    try:
        table = [[c.strip() for c in row] for row in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)]
    except csv.Error as exc:
        res["error"] = "Could not read the CSV (%s)." % exc
        return res
    ncols = max(len(r) for r in table)

    def is_num(c):
        return bool(_NUMBER.match(c))

    # header: first row with no numbers and no timestamps in it
    header = None
    first = table[0]
    if first and not any(is_num(c) or parse_time_cell(c) is not None or _looks_like_date_only(c) for c in first if c):
        header = first
        table = table[1:]
    res["header"] = header
    res["total_rows"] = len(table)
    if not table:
        res["error"] = "The CSV has a header but no data rows yet."
        return res
    body = table[-400:] if len(table) > 400 else table      # sample for column detection

    def col_values(i):
        return [r[i] for r in body if i < len(r) and r[i] != ""]

    dayfirst = False
    for i in range(ncols):
        dayfirst = dayfirst or _infer_dayfirst(col_values(i))

    def col_is_time(i):
        vals = col_values(i)
        return bool(vals) and all(parse_time_cell(v, clock, dayfirst) is not None for v in vals)

    hname = lambda i: (header[i].lower() if header and i < len(header) else "")

    # ---- timestamp column
    tcol = time_col - 1 if time_col > 0 and time_col <= ncols else None
    if tcol is None:
        cands = [i for i in range(ncols) if col_is_time(i)]
        named = [i for i in cands if re.search(r"time|date|stamp|when|epoch|\bts\b", hname(i))]
        tcol = (named or cands or [None])[0]
    dcol = None
    if tcol is None:                                          # separate date and time columns?
        for i in range(ncols - 1):
            dv, tv = col_values(i), col_values(i + 1)
            if dv and tv and all(_looks_like_date_only(v) for v in dv) and all(_looks_like_time_only(v) for v in tv):
                dcol, tcol = i, i + 1
                break
    res["time_col"], res["combined"] = tcol, dcol is not None

    # ---- count column
    ccol = count_col - 1 if count_col > 0 and count_col <= ncols else None
    skip = {tcol, dcol}
    if ccol is None:
        numeric = [i for i in range(ncols) if i not in skip and col_values(i) and all(is_num(v) for v in col_values(i))]
        for pattern in (r"people|crowd|attend|visitor|estimate|audience", r"device|signal|count|number|total|detect"):
            hit = [i for i in numeric if re.search(pattern, hname(i))]
            if hit:
                ccol = hit[0]
                break
        if ccol is None and numeric:
            ccol = numeric[-1]                                # last numeric column is usually the adjusted number
    res["count_col"] = ccol
    if ccol is None:
        res["error"] = "Could not find a numeric column with the device count. Set the count column manually."
        return res

    rows = []
    for r in table:
        if ccol >= len(r) or not is_num(r[ccol]):
            continue
        count = max(0, int(round(float(r[ccol]))))
        if tcol is None:
            rows.append((None, count))
            continue
        cell = (r[dcol] + " " + r[tcol]) if dcol is not None and tcol < len(r) and dcol < len(r) else (r[tcol] if tcol < len(r) else "")
        ts = parse_time_cell(cell, clock, dayfirst)
        if ts is not None:
            rows.append((ts, count))
    res["rows"] = rows
    res["ok"] = bool(rows)
    if not rows:
        res["error"] = "No usable rows found (check the time and count columns)."
    return res


def _median3(values):
    out = []
    for i, v in enumerate(values):
        a = values[i - 1] if i > 0 else v
        b = values[i + 1] if i + 1 < len(values) else v
        out.append(sorted((a, v, b))[1])
    return out


def estimate_people(samples, gap_s=1800):
    """samples: [(ts, count)] for one show night, oldest first.
    The board reports roughly how many devices are nearby right now, so the estimated number of
    visitors is the sum of the increases (arrivals) between readings, after a light median filter
    that removes one-reading blips.  A gap longer than gap_s starts a fresh baseline.
    Returns {"people": est. visitors, "people_peak": most at once, "samples": n}."""
    if not samples:
        return {"people": 0, "people_peak": 0, "samples": 0}
    smooth = _median3([c for _, c in samples])
    total, prev, prev_ts = 0, 0, None
    for (ts, _), c in zip(samples, smooth):
        if prev_ts is not None and ts - prev_ts > gap_s:
            prev = 0
        if c > prev:
            total += c - prev
        prev, prev_ts = c, ts
    return {"people": int(total), "people_peak": int(max(smooth)), "samples": len(samples)}


# --------------------------------------------------------------------------
# Website sync
# --------------------------------------------------------------------------
def sign_body(secret, timestamp, body_bytes):
    msg = str(int(timestamp)).encode() + b"." + body_bytes
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def post_signed(base_url, route, payload, secret, verify_tls=True, timeout=20):
    """POST a signed JSON body to the WordPress plugin.

    Returns (ok, message, data). Tries pretty permalinks first, then ?rest_route=.
    Redirects (http->https, www) are followed manually so the POST body survives.
    """
    if not base_url.lower().startswith(("http://", "https://")):
        return False, "The website address must start with http:// or https://", None
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-LSCC-Timestamp": str(ts),
        "X-LSCC-Signature": sign_body(secret, ts, body),
    }
    ctx = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    candidates = [
        base_url + "/wp-json/lscc/v1/" + route,
        base_url + "/index.php?rest_route=/lscc/v1/" + route,
    ]
    last = (False, "No response", None)
    for url in candidates:
        for _hop in range(4):
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with opener.open(req, timeout=timeout) as resp:
                    raw = resp.read(1 << 20)
                    code = resp.status
            except urllib.error.HTTPError as err:
                raw, code = err.read(1 << 20), err.code
                if code in (301, 302, 303, 307, 308) and err.headers.get("Location"):
                    url = urllib.parse.urljoin(url, err.headers["Location"])
                    continue
            except (urllib.error.URLError, OSError, ssl.SSLError, ValueError) as err:
                reason = getattr(err, "reason", err)
                return False, "Could not reach website: %s" % reason, None
            break
        else:
            return False, "Too many redirects - check the website address", None
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            data = None
        if code == 200 and isinstance(data, dict) and data.get("ok"):
            return True, "OK", data
        if code == 404:
            last = (False, "Plugin endpoint not found. Is 'Light Show Car Counter' active "
                           "on the website and the REST API enabled?", data)
            continue
        msg = (data or {}).get("message") if isinstance(data, dict) else None
        code_name = (data or {}).get("code") if isinstance(data, dict) else None
        if code_name == "lscc_bad_signature":
            msg = "Website rejected the signature - the shared secret does not match."
        elif code_name == "lscc_stale_timestamp":
            msg = "Clock mismatch between this Pi and the website (%s)." % (msg or "")
        return False, "HTTP %d: %s" % (code, msg or raw[:120].decode("utf-8", "replace")), data
    return last


# --------------------------------------------------------------------------
# The daemon
# --------------------------------------------------------------------------
class Daemon:
    def __init__(self, paths):
        self.paths = paths
        self.cfg = Config(paths["config"])
        self.store = Store(paths["db"])
        self.detector = Detector()
        self.parser = TFParser()
        self.stop_evt = threading.Event()
        self.started = time.time()

        self.fd = None
        self.port_open = (None, None)
        self.next_open_try = 0.0
        self.last_frame_mono = 0.0
        self.frames_window = []        # monotonic times of recent frames (for fps)
        self.dist_cm = None
        self.strength = 0
        self.sensor_ok = False
        self.sensor_error = "not opened"
        self.port_name = None

        self.test_mode = False
        self.test_count = 0
        self.calibration = None        # dict while calibrating
        self.last_result = None        # last command result (for the UI)

        self.lock = threading.Lock()   # guards the shared dict below
        self.shared = {"fpp_playing": False, "fpp_last_playing": 0.0, "fpp_known": False,
                       "sync": {}, "warnings": []}
        self.sync_q = queue.Queue()
        self.people = {"ok": None, "error": "", "last_poll": 0, "last_ok_ts": 0, "latest_count": None,
                       "latest_ts": None, "rows": 0, "fails": 0, "skew_s": None}
        self.people_test = None        # result of the last "Test board" click (shown in the UI)
        self._people_cache = None
        self.stats_dirty = True
        self._today_cache = None
        self._season_cache = None
        self.apply_detector_params()
        self._load_last_sync()

    # ---- config helpers --------------------------------------------------
    def apply_detector_params(self):
        c = self.cfg
        self.detector.set_params(c["min_cm"], c["max_cm"], c["min_strength"],
                                 c["confirm_ms"], c["clear_ms"], c["max_dwell_s"])

    def _load_last_sync(self):
        raw = self.store.meta_get("last_sync")
        info = {}
        if raw:
            try:
                info = json.loads(raw)
            except ValueError:
                info = {}
        with self.lock:
            self.shared["sync"] = info

    # ---- serial ----------------------------------------------------------
    def ensure_serial(self, now):
        port = resolve_port(self.cfg)
        want = (port, self.cfg["baud"])
        if self.fd is not None and self.port_open != want:
            self.close_serial()
        if self.fd is not None:
            return
        if now < self.next_open_try:
            return
        self.port_name = port
        if port is None:
            self.next_open_try = now + 3
            msg = ("no USB serial adapter found - plug it in" if self.cfg["connection"] == "usb"
                   else "no serial port selected")
            if msg != self.sensor_error:
                log.error(msg)
            self.sensor_error = msg
            self.sensor_ok = False
            return
        try:
            self.fd = open_serial(*want)
            self.port_open = want
            self.parser = TFParser()
            self.sensor_error = "waiting for data"
            log.info("Opened %s @ %d baud", *want)
        except (OSError, termios.error) as exc:
            self.next_open_try = now + 5
            msg = "cannot open %s: %s" % (want[0], exc.strerror if hasattr(exc, "strerror") and exc.strerror else exc)
            if msg != self.sensor_error:
                log.error(msg)
            self.sensor_error = msg
            self.sensor_ok = False

    def close_serial(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None
        self.port_open = (None, None)
        self.detector.reset()
        self.dist_cm = None

    def read_frames(self, timeout):
        if self.fd is None:
            time.sleep(timeout)
            return []
        try:
            ready, _, _ = select.select([self.fd], [], [], timeout)
            if not ready:
                return []
            data = os.read(self.fd, 4096)
        except (OSError, ValueError) as exc:
            log.error("Serial read failed: %s", exc)
            self.sensor_error = "serial read failed: %s" % exc
            self.close_serial()
            self.next_open_try = time.monotonic() + 5
            return []
        if not data:
            return []
        return self.parser.feed(data)

    # ---- frame handling --------------------------------------------------
    def handle_frame(self, mono, raw_dist, strength):
        self.frames_window.append(mono)
        self.last_frame_mono = mono
        if not self.sensor_ok:
            log.info("Sensor data OK")
        self.sensor_ok = True
        self.sensor_error = ""
        if raw_dist == 0 or raw_dist == 0xFFFF:
            dist = None
        else:
            dist = raw_dist / 10.0 if self.cfg["unit"] == "mm" else float(raw_dist)
        self.dist_cm = dist
        self.strength = strength

        cal = self.calibration
        if cal is not None and dist is not None:
            cal["samples"].append(dist)

        if self.detector.feed(mono, dist, strength) == "car":
            self.on_car()

    def on_car(self):
        now = datetime.datetime.now()
        if self.test_mode:
            self.test_count += 1
            log.info("TEST car #%d", self.test_count)
            return
        if self.calibration is not None:
            return
        active, reason = self.counting_now(now)
        sd = show_date_for(now, self.cfg["rollover_hour"])
        kind = "car" if active else "offhours"
        self.store.add_event(now.timestamp(), sd, now.hour, 1, kind)
        self.stats_dirty = True
        log.info("%s counted for %s (%s)", "Car" if active else "Off-hours detection", sd, reason)

    def counting_now(self, now_dt=None):
        with self.lock:
            playing = self.shared["fpp_playing"]
            last = self.shared["fpp_last_playing"]
            known = self.shared["fpp_known"]
        return counting_state(self.cfg, now_dt or datetime.datetime.now(), playing, last, time.time(), known)

    # ---- commands from the web UI ---------------------------------------
    def process_commands(self):
        cdir = self.paths["cmd"]
        try:
            names = sorted(n for n in os.listdir(cdir) if n.endswith(".json"))
        except OSError:
            return
        for name in names:
            path = os.path.join(cdir, name)
            try:
                with open(path) as fh:
                    cmd = json.load(fh)
            except (OSError, ValueError):
                cmd = None
            try:
                os.unlink(path)
            except OSError:
                pass
            if isinstance(cmd, dict):
                try:
                    self.run_command(cmd)
                except Exception as exc:  # never let a bad command kill counting
                    log.exception("Command failed")
                    self.set_result(cmd.get("id"), False, "Internal error: %s" % exc)

    def set_result(self, cid, ok, message):
        self.last_result = {"id": cid, "ok": bool(ok), "message": message, "ts": int(time.time())}

    def run_command(self, cmd):
        cid, name = cmd.get("id"), cmd.get("cmd")
        now = datetime.datetime.now()
        sd = show_date_for(now, self.cfg["rollover_hour"])
        if name == "adjust":
            delta = 1 if int(cmd.get("delta", 1)) > 0 else -1
            if delta < 0 and self.store.day(sd)["total"] <= 0:
                return self.set_result(cid, False, "Tonight's count is already 0.")
            self.store.add_event(now.timestamp(), sd, now.hour, delta, "manual")
            self.stats_dirty = True
            log.info("Manual adjustment %+d for %s", delta, sd)
            self.set_result(cid, True, "Tonight's count adjusted by %+d." % delta)
        elif name == "reset_today":
            n = self.store.void_day(sd)
            self.stats_dirty = True
            log.info("Reset %s (%d events voided)", sd, n)
            self.set_result(cid, True, "Tonight's count was reset.")
        elif name == "test_mode":
            self.test_mode = bool(cmd.get("on"))
            self.test_count = 0
            self.set_result(cid, True, "Test mode %s." % ("ON - cars are not recorded" if self.test_mode else "off"))
        elif name == "calibrate":
            if not self.sensor_ok:
                return self.set_result(cid, False, "No sensor data - check wiring and serial port.")
            self.calibration = {"id": cid, "until": time.monotonic() + 6.0, "samples": []}
            self.set_result(cid, True, "Calibrating for 6 seconds - keep the road clear...")
            self.last_result["pending"] = True
        elif name in ("sync_now", "sync_test", "people_test", "people_poll"):
            self.sync_q.put(cmd)
        else:
            self.set_result(cid, False, "Unknown command")

    def finish_calibration(self):
        cal, self.calibration = self.calibration, None
        samples = sorted(cal["samples"])
        c = self.cfg
        if not samples:
            c.update({"max_cm": 1200})
            self.apply_detector_params()
            return self.set_result(cal["id"], True,
                                   "Nothing detected in 6 s - the empty road reads out of range. "
                                   "Max distance set to 1200 cm.")
        nearest = samples[max(0, int(len(samples) * 0.02))]
        new_max = int(nearest * 0.85)
        if new_max <= c["min_cm"] + 10:
            return self.set_result(cal["id"], False,
                                   "Something is only %.0f cm from the sensor. Clear the beam or re-aim, then try again." % nearest)
        c.update({"max_cm": new_max})
        self.apply_detector_params()
        self.set_result(cal["id"], True,
                        "Nearest background reading %.0f cm. Max distance set to %d cm." % (nearest, new_max))

    # ---- data for the UI -------------------------------------------------
    def today_info(self, sd):
        key = (self.store.version, sd)
        if self._today_cache is None or self._today_cache[0] != key:
            self._today_cache = (key, self.store.day(sd), self.store.season_total())
        return self._today_cache[1], self._today_cache[2]

    def write_stats(self):
        since = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        days = self.with_people(self.store.days(since), since)
        nights = [d for d in days if d["total"] > 0]
        best = max(nights, key=lambda d: d["total"]) if nights else None
        atomic_write_json(self.paths["stats"], {
            "generated": int(time.time()),
            "days": days,
            "season_total": self.store.season_total(),
            "best": {"date": best["date"], "total": best["total"]} if best else None,
        })
        self.stats_dirty = False

    def write_status(self, mono):
        now_dt = datetime.datetime.now()
        sd = show_date_for(now_dt, self.cfg["rollover_hour"])
        today, season = self.today_info(sd)
        active, reason = self.counting_now(now_dt)
        self.frames_window = [t for t in self.frames_window if mono - t <= 2.0]
        fps = len(self.frames_window) / 2.0
        stale = (mono - self.last_frame_mono) > 3.0 if self.last_frame_mono else True
        if self.fd is not None and stale and self.sensor_ok:
            self.sensor_ok = False
            self.sensor_error = "no data from sensor for 3 s - check wiring, baud rate and serial port"
            log.error(self.sensor_error)
            self.detector.reset()
            self.dist_cm = None
        warnings = []
        if not self.sensor_ok:
            warnings.append("Sensor: " + (self.sensor_error or "no data"))
        if self.detector.stuck:
            warnings.append("The beam has been blocked for over %d s - check for an obstruction or mis-aimed sensor."
                            % self.cfg["max_dwell_s"])
        with self.lock:
            sync = dict(self.shared["sync"])
            fpp_playing = self.shared["fpp_playing"]
        pinfo = dict(self.people)
        if self.cfg["people_enabled"]:
            if pinfo["ok"] is False and pinfo["fails"] >= 2:
                warnings.append("Crowd board: " + pinfo["error"])
            elif pinfo.get("clock_warning"):
                warnings.append("Crowd board: " + pinfo["clock_warning"])
        if self.cfg["sync_enabled"] and sync.get("last_ok") is False:
            warnings.append("Last website sync failed: " + str(sync.get("message", "")))
        det = self.detector
        atomic_write_json(self.paths["status"], {
            "ts": time.time(),
            "version": VERSION,
            "pid": os.getpid(),
            "uptime": int(time.time() - self.started),
            "show_date": sd,
            "show_name": self.cfg["show_name"],
            "sensor": {
                "ok": self.sensor_ok,
                "error": self.sensor_error,
                "port": self.port_name,
                "connection": self.cfg["connection"],
                "distance_cm": None if self.dist_cm is None else round(self.dist_cm, 1),
                "strength": self.strength,
                "fps": round(fps, 1),
                "bad_frames": self.parser.bad_frames,
            },
            "detector": {
                "state": det.state,
                "in_zone": det.in_zone,
                "present_s": round(det.present_seconds(mono), 1),
                "stuck": det.stuck,
                "min_cm": self.cfg["min_cm"],
                "max_cm": self.cfg["max_cm"],
            },
            "counting": {"active": active, "reason": reason, "mode": self.cfg["schedule_mode"]},
            "today": today,
            "season_total": season,
            "test_mode": self.test_mode,
            "test_count": self.test_count,
            "calibrating": self.calibration is not None,
            "fpp_playing": fpp_playing,
            "fpp": {"host": self.cfg["fpp_host"], "known": self.shared["fpp_known"], "playing": fpp_playing},
            "sync": sync,
            "sync_enabled": self.cfg["sync_enabled"],
            "result": self.last_result,
            "people": {
                "enabled": self.cfg["people_enabled"],
                "host": self.cfg["people_host"],
                "interval_min": self.cfg["people_interval_min"],
                "status": pinfo,
                "today": self.people_today(sd) if self.cfg["people_enabled"] else None,
                "test": self.people_test,
            },
            "warnings": warnings,
        })

    # ---- background thread: FPP status, stats file, website sync ---------
    def poll_fpp(self):
        host = self.cfg["fpp_host"] or ("" if STANDALONE else "127.0.0.1")
        if not host:
            return
        playing = False
        known = False
        try:
            with urllib.request.urlopen("http://%s/api/fppd/status" % host, timeout=3) as resp:
                data = json.loads(resp.read(1 << 18).decode("utf-8", "replace"))
            known = True
            playing = str(data.get("status_name", "")).lower() == "playing"
        except (OSError, ValueError, urllib.error.URLError):
            pass
        with self.lock:
            self.shared["fpp_known"] = known
            self.shared["fpp_playing"] = playing
            if playing:
                self.shared["fpp_last_playing"] = time.time()

    # ---- BaldrickSignals crowd board -------------------------------------
    def row_counted(self, dt):
        """Does a board reading taken at dt fall inside the show hours?  Uses the show schedule;
        'playing' mode has no history of FPP state, so the schedule is used if there is one."""
        mode = self.cfg["schedule_mode"]
        if mode == "always" or not self.cfg["schedules"]:
            return True
        return schedule_active(self.cfg["schedules"], dt)

    def people_poll(self, kind="auto", test=False):
        """Download the board's CSV and import new readings.  Returns (ok, message)."""
        c = self.cfg
        host = c["people_host"]
        now = time.time()
        last_ts = float(self.store.meta_get("people_last_ts", 0) or 0)
        if test:
            since = now - 86400                         # just enough to show what the board sends
        elif last_ts:
            since = last_ts - 900                       # small overlap; duplicates are ignored
        else:
            since = now - max(c["sync_days"], 7) * 86400   # first check: catch up on the last week
        ok, payload, url = fetch_board_csv(host, since)
        info = self.people
        info["last_poll"] = int(now)
        if not ok:
            info.update(ok=False, error=payload, fails=info["fails"] + 1)
            if test:
                self.people_test = {"ts": int(now), "ok": False, "message": payload, "lines": [], "url": url}
            log.warning("Crowd board: %s", payload)
            return False, payload
        parsed = parse_board_csv(payload, c["people_time_col"], c["people_count_col"], c["people_clock"])
        hdr = parsed["header"]

        def colname(i):
            if i is None:
                return "none"
            return "column %d%s" % (i + 1, (" (%s)" % hdr[i]) if hdr and i < len(hdr) and hdr[i] else "")

        detail = {"ts": int(now), "ok": parsed["ok"], "lines": parsed["lines"], "rows": parsed["total_rows"],
                  "time_col": colname(parsed["time_col"]) + (" + next column" if parsed["combined"] else ""),
                  "count_col": colname(parsed["count_col"]), "delimiter": parsed["delimiter"],
                  "clock": c["people_clock"], "message": "", "url": url}
        if not parsed["ok"]:
            info.update(ok=False, error=parsed["error"], fails=info["fails"] + 1)
            detail["message"] = parsed["error"]
            if test:
                self.people_test = detail
            log.warning("Crowd board CSV: %s", parsed["error"])
            return False, parsed["error"]

        rows = parsed["rows"]
        if parsed["time_col"] is None:     # counts only: take the newest value as 'now'
            rows = [(now, rows[-1][1])]
            detail["note"] = "No timestamp column found - using the newest count at the time of each check."
        latest_ts, latest_count = rows[-1]
        skew = now - latest_ts
        info.update(ok=True, error="", fails=0, last_ok_ts=int(now), latest_count=latest_count,
                    latest_ts=int(latest_ts), rows=parsed["total_rows"], skew_s=int(skew))
        detail.update(latest_count=latest_count, latest_ts=int(latest_ts), skew_s=int(skew))
        problems = []
        if skew < -300:
            problems.append("The board's clock is %d min ahead of the Pi - check the 'Board clock' setting." % round(-skew / 60))
        info["clock_warning"] = problems[0] if problems else ""
        msg = "Board OK: %d rows, newest reading %d device(s) at %s." % (
            parsed["total_rows"], latest_count, datetime.datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d %H:%M:%S"))
        if not test:
            floor = now - 90 * 86400
            new = [(t, cnt) for t, cnt in rows if t > last_ts and t >= floor and t <= now + 3600]
            batch = []
            for t, cnt in new:
                dt = datetime.datetime.fromtimestamp(t)
                batch.append((t, show_date_for(dt, c["rollover_hour"]), cnt, self.row_counted(dt)))
            added = self.store.add_people_samples(batch)
            if new:
                self.store.meta_set("people_last_ts", int(max(t for t, _ in new)))
            self.store.people_prune()
            self.stats_dirty = True
            self._people_cache = None
            if added:
                log.info("Crowd board (%s): %d new reading(s), latest %d", kind, added, latest_count)
            msg += " %d new reading(s) saved." % added
        else:
            would = sum(1 for t, _ in rows if t >= now - 86400)
            detail["message"] = msg
            detail["recent_rows"] = would
            self.people_test = detail
            if problems:
                msg += " " + problems[0]
        return True, msg

    def people_scheduler(self, state):
        c = self.cfg
        if not c["people_enabled"] or not c["people_host"]:
            return
        now = time.time()
        active, _ = self.counting_now()
        if active:
            state["active_ts"] = now
        if state.get("host") != c["people_host"]:        # new address: check straight away
            state.update(host=c["people_host"], next=0.0)
        if now < state.get("next", 0.0):
            return
        interval = c["people_interval_min"] * 60
        # outside the show (and for 30 min after it) a slow check keeps the status fresh without
        # hammering the board; its history CSV makes up for anything missed
        quiet = (not active) and now - state.get("active_ts", 0) > 1800
        state["next"] = now + (max(interval, 3600) if quiet else interval)
        try:
            self.people_poll("auto")
        except Exception:
            log.exception("Crowd board poll failed")

    def people_today(self, sd):
        key = (self.store.version, sd)
        if self._people_cache is None or self._people_cache[0] != key:
            self._people_cache = (key, self.store.people_days(sd, sd).get(sd, {"people": 0, "people_peak": 0, "samples": 0}))
        return self._people_cache[1]

    def with_people(self, days, since, until=None):
        """Add the crowd numbers to day dicts (and nights that only have crowd readings)."""
        if not self.cfg["people_enabled"]:
            return days
        pd = self.store.people_days(since, until)
        have = {d["date"] for d in days}
        out = [dict(d) for d in days]
        for sd in pd:
            if sd not in have:
                out.append({"date": sd, "total": 0, "offhours": 0, "hours": [0] * 24, "first_ts": None, "last_ts": None})
        for d in out:
            if d["date"] in pd:
                d["people"] = pd[d["date"]]["people"]
                d["people_peak"] = pd[d["date"]]["people_peak"]
        return sorted(out, key=lambda d: d["date"])

    def build_payload(self, live):
        days_back = 1 if live else self.cfg["sync_days"]
        sd_today = show_date_for(datetime.datetime.now(), self.cfg["rollover_hour"])
        since = (datetime.date.fromisoformat(sd_today) - datetime.timedelta(days=days_back - 1)).isoformat()
        return {
            "v": 1,
            "live": bool(live),
            "show_name": self.cfg["show_name"],
            "plugin_version": VERSION,
            "sent_at": int(time.time()),
            "days": self.with_people(self.store.days(since), since),
        }

    def record_sync(self, ok, message, kind, data=None):
        info = {"ts": int(time.time()), "last_ok": bool(ok), "message": message, "kind": kind}
        if ok and isinstance(data, dict):
            info["received"] = data.get("received")
            info["season_total"] = data.get("season_total")
        if ok:
            info["last_ok_ts"] = info["ts"]
        else:
            with self.lock:
                info["last_ok_ts"] = self.shared["sync"].get("last_ok_ts")
        with self.lock:
            self.shared["sync"] = info
        self.store.meta_set("last_sync", json.dumps(info))

    def do_sync(self, live, kind):
        c = self.cfg
        if not c["wp_url"] or not c["secret"]:
            self.record_sync(False, "Website address and shared secret are required.", kind)
            return False, "Website address and shared secret are required."
        if c["people_enabled"] and c["people_host"] and not live:
            try:
                self.people_poll("pre-upload")      # pick up the newest readings before sending
            except Exception:
                log.exception("Crowd board poll before upload failed")
        ok, msg, data = post_signed(c["wp_url"], "ingest", self.build_payload(live),
                                    c["secret"], c["verify_tls"])
        self.record_sync(ok, "Uploaded OK" if ok else msg, kind, data)
        if ok:
            log.info("Website sync (%s) ok: %s", kind, data.get("received") if data else "")
            return True, "Uploaded %s night(s) to the website." % (data or {}).get("received", "?")
        log.warning("Website sync (%s) failed: %s", kind, msg)
        return False, msg

    def run_sync_command(self, cmd):
        c = self.cfg
        cid = cmd.get("id")
        if cmd.get("cmd") in ("people_test", "people_poll"):
            ok, msg = self.people_poll("test" if cmd.get("cmd") == "people_test" else "manual", test=cmd.get("cmd") == "people_test")
            return self.set_result(cid, ok, msg)
        if cmd.get("cmd") == "sync_test":
            if not c["wp_url"] or not c["secret"]:
                return self.set_result(cid, False, "Enter the website address and shared secret first.")
            ok, msg, data = post_signed(c["wp_url"], "ping", {"v": 1, "ping": True, "plugin_version": VERSION},
                                        c["secret"], c["verify_tls"])
            if ok:
                msg = "Connected to \"%s\" (plugin %s). Signature accepted." % (
                    data.get("site", "website"), data.get("plugin_version", "?"))
            self.set_result(cid, ok, msg)
        else:
            ok, msg = self.do_sync(False, "manual")
            self.set_result(cid, ok, msg)

    def sync_scheduler(self, state):
        c = self.cfg
        if not c["sync_enabled"] or not c["wp_url"] or not c["secret"]:
            return
        now_dt = datetime.datetime.now()
        now = time.time()
        # nightly upload, with catch-up if the Pi was off or the site was down
        minutes = parse_hhmm(c["sync_time"])
        due = now_dt.replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)
        if state.get("due_key") != due.date():
            state.update(due_key=due.date(), attempts=0, next_try=0.0)
        last_ok = float(self.store.meta_get("nightly_ok_ts", 0) or 0)
        if now_dt >= due and last_ok < due.timestamp() and state["attempts"] < 12 and now >= state["next_try"]:
            ok, _ = self.do_sync(False, "nightly")
            if ok:
                self.store.meta_set("nightly_ok_ts", int(now))
            else:
                state["attempts"] += 1
                state["next_try"] = now + min(600 * state["attempts"], 3600)
        # optional live updates while the show is running
        interval = c["live_interval_min"]
        if interval and self.store.version != state.get("live_version") and now - state.get("live_ts", 0) >= interval * 60:
            active, _ = self.counting_now(now_dt)
            if active:
                version = self.store.version
                ok, _ = self.do_sync(True, "live")
                state["live_ts"] = now
                if ok:
                    state["live_version"] = version

    def housekeeping(self):
        next_fpp = 0.0
        next_stats = 0.0
        sync_state = {}
        people_state = {}
        while not self.stop_evt.is_set():
            now = time.time()
            try:
                while True:
                    try:
                        cmd = self.sync_q.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        self.run_sync_command(cmd)
                    except Exception as exc:
                        log.exception("Sync command failed")
                        self.set_result(cmd.get("id"), False, "Internal error: %s" % exc)
                if now >= next_fpp:
                    self.poll_fpp()
                    next_fpp = now + 5
                if self.stats_dirty or now >= next_stats:
                    self.write_stats()
                    next_stats = now + 60
                self.sync_scheduler(sync_state)
                self.people_scheduler(people_state)
            except Exception:
                log.exception("Housekeeping error")
            self.stop_evt.wait(1.0)

    # ---- main loop -------------------------------------------------------
    def run(self):
        threading.Thread(target=self.housekeeping, name="housekeeping", daemon=True).start()
        next_slow = 0.0
        log.info("Car counter %s started (pid %d)", VERSION, os.getpid())
        while not self.stop_evt.is_set():
            mono = time.monotonic()
            if self.cfg.reload_if_changed():
                self.apply_detector_params()
                log.info("Configuration reloaded")
            self.ensure_serial(mono)
            for dist, strength in self.read_frames(0.1):
                self.handle_frame(time.monotonic(), dist, strength)
            mono = time.monotonic()
            if self.calibration is not None and mono >= self.calibration["until"]:
                self.finish_calibration()
            if mono >= next_slow:
                self.process_commands()
                self.write_status(mono)
                next_slow = mono + 0.5
        self.close_serial()
        log.info("Car counter stopped")


def setup_logging(path):
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        ensure_dir(os.path.dirname(path))
        handler = logging.handlers.RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=2)
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)
    log.addHandler(handler)


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return 0
    paths = get_paths()
    ensure_dir(paths["data"])
    ensure_dir(paths["run"], 0o777)
    ensure_dir(paths["cmd"], 0o777)
    for p in (paths["run"], paths["cmd"]):
        try:
            os.chmod(p, 0o777)
        except OSError:
            pass
    setup_logging(paths["log"])
    lock_fh = open(paths["lock"], "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another car counter daemon is already running", file=sys.stderr)
        return 75
    daemon = Daemon(paths)

    def _stop(_sig, _frm):
        daemon.stop_evt.set()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        daemon.run()
    except Exception:
        log.exception("Fatal error")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
