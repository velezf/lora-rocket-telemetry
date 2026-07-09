"""Host tests for the Stage-1 publish DATA generator.

`flights publish` ships DATA ONLY into the site repo (a flights.json summary + a
per-flight CSV); it never writes .qmd (every .qmd there is a hand-polished Stage-2
artifact). These pure functions build that summary. Every AGL number is auditable:
peak AGL = peak_alt_ft - baseline_ft, and baseline_ft + baseline_n travel with it.
"""
import json
import unittest

import tempfile
from pathlib import Path

from ground.flights.flights import Flight
from ground.publish.data import flights_summary, permalink, write_flight_data

F1 = Flight(
    flight_id="2026-07-08-F1", src=1,
    t_start="2026-07-08T18:21:57.444Z", t_end="2026-07-08T18:23:25.000Z",
    label="shake test", motor="none", field="~406 ft ASL",
    stats={"peak_alt_ft": -74, "duration_s": 87.556, "packets_rx": 75,
           "packets_lost": 1, "rssi_min": -38, "rssi_max": -14,
           "baseline_ft": -84, "baseline_n": 15},
)


class TestFlightsSummary(unittest.TestCase):
    def setUp(self):
        self.rows = flights_summary([F1])
        self.r = self.rows[0]

    def test_json_serialisable(self):
        json.dumps(self.rows)                               # OJS reads this verbatim

    def test_peak_agl_computed_and_baseline_travels(self):
        self.assertEqual(self.r["peak_agl_ft"], 10)        # -74 - (-84)
        self.assertEqual(self.r["peak_alt_ft"], -74)       # raw preserved too
        self.assertEqual(self.r["baseline_ft"], -84)
        self.assertEqual(self.r["baseline_n"], 15)

    def test_identity_and_link_quality_fields(self):
        self.assertEqual((self.r["flight_id"], self.r["date"], self.r["src"]),
                         ("2026-07-08-F1", "2026-07-08", 1))
        self.assertEqual((self.r["packets_rx"], self.r["packets_lost"]), (75, 1))
        self.assertEqual(self.r["loss_pct"], 1.32)         # 1/(75+1)
        self.assertEqual((self.r["rssi_min"], self.r["rssi_max"]), (-38, -14))

    def test_annotations_and_csv_pointer(self):
        self.assertEqual((self.r["label"], self.r["motor"], self.r["field"]),
                         ("shake test", "none", "~406 ft ASL"))
        self.assertEqual(self.r["csv"], "lora-flights/2026-07-08-F1.csv")   # relative to the page

    def test_no_baseline_leaves_peak_agl_null_with_raw_flag(self):
        f = Flight(flight_id="x-F1", src=1, t_start="2026-07-09T00:00:00.000Z", t_end=None,
                   stats={"peak_alt_ft": 500, "packets_rx": 10, "packets_lost": 0,
                          "baseline_ft": None, "baseline_n": 0})
        r = flights_summary([f])[0]
        self.assertIsNone(r["peak_agl_ft"])                # honest: no baseline -> no AGL
        self.assertEqual(r["peak_alt_ft"], 500)            # raw still available

    def test_sorted_newest_first(self):
        a = Flight("2026-07-08-F1", 1, "2026-07-08T00:00:00Z", None, stats={})
        b = Flight("2026-07-09-F1", 1, "2026-07-09T00:00:00Z", None, stats={})
        ids = [r["flight_id"] for r in flights_summary([a, b])]
        self.assertEqual(ids, ["2026-07-09-F1", "2026-07-08-F1"])   # newest first


class TestWriteFlightData(unittest.TestCase):
    def test_ships_json_and_csv_no_qmd(self):
        recs = [{"type": "packet", "received_at": "2026-07-08T18:22:00.000Z", "rssi": -30,
                 "src": 1, "seq": 20,
                 "fields": {"SYS": 7, "SRC": 1, "SEQ": 20, "St": 1, "ALT": -80, "Max": -80}}]
        with tempfile.TemporaryDirectory() as d:
            url = write_flight_data(d, [F1], "2026-07-08-F1", recs)
            base = Path(d) / "projects" / "lora-flights"
            self.assertTrue((base / "flights.json").exists())
            self.assertTrue((base / "2026-07-08-F1.csv").exists())
            self.assertEqual(list(base.glob("*.qmd")), [])           # DATA only, never .qmd
            self.assertIn("2026-07-08-F1", (base / "flights.json").read_text())
            self.assertTrue(url.endswith("?flight=2026-07-08-F1"))


class TestPermalink(unittest.TestCase):
    def test_ojs_url_param_deep_link(self):
        self.assertEqual(permalink("2026-07-08-F1"),
                         "https://velezf.github.io/projects/lora-flights.html?flight=2026-07-08-F1")


if __name__ == "__main__":
    unittest.main()
