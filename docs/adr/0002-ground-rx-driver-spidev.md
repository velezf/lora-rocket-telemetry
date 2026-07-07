# ADR 0002 — Ground-station LoRa RX uses raw spidev + lgpio (Blinka rejected)

- **Status:** Accepted
- **Date:** 2026-07-07
- **Relates to:** Epic 2.5 (native LoRa RX); [ADR 0001](0001-packet-format-v1.md) (the payload this driver hands off)

## Context

Epic 2.5 originally scoped `adafruit_rfm9x` for native LoRa RX, which runs on Adafruit
Blinka (`busio`/`digitalio`). On this ground station — Raspberry Pi 5 (BCM2712), Debian 13
Trixie, Python 3.13.5 — Blinka does not install or run cleanly:

- `adafruit-blinka` pulls source-only deps `RPi.GPIO` + `rpi_ws281x`; in an isolated venv
  they fail to build (`fatal error: Python.h` — no `python3-dev`).
- The deeper blocker: `RPi.GPIO` 0.7.2 mmaps BCM283x registers and **does not run on the
  Pi 5 / RP1**. The supported path is the `rpi-lgpio` shim (already installed system-wide),
  which the naive pip build bypasses. Blinka is achievable but fragile and buys nothing.
- The rest of the ground stack is already **Blinka-free**: OLED via `luma.oled`, panel LEDs
  via `gpiozero` on the lgpio backend. Only the radio was in question.

## Decision

The ground RX is a small **raw SX127x driver over `spidev` + `lgpio`**
([`ground/rx/sx127x.py`](../../ground/rx/sx127x.py)), configured to mirror the sled's
RadioHead RH_RF95 modem settings (434 MHz, BW125 / SF7 / CR 4-5, sync `0x12`, CRC on).
Blinka / `adafruit_rfm9x` are **rejected** for the ground station.

## Consequences

- No Blinka anywhere on the ground station — a leaner, Pi-5-native dependency set.
- The driver is **importable and host-tested** (SPI transport is injected; register and
  frame logic run with a fake SPI, no hardware).
- **CRC-errored and malformed frames are dropped and counted** — the PHY-CRC integrity
  guarantee ADR 0001 relies on is enforced at the driver boundary.
- The 4-byte RadioHead header (TO/FROM/ID/FLAGS) is validated (`nb >= 5`) and split out;
  the driver hands **validated payload bytes** to the ADR-0001 decoder. Packet parsing is
  not this driver's job.
- If a future component genuinely needs the Adafruit ecosystem, revisit via `python3-dev`
  + the `rpi-lgpio` shim (documented cost), not as the default.
