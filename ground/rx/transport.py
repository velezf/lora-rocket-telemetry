"""Hardware SPI transport for SX127xRx on a Raspberry Pi (spidev + lgpio).

Kept out of sx127x.py so the driver logic stays host-testable: spidev and lgpio
are imported lazily inside __init__, only when talking to real hardware. Defaults
match docs/ground-station-wiring.md — radio on SPI0/CE1, RESET on GPIO25.
"""
from __future__ import annotations

import time


class SpidevLgpioTransport:
    def __init__(self, spi_bus: int = 0, spi_cs: int = 1, reset_gpio: int = 25,
                 max_speed_hz: int = 1_000_000, gpiochip: int = 0):
        import spidev  # pyright: ignore[reportMissingImports]  # Pi-only dep
        import lgpio  # pyright: ignore[reportMissingImports]  # Pi-only dep
        self._lgpio = lgpio
        self._reset_gpio = reset_gpio
        self._h = lgpio.gpiochip_open(gpiochip)
        lgpio.gpio_claim_output(self._h, reset_gpio, 1)
        self._spi = spidev.SpiDev()
        self._spi.open(spi_bus, spi_cs)
        self._spi.max_speed_hz = max_speed_hz
        self._spi.mode = 0

    def transfer(self, data):
        return self._spi.xfer2(list(data))

    def reset(self) -> None:
        self._lgpio.gpio_write(self._h, self._reset_gpio, 0)
        time.sleep(0.01)
        self._lgpio.gpio_write(self._h, self._reset_gpio, 1)
        time.sleep(0.01)

    def close(self) -> None:
        self._spi.close()
        self._lgpio.gpiochip_close(self._h)
