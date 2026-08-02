"""Host tests for the pure OLED render (panel dict -> display lines)."""
import unittest

from ground.oled.render import oled_lines
from ground.oled.spec import frame_spec, FrameSpec, LIVENESS_GLYPHS
from ground.oled.draw import render, spec_lines, WIDTH, HEIGHT


class TestOledRender(unittest.TestCase):
    def test_in_flight_panel(self):
        panel = {"src": 1, "callsign": "KC3ZTQ", "altitude_ft": 500, "peak_ft": 500,
                 "state": "ascent", "rssi": -60, "seq_loss_pct": 0.0,
                 "flight_id": "2026-07-08-F1", "flight_open": True}
        lines = oled_lines(panel)
        self.assertEqual(len(lines), 4)
        self.assertIn("SRC:1", lines[0])
        self.assertIn("KC3ZTQ", lines[0])
        self.assertIn("500", lines[1])
        self.assertIn("ASCENT", lines[2])
        self.assertIn("F1", lines[2])          # short flight tag
        self.assertIn("-60", lines[3])

    def test_idle_panel_no_callsign(self):
        panel = {"src": 2, "callsign": None, "altitude_ft": 0, "peak_ft": 0,
                 "state": "pad", "rssi": -70, "seq_loss_pct": 0.0,
                 "flight_id": None, "flight_open": False}
        lines = oled_lines(panel)
        self.assertEqual(lines[0], "SRC:2")    # no trailing callsign
        self.assertIn("PAD", lines[2])
        self.assertIn("idle", lines[2])

    def test_missing_values_show_placeholder(self):
        lines = oled_lines({"src": 1, "altitude_ft": None, "peak_ft": None})
        self.assertIn("--", lines[1])
        self.assertEqual(len(lines), 4)


def _panel(src=1, **over):
    p = {"src": src, "callsign": None, "altitude_ft": 100, "peak_ft": 120,
         "state": "pad", "rssi": -60, "seq_loss_pct": 0.0,
         "flight_id": None, "flight_open": False}
    p.update(over)
    return p


def _blob(spec):
    """All human-readable text in a frame, lowercased — assert on MEANING, not layout."""
    return " ".join(spec.texts()).lower()


class TestFrameSpec(unittest.TestCase):
    """frame_spec() is the PURE layer: what is on screen, not how it is drawn. These tests
    are written against meaning so they survive the layout redesign that replaces the
    drawing layer wholesale. `tick` is injected — no clock read, no hardware."""

    # --- idle page: a quiet pad must show real content, never an empty screen ---

    def test_idle_page_when_no_panels(self):
        # The 2026-07-30 bench defect: with no sled transmitting the display sat at luma's
        # cleared-black init state and read as BROKEN. A quiet pad is normal; say so.
        spec = frame_spec({"panels": []}, clock="rtc", tick=0)
        self.assertEqual(spec.page, "idle")
        blob = _blob(spec)
        self.assertIn("ready", blob)
        self.assertIn("src:1", blob)        # what it is waiting for
        self.assertIn("rssi", blob)
        self.assertIn("--", blob)           # no-signal placeholder

    def test_idle_page_when_view_is_none(self):
        # Fail-safe: no snapshot published yet (startup) must still render, not crash.
        spec = frame_spec(None, clock="unknown", tick=0)
        self.assertEqual(spec.page, "idle")
        self.assertIn("ready", _blob(spec))

    def test_idle_page_shows_clock_provenance(self):
        for prov in ("rtc", "attested", "unknown"):
            spec = frame_spec({"panels": []}, clock=prov, tick=0)
            self.assertEqual(spec.clock, prov)
            self.assertIn(prov, _blob(spec), f"clock={prov} not visible on screen")

    # --- liveness: a frozen render thread must be VISIBLE, not plausible ---

    def test_liveness_glyph_advances_with_tick(self):
        # Same self-detecting principle as G_ALIVE never being SOLID: if the render thread
        # wedges, the last frame must not look like a healthy one.
        glyphs = {frame_spec({"panels": []}, clock="rtc", tick=t).liveness_glyph
                  for t in range(len(LIVENESS_GLYPHS))}
        self.assertEqual(len(glyphs), len(LIVENESS_GLYPHS),
                         "liveness glyph repeats within one cycle — a wedged render "
                         "thread would be indistinguishable from a healthy one")

    def test_liveness_glyph_also_advances_on_the_live_page(self):
        glyphs = {frame_spec({"panels": [_panel()]}, clock="rtc", tick=t).liveness_glyph
                  for t in range(len(LIVENESS_GLYPHS))}
        self.assertEqual(len(glyphs), len(LIVENESS_GLYPHS))

    # --- live page ---

    def test_live_page_carries_state_and_hero(self):
        spec = frame_spec({"panels": [_panel(state="ascent", altitude_ft=500)]},
                          clock="rtc", tick=0)
        self.assertEqual(spec.page, "live")
        self.assertEqual(spec.state, "ASCENT")
        self.assertEqual(spec.hero, "500")          # the dominant number, for the 28px hero
        self.assertEqual(spec.hero_unit, "ft")

    def test_live_page_hero_placeholder_when_altitude_unknown(self):
        spec = frame_spec({"panels": [_panel(altitude_ft=None)]}, clock="rtc", tick=0)
        self.assertEqual(spec.hero, "--")

    # --- panel choice: FORCED by moving render off the RX thread (no observed SRC) ---

    def test_prefers_the_panel_with_an_open_flight(self):
        quiet = _panel(src=1, state="pad")
        flying = _panel(src=2, state="ascent", flight_open=True, flight_id="2026-08-02-F2")
        self.assertIn("src:2", _blob(frame_spec({"panels": [quiet, flying]}, tick=0)))

    def test_falls_back_to_lowest_src_when_no_flight_open(self):
        spec = frame_spec({"panels": [_panel(src=3), _panel(src=1)]}, tick=0)
        self.assertIn("src:1", _blob(spec))

    def test_spec_is_immutable(self):
        # The RX thread publishes it and the render thread consumes it — it must not be
        # mutable shared state across that boundary.
        spec = frame_spec({"panels": []}, tick=0)
        with self.assertRaises(Exception):
            spec.page = "live"          # type: ignore[misc]


class TestDrawLayer(unittest.TestCase):
    """The drawing layer is deliberately trivial and expected to be REPLACED by the
    redesign. Asserted on structure only — NO golden images in this branch, because the
    default PIL font is not guaranteed identical on Mac and Pi, which is exactly the
    divergence that forced the commit-a-font decision."""

    def test_render_produces_a_128x64_1bit_image(self):
        img = render(frame_spec({"panels": []}, clock="rtc", tick=0))
        self.assertEqual(img.size, (WIDTH, HEIGHT))
        self.assertEqual(img.mode, "1")

    def test_rendered_frames_fit_the_display(self):
        for view in (None, {"panels": []}, {"panels": [_panel()]}):
            for tick in range(8):
                lines = spec_lines(frame_spec(view, clock="rtc", tick=tick))
                self.assertLessEqual(len(lines), 4, "more than 4 lines will not fit")
                for line in lines:
                    self.assertLessEqual(len(line), 21, f"line too wide: {line!r}")

    def test_idle_and_live_frames_differ_on_screen(self):
        idle = render(frame_spec({"panels": []}, clock="rtc", tick=0))
        live = render(frame_spec({"panels": [_panel(altitude_ft=500)]}, clock="rtc", tick=0))
        self.assertNotEqual(idle.tobytes(), live.tobytes())


if __name__ == "__main__":
    unittest.main()
