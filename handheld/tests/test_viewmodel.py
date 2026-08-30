"""Pure view-model for the kids' handheld (Epic 8.2).

Frames enter through the REAL v1 decoder (`ground/decode/v1.py`) rather than
hand-built dicts, so these tests exercise the actual wire contract — the same
anti-hollow discipline as the ground unknown-tag gate tests. Time is injected
(monotonic seconds); no I/O anywhere.
"""
from ground.decode.v1 import decode

from handheld.app.viewmodel import HandheldModel


def frame(st, alt, maxft=None, seq=1, met=0):
    toks = [f"V:1 SYS:7 SRC:1 SEQ:{seq} St:{st} ALT:{alt}ft"]
    if maxft is not None:
        toks.append(f"Max:{maxft}ft")
    toks.append(f"MET:{met}")
    pkt = decode(" ".join(toks).encode("ascii"))
    assert pkt.ok, pkt
    return pkt


def test_fresh_model_is_idle():
    m = HandheldModel()
    v = m.snapshot(mono=100.0)
    assert v.mode == "idle"
    assert v.alt_ft is None


def test_pad_frame_goes_live_without_liftoff_banner():
    m = HandheldModel()
    m.observe(frame(st=0, alt=3), rssi_dbm=-52.0, mono=10.0)
    v = m.snapshot(mono=10.1)
    assert v.mode == "live"
    assert v.alt_ft == 3
    assert v.st == 0
    assert v.rssi_dbm == -52.0
    assert not v.liftoff_banner


def test_liftoff_banner_on_st_transition_then_clears():
    m = HandheldModel(liftoff_banner_s=3.0)
    m.observe(frame(st=0, alt=2, seq=1), rssi_dbm=-50, mono=10.0)
    m.observe(frame(st=1, alt=120, seq=2), rssi_dbm=-50, mono=11.0)
    assert m.snapshot(mono=11.5).liftoff_banner       # inside the window
    assert m.snapshot(mono=13.9).liftoff_banner       # still inside
    assert not m.snapshot(mono=14.1).liftoff_banner   # expired
    # banner is for the TRANSITION: a model born mid-flight (first frame
    # already St:1) must not fabricate a liftoff moment it never saw
    m2 = HandheldModel(liftoff_banner_s=3.0)
    m2.observe(frame(st=1, alt=500, seq=9), rssi_dbm=-60, mono=20.0)
    assert not m2.snapshot(mono=20.1).liftoff_banner


def test_peak_tracks_alt_and_trusts_sled_max():
    m = HandheldModel()
    m.observe(frame(st=1, alt=100, seq=1), rssi_dbm=-50, mono=1.0)
    m.observe(frame(st=1, alt=250, seq=2), rssi_dbm=-50, mono=2.0)
    m.observe(frame(st=1, alt=180, seq=3), rssi_dbm=-50, mono=3.0)
    assert m.snapshot(mono=3.1).peak_ft == 250
    # the sled's own Max is authoritative when it exceeds what we saw
    # (RF loss can hide the true peak from the handheld)
    m.observe(frame(st=2, alt=170, maxft=310, seq=4), rssi_dbm=-50, mono=4.0)
    assert m.snapshot(mono=4.1).peak_ft == 310


def test_apogee_reveal_on_descent_and_it_latches():
    m = HandheldModel()
    m.observe(frame(st=1, alt=400, seq=1), rssi_dbm=-50, mono=1.0)
    assert not m.snapshot(mono=1.1).apogee_reveal
    m.observe(frame(st=2, alt=390, maxft=412, seq=2), rssi_dbm=-50, mono=2.0)
    v = m.snapshot(mono=2.1)
    assert v.apogee_reveal
    assert v.peak_ft == 412
    # stays revealed for the rest of the flight
    m.observe(frame(st=2, alt=200, maxft=412, seq=3), rssi_dbm=-50, mono=30.0)
    assert m.snapshot(mono=30.1).apogee_reveal


def test_stale_after_quiet_gap_keeps_last_data_and_reports_age():
    m = HandheldModel(stale_s=5.0)
    m.observe(frame(st=1, alt=300, seq=1), rssi_dbm=-55, mono=10.0)
    assert m.snapshot(mono=14.9).mode == "live"
    v = m.snapshot(mono=15.1)
    assert v.mode == "stale"
    assert v.alt_ft == 300          # last data retained, not blanked
    assert v.age_s == 5.1
    # a new frame recovers to live
    m.observe(frame(st=1, alt=320, seq=2), rssi_dbm=-58, mono=16.0)
    assert m.snapshot(mono=16.1).mode == "live"


def test_foreign_sys_is_ignored_but_counted():
    m = HandheldModel()
    pkt = decode(b"V:1 SYS:3 SRC:1 SEQ:5 St:1 ALT:999ft")
    assert pkt.ok
    m.observe(pkt, rssi_dbm=-40, mono=1.0)
    v = m.snapshot(mono=1.1)
    assert v.mode == "idle"          # nothing accepted
    assert v.alt_ft is None
    assert m.foreign_sys == 1        # ...and the drop is visible, not silent
