"""OLED display shell (Pi-only): luma.oled SSD1306 at I2C 0x3d (per the wiring doc).

Shares I2C-1 read-only with the PiSugar (0x57) — no bus contention (the radio is on
SPI). The ssd1306 constructor probes the address, so a missing/misconfigured display
fails at construction and the caller degrades silently. Every draw swallows I/O errors
so the OLED can never crash the radio owner.
"""
OLED_ADDR = 0x3D


class OledDisplay:
    def __init__(self, addr: int = OLED_ADDR, i2c_port: int = 1):
        from luma.core.interface.serial import i2c   # pyright: ignore[reportMissingImports]  # Pi-only
        from luma.oled.device import ssd1306          # pyright: ignore[reportMissingImports]  # Pi-only
        self._device = ssd1306(i2c(port=i2c_port, address=addr), width=128, height=64)

    def show(self, lines):
        try:
            from luma.core.render import canvas       # pyright: ignore[reportMissingImports]  # Pi-only
            with canvas(self._device) as draw:
                for i, line in enumerate(lines[:4]):
                    draw.text((0, i * 16), str(line)[:21], fill="white")
        except Exception:
            pass    # OLED I/O failures degrade silently — never crash the radio owner
