"""Host tests for the flight segmentation state machine.

Pure: timestamps + a monotonic clock are passed in, so open/close decisions and
stats are deterministic (Mac + Pi). Flights are derived metadata over the packet
stream — concurrent open flights per SRC (multi-bird), open on St->ascent, close
on silence-timeout or manual close.
"""
import unittest

from ground.flights.segmenter import FlightSegmenter
from ground.flights.flights import Flight


class TestSegmenter(unittest.TestCase):
    def obs(self, seg, received_at, t, src, st, alt=0, rssi=-60, seq=0):
        return seg.observe(received_at, t, src, st, alt, rssi, seq)

    def test_pad_packets_do_not_open_flight(self):
        seg = FlightSegmenter()
        self.obs(seg, "2026-07-08T00:00:00Z", 0.0, 1, st=0, alt=-5)
        self.obs(seg, "2026-07-08T00:00:01Z", 1.0, 1, st=0, alt=-5)
        self.assertEqual(seg.open_srcs(), [])
        self.assertEqual(seg.check_timeouts(1000.0), [])

    def test_ascent_opens_flight(self):
        seg = FlightSegmenter()
        self.obs(seg, "2026-07-08T00:00:00Z", 0.0, 1, st=1, alt=100, seq=1)
        self.assertEqual(seg.open_srcs(), [1])

    def test_silence_closes_with_stats(self):
        seg = FlightSegmenter(silence_timeout_s=90)
        self.obs(seg, "2026-07-08T00:00:00Z", 0.0, 1, st=1, alt=100, rssi=-50, seq=1)
        self.obs(seg, "2026-07-08T00:00:01Z", 1.0, 1, st=1, alt=500, rssi=-60, seq=2)
        self.obs(seg, "2026-07-08T00:00:02Z", 2.0, 1, st=2, alt=300, rssi=-55, seq=4)  # seq 3 missed
        closed = seg.check_timeouts(93.0)  # 91 s of silence -> close
        self.assertEqual(len(closed), 1)
        fl = closed[0]
        self.assertIsInstance(fl, Flight)
        self.assertEqual(fl.src, 1)
        self.assertTrue(fl.flight_id.endswith("F1"))
        self.assertEqual(fl.stats["peak_alt_ft"], 500)
        self.assertEqual(fl.stats["packets_rx"], 3)
        self.assertEqual(fl.stats["packets_lost"], 1)
        self.assertEqual(fl.stats["rssi_min"], -60)
        self.assertEqual(fl.stats["rssi_max"], -50)
        self.assertAlmostEqual(fl.stats["duration_s"], 2.0)
        self.assertEqual(fl.t_start, "2026-07-08T00:00:00Z")
        self.assertEqual(fl.t_end, "2026-07-08T00:00:02Z")
        self.assertEqual(seg.open_srcs(), [])

    def test_manual_close(self):
        seg = FlightSegmenter()
        self.obs(seg, "2026-07-08T00:00:00Z", 0.0, 1, st=1, alt=100)
        self.assertIsInstance(seg.close(1), Flight)
        self.assertEqual(seg.open_srcs(), [])
        self.assertIsNone(seg.close(1))  # already closed

    def test_concurrent_multibird_overlapping(self):
        seg = FlightSegmenter(silence_timeout_s=30)
        self.obs(seg, "2026-07-08T00:00:00Z", 0.0, 1, st=1, alt=100, seq=1)
        self.obs(seg, "2026-07-08T00:00:10Z", 10.0, 1, st=1, alt=900, seq=2)
        self.obs(seg, "2026-07-08T00:00:20Z", 20.0, 3, st=1, alt=100, seq=1)   # SRC 3 boosts 20 s later
        self.assertEqual(sorted(seg.open_srcs()), [1, 3])                       # concurrent
        self.obs(seg, "2026-07-08T00:00:22Z", 22.0, 1, st=2, alt=800, seq=3)
        self.obs(seg, "2026-07-08T00:00:35Z", 35.0, 3, st=1, alt=1200, seq=2)
        closed = seg.check_timeouts(200.0)
        self.assertEqual(len(closed), 2)
        by_src = {f.src: f for f in closed}
        self.assertEqual(set(by_src), {1, 3})
        self.assertNotEqual(by_src[1].flight_id, by_src[3].flight_id)           # distinct ids
        self.assertEqual(by_src[1].stats["peak_alt_ft"], 900)                   # independent peaks
        self.assertEqual(by_src[3].stats["peak_alt_ft"], 1200)
        self.assertLess(by_src[1].t_start, by_src[3].t_start)                   # overlapping spans
        self.assertEqual({by_src[1].flight_id[-2:], by_src[3].flight_id[-2:]}, {"F1", "F2"})

    def test_reopen_after_close_gets_new_id(self):
        seg = FlightSegmenter(silence_timeout_s=10)
        self.obs(seg, "2026-07-08T00:00:00Z", 0.0, 1, st=1, alt=100)
        first = seg.check_timeouts(20.0)[0]
        self.obs(seg, "2026-07-08T00:05:00Z", 300.0, 1, st=1, alt=100)          # new boost, same day
        self.assertEqual(seg.open_srcs(), [1])
        second = seg.close(1)
        self.assertNotEqual(first.flight_id, second.flight_id)                  # ids never reused


if __name__ == "__main__":
    unittest.main()
