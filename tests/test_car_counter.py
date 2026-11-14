"""
Tests for the FPP Car Counter daemon.   Run:  python3 -m unittest discover -s tests -v
Uses a pseudo-terminal as a fake lidar and a local HTTP server as a fake website.
"""
import datetime
import http.server
import json
import os
import pty
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "counter"))
import car_counter as cc  # noqa: E402


def frame(dist, strength=500):
    body = bytes([0x59, 0x59]) + struct.pack("<HHH", dist, strength, 1600)
    return body + bytes([sum(body) & 0xFF])


class ParserTests(unittest.TestCase):
    def test_valid_and_split_frames(self):
        p = cc.TFParser()
        data = frame(123) + frame(456, 99)
        out = p.feed(data[:5]) + p.feed(data[5:])
        self.assertEqual(out, [(123, 500), (456, 99)])

    def test_resync_after_garbage_and_bad_checksum(self):
        p = cc.TFParser()
        bad = bytearray(frame(77))
        bad[8] ^= 0xFF
        out = p.feed(b"\x00\x59\x01" + bytes(bad) + frame(200))
        self.assertEqual(out, [(200, 500)])
        self.assertEqual(p.bad_frames, 1)


class DetectorTests(unittest.TestCase):
    def run_seq(self, det, seq, hz=100):
        """seq: list of (seconds, distance_cm or None). Returns number of cars counted."""
        t, cars = 1000.0, 0
        for secs, dist in seq:
            for _ in range(int(secs * hz)):
                t += 1.0 / hz
                if det.feed(t, dist, 500) == "car":
                    cars += 1
        return cars

    def make(self):
        d = cc.Detector()
        d.set_params(30, 800, 0, 250, 800, 120)
        return d

    def test_single_car(self):
        self.assertEqual(self.run_seq(self.make(), [(1, None), (2, 300), (2, None)]), 1)

    def test_two_cars_with_gap(self):
        seq = [(1, None), (1.5, 300), (1.5, None), (1.5, 280), (1.5, None)]
        self.assertEqual(self.run_seq(self.make(), seq), 2)

    def test_bumper_to_bumper_gap_shorter_than_clear_is_one(self):
        seq = [(1, None), (1, 300), (0.4, None), (1, 300), (2, None)]
        self.assertEqual(self.run_seq(self.make(), seq), 1)

    def test_too_brief_is_ignored(self):
        self.assertEqual(self.run_seq(self.make(), [(1, None), (0.1, 300), (1, None)]), 0)

    def test_single_glitch_frame_does_not_restart_confirmation(self):
        d = self.make()
        t, cars = 0.0, 0
        for i in range(60):
            t += 0.01
            dist = None if i == 10 else 300
            if d.feed(t, dist, 500) == "car":
                cars += 1
        self.assertEqual(cars, 1)

    def test_out_of_range_distances_ignored(self):
        d = self.make()
        self.assertEqual(self.run_seq(d, [(2, 900), (2, 10), (2, 0)]), 0)

    def test_min_strength(self):
        d = self.make()
        d.min_strength = 1000
        self.assertEqual(self.run_seq(d, [(2, 300)]), 0)

    def test_parked_car_counts_once_and_flags_stuck(self):
        d = self.make()
        d.max_dwell_s = 5
        self.assertEqual(self.run_seq(d, [(10, 300)], hz=50), 1)
        self.assertTrue(d.stuck)
        self.run_seq(d, [(2, None)], hz=50)
        self.assertEqual(d.state, cc.IDLE)
        self.assertFalse(d.stuck)


class ScheduleTests(unittest.TestCase):
    def cfg(self, **kw):
        raw = {"schedule_mode": "window", "window_start": "17:00", "window_end": "22:00"}
        raw.update(kw)
        return cc.normalize_config(raw)

    def test_window(self):
        c = self.cfg()
        at = lambda h, m=0: datetime.datetime(2026, 12, 1, h, m)
        self.assertTrue(cc.counting_state(c, at(17), False, 0, 0)[0])
        self.assertTrue(cc.counting_state(c, at(21, 59), False, 0, 0)[0])
        self.assertFalse(cc.counting_state(c, at(22), False, 0, 0)[0])
        self.assertFalse(cc.counting_state(c, at(12), False, 0, 0)[0])

    def test_overnight_window(self):
        c = self.cfg(window_start="18:00", window_end="01:00")
        at = lambda h: datetime.datetime(2026, 12, 1, h, 0)
        self.assertTrue(cc.counting_state(c, at(23), False, 0, 0)[0])
        self.assertTrue(cc.counting_state(c, at(0), False, 0, 0)[0])
        self.assertFalse(cc.counting_state(c, at(3), False, 0, 0)[0])

    def test_playing_with_grace(self):
        c = self.cfg(schedule_mode="playing", grace_min=10)
        now = datetime.datetime(2026, 12, 1, 20, 0)
        self.assertTrue(cc.counting_state(c, now, True, 0, 1000)[0])
        self.assertTrue(cc.counting_state(c, now, False, 900, 1000)[0])
        self.assertFalse(cc.counting_state(c, now, False, 100, 1000)[0])

    def test_show_date_rollover(self):
        self.assertEqual(cc.show_date_for(datetime.datetime(2026, 12, 2, 0, 30), 6), "2026-12-01")
        self.assertEqual(cc.show_date_for(datetime.datetime(2026, 12, 2, 6, 0), 6), "2026-12-02")
        self.assertEqual(cc.show_date_for(datetime.datetime(2026, 12, 1, 19, 0), 6), "2026-12-01")


class ConfigTests(unittest.TestCase):
    def test_coercion_and_defaults(self):
        c = cc.normalize_config({"min_cm": "abc", "max_cm": 5, "baud": 1234, "window_start": "25:99",
                                 "verify_tls": "false", "wp_url": "https://x.com/", "bogus": 1})
        self.assertEqual(c["min_cm"], 30)
        self.assertGreater(c["max_cm"], c["min_cm"])
        self.assertEqual(c["baud"], 115200)
        self.assertEqual(c["window_start"], "17:00")
        self.assertFalse(c["verify_tls"])
        self.assertEqual(c["wp_url"], "https://x.com")
        self.assertNotIn("bogus", c)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = cc.Store(os.path.join(self.dir, "t.db"))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_totals_hours_void(self):
        s = self.store
        for h in (18, 18, 19):
            s.add_event(1000 + h, "2026-12-01", h, 1, "car")
        s.add_event(2000, "2026-12-01", 19, 1, "manual")
        s.add_event(2001, "2026-12-01", 23, 1, "offhours")
        s.add_event(3000, "2026-12-02", 20, 1, "car")
        d = s.day("2026-12-01")
        self.assertEqual((d["total"], d["offhours"]), (4, 1))
        self.assertEqual((d["hours"][18], d["hours"][19]), (2, 2))
        self.assertEqual(s.season_total(), 5)
        s.void_day("2026-12-01")
        d = s.day("2026-12-01")
        self.assertEqual((d["total"], d["offhours"]), (0, 0))
        self.assertEqual(s.season_total(), 1)
        self.assertEqual(len(s.days("2026-12-01")), 2)   # voided day still reported (as 0) so the website is corrected


class SyncTests(unittest.TestCase):
    def test_signature_matches_known_vector(self):
        sig = cc.sign_body("secret", 1700000000, b'{"a":1}')
        import hashlib, hmac
        self.assertEqual(sig, hmac.new(b"secret", b'1700000000.{"a":1}', hashlib.sha256).hexdigest())

    def _server(self, handler_fn):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n)
                handler_fn(self, body)
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    def _reply(self, h, code, obj, extra=None):
        data = json.dumps(obj).encode()
        h.send_response(code)
        h.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            h.send_header(k, v)
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    def test_post_ok_verifies_signature_and_falls_back_to_rest_route(self):
        seen = {}

        def fn(h, body):
            if h.path.startswith("/wp-json/"):
                return self._reply(h, 404, {"code": "rest_no_route"})
            seen["path"] = h.path
            ts = h.headers["X-LSCC-Timestamp"]
            expect = cc.sign_body("s3cret", ts, body)
            ok = h.headers["X-LSCC-Signature"] == expect
            self._reply(h, 200 if ok else 401, {"ok": ok, "received": 1, "site": "T", "code": "lscc_bad_signature"})
        srv = self._server(fn)
        base = "http://127.0.0.1:%d" % srv.server_port
        ok, msg, data = cc.post_signed(base, "ingest", {"days": []}, "s3cret")
        self.assertTrue(ok, msg)
        self.assertIn("rest_route=/lscc/v1/ingest", seen["path"])
        ok, msg, _ = cc.post_signed(base, "ingest", {"days": []}, "wrong")
        self.assertFalse(ok)
        self.assertIn("secret", msg)
        srv.shutdown()

    def test_redirect_keeps_post(self):
        def fn(h, body):
            if h.path.startswith("/old/"):
                return self._reply(h, 301, {}, {"Location": "/new" + h.path[4:]})
            self._reply(h, 200, {"ok": True, "received": len(json.loads(body)["days"])})
        srv = self._server(fn)
        # simulate a site that redirects the wp-json URL
        base = "http://127.0.0.1:%d/old" % srv.server_port
        ok, msg, data = cc.post_signed(base, "ingest", {"days": [1, 2]}, "x")
        self.assertTrue(ok, msg)
        self.assertEqual(data["received"], 2)
        srv.shutdown()

    def test_address_without_scheme_gives_friendly_error(self):
        ok, msg, _ = cc.post_signed("example.com", "ingest", {}, "x")
        self.assertFalse(ok)
        self.assertIn("http", msg)

    def test_unreachable(self):
        ok, msg, _ = cc.post_signed("http://127.0.0.1:1", "ingest", {}, "x", timeout=2)
        self.assertFalse(ok)
        self.assertIn("Could not reach", msg)


class EndToEndTests(unittest.TestCase):
    """Fake lidar on a pty -> daemon -> sqlite -> status.json -> fake website."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ["CC_DATA_DIR"] = os.path.join(self.dir, "data")
        os.environ["CC_RUN_DIR"] = os.path.join(self.dir, "run")
        os.environ["CC_LOG_FILE"] = os.path.join(self.dir, "log", "c.log")
        self.paths = cc.get_paths()
        for p in (self.paths["data"], self.paths["run"], self.paths["cmd"]):
            os.makedirs(p, exist_ok=True)
        self.master, slave = pty.openpty()
        self.slave_name = os.ttyname(slave)
        self.slave = slave
        self.received = []
        cc.atomic_write_json(self.paths["config"], {
            "serial_port": self.slave_name, "schedule_mode": "always", "confirm_ms": 100,
            "clear_ms": 300, "min_cm": 30, "max_cm": 800, "rollover_hour": 0,
        }, 0o600)
        self.d = cc.Daemon(self.paths)
        self.thread = threading.Thread(target=self.d.run, daemon=True)
        self.thread.start()
        self.pump_stop = False
        self.dist = 0
        threading.Thread(target=self.pump, daemon=True).start()

    def pump(self):
        while not self.pump_stop:
            os.write(self.master, frame(self.dist))
            time.sleep(0.01)

    def tearDown(self):
        self.pump_stop = True
        self.d.stop_evt.set()
        self.thread.join(3)
        shutil.rmtree(self.dir)
        for k in ("CC_DATA_DIR", "CC_RUN_DIR", "CC_LOG_FILE"):
            os.environ.pop(k, None)

    def status(self):
        with open(self.paths["status"]) as fh:
            return json.load(fh)

    def wait(self, pred, timeout=6):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if pred(self.status()):
                    return True
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        return False

    def drive_car(self):
        self.dist = 250
        time.sleep(0.8)
        self.dist = 0
        time.sleep(0.8)

    def send(self, cmd, **kw):
        kw.update(cmd=cmd, id=str(time.time()))
        with open(os.path.join(self.paths["cmd"], "%f.json" % time.time()), "w") as fh:
            json.dump(kw, fh)
        return kw["id"]

    def test_counts_cars_manual_adjust_reset_and_test_mode(self):
        self.assertTrue(self.wait(lambda s: s["sensor"]["ok"]))
        self.drive_car()
        self.drive_car()
        self.assertTrue(self.wait(lambda s: s["today"]["total"] == 2), self.status())
        self.assertEqual(self.status()["season_total"], 2)

        self.send("adjust", delta=1)
        self.assertTrue(self.wait(lambda s: s["today"]["total"] == 3))
        self.send("adjust", delta=-1)
        self.assertTrue(self.wait(lambda s: s["today"]["total"] == 2))

        self.send("test_mode", on=True)
        self.assertTrue(self.wait(lambda s: s["test_mode"]))
        self.drive_car()
        self.assertTrue(self.wait(lambda s: s["test_count"] == 1))
        self.assertEqual(self.status()["today"]["total"], 2)   # not recorded
        self.send("test_mode", on=False)

        self.send("reset_today")
        self.assertTrue(self.wait(lambda s: s["today"]["total"] == 0))
        self.assertTrue(self.wait(lambda s: s["sensor"]["fps"] > 20))

    def test_offhours_not_counted(self):
        self.d.cfg.update({"schedule_mode": "window", "window_start": "03:00", "window_end": "03:01"})
        now = datetime.datetime.now()
        if now.hour == 3 and now.minute == 0:
            self.skipTest("inside the test window")
        self.assertTrue(self.wait(lambda s: s["sensor"]["ok"]))
        self.drive_car()
        self.assertTrue(self.wait(lambda s: s["today"]["offhours"] == 1))
        self.assertEqual(self.status()["today"]["total"], 0)

    def test_calibration(self):
        self.assertTrue(self.wait(lambda s: s["sensor"]["ok"]))
        self.dist = 600          # an empty road reads 6 m (e.g. far kerb)
        cid = self.send("calibrate")
        self.assertTrue(self.wait(lambda s: s["result"] and s["result"]["id"] == cid and not s["result"].get("pending"), 12))
        self.assertEqual(self.d.cfg["max_cm"], 510)   # 600 * 0.85

    def test_nightly_sync_end_to_end(self):
        got = {}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self_h):
                body = self_h.rfile.read(int(self_h.headers["Content-Length"]))
                ok = self_h.headers["X-LSCC-Signature"] == cc.sign_body("topsecret", self_h.headers["X-LSCC-Timestamp"], body)
                got["body"] = json.loads(body)
                got["ok"] = ok
                data = json.dumps({"ok": ok, "received": len(got["body"]["days"]), "season_total": 2, "site": "S"}).encode()
                self_h.send_response(200 if ok else 401)
                self_h.send_header("Content-Length", str(len(data)))
                self_h.end_headers()
                self_h.wfile.write(data)
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.assertTrue(self.wait(lambda s: s["sensor"]["ok"]))
        self.drive_car()
        self.drive_car()
        self.assertTrue(self.wait(lambda s: s["today"]["total"] == 2))
        self.d.cfg.update({"wp_url": "http://127.0.0.1:%d" % srv.server_port, "secret": "topsecret",
                           "sync_enabled": True, "sync_time": "00:00"})
        # sync_time 00:00 is always in the past -> the scheduler uploads on its own
        self.assertTrue(self.wait(lambda s: s["sync"].get("last_ok") is True, 10), self.status()["sync"])
        self.assertTrue(got["ok"])
        today = [d for d in got["body"]["days"] if d["total"] == 2]
        self.assertEqual(len(today), 1)
        self.assertEqual(sum(today[0]["hours"]), 2)
        # test-connection command
        cid = self.send("sync_test")
        self.assertTrue(self.wait(lambda s: s["result"] and s["result"]["id"] == cid, 8))
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
