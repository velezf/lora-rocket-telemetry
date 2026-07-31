"""RED-phase tests for the pure supervisor logic (ground.panel.supervisor).

Freshness (fail-closed), the heartbeat-file -> led_states-input mapping, and the Blink ->
on/off tick encoding (HEARTBEAT must stay a blink so a frozen supervisor is detectable).
`now` is injected as a datetime; no wall-clock read, no hardware.
"""
from datetime import datetime, timedelta, timezone

from ground.panel.leds import Blink, led_states
from ground.panel.supervisor import (
    fresh, supervisor_state, is_lit, TICKS_PER_SEC, STALE_S,
)

NOW = datetime(2026, 7, 31, 1, 0, 0, tzinfo=timezone.utc)


def _iso(delta_s):
    return (NOW - timedelta(seconds=delta_s)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# --- fresh(): fail-closed staleness ---

def test_fresh_true_when_recent():
    assert fresh(_iso(1.0), NOW, STALE_S) is True


def test_fresh_false_when_stale():
    assert fresh(_iso(5.0), NOW, STALE_S) is False


def test_fresh_false_on_none():
    assert fresh(None, NOW, STALE_S) is False


def test_fresh_false_on_unparseable():
    assert fresh("not-a-timestamp", NOW, STALE_S) is False


def test_fresh_naive_string_fails_closed_and_logs():
    # A naive timestamp (no Z / no offset) is a tz BUG, not normal state: fail-closed AND log,
    # so it can't hide as a permanent legitimate-looking RED.
    logs = []
    assert fresh("2026-07-31T01:00:00.000", NOW, STALE_S, log=logs.append) is False
    assert logs and "naive" in logs[0].lower()


def test_fresh_stale_does_not_log():
    # normal staleness is not a bug — no log noise
    logs = []
    assert fresh(_iso(9.0), NOW, STALE_S, log=logs.append) is False
    assert logs == []


def test_fresh_none_does_not_log():
    logs = []
    assert fresh(None, NOW, STALE_S, log=logs.append) is False
    assert logs == []


def test_fresh_future_timestamp_is_fresh():
    assert fresh(_iso(-1.0), NOW, STALE_S) is True   # file newer than now (clock jitter) = fresh


# --- supervisor_state(): heartbeat file + polls -> led_states input ---

def _raw(ts_age=1.0, rx_age=1.0, flight_open=False, write_ok=True):
    return {
        "ts": _iso(ts_age),
        "last_rx_ts": None if rx_age is None else _iso(rx_age),
        "flight_open": flight_open,
        "write_ok": write_ok,
    }


def test_state_alive_when_heartbeat_fresh():
    st = supervisor_state(_raw(ts_age=1.0), NOW)
    assert st["ingest_alive"] is True


def test_state_down_when_heartbeat_stale():
    st = supervisor_state(_raw(ts_age=9.0), NOW)
    assert st["ingest_alive"] is False


def test_state_down_when_file_missing():
    # No heartbeat file at all (None) -> fail-closed "down".
    st = supervisor_state(None, NOW)
    assert st["ingest_alive"] is False


def test_state_rx_fresh_from_last_rx_ts():
    assert supervisor_state(_raw(rx_age=1.0), NOW)["rx_fresh"] is True
    assert supervisor_state(_raw(rx_age=9.0), NOW)["rx_fresh"] is False
    assert supervisor_state(_raw(rx_age=None), NOW)["rx_fresh"] is False


def test_state_battery_low_threshold():
    assert supervisor_state(_raw(), NOW, battery_pct=9.0)["battery_low"] is True
    assert supervisor_state(_raw(), NOW, battery_pct=80.0)["battery_low"] is False
    assert supervisor_state(_raw(), NOW, battery_pct=None)["battery_low"] is False


def test_state_passes_through_flight_clock_shutdown():
    st = supervisor_state(_raw(flight_open=True), NOW,
                          clock_provenance="attested", shutting_down=True)
    assert st["flight_open"] is True
    assert st["clock"] == "attested"
    assert st["shutting_down"] is True


def test_state_feeds_led_states_directly():
    # The output must be a valid led_states() input (integration): stale heartbeat -> RED SOLID.
    st = supervisor_state(_raw(ts_age=9.0), NOW)
    assert led_states(st)["RED"] == Blink.SOLID


# --- is_lit(): Blink -> on/off at a tick ---

def test_solid_always_on():
    assert all(is_lit(Blink.SOLID, t) for t in range(2 * TICKS_PER_SEC))


def test_off_always_off():
    assert not any(is_lit(Blink.OFF, t) for t in range(2 * TICKS_PER_SEC))


def test_heartbeat_is_a_pulse_never_constant():
    vals = [is_lit(Blink.HEARTBEAT, t) for t in range(2 * TICKS_PER_SEC)]
    assert any(vals) and not all(vals)          # it blinks (both states appear)
    assert sum(vals) < len(vals) / 2            # brief pulse, mostly off — not ~50% duty


def test_fast_toggles_more_than_slow():
    def transitions(blink):
        v = [is_lit(blink, t) for t in range(4 * TICKS_PER_SEC)]
        return sum(1 for a, b in zip(v, v[1:]) if a != b)
    assert transitions(Blink.FAST) > transitions(Blink.SLOW)
