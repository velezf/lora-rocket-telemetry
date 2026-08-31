"""AGL pad baseline on the handheld (Epic 8.2 slice 5).

Reuses `ground/flights/baseline.py::pad_baseline` — the same pure function
the ground live path locks at flight_open — so the handheld displays AGL,
not raw baro (first bench 2026-08-31: sled on the pad read -85 ft, PK 0).
Semantics mirror the ground: compute while St:0, FREEZE at liftoff; a
handheld powered on mid-flight (no pad history) falls back to raw.
"""
from ground.decode.v1 import decode

from handheld.app.viewmodel import HandheldModel


def obs(m, mono, st, alt, maxft=0, seq=1):
    pkt = decode(f"V:1 SYS:7 SRC:1 SEQ:{seq} St:{st} ALT:{alt}ft Max:{maxft}ft".encode())
    assert pkt.ok
    m.observe(pkt, rssi_dbm=-45.0, mono=mono)


def settle(m, alt=-85, t0=0.0, seconds=25):
    for i in range(seconds):
        obs(m, mono=t0 + i, st=0, alt=alt, seq=i + 1)
    return t0 + seconds - 1


def test_quiet_pad_displays_zero_agl():
    m = HandheldModel()
    settle(m)
    v = m.snapshot(mono=25.0)
    assert v.alt_ft == 0            # -85 raw - (-85) baseline
    assert v.peak_ft == 0           # raw Max:0 is corrected too... to +85?  no:
    # Max is the sled's running max of the SAME raw quantity, but on a quiet
    # pad raw Max:0 predates nothing real — corrected peak must not exceed
    # corrected alt on a pad that has never moved
    assert v.peak_ft <= max(v.alt_ft, 0)


def test_flight_altitudes_are_agl_and_peak_tracks():
    m = HandheldModel()
    t = settle(m)
    obs(m, mono=t + 1, st=1, alt=115, maxft=115, seq=90)   # boost: 115 raw
    v = m.snapshot(mono=t + 1.1)
    assert v.alt_ft == 200          # 115 - (-85)
    assert v.peak_ft == 200
    obs(m, mono=t + 2, st=2, alt=150, maxft=327, seq=91)   # descent, sled Max
    v = m.snapshot(mono=t + 2.1)
    assert v.alt_ft == 235
    assert v.peak_ft == 412         # 327 - (-85): sled Max corrected on the
    assert v.apogee_reveal          # same raw scale


def test_baseline_freezes_at_liftoff():
    m = HandheldModel()
    t = settle(m, alt=-85)
    obs(m, mono=t + 1, st=1, alt=15, seq=50)
    # descent samples must not re-baseline even though St later returns... it
    # doesn't (latched states), but pad-like altitudes in flight must not shift
    # the zero: baseline stays -85
    obs(m, mono=t + 40, st=2, alt=-80, seq=51)
    assert m.snapshot(mono=t + 40.1).alt_ft == 5    # -80 - (-85)


def test_midflight_power_on_falls_back_to_raw():
    m = HandheldModel()
    obs(m, mono=1.0, st=1, alt=400, maxft=400, seq=9)
    v = m.snapshot(mono=1.1)
    assert v.alt_ft == 400          # no pad history: raw, not garbage
    assert v.peak_ft == 400


def test_unstable_pad_keeps_raw_until_it_settles():
    m = HandheldModel()
    # bouncing altitudes (handling): stdev far beyond MAX_STDEV
    for i, a in enumerate([-85, -60, -95, -70, -88, -55, -90, -65,
                           -85, -60, -95, -70, -88, -55, -90, -65,
                           -85, -60, -95, -70, -88, -55, -90, -65]):
        obs(m, mono=float(i), st=0, alt=a, seq=i + 1)
    assert m.snapshot(mono=23.1).alt_ft == -65      # last raw; no false zero
    # then it settles: 20 s of quiet -85 and the zero locks in
    for i in range(20):
        obs(m, mono=30.0 + i, st=0, alt=-85, seq=40 + i)
    assert m.snapshot(mono=49.5).alt_ft == 0
