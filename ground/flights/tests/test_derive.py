"""Host tests for deriving the flights index from a session log."""
import unittest

from ground.flights.derive import derive_flights


def pkt(ts, src, st, alt, seq, rssi=-60):
    return {"type": "packet", "received_at": ts, "rssi": rssi, "src": src, "seq": seq,
            "fields": {"SYS": 7, "SRC": src, "SEQ": seq, "St": st, "ALT": alt}}


class TestDerive(unittest.TestCase):
    def test_single_flight_from_pad_ascent_descent(self):
        recs = [
            pkt("2026-07-08T00:00:00.000Z", 1, 0, -5, 1),    # pad — no flight
            pkt("2026-07-08T00:00:01.000Z", 1, 1, 100, 2),   # ascent — open
            pkt("2026-07-08T00:00:02.000Z", 1, 2, 500, 3),   # descent
        ]
        flights = derive_flights(recs, silence_timeout_s=90)
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].src, 1)
        self.assertEqual(flights[0].stats["peak_alt_ft"], 500)

    def test_two_flights_same_src_split_by_silence(self):
        recs = [
            pkt("2026-07-08T00:00:00.000Z", 1, 1, 100, 1),
            pkt("2026-07-08T00:05:00.000Z", 1, 1, 200, 2),   # 300 s later > 90 s -> new flight
        ]
        flights = derive_flights(recs, silence_timeout_s=90)
        self.assertEqual(len(flights), 2)
        self.assertNotEqual(flights[0].flight_id, flights[1].flight_id)

    def test_multibird_two_srcs(self):
        recs = [
            pkt("2026-07-08T00:00:00.000Z", 1, 1, 100, 1),
            pkt("2026-07-08T00:00:05.000Z", 3, 1, 900, 1),
        ]
        flights = derive_flights(recs, silence_timeout_s=90)
        self.assertEqual({f.src for f in flights}, {1, 3})

    def test_events_and_errors_ignored(self):
        recs = [
            {"type": "event", "received_at": "2026-07-08T00:00:00.000Z", "event": "service_start"},
            {"type": "packet", "received_at": "2026-07-08T00:00:00.000Z", "rssi": -60,
             "error": "malformed-token", "raw": "V:1 GARBAGE"},           # no fields
            pkt("2026-07-08T00:00:01.000Z", 1, 0, -5, 1),                 # pad only, never ascends
        ]
        self.assertEqual(derive_flights(recs), [])

    def test_manual_close_and_annotate_survive_rebuild(self):
        session = [
            pkt("2026-07-08T00:00:00.000Z", 1, 1, 100, 1),
            pkt("2026-07-08T00:00:01.000Z", 1, 1, 500, 2),
            pkt("2026-07-08T00:00:02.000Z", 1, 1, 600, 3),
        ]
        ops = [
            {"op": "close", "src": 1, "at": "2026-07-08T00:00:01.000Z"},
            {"op": "annotate", "src": 1, "at": "2026-07-08T00:00:00.000Z", "label": "Maiden", "motor": "F15"},
        ]
        flights = derive_flights(session, ops, silence_timeout_s=90)
        self.assertEqual(len(flights), 2)                              # manual close split the run
        f1 = next(f for f in flights if f.t_start == "2026-07-08T00:00:00.000Z")
        self.assertEqual(f1.t_end, "2026-07-08T00:00:01.000Z")        # closed at the manual time
        self.assertEqual(f1.label, "Maiden")                          # annotation survived derivation
        self.assertEqual(f1.motor, "F15")

    def test_manual_close_beats_silence(self):
        session = [
            pkt("2026-07-08T00:00:00.000Z", 1, 1, 100, 1),
            pkt("2026-07-08T00:03:20.000Z", 1, 1, 200, 2),            # 200 s gap > 90 s silence
        ]
        self.assertEqual(len(derive_flights(session, silence_timeout_s=90)), 2)     # auto-splits
        ops = [{"op": "close", "src": 1, "at": "2026-07-08T00:05:00.000Z"}]         # pending close protects
        self.assertEqual(len(derive_flights(session, ops, silence_timeout_s=90)), 1)  # silence suppressed


if __name__ == "__main__":
    unittest.main()
