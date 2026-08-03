"""RED-phase tests for the three-page LAYOUT (ground.oled.draw).

These assert GEOMETRY and STRUCTURE — band occupancy, centring, inversion — never exact
pixels. Golden images pin exact pixels separately; if a test in this file breaks when a
glyph is redrawn, it was written wrong.

The load-bearing test here is `test_layout_survives_a_narrower_glyph_set`. It swaps in a
deliberately narrower hero font and asserts the layout still centres. That makes "the layout
does not bake in glyph metrics" PROVABLE rather than promised — which matters because the
4 px stroke was approved on operator judgement, not a measured distance, so a later redraw
at 3 px is a live possibility. If that day comes, only the glyphs and the goldens change.
"""
import unittest
from unittest import mock

from ground.oled.spec import frame_spec
from ground.oled.draw import (
    render, small_ink_rows, WIDTH, HEIGHT, HEADER_Y, HEADER_H,
    BAND_Y, BAND_H, HERO_Y, HERO_H, TREND_Y, TREND_H,
)


def _panel(src=1, **over):
    p = {"src": src, "callsign": "KC3ZTQ", "altitude_ft": 1834, "peak_ft": 1834,
         "state": "ascent", "rssi": -72, "seq_loss_pct": 1.3,
         "flight_id": "2026-08-02-F2", "flight_open": True}
    p.update(over)
    return p


def _rows_lit(img):
    """{row_index: count_of_lit_pixels} — structure without asserting exact pixels."""
    px = img.load()
    return {y: sum(1 for x in range(WIDTH) if px[x, y]) for y in range(HEIGHT)}


def _band_rows(lit, y0, h):
    return [lit[y] for y in range(y0, y0 + h)]


def _lit_x_range(img, y0, h):
    """Leftmost and rightmost lit column within a band — for centring assertions.

    Raises if the band is EMPTY rather than returning None: every caller is asserting
    something about where pixels are, so "there are none" is a failure in all of them, and
    an Optional return would only push that discovery into a confusing downstream error.
    """
    px = img.load()
    xs = [x for y in range(y0, y0 + h) for x in range(WIDTH) if px[x, y]]
    assert xs, f"band at y={y0} h={h} is empty — nothing was drawn"
    return min(xs), max(xs)


class TestCanvas(unittest.TestCase):
    def test_render_is_a_128x64_1bit_image(self):
        img = render(frame_spec(None, tick=0))
        self.assertEqual(img.size, (WIDTH, HEIGHT))
        self.assertEqual(img.mode, "1")

    def test_bands_fit_the_panel_and_do_not_overlap(self):
        bands = sorted([(HEADER_Y, 8), (BAND_Y, BAND_H), (HERO_Y, HERO_H), (TREND_Y, TREND_H)])
        for (y0, h), (y1, _) in zip(bands, bands[1:]):
            self.assertLessEqual(y0 + h, y1, f"band at {y0} (h={h}) overlaps the one at {y1}")
        last_y, last_h = bands[-1]
        self.assertLessEqual(last_y + last_h, HEIGHT, "bands overflow the panel")


class TestHeroBand(unittest.TestCase):
    """Closure-bar question 2: how high. The hero owns 28 px and must be centred."""

    def test_hero_pixels_land_in_the_hero_band(self):
        img = render(frame_spec({"panels": [_panel()]}, tick=0))
        lit = _rows_lit(img)
        self.assertGreater(sum(_band_rows(lit, HERO_Y, HERO_H)), 0, "hero band is empty")

    def test_hero_is_horizontally_centred(self):
        img = render(frame_spec({"panels": [_panel(altitude_ft=1834)]}, tick=0))
        lo, hi = _lit_x_range(img, HERO_Y, HERO_H)
        left, right = lo, WIDTH - 1 - hi
        self.assertLessEqual(abs(left - right), 2, f"hero off-centre: {left} vs {right}")

    def test_overflow_hero_still_fits_the_panel(self):
        img = render(frame_spec({"panels": [_panel(altitude_ft=10234)]}, tick=0))
        lo, hi = _lit_x_range(img, HERO_Y, HERO_H)
        self.assertGreaterEqual(lo, 0)
        self.assertLess(hi, WIDTH)

    def test_negative_hero_still_fits(self):
        img = render(frame_spec({"panels": [_panel(altitude_ft=-84)]}, tick=0))
        lo, hi = _lit_x_range(img, HERO_Y, HERO_H)
        self.assertLess(hi, WIDTH)


class TestTextInkFitsItsBand(unittest.TestCase):
    """A band's NOMINAL cell is not where its pixels are.

    `test_bands_fit_the_panel_and_do_not_overlap` passes on arithmetic — the bands genuinely
    do not overlap — while the inverted state band was still painting over the bottom rows of
    the header text, because PIL's default font carries a ~2 px top bearing and descenders
    push ink up to 4 rows past the nominal cell. `apogee-gs` lost THREE rows; `SRC:1 KC3ZTQ`
    lost one, and that string is the Part-97 station ID, the one piece of text on this panel
    with a regulatory reason to be legible.

    Same shape as the hero-centring test, one band up: assert where the INK lands, never
    where the layout says it should. An arithmetic test cannot catch a rendering fact.
    """

    def test_header_text_ink_is_fully_inside_the_header_band(self):
        for text in ("SRC:1 KC3ZTQ",          # Part-97 station ID — must not clip
                     "apogee-gs -",           # descenders in p and g
                     "-72dBm", "--", "SRC:12 KC3ZTQ-11"):
            lo, hi = small_ink_rows(text, 0, HEADER_Y)
            self.assertGreaterEqual(lo, HEADER_Y, f"{text!r} ink starts above the header")
            self.assertLess(hi, BAND_Y,
                            f"{text!r} ink reaches row {hi}; the state band paints from "
                            f"{BAND_Y} and would clip it")

    def test_header_ink_survives_the_burn_in_shift(self):
        # The 1 px shift must not push ink into the band either.
        for text in ("SRC:1 KC3ZTQ", "apogee-gs -"):
            lo, hi = small_ink_rows(text, 0, HEADER_Y + 1)
            self.assertLess(hi, BAND_Y, f"{text!r} clips once shifted by burn-in")


class TestStateBand(unittest.TestCase):
    """Closure-bar question 1: is it capturing. The band is INVERTED so state reads first."""

    def test_state_band_is_inverted(self):
        # Inverted = mostly-lit background with dark glyphs, so the band's lit count must be
        # far higher than a normal text row's.
        img = render(frame_spec({"panels": [_panel()]}, tick=0))
        lit = _rows_lit(img)
        band = _band_rows(lit, BAND_Y, BAND_H)
        self.assertGreater(min(band), WIDTH // 2,
                           "state band is not inverted — every row should be mostly lit")

    def test_hero_band_is_not_inverted(self):
        # Only the band inverts; a second inverted region would compete with it.
        img = render(frame_spec({"panels": [_panel()]}, tick=0))
        lit = _rows_lit(img)
        self.assertLess(max(_band_rows(lit, HERO_Y, HERO_H)), WIDTH // 2)


class TestPagesDiffer(unittest.TestCase):
    def test_idle_live_and_summary_are_visually_distinct(self):
        idle = render(frame_spec(None, tick=0)).tobytes()
        live = render(frame_spec({"panels": [_panel()]}, tick=0)).tobytes()
        summ = render(frame_spec({"panels": [_panel(flight_open=False)]},
                                 last_flight={"flight_id": "2026-08-02-F2", "peak_ft": 1834},
                                 tick=0)).tobytes()
        self.assertNotEqual(idle, live)
        self.assertNotEqual(live, summ)
        self.assertNotEqual(idle, summ)


class TestBurnIn(unittest.TestCase):
    """Mitigate, NEVER blank — a blanking screensaver would rebuild the dark-looks-broken
    ambiguity this whole epic removed."""

    def test_frame_shifts_over_time(self):
        a = render(frame_spec({"panels": [_panel()]}, tick=0)).tobytes()
        b = render(frame_spec({"panels": [_panel()]}, tick=10_000)).tobytes()
        self.assertNotEqual(a, b, "no burn-in shift across a long interval")

    def test_frame_is_never_blank(self):
        for tick in (0, 1, 37, 600, 10_000):
            for view in (None, {"panels": [_panel()]}):
                img = render(frame_spec(view, tick=tick))
                self.assertGreater(sum(_rows_lit(img).values()), 0,
                                   f"blank frame at tick={tick} — never blank, ever")


class TestMetricsAreNotBakedIn(unittest.TestCase):
    """THE falsifiable test for the two-layer split.

    Stroke weight was approved on operator JUDGEMENT, not a measured distance, so a redraw at
    3 px remains live. If the layout hardcoded any horizontal metric, that redraw would
    silently mis-centre the hero. Swapping in a narrower glyph set must simply re-centre.
    """

    def test_layout_survives_a_narrower_glyph_set(self):
        from ground.oled import glyphs as G
        narrow = {ch: [row[:len(row) // 2] for row in rows] for ch, rows in G.GLYPHS.items()}
        spec = frame_spec({"panels": [_panel(altitude_ft=1834)]}, tick=0)

        wide_lo, wide_hi = _lit_x_range(render(spec), HERO_Y, HERO_H)
        with mock.patch.object(G, "GLYPHS", narrow):
            img = render(spec)
        thin_lo, thin_hi = _lit_x_range(img, HERO_Y, HERO_H)
        self.assertLess(thin_hi - thin_lo, wide_hi - wide_lo, "narrow set was not narrower")
        left, right = thin_lo, WIDTH - 1 - thin_hi
        self.assertLessEqual(abs(left - right), 2,
                             "hero did not re-centre — a horizontal metric is hardcoded")


if __name__ == "__main__":
    unittest.main()
