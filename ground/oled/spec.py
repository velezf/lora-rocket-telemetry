"""Pure OLED frame SPEC — what is on the screen, not how it is drawn.

    frame_spec(view, clock, rx_age_s, last_flight, tick) -> FrameSpec   # here: semantic, pure
    render(spec)                                         -> PIL.Image   # draw.py: pixels

Everything in this module is stdlib-only, clock-free and hardware-free; `tick` is INJECTED,
exactly like the panel supervisor's is_lit(). The split exists so the layout redesign can
replace the drawing layer wholesale without touching semantics — if a redesign forces a
change to this module's public surface, the seam was in the wrong place and that should be
surfaced, not worked around.

SURFACE SPLIT (the rule that decides what belongs here at all):
  * The LED panel is SUPERVISOR-owned, in its own process. It survives the failures it
    reports, so it answers "IS THE SYSTEM WORKING".
  * This display's render thread lives INSIDE apogee-ingest. When that process dies the
    OLED freezes showing plausible content and cannot report its own death, so it answers
    "WHAT IS THE FLIGHT DOING".
They are not peers. The OLED must never be the authoritative reporter of a system-health
fact — which is why clock provenance appears on IDLE (a pre-launch check, made standing at
the box where B_CLOCK can be cross-checked) and is ABSENT from LIVE and SUMMARY, where a
frozen "CLK rtc" would be a trust claim from the least trustworthy channel.

The one system-health signal that DOES belong here is the liveness glyph: it reports the
RENDER THREAD's own aliveness, a different failure domain from G_ALIVE (the RX loop). No
LED can report it.
"""
from dataclasses import dataclass, field

from ground.oled.render import oled_lines

LIVENESS_GLYPHS = ("-", "\\", "|", "/")   # 4-phase; any change per tick proves the loop turns

PAGE_IDLE, PAGE_LIVE, PAGE_SUMMARY = "idle", "live", "summary"

# Freshness threshold for the hero, applied ONLY in states where silence is abnormal.
# Matches the RX LED's staleness window so the two surfaces agree about what "quiet" means.
STALE_S = 3.0

# Trend strip window. TIME-based, not sample-based: a sample count silently stretches under
# packet loss (60 samples could be four minutes on a bad link), and the strip would then
# misrepresent its own timespan — a quiet lie about how much history you are looking at.
TREND_WINDOW_S = 120.0

# States in which radio silence is NORMAL and must not raise an alarm. A silent pad is the
# expected condition before launch; a silent ascent is the lying-display case this exists
# to catch.
QUIET_STATES = frozenset({"pad", "idle", "ready", "landed", "?", ""})


@dataclass(frozen=True)
class FrameSpec:
    """Semantic description of one frame. The drawing layer decides fonts and geometry.

    Frozen because it crosses the RX -> render thread boundary; that must not become
    mutable shared state. No geometry may leak into this class (pinned by test)."""
    page: str                      # idle | live | summary
    identity: str                  # who we are / who is talking
    state: str                     # READY / PAD / ASCENT / DESCENT / LANDED
    hero: str                      # dominant value, already overflow-formatted ("--" if none)
    hero_unit: str                 # "ft" (empty when there is no number)
    clock: str                     # provenance; rendered on IDLE only (see module docstring)
    tick: int                      # monotonic render tick — BOTH layers derive time from it
    stale: bool = False            # hero is frozen and the state says that is abnormal
    age_s: float | None = None     # seconds since the last accepted packet, if known
    rssi: int | None = None
    loss_pct: float = 0.0
    rows: tuple = field(default_factory=tuple)     # micro-stat lines, in reading order
    trend: tuple = field(default_factory=tuple)    # (age_s, agl_ft) samples for the strip

    @property
    def liveness_glyph(self) -> str:
        return LIVENESS_GLYPHS[self.tick % len(LIVENESS_GLYPHS)]

    def texts(self) -> tuple:
        """Every human-readable string in the frame — for assertions and the text renderer."""
        hero = f"{self.hero}{self.hero_unit}"
        return (self.identity, self.state, hero) + tuple(self.rows)


def format_hero(value) -> str:
    """The dominant number as display text, bounded to 5 glyphs over the hand-drawn set.

    Overflow policy lives HERE, in the pure layer, so it is a testable decision rather than
    a font-size hack at draw time. Above 9,999 ft we switch UNITS rather than shrink or
    clip: shrinking breaks "readable at arm's length" exactly when altitude matters most,
    and clipping is a lie. Sub-100 ft precision is meaningless at 10k.

    Truncates rather than rounds, so the hero can never OVERSTATE altitude.
    """
    if value is None:
        return "--"                                    # never 0 — that would be a lie
    v = int(value)
    sign, mag = ("-" if v < 0 else ""), abs(v)
    if mag < 10_000:
        return f"{sign}{mag}"
    if mag < 100_000:
        return f"{sign}{mag // 100 / 10:.1f}k"          # truncated: 10234 -> 10.2k
    return f"{sign}{mag // 1000}k"                      # 123456 -> 123k


def is_stale(state, age_s) -> bool:
    """Is the hero frozen in a way the operator must be warned about?

    STATE-DEPENDENT by design: silence on the PAD is normal and must not cry wolf, while
    silence during ASCENT/DESCENT means the number on screen is the past — the same
    lying-display class as a flight LED still lit after an ingest crash.

    An UNKNOWN age is not an alarm: absence of data is not stale data (startup, no packet
    has ever arrived), and a false alarm at power-on would train the operator to ignore it.
    """
    if age_s is None:
        return False
    if str(state or "").lower() in QUIET_STATES:
        return False
    return age_s > STALE_S


def trend_window(samples, now_s, window_s=TREND_WINDOW_S) -> tuple:
    """Keep the samples inside a TIME window. `samples` is [(t_s, value), ...]."""
    return tuple((t, v) for t, v in samples if now_s - t <= window_s)


def _pick(panels):
    """Which SRC does the display follow?

    FORCED, not chosen: rendering runs off the RX thread, so there is no observed packet
    whose SRC keys the display — the render thread wakes on a timer and must decide. Prefer
    a panel with an open flight (what the operator is watching), else the lowest SRC for
    determinism. Cycling multiple SRCs waits for Epic 7 to make a second node exist.
    """
    flying = [p for p in panels if p.get("flight_open")]
    return min(flying or panels, key=lambda p: p.get("src", 0))


def _page(panels, last_flight) -> str:
    """Page follows FLIGHT STATE, never a timer.

    SUMMARY holds until the next flight opens rather than timing out: it is what the
    operator reads walking downrange with the box in hand, and a timeout would blank the
    one number they went to fetch. Because the page is derived from flight state (not from
    in-memory flags), a mid-flight restart returns to LIVE instead of dropping to IDLE.
    """
    if not panels:
        return PAGE_IDLE
    if any(p.get("flight_open") for p in panels):
        return PAGE_LIVE
    if last_flight:
        return PAGE_SUMMARY
    return PAGE_IDLE               # a sled on the pad, no flight open: the pad page


def frame_spec(view, clock="unknown", rx_age_s=None, last_flight=None, tick=0) -> FrameSpec:
    """Dashboard view_model (or None) + external inputs -> FrameSpec.

    `view=None` or no panels -> IDLE. A quiet pad is NORMAL and must say so: the 2026-07-30
    bench defect was an empty screen reading as a broken box, because the old renderer ran
    only on an observation callback and never drew anything on a silent pad.
    """
    panels = (view or {}).get("panels") or []
    page = _page(panels, last_flight)

    if not panels:
        return FrameSpec(
            page=PAGE_IDLE, identity="apogee-gs", state="READY",
            hero="--", hero_unit="", clock=clock, tick=tick,
            rows=("waiting SRC:1", f"CLK {clock}", "RSSI --"),
        )

    panel = _pick(panels)
    lines = oled_lines(panel)
    state = str(panel.get("state", "?")).upper()
    rssi, loss = panel.get("rssi"), panel.get("seq_loss_pct", 0.0)

    if page == PAGE_SUMMARY:
        hero = format_hero((last_flight or {}).get("peak_ft"))
        fid = (last_flight or {}).get("flight_id", "")
        rows = (f"PEAK {fid}".rstrip(), f"RSSI {rssi if rssi is not None else '--'}",
                f"LOSS {loss}%")
    else:
        hero = format_hero(panel.get("altitude_ft"))
        rows = [f"P {format_hero(panel.get('peak_ft'))}ft",
                f"RSSI {rssi if rssi is not None else '--'} L{loss}%"]
        if page == PAGE_IDLE:
            # Pre-launch only: clock provenance is a SYSTEM-HEALTH fact and belongs to
            # B_CLOCK, which survives an ingest death this display cannot report. It is
            # shown here because the operator is standing at the box and can cross-check.
            rows.append(f"CLK {clock}")
        rows = tuple(rows)

    return FrameSpec(
        page=page, identity=lines[0], state=state,
        hero=hero, hero_unit="ft" if hero != "--" else "",
        clock=clock, tick=tick,
        stale=is_stale(panel.get("state"), rx_age_s), age_s=rx_age_s,
        rssi=rssi, loss_pct=loss, rows=rows,
    )
