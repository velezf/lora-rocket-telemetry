"""RED-phase tests for the OLED layout redesign — the PURE layer only.

Every test here is written against MEANING, never geometry: the drawing layer owns pixels
and is asserted separately by golden images. That split is the point — if a test in this
file has to change when the hero font changes, it was written wrong.

Scope is the closure bar's four questions and nothing else:
  1 capturing · 2 how high · 3 is this number current · 4 is the link healthy
"""
import unittest

from ground.oled.spec import (
    FrameSpec, frame_spec, format_hero, trend_window, is_stale, STALE_S,
    TREND_WINDOW_S, LIVENESS_GLYPHS,
)


def _panel(src=1, **over):
    p = {"src": src, "callsign": "KC3ZTQ", "altitude_ft": 100, "peak_ft": 120,
         "state": "pad", "rssi": -60, "seq_loss_pct": 0.0,
         "flight_id": None, "flight_open": False}
    p.update(over)
    return p


def _view(panels=(), **over):
    v = {"panels": list(panels)}
    v.update(over)
    return v


# --- QUESTION 2: how high — hero overflow policy lives in the PURE layer ---

class TestHeroOverflow(unittest.TestCase):
    """A 28px hero fits ~4 glyphs. Shrinking the font breaks 'readable at arm's length'
    exactly when altitude matters most, and clipping is a lie — so >=10k switches units."""

    def test_plain_digits_up_to_four(self):
        self.assertEqual(format_hero(0), "0")
        self.assertEqual(format_hero(842), "842")
        self.assertEqual(format_hero(9999), "9999")

    def test_five_digits_switch_to_k(self):
        self.assertEqual(format_hero(10000), "10.0k")
        self.assertEqual(format_hero(10234), "10.2k")

    def test_hero_never_exceeds_five_glyphs(self):
        for v in (0, 999, 9999, 10000, 12345, 99999, 123456):
            self.assertLessEqual(len(format_hero(v)), 5, f"{v} overflows the hero")

    def test_negative_agl_is_representable(self):
        # AGL goes negative below the pad baseline — F1's raw baseline was -84 ft.
        self.assertEqual(format_hero(-84), "-84")

    def test_missing_altitude_is_a_placeholder_not_a_zero(self):
        # Showing 0 for "no data" would be a lying display.
        self.assertEqual(format_hero(None), "--")

    def test_glyph_set_is_bounded(self):
        # The hero font is HAND-DRAWN, so the alphabet must stay small and known.
        used = set()
        for v in (None, -84, 0, 9999, 10234, 99999):
            used |= set(format_hero(v))
        self.assertTrue(used <= set("0123456789.k-"), f"unexpected hero glyphs: {used}")


# --- QUESTION 3: is this number current — freshness rides the STATE BAND ---

class TestFreshness(unittest.TestCase):
    """A frozen hero is visually identical to a live one — the same lying-display class
    removed from the LED panel. Threshold is STATE-DEPENDENT: a silent pad is normal, a
    silent ascent is not."""

    def test_silence_on_the_pad_is_not_stale(self):
        self.assertFalse(is_stale("pad", age_s=30.0))
        self.assertFalse(is_stale("idle", age_s=120.0))

    def test_silence_during_ascent_is_stale(self):
        self.assertTrue(is_stale("ascent", age_s=STALE_S + 0.1))
        self.assertTrue(is_stale("descent", age_s=STALE_S + 0.1))

    def test_fresh_ascent_is_not_stale(self):
        self.assertFalse(is_stale("ascent", age_s=0.5))

    def test_unknown_age_is_not_an_alarm(self):
        # No last_rx_ts yet (startup) must not scream; absence of data != stale data.
        self.assertFalse(is_stale("ascent", age_s=None))

    def test_stale_flight_surfaces_on_the_spec(self):
        spec = frame_spec(_view([_panel(state="ascent", flight_open=True)]),
                          rx_age_s=10.0, tick=0)
        self.assertTrue(spec.stale)
        self.assertEqual(spec.age_s, 10.0)

    def test_stale_does_not_blank_the_hero(self):
        # Question 2 must survive question 3: the number stays readable while stale.
        spec = frame_spec(_view([_panel(state="ascent", flight_open=True, altitude_ft=1500)]),
                          rx_age_s=10.0, tick=0)
        self.assertTrue(spec.stale)
        self.assertEqual(spec.hero, "1500")


# --- QUESTION 4: link health ---

class TestLinkHealth(unittest.TestCase):
    def test_live_page_carries_rssi_and_loss(self):
        spec = frame_spec(_view([_panel(rssi=-72, seq_loss_pct=3.5)]), tick=0)
        self.assertEqual(spec.rssi, -72)
        self.assertEqual(spec.loss_pct, 3.5)

    def test_missing_rssi_is_none_not_zero(self):
        spec = frame_spec(_view([_panel(rssi=None)]), tick=0)
        self.assertIsNone(spec.rssi)


# --- QUESTION 1: capturing — three pages, chosen by FLIGHT STATE not a timer ---

class TestPageSelection(unittest.TestCase):
    def test_idle_when_no_panels(self):
        self.assertEqual(frame_spec(None, tick=0).page, "idle")
        self.assertEqual(frame_spec(_view(), tick=0).page, "idle")

    def test_live_when_a_flight_is_open(self):
        spec = frame_spec(_view([_panel(flight_open=True, state="ascent")]), tick=0)
        self.assertEqual(spec.page, "live")

    def test_summary_after_flight_close(self):
        spec = frame_spec(_view([_panel(flight_open=False, state="landed")]),
                          last_flight={"flight_id": "2026-08-02-F2", "peak_ft": 1834}, tick=0)
        self.assertEqual(spec.page, "summary")

    def test_summary_hero_is_the_PEAK_not_the_live_altitude(self):
        # SUMMARY is what the operator reads walking downrange; peak is the number they went
        # to fetch.
        spec = frame_spec(_view([_panel(flight_open=False, altitude_ft=3)]),
                          last_flight={"flight_id": "2026-08-02-F2", "peak_ft": 1834}, tick=0)
        self.assertEqual(spec.hero, "1834")

    def test_summary_holds_until_a_new_flight_opens_not_on_a_timer(self):
        # A timeout would blank the one number the operator walked downrange to read.
        last = {"flight_id": "2026-08-02-F2", "peak_ft": 1834}
        for tick in (0, 100, 100000):
            self.assertEqual(frame_spec(_view([_panel()]), last_flight=last, tick=tick).page,
                             "summary")
        reopened = frame_spec(_view([_panel(flight_open=True, state="ascent")]),
                              last_flight=last, tick=0)
        self.assertEqual(reopened.page, "live")

    def test_page_is_recoverable_after_a_restart_mid_flight(self):
        # Derived from flight state, never from in-memory flags: a restart during a flight
        # must return to LIVE, not drop the operator back to IDLE.
        spec = frame_spec(_view([_panel(flight_open=True, state="ascent")]),
                          last_flight=None, tick=0)
        self.assertEqual(spec.page, "live")


# --- surface split: the OLED must not be the authoritative reporter of system health ---

class TestSurfaceSplit(unittest.TestCase):
    """The LED panel is SUPERVISOR-owned and survives the failures it reports; the OLED
    render thread lives inside apogee-ingest and freezes with plausible content when that
    process dies. So the OLED carries "what is the flight doing", and anything answering
    "is the system working" is the LEDs' job — the OLED cannot report its own death."""

    def test_clock_provenance_appears_on_idle(self):
        # Pre-launch check, space is free, and the operator is standing at the box where
        # B_CLOCK can be cross-checked directly.
        spec = frame_spec(_view(), clock="rtc", tick=0)
        self.assertIn("rtc", " ".join(spec.texts()).lower())

    def test_clock_provenance_is_ABSENT_from_the_live_page(self):
        # Worse than redundant: a frozen "CLK rtc" mid-flight is a trust claim made by the
        # one surface that can freeze showing plausible content. B_CLOCK owns it, and
        # survives an ingest death that the OLED cannot report.
        spec = frame_spec(_view([_panel(flight_open=True, state="ascent")]),
                          clock="rtc", tick=0)
        self.assertNotIn("clk", " ".join(spec.texts()).lower())
        self.assertNotIn("rtc", " ".join(spec.texts()).lower())

    def test_clock_provenance_is_ABSENT_from_the_summary_page(self):
        spec = frame_spec(_view([_panel()]), clock="rtc",
                          last_flight={"flight_id": "2026-08-02-F2", "peak_ft": 1834}, tick=0)
        self.assertNotIn("clk", " ".join(spec.texts()).lower())

    def test_liveness_glyph_is_present_on_every_page(self):
        # The one system-health signal the OLED is uniquely qualified to carry: it reports
        # the RENDER THREAD's aliveness, a different failure domain from G_ALIVE (the RX
        # loop). No LED can report it.
        pages = (
            frame_spec(_view(), tick=0),
            frame_spec(_view([_panel(flight_open=True, state="ascent")]), tick=0),
            frame_spec(_view([_panel()]), last_flight={"flight_id": "F2", "peak_ft": 10}, tick=0),
        )
        for spec in pages:
            self.assertIn(spec.liveness_glyph, LIVENESS_GLYPHS)


# --- trend strip: TIME-based window, and the sacrificial element ---

class TestTrendWindow(unittest.TestCase):
    """Sample-based windows silently stretch under packet loss — 60 samples could be four
    minutes on a bad link, and the strip would misrepresent its own timespan."""

    def test_window_is_time_based_and_drops_old_samples(self):
        samples = [(t, float(t)) for t in range(0, 300, 10)]     # (age_s, agl_ft)
        kept = trend_window(samples, now_s=300.0, window_s=TREND_WINDOW_S)
        self.assertTrue(all(300.0 - t <= TREND_WINDOW_S for t, _ in kept))

    def test_packet_loss_does_not_stretch_the_window(self):
        sparse = [(0.0, 0.0), (250.0, 500.0), (299.0, 900.0)]    # a long gap
        kept = trend_window(sparse, now_s=300.0, window_s=TREND_WINDOW_S)
        self.assertNotIn((0.0, 0.0), kept, "a stale sample survived a time-based window")

    def test_empty_history_is_safe(self):
        self.assertEqual(trend_window([], now_s=10.0, window_s=TREND_WINDOW_S), ())


# --- the spec is still a SPEC: pure, immutable, and drawing-agnostic ---

class TestSpecContract(unittest.TestCase):
    def test_spec_is_frozen(self):
        # It crosses the RX -> render thread boundary; it must not be mutable shared state.
        spec = frame_spec(None, tick=0)
        with self.assertRaises(Exception):
            spec.page = "live"      # type: ignore[misc]

    def test_tick_is_the_monotonic_clock_both_layers_derive_from(self):
        # Renamed from `liveness`: the draw layer needs a clock for the burn-in shift, and
        # deriving a 30s phase from a field named "liveness" is exactly the implicit
        # coupling this split exists to prevent.
        self.assertEqual(frame_spec(None, tick=7).tick, 7)

    def test_liveness_glyph_still_advances_and_uses_every_phase(self):
        glyphs = {frame_spec(None, tick=t).liveness_glyph for t in range(len(LIVENESS_GLYPHS))}
        self.assertEqual(len(glyphs), len(LIVENESS_GLYPHS))

    def test_spec_carries_no_geometry(self):
        # No pixel/font/offset fields may leak into the pure layer.
        banned = ("x", "y", "px", "font", "width", "height", "offset", "shift", "invert")
        for name in FrameSpec.__dataclass_fields__:
            self.assertNotIn(name.lower(), banned, f"geometry leaked into the spec: {name}")


if __name__ == "__main__":
    unittest.main()
