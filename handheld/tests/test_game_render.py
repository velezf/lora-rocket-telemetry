"""Game display integration (Epic 8.4): render(view, game=...)."""
from handheld.app.game import GuessGame


def game(**kw):
    g = GuessGame(**kw)
    g.press_lock(mono=0.0)               # past the startup rules screen
    return g
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
    g = game(start_ft=300)
    for view in (V(), IDLE()):
        plain = render(view)
        entry = render(view, game=g)
        assert plain.tobytes() != entry.tobytes()
    # the VALUE is displayed: a different dial renders differently
    g2 = game(start_ft=475)
    assert render(V(), game=g).tobytes() != render(V(), game=g2).tobytes()


def test_watching_phase_stops_overlaying_the_dial():
    g = game()
    g.press_lock(mono=1.0)
    g.press_lock(mono=2.0)
    g.on_view(V(st=1))
    assert g.phase == "watching"
    inflight = V(st=1, alt_ft=250, peak_ft=250)
    assert render(inflight, game=g).tobytes() == render(inflight).tobytes()


def test_reveal_shows_the_winner():
    g = game()
    g.press_up(mono=1.0)                  # Bacon dials 325, banks at liftoff
    g.on_view(V(st=1))
    reveal_view = V(st=2, apogee_reveal=True, alt_ft=100, peak_ft=412)
    g.on_view(reveal_view)
    assert g.winner == ("Bacon", 325)
    with_winner = render(reveal_view, game=g)
    without = render(reveal_view)
    assert with_winner.tobytes() != without.tobytes()
    # and a no-players game reveals exactly the plain apogee screen
    g_empty = game()
    g_empty.on_view(reveal_view)
    assert render(reveal_view, game=g_empty).tobytes() == without.tobytes()


def test_confirm_screen_differs_from_dialing():
    g_dial = game()
    g_ok = game()
    g_ok.press_lock(mono=1.0)             # sitting at "Bacon 300 OK?"
    assert g_ok.confirming
    v = V()
    assert render(v, game=g_dial).tobytes() != render(v, game=g_ok).tobytes()


def test_rssi_still_rendered_during_entry():
    g = game()
    with_rssi = render(V(rssi_dbm=-50.0), game=g)
    without = render(V(rssi_dbm=None), game=g)
    assert with_rssi.tobytes() != without.tobytes()   # moved, not dropped


def test_rules_screen_shows_and_toggles():
    raw = GuessGame()                     # startup: rules screen
    v = IDLE()
    closest = render(v, game=raw)
    raw.press_up(mono=1.0)                # toggle to NoOver
    noover = render(v, game=raw)
    assert closest.tobytes() != noover.tobytes()
    confirmed = game()                    # past the menu: entry screen
    assert render(v, game=confirmed).tobytes() != closest.tobytes()


def test_armed_screen_acknowledges_locked_guesses():
    g = game(players=("Bacon", "Dragon"))
    g.press_lock(mono=1.0); g.press_lock(mono=2.0)   # Bacon in
    g.press_lock(mono=3.0); g.press_lock(mono=4.0)   # Dragon in -> armed
    assert g.armed
    v = V()
    armed = render(v, game=g)
    assert armed.tobytes() != render(v).tobytes()     # not the plain pad page
    g2 = game(players=("Bacon", "Dragon"))            # menu vs armed differ too
    assert armed.tobytes() != render(v, game=g2).tobytes()
