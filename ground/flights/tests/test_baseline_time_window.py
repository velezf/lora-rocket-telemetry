"""The pad-baseline window is TIME-based, not sample-count-based (ADR 0005 §7).

`WINDOW = 15` was a *sample* count calibrated in *seconds* at the ~1 Hz ground
packet rate. At 10 Hz TX (ADR 0005) the same constant silently shrinks the AGL
baseline window to 1.5 s — quiet enough to pass the variance gate on data that
is nothing like a settled pad. These tests pin the property that matters: the
SAME wall-clock window of pad data produces the SAME baseline at ANY packet
rate, and a 10 Hz stream must NOT lock on 1.5 s of data.

`pad_baseline` therefore takes time-ordered (t_seconds, alt_ft) pairs; the
clock is the caller's monotonic time (the segmenter's `t`, the dashboard's
`obs.mono`, derive's epoch seconds) — only differences matter.
"""
import unittest

from ground.flights.baseline import (
    pad_baseline, trim_history, WINDOW_S, EXCLUDE_TAIL_S, HIST_KEEP_S,
)


def _stream(rate_hz, duration_s, alt_fn, t0=0.0):
    """(t, alt) pairs at a fixed rate: alt_fn(t) -> altitude."""
    dt = 1.0 / rate_hz
    n = round(duration_s * rate_hz)
    return [(t0 + i * dt, alt_fn(t0 + i * dt)) for i in range(n)]


def _quiet(_t):
    return -84


class TestSameWallClockWindowAtAnyRate(unittest.TestCase):
    def test_same_15s_of_pad_data_same_baseline_at_1hz_and_10hz(self):
        # 20 s of quiet pad: identical wall-clock content at both rates.
        b1, n1 = pad_baseline(_stream(1, 20, _quiet))
        b10, n10 = pad_baseline(_stream(10, 20, _quiet))
        self.assertEqual(b1, -84)
        self.assertEqual(b10, -84)
        self.assertEqual(b1, b10)
        # n_used stays a sample count, so it scales with rate — 15 s worth each.
        self.assertEqual(n1, 15)
        self.assertEqual(n10, 150)

    def test_early_junk_outside_the_window_is_excluded_at_both_rates(self):
        # 2 s of boot transient, then 18 s of quiet: the trailing 15 s window
        # (after the 2 s tail exclusion) holds only quiet samples at any rate.
        def alt(t):
            return -300 if t < 2.0 else -84
        for rate in (1, 10):
            base, _ = pad_baseline(_stream(rate, 20, alt))
            self.assertEqual(base, -84, f"rate {rate} Hz")

    def test_motion_inside_the_window_fails_the_gate_at_both_rates(self):
        # Carry-to-pad motion 10 s ago sits INSIDE the 15 s window at any rate.
        def alt(t):
            return -40 if 9.0 <= t < 11.0 else -84
        for rate in (1, 10):
            base, n = pad_baseline(_stream(rate, 20, alt))
            self.assertIsNone(base, f"rate {rate} Hz")
            self.assertEqual(n, 0)


class TestTenHertzDoesNotShrinkTheWindow(unittest.TestCase):
    def test_10hz_must_not_lock_on_1p5_seconds_of_quiet(self):
        """THE defect this change exists to prevent (ADR 0005 §7): at 10 Hz the
        old 15-SAMPLE window spans 1.5 s, so a rocket still being handled looks
        'quiet' the moment the last ~17 samples settle. 17 s of motion followed
        by 3 s of quiet must NOT produce a baseline — the 15 s window still
        contains the motion."""
        def alt(t):
            return -84 + (10 if int(t * 2) % 2 else -10) if t < 17.0 else -84
        base, n = pad_baseline(_stream(10, 20, alt))
        self.assertIsNone(base)
        self.assertEqual(n, 0)

    def test_exclude_tail_is_2_seconds_not_2_samples(self):
        # Boost-onset spikes fill the final 2 s. At 10 Hz that is 20 samples;
        # a 2-SAMPLE exclusion would leave 18 spikes inside the window.
        def alt(t):
            return 45 if t >= 18.0 else -84
        base, n = pad_baseline(_stream(10, 20, alt))
        self.assertEqual(base, -84)
        self.assertEqual(n, 150)


class TestOneHertzBehaviourPreserved(unittest.TestCase):
    """The old sample-count semantics WERE the time semantics at exactly 1 Hz.
    These mirror ground/flights/tests/test_baseline.py's original scenarios."""

    def test_quiet_pad_locks_15_samples(self):
        base, n = pad_baseline(_stream(1, 20, _quiet))
        self.assertEqual((base, n), (-84, 15))

    def test_final_two_seconds_excluded(self):
        def alt(t):
            return {18.0: 30, 19.0: 45}.get(t, -84)
        base, n = pad_baseline(_stream(1, 20, alt))
        self.assertEqual((base, n), (-84, 15))

    def test_two_samples_all_within_exclude_tail(self):
        base, n = pad_baseline([(0.0, -84), (1.0, -84)])
        self.assertIsNone(base)
        self.assertEqual(n, 0)


class TestTrimHistory(unittest.TestCase):
    def test_keeps_exactly_what_a_future_baseline_can_use(self):
        # After trimming, a baseline over the trimmed history equals one over
        # the full history — nothing usable was dropped.
        full = _stream(10, 60, _quiet)
        trimmed = trim_history(full)
        self.assertEqual(pad_baseline(trimmed), pad_baseline(full))

    def test_bounded_by_time_not_count(self):
        # 60 s at 10 Hz trims to the trailing HIST_KEEP_S seconds.
        trimmed = trim_history(_stream(10, 60, _quiet))
        span = trimmed[-1][0] - trimmed[0][0]
        self.assertLessEqual(span, HIST_KEEP_S)
        # and it retains a full window's worth: 15 s + 2 s tail at 10 Hz.
        self.assertGreaterEqual(len(trimmed), round((WINDOW_S + EXCLUDE_TAIL_S) * 10) - 1)

    def test_empty_history(self):
        self.assertEqual(trim_history([]), [])


class TestDerivePathAtTenHertz(unittest.TestCase):
    """End-to-end through derive_flights: ISO timestamps at 0.1 s spacing."""

    @staticmethod
    def _pkt(t, st, alt, seq):
        assert t < 60, "single-minute fixture"
        iso = f"2026-07-08T00:00:{t:06.3f}Z"
        return {"type": "packet", "received_at": iso, "rssi": -60, "src": 1,
                "seq": seq,
                "fields": {"SYS": 7, "SRC": 1, "SEQ": seq, "St": st, "ALT": alt}}

    def _derive(self, pad_alt_fn, rate_hz, pad_s=20):
        from ground.flights.derive import derive_flights
        dt = 1.0 / rate_hz
        n = round(pad_s * rate_hz)
        recs = [self._pkt(i * dt, 0, pad_alt_fn(i * dt), i) for i in range(n)]
        recs.append(self._pkt(pad_s, 1, 100, n))            # boost
        flights = derive_flights(recs, silence_timeout_s=90)
        self.assertEqual(len(flights), 1)
        return flights[0]

    def test_quiet_pad_baseline_identical_at_both_rates(self):
        f1 = self._derive(_quiet, 1)
        f10 = self._derive(_quiet, 10)
        self.assertEqual(f1.stats["baseline_ft"], -84)
        self.assertEqual(f10.stats["baseline_ft"], -84)

    def test_10hz_derive_does_not_lock_on_a_briefly_quiet_tail(self):
        def alt(t):
            return -84 + (10 if int(t * 2) % 2 else -10) if t < 17.0 else -84
        f = self._derive(alt, 10)
        self.assertIsNone(f.stats["baseline_ft"])
        self.assertEqual(f.stats["baseline_n"], 0)


class TestDashboardModelAtTenHertz(unittest.TestCase):
    """The live surface uses obs.mono as its clock — same property end to end."""

    @staticmethod
    def _obs(mono, st, alt, seq):
        from ground.ingest.core import Observation
        from ground.decode.v1 import decode
        pkt = f"V:1 SYS:7 SRC:1 SEQ:{seq} St:{st} ALT:{alt}ft Max:0ft"
        return Observation(f"t{seq}", -60, decode(pkt.encode()), mono)

    def test_10hz_pad_locks_a_15s_baseline_at_flight_open(self):
        from ground.dashboard.model import LiveState
        s = LiveState()
        for i in range(200):                        # 20 s of quiet pad at 10 Hz
            s.update(self._obs(i * 0.1, 0, -84, i))
        s.update(self._obs(20.0, 1, 500, 200))      # boost -> lock
        self.assertEqual(s.snapshot()[1]["locked_baseline"], -84)

    def test_10hz_briefly_quiet_tail_does_not_lock(self):
        from ground.dashboard.model import LiveState
        s = LiveState()
        for i in range(200):                        # motion until t=17 s, quiet after
            t = i * 0.1
            alt = (-84 + (10 if int(t * 2) % 2 else -10)) if t < 17.0 else -84
            s.update(self._obs(t, 0, alt, i))
        s.update(self._obs(20.0, 1, 500, 200))
        self.assertIsNone(s.snapshot()[1]["locked_baseline"])


if __name__ == "__main__":
    unittest.main()
