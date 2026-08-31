"""RocketLab sim core (3rd game): deterministic 1-DOF apogee predictor.

The sim is the game's SINGLE answer authority (RESUME 2026-08-31:
consistency beats accuracy). Tests use independent evidence where physics
offers it: the vacuum result must sit BELOW the closed-form energy bound
(impulse -> velocity, ignore gravity loss) and above a sane fraction of it
— a bracket the sim cannot satisfy by construction alone.
"""
from handheld.app.rockets import MOTORS, ROCKETS, motor, rocket
from handheld.app.rocketsim import apogee_ft

G = 9.81


def test_tables_are_well_formed():
    assert len(ROCKETS) >= 6 and len(MOTORS) >= 6
    for name, dry_g, diam_mm in ROCKETS:
        assert len(name) <= 8            # fits the OLED
        assert 5 < dry_g < 500 and 10 < diam_mm < 80
    codes = [m[0] for m in MOTORS]
    assert codes == sorted(codes, key=lambda c: "ABCDEF".index(c[0]))
    for code, impulse, avg_n, prop_g, motor_g in MOTORS:
        assert impulse > 0 and avg_n > 0 and 0 < prop_g < motor_g


def test_deterministic():
    assert apogee_ft(rocket("Alpha"), motor("C6")) == apogee_ft(
        rocket("Alpha"), motor("C6"))


def test_bigger_motor_flies_higher():
    r = rocket("Alpha")
    alts = [apogee_ft(r, motor(c)) for c in ("A8", "B6", "C6")]
    assert alts[0] < alts[1] < alts[2]


def test_heavier_rocket_flies_lower():
    m = motor("C6")
    light = min(ROCKETS, key=lambda r: r[1])
    heavy = max(ROCKETS, key=lambda r: r[1])
    assert apogee_ft(heavy, m) < apogee_ft(light, m)


def test_drag_costs_altitude():
    r, m = rocket("Alpha"), motor("C6")
    assert apogee_ft(r, m, cd=0.0) > apogee_ft(r, m)


def test_vacuum_sim_sits_inside_the_closed_form_bracket():
    # closed form (impulse -> velocity on the average total mass, no drag,
    # no gravity loss): an UPPER bound the sim must respect; and a real
    # burn cannot lose more than ~half of it for these thrust/weight ratios
    r, m = rocket("Alpha"), motor("C6")
    _, impulse, _, prop_g, motor_g = m
    mass_avg = (r[1] + motor_g - prop_g / 2) / 1000.0
    v = impulse / mass_avg
    bound_ft = (v * v / (2 * G)) * 3.28084
    got = apogee_ft(r, m, cd=0.0)
    assert got < bound_ft
    assert got > 0.5 * bound_ft


def test_a_rocket_the_motor_cannot_lift_stays_on_the_pad():
    impossible = ("Brick", 5000, 25)     # 5 kg on an A8
    assert apogee_ft(impossible, motor("A8")) == 0


def test_the_real_bird_lands_in_a_believable_band():
    # Katana Jr flew 859 ft AGL on an F15 (2026-08-25, measured). The sim
    # is a game, not a range-safety tool — but it should land in the same
    # county: 0.5x-2x of the measured flight.
    got = apogee_ft(rocket("Katana"), motor("F15"))
    assert 430 < got < 1720, got
