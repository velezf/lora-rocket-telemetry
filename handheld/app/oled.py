"""SSD1306 display wrapper with the unconditional recovery heartbeat.

Ground lesson, encoded (docs/RESUME.md "What the OLED fix taught",
2026-08-02): a power-cycled SSD1306 comes back reset but still ACKs, so
recovery cannot be triggered — the re-init must ship with EVERY frame. And
the preamble must never contain 0xAE (display-off): that byte is cold-start
hygiene, and on the ground box it was the once-a-second visible flash.
"""
from __future__ import annotations

# Charge pump on (0x8D 0x14), horizontal addressing (0x20 0x00),
# display on (0xAF). No 0xAE — pinned by test.
SSD1306_RECOVERY_PREAMBLE = (0x8D, 0x14, 0x20, 0x00, 0xAF)


class HeartbeatDisplay:
    """Wraps a duck-typed adafruit_ssd1306 object (write_cmd/image/show)."""

    def __init__(self, ssd):
        self._ssd = ssd

    def show(self, img) -> None:
        """Preamble + frame. Raises on I/O failure — the loop counts it."""
        for b in SSD1306_RECOVERY_PREAMBLE:
            self._ssd.write_cmd(b)
        self._ssd.image(img)
        self._ssd.show()
