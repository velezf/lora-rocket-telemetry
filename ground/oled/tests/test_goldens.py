"""Golden-image tests — exact pixels for each page and each hero form.

WHY GOLDENS ARE SAFE HERE, AND WHAT THEY DO NOT PROVE.

A golden preserves whatever it was generated from, INCLUDING A MISTAKE. No test can say
"this is the wrong picture" — only a human looking at the real medium can. So every golden
in this directory was generated only AFTER the corresponding frame was displayed on the
actual SSD1306 and approved by eye (2026-08-03). Two defects were caught that way and would
otherwise have been frozen here forever: the hero receiving "1834ft" (the bounded alphabet
raised rather than drawing a plausible wrong picture), and the inverted state band clipping
the bottom row of the header text — including the Part-97 callsign.

REGENERATION IS NOT A FIX. If one of these fails, the question is "did the picture change
for a reason someone decided?" — not "how do I make the test pass". Regenerate only with an
explicit named reason, the same rule the F1 flight golden carries.

DETERMINISM. The hero digits are hand-drawn bitmaps in ground/oled/glyphs.py, so they are
identical everywhere. The small text still uses PIL's DEFAULT bitmap font, which ships inside
Pillow — deterministic for a given Pillow version (Mac and Pi are both on 12.3.0 today) but
NOT pinned. Committing a pixel TTF to ground/oled/fonts/ remains open; until then a Pillow
upgrade can legitimately break these, and that is a version change, not a regression.
"""
import unittest
from pathlib import Path

from ground.oled.spec import frame_spec
from ground.oled.draw import render

_GOLDENS = Path(__file__).parent / "goldens"


def _panel(**over):
    p = {"src": 1, "callsign": "KC3ZTQ", "altitude_ft": 1834, "peak_ft": 1834,
         "state": "ascent", "rssi": -72, "seq_loss_pct": 1.3,
         "flight_id": "2026-08-02-F2", "flight_open": True}
    p.update(over)
    return p


def _cases():
    live = _panel()
    done = _panel(state="landed", flight_open=False, altitude_ft=3)
    last = {"flight_id": "2026-08-02-F2", "peak_ft": 1834}
    return {
        "pad":      frame_spec(None, clock="rtc", tick=0),
        "live":     frame_spec({"panels": [live]}, clock="rtc", tick=0),
        "summary":  frame_spec({"panels": [done]}, clock="rtc", last_flight=last, tick=0),
        "stale":    frame_spec({"panels": [live]}, clock="rtc", rx_age_s=4.2, tick=0),
        "overflow": frame_spec({"panels": [_panel(altitude_ft=10234)]}, clock="rtc", tick=0),
        "negative": frame_spec({"panels": [_panel(altitude_ft=-84)]}, clock="rtc", tick=0),
    }


class TestGoldens(unittest.TestCase):
    def test_every_page_matches_its_golden(self):
        from PIL import Image   # pyright: ignore[reportMissingImports]
        for name, spec in _cases().items():
            with self.subTest(page=name):
                path = _GOLDENS / f"{name}.png"
                self.assertTrue(path.exists(), f"missing golden {path}")
                expected = Image.open(path).convert("1")
                self.assertEqual(render(spec).tobytes(), expected.tobytes(),
                                 f"{name} differs from its golden — regenerate ONLY with an "
                                 f"explicit named reason, never to make the test pass")

    def test_the_golden_set_covers_every_page_and_every_hero_form(self):
        # A golden suite that silently loses a case is worse than none: it reports green
        # while covering less. Pin the roster itself.
        self.assertEqual(sorted(p.stem for p in _GOLDENS.glob("*.png")),
                         sorted(_cases()))
        pages = {s.page for s in _cases().values()}
        self.assertEqual(pages, {"idle", "live", "summary"})
        heroes = {s.hero for s in _cases().values()}
        self.assertTrue({"--", "1834", "10.2k", "-84"} <= heroes,
                        f"hero forms not all covered: {heroes}")

    def test_the_stale_golden_really_is_stale(self):
        # Guard against the stale case silently degenerating into a duplicate of `live`.
        c = _cases()
        self.assertTrue(c["stale"].stale)
        self.assertFalse(c["live"].stale)
        self.assertNotEqual(render(c["stale"]).tobytes(), render(c["live"]).tobytes())


if __name__ == "__main__":
    unittest.main()
