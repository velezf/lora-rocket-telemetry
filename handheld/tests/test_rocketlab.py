"""RocketLab game flow (3rd game): menu -> rocket -> motor -> guesses -> sim reveal.

Same button grammar as everything else (#5/#6 dial, #12 confirm), dedicated
full screens (no ALT/dBm — it's an offline mode), and the decided
constraint: A REAL LIFTOFF PREEMPTS THE QUIZ.
"""
from handheld.app.game import GuessGame
from handheld.app.rockets import MOTORS, ROCKETS, motor, rocket
from handheld.app.rocketsim import apogee_ft
from handheld.app.viewmodel import View


def V(**kw):
    base = dict(mode="live", alt_ft=0, peak_ft=0, st=0, rssi_dbm=-50.0,
                age_s=0.1, liftoff_banner=False, apogee_reveal=False,
                battery_pct=None)
    base.update(kw)
    return View(**base)


def to_lab(g):
    """Cycle the startup menu to RocketLab and confirm."""
    g.press_down(mono=0.1)               # closest -> (wrap) -> RocketLab
    assert g.menu_label == "RocketLab"
    g.press_lock(mono=0.4)
    return g


def test_menu_cycles_three_games():
    g = GuessGame()
    assert g.menu_label == "Closest"
    g.press_up(mono=1.0)
    assert g.menu_label == "NoOver"
    g.press_up(mono=2.0)
    assert g.menu_label == "RocketLab"
    g.press_up(mono=3.0)
    assert g.menu_label == "Closest"     # wraps


def test_lab_flow_rocket_then_motor_then_names():
    g = to_lab(GuessGame())
    assert g.phase == "rocket"
    assert g.rocket_row == ROCKETS[0]
    g.press_up(mono=1.0)
    assert g.rocket_row == ROCKETS[1]
    g.press_down(mono=2.0)
    g.press_down(mono=3.0)
    assert g.rocket_row == ROCKETS[-1]   # wraps backwards
    g.press_lock(mono=4.0)
    assert g.phase == "motor"
    g.press_up(mono=5.0)
    assert g.motor_row == MOTORS[1]
    g.press_lock(mono=6.0)
    assert g.phase == "entry"
    assert g.entering_name == "Bacon"


def test_last_lock_reveals_the_sim_answer():
    g = to_lab(GuessGame(players=("Bacon", "Dragon")))
    g.press_lock(mono=1.0)               # rocket: ROCKETS[0]
    g.press_lock(mono=2.0)               # motor: MOTORS[0]
    expected = apogee_ft(ROCKETS[0], MOTORS[0])
    g.press_up(mono=3.0)                 # Bacon: 325
    g.press_lock(mono=4.0); g.press_lock(mono=5.0)
    g.press_lock(mono=6.0); g.press_lock(mono=7.0)   # Dragon: 325 too
    assert g.phase == "reveal"
    assert g.peak_ft == expected         # the sim IS the answer
    assert g.winner is not None
    assert g.winner[0] == "Bacon"        # tie -> earlier kid


def test_real_liftoff_preempts_the_quiz():
    g = to_lab(GuessGame())
    g.press_lock(mono=1.0)               # rocket picked
    g.press_up(mono=2.0)                 # mid motor-pick
    g.on_view(V(st=1, liftoff_banner=True))
    assert g.mode == "live"              # quiz discarded
    assert g.phase == "watching"         # the real flight owns the screen
    assert g.guesses == []


def test_chord_resets_lab_to_the_menu():
    g = to_lab(GuessGame())
    g.press_lock(mono=1.0)
    g.reset()
    assert g.phase == "rules"
    assert g.mode == "live"


def test_lab_reveal_survives_pad_frames_until_chord():
    # offline mode: pad frames must NOT reset the reveal (nobody flew)
    g = to_lab(GuessGame(players=("Bacon",)))
    g.press_lock(mono=1.0); g.press_lock(mono=2.0)
    g.press_lock(mono=3.0); g.press_lock(mono=4.0)
    assert g.phase == "reveal"
    g.on_view(V(st=0))
    assert g.phase == "reveal"           # still showing the answer


def test_lab_screens_render_and_show_the_data():
    from handheld.app.render import render

    g = to_lab(GuessGame())
    v = V()
    rocket_a = render(v, game=g)
    g.press_up(mono=1.0)                     # different rocket -> mass shown
    rocket_b = render(v, game=g)
    assert rocket_a.tobytes() != rocket_b.tobytes()
    # lab screens ignore live telemetry entirely (offline mode: no ALT/dBm)
    assert render(V(alt_ft=999, rssi_dbm=-30.0), game=g).tobytes() == \
        rocket_b.tobytes()
    g.press_lock(mono=2.0)                   # motor screen
    motor_a = render(v, game=g)
    assert motor_a.tobytes() != rocket_b.tobytes()
    g.press_lock(mono=3.0)                   # entry: named dial on lab screen
    entry = render(v, game=g)
    assert entry.tobytes() != motor_a.tobytes()


def test_lab_reveal_screen_shows_sim_number():
    from handheld.app.render import render

    g = to_lab(GuessGame(players=("Bacon",)))
    g.press_lock(mono=1.0); g.press_lock(mono=2.0)
    g.press_lock(mono=3.0); g.press_lock(mono=4.0)
    assert g.phase == "reveal"
    a = render(V(), game=g)
    # a different sim answer renders differently (the number is displayed)
    g2 = to_lab(GuessGame(players=("Bacon",)))
    g2.press_lock(mono=1.0)                  # rocket 0
    g2.press_up(mono=1.5); g2.press_up(mono=2.0)
    g2.press_lock(mono=2.5)                  # a bigger motor
    g2.press_lock(mono=3.0); g2.press_lock(mono=3.5)
    assert g2.phase == "reveal" and g2.peak_ft != g.peak_ft
    assert render(V(), game=g2).tobytes() != a.tobytes()
