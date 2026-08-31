"""Handheld receiver entry point (Epic 8.2) — hardware construction + threads.

Runs ONLY on the Zero (Blinka). Everything with logic lives in the tested
modules; this file is deliberately thin glue, same posture as the ground
station's service shims. Run from the repo checkout:

    cd ~/lora-rocket-telemetry && ~/radio/.venv/bin/python -m handheld.app.main

Wiring facts are cited, not restated: bonnet CS/RESET pins per ~/radio's
radio_check.py (CE1/D25 — CE1 freed by the spi0-1cs overlay in
/boot/firmware/config.txt), OLED 128x32 @ 0x3C per handheld/README.md.
"""
from __future__ import annotations

import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ground.rx.sx127x import LoRaConfig

from handheld.app.battery import read_battery_pct
from handheld.app.loop import LoopCounters, battery_tick, render_tick, rx_step
from handheld.app.oled import HeartbeatDisplay
from handheld.app.rx import RxCounters, apply_settings
from handheld.app.viewmodel import HandheldModel

RENDER_PERIOD_S = 1.0
BATTERY_EVERY_TICKS = 30   # gauge poll cadence: every 30 render ticks (~30 s)


def build_radio(cfg: LoRaConfig):
    import adafruit_rfm9x
    import board
    import busio
    import digitalio

    cs = digitalio.DigitalInOut(board.CE1)
    reset = digitalio.DigitalInOut(board.D25)
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    radio = adafruit_rfm9x.RFM9x(spi, cs, reset, cfg.freq_hz / 1_000_000)
    apply_settings(radio, cfg)
    return radio


def build_display():
    import adafruit_ssd1306
    import board

    return HeartbeatDisplay(
        adafruit_ssd1306.SSD1306_I2C(128, 32, board.I2C(), addr=0x3C))


def main() -> int:
    cfg = LoRaConfig()
    radio = build_radio(cfg)
    display = build_display()
    model = HandheldModel()
    rx_counters, counters = RxCounters(), LoopCounters()
    stop = threading.Event()

    def render_loop():
        tick = 0
        while not stop.is_set():
            if tick % BATTERY_EVERY_TICKS == 0:
                battery_tick(model, read_battery_pct, time.monotonic(), counters)
            render_tick(model, display, time.monotonic(), counters)
            tick += 1
            stop.wait(RENDER_PERIOD_S)

    t = threading.Thread(target=render_loop, name="render", daemon=True)
    t.start()

    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    print(f"[handheld] listening {cfg.freq_hz/1e6:.1f} MHz "
          f"SF{cfg.spreading_factor} BW{cfg.bandwidth_khz:.0f}", flush=True)
    while not stop.is_set():
        rx_step(radio, model, time.monotonic(), rx_counters, counters)

    t.join(timeout=2.0)
    print(f"[handheld] stopped: accepted={rx_counters.accepted} "
          f"decode_errors={rx_counters.decode_errors} "
          f"foreign_sys={model.foreign_sys} rx_errors={counters.rx_errors} "
          f"render_errors={counters.render_errors} "
          f"battery_errors={counters.battery_errors}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
