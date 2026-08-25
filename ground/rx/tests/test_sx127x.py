# pyright: reportOptionalMemberAccess=false
# ^ receive() returns RxFrame|None; tests access it after asserting a frame arrived.
"""Host tests for the SX127x LoRa RX driver against a fake SPI transport.

No spidev/lgpio and no hardware — the driver takes an injected transport, so all
register and frame logic runs on the host (`python3 -m unittest`).
"""
import unittest

from ground.rx.sx127x import (
    SX127xRx, LoRaConfig, RxFrame,
    R_FIFO, R_OPMODE, R_IRQFLAGS, R_RXNB, R_FIFORXCUR, R_FIFOADDR,
    R_MODEM1, R_MODEM2, R_MODEM3, R_SYNC, R_PREMSB, R_PRELSB,
    R_FRMSB, R_FRMID, R_FRLSB, R_PKTRSSI, R_PKTSNR, R_VERSION,
    IRQ_RXDONE, IRQ_CRCERR, LORA, RXCONT,
)


class FakeSpi:
    """Minimal SX127x SPI model: readable registers + an RX FIFO buffer.

    transfer(data): data[0] is the address byte. MSB set => write (record it);
    else read. A read starting at R_FIFO returns the FIFO buffer bytes.
    """

    def __init__(self):
        self.registers = {
            R_VERSION: 0x12,
            R_IRQFLAGS: 0x00,
            R_RXNB: 0x00,
            R_FIFORXCUR: 0x00,
            R_PKTRSSI: 0x00,
            R_PKTSNR: 0x00,
        }
        self.fifo = b""
        self.writes = []  # list of (addr, value)
        self.reset_count = 0

    def reset(self):
        self.reset_count += 1

    def transfer(self, data):
        addr = data[0]
        if addr & 0x80:  # write
            reg = addr & 0x7F
            self.registers[reg] = data[1]
            self.writes.append((reg, data[1]))
            return [0] * len(data)
        reg = addr & 0x7F
        n = len(data) - 1
        if reg == R_FIFO:
            body = list(self.fifo[:n]) + [0] * max(0, n - len(self.fifo))
            return [0] + body
        return [0] + [self.registers.get(reg, 0)] * n

    # helpers for tests
    def wrote(self, addr):
        """Last value written to addr, or None."""
        for a, v in reversed(self.writes):
            if a == addr:
                return v
        return None

    def load_frame(self, payload_with_header, crc_err=False):
        self.fifo = bytes(payload_with_header)
        self.registers[R_RXNB] = len(payload_with_header)
        self.registers[R_FIFORXCUR] = 0
        flags = IRQ_RXDONE | (IRQ_CRCERR if crc_err else 0)
        self.registers[R_IRQFLAGS] = flags


def make_radiohead_frame(payload: bytes, to=0xFF, frm=0xFF, mid=0x00, flags=0x00):
    return bytes([to, frm, mid, flags]) + payload


class TestConfigure(unittest.TestCase):
    def setUp(self):
        self.spi = FakeSpi()
        self.rx = SX127xRx(self.spi, LoRaConfig(), sleep=lambda *_: None)

    def test_configure_sets_lora_rx_continuous(self):
        self.rx.configure()
        # first opmode write enters LoRa+sleep; final is LoRa+RXCONTINUOUS
        self.assertEqual(self.spi.wrote(R_OPMODE), LORA | RXCONT)

    def test_configure_modem_registers_for_bw500_sf7_cr45_crc(self):
        # Default is BW500 per docs/adr/0005-telemetry-rate-and-rf-configuration.md.
        self.rx.configure()
        self.assertEqual(self.spi.wrote(R_MODEM1), 0x92)  # BW500, CR4/5, explicit hdr
        self.assertEqual(self.spi.wrote(R_MODEM2), 0x74)  # SF7, CRC on
        self.assertEqual(self.spi.wrote(R_MODEM3), 0x04)  # AGC on, LDRO off (0.256 ms symbol)

    def test_configure_frequency_434mhz(self):
        self.rx.configure()
        self.assertEqual(self.spi.wrote(R_FRMSB), 0x6C)
        self.assertEqual(self.spi.wrote(R_FRMID), 0x80)
        self.assertEqual(self.spi.wrote(R_FRLSB), 0x00)

    def test_configure_sync_and_preamble(self):
        self.rx.configure()
        self.assertEqual(self.spi.wrote(R_SYNC), 0x12)
        self.assertEqual(self.spi.wrote(R_PREMSB), 0x00)
        self.assertEqual(self.spi.wrote(R_PRELSB), 0x08)

    def test_reset_invoked(self):
        self.rx.configure()
        self.assertEqual(self.spi.reset_count, 1)


class TestConfigEncoding(unittest.TestCase):
    def test_sf9_bw250_cr48_registers(self):
        spi = FakeSpi()
        rx = SX127xRx(spi, LoRaConfig(bandwidth_khz=250, spreading_factor=9,
                                      coding_rate=8, crc=True), sleep=lambda *_: None)
        rx.configure()
        # BW250=0x8, CR4/8 code=4 -> MODEM1 = (0x8<<4)|(4<<1) = 0x88
        self.assertEqual(spi.wrote(R_MODEM1), 0x88)
        # SF9 -> (9<<4)|CRC(0x04) = 0x94
        self.assertEqual(spi.wrote(R_MODEM2), 0x94)

    def test_bw500_cr45_explicit_header_register_byte(self):
        # The ADR 0005 flight configuration, asserted independently of the
        # default: BW500 code 0x9, CR4/5 code 1, explicit header bit0=0
        # -> RegModemConfig1 = (0x9<<4)|(1<<1)|0 = 0x92.
        from ground.rx.sx127x import _BW_CODES
        self.assertIn(500, _BW_CODES)
        self.assertEqual(_BW_CODES[500], 0x9)
        cfg = LoRaConfig(bandwidth_khz=500, spreading_factor=7, coding_rate=5)
        self.assertEqual(cfg.modem_config1(), 0x92)

    def test_default_config_is_the_adr0005_flight_config(self):
        # One authority for the both-ends constant (cited in LoRaConfig): if the
        # default drifts off SF7/BW500/CR4:5 the link to the sled goes silently
        # dark, so the default itself is pinned here.
        cfg = LoRaConfig()
        self.assertEqual((cfg.bandwidth_khz, cfg.spreading_factor, cfg.coding_rate),
                         (500, 7, 5))


class TestReceive(unittest.TestCase):
    def setUp(self):
        self.spi = FakeSpi()
        self.rx = SX127xRx(self.spi, LoRaConfig(), sleep=lambda *_: None)

    def test_no_packet_returns_none(self):
        self.spi.registers[R_IRQFLAGS] = 0x00
        self.assertIsNone(self.rx.receive())

    def test_good_frame_parsed(self):
        self.spi.load_frame(make_radiohead_frame(b"V:1 SEQ:42", mid=7, flags=0x01))
        self.spi.registers[R_PKTRSSI] = 108  # -164 + 108 = -56 dBm
        self.spi.registers[R_PKTSNR] = 40     # 40/4 = 10.0 dB
        frame = self.rx.receive()
        self.assertIsInstance(frame, RxFrame)
        self.assertEqual(frame.to, 0xFF)
        self.assertEqual(frame.source, 0xFF)
        self.assertEqual(frame.msg_id, 7)
        self.assertEqual(frame.header_flags, 0x01)
        self.assertEqual(frame.payload, b"V:1 SEQ:42")
        self.assertEqual(frame.rssi_dbm, -56)
        self.assertEqual(frame.snr_db, 10.0)
        self.assertEqual(self.rx.received, 1)
        self.assertEqual(self.rx.crc_errors, 0)

    def test_crc_error_frame_is_dropped(self):
        self.spi.load_frame(make_radiohead_frame(b"V:1 corrupt"), crc_err=True)
        self.assertIsNone(self.rx.receive())          # never handed downstream
        self.assertEqual(self.rx.crc_errors, 1)
        self.assertEqual(self.rx.received, 0)
        # IRQ flags cleared even on a dropped frame
        self.assertEqual(self.spi.wrote(R_IRQFLAGS), 0xFF)

    def test_short_frame_is_dropped(self):
        # 4 bytes = RadioHead header only, zero payload -> invalid (need nb>=5)
        self.spi.load_frame(bytes([0xFF, 0xFF, 0x00, 0x00]))
        self.assertIsNone(self.rx.receive())
        self.assertEqual(self.rx.malformed, 1)
        self.assertEqual(self.rx.received, 0)

    def test_fifo_pointer_set_to_current_before_read(self):
        self.spi.load_frame(make_radiohead_frame(b"hello"))
        self.spi.registers[R_FIFORXCUR] = 0x00
        self.rx.receive()
        self.assertEqual(self.spi.wrote(R_FIFOADDR), 0x00)


if __name__ == "__main__":
    unittest.main()


class TestHighBwSensitivityErrata(unittest.TestCase):
    """SX1276 errata note §2.1 ("Sensitivity Optimization with a 500 kHz
    Bandwidth"): at BW500 the receiver needs 0x36=0x02 and 0x3A=0x7F (410-525
    MHz band; 0x64 for 862-1020 MHz), else sensitivity is degraded below the
    datasheet figure the ADR 0005 link budget assumes. For every other
    bandwidth 0x36 returns to 0x03 (automatic) and 0x3A is left to the chip.
    Register values are from the errata sheet — flagged for verification
    against the published document before the bench (red-team finding 8)."""

    def _configured(self, cfg):
        spi = FakeSpi()
        SX127xRx(spi, cfg, sleep=lambda *_: None).configure()
        return spi

    def test_bw500_in_the_434mhz_band_writes_lf_errata_values(self):
        spi = self._configured(LoRaConfig())          # deployed default: BW500 @ 434 MHz
        self.assertEqual(spi.wrote(0x36), 0x02)
        self.assertEqual(spi.wrote(0x3A), 0x7F)

    def test_bw500_in_the_hf_band_writes_hf_errata_value(self):
        spi = self._configured(LoRaConfig(freq_hz=915_000_000))
        self.assertEqual(spi.wrote(0x36), 0x02)
        self.assertEqual(spi.wrote(0x3A), 0x64)

    def test_other_bandwidths_restore_automatic_mode(self):
        spi = self._configured(LoRaConfig(bandwidth_khz=125))
        self.assertEqual(spi.wrote(0x36), 0x03)       # automatic per errata
        self.assertIsNone(spi.wrote(0x3A))            # auto mode: chip manages 0x3A
