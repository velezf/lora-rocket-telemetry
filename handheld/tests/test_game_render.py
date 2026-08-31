"""Game display integration (Epic 8.4): render(view, game=...)."""
from handheld.app.game import GuessGame
from handheld.app.render import render
from handheld.app.viewmodel import View


def V(**kw):
    base = dict(mode="live", alt_ft=0, peak_ft=0, st=0, rssi_dbm=-50.0,
                age_s=0.1, liftoff_banner=False, apogee_reveal=False,
                battery_pct=None)
    base.update(kw)
    return View(**base)


def IDLE(**kw):
    base = dict(mode="idle", alt_ft=None, peak_ft=None, st=None, rssi_dbm=None,
                age_s=None, liftoff_banner=False, apogee_reveal=False,
                battery_pct=None)
    base.update(kw)
    return View(**base)


def test_no_game_renders_exactly_as_before():
    assert render(V()).tobytes() == render(V(), game=None).tobytes()


def test_entry_overlay_shows_the_dial_on_pad_and_idle():
    g = GuessGame(start_ft=300)
    for view in (V(), IDLE()):
        plain = render(view)
        entry = render(view, game=g)
        assert plain.tobytes() != entry.tobytes()
    # the VALUE is displayed: a different dial renders differently
    g2 = GuessGame(start_ft=475)
    assert render(V(), game=g).tobytes() != render(V(), game=g2).tobytes()


def test_watching_phase_stops_overlaying_the_dial():
    g = GuessGame()
    g.press_lock(mono=1.0)
    g.on_view(V(st=1))
    assert g.phase == "watching"
    inflight = V(st=1, alt_ft=250, peak_ft=250)
    assert render(inflight, game=g).tobytes() == render(inflight).tobytes()


def test_reveal_shows_the_winner():
    g = GuessGame()
    g.press_up(mono=1.0)                  # Bacon dials 325, banks at liftoff
    g.on_view(V(st=1))
    reveal_view = V(st=2, apogee_reveal=True, alt_ft=100, peak_ft=412)
    g.on_view(reveal_view)
    assert g.winner == ("Bacon", 325)
    with_winner = render(reveal_view, game=g)
    without = render(reveal_view)
    assert with_winner.tobytes() != without.tobytes()
    # and a no-players game reveals exactly the plain apogee screen
    g_empty = GuessGame()
    g_empty.on_view(reveal_view)
    assert render(reveal_view, game=g_empty).tobytes() == without.tobytes()
