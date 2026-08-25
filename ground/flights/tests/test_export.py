"""Host tests for per-flight export — pandas-friendly rows, one per packet."""
import csv
import io
import json
import unittest

from ground.flights.export import flight_rows, rows_to_csv, rows_to_json, COLUMNS
from ground.flights.flights import Flight


def pkt(received_at, src, seq, alt, rssi=-60):
    return {"type": "packet", "received_at": received_at, "rssi": rssi,
            "sys": 7, "src": src, "seq": seq,
            "fields": {"SYS": 7, "SRC": src, "SEQ": seq, "St": 1, "ALT": alt, "Max": alt,
                       "G": 1.0, "Pg": 1.0, "T": 20.0, "Batt": 3.9, "MET": 0},
            "unknown": {}, "raw": "..."}


class TestExport(unittest.TestCase):
    def setUp(self):
        self.flight = Flight(flight_id="2026-07-08-F1", src=1,
                             t_start="2026-07-08T00:00:00Z", t_end="2026-07-08T00:00:02Z", stats={})
        self.records = [
            {"type": "event", "received_at": "2026-07-08T00:00:00Z", "event": "service_start"},  # excluded
            pkt("2026-07-08T00:00:00Z", 1, 1, 100),
            pkt("2026-07-08T00:00:01Z", 1, 2, 500),
            pkt("2026-07-08T00:00:02Z", 1, 3, 300),
            pkt("2026-07-08T00:00:01Z", 3, 5, 999),   # other SRC -> excluded
            pkt("2026-07-08T00:00:05Z", 1, 9, 111),   # after t_end -> excluded
        ]

    def test_filters_by_src_and_span(self):
        rows = flight_rows(self.records, self.flight)
        self.assertEqual([r["SEQ"] for r in rows], [1, 2, 3])
        self.assertEqual([r["ALT"] for r in rows], [100, 500, 300])
        self.assertTrue(all(r["flight_id"] == "2026-07-08-F1" for r in rows))

    def test_consistent_columns(self):
        rows = flight_rows(self.records, self.flight)
        for r in rows:
            self.assertEqual(list(r.keys()), COLUMNS)

    def test_csv_header_and_rows(self):
        text = rows_to_csv(flight_rows(self.records, self.flight))
        reader = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(reader), 3)
        self.assertEqual(reader[0]["flight_id"], "2026-07-08-F1")

    def test_json_roundtrips(self):
        rows = flight_rows(self.records, self.flight)
        self.assertEqual(json.loads(rows_to_json(rows)), rows)

    def test_missing_field_is_none(self):
        rec = pkt("2026-07-08T00:00:01Z", 1, 2, 500)
        del rec["fields"]["ALT"]
        rows = flight_rows([rec], self.flight)
        self.assertIsNone(rows[0]["ALT"])

    def test_a_bare_call_beacon_is_not_a_row_in_the_flight_trace(self):
        """Same policy as the index: frames that are not telemetry do not
        participate in flight accounting (ground/flights/segmenter.py
        is_telemetry). A bare `CALL` beacon inside the flight's window has no
        `St`/`ALT`/`SEQ`, so it would export as a row of nulls — and the CSV is
        the per-packet trace of the very flight whose `packets_rx` excludes it.
        A trace with more rows than `packets_rx` is a published artifact that
        contradicts its own summary."""
        beacon = {"type": "packet", "received_at": "2026-07-08T00:00:01Z", "rssi": -60,
                  "sys": 7, "src": 1, "seq": None, "fields": {"SYS": 7, "SRC": 1},
                  "unknown": {"CALL": "KC3ZTQ"}, "raw": "V:1 SYS:7 SRC:1 CALL:KC3ZTQ"}
        rows = flight_rows(self.records + [beacon], self.flight)
        self.assertEqual([r["SEQ"] for r in rows], [1, 2, 3])   # no null-only row

    def test_decode_error_packets_excluded(self):
        err = {"type": "packet", "received_at": "2026-07-08T00:00:01Z", "rssi": -60,
               "error": "malformed-token", "raw": "V:1 GARBAGE"}  # no src/fields
        rows = flight_rows([err], self.flight)
        self.assertEqual(rows, [])

    # --- The 10 Hz build's tags reach the archive (red-team #1 of the F2 publish
    # review, 2026-08-25): the export column list silently dropped every additive
    # tag, so F2's CSV would have carried none of the data the 10 Hz build exists
    # to produce. Columns follow the wire order (ADR 0005 A1.4). ---

    def test_new_tags_export_as_columns(self):
        rec = pkt("2026-07-08T00:00:01Z", 1, 2, 500)
        rec["fields"].update({"Vel": -12.3, "Gmx": 2.8, "Gmn": 0.5, "Wmx": 227.9})
        rows = flight_rows([rec], self.flight)
        self.assertEqual(rows[0]["Vel"], -12.3)
        self.assertEqual(rows[0]["Gmx"], 2.8)
        self.assertEqual(rows[0]["Gmn"], 0.5)
        self.assertEqual(rows[0]["Wmx"], 227.9)

    def test_pad_frame_raw_channels_export_as_columns(self):
        rec = pkt("2026-07-08T00:00:01Z", 1, 2, 500)
        rec["fields"]["St"] = 0
        rec["fields"].update({"Vel": 0.1, "Gmx": 1.0, "Gmn": 0.9,
                              "Gyx": 0.4, "Gyy": 0.5, "Gyz": -0.1,
                              "Mgx": -16.0, "Mgy": 24.4, "Mgz": 28.6})
        rows = flight_rows([rec], self.flight)
        self.assertEqual(rows[0]["Gyx"], 0.4)
        self.assertEqual(rows[0]["Mgz"], 28.6)
        self.assertIsNone(rows[0]["Wmx"])      # pad frames carry no Wmx: empty, not fake

    def test_old_records_get_empty_new_columns_not_errors(self):
        """Re-deriving F1 (pre-10 Hz records) stays valid: the new columns exist
        and are empty. Additive, deterministic — a re-export differs from the
        published F1 CSV only by empty superset columns."""
        rows = flight_rows(self.records, self.flight)      # fixtures have no new tags
        for r in rows:
            for tag in ("Vel", "Gmx", "Gmn", "Wmx", "Gyx", "Gyy", "Gyz",
                        "Mgx", "Mgy", "Mgz"):
                self.assertIn(tag, r)
                self.assertIsNone(r[tag])

    def test_column_order_is_base_then_wire_order(self):
        self.assertEqual(
            COLUMNS,
            ["flight_id", "received_at", "rssi",
             "SYS", "SRC", "SEQ", "St", "ALT", "Max", "G", "Pg", "T", "Batt", "MET",
             "Vel", "Gmx", "Gmn", "Wmx",
             "Gyx", "Gyy", "Gyz", "Mgx", "Mgy", "Mgz"])


if __name__ == "__main__":
    unittest.main()
