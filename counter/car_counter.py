#!/usr/bin/env python3
"""
FPP Car Counter daemon.

Reads a Benewake TFmini / TFmini-S / TFmini Plus / TF-Luna lidar over UART,
counts vehicles passing the sensor, stores every event in SQLite and
(optionally) uploads nightly totals to a WordPress site.

Standard library only - nothing to pip install on the Pi.
Written for Python 3.7+ (FPP images ship 3.9 - 3.11).
"""
import datetime
import fcntl
import hashlib
import hmac
import json
import logging
import logging.handlers
import os
import queue
import random
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

VERSION = "1.0.0"
USER_AGENT = "fpp-car-counter/" + VERSION

log = logging.getLogger("car-counter")


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
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
    "serial_port": ("str", "/dev/serial0", 120),
    "baud": ("choice", 115200, list(BAUDS.keys())),
    "unit": ("choice", "cm", ["cm", "mm"]),
    "min_cm": ("int", 30, 1, 5000),
    "max_cm": ("int", 1200, 2, 20000),
    "min_strength": ("int", 0, 0, 65534),
    "confirm_ms": ("int", 250, 20, 5000),
    "clear_ms": ("int", 800, 100, 30000),
    "max_dwell_s": ("int", 120, 5, 3600),
    "schedule_mode": ("choice", "window", ["always", "window", "playing"]),
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


def normalize_config(raw):
    cfg = {}
    for key, spec in SCHEMA.items():
        cfg[key] = coerce(key, raw[key]) if key in raw else spec[1]
    if isinstance(raw.get("schedules"), list):
        cfg["schedules"] = coerce_schedules(raw["schedules"])
    else:  # older config (single window) or fresh install: one entry for every day
        cfg["schedules"] = [{"days": list(range(7)), "start": cfg["window_start"], "end": cfg["window_end"]}]
    if cfg["max_cm"] <= cfg["min_cm"]:
        cfg["max_cm"] = cfg["min_cm"] + 10
    cfg["wp_url"] = cfg["wp_url"].rstrip("/")
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


def counting_state(cfg, dt, fpp_playing, fpp_last_playing_ts, now_ts):
    """Returns (counting_active, reason)."""
    mode = cfg["schedule_mode"]
    if mode == "always":
        return True, "always on"
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

    def meta_get(self, key, default=None):
        row = self._db().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def meta_set(self, key, value):
        self._db().execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, str(value)))


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

        self.test_mode = False
        self.test_count = 0
        self.calibration = None        # dict while calibrating
        self.last_result = None        # last command result (for the UI)

        self.lock = threading.Lock()   # guards the shared dict below
        self.shared = {"fpp_playing": False, "fpp_last_playing": 0.0, "fpp_known": False,
                       "sync": {}, "warnings": []}
        self.sync_q = queue.Queue()
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
        want = (self.cfg["serial_port"], self.cfg["baud"])
        if self.fd is not None and self.port_open != want:
            self.close_serial()
        if self.fd is not None:
            return
        if now < self.next_open_try:
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
        return counting_state(self.cfg, now_dt or datetime.datetime.now(), playing, last, time.time())

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
        elif name in ("sync_now", "sync_test"):
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
        days = self.store.days(since)
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
                "port": self.cfg["serial_port"],
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
            "sync": sync,
            "sync_enabled": self.cfg["sync_enabled"],
            "result": self.last_result,
            "warnings": warnings,
        })

    # ---- background thread: FPP status, stats file, website sync ---------
    def poll_fpp(self):
        playing = False
        known = False
        try:
            with urllib.request.urlopen("http://127.0.0.1/api/fppd/status", timeout=2) as resp:
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
            "days": self.store.days(since),
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
