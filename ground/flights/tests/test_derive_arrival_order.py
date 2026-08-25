"""Arrival order is the AUTHORITY for session packets (found 2026-08-25, first
10 Hz field data): the session file's append order is the physical receive
order, but `received_at` wall stamps can invert by tens of ms (observed: 33 ms,
~20 s cadence, at the range). derive's time-sort re-ordered such packets, and
the segmenter's wraparound gap arithmetic turned each backwards pair into
~65,535 "lost" packets — flight F1 reported 720,906 lost from 11 inversions.
At 1 Hz an inversion can never cross packet boundaries; 10 Hz exposed it.

Two independent defenses, both pinned here:
 1. derive preserves session file order for packets (ops still interleave by time),
 2. the segmenter's gap stat treats a backwards/duplicate SEQ as a reordering
    artifact (0 lost), never as ~65k loss.
"""
import unittest

from ground.flights.derive import derive_flights
from ground.flights.segmenter import FlightSegmenter


def _pkt(ts, seq, st=2, alt=100):
    return {"type": "packet", "received_at": ts, "rssi": -60, "src": 1, "seq": seq,
            "fields": {"SYS": 7, "SRC": 1, "SEQ": seq, "St": st, "ALT": alt, "Max": alt}}


class TestDerivePreservesArrivalOrder(unittest.TestCase):
    def test_timestamp_inversion_does_not_manufacture_loss(self):
        # File order (= arrival order) is seq 1,2,3,4 — but seq 3's wall stamp
        # is EARLIER than seq 2's (the observed 33 ms inversion, exaggerated).
        recs = [
            _pkt("2026-08-25T21:04:06.900Z", 1, st=1),
            _pkt("2026-08-25T21:04:07.134Z", 2),
            _pkt("2026-08-25T21:04:07.101Z", 3),     # stamp earlier, arrival later
            _pkt("2026-08-25T21:04:07.300Z", 4),
        ]
        flights = derive_flights(recs, ops=[], silence_timeout_s=1)
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].stats["packets_lost"], 0)
        self.assertEqual(flights[0].stats["packets_rx"], 4)

    def test_real_gaps_still_counted_through_an_inversion(self):
        recs = [
            _pkt("2026-08-25T21:04:06.900Z", 1, st=1),
            _pkt("2026-08-25T21:04:07.134Z", 2),
            _pkt("2026-08-25T21:04:07.101Z", 3),     # inversion
            _pkt("2026-08-25T21:04:07.300Z", 7),     # 3 genuinely lost (4,5,6)
        ]
        flights = derive_flights(recs, ops=[], silence_timeout_s=1)
        self.assertEqual(flights[0].stats["packets_lost"], 3)

    def test_ops_still_interleave_by_time(self):
        # A manual close between two packet stamps must still take effect there:
        # the fix preserves PACKET order, not ops positioning.
        recs = [
            _pkt("2026-08-25T21:04:00.000Z", 1, st=1),
            _pkt("2026-08-25T21:10:00.000Z", 2, st=1),   # would extend the flight
        ]
        ops = [{"op": "close", "src": 1, "at": "2026-08-25T21:05:00.000Z"}]
        flights = derive_flights(recs, ops=ops, silence_timeout_s=9999)
        self.assertEqual(len(flights), 2)                # close split them


class TestSegmenterGapStatIsReorderTolerant(unittest.TestCase):
    """Defense in depth: even if a reordered stream reaches the segmenter, a
    backwards or duplicate SEQ is a reordering artifact, not ~65k lost."""

    def _seg_gaps(self, seqs):
        seg = FlightSegmenter(silence_timeout_s=9999)
        t = 0.0
        for i, s in enumerate(seqs):
            seg.observe(f"2026-08-25T21:00:0{i}.000Z", t + i, 1, 1, 100 + i, -60, s)
        return seg.close(1).stats["packets_lost"]

    def test_backwards_seq_adds_zero_not_65k(self):
        self.assertEqual(self._seg_gaps([10, 11, 12, 11, 13]), 0)

    def test_duplicate_seq_adds_zero(self):
        self.assertEqual(self._seg_gaps([10, 11, 11, 12]), 0)

    def test_genuine_wraparound_still_counts(self):
        # 65534 -> 2 across the uint16 wrap = 3 lost (65535, 0, 1): the wrap
        # case the modulo exists for must survive the tolerance.
        self.assertEqual(self._seg_gaps([65533, 65534, 2]), 3)

    def test_forward_gaps_unchanged(self):
        self.assertEqual(self._seg_gaps([1, 2, 10, 11]), 7)


if __name__ == "__main__":
    unittest.main()
