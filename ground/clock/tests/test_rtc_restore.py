"""Host tests for the pure RTC-boot-restore logic (feat/rtc-boot-restore).

The Pi 5's rtc0 comes up at 1970 (no coin cell) and systemd-timesyncd then restores
its saved-clock FLOOR (= last shutdown); nothing reads the PiSugar RTC into the system
clock, so apogee-ingest's year>=2024 gate opened a mis-dated session (2026-07-13 boot).
These pure functions decide whether to set the clock from the PiSugar RTC at boot, and
harden the trust gate so a plausible-year floor ALONE no longer satisfies it. Read
mechanism (pisugar-server API) is a thin Pi-only shell, not tested here.
"""
import unittest
from datetime import datetime, timezone

from ground.clock.rtc_restore import (
    parse_rtc, extract_rtc_time, is_valid, decide, audit_event, clock_trustworthy,
)

UTC = timezone.utc


def dt(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


class TestParse(unittest.TestCase):
    def test_iso_with_offset(self):
        # pisugar-server returns ISO-8601 with a tz offset
        self.assertEqual(parse_rtc("2026-07-13T15:58:33.000-04:00"),
                         dt(2026, 7, 13, 19, 58, 33))          # same instant as 19:58:33Z

    def test_malformed_is_none(self):
        self.assertIsNone(parse_rtc("not-a-date"))

    def test_empty_is_none(self):
        self.assertIsNone(parse_rtc(""))


class TestExtractRtcTime(unittest.TestCase):
    def test_extracts_iso_from_reply(self):
        self.assertEqual(extract_rtc_time("rtc_time: 2026-07-13T15:58:33.000-04:00"),
                         "2026-07-13T15:58:33.000-04:00")

    def test_absent_line_is_none(self):
        self.assertIsNone(extract_rtc_time("Invalid request."))

    def test_empty_is_none(self):
        self.assertIsNone(extract_rtc_time(""))

    def test_round_trips_into_parse_rtc(self):
        iso = extract_rtc_time("model: PiSugar 3\nrtc_time: 2026-07-13T15:58:33.000-04:00\n")
        self.assertEqual(parse_rtc(iso), dt(2026, 7, 13, 19, 58, 33))


class TestValid(unittest.TestCase):
    def test_rejects_epoch_1970(self):
        self.assertFalse(is_valid(dt(1970, 1, 1, 0, 0, 13)))

    def test_rejects_far_future(self):
        self.assertFalse(is_valid(dt(2101, 1, 1)))

    def test_accepts_current(self):
        self.assertTrue(is_valid(dt(2026, 7, 13)))

    def test_none_is_invalid(self):
        self.assertFalse(is_valid(None))


class TestDecide(unittest.TestCase):
    def test_sets_when_sys_clock_bogus(self):
        action, _ = decide(dt(2026, 7, 13, 20), dt(1970, 1, 1, 0, 0, 13))
        self.assertEqual(action, "set")

    def test_sets_when_sys_behind_rtc_floor_case(self):
        # the observed bug: sys sits on the Jul-08 floor, PiSugar RTC has the real Jul-13
        action, reason = decide(dt(2026, 7, 13, 19, 40), dt(2026, 7, 8, 21, 51))
        self.assertEqual(action, "set")
        self.assertIn("behind", reason)

    def test_leaves_when_already_current(self):
        action, _ = decide(dt(2026, 7, 13, 20, 0, 30), dt(2026, 7, 13, 20))   # +30 s < threshold
        self.assertEqual(action, "leave")

    def test_never_steps_clock_backward(self):
        # sys is NTP-correct, rtc is stale-behind (days) -> must NOT drag the clock back
        action, reason = decide(dt(2026, 7, 8, 21, 51), dt(2026, 7, 13, 19, 40))
        self.assertEqual(action, "leave")
        self.assertIn("back", reason)

    def test_attests_when_rtc_within_tolerance_behind(self):
        # RTC a few seconds BEHIND sys still CONFIRMS the clock -> clock-already-current
        # (so the marker drops; an offline brief power-cycle must not fail closed).
        action, reason = decide(dt(2026, 7, 13, 20, 0, 0), dt(2026, 7, 13, 20, 0, 5))
        self.assertEqual((action, reason), ("leave", "clock-already-current"))

    def test_leaves_when_rtc_invalid(self):
        action, _ = decide(None, dt(2026, 7, 13, 20))
        self.assertEqual(action, "leave")


class TestAuditEvent(unittest.TestCase):
    def test_payload_shape(self):
        e = audit_event(dt(2026, 7, 13, 19, 40), dt(2026, 7, 8, 21, 51),
                        "set", "sys-behind-rtc", "2026-07-13T19:40:00.000Z")
        self.assertEqual((e["type"], e["event"]), ("event", "rtc_restore"))
        self.assertEqual((e["action"], e["reason"]), ("set", "sys-behind-rtc"))
        for k in ("rtc_time", "sys_before", "received_at"):
            self.assertIn(k, e)


class TestGateHardening(unittest.TestCase):
    def test_plausible_year_floor_alone_is_untrusted(self):
        # THE observed bug, pinned: 2026 + no NTP + no restore marker -> NOT trusted
        self.assertFalse(clock_trustworthy(ntp_synced=False, rtc_restored=False, year=2026))

    def test_trusted_with_ntp(self):
        self.assertTrue(clock_trustworthy(ntp_synced=True, rtc_restored=False, year=2026))

    def test_trusted_with_rtc_restore_marker(self):
        self.assertTrue(clock_trustworthy(ntp_synced=False, rtc_restored=True, year=2026))

    def test_epoch_year_never_trusted(self):
        self.assertFalse(clock_trustworthy(ntp_synced=True, rtc_restored=True, year=1970))


if __name__ == "__main__":
    unittest.main()
