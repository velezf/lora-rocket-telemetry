"""Pure supervisor logic (feat/panel-leds).

The thin Pi-only shell polls sources (heartbeat state file, pisugar battery, /run clock
marker, systemd shutdown state) and drives GPIO. These pure functions carry the judgement:

- fresh(iso_ts, now, max_age_s): is a timestamp recent enough? Fail-closed, tz-strict.
- supervisor_state(raw, now, ...): heartbeat-file dict + external polls -> the led_states()
  input, deriving ingest_alive / rx_fresh / battery_low from freshness + thresholds.
- is_lit(blink, tick): Blink -> on/off at an integer tick. HEARTBEAT stays a brief pulse
  (never constant) so a frozen supervisor's stuck LED can't read as a blink.

`now` is injected (a datetime the shell passes) — no wall-clock read here; hardware-free.

TICK RATE: the shell renders at TICKS_PER_SEC (8 Hz). is_lit GENERATES the waveform from the
tick counter (it does not SAMPLE an external signal), so there is no aliasing: 8 Hz ticks
produce a clean FAST=4 Hz square and SLOW=1 Hz square — 4x apart, visibly distinct. If the
shell ran at 1 Hz, FAST and SLOW would collapse; it must run at TICKS_PER_SEC.
"""
from datetime import datetime

from ground.panel.leds import Blink

TICKS_PER_SEC = 8      # shell render rate; FAST=4 Hz, SLOW=1 Hz -> 4x apart, distinct
STALE_S = 3.0          # heartbeat liveness (matches the loop-turn analysis)
RX_STALE_S = 3.0       # link activity

# Warning threshold chosen for MINUTES OF RUNWAY, not a round %: aim for ~15+ min to the
# PiSugar 5% auto-shutdown. PiSugar 3 Plus 5000 mAh (~18.5 Wh) at a ~5 W ground-station draw:
# 15%->5% ~= 20 min. CAVEAT: the pisugar API reports model "PiSugar 3" and CANNOT distinguish
# the Plus from the 1200 mAh non-Plus — if this is the non-Plus, 15% is only ~5 min (a surprise,
# not a warning) and this must rise to ~35%. Confirm the physical pack + a real discharge
# measurement. See RESUME backlog "battery-low threshold — measure discharge rate".
LOW_BATT_PCT = 15.0


def fresh(iso_ts, now, max_age_s, log=None) -> bool:
    """True iff iso_ts is a valid AWARE-UTC timestamp within max_age_s of `now` (also aware).

    Fail-closed. `None` -> False (no data yet — normal, silent). A NAIVE or unparseable
    timestamp is a BUG (a naive-vs-aware compare would TypeError into a permanent, legitimate-
    looking RED) -> False AND log via the callback. Normal staleness does NOT log.
    """
    if iso_ts is None:
        return False                                    # no data — normal, not a bug
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        if log:
            log(f"heartbeat ts unparseable: {iso_ts!r} — treating as stale (bug)")
        return False
    if dt.tzinfo is None:
        if log:
            log(f"heartbeat ts is NAIVE (tz bug): {iso_ts!r} — treating as stale")
        return False
    if now.tzinfo is None:
        if log:
            log("supervisor 'now' is NAIVE (tz bug) — treating as stale")
        return False
    return (now - dt).total_seconds() <= max_age_s      # future ts (negative) is fresh


def supervisor_state(raw, now, battery_pct=None, clock_provenance="unknown",
                     shutting_down=False, log=None) -> dict:
    """Heartbeat-file dict (or None) + external polls -> a led_states() input snapshot.
    raw=None (file missing/unreadable) -> fail-closed 'down' snapshot."""
    raw = raw or {}
    return {
        "ingest_alive": fresh(raw.get("ts"), now, STALE_S, log=log),
        "write_ok": bool(raw.get("write_ok", True)),
        "shutting_down": shutting_down,
        "battery_low": battery_pct is not None and battery_pct <= LOW_BATT_PCT,
        "flight_open": bool(raw.get("flight_open", False)),
        "rx_fresh": fresh(raw.get("last_rx_ts"), now, RX_STALE_S, log=log),
        "clock": clock_provenance,
        "rf_foreign": bool(raw.get("rf_foreign", False)),
        "crc_climbing": bool(raw.get("crc_climbing", False)),
    }


def is_lit(blink, tick) -> bool:
    """Blink -> on/off at integer `tick` (TICKS_PER_SEC per second)."""
    if blink == Blink.SOLID:
        return True
    if blink == Blink.HEARTBEAT:
        return tick % TICKS_PER_SEC == 0                 # brief 1-tick pulse each second
    if blink == Blink.SLOW:
        return (tick // (TICKS_PER_SEC // 2)) % 2 == 0   # ~1 Hz square (0.5 s on/off)
    if blink == Blink.FAST:
        return tick % 2 == 0                             # ~4 Hz square at 8 ticks/s
    return False                                         # OFF (and any unknown)
