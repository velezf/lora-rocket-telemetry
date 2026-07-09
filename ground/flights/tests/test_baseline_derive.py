"""v2 baseline in the DERIVE path — the pad zero is recomputed retrospectively at
flight_open and stored in the flight's index entry (stats.baseline_ft / baseline_n).

Fixture scenarios from the kickoff: boot-transient settling curve -> excluded;
carry-to-pad motion -> excluded (unstable); long pad with slow drift -> baseline
tracks the late quiet window, not the stale early one.
"""
import unittest

from ground.flights.derive import derive_flights


def _ts(sec):
    m, s = divmod(sec, 60)
    return f"2026-07-08T00:{m:02d}:{s:02d}.000Z"


def _pkt(sec, st, alt, seq, src=1):
    return {"type": "packet", "received_at": _ts(sec), "rssi": -60, "src": src, "seq": seq,
            "fields": {"SYS": 7, "SRC": src, "SEQ": seq, "St": st, "ALT": alt}}


def _flight(pad_alts, boost_alt=100):
    """Derive one flight from a pad run (St:0) followed by a boost (St:1)."""
    recs = [_pkt(i, 0, a, i + 1) for i, a in enumerate(pad_alts)]
    recs.append(_pkt(len(pad_alts), 1, boost_alt, len(pad_alts) + 1))
    flights = derive_flights(recs, silence_timeout_s=90)
    assert len(flights) == 1
    return flights[0]


class TestBaselineInIndex(unittest.TestCase):
    def test_baseline_stored_in_index_entry(self):
        f = _flight([-84] * 20)
        self.assertEqual(f.stats["baseline_ft"], -84)
        self.assertEqual(f.stats["baseline_n"], 15)

    def test_boot_transient_settling_curve_excluded(self):
        # power-on settling, then a long quiet pad -> trailing window is all quiet
        f = _flight([-300, -200, -140, -100] + [-84] * 20)
        self.assertEqual(f.stats["baseline_ft"], -84)

    def test_carry_to_pad_motion_is_unstable_no_baseline(self):
        f = _flight([-84, -55] * 10)                    # noisy handling on the way to the pad
        self.assertIsNone(f.stats["baseline_ft"])
        self.assertEqual(f.stats["baseline_n"], 0)

    def test_slow_drift_tracks_late_quiet_window(self):
        f = _flight(list(range(-100, -85)) + [-84] * 15)   # early drift, late settle
        self.assertEqual(f.stats["baseline_ft"], -84)      # late window, not the stale -9x

    def test_second_flight_reestablishes_its_own_baseline(self):
        # pad A -> flight A (silence) -> pad B (different level) -> flight B
        recs = [_pkt(i, 0, -84, i + 1) for i in range(18)]
        recs.append(_pkt(18, 1, 50, 19))                    # flight A opens
        recs += [_pkt(200 + i, 0, -40, 100 + i) for i in range(18)]   # 90s+ silence, new pad level
        recs.append(_pkt(220, 1, 90, 130))                  # flight B opens
        flights = derive_flights(recs, silence_timeout_s=90)
        self.assertEqual(len(flights), 2)
        self.assertEqual(flights[0].stats["baseline_ft"], -84)
        self.assertEqual(flights[1].stats["baseline_ft"], -40)   # B's own pad, not A's


if __name__ == "__main__":
    unittest.main()
