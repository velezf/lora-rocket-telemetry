"""Pure layout renderer: viewmodel.View -> 128x32 1-bit PIL image (Epic 8.2).

No hardware, no clocks — deterministic f(View), host-testable. The display
glue ships whatever this returns to the SSD1306; all decisions about WHAT to
show live in the view-model, all decisions about WHERE live here.

Uses Pillow's embedded default font only (no committed font assets — the
ground OLED redesign deferred hand-drawn/bitmap fonts, same posture here).
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 128, 32

_SMALL = ImageFont.load_default()
_HERO = ImageFont.load_default(size=17)

_ST_LABEL = {0: "PAD", 1: "UP!", 2: "DOWN"}


def render(view) -> Image.Image:
    img = Image.new("1", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)

    if view.mode == "idle":
        # a quiet pad must LOOK alive (the 2026-07-30 ground OLED defect was
        # an idle screen indistinguishable from a dead one)
        d.text((0, 0), "APOGEE ZEPHYR", font=_SMALL, fill=1)
        d.text((0, 11), "listening for", font=_SMALL, fill=1)
        d.text((0, 21), "the rocket...", font=_SMALL, fill=1)
        if view.battery_pct is not None:
            d.text((96, 0), f"{view.battery_pct}%", font=_SMALL, fill=1)
        return img

    if view.liftoff_banner:
        d.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], fill=1)
        d.text((20, 7), "LIFTOFF!", font=_HERO, fill=0)
        return img

    if view.apogee_reveal:
        d.text((0, 0), "APOGEE", font=_SMALL, fill=1)
        d.text((0, 10), f"{view.peak_ft}ft", font=_HERO, fill=1)
        d.text((92, 0), f"{view.alt_ft}", font=_SMALL, fill=1)
    else:
        d.text((0, 0), f"{view.alt_ft}ft", font=_HERO, fill=1)
        d.text((0, 22), f"PK {view.peak_ft}", font=_SMALL, fill=1)

    st = _ST_LABEL.get(view.st, "?")
    d.text((66, 22), st, font=_SMALL, fill=1)

    if view.mode == "stale":
        d.text((92, 22), f"?{view.age_s:.0f}s", font=_SMALL, fill=1)
    elif view.rssi_dbm is not None:
        d.text((98, 22), f"{view.rssi_dbm:.0f}", font=_SMALL, fill=1)

    return img
