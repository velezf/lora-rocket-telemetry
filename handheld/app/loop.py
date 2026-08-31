"""The two loop bodies (Epic 8.2 slice 4): RX step and render tick.

Pure orchestration over injected objects — the threads and hardware
construction live in main.py. Both steps survive their fault domain's
failures by counting them (LoopCounters), never by raising: a display
fault must not stop telemetry capture, and a radio fault must not kill
the display heartbeat (the ground station's two-surfaces lesson).
"""
from __future__ import annotations

from dataclasses import dataclass

from handheld.app.render import render
from handheld.app.rx import handle_payload


@dataclass
class LoopCounters:
    render_errors: int = 0
    rx_errors: int = 0
    battery_errors: int = 0


def battery_tick(model, reader, mono: float, counters) -> None:
    """Poll the gauge once (reader: () -> int|None). Never raises — a dead
    pisugar-server must not touch telemetry or the display."""
    try:
        model.set_battery(reader(), mono)
    except Exception:
        counters.battery_errors += 1


def rx_step(radio, model, mono: float, rx_counters, counters) -> None:
    """Poll the radio once; fold any payload into the model. Never raises."""
    try:
        payload = radio.receive(with_header=False, timeout=0.5)
    except Exception:
        counters.rx_errors += 1
        return
    if payload is None:
        return
    handle_payload(model, bytes(payload), rssi_dbm=float(radio.last_rssi),
                   mono=mono, counters=rx_counters)


def render_tick(model, display, mono: float, counters, game=None) -> None:
    """Snapshot -> (game transitions) -> render -> show, unconditionally.

    Runs even with no new data — a quiet pad must not look dead — and
    the display's recovery preamble rides every frame (see oled.py).
    The game watches the same snapshot the display shows (one truth).
    """
    try:
        view = model.snapshot(mono)
        if game is not None:
            game.on_view(view)
        display.show(render(view, game))
    except Exception:
        counters.render_errors += 1
