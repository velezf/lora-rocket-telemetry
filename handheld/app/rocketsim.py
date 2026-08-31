"""RocketLab 1-DOF apogee sim — the game's single answer authority.

Deliberately simple and deterministic: vertical flight, average thrust over
the certified burn time, linear propellant burn-off, quadratic drag. Not a
range-safety tool — a consistent referee for a guessing game (RESUME
2026-08-31: consistency beats accuracy).

KID-TWEAKABLE KNOBS: CD (streamline your rocket!), RHO (hot day, thin air).
"""
from __future__ import annotations

import math

CD = 0.75             # blunt little sport rocket
RHO = 1.225           # kg/m^3, sea level
G = 9.81
DT = 0.005            # s
M_TO_FT = 3.28084


def apogee_ft(rocket_row, motor_row, cd: float = CD) -> int:
    """(name, dry g, diam mm) x (code, Ns, N, prop g, motor g) -> feet."""
    _, dry_g, diam_mm = rocket_row
    _, impulse, avg_n, prop_g, motor_g = motor_row

    burn_s = impulse / avg_n
    m_dry = (dry_g + motor_g - prop_g) / 1000.0    # after burnout
    m_prop = prop_g / 1000.0
    area = math.pi * (diam_mm / 2000.0) ** 2

    # can it even leave the pad? (liftoff needs thrust > weight)
    if avg_n <= (m_dry + m_prop) * G:
        return 0

    v = 0.0
    h = 0.0
    t = 0.0
    while True:
        burning = t < burn_s
        m = m_dry + (m_prop * (1.0 - t / burn_s) if burning else 0.0)
        thrust = avg_n if burning else 0.0
        drag = 0.5 * RHO * cd * area * v * v * (1 if v > 0 else -1)
        a = (thrust - drag) / m - G
        v += a * DT
        h += v * DT
        t += DT
        if not burning and v <= 0.0:
            return max(0, int(round(h * M_TO_FT)))
        if t > 120.0:                                # sim runaway guard
            return max(0, int(round(h * M_TO_FT)))
