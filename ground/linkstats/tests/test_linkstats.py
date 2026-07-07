"""Host tests for the per-(SYS,SRC) link statistics tracker (Epic 4.3).

Pure Python, no radio/I-O imports — must pass on both Mac and Pi
(`python3 -m unittest`). Mirrors the discipline of ground/decode.

Design decision D3: loss/quality stats are tracked PER (sys, src) key, never a
global last_seq. A gap in one source must never affect another. SEQ is a uint16
that wraps at 65535 (ADR 0001), so missed-packet inference is modulo 65536.
"""
import unittest

from ground.linkstats.linkstats import LinkStats


class TestLinkStatsBasics(unittest.TestCase):
    def test_first_packet_seeds_with_zero_gaps(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=100, rssi=-50)
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["rx"], 1)
        self.assertEqual(snap[(7, 1)]["gaps"], 0)
        self.assertEqual(snap[(7, 1)]["last_seq"], 100)

    def test_consecutive_packets_no_gaps(self):
        ls = LinkStats()
        for seq in (5, 6, 7, 8):
            ls.update(sys=7, src=1, seq=seq, rssi=-40)
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["rx"], 4)
        self.assertEqual(snap[(7, 1)]["gaps"], 0)
        self.assertEqual(snap[(7, 1)]["last_seq"], 8)

    def test_single_gap_counts_missed(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=5, rssi=-40)
        ls.update(sys=7, src=1, seq=8, rssi=-40)  # 6,7 missed -> 2
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["rx"], 2)
        self.assertEqual(snap[(7, 1)]["gaps"], 2)
        self.assertEqual(snap[(7, 1)]["last_seq"], 8)


class TestPerSourceIndependence(unittest.TestCase):
    def test_interleaved_sources_independent_gaps(self):
        ls = LinkStats()
        # Same SYS, two sources, interleaved, each with its own gap.
        ls.update(sys=7, src=1, seq=1, rssi=-30)
        ls.update(sys=7, src=2, seq=100, rssi=-60)
        ls.update(sys=7, src=1, seq=2, rssi=-30)    # SRC1 no gap
        ls.update(sys=7, src=2, seq=103, rssi=-60)  # SRC2 missed 101,102 -> 2
        ls.update(sys=7, src=1, seq=5, rssi=-30)    # SRC1 missed 3,4 -> 2
        ls.update(sys=7, src=2, seq=104, rssi=-60)  # SRC2 no gap

        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["rx"], 3)
        self.assertEqual(snap[(7, 1)]["gaps"], 2)
        self.assertEqual(snap[(7, 1)]["last_seq"], 5)
        self.assertEqual(snap[(7, 2)]["rx"], 3)
        self.assertEqual(snap[(7, 2)]["gaps"], 2)
        self.assertEqual(snap[(7, 2)]["last_seq"], 104)

    def test_gap_in_one_source_never_touches_other(self):
        ls = LinkStats()
        ls.update(sys=1, src=1, seq=10, rssi=-10)
        ls.update(sys=1, src=2, seq=10, rssi=-10)
        # Huge jump on src 1 only.
        ls.update(sys=1, src=1, seq=1000, rssi=-10)
        ls.update(sys=1, src=2, seq=11, rssi=-10)
        snap = ls.snapshot()
        self.assertEqual(snap[(1, 1)]["gaps"], 989)
        self.assertEqual(snap[(1, 2)]["gaps"], 0)

    def test_same_src_different_sys_are_distinct_keys(self):
        ls = LinkStats()
        ls.update(sys=1, src=1, seq=5, rssi=-10)
        ls.update(sys=2, src=1, seq=50, rssi=-10)
        snap = ls.snapshot()
        self.assertIn((1, 1), snap)
        self.assertIn((2, 1), snap)
        self.assertEqual(snap[(1, 1)]["last_seq"], 5)
        self.assertEqual(snap[(2, 1)]["last_seq"], 50)


class TestWraparound(unittest.TestCase):
    def test_wrap_no_missed(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=65535, rssi=-40)
        ls.update(sys=7, src=1, seq=0, rssi=-40)  # 0 missed across wrap
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["gaps"], 0)
        self.assertEqual(snap[(7, 1)]["last_seq"], 0)

    def test_wrap_with_missed(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=65535, rssi=-40)
        ls.update(sys=7, src=1, seq=2, rssi=-40)  # 0,1 missed -> 2
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["gaps"], 2)
        self.assertEqual(snap[(7, 1)]["last_seq"], 2)

    def test_no_wrap_still_counts(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=5, rssi=-40)
        ls.update(sys=7, src=1, seq=8, rssi=-40)  # 6,7 -> 2
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["gaps"], 2)


class TestRssiStats(unittest.TestCase):
    def test_min_max_mean(self):
        ls = LinkStats()
        for i, r in enumerate((-50, -30, -70, -40), start=1):
            ls.update(sys=7, src=1, seq=i, rssi=r)
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["rssi_min"], -70)
        self.assertEqual(snap[(7, 1)]["rssi_max"], -30)
        self.assertAlmostEqual(snap[(7, 1)]["rssi_mean"], (-50 - 30 - 70 - 40) / 4.0)

    def test_single_packet_rssi(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=1, rssi=-42)
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["rssi_min"], -42)
        self.assertEqual(snap[(7, 1)]["rssi_max"], -42)
        self.assertEqual(snap[(7, 1)]["rssi_mean"], -42)

    def test_rssi_none_is_ignored(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=1, rssi=None)
        ls.update(sys=7, src=1, seq=2, rssi=-60)
        snap = ls.snapshot()
        self.assertEqual(snap[(7, 1)]["rx"], 2)
        self.assertEqual(snap[(7, 1)]["rssi_min"], -60)
        self.assertEqual(snap[(7, 1)]["rssi_max"], -60)
        self.assertEqual(snap[(7, 1)]["rssi_mean"], -60)

    def test_rssi_all_none(self):
        ls = LinkStats()
        ls.update(sys=7, src=1, seq=1, rssi=None)
        snap = ls.snapshot()
        self.assertIsNone(snap[(7, 1)]["rssi_min"])
        self.assertIsNone(snap[(7, 1)]["rssi_max"])
        self.assertIsNone(snap[(7, 1)]["rssi_mean"])


if __name__ == "__main__":
    unittest.main()
