"""Battery % on the OLED (Epic 8.2 slice 6).

Source is pisugar-server's TCP protocol (`get battery` on :8423 — see
handheld/README.md "Access & operations"). The parse and the model/render
paths are pure and tested; the socket read is thin glue. A kid-held device
that dies silently mid-flight is a sad kid — the idle page shows charge.
"""
from handheld.app.battery import parse_battery
from handheld.app.loop import LoopCounters, battery_tick
from handheld.app.render import render
from handheld.app.viewmodel import HandheldModel, View


def test_parse_battery():
    assert parse_battery(b"battery: 88.47138\n") == 88
    assert parse_battery(b"battery: 5.4") == 5
    assert parse_battery(b"battery: I2C not connected") is None   # the dead-bus reply
    assert parse_battery(b"") is None
    assert parse_battery(b"nonsense") is None


def test_model_carries_battery_into_view():
    m = HandheldModel()
    assert m.snapshot(mono=1.0).battery_pct is None
    m.set_battery(88, mono=2.0)
    assert m.snapshot(mono=2.1).battery_pct == 88
    m.set_battery(None, mono=3.0)              # reader failed: keep last known
    assert m.snapshot(mono=3.1).battery_pct == 88


def test_idle_page_shows_battery_when_known():
    base = dict(mode="idle", alt_ft=None, peak_ft=None, st=None, rssi_dbm=None,
                age_s=None, liftoff_banner=False, apogee_reveal=False)
    without = render(View(**base, battery_pct=None))
    with_b = render(View(**base, battery_pct=88))
    assert without.tobytes() != with_b.tobytes()
    # and the value is actually displayed, not just a flag
    assert render(View(**base, battery_pct=12)).tobytes() != with_b.tobytes()


def test_battery_tick_reads_counts_and_survives():
    m = HandheldModel()
    c = LoopCounters()
    battery_tick(m, lambda: 77, mono=1.0, counters=c)
    assert m.snapshot(mono=1.1).battery_pct == 77

    def broken():
        raise OSError("pisugar-server down")

    battery_tick(m, broken, mono=2.0, counters=c)   # counted, never raised
    assert c.battery_errors == 1
    assert m.snapshot(mono=2.1).battery_pct == 77   # last known retained
