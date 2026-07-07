"""Host tests for the Epic 4.3 flights index model.

Pure Python, no radio/file/I-O — must pass on both Mac and Pi
(`python3 -m unittest`). Covers the flight-id scheme (design decision D2) and
round-trippable index (de)serialization. No open/close segmentation here.
"""
import unittest

from ground.flights.flights import (
    Flight,
    next_flight_id,
    flights_to_json,
    flights_from_json,
)


class TestNextFlightId(unittest.TestCase):
    def test_first_flight_of_date_is_f1(self):
        self.assertEqual(next_flight_id("2026-07-07", []), "2026-07-07-F1")

    def test_second_flight_same_date_is_f2(self):
        self.assertEqual(
            next_flight_id("2026-07-07", ["2026-07-07-F1"]),
            "2026-07-07-F2",
        )

    def test_new_date_starts_at_f1(self):
        existing = ["2026-07-06-F1", "2026-07-06-F2"]
        self.assertEqual(next_flight_id("2026-07-07", existing), "2026-07-07-F1")

    def test_other_dates_ignored_in_count(self):
        existing = [
            "2026-07-06-F1",
            "2026-07-06-F2",
            "2026-07-07-F1",
            "2026-08-01-F9",
        ]
        self.assertEqual(next_flight_id("2026-07-07", existing), "2026-07-07-F2")


class TestFlightRoundTrip(unittest.TestCase):
    def test_round_trip_full(self):
        flights = [
            Flight(
                flight_id="2026-07-07-F1",
                src=1,
                t_start="2026-07-07T12:00:00Z",
                t_end="2026-07-07T12:05:00Z",
                label="first launch",
                motor="F44",
                field="Potter",
                stats={
                    "peak_alt_ft": 1234,
                    "duration_s": 300,
                    "packets_rx": 512,
                    "packets_lost": 3,
                    "rssi_min": -110,
                    "rssi_max": -42,
                },
            ),
            Flight(flight_id="2026-07-07-F2", src=2, t_start=None, t_end=None),
        ]
        restored = flights_from_json(flights_to_json(flights))
        self.assertEqual(restored, flights)

    def test_defaults_round_trip(self):
        f = Flight(flight_id="2026-07-07-F1", src=1, t_start=None, t_end=None)
        self.assertEqual(f.label, "")
        self.assertEqual(f.motor, "")
        self.assertEqual(f.field, "")
        self.assertEqual(f.stats, {})
        restored = flights_from_json(flights_to_json([f]))
        self.assertEqual(restored, [f])

    def test_json_is_a_list_of_objects(self):
        import json

        f = Flight(flight_id="2026-07-07-F1", src=1, t_start=None, t_end=None)
        parsed = json.loads(flights_to_json([f]))
        self.assertIsInstance(parsed, list)
        self.assertEqual(parsed[0]["flight_id"], "2026-07-07-F1")
        self.assertEqual(parsed[0]["stats"], {})


if __name__ == "__main__":
    unittest.main()
