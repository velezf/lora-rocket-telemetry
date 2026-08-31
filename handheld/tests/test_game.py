"""Guess-the-apogee (Epic 8.4): pure game logic.

Three buttons: up/down dial the guess, lock banks it and hands the dial to
the next kid. Liftoff closes the betting window; the apogee reveal names
the winner. Time is injected; debounce lives HERE (pure, testable) so the
GPIO glue stays a dumb edge-poller.
"""
from handheld.app.game import GuessGame
from handheld.app.viewmodel import View


def game(**kw):
    """A GuessGame taken past the startup rules screen (confirmed at t=0)."""
    g = GuessGame(**kw)
    g.press_lock(mono=0.0)
    return g


def lock(g, mono):
    """A completed lock is TWO presses (ask, then confirm), debounce-spaced."""
    g.press_lock(mono=mono)
    g.press_lock(mono=mono + 0.2)


def V(**kw):
    base = dict(mode="live", alt_ft=0, peak_ft=0, st=0, rssi_dbm=-50.0,
                age_s=0.1, liftoff_banner=False, apogee_reveal=False,
                battery_pct=None)
    base.update(kw)
    return View(**base)


def test_dialing_and_clamping():
    g = game(step_ft=25, start_ft=300)
    assert g.phase == "entry"
    assert g.current_guess == 300
    g.press_up(mono=1.0)
    g.press_up(mono=2.0)
    assert g.current_guess == 350
    g.press_down(mono=3.0)
    assert g.current_guess == 325
    for i in range(30):
        g.press_down(mono=4.0 + i)
    assert g.current_guess == 0          # clamped, never negative


def test_debounce_counts_rapid_presses_once():
    g = game(step_ft=25, start_ft=300, debounce_s=0.15)
    g.press_up(mono=1.00)
    g.press_up(mono=1.05)                # bounce — ignored
    g.press_up(mono=1.30)                # real second press
    assert g.current_guess == 350


def test_lock_banks_guess_and_prompts_the_next_kid_by_name():
    g = game(start_ft=300)               # default roster: Bacon, HnyBsct, Dragon
    assert g.entering_name == "Bacon"
    g.press_up(mono=1.0)                 # Bacon dials 325
    lock(g, 2.0)
    assert g.guesses == [325]
    assert g.entering_name == "HnyBsct"  # next kid prompted by name
    assert g.current_guess == 325        # dial starts where Bacon left it
    g.press_down(mono=3.0)
    lock(g, 4.0)
    assert g.entering_name == "Dragon"
    assert g.guesses == [325, 300]


def test_roster_end_closes_entry():
    g = game(players=("Bacon", "Dragon"))
    lock(g, 1.0)
    lock(g, 2.0)
    assert g.phase == "watching"         # every kid seated
    g.press_up(mono=3.0)                 # dead button
    assert g.guesses == [300, 300]


def test_liftoff_closes_the_betting_window():
    g = game()
    g.press_up(mono=1.0)                 # Bacon dialing 325, never locked
    g.on_view(V(st=1, liftoff_banner=True))
    assert g.phase == "watching"
    assert g.guesses == [325]            # an un-locked dial banks at liftoff
    g.press_up(mono=2.0)                 # too late
    assert g.guesses == [325]


def test_reveal_names_the_closest_and_ties_go_to_the_earlier_kid():
    g = game()
    lock(g, 1.0)                         # Bacon: 300
    g.press_up(mono=2.0); g.press_up(mono=3.0); g.press_up(mono=4.0)
    lock(g, 5.0)                         # HnyBsct: 375
    g.on_view(V(st=1))
    g.on_view(V(st=2, apogee_reveal=True, peak_ft=412))
    assert g.phase == "reveal"
    assert g.winner == ("HnyBsct", 375)  # |375-412| < |300-412|
    # tie case: two equal distances -> the earlier kid in the roster
    g2 = game()
    lock(g2, 1.0)                        # Bacon: 300
    lock(g2, 2.0)                        # HnyBsct: 300
    g2.on_view(V(st=2, apogee_reveal=True, peak_ft=350))
    assert g2.winner == ("Bacon", 300)


def test_no_players_no_winner():
    g = game()
    g.on_view(V(st=1))                   # nobody touched a button
    g.on_view(V(st=2, apogee_reveal=True, peak_ft=400))
    assert g.guesses == []
    assert g.winner is None


def test_render_tick_drives_game_from_the_displayed_snapshot():
    from ground.decode.v1 import decode

    from handheld.app.loop import LoopCounters, render_tick
    from handheld.app.viewmodel import HandheldModel

    class NullDisplay:
        def show(self, img):
            pass

    m = HandheldModel()
    g = game()
    g.press_up(mono=0.5)                 # a kid dialed
    m.observe(decode(b"V:1 SYS:7 SRC:1 SEQ:1 St:0 ALT:5ft"), -50.0, 1.0)
    m.observe(decode(b"V:1 SYS:7 SRC:1 SEQ:2 St:1 ALT:120ft"), -50.0, 2.0)
    render_tick(m, NullDisplay(), mono=2.1, counters=LoopCounters(), game=g)
    assert g.phase == "watching"         # liftoff seen through the same snapshot
    assert g.guesses == [325]


def test_next_flight_resets_game_to_fresh_entry():
    g = game()
    lock(g, 1.0)
    g.on_view(V(st=2, apogee_reveal=True, peak_ft=400))
    assert g.phase == "reveal"
    # sled power-cycled for the next launch: pad frames again -> back to
    # the rules screen (the round restarts from the game pick)
    g.on_view(V(st=0, apogee_reveal=False, peak_ft=0))
    assert g.phase == "rules"
    assert g.guesses == [] and g.winner is None


def test_no_over_rule_is_price_is_right():
    g = game(rule="no-over")
    lock(g, 1.0)                                  # Bacon: 300
    g.press_up(mono=2.0); g.press_up(mono=3.0)
    g.press_up(mono=4.0); g.press_up(mono=5.0)
    lock(g, 6.0)                                  # HnyBsct: 400
    g.on_view(V(st=2, apogee_reveal=True, peak_ft=390))
    # 400 is CLOSER (10 vs 90) but busted: under-only wins
    assert g.winner == ("Bacon", 300)


def test_no_over_rule_everyone_busts_nobody_wins():
    g = game(rule="no-over")
    g.press_up(mono=1.0)                          # Bacon: 325
    lock(g, 2.0)
    g.press_up(mono=3.0)                          # HnyBsct: 350
    lock(g, 4.0)
    g.on_view(V(st=2, apogee_reveal=True, peak_ft=200))
    assert g.phase == "reveal"
    assert g.winner is None                       # the rocket wins


def test_exact_guess_wins_under_both_rules():
    for rule in ("closest", "no-over"):
        g = game(rule=rule)
        lock(g, 1.0)                              # Bacon: 300
        g.on_view(V(st=2, apogee_reveal=True, peak_ft=300))
        assert g.winner == ("Bacon", 300), rule


def test_lock_requires_a_confirm_press():
    g = game()
    g.press_up(mono=1.0)                 # Bacon dials 325
    g.press_lock(mono=2.0)               # first press: asks, banks NOTHING
    assert g.confirming
    assert g.guesses == []
    assert g.entering_name == "Bacon"
    g.press_lock(mono=3.0)               # second press: banked
    assert not g.confirming
    assert g.guesses == [325]
    assert g.entering_name == "HnyBsct"


def test_dialing_cancels_the_confirm():
    g = game()
    g.press_lock(mono=1.0)               # "Bacon 300 OK?"
    assert g.confirming
    g.press_up(mono=2.0)                 # no — more altitude
    assert not g.confirming
    assert g.current_guess == 325
    assert g.guesses == []               # nothing banked by the detour


def test_liftoff_banks_even_mid_confirm():
    g = game()
    g.press_up(mono=1.0)
    g.press_lock(mono=2.0)               # sitting at "Bacon 325 OK?"
    g.on_view(V(st=1, liftoff_banner=True))
    assert g.guesses == [325]            # the countdown answered for them
    assert g.phase == "watching"


def test_startup_asks_which_game_first():
    g = GuessGame()                      # raw: nobody confirmed a rule yet
    assert g.phase == "rules"
    assert g.rule == "closest"           # the RULE knob is the preselection
    g.press_up(mono=1.0)                 # dial toggles the choice
    assert g.rule == "no-over"
    g.press_down(mono=2.0)
    assert g.rule == "closest"
    g.press_lock(mono=3.0)               # confirm -> guessing begins
    assert g.phase == "entry"
    assert g.entering_name == "Bacon"


def test_liftoff_during_rules_screen_skips_the_game():
    g = GuessGame()
    g.on_view(V(st=1, liftoff_banner=True))
    assert g.phase == "watching"
    assert g.guesses == []


def test_next_flight_returns_to_the_rules_screen():
    g = game()
    lock(g, 1.0)
    g.on_view(V(st=2, apogee_reveal=True, peak_ft=400))
    g.on_view(V(st=0, apogee_reveal=False, peak_ft=0))
    assert g.phase == "rules"
