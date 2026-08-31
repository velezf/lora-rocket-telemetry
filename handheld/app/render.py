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


def _game_dial_line(game) -> str | None:
    """The rules/entry overlay text, or None when the game has none."""
    if game is None:
        return None
    if game.armed:
        return f"LOCKED x{len(game.guesses)} #12=play"
    if game.phase == "rules":
        return f"GAME? {game.menu_label}"
    if game.phase == "entry":
        if game.confirming:
            return f"{game.entering_name} {game.current_guess} OK?"
        return f"{game.entering_name}? {game.current_guess}ft"
    return None


def _render_lab(game) -> Image.Image:
    """RocketLab's dedicated full screens — an offline mode, so no ALT/dBm
    (field ask 2026-08-31); the rocket picker shows MASS, not just a name."""
    img = Image.new("1", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    if game.phase == "rocket":
        # name TOP-RIGHT in line with the label (field fix 2026-08-31: at
        # y10 the big font ran down into the mass line)
        name, mass_g, diam_mm = game.rocket_row
        d.text((0, 0), "ROCKET?", font=_SMALL, fill=1)
        d.text((WIDTH - d.textlength(name, font=_HERO), 0), name,
               font=_HERO, fill=1)
        d.text((0, 20), f"{mass_g}g", font=_SMALL, fill=1)
        d.text((48, 20), f"{diam_mm}mm", font=_SMALL, fill=1)
    elif game.phase == "motor":
        code, impulse, avg_n, _, _ = game.motor_row
        d.text((0, 0), "MOTOR?", font=_SMALL, fill=1)
        d.text((0, 10), code, font=_HERO, fill=1)
        d.text((48, 20), f"{impulse:g}Ns", font=_SMALL, fill=1)
        d.text((96, 20), f"{avg_n:g}N", font=_SMALL, fill=1)
    elif game.phase == "entry":
        d.text((0, 0), f"{game.rocket_row[0]} + {game.motor_row[0]}",
               font=_SMALL, fill=1)
        d.text((0, 20), _game_dial_line(game) or "", font=_SMALL, fill=1)
    else:                                    # reveal: the sim's verdict
        d.text((0, 0), "SIM SAYS", font=_SMALL, fill=1)
        d.text((0, 10), f"{game.peak_ft}ft", font=_HERO, fill=1)
        if game.winner is not None:
            name, guess = game.winner
            d.text((70, 8), f"{name}!", font=_SMALL, fill=1)
            d.text((70, 20), f"wins {guess}", font=_SMALL, fill=1)
    return img


def render(view, game=None) -> Image.Image:
    if game is not None and game.mode == "lab":
        return _render_lab(game)
    img = Image.new("1", (WIDTH, HEIGHT), 0)
    d = ImageDraw.Draw(img)
    dial = _game_dial_line(game)

    if view.mode == "idle":
        # a quiet pad must LOOK alive (the 2026-07-30 ground OLED defect was
        # an idle screen indistinguishable from a dead one)
        d.text((0, 0), "APOGEE ZEPHYR", font=_SMALL, fill=1)
        d.text((0, 11), "listening for", font=_SMALL, fill=1)
        d.text((0, 21), dial or "the rocket...", font=_SMALL, fill=1)
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
        if game is not None and game.winner is not None:
            name, guess = game.winner
            d.text((70, 8), f"{name}!", font=_SMALL, fill=1)
            d.text((70, 20), f"wins {guess}", font=_SMALL, fill=1)
        d.text((66, 20), _ST_LABEL.get(view.st, "?"), font=_SMALL, fill=1)
        if view.mode == "stale":
            d.text((92, 20), f"?{view.age_s:.0f}s", font=_SMALL, fill=1)
        return img

    # live/stale page. RSSI lives TOP-RIGHT with units (field feedback
    # 2026-08-31: unlabeled it read as a floating mystery number, and on the
    # bottom row it collided with the dial). Everything gets a label.
    d.text((0, 0), "ALT", font=_SMALL, fill=1)
    d.text((22, 0), f"{view.alt_ft}ft", font=_HERO, fill=1)
    if view.rssi_dbm is not None:
        rssi = f"{view.rssi_dbm:.0f}dBm"
        d.text((WIDTH - d.textlength(rssi, font=_SMALL), 0), rssi,
               font=_SMALL, fill=1)
    if dial:
        # the dial owns the whole bottom row; the state word is redundant
        # during betting (betting only happens on the pad)
        d.text((0, 20), dial, font=_SMALL, fill=1)
    else:
        d.text((0, 20), f"PK {view.peak_ft}", font=_SMALL, fill=1)
        d.text((66, 20), _ST_LABEL.get(view.st, "?"), font=_SMALL, fill=1)
        if view.mode == "stale":
            d.text((92, 20), f"?{view.age_s:.0f}s", font=_SMALL, fill=1)

    return img
