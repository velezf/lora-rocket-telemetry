"""Tests for the pure panel-LED policy (ground.panel.leds).

State matrix + the RED precedence chain (shutdown-pulse > low-batt-fast >
steady-not-recording > off), the BlinkState vocabulary, the fail-closed degradation, and
the lamp-test sweep. No hardware in the loop. OFF-asserting cases carry a positive
co-assertion so an all-OFF stub cannot satisfy them by accident.
"""
from ground.panel.leds import Blink, LEDS, led_states, lamp_test_order


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
