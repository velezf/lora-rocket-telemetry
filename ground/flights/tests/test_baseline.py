"""Host tests for the v2 pad-baseline (stability-gated trailing TIME window).

Replaces the naive "rolling mean of all St:0 ALT". Pure function: a trailing,
time-ordered sequence of pre-boost pad (t, ALT) samples in, (baseline_ft, n_used)
out. The window is wall-clock seconds (ADR 0005 §7 — a sample count calibrated in
seconds shrank to 1.5 s at 10 Hz); the variance gate threshold is derived from
real F1 pad noise. Rate-independence itself is pinned in
test_baseline_time_window.py; these are the original 1 Hz behaviour scenarios,
where the time window reproduces the old sample-count semantics exactly.
See docs/agl-baseline-v2-audit.md.
"""
import unittest

from ground.flights.baseline import pad_baseline


def _at_1hz(alts):
    """The original flat-altitude fixtures, stamped at the ~1 Hz ground rate."""
    return [(float(i), a) for i, a in enumerate(alts)]


class TestPadBaseline(unittest.TestCase):
    def test_stable_window_locks_mean(self):
        base, n = pad_baseline(_at_1hz([-84] * 20))
        self.assertEqual(base, -84)
        self.assertEqual(n, 15)                         # 15 s window at 1 Hz

    def test_excludes_final_preboost_samples(self):
        # last 2 s are pre-boost handling spikes; must not skew the baseline
        base, n = pad_baseline(_at_1hz([-84] * 17 + [30, 45]))
        self.assertEqual(base, -84)
        self.assertEqual(n, 15)

    def test_unstable_window_falls_back_to_none(self):
        base, n = pad_baseline(_at_1hz([-84, -70] * 12))    # ~7 ft stdev >> 2.0 gate
        self.assertIsNone(base)
        self.assertEqual(n, 0)

    def test_boot_transient_at_start_is_excluded_by_trailing_window(self):
        # a settling curve at power-on, then a long quiet pad -> trailing window is
        # all quiet; the early transient never enters it
        samples = _at_1hz([-260, -180, -130, -100] + [-84] * 20)
        base, n = pad_baseline(samples)
        self.assertEqual(base, -84)

    def test_slow_drift_tracks_late_quiet_window_not_stale_early(self):
        early_drift = list(range(-100, -90))            # noisy early climb
        late_quiet = [-84] * 20
        base, _ = pad_baseline(_at_1hz(early_drift + late_quiet))
        self.assertEqual(base, -84)                     # late window, not the stale -95ish

    def test_gate_boundary_passes_at_threshold(self):
        # a window with stdev just under 2.0 ft still locks
        base, _ = pad_baseline(_at_1hz([-85, -83] * 8), max_stdev=2.0)   # stdev 1.0
        self.assertIsNotNone(base)

    def test_none_samples_filtered(self):
        base, n = pad_baseline(_at_1hz([None] * 2 + [-84] * 18))
        self.assertEqual(base, -84)

    def test_too_few_samples_returns_none(self):
        base, n = pad_baseline(_at_1hz([-84, -84]))     # both inside the 2 s tail
        self.assertIsNone(base)
        self.assertEqual(n, 0)

    def test_empty_returns_none(self):
        base, n = pad_baseline([])
        self.assertIsNone(base)
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
