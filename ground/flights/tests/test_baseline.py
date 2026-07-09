"""Host tests for the v2 pad-baseline (stability-gated trailing window).

Replaces the naive "rolling mean of all St:0 ALT". Pure function: a trailing
sequence of pre-boost pad ALT samples in, (baseline_ft, n_used) out. Mirrors the
V1 window length (~short average just before use) but adds a variance gate the V1
firmware never had — threshold derived from real F1 pad noise. See
docs/agl-baseline-v2-audit.md.
"""
import unittest

from ground.flights.baseline import pad_baseline


class TestPadBaseline(unittest.TestCase):
    def test_stable_window_locks_mean(self):
        base, n = pad_baseline([-84] * 20)
        self.assertEqual(base, -84)
        self.assertEqual(n, 15)                         # default window

    def test_excludes_final_preboost_samples(self):
        # last 2 samples are pre-boost handling spikes; must not skew the baseline
        base, n = pad_baseline([-84] * 17 + [30, 45])
        self.assertEqual(base, -84)
        self.assertEqual(n, 15)

    def test_unstable_window_falls_back_to_none(self):
        base, n = pad_baseline([-84, -70] * 12)         # ~7 ft stdev >> 2.0 gate
        self.assertIsNone(base)
        self.assertEqual(n, 0)

    def test_boot_transient_at_start_is_excluded_by_trailing_window(self):
        # a settling curve at power-on, then a long quiet pad -> trailing window is
        # all quiet; the early transient never enters it
        samples = [-260, -180, -130, -100] + [-84] * 20
        base, n = pad_baseline(samples)
        self.assertEqual(base, -84)

    def test_slow_drift_tracks_late_quiet_window_not_stale_early(self):
        early_drift = list(range(-100, -90))            # noisy early climb
        late_quiet = [-84] * 20
        base, _ = pad_baseline(early_drift + late_quiet)
        self.assertEqual(base, -84)                     # late window, not the stale -95ish

    def test_gate_boundary_passes_at_threshold(self):
        # a window with stdev just under 2.0 ft still locks
        base, _ = pad_baseline([-85, -83] * 8, max_stdev=2.0)   # stdev 1.0
        self.assertIsNotNone(base)

    def test_none_samples_filtered(self):
        base, n = pad_baseline([None] * 2 + [-84] * 18)
        self.assertEqual(base, -84)

    def test_too_few_samples_returns_none(self):
        base, n = pad_baseline([-84, -84])              # both dropped by exclude_tail
        self.assertIsNone(base)
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
