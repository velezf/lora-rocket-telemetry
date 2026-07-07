"""SX127x (RFM9x) LoRa receiver driver — pure register/frame logic.

Host-testable: the SPI transport is injected (see FakeSpi in the tests and
SpidevLgpioTransport for hardware), so all config-encoding and frame-parsing
logic runs without spidev/lgpio or a radio. No module-level side effects.

Mirrors the sled's RadioHead RH_RF95 defaults and strips RadioHead's 4-byte
header (TO, FROM, ID, FLAGS). CRC-errored and malformed frames are dropped and
counted — never handed downstream. Driver API ends at validated payload bytes;
packet parsing is the ADR-0001 decoder's job (out of scope here).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

# --- SX127x registers ---
R_FIFO = 0x00
R_OPMODE = 0x01
R_FRMSB = 0x06
R_FRMID = 0x07
R_FRLSB = 0x08
R_LNA = 0x0C
R_FIFOADDR = 0x0D
R_FIFORXBASE = 0x0F
R_FIFORXCUR = 0x10
R_IRQFLAGS = 0x12
R_RXNB = 0x13
R_PKTSNR = 0x19
R_PKTRSSI = 0x1A
R_RSSI = 0x1B
R_MODEM1 = 0x1D
R_MODEM2 = 0x1E
R_MODEM3 = 0x26
R_PREMSB = 0x20
R_PRELSB = 0x21
R_SYNC = 0x39
R_VERSION = 0x42

# opmode (LoRa long-range bit + mode)
LORA = 0x80
SLEEP = 0x00
STDBY = 0x01
RXCONT = 0x05

# IRQ flags
IRQ_RXDONE = 0x40
IRQ_CRCERR = 0x20

SX1276_VERSION = 0x12
RH_HEADER_LEN = 4  # RadioHead: TO, FROM, ID, FLAGS

_FSTEP = 32_000_000 / (1 << 19)  # 61.035... Hz

# bandwidth (kHz) -> RegModemConfig1 code
_BW_CODES = {
    7.8: 0, 10.4: 1, 15.6: 2, 20.8: 3, 31.25: 4,
    41.7: 5, 62.5: 6, 125: 7, 250: 8, 500: 9,
}


@dataclass
class LoRaConfig:
    """Modem configuration. Defaults mirror the sled's RadioHead Bw125Cr45Sf128."""
    freq_hz: int = 434_000_000
    bandwidth_khz: float = 125
    spreading_factor: int = 7        # 6..12
    coding_rate: int = 5             # denominator of 4/N: 5..8
    sync_word: int = 0x12            # private-network default (RH + adafruit)
    preamble: int = 8
    crc: bool = True

    def modem_config1(self) -> int:
        bw = _BW_CODES[self.bandwidth_khz]
        cr = self.coding_rate - 4     # 5->1 .. 8->4
        return (bw << 4) | (cr << 1)  # explicit header (bit0 = 0)

    def modem_config2(self) -> int:
        return (self.spreading_factor << 4) | (0x04 if self.crc else 0x00)

    def modem_config3(self) -> int:
        symbol_ms = (1 << self.spreading_factor) / (self.bandwidth_khz * 1000) * 1000
        ldro = 0x08 if symbol_ms > 16 else 0x00   # low-data-rate optimize
        return 0x04 | ldro                          # AGC auto on

    def frf(self) -> int:
        return round(self.freq_hz / _FSTEP)


@dataclass
class RxFrame:
    """A validated, CRC-good RadioHead frame with its header split out."""
    to: int
    source: int
    msg_id: int
    header_flags: int
    payload: bytes
    rssi_dbm: int
    snr_db: float


class SX127xRx:
    """LoRa receiver over an injected SPI transport.

    transport must provide:
      - transfer(list[int]) -> list[int]   (SPI full-duplex, like spidev.xfer2)
      - reset()                            (pulse the radio's RESET line)
    """

    def __init__(self, transport, config: LoRaConfig | None = None, sleep=time.sleep):
        self._t = transport
        self.config = config or LoRaConfig()
        self._sleep = sleep
        self.received = 0
        self.crc_errors = 0
        self.malformed = 0

    # --- low-level register access ---
    def _read(self, addr: int) -> int:
        return self._t.transfer([addr & 0x7F, 0x00])[1]

    def _write(self, addr: int, value: int) -> None:
        self._t.transfer([(addr | 0x80) & 0xFF, value & 0xFF])

    def _burst(self, addr: int, n: int) -> list:
        return self._t.transfer([addr & 0x7F] + [0x00] * n)[1:]

    def _settle(self) -> None:
        self._sleep(0.01)

    def version(self) -> int:
        return self._read(R_VERSION)

    # --- configuration ---
    def configure(self) -> None:
        c = self.config
        self._t.reset()
        self._write(R_OPMODE, LORA | SLEEP)   # LoRa mode requires SLEEP first
        self._settle()
        frf = c.frf()
        self._write(R_FRMSB, (frf >> 16) & 0xFF)
        self._write(R_FRMID, (frf >> 8) & 0xFF)
        self._write(R_FRLSB, frf & 0xFF)
        self._write(R_MODEM1, c.modem_config1())
        self._write(R_MODEM2, c.modem_config2())
        self._write(R_MODEM3, c.modem_config3())
        self._write(R_PREMSB, (c.preamble >> 8) & 0xFF)
        self._write(R_PRELSB, c.preamble & 0xFF)
        self._write(R_SYNC, c.sync_word)
        self._write(R_LNA, 0x20)               # max LNA gain
        self._write(R_FIFORXBASE, 0x00)
        self._write(R_FIFOADDR, 0x00)
        self._write(R_OPMODE, LORA | STDBY)
        self._settle()
        self._write(R_OPMODE, LORA | RXCONT)
        self._settle()

    def rssi_floor(self) -> int:
        return -164 + self._read(R_RSSI)        # LF band (<525 MHz)

    # --- receive one packet (poll; DIO0 unwired) ---
    def receive(self) -> RxFrame | None:
        """Return the next validated frame, or None (no packet / dropped).

        CRC-errored and too-short frames are dropped and counted; a corrupted
        payload is never returned.
        """
        flags = self._read(R_IRQFLAGS)
        if not (flags & IRQ_RXDONE):
            return None
        crc_err = bool(flags & IRQ_CRCERR)
        nb = self._read(R_RXNB)
        self._write(R_FIFOADDR, self._read(R_FIFORXCUR))
        raw = bytes(self._burst(R_FIFO, nb))
        rssi = -164 + self._read(R_PKTRSSI)
        snr_raw = self._read(R_PKTSNR)
        snr = (snr_raw - 256 if snr_raw > 127 else snr_raw) / 4.0
        self._write(R_IRQFLAGS, 0xFF)           # clear IRQ flags (even on drop)

        if crc_err:
            self.crc_errors += 1
            return None
        if nb < RH_HEADER_LEN + 1:              # need header + >=1 payload byte
            self.malformed += 1
            return None

        self.received += 1
        return RxFrame(
            to=raw[0], source=raw[1], msg_id=raw[2], header_flags=raw[3],
            payload=raw[RH_HEADER_LEN:], rssi_dbm=rssi, snr_db=snr,
        )
