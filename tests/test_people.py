"""Tests for the BaldrickSignals crowd-board support.  Run:  python3 -m unittest discover -s tests -v
The board's CSV layout is undocumented, so several plausible layouts are parsed here."""
import datetime
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "counter"))
import car_counter as cc  # noqa: E402


def local_ts(dt):
    return dt.timestamp()


class UrlTests(unittest.TestCase):
    def test_urls_prefer_log_endpoint_then_csv(self):
        u = cc.board_urls("192.168.1.167", 1794633908)
        self.assertEqual(u[0], "http://192.168.1.167/turnip_data_log/data?format=csv&mark_discontinuities=0&from=1794633908")
        self.assertEqual(u[1], "http://192.168.1.167/csv")
        self.assertEqual(cc.board_urls("", 5), [])


class HostTests(unittest.TestCase):
    def test_normalize(self):
        n = cc.normalize_board_host
        self.assertEqual(n("192.168.1.50"), "192.168.1.50")
        self.assertEqual(n("http://192.168.1.50/csv"), "192.168.1.50")
        self.assertEqual(n(" baldrickboard.local "), "baldrickboard.local")
        self.assertEqual(n("10.0.0.5:8080/x"), "10.0.0.5:8080")
        self.assertEqual(n("bad host!"), "")
        self.assertEqual(n(""), "")


class ParseTests(unittest.TestCase):
    def test_iso_header_picks_crowd_column(self):
        text = "Timestamp,Devices,Crowd\n2026-11-14 18:00:00,12,6\n2026-11-14 18:00:30,14,7\n2026-11-14 18:01:00,15,8\n"
        r = cc.parse_board_csv(text)
        self.assertTrue(r["ok"])
        self.assertEqual((r["time_col"], r["count_col"]), (0, 2))
        self.assertEqual([c for _, c in r["rows"]], [6, 7, 8])
        self.assertAlmostEqual(r["rows"][0][0], datetime.datetime(2026, 11, 14, 18, 0, 0).timestamp())

    def test_no_header_epoch_and_count(self):
        now = int(time.time())
        r = cc.parse_board_csv("%d,5\n%d,9\n" % (now - 30, now))
        self.assertTrue(r["ok"])
        self.assertEqual(r["rows"], [(now - 30, 5), (now, 9)])

    def test_epoch_milliseconds(self):
        r = cc.parse_board_csv("time,count\n1763150400000,3\n")
        self.assertEqual(r["rows"][0], (1763150400.0, 3))

    def test_separate_date_and_time_columns_dayfirst_inferred(self):
        text = "Date,Time,Count\n13/11/2026,19:00:00,4\n14/11/2026,19:00:30,6\n"
        r = cc.parse_board_csv(text)
        self.assertTrue(r["ok"] and r["combined"])
        self.assertEqual(datetime.datetime.fromtimestamp(r["rows"][0][0]).date(), datetime.date(2026, 11, 13))
        self.assertEqual([c for _, c in r["rows"]], [4, 6])

    def test_us_month_first(self):
        r = cc.parse_board_csv("time,people\n11/14/2026 7:05 PM,8\n11/14/2026 7:10 PM,9\n")
        self.assertTrue(r["ok"])
        self.assertEqual(datetime.datetime.fromtimestamp(r["rows"][0][0]), datetime.datetime(2026, 11, 14, 19, 5))

    def test_semicolon_and_utc_clock(self):
        r = cc.parse_board_csv("time;count\n2026-11-14 18:00:00;3\n", clock="utc")
        self.assertTrue(r["ok"])
        self.assertEqual(r["rows"][0][0], datetime.datetime(2026, 11, 14, 18, 0, tzinfo=datetime.timezone.utc).timestamp())

    def test_manual_column_override(self):
        text = "time,a,b\n2026-11-14 18:00:00,100,5\n"
        self.assertEqual(cc.parse_board_csv(text)["rows"][0][1], 5)            # auto: last numeric column
        self.assertEqual(cc.parse_board_csv(text, count_col=2)["rows"][0][1], 100)

    def test_garbage_and_empty(self):
        self.assertFalse(cc.parse_board_csv("")["ok"])
        self.assertFalse(cc.parse_board_csv("hello world\nfoo bar\n")["ok"])
        self.assertFalse(cc.parse_board_csv("time,count\n")["ok"])

    def test_counts_only_has_no_time_column(self):
        r = cc.parse_board_csv("count\n3\n4\n")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["time_col"])


class EstimateTests(unittest.TestCase):
    def test_arrivals_and_peak(self):
        s = [(0, 2), (30, 5), (60, 9), (90, 7), (120, 11)]
        e = cc.estimate_people(s)
        self.assertEqual(e["people_peak"], 11)
        self.assertGreaterEqual(e["people"], e["people_peak"])

    def test_single_blip_ignored(self):
        flat = [(i * 30, 5) for i in range(10)]
        blip = list(flat)
        blip[4] = (120, 40)
        self.assertEqual(cc.estimate_people(blip)["people"], cc.estimate_people(flat)["people"])

    def test_cumulative_series_gives_final_value(self):
        s = [(i * 30, min(i, 20)) for i in range(40)]
        self.assertEqual(cc.estimate_people(s)["people"], 20)

    def test_gap_starts_fresh_baseline(self):
        s = [(0, 10), (30, 10), (10000, 10), (10030, 10)]
        self.assertEqual(cc.estimate_people(s)["people"], 20)

    def test_empty(self):
        self.assertEqual(cc.estimate_people([])["people"], 0)


class FakeBoard:
    def __init__(self):
        self.body = ""
        self.status = 200
        self.legacy = False          # True = older firmware without /turnip_data_log/data
        self.requests = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.requests.append(self.path)
                ok_path = self.path == "/csv" or (self.path.startswith("/turnip_data_log/data?") and not outer.legacy)
                if not ok_path:
                    self.send_response(404); self.end_headers(); return
                self.send_response(outer.status)
                self.send_header("Content-Type", "text/csv")
                self.end_headers()
                self.wfile.write(outer.body.encode())

            def log_message(self, *a):
                pass

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.host = "127.0.0.1:%d" % self.srv.server_port

    def close(self):
        self.srv.shutdown()


class PollTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.environ["CC_DATA_DIR"] = os.path.join(self.dir, "data")
        os.environ["CC_RUN_DIR"] = os.path.join(self.dir, "run")
        os.environ["CC_LOG_FILE"] = os.path.join(self.dir, "log", "c.log")
        self.paths = cc.get_paths()
        for p in (self.paths["data"], self.paths["run"], self.paths["cmd"]):
            os.makedirs(p, exist_ok=True)
        self.board = FakeBoard()
        cc.atomic_write_json(self.paths["config"], {
            "people_enabled": True, "people_host": self.board.host, "people_interval_min": 5,
            "schedule_mode": "window", "rollover_hour": 0,
            "schedules": [{"days": list(range(7)), "start": "17:00", "end": "22:00"}],
        }, 0o600)
        self.d = cc.Daemon(self.paths)
        self.today = datetime.date.today()

    def tearDown(self):
        self.board.close()
        shutil.rmtree(self.dir)
        for k in ("CC_DATA_DIR", "CC_RUN_DIR", "CC_LOG_FILE"):
            os.environ.pop(k, None)

    def csv_for(self, readings):
        """readings: [(hour, minute, count)] today."""
        lines = ["Timestamp,Devices,Crowd"]
        for h, m, c in readings:
            lines.append("%s %02d:%02d:00,%d,%d" % (self.today.isoformat(), h, m, c * 2, c))
        return "\n".join(lines) + "\n"

    def test_import_filters_show_hours_dedupes_and_reports(self):
        # 15:00 is outside the 17:00-22:00 schedule; the rest are inside
        self.board.body = self.csv_for([(15, 0, 30), (18, 0, 2), (18, 5, 6), (18, 10, 9), (18, 15, 9), (18, 20, 4)])
        ok, msg = self.d.people_poll("manual")
        self.assertTrue(ok, msg)
        self.assertIn("6 new", msg)                            # all stored; the 15:00 one is flagged as outside show hours
        ok, msg = self.d.people_poll("manual")                 # same CSV again: nothing new
        self.assertIn("0 new", msg)
        day = self.d.store.people_days(self.today.isoformat())[self.today.isoformat()]
        self.assertEqual(day["samples"], 5)
        self.assertEqual(day["people_peak"], 9)
        self.assertGreaterEqual(day["people"], 9)
        # newer rows are picked up
        self.board.body = self.csv_for([(15, 0, 30), (18, 0, 2), (18, 5, 6), (18, 10, 9), (18, 15, 9), (18, 20, 4), (18, 25, 12), (18, 30, 12)])
        self.assertIn("2 new", self.d.people_poll("manual")[1])
        self.assertEqual(self.d.store.people_latest()["count"], 12)

    def test_payload_carries_people_and_cars_separately(self):
        sd = self.today.isoformat()
        self.d.store.add_event(time.time(), sd, 19, 1, "car")
        self.d.store.add_event(time.time(), sd, 19, 1, "car")
        self.board.body = self.csv_for([(18, 0, 3), (18, 5, 8), (18, 10, 8)])
        self.d.people_poll("manual")
        day = [x for x in self.d.build_payload(False)["days"] if x["date"] == sd][0]
        self.assertEqual(day["total"], 2)                       # cars untouched
        self.assertEqual(day["people_peak"], 8)
        self.assertGreaterEqual(day["people"], 8)

    def test_people_only_night_is_included(self):
        self.board.body = self.csv_for([(19, 0, 5), (19, 5, 5)])
        self.d.people_poll("manual")
        days = self.d.build_payload(False)["days"]
        self.assertEqual([x["total"] for x in days if x["date"] == self.today.isoformat()], [0])

    def test_disabled_adds_no_people_fields(self):
        self.board.body = self.csv_for([(19, 0, 5)])
        self.d.people_poll("manual")
        self.d.cfg.update({"people_enabled": False})
        self.d.store.add_event(time.time(), self.today.isoformat(), 19, 1, "car")
        self.assertTrue(all("people" not in x for x in self.d.build_payload(False)["days"]))

    def test_test_button_does_not_save_and_reports_columns(self):
        self.board.body = self.csv_for([(18, 0, 3), (18, 5, 8)])
        ok, msg = self.d.people_poll("test", test=True)
        self.assertTrue(ok)
        self.assertIsNone(self.d.store.people_latest())
        t = self.d.people_test
        self.assertTrue(t["ok"])
        self.assertIn("Crowd", t["count_col"])
        self.assertIn("Timestamp", t["time_col"])
        self.assertEqual(t["latest_count"], 8)

    def test_unreachable_and_http_error(self):
        self.board.status = 500
        ok, msg = self.d.people_poll("manual")
        self.assertFalse(ok)
        self.assertIn("500", msg)
        self.board.close()
        self.d.cfg.update({"people_host": "127.0.0.1:1"})
        ok, msg = self.d.people_poll("manual")
        self.assertFalse(ok)
        self.assertIn("Could not reach", msg)
        self.assertEqual(self.d.people["fails"], 2)
        self.board = FakeBoard()                                 # so tearDown can close

    def test_board_clock_ahead_warns(self):
        future = (datetime.datetime.now() + datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
        self.board.body = "Timestamp,Crowd\n%s,4\n" % future
        ok, msg = self.d.people_poll("test", test=True)
        self.assertTrue(ok)
        self.assertIn("ahead", msg)

    def test_asks_only_for_new_readings(self):
        self.board.body = self.csv_for([(18, 0, 3), (18, 5, 4)])
        t0 = time.time()
        self.d.people_poll("manual")
        first = self.board.requests[-1]
        self.assertIn("/turnip_data_log/data?format=csv&mark_discontinuities=0&from=", first)
        frm = int(first.split("from=")[1])
        self.assertAlmostEqual(frm, t0 - 7 * 86400, delta=30)          # first check catches up a week
        self.d.people_poll("manual")
        frm2 = int(self.board.requests[-1].split("from=")[1])
        last = int(self.d.store.meta_get("people_last_ts"))
        self.assertEqual(frm2, last - 900)                              # next checks start at the last reading

    def test_older_firmware_falls_back_to_csv(self):
        self.board.legacy = True
        self.board.body = self.csv_for([(18, 0, 3), (18, 5, 4)])
        ok, msg = self.d.people_poll("manual")
        self.assertTrue(ok, msg)
        self.assertTrue(self.board.requests[0].startswith("/turnip_data_log/data"))
        self.assertEqual(self.board.requests[-1], "/csv")
        self.assertIn("/csv", self.d.people_test["url"] if self.d.people_test else "/csv")

    def test_test_result_reports_url(self):
        self.board.body = self.csv_for([(18, 0, 3)])
        self.d.people_poll("test", test=True)
        self.assertIn("/turnip_data_log/data", self.d.people_test["url"])

    def test_status_json_has_people_block(self):
        self.board.body = self.csv_for([(18, 0, 3)])
        self.d.people_poll("manual")
        self.d.write_status(time.monotonic())
        with open(self.paths["status"]) as fh:
            st = json.load(fh)
        self.assertTrue(st["people"]["enabled"])
        self.assertEqual(st["people"]["status"]["latest_count"], 3)
        self.assertIsNotNone(st["people"]["today"])

    def test_command_runs_through_queue(self):
        self.board.body = self.csv_for([(18, 0, 3), (18, 5, 4)])
        self.d.run_command({"id": "abc", "cmd": "people_test"})
        cmd = self.d.sync_q.get_nowait()
        self.d.run_sync_command(cmd)
        self.assertTrue(self.d.last_result["ok"])
        self.assertEqual(self.d.last_result["id"], "abc")


if __name__ == "__main__":
    unittest.main()
