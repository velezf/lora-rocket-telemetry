"""Host tests for LiveFlights — driven entirely by injected timestamps.

Wall time (`received_at`) is what gets recorded; a monotonic value (`mono`) drives
the silence sweep, so a wall-clock step (NTP/RTC jump) can't spuriously close a flight.
"""
import json
import tempfile
import unittest
from pathlib import Path

from ground.flights.live import LiveFlights
from ground.ingest.core import Observation
from ground.decode.v1 import decode


def obs(received_at, mono, src, st, alt, seq, rssi=-60):
    p = decode(f"V:1 SYS:7 SRC:{src} SEQ:{seq} St:{st} ALT:{alt}ft".encode())
    return Observation(received_at, rssi, p, mono)


class TestLiveFlights(unittest.TestCase):
    def test_open_and_close_events(self):
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snap.json"
            lines = []
            live = LiveFlights(lines.append, snap, silence_timeout_s=90)
            live.on_observation(obs("2026-07-08T00:00:00.000Z", 0.0, 1, 1, 100, 1))
            live.on_observation(obs("2026-07-08T00:00:01.000Z", 1.0, 1, 2, 500, 2))
            events = [json.loads(x) for x in lines]
            self.assertTrue(any(e.get("event") == "flight_open" and e["src"] == 1 for e in events))
            live.tick("2026-07-08T00:02:00.000Z", 120.0)   # 120 s mono > 90 -> close
            events = [json.loads(x) for x in lines]
            self.assertTrue(any(e.get("event") == "flight_close" and e["src"] == 1 for e in events))
            self.assertEqual(len(json.loads(snap.read_text())), 1)

    def test_shutdown_leaves_open_flight_open(self):
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snap.json"
            lines = []
            live = LiveFlights(lines.append, snap, silence_timeout_s=90)
            live.on_observation(obs("2026-07-08T00:00:00.000Z", 0.0, 1, 1, 100, 1))
            live.tick("2026-07-08T00:00:30.000Z", 30.0)     # 30 s mono < 90 -> still active
            self.assertEqual(live.open_srcs(), [1])
            self.assertEqual([x for x in lines if "flight_close" in x], [])
            self.assertFalse(snap.exists())

    def test_wall_clock_jump_does_not_close_flight(self):
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snap.json"
            lines = []
            live = LiveFlights(lines.append, snap, silence_timeout_s=90)
            live.on_observation(obs("2026-07-08T00:00:00.000Z", 0.0, 1, 1, 100, 1))
            # wall clock LEAPS forward 1 h (NTP correction) but mono advances only 2 s
            live.on_observation(obs("2026-07-08T01:00:02.000Z", 2.0, 1, 1, 500, 2))
            live.tick("2026-07-08T01:00:05.000Z", 5.0)      # 5 s mono -> NOT closed despite the wall jump
            self.assertEqual(live.open_srcs(), [1])
            self.assertEqual([x for x in lines if "flight_close" in x], [])
            # a real mono silence closes it; the record carries the stepped wall time
            live.tick("2026-07-08T01:02:00.000Z", 200.0)    # 200 s mono > 90 -> close
            closed = json.loads(snap.read_text())
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0]["t_end"], "2026-07-08T01:00:02.000Z")


if __name__ == "__main__":
    unittest.main()
