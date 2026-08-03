"""OLED drawing layer — FrameSpec -> a 128x64 1-bit PIL image.

Option A, number-dominant, four bands top to bottom:

    HEADER   8 px   identity (left) + RSSI (right)
    BAND    11 px   INVERTED state band + direction glyph
    HERO    28 px   the dominant number, hand-drawn glyphs (ground/oled/glyphs.py)
    TREND   10 px   thin strip + micro-stats   <- SACRIFICIAL: if a row is cramped,
                                                  the hero keeps its 28 px and this goes

NO HARDCODED HORIZONTAL METRICS. Every x-position is derived from `text_width()` /
`advance()` at render time, never a baked-in pixel offset. That is not tidiness: the 4 px
stroke was approved on operator JUDGEMENT rather than a measured distance, so a redraw at
3 px remains a live possibility. Because the layout derives its geometry, such a redraw
re-centres itself and costs only the glyphs and the goldens. `test_layout.py` proves this by
swapping in a deliberately narrower glyph set and asserting the hero still centres — the
claim is falsifiable, not promised.

BURN-IN: mitigate, NEVER blank. The whole frame shifts by one pixel on a slow cycle. A
blanking screensaver would rebuild the exact dark-looks-broken ambiguity this epic removed.

The small text uses PIL's default bitmap font TODAY, which is why golden images cover only
structure so far; the committed pixel TTF lands with the goldens.
"""
from ground.oled.glyphs import glyph, glyph_size, advance, text_width
from ground.oled.spec import PAGE_IDLE, PAGE_LIVE, PAGE_SUMMARY

WIDTH, HEIGHT = 128, 64

HEADER_Y, HEADER_H = 0, 8
BAND_Y, BAND_H = 9, 11
HERO_Y, HERO_H = 21, 28
TREND_Y, TREND_H = 50, 10

# Burn-in: shift the whole frame 1 px on a slow cycle. Long enough not to read as motion
# (motion is the display's alarm channel), short enough to move pixels well before damage.
_SHIFT_PERIOD_TICKS = 45          # at ~1 Hz redraw: a step roughly every 45 s
_SHIFT_STATES = ((0, 0), (1, 0), (1, 1), (0, 1))


def draw_small(d, text, x, y, fill=1):
    """Draw small text with its INK TOP at `y`, not its nominal origin.

    PIL's default bitmap font carries a ~2 px top bearing, and descenders (g, p, y) push
    ink up to 4 rows past the nominal cell — so `d.text((x, 0), "apogee-gs")` puts ink on
    rows 4..11, three of which the state band then paints over. The Part-97 callsign is the
    one string on this panel with a REGULATORY reason to be legible, so it must not be
    clipped.

    This is the same advance-vs-ink distinction that kept the unit out of the hero band, one
    band up: a glyph's nominal cell is not where its pixels are. Measuring rather than
    assuming means every string's 8-row ink lands inside the 8 px header with no resize and
    no magic constant.
    """
    top = d.textbbox((0, 0), str(text))[1]
    d.text((x, y - top), str(text), fill=fill)


def small_ink_rows(text, x=0, y=0):
    """Ink rows that `draw_small` would occupy — so a test can pin containment."""
    from PIL import Image, ImageDraw   # pyright: ignore[reportMissingImports]
    img = Image.new("1", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    draw_small(d, text, x, y)
    px = img.load()
    rows = [r for r in range(HEIGHT) if any(px[c, r] for c in range(WIDTH))]
    if not rows:                # a string that draws nothing is a caller's bug, not a value
        raise ValueError(f"{text!r} rendered no ink at y={y}")
    return min(rows), max(rows)


def burn_in_offset(tick):
    """(dx, dy) for this tick — a 4-phase 1 px walk. Pure, so it is testable."""
    return _SHIFT_STATES[(tick // _SHIFT_PERIOD_TICKS) % len(_SHIFT_STATES)]


def _draw_hero(d, text, y, dx, dy):
    """Hand-drawn DIGITS ONLY, horizontally centred. Width is MEASURED, never assumed.

    The unit does NOT live in this band, for two reasons that reinforce each other. The
    hero alphabet is bounded to `0-9 . k -` (13 hand-drawn shapes) and `glyph()` raises on
    anything else deliberately — that guard caught "1834ft" being handed to the hero during
    development, which is the guard working, not an inconvenience. And mixing small text
    into the band breaks centring: a proportional font's ADVANCE width is not its INK width,
    so a block centred on advances renders visibly off-centre. Digits-only centres exactly,
    and 28 px is the panel's scarcest resource — a unit suffix does not deserve it.
    """
    x = dx + max(0, (WIDTH - text_width(text)) // 2)
    cell = max(glyph_size(c)[0] for c in "0123456789")
    for ch in text:
        rows = glyph(ch)
        for ry, row in enumerate(rows):
            for rx, px in enumerate(row):
                if px == "#":
                    d.point((x + rx, y + ry + dy), fill=1)
        x += advance(ch, True, cell, 2)


def _draw_band(d, left, right, dx, dy):
    """The INVERTED state band: filled rectangle, text knocked out in black.

    Inverted because state is the first thing to read at arm's length, and because a
    freshness alarm can ride here without costing a row or new glyph art.
    """
    d.rectangle([dx, BAND_Y + dy, WIDTH - 1 + dx, BAND_Y + BAND_H - 1 + dy], fill=1)
    draw_small(d, left[:16], 2 + dx, BAND_Y + 2 + dy, fill=0)
    if right:
        draw_small(d, right, WIDTH - 6 * len(right) - 2 + dx, BAND_Y + 2 + dy, fill=0)


def band_text(spec):
    """What the state band says. STALE WINS: freshness rides the band rather than the hero,
    so question 3 (is this number current) never costs question 2 (how high) — the number
    stays readable while the band carries the alarm."""
    if spec.stale:
        age = f"{spec.age_s:.1f}s" if spec.age_s is not None else ""
        return "NO DATA", age
    arrow = {"ASCENT": "^", "DESCENT": "v"}.get(spec.state, "")
    return spec.state[:12], arrow


def _draw_trend(d, spec, dx, dy):
    """Thin strip + micro-stats. Autoscaled to the window's own min/max, which is what makes
    it earn its width during a slow chute descent; without autoscale it is flat decoration
    and, by the closure bar, should be dropped instead of shipped."""
    if spec.trend:
        ys = [v for _, v in spec.trend]
        lo, hi = min(ys), max(ys)
        span = (hi - lo) or 1
        n = len(spec.trend)
        for i, (_, v) in enumerate(spec.trend):
            x = dx + (i * (WIDTH - 1)) // max(1, n - 1)
            y = TREND_Y + TREND_H - 1 - int((v - lo) / span * (TREND_H - 1))
            d.point((x, y + dy), fill=1)
    elif spec.rows:
        draw_small(d, str(spec.rows[-1])[:21], 2 + dx, TREND_Y + dy)
    if spec.hero_unit:      # unit lives HERE, not in the hero band (see _draw_hero)
        draw_small(d, spec.hero_unit, WIDTH - 6 * len(spec.hero_unit) - 1 + dx,
                   TREND_Y + dy)


def render(spec):
    """FrameSpec -> PIL.Image (mode "1", 128x64), ready for luma's device.display()."""
    from PIL import Image, ImageDraw   # pyright: ignore[reportMissingImports]  # lazy: keeps spec.py dependency-free

    img = Image.new("1", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    dx, dy = burn_in_offset(spec.tick)

    rssi = f"{spec.rssi}dBm" if spec.rssi is not None else "--"
    draw_small(d, f"{spec.identity} {spec.liveness_glyph}"[:16], dx, HEADER_Y + dy)
    draw_small(d, rssi, WIDTH - 6 * len(rssi) - 1 + dx, HEADER_Y + dy)

    left, right = band_text(spec)
    _draw_band(d, left, right, dx, dy)
    _draw_hero(d, spec.hero, HERO_Y, dx, dy)

    if spec.page == PAGE_IDLE:
        draw_small(d, " ".join(str(r) for r in spec.rows)[:21], 2 + dx, TREND_Y + dy)
    elif spec.page in (PAGE_LIVE, PAGE_SUMMARY):
        _draw_trend(d, spec, dx, dy)
    return img


def spec_lines(spec):
    """Legacy text rows, retained for the bring-up tools and the Pi-side text path."""
    head = f"{spec.identity} {spec.liveness_glyph}"
    rows = list(spec.rows) if spec.page == PAGE_IDLE else \
        [f"{spec.state} {spec.hero}{spec.hero_unit}"] + list(spec.rows[1:])
    return [line[:21] for line in ([head] + rows)[:4]]
