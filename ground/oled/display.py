"""OLED display shell (Pi-only): luma.oled SSD1306 at I2C 0x3d (per the wiring doc).

Shares I2C-1 read-only with the PiSugar (0x57) — no bus contention (the radio is on
SPI). The ssd1306 constructor probes the address, so a missing/misconfigured display
fails at construction and the caller degrades silently. Every draw swallows I/O errors
so the OLED can never crash the radio owner.
"""
OLED_ADDR = 0x3D

# SSD1306 128x64 power-on init, re-sent before EVERY frame.
#
# WHY UNCONDITIONALLY, and why not an error check: luma sends this sequence once, at
# construction. A display that loses power mid-session (a connector reseating in transit)
# comes back RESET — display OFF, charge pump off, addressing/multiplex defaulted — but it
# still ACKs on I2C, so luma keeps writing pixels into a dark panel and NOTHING raises.
# There is no error to detect, which is why the recovery has to be unconditional rather
# than triggered. Re-sending ~1 Hz costs a few dozen bytes on a bus that is otherwise idle.
_INIT_SEQ = (
    0xAE,               # display off
    0xD5, 0x80,         # clock divide / oscillator frequency
    0xA8, 0x3F,         # multiplex ratio = 64 rows
    0xD3, 0x00,         # display offset 0
    0x40,               # start line 0
    0x8D, 0x14,         # charge pump ON  <- the one a reset display loses; without it, dark
    0x20, 0x00,         # horizontal addressing mode
    0xA1, 0xC8,         # segment remap + COM scan direction (orientation)
    0xDA, 0x12,         # COM pins configuration
    0x81, 0xCF,         # contrast
    0xD9, 0xF1,         # pre-charge period
    0xDB, 0x40,         # VCOMH deselect level
    0xA4,               # resume from RAM (not all-pixels-on)
    0xA6,               # normal (not inverted)
    0x2E,               # deactivate scroll
    0xAF,               # display ON
)


class OledDisplay:
    def __init__(self, addr: int = OLED_ADDR, i2c_port: int = 1):
        from luma.core.interface.serial import i2c   # pyright: ignore[reportMissingImports]  # Pi-only
        from luma.oled.device import ssd1306          # pyright: ignore[reportMissingImports]  # Pi-only
        self._device = ssd1306(i2c(port=i2c_port, address=addr), width=128, height=64)

    def reinit(self):
        """Re-send the power-on sequence. Safe to call every frame; swallows I/O errors."""
        try:
            self._device.command(*_INIT_SEQ)
        except Exception:
            pass    # a wedged bus must never propagate — see show_image()

    def show_image(self, image, reinit: bool = True):
        """Draw a PIL image (mode "1", 128x64). Re-inits first by default.

        Swallows everything: this runs on the RENDER thread, and the whole point of moving
        it off the RX thread is that no display fault can reach telemetry capture. A hung
        I2C write blocks only this thread; the radio loop keeps turning and the heartbeat
        keeps ticking.
        """
        try:
            if reinit:
                self.reinit()
            self._device.display(image)
        except Exception:
            pass    # OLED I/O failures degrade silently — never crash the radio owner

    def show(self, lines):
        """Legacy text path. Retained for the bring-up tools; the service renders images."""
        try:
            from luma.core.render import canvas       # pyright: ignore[reportMissingImports]  # Pi-only
            with canvas(self._device) as draw:
                for i, line in enumerate(lines[:4]):
                    draw.text((0, i * 16), str(line)[:21], fill="white")
        except Exception:
            pass    # OLED I/O failures degrade silently — never crash the radio owner
