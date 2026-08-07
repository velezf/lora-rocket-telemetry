# HANDOFF — catch-up prompt for a fresh Claude session

Copy-paste the block below to bring a new Claude session (or a plan-author Claude that
lacks this session's context) up to speed, so it doesn't re-plan already-finished work.
Keep it in sync with [`RESUME.md`](RESUME.md) — the authoritative live status — whenever an
epic lands.

```
You're resuming RocketLoRaTelemetry V2 (LoRa rocket telemetry: Feather M0 sled TX, Pi 5
ground station "apogee-gs", lander, kids' handheld). READ docs/RESUME.md FIRST — it's the
live status — and CLAUDE.md for conventions.

Working agreement (strict): Frank approves every commit AND merge. One feature branch per
unit of work, TDD (red→green→refactor), --no-ff merges. PAUSE for explicit approval before
every commit, merge, and push — never publish to origin without it.

DONE and merged to main (do NOT re-plan these):
- Epic 1 (PlatformIO/Mac): done; 1.4 upload path proven on the real Feather M0.
- Epic 2 (Pi 5 ground station): done — peripherals wired (radio SPI0/CE1, OLED I²C 0x3d,
  PiSugar, 6 panel LEDs), native RX driver ground/rx/sx127x.py (raw spidev+lgpio,
  host-tested), 2.6 low-battery shutdown configured. **2.2 hotspot CLOSED 2026-08-07** (validated router-off on hotspot alone; cold-boot rejoin unobserved and closed on the convenience-not-data-path argument). **Epic 2 fully closed.**
- Epic 3 (sled TX + contract): COMPLETE. ADR 0001 = locked packet format. firmware/lib/ has
  host-tested pure units (packet encoder, launch, apogee, conversions). firmware/src/main.cpp
  emits ADR v1 (V:1 SYS:7 SRC:1 SEQ:.. St:.. ALT:..ft ...); B4/B5 (SYS/SRC, SEQ/St) folded in.
  Verified end-to-end: sled → ground driver, 22/22 payloads match the ADR grammar, 0 CRC errors.
- Epic 5.1 evidence done (9-DoF LSM6DSOX/LIS3MDL smoked on the sled bus; libs NOT yet in
  platformio.ini — Epic 5 owns that). Epic 8.1 handheld groundwork merged.

Locked decisions:
- ADR 0001 = packet format v1 (keyed KEY:VALUE ASCII, leading V:1, additive/unknown-tag
  tolerant). Human-readable index: docs/telemetry-dictionary.md.
- ADR 0002 = ground RX is raw spidev+lgpio; Blinka REJECTED (RPi.GPIO won't run on Pi 5 /
  BCM2712). The whole ground stack is Blinka-free.

Standing gates / gotchas:
- Keep the e2e check (sled TX → ground/rx driver → payload matches ADR fixtures) as a REQUIRED
  merge gate for anything touching encode/decode — it caught a newlib-nano float-printf bug
  host tests missed (feather env now carries -Wl,-u,_printf_float).
- Feather M0 re-flashes reliably need a manual double-tap to bootloader (ask Frank).

Next up: Epic 4 — 4.1 Python decoder (assert against ADR 0001's golden vector AND an
unknown-tag fixture), then 4.2 ingest service on the merged ground/rx/ driver (delete the Pi
scratch scripts rx_test.py / rx_driver_check.py in that branch), then logging/dashboard/OLED.

Hardware is all on the bench (not boxed). Mac = firmware; Pi 5 = ssh rocketman@apogee-gs.local.
Pull before starting.
```
