# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: 2026-07-07 (Claude, on Mac + Pi 5 over SSH)._

## Where we are

Foundations are down and **Epic 3 is essentially complete**. Epic 1 (Mac PlatformIO
toolchain) is built and the **1.4 upload path is proven on the real Feather M0**. The v1
packet contract — the keystone everything decodes against — is **locked** as ADR 0001.
The Epic 2 ground station (`apogee-gs`) is up: peripherals wired & bench-verified, the
native **LoRa RX driver** (`ground/rx/`, raw spidev+lgpio, host-tested; ADR 0002) built,
and PiSugar graceful low-battery shutdown configured. **The sled TX now emits the ADR v1
format** — packets built from host-tested pure units (encoder / launch / apogee /
conversions) — and the ground driver receives + CRC-checks them, **verified end-to-end**
(sled → Pi, 22/22 payloads match the ADR grammar, RSSI ~−60 dBm). Epic 8 has its platform
groundwork merged. **Next up: Epic 4** (Python decoder + ingest/log/dashboard) on the driver.

## Ground station (`apogee-gs`) — access

- **SSH:** `ssh rocketman@apogee-gs.local` (key auth, passwordless sudo).
- **Pi Connect:** signed in as device `apogee-gs` (`rpi-connect-lite`, remote shell;
  no screen sharing — headless). Reachable from anywhere, not just the local network.
- **Claude Code:** installed (`2.1.197`), on PATH (`~/.local/bin`), **authenticated** via
  `claude auth login` (claude.ai, Max). Headless `claude -p` works.
- **OS:** Raspberry Pi OS 64-bit, **Trixie / Debian 13** (not Bookworm). **Python 3.13.5**
  (`/usr/bin/python3`), `venv` works. No system `pip` (PEP 668 — use venv). A **`~/gs-venv`**
  venv exists (`luma.oled` for the OLED); **`uv` not yet installed**.
- **Repo:** cloned at `~/lora-rocket-telemetry` via a **read-only deploy key** (`apogee-gs`);
  `git pull` works (Pi pulled to current `main`).
- **Wi-Fi:** home **WideRoad** (priority 0) first, **iPhone 17 hotspot** fallback
  (priority −10, infinite retry, persistent NM keyfile). Networking is netplan-rendered
  → NetworkManager. _(Hotspot secret lives only on the Pi, never in this repo.)_

## Wired peripherals (bench-verified 2026-07-07)

| Device | Bus | Address / CS | Notes |
|--------|-----|--------------|-------|
| RFM96 LoRa radio | SPI0 | **CE1** (`/dev/spidev0.1`, pin 26); RESET GPIO25 (pin 22) | `RegVersion 0x12`. **Not CE0.** |
| OLED (Adafruit 938, SSD1306 128×64) | I²C-1 | `0x3d` | driven via `~/gs-venv` + **`luma.oled`** |
| PiSugar 3 Plus UPS | I²C-1 | `0x57` batt, `0x68` RTC | `pisugar-server`; auto-shutdown at 5% / 30 s |
| Front-panel LEDs ×6 | GPIO | `5,6,13,26,12,16` (L→R: grn×3, red, blu×2) | active-high; bring-up via `ground/tools/led_check.py` |
| Sled 9-DoF (bench, Epic 5.1) | I²C | LSM6DSOX `0x6a`, LIS3MDL `0x1c` | on the sled's STEMMA QT bus alongside BMP390 `0x77` / ADXL375 `0x53` |

**Native LoRa RX** = the repo's `ground/rx/` **SX127x driver** (raw `spidev`+`lgpio`,
host-tested against a fake SPI, CRC-enforcing, RadioHead-header aware). **Blinka rejected —
[ADR 0002](adr/0002-ground-rx-driver-spidev.md)** (RPi.GPIO won't run on BCM2712). OLED uses
`luma.oled`; LEDs use `gpiozero`/lgpio — the whole ground stack is Blinka-free. `rocketman`
is in `spi`/`i2c`/`gpio` groups; `i2cdetect` is in `/usr/sbin`. **Authoritative pin map:**
[`docs/ground-station-wiring.md`](ground-station-wiring.md).

## Hardware state (bench, 2026-07-07)

- **All three nodes built and on the bench**, none yet enclosed:
  - **Sled** — Feather M0 + RFM95 + BMP390 `0x77` + ADXL375 `0x53`, now with the **9-DoF
    LSM6DSOX `0x6a` + LIS3MDL `0x1c` chained on**; runs the ADR v1 TX firmware.
  - **Lander** (KB2040 + 2nd RFM96) and **handheld** (Pi Zero 2 W + LoRa/OLED bonnet) —
    built, on bench; firmware not started (Epics 7 / 8).
- **Ground station** — Pi 5 in **benchtop config, not yet boxed** (radio/OLED/PiSugar/LEDs wired).
- **9-DoF** I²C-smoked (Epic 5.1 evidence — WHO_AM_I `0x6C`/`0x3D`, sane gyro/mag reads). Its
  libraries are **NOT in `platformio.ini` yet** — Epic 5 owns adding `Adafruit_LSM6DSOX`/`_LIS3MDL`.

## Epic status

| Epic | Status |
|------|--------|
| 1 — PlatformIO dev env (Mac) | ✅ **Done.** 1.1–1.3 + **1.4 upload smoke proven** on the Feather M0 (SAM-BA upload + serial heartbeat). |
| 2 — Pi 5 ground-station bring-up | ✅ **2.1–2.6 done.** OS/SSH/Wi-Fi/Claude Code/deploy-key clone; radio SPI0/CE1, OLED 0x3d, PiSugar batt+RTC, 6 panel LEDs; **2.5 RX driver** in `ground/rx/`; **2.6 low-battery auto-shutdown** configured. **Remaining: 2.2 hotspot fallback field test** (physical); panel-LED *functions* unassigned (Epic 4). |
| 3 — Sled TX firmware + contract | ✅ **Complete.** ADR 0001 locked; encoder/launch/apogee/conversions as host-tested `lib/` units; `src/main.cpp` emits **ADR v1** (`V:1 SYS:7 SRC:1 …`) with live SYS/SRC/SEQ/St/MET (**B4/B5 folded into the integration commit**); **e2e verified** — sled→Pi driver, **22/22 ADR-OK**, 0 CRC errors. |
| 4 — Ground service (decode/log/dash/web/OLED) | ⏳ **Next.** 4.1 Python decoder (against ADR 0001 — include an unknown-tag fixture) + 4.2 ingest on the `ground/rx/` driver; then log/dashboard/OLED. |
| 5 — 9-DoF integration | 🟡 **5.1 hardware evidence done** (LSM6DSOX 0x6a + LIS3MDL 0x1c on the sled bus; WHO_AM_I 0x6C/0x3D; sane gyro/mag). 5.2–5.4 not started; `Roll`/`Spin` reserved (ADR 0001 App. A). |
| 6 — Relay deployment (safety-critical) | ⏳ Not started. |
| 7 — Lander payload (`SRC:2`) | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 8 — Kids' handheld | 🟡 **8.1 platform groundwork merged** (PR #1, `handheld/`). Bench bring-up pending PiSugar 3 + SRH805S antenna (both ordered). 8.2–8.5 not started. |

## Open branches (pending review/merge)

**None** — all Epic 1/2/3 work is merged and pushed to `origin/main`. Merged feature
branches (kept, not deleted): `feat/gs-bringup`, `feat/ground-rx-driver`,
`feat/firmware-b{3,6,7,8}-*`, `feat/sled-tx-adr-integration`, `docs/telemetry-dictionary`.

## Locked decisions

- **Packet format v1** ([ADR 0001](adr/0001-packet-format-v1.md)): keyed `KEY:VALUE` ASCII,
  leading `V:1`; `MET` time token; **no app-layer checksum** (rely on LoRa PHY CRC); `SYS`
  default `7`; `SRC` `1=sled, 2=lander`; additive tags tolerated, unknown tags ignored.
  Human-readable index: [`docs/telemetry-dictionary.md`](telemetry-dictionary.md).
- **Ground RX = raw spidev + lgpio** ([ADR 0002](adr/0002-ground-rx-driver-spidev.md)),
  Blinka rejected on Pi 5.
- **ADR numbering:** global `docs/adr/` and per-component logs both fine.

## Immediate next steps

1. **Epic 4.1 — Python decoder:** parse the ADR v1 payload the `ground/rx/` driver hands
   over; assert against ADR 0001's golden vector **and an unknown-tag fixture** (forward-compat).
2. **Epic 4.2 — ingest service:** run the driver as a service → decoded packets → log
   (`SEQ`/`SRC` loss stats), then dashboard + status OLED (4.4/4.6).
3. **2.2 hotspot field test** (physical): away from home Wi-Fi, confirm `apogee-gs` falls
   back to the iPhone hotspot (`iwgetid -r` / `nmcli`).
4. **Assign the 6 panel-LED functions** (Epic 4) — driven from decoded packets.

## Notes / gotchas

- **Standing merge gate:** the e2e check (sled TX → `ground/rx/` driver → payload matches
  the ADR fixtures) caught the newlib-nano float-printf bug that host tests could NOT —
  **keep the e2e check as a required gate for anything touching encode/decode.**
- **newlib-nano `%f`:** float printf is off by default → the feather env carries
  `-Wl,-u,_printf_float` (float tags encode empty on-target otherwise, though host tests pass).
- **Feather M0 re-flashing:** first upload of a session works; re-flashes reliably need a
  **manual double-tap to bootloader** (SAM-BA flake). See memory `feather-m0-flash-double-tap`.
- **Scratch debris on the Pi** (not in repo): `~/rx_test.py`, `~/rx_driver_check.py` —
  superseded by the 4.2 ingest service; **delete them in the 4.2 branch.**
