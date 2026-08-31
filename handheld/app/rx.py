"""RX glue for the bonnet radio (Epic 8.2).

Pure/testable here: the LoRaConfig -> adafruit_rfm9x settings mapping and
the payload -> model path. The Blinka/SPI construction lives in main (thin,
hardware-only) — this module imports no radio library.

`ground/rx/sx127x.py::LoRaConfig` is the ONE authority for the RF constants
(ADR 0005 §7); this mapping only converts units to the adafruit_rfm9x
property vocabulary. adafruit_rfm9x is RadioHead-compatible by design: its
receive(with_header=False) strips the 4-byte RH header, and the LoRa sync
word stays at the SX127x private-network default (0x12) that LoRaConfig
also specifies — the library exposes no property for it.
"""
from __future__ import annotations

from dataclasses import dataclass


def rfm9x_settings(cfg) -> dict:
    return {
        "frequency_mhz": cfg.freq_hz / 1_000_000,
        "signal_bandwidth": int(cfg.bandwidth_khz * 1000),
        "spreading_factor": cfg.spreading_factor,
        "coding_rate": cfg.coding_rate,
        "preamble_length": cfg.preamble,
        "enable_crc": cfg.crc,
    }


def apply_settings(radio, cfg) -> None:
    for key, val in rfm9x_settings(cfg).items():
        setattr(radio, key, val)


@dataclass
class RxCounters:
    accepted: int = 0
    decode_errors: int = 0


def handle_payload(model, payload: bytes, rssi_dbm: float, mono: float,
                   counters: RxCounters) -> bool:
    """Decode one RH-header-stripped payload into the model. Never raises."""
    from ground.decode.v1 import decode

    pkt = decode(payload)
    if not pkt.ok:
        counters.decode_errors += 1
        return False
    if model.observe(pkt, rssi_dbm=rssi_dbm, mono=mono):
        counters.accepted += 1
        return True
    return False
