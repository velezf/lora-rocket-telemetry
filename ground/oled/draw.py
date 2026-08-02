"""OLED drawing layer — FrameSpec -> a 128x64 1-bit PIL image.

This is the layer the layout redesign REPLACES wholesale (28 px hand-drawn hero digits,
inverted state band + glyph, RSSI icon, thin trend strip, three pages sharing one scan
pattern). Today it is deliberately trivial: the same four text rows the display has always
shown, drawn into an image instead of handed to luma as strings.

Keeping it trivial is the point — the FIX branch changes WHERE rendering happens and WHEN,
not what it looks like. The spec layer (ground/oled/spec.py) carries the meaning and its
tests survive the redesign; this file is expected to be thrown away.

NO GOLDEN-IMAGE TESTS IN THIS BRANCH. Goldens attach here only once the hand-drawn digits
and a committed bold pixel TTF land, because the default PIL bitmap font is not guaranteed
identical between the Mac and the Pi — host/Pi divergence is the exact constraint that
forced the commit-a-font decision in the first place. Until then this layer is asserted on
structure (size, mode), not pixels.
"""
WIDTH, HEIGHT = 128, 64
_LINE_H = 16
_MAX_CHARS = 21          # what the default font fits across 128 px


def spec_lines(spec) -> list:
    """FrameSpec -> the <=4 short text rows this trivial renderer draws.

    Text-shaped, and therefore temporary: the redesign replaces rows-of-text with a hero
    number plus micro-stats. The liveness glyph rides on the identity row so it is visible
    on every page without costing a row.
    """
    head = f"{spec.identity} {spec.liveness_glyph}"
    if spec.page == "idle":
        rows = list(spec.rows)
    else:
        rows = [f"{spec.state} {spec.hero}{spec.hero_unit}"] + list(spec.rows[1:])
    return [line[:_MAX_CHARS] for line in ([head] + rows)[:4]]


def render(spec):
    """FrameSpec -> PIL.Image (mode "1", 128x64) ready for luma's device.display().

    PIL is imported lazily so the pure spec layer stays importable without Pillow.
    """
    from PIL import Image, ImageDraw   # pyright: ignore[reportMissingImports]  # lazy: keeps the pure layer dependency-free

    img = Image.new("1", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(spec_lines(spec)):
        d.text((0, i * _LINE_H), line, fill=1)
    return img
