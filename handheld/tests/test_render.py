"""Layout renderer for the handheld's 128x32 SSD1306 (Epic 8.2).

Behavioral tests, not golden images (goldens were an explicitly deferred
branch of the ground OLED redesign — same posture here). The properties:
right geometry, deterministic output, every mode visibly distinct, and the
idle page is never a dead-black screen — the 2026-07-30 ground defect was
precisely a quiet pad rendering as nothing.
"""
from handheld.app.render import render
from handheld.app.viewmodel import View


def V(**kw):
    base = dict(mode="live", alt_ft=1234, peak_ft=1500, st=1, rssi_dbm=-52.0,
                age_s=0.4, liftoff_banner=False, apogee_reveal=False)
    base.update(kw)
    return View(**base)


def lit(img):
    return sum(1 for p in img.getdata() if p)


def test_geometry_and_mode():
    img = render(V())
    assert img.size == (128, 32)
    assert img.mode == "1"


def test_deterministic():
    assert render(V()).tobytes() == render(V()).tobytes()


def test_idle_page_is_not_dead_black():
    img = render(View("idle", None, None, None, None, None, False, False))
    assert lit(img) > 50   # a quiet pad must LOOK alive


def test_live_shows_data_and_tracks_altitude():
    a = render(V(alt_ft=100))
    b = render(V(alt_ft=9900))
    assert lit(a) > 50
    assert a.tobytes() != b.tobytes()


def test_liftoff_banner_dominates():
    quiet = render(V())
    banner = render(V(liftoff_banner=True))
    assert banner.tobytes() != quiet.tobytes()
    # the banner is the kid moment: visually loud — much more lit area
    # than the normal live page (inverted field)
    assert lit(banner) > lit(quiet) * 2


def test_stale_differs_from_live_with_same_data():
    live = render(V(mode="live", age_s=0.2))
    stale = render(V(mode="stale", age_s=42.0))
    assert live.tobytes() != stale.tobytes()


def test_apogee_reveal_differs_and_shows_peak():
    up = render(V(st=1))
    reveal = render(V(st=2, apogee_reveal=True, alt_ft=300, peak_ft=412))
    assert reveal.tobytes() != up.tobytes()
    # peak value changes the revealed screen (it is actually displayed)
    reveal2 = render(V(st=2, apogee_reveal=True, alt_ft=300, peak_ft=999))
    assert reveal.tobytes() != reveal2.tobytes()
