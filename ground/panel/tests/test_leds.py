"""Tests for the pure panel-LED policy (ground.panel.leds).

State matrix + the RED precedence chain (shutdown-pulse > low-batt-fast >
steady-not-recording > off), the BlinkState vocabulary, the fail-closed degradation, and
the lamp-test sweep. No hardware in the loop. OFF-asserting cases carry a positive
co-assertion so an all-OFF stub cannot satisfy them by accident.
"""
import itertools

from ground.panel.leds import (
    Blink, LEDS, LED_GPIO, COLOR, led_states, lamp_test_order, lamp_sweep_plan,
)


def base_state():
    """Nominal healthy pad: ingest up + persisting, no flight, quiet link, RTC clock."""
    return {
        "ingest_alive": True,     # supervisor's freshness verdict on the heartbeat file
        "write_ok": True,         # ingest is persisting the session log
        "shutting_down": False,
        "battery_low": False,
        "flight_open": False,     # any SRC flight open
        "rx_fresh": False,        # accepted a packet recently
        "clock": "rtc",           # "rtc" | "attested" | "unknown"
        "rf_foreign": False,
        "crc_climbing": False,
    }


def _with(**over):
    s = base_state()
    s.update(over)
    return s


# --- vocabulary / structure ---

def test_blink_vocabulary():
    assert {b.name for b in Blink} == {"OFF", "SLOW", "FAST", "SOLID", "HEARTBEAT"}


def test_all_leds_always_present():
    assert set(led_states(base_state())) == set(LEDS)


# --- RED: the precedence chain (shutdown > low-batt > not-recording > off) ---

def test_red_off_when_healthy_recording():
    out = led_states(base_state())
    assert out["RED"] == Blink.OFF
    assert out["G_ALIVE"] == Blink.HEARTBEAT   # discriminating: not an all-OFF board


def test_red_solid_when_ingest_down():
    assert led_states(_with(ingest_alive=False))["RED"] == Blink.SOLID


def test_red_solid_when_write_failing():
    assert led_states(_with(write_ok=False))["RED"] == Blink.SOLID


def test_red_fast_on_low_batt_even_while_recording():
    assert led_states(_with(battery_low=True))["RED"] == Blink.FAST


def test_red_lowbatt_outranks_not_recording():
    assert led_states(_with(battery_low=True, ingest_alive=False))["RED"] == Blink.FAST


def test_red_shutdown_outranks_everything():
    s = _with(shutting_down=True, battery_low=True, ingest_alive=False, write_ok=False)
    assert led_states(s)["RED"] == Blink.SLOW


# --- fail-closed degradation: stale heartbeat (incl. persistent write failure) ---

def test_fail_closed_snapshot_red_solid_greens_off():
    # Supervisor sees no fresh ingest state -> "down" snapshot. Correct degradation:
    # RED SOLID (don't-trust-me) and every green dark, regardless of stale in-memory hopes.
    out = led_states(_with(ingest_alive=False, flight_open=False, rx_fresh=False))
    assert out["RED"] == Blink.SOLID
    assert out["G_ALIVE"] == Blink.OFF
    assert out["G_RX"] == Blink.OFF
    assert out["G_FLIGHT"] == Blink.OFF


# --- greens: alive heartbeat / RX / flight-open ---

def test_green_alive_heartbeat_when_up():
    assert led_states(base_state())["G_ALIVE"] == Blink.HEARTBEAT


def test_green_alive_never_solid_across_all_states():
    # Self-detecting supervisor liveness: G_ALIVE must be HEARTBEAT or OFF, never SOLID —
    # a frozen supervisor leaves it stuck solid/dark, which cannot be mistaken for a blink.
    bools = [False, True]
    for (alive, wok, sd, low, fo, rx, fg, crc) in itertools.product(bools, repeat=8):
        for clock in ("rtc", "attested", "unknown"):
            out = led_states({
                "ingest_alive": alive, "write_ok": wok, "shutting_down": sd,
                "battery_low": low, "flight_open": fo, "rx_fresh": rx,
                "clock": clock, "rf_foreign": fg, "crc_climbing": crc,
            })
            assert out["G_ALIVE"] in (Blink.HEARTBEAT, Blink.OFF)


def test_green_alive_off_when_down():
    out = led_states(_with(ingest_alive=False))
    assert out["G_ALIVE"] == Blink.OFF
    assert out["RED"] == Blink.SOLID           # discriminating co-assertion


def test_green_rx_blinks_when_fresh():
    assert led_states(_with(rx_fresh=True))["G_RX"] == Blink.FAST


def test_green_rx_off_when_silent():
    out = led_states(base_state())
    assert out["G_RX"] == Blink.OFF
    assert out["G_ALIVE"] == Blink.HEARTBEAT   # discriminating: healthy pad, just quiet


def test_green_flight_solid_when_open():
    assert led_states(_with(flight_open=True))["G_FLIGHT"] == Blink.SOLID


def test_green_flight_off_when_closed():
    out = led_states(base_state())
    assert out["G_FLIGHT"] == Blink.OFF
    assert out["G_ALIVE"] == Blink.HEARTBEAT   # discriminating


# --- blues: clock provenance / RF trouble ---

def test_blue_clock_solid_rtc():
    assert led_states(_with(clock="rtc"))["B_CLOCK"] == Blink.SOLID


def test_blue_clock_slow_attested():
    assert led_states(_with(clock="attested"))["B_CLOCK"] == Blink.SLOW


def test_blue_clock_off_unknown():
    out = led_states(_with(clock="unknown"))
    assert out["B_CLOCK"] == Blink.OFF
    assert out["G_ALIVE"] == Blink.HEARTBEAT   # discriminating: ingest still up


def test_blue_rf_fast_on_crc_climbing():
    assert led_states(_with(crc_climbing=True))["B_RF"] == Blink.FAST


def test_blue_rf_slow_on_foreign():
    assert led_states(_with(rf_foreign=True))["B_RF"] == Blink.SLOW


def test_blue_rf_crc_outranks_foreign():
    assert led_states(_with(crc_climbing=True, rf_foreign=True))["B_RF"] == Blink.FAST


def test_blue_rf_off_when_clean():
    out = led_states(base_state())
    assert out["B_RF"] == Blink.OFF
    assert out["B_CLOCK"] == Blink.SOLID       # discriminating


# --- lamp test: the power-on sweep must cover every LED exactly once ---

def test_lamp_test_covers_all_six_once():
    order = lamp_test_order()
    assert sorted(order) == sorted(LEDS)
    assert len(order) == len(set(order)) == 6


# --- the panel map: physical order, GPIO assignment and colors must agree ---
#
# These three facts used to live in two files that could disagree (lamp_test_order here,
# LED_GPIO/COLOR in the Pi shell). They did disagree — in 4 of 6 slots — and it cost a
# full bench session of single-LED probes to find out. Now they sit together and this
# test enforces agreement in milliseconds on the Mac. Do not re-split them.

PANEL_COLORS = ["blue", "blue", "red", "green", "green", "green"]   # 🔵🔵🔴🟢🟢🟢, probed 2026-07-31


def test_every_led_has_a_gpio_and_a_color():
    assert sorted(LED_GPIO) == sorted(LEDS)
    assert sorted(COLOR) == sorted(LED_GPIO.values())
    assert len(set(LED_GPIO.values())) == 6         # no two LEDs share a line


def test_physical_order_maps_through_gpio_to_the_confirmed_color_sequence():
    # THE pin. lamp_test_order() is physical left->right; mapping it through LED_GPIO and
    # COLOR must reproduce the sequence read off the real panel. A wrong LED map means
    # misreading the panel at the pad, so it is worth a test rather than a probe.
    assert [COLOR[LED_GPIO[name]] for name in lamp_test_order()] == PANEL_COLORS


def test_flight_led_is_adjacent_to_red():
    # Design intent: flight-open sits beside RED as the recording-status pair, so the
    # "am I capturing?" signals read as one group.
    order = lamp_test_order()
    assert abs(order.index("G_FLIGHT") - order.index("RED")) == 1


# --- lamp-sweep PLAN: the pacing the Pi shell executes verbatim ---
#
# The plan is pure so the properties that make the sweep *readable by eye* are pinned by
# test rather than living as magic sleeps in the hardware shell (which no test can reach).

def _march(plan):
    """The single-LED steps of a plan, in order, as flat LED names."""
    return [lit[0] for lit, _ in plan if len(lit) == 1]


def test_lamp_sweep_plan_opens_with_every_led_lit_at_once():
    # Dead-LED detection is a SEPARATE question from position: light all six together so a
    # dark one is obvious without the operator having to track order at the same time.
    lit, secs = lamp_sweep_plan()[0]
    assert sorted(lit) == sorted(LEDS)
    assert secs > 0


def test_lamp_sweep_plan_marches_in_lamp_test_order():
    # THE pin for "one order, tested, used": the plan the shell executes must march in
    # lamp_test_order() — a production sweep that ignores the tested order is a fiction.
    assert _march(lamp_sweep_plan(passes=1)) == lamp_test_order()
    assert _march(lamp_sweep_plan(passes=2)) == lamp_test_order() * 2


def test_lamp_sweep_plan_darkens_between_lit_steps():
    # Without a dark gap, the three ADJACENT greens read as one sliding glow and the
    # operator cannot call where one position ends and the next begins.
    plan = lamp_sweep_plan()
    for (lit_a, _), (lit_b, _) in zip(plan, plan[1:]):
        assert not (lit_a and lit_b), f"{lit_a} -> {lit_b} with no dark gap"


def test_lamp_sweep_plan_every_step_has_a_positive_duration():
    assert all(secs > 0 for _, secs in lamp_sweep_plan())


def test_lamp_sweep_plan_pass_break_is_longer_than_an_inter_led_gap():
    # A second pass is the operator's confirmation read; the break must be unmistakably
    # longer than an inter-LED gap or pass 2 looks like a 7th position.
    plan = lamp_sweep_plan(passes=2)
    dark = [secs for lit, secs in plan if not lit]
    assert max(dark) > min(dark)
