"""RocketLab data tables — KID-TWEAKABLE (add your rocket / motor here).

Approximate catalog + NAR-certification numbers, curated small on purpose
(RESUME 2026-08-31). The motor CODE is display only: the classic Estes
codes overstate average thrust (an A8 certifies near 3 N, not 8), so the
physics columns carry certified-ish values and the code is just a name.
Names must stay <= 8 chars to fit the OLED list screen.
"""
from __future__ import annotations

# (name, dry mass g — no motor, body diameter mm)
ROCKETS = (
    ("Viking", 17, 19),
    ("Wizard", 22, 19),
    ("Alpha", 34, 25),
    ("Crossfir", 40, 25),
    ("BigBerth", 62, 41),
    # The fleet's real bird (with the telemetry sled aboard) — 859 ft on an
    # F15, 2026-08-25. Dry mass WEIGHED by Frank 2026-08-31 (~432 g); the
    # flight's own physics independently agreed (Vel max 201 ft/s vs the
    # F15's impulse -> ~0.5 kg average flying mass).
    ("Katana", 432, 34),
)

# (code, total impulse Ns, certified avg thrust N, propellant g, motor mass g)
MOTORS = (
    ("A8", 2.5, 3.2, 3.3, 16.4),
    ("B6", 5.0, 4.3, 5.6, 18.3),
    ("C6", 10.0, 4.7, 10.8, 24.0),
    ("D12", 20.0, 10.2, 21.1, 42.6),
    ("E12", 30.0, 10.8, 35.8, 57.0),
    ("F15", 49.6, 14.8, 60.0, 102.0),
)


def rocket(name: str):
    return next(r for r in ROCKETS if r[0] == name)


def motor(code: str):
    return next(m for m in MOTORS if m[0] == code)
