"""Pure OLED frame SPEC — what is on the screen, not how it is drawn.

Two layers, deliberately:

    frame_spec(view, clock, tick) -> FrameSpec   # THIS module: semantic, pure, stdlib-only
    render(spec)                  -> PIL.Image   # ground/oled/draw.py: pixels

The split exists because the display is scheduled for a layout redesign (28 px hand-drawn
hero, inverted state band, trend strip, three pages). A `-> list[str]` renderer bakes the
display's *text-ness* into its tests, so the redesign would delete the function and every
test with it. A spec survives: the redesign swaps the drawing layer wholesale and these
tests keep their meaning.

`tick` is INJECTED — no clock read, no hardware, exactly like the panel supervisor's
is_lit(). `liveness` advances with it so a wedged render thread is VISIBLE: without it, a
render thread that dies leaves a perfectly plausible last frame on the glass, which is the
same lying-display class removed from the LED panel (a stuck G_ALIVE cannot read as a
blink). A frozen glyph is the display's equivalent.
"""
from dataclasses import dataclass, field

from ground.oled.render import oled_lines

LIVENESS_GLYPHS = ("-", "\\", "|", "/")   # 4-phase; any change per tick proves the loop turns


@dataclass(frozen=True)
class FrameSpec:
    """Semantic description of one frame. The drawing layer decides fonts and geometry."""
    page: str                      # "idle" | "live"
    identity: str                  # who we are / who is talking
    state: str                     # READY / PAD / ASCENT / DESCENT / ...
    hero: str                      # the dominant value, already overflow-formatted ("--" if none)
    hero_unit: str                 # "ft" (empty on idle)
    clock: str                     # clock provenance: rtc / attested / unknown
    liveness: int                  # index into LIVENESS_GLYPHS; MUST advance with tick
    rows: tuple = field(default_factory=tuple)   # micro-stat lines, in reading order

    @property
    def liveness_glyph(self) -> str:
        return LIVENESS_GLYPHS[self.liveness % len(LIVENESS_GLYPHS)]

    def texts(self) -> tuple:
        """Every human-readable string in the frame — for assertions and the text renderer."""
        return (self.identity, self.state, f"{self.hero}{self.hero_unit}") + tuple(self.rows)


def _pick(panels):
    """Which SRC does the LIVE page show?

    FORCED, not chosen: rendering moved OFF the RX thread, so there is no longer an
    observed packet whose SRC keys the display — the render thread wakes on a timer and
    must decide for itself. Prefer a panel with an open flight (that is the one the
    operator is watching), else the lowest SRC for determinism. Cycling through multiple
    SRCs is a redesign idea and lives in the backlog.
    """
    flying = [p for p in panels if p.get("flight_open")]
    return min(flying or panels, key=lambda p: p.get("src", 0))


def _hero(panel) -> str:
    """The dominant number as display text. Overflow policy lives HERE, in the pure layer,
    so it is testable — the drawing layer only chooses a font size. Today: pass through.
    (>9,999 ft has no defined behaviour yet — see the RESUME backlog item.)"""
    alt = panel.get("altitude_ft")
    return "--" if alt is None else str(alt)


def frame_spec(view, clock="unknown", tick=0) -> FrameSpec:
    """Snapshot (a dashboard view_model dict, or None) + clock provenance + tick -> FrameSpec.

    `view=None` or no panels -> the IDLE page. A quiet pad is NORMAL and must say so: the
    2026-07-30 bench defect was an empty screen reading as a broken box, because the old
    renderer only ran on an observation callback and never drew anything on a silent pad.
    """
    panels = (view or {}).get("panels") or []
    if not panels:
        return FrameSpec(
            page="idle", identity="apogee-gs", state="READY",
            hero="--", hero_unit="", clock=clock, liveness=tick,
            rows=("waiting SRC:1", f"CLK {clock}", "RSSI --"),
        )
    panel = _pick(panels)
    lines = oled_lines(panel)      # reuse the tested panel->summary renderer for the rows
    return FrameSpec(
        page="live", identity=lines[0], state=str(panel.get("state", "?")).upper(),
        hero=_hero(panel), hero_unit="ft", clock=clock, liveness=tick,
        rows=tuple(lines[1:]),
    )
