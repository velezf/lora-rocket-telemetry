"""Pi-only front-panel LED supervisor (apogee-panel).

Owns ALL SIX front-panel LEDs and drives them from the pure policy in ground/panel/{leds,
supervisor}.py — ingest is only a state source (the /run heartbeat file). Fail-closed: a
missing/stale heartbeat -> RED (not recording), so the invisible fail-closed gate is visible
without a screen. Runs at 8 Hz so FAST/SLOW blinks stay distinct. A power-on lamp sweep (pure
plan in leds.py) lights all six at once for dead-LED detection, then marches them in the
believed physical L->R order — so a correct LED_GPIO map reads as a clean march and a wrong one
shows a visible out-of-order jump, which is what pins the per-position GPIOs.

Raw lgpio (active-high) — the SAME single GPIO story as the RX transport (ADR 0002); no second
GPIO abstraction on the box, which the Epic 8 handheld inherits. Hardware glue, NOT host-tested
(like restore_clock.py); the judgement lives in the host-tested pure modules. Runs as rocketman
(in the gpio group); reads pisugar over localhost.
"""
import os
import json
import signal
import socket
import subprocess
import time
from datetime import datetime, timezone

import lgpio   # pyright: ignore[reportMissingImports]  # Pi-only dep

from ground.panel.leds import led_states, lamp_sweep_plan, lamp_test_order
from ground.panel.supervisor import supervisor_state, is_lit, TICKS_PER_SEC
from ground.panel.heartbeat import STATE_PATH

MARKER = "/run/apogee-rtc-restored"
GPIOCHIP = 0   # matches ground/rx/transport.py (RESET GPIO25); Pi 5 header GPIOs

# Colors are FIXED by the harness (GPIO 5/6/13 green, 26 red, 12/16 blue). The per-position
# function assignment (which green is flight-open, which blue is clock, ...) is PROVISIONAL
# until the power-on lamp sweep resolves physical L->R; then this map + the wiring doc's
# reversed order get corrected together.
LED_GPIO = {"RED": 26, "G_ALIVE": 5, "G_RX": 6, "G_FLIGHT": 13, "B_CLOCK": 12, "B_RF": 16}
COLOR = {5: "green", 6: "green", 13: "green", 26: "red", 12: "blue", 16: "blue"}


def _log(msg):
    print(f"[panel] {msg}", flush=True)


def read_state():
    """Ingest heartbeat file -> dict, or None (missing/unreadable/corrupt -> fail-closed down)."""
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_battery():
    try:
        with socket.create_connection(("127.0.0.1", 8423), 1.0) as s:
            s.sendall(b"get battery\n")
            reply = s.recv(128).decode(errors="replace")
        for line in reply.splitlines():
            if line.startswith("battery:"):
                return float(line.split(":", 1)[1])
    except (OSError, ValueError):
        return None
    return None


def read_provenance():
    # Marker present -> clock established (RTC-restore OR attest). Distinguishing attested needs
    # the marker to carry its reason (see RESUME "Panel signals designed but INERT"); for now
    # present -> rtc, absent -> unknown.
    return "rtc" if os.path.exists(MARKER) else "unknown"


def read_shutting_down():
    try:
        out = subprocess.run(["systemctl", "is-system-running"],
                             capture_output=True, text=True, timeout=1)
        return out.stdout.strip() == "stopping"
    except (OSError, subprocess.SubprocessError):
        return False


def lamp_sweep(chip):
    """Execute the pure lamp_sweep_plan() verbatim — the order and pacing are decided and
    tested in ground/panel/leds.py, not here. This function is only GPIO writes and sleeps.

    The march runs in the order we BELIEVE is physical left->right, so a correct LED_GPIO
    map looks like a clean L->R march and a wrong one shows a visible out-of-order jump.
    Each step is logged with its GPIO + color so the journal can be read back against what
    the operator saw."""
    _log("lamp test — all six together first (dead-LED check), then a L->R march, twice.")
    for lit, secs in lamp_sweep_plan():
        if len(lit) == 1:
            name = lit[0]
            _log(f"  expect position {lamp_test_order().index(name) + 1}/6 — "
                 f"{COLOR[LED_GPIO[name]]} (GPIO{LED_GPIO[name]}, logical {name})")
        elif lit:
            _log(f"  all {len(lit)} LEDs on — any dark one is dead")
        for name, gpio in LED_GPIO.items():
            lgpio.gpio_write(chip, gpio, 1 if name in lit else 0)
        time.sleep(secs)
    _log("lamp test done — report the observed left->right color sequence per position.")


def main():
    chip = lgpio.gpiochip_open(GPIOCHIP)
    for gpio in LED_GPIO.values():
        lgpio.gpio_claim_output(chip, gpio, 0)      # active-high output, initial off

    stop = {"v": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("v", True))
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("v", True))

    try:
        lamp_sweep(chip)
        _log(f"supervisor up — {TICKS_PER_SEC} Hz, state={STATE_PATH}")

        tick = 0
        battery = None
        shutting = False
        provenance = "unknown"
        period = 1.0 / TICKS_PER_SEC
        while not stop["v"]:
            now = datetime.now(timezone.utc)
            if tick % TICKS_PER_SEC == 0:            # slow-changing polls at ~1 Hz
                battery = read_battery()
                shutting = read_shutting_down()
                provenance = read_provenance()
            raw = read_state()
            bug_log = _log if tick % TICKS_PER_SEC == 0 else None   # rate-limit tz-bug log ~1 Hz
            st = supervisor_state(raw, now, battery_pct=battery,
                                  clock_provenance=provenance, shutting_down=shutting, log=bug_log)
            for name, blink in led_states(st).items():
                lgpio.gpio_write(chip, LED_GPIO[name], 1 if is_lit(blink, tick) else 0)
            tick += 1
            time.sleep(period)
    finally:
        for gpio in LED_GPIO.values():               # clean exit — don't freeze LEDs lit
            lgpio.gpio_write(chip, gpio, 0)
        lgpio.gpiochip_close(chip)
        _log("supervisor stopped")


if __name__ == "__main__":
    main()
