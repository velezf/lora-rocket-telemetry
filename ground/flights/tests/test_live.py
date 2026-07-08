"""Host tests for LiveFlights — driven entirely by injected timestamps."""
import json
import tempfile
import unittest
from pathlib import Path

from ground.flights.live import LiveFlights
from ground.ingest.core import Observation
from ground.decode.v1 import decode


def obs(received_at, src, st, alt, seq, rssi=-60):
    p = decode(f"V:1 SYS:7 SRC:{src} SEQ:{seq} St:{st} ALT:{alt}ft".encode())
    return Observation(received_at, rssi, p)


class TestLiveFlights(unittest.TestCase):
    def test_open_and_close_events_from_injected_time(self):
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snap.json"
            lines = []
            live = LiveFlights(lines.append, snap, silence_timeout_s=90)
            live.on_observation(obs("2026-07-08T00:00:00.000Z", 1, 1, 100, 1))
            live.on_observation(obs("2026-07-08T00:00:01.000Z", 1, 2, 500, 2))
            events = [json.loads(x) for x in lines]
            self.assertTrue(any(e.get("event") == "flight_open" and e["src"] == 1 for e in events))
            live.tick("2026-07-08T00:02:00.000Z")   # 119 s > 90 s (injected now) -> close
            events = [json.loads(x) for x in lines]
            self.assertTrue(any(e.get("event") == "flight_close" and e["src"] == 1 for e in events))
            self.assertEqual(len(json.loads(snap.read_text())), 1)   # closed flight in the snapshot

    def test_shutdown_leaves_open_flight_open(self):
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snap.json"
            lines = []
            live = LiveFlights(lines.append, snap, silence_timeout_s=90)
            live.on_observation(obs("2026-07-08T00:00:00.000Z", 1, 1, 100, 1))
            live.tick("2026-07-08T00:00:30.000Z")   # final sweep within the window (30 s < 90 s)
            self.assertEqual(live.open_srcs(), [1])                  # still OPEN
            self.assertEqual([x for x in lines if "flight_close" in x], [])  # no close emitted
            self.assertFalse(snap.exists())                         # nothing closed -> no snapshot


if __name__ == "__main__":
    unittest.main()
