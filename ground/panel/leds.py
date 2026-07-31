"""Pure panel-LED state logic (feat/panel-leds).

Six front-panel LEDs are an at-ten-feet operator surface. A supervisor process owns all
six GPIO lines and drives them from this pure policy; ingest is only a *state source*
(publishes a heartbeat state file). Fail-closed by default: with no fresh ingest state the
supervisor passes an "ingest down" snapshot and this returns the NOT-RECORDING pattern.

`ingest_alive` is the supervisor's *freshness verdict* on the heartbeat file, not a claim
ingest made about itself. So a persistent heartbeat-WRITE failure degrades correctly:
the file goes stale -> ingest_alive=False -> RED SOLID + greens OFF ("don't trust me"),
while ingest keeps capturing telemetry. That fail-safe direction (indicator degrades, data
keeps landing) depends on the publisher swallowing write errors and never letting them
escape into the radio loop — enforced and tested on the ingest/publisher side, not here.

This module is clock-free and hardware-free (host-tested, like ground/clock/). The thin
Pi-only shell polls the state sources, calls led_states(), drives GPIO, and runs the
power-on lamp sweep (lamp_test_order) so a dead LED can't hide as a valid OFF/idle state.

G_ALIVE is a HEARTBEAT (blink), NEVER solid — self-detecting one level up: if the supervisor
process itself freezes, every LED sticks in its last state, and a stuck G_ALIVE reads as
solid or dark, neither of which is a blink. So the panel reveals a dead *supervisor*, not
just a dead ingest. Pair with Restart=always on apogee-panel.service. led_states() therefore
never returns SOLID for G_ALIVE (pinned by test).

Logical LED names (color-based; physical position resolved by the lamp test):
  RED, G_ALIVE, G_RX, G_FLIGHT, B_CLOCK, B_RF
"""
from enum import Enum


class Blink(Enum):
    OFF = "off"
    SLOW = "slow"            # slow pulse
    FAST = "fast"            # fast blink
    SOLID = "solid"
    HEARTBEAT = "heartbeat"  # 1 Hz single blink (liveness)


LEDS = ("RED", "G_ALIVE", "G_RX", "G_FLIGHT", "B_CLOCK", "B_RF")

# THE PANEL MAP. Logical names bind to a PHYSICAL POSITION — never to a GPIO number and
# never to an ordinal like "the first blue". Positions are counted left->right from the
# operator's view, 1..6, and are the only stable way to talk about a panel you can point at.
#
# Pure data, so it lives here with lamp_test_order() and not in the Pi shell: these three
# facts must agree, and when they lived in two files they disagreed in 4 of 6 slots — found
# only by lighting LEDs one at a time at the bench. A host test now enforces agreement.
# Colors are FIXED by the harness; the wiring is what it is.
LED_GPIO = {"RED": 26, "G_ALIVE": 5, "G_RX": 6, "G_FLIGHT": 13, "B_CLOCK": 12, "B_RF": 16}
COLOR = {5: "green", 6: "green", 13: "green", 26: "red", 12: "blue", 16: "blue"}


def led_states(state: dict) -> dict:
    """Pure: system-state snapshot -> {led_name: Blink}."""
    # NOTE: write_ok is a valid, tested input, but the ingest heartbeat publisher currently
    # hardcodes write_ok=True — so RED's write-failing leg is INERT end-to-end until the writer
    # exposes health. Do not claim RED covers disk-full yet. Canonical list of inert panel
    # signals: RESUME "Panel signals designed but INERT" (do not restate it here).
    recording = state["ingest_alive"] and state["write_ok"]

    # RED precedence chain: shutdown-pulse > low-batt-fast > steady-not-recording > off.
    if state["shutting_down"]:
        red = Blink.SLOW
    elif state["battery_low"]:
        red = Blink.FAST
    elif not recording:            # ingest down / gate refused / write failing
        red = Blink.SOLID
    else:
        red = Blink.OFF

    clock = state["clock"]
    clock_blink = (Blink.SOLID if clock == "rtc"
                   else Blink.SLOW if clock == "attested"
                   else Blink.OFF)   # "unknown" / no marker

    return {
        "RED": red,
        "G_ALIVE": Blink.HEARTBEAT if state["ingest_alive"] else Blink.OFF,
        "G_RX": Blink.FAST if state["rx_fresh"] else Blink.OFF,
        "G_FLIGHT": Blink.SOLID if state["flight_open"] else Blink.OFF,
        "B_CLOCK": clock_blink,
        # RF trouble: CRC-climbing is the salient (fast) case, foreign traffic the slow one.
        "B_RF": (Blink.FAST if state["crc_climbing"]
                 else Blink.SLOW if state["rf_foreign"]
                 else Blink.OFF),
    }


def lamp_test_order() -> list:
    """The six LEDs in PHYSICAL LEFT->RIGHT order — 🔵🔵🔴🟢🟢🟢, resolved per-position by
    single-LED probing on the bench 2026-07-31 (pos1 GPIO16, pos2 GPIO12, pos3 GPIO26,
    pos4 GPIO13, pos5 GPIO6, pos6 GPIO5). Doubles as the power-on sweep order; every LED
    appears exactly once so a dead one shows up at boot.

    Reading the panel left->right: RF trouble, clock provenance, NOT-RECORDING, flight
    open, RX activity, alive-heartbeat. The two "is my data good?" signals — RED
    (not recording) and B_CLOCK (timestamps trustworthy) — are ADJACENT on purpose, so
    trust reads in one glance; G_FLIGHT sits on RED's other side as the recording-status
    pair (pinned by test).
    """
    return ["B_RF", "B_CLOCK", "RED", "G_FLIGHT", "G_RX", "G_ALIVE"]


def lamp_sweep_plan(on_s=1.2, gap_s=0.4, all_on_s=1.5, pass_gap_s=2.0, passes=2) -> list:
    """Power-on sweep as an ordered list of `(lit_led_names, seconds)` steps. Pure: the Pi
    shell executes it verbatim, so the pacing is testable instead of being magic sleeps in
    hardware glue no test can reach.

    Two questions, deliberately separated so the operator answers one at a time:
      1. "is any LED dead?"  -> the opening all-on frame (position-independent),
      2. "which GPIO is where?" -> the march, in lamp_test_order().

    Because the march runs in the order we BELIEVE is physical left->right, a correct
    LED_GPIO map produces a clean uninterrupted L->R march; any wrong assignment shows up
    as a visible out-of-order jump, which localises the error instead of merely failing.
    Every lit step is followed by a dark gap (three adjacent greens would otherwise read as
    one sliding glow), and a longer break separates the confirmation pass from the first.
    """
    plan = [(tuple(LEDS), all_on_s), ((), gap_s)]     # all-on: dead-LED check, then dark
    for p in range(passes):
        if p:
            plan.append(((), pass_gap_s))            # unmistakably longer = "new pass"
        for name in lamp_test_order():
            plan.append(((name,), on_s))
            plan.append(((), gap_s))
    return plan
