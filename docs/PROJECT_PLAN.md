# RocketLoRaTelemetry — Project Plan

Roadmap for the Apogee Zephyr telemetry system: replatform the firmware, stand up a Raspberry Pi 5 ground station with native LoRa reception, build the logging / dashboard / web pipeline, and fly a deployable second vehicle plus a kids' handheld. **Hardware is locked — this is now an execution roadmap.**

## How this is structured

- **Epics** are session-sized chunks of work — the unit we tackle one at a time.
- The **X.1 / X.2** sprints under each epic are a *proposed first pass* — a scaffold to refine, reorder, or split when you break them down.
- Assumed throughout: **TDD (red → green → refactor)** for all logic, **one branch per feature**, **SSH** for git.
- The **v1 packet format** is the single contract shared by every node — the rocket TX, the Python decoder, and the handheld:

  ```
  V:1 SYS:7 SRC:1 SEQ:42 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V St:1 t+12s
  ```

  `V` version · `SYS` network · `SRC` source vehicle · `SEQ` packet counter · flight fields · `St` state (0 pad / 1 ascent / 2 descent). Battery status derived on the ground. New tags are additive. Because `SYS`/`SRC` ride in the payload string, the contract is transport-agnostic.
- **The sled is the only C++ in the project.** Native-Pi RX (Epic 2.5) means there's no RX firmware — the ground side is all Python.

## Dependency order

Epics 1 and 2 are independent foundations (Mac toolchain vs. Pi bring-up) and can run in parallel. Epic 3 needs Epic 1. Epic 4 needs Epic 2 (Pi + native RX) and Epic 3's packet contract (3.2–3.4). Epic 5 builds on 3 and 4. Epic 6 (relay deployment) is safety-critical and depends on Epic 3's apogee detection (3.6). Epics 7 (lander) and 8 (handheld) are additional nodes on the shared grammar. Core loop to a first flight: 1 → 2 → 3 → 4; Epics 7 and 8 are optional to that first flight.

## Build notes (operational gotchas)

- **Run the ground station lid-off.** It solves two things at once: open airflow over the passive heatsinks (no sealed-box heat trap), and it frees the Pi 5's onboard WiFi from the metal box's shielding — the phone-hotspot dashboard link depends on that WiFi. (If you ever seal it: add vent holes *and* a USB WiFi dongle with an external antenna, since the Pi 5's built-in WiFi can't take one.)
- **PiSugar 3 Plus caps ~3A; the Pi 5 can peak to ~5A.** Fine for this light load, but set `usb_max_current_enable=1`, keep the buck→PiSugar charge cable short, and let the metal case + heatsinks handle thermals.
- **Handheld antenna gender:** the SRH805S is SMA-*female*, so the bonnet's pigtail must present SMA-*male* to mate (gender-changers on hand if it doesn't).
- **Bench setup:** the Pi 5 is USB-C and gets powered in the box via the PiSugar pogo pins — but you'll need any USB-C charger to image the card and do first setup at the desk.

## Hardware roster

**Ground station**
- Raspberry Pi 5 (8 GB) *[have]*
- PiSugar 3 Plus UPS *[have — 3A cap, see build notes]*
- Blue metal project box, ~9.8 × 7.5 × 4.3" *[have]* — run lid-off
- Passive heatsink kit (Pi 4-style; large square on the BCM2712 SoC, small on RP1) *[ordered]*
- 12 V → TOBSUN 5 V/5 A buck → PiSugar micro-USB charge port *[have]*
- RFM96W breakout w/ soldered uFL → micro-SMA adapter → box antenna, on the Pi's SPI *[have, ready]*
- Adafruit 938 OLED (1.3" 128×64 SSD1306, STEMMA QT / I²C) + 4397 QT-to-female-socket cable *[ordered]*
- RTL-SDR + Direwolf APRS, on the second box antenna *[have]*
- SanDisk Ultra 32 GB A1 microSD *[have]*

**Rocket sled (TX, `SRC:1`)**
- Feather M0 RFM96 *[have]* + wire-whip antenna *[have]*
- BMP390 + ADXL375 *[have]*
- LSM6DSOX + LIS3MDL 9-DoF *[have]*
- 2× STEMMA relays for deployment *[have]*

**Lander (`SRC:2`)**
- KB2040 *[have]* + second RFM96W breakout w/ soldered quarter-wave wire antenna *[have, ready]*
- BME680 *[ordered]* + APDS9960 *[have]*
- small LiPo *[have]*

**Kids' handheld**
- Pi Zero 2 W with headers *[have]*
- LoRa bonnet w/ OLED *[have]* + pigtail (must present SMA-male — see build notes)
- BaoFeng SRH805S antenna *[ordered]*
- M2.5 standoffs *[have]* + microSD *[have]* + PiSugar 3 *[ordered]*

**Freed by native RX:** the old ground-RX Feather M0 RFM96 is now unused — backup RX or a future third node.

**Shopping list:** nothing outstanding — everything is in hand or ordered. *(Later epics only, from rocketry suppliers: deployment hardware — e-matches, pyro battery, arm switch — and the lander's streamer + potting.)*

---

## Epic 1 — PlatformIO dev environment (Mac)

*Goal: VSCode + PlatformIO builds the sled firmware and runs host-side logic tests; you can flash the sled from the MacBook.*

- **1.1** — Install PlatformIO in VSCode; scaffold the project layout (new `firmware/` tree vs. adapt the existing `RocketLoRaTelemetry/` folders)
- **1.2** — Define the `feather_m0_tx` build environment (`board = adafruit_feather_m0`, `framework = arduino`); pin `lib_deps`: RadioHead, Adafruit BMP3XX, Adafruit ADXL375, Adafruit Unified Sensor
- **1.3** — Add a `native` test environment so logic units run on the Mac with no hardware (the red/green loop lives here)
- **1.4** — Upload smoke test: flash a trivial serial sketch to the sled to prove the toolchain + upload path

## Epic 2 — Ground-station bring-up (Raspberry Pi 5 8 GB)

*Goal: the Pi 5 boots onto your phone hotspot, runs Claude Code, pulls ground-side code from GitHub, receives LoRa natively via the breakout, drives a status OLED, and runs on a battery UPS. As a real Pi, Blinka, the radio, and the PiSugar are all first-class — no Libre overlay glue.*

- **2.1** — OS baseline: Raspberry Pi OS 64-bit (Trixie / Debian 13), updates, headless SSH, Python 3; enable I²C + SPI via `raspi-config` (a toggle now, not a device-tree overlay)
- **2.2** — WiFi-on-boot: NetworkManager autoconnect → phone hotspot (fixed SSID/password, infinite retry); verify cold-boot rejoin
- **2.3** — Claude Code on the Pi: native installer; 8 GB is comfortable. Runs but isn't Mac-snappy — good for on-box tinkering, heavy lifting stays on the Mac
- **2.4** — GitHub pull path: SSH deploy key, clone, `git pull` update routine for ground-side code
- **2.5** — **Native LoRa RX:** wire the antenna-equipped RFM96W breakout to the Pi's SPI (~7 lines: SPI ×3, CS, RESET, 3V3, GND; DIO0 unconnected). **AS BUILT (deviates from this text — see [ADR 0002](adr/0002-ground-rx-driver-spidev.md)): raw `spidev` + `lgpio`, not Blinka/`adafruit_rfm9x`.** RPi.GPIO won't run on BCM2712 and Blinka was rejected; the repo's own SX127x driver (`ground/rx/`) drives the modem at 434 MHz mirroring the sled's RadioHead config, enforces CRC, strips the 4-byte RadioHead header, and accepts broadcast (`0xFF`). Host-tested against a fake SPI. The whole ground stack is Blinka-free
- **2.6** — UPS / power: PiSugar 3 Plus back-mounts on pogo pins (header stays free), powering the Pi 5 from underneath; feed the 12 V → buck → micro-USB chain into its micro-USB charge port; battery % over I²C; graceful low-battery shutdown. Mind the 3A cap (see build notes). Cooling is passive — heatsinks on the SoC + RP1, run lid-off

## Epic 3 — Firmware (sled TX) + shared contract + addressing

*Goal: the sled TX rebuilt under PlatformIO; the v1 packet format and addressing locked behind a tested boundary; flight logic extracted into host-tested units. No RX firmware — the Pi receives natively.*

- **3.1** — Port the existing TX into `feather_m0_tx`; build, flash, confirm behavior parity
- **3.2** — **Shared packet format v1 (keystone):** single source of truth, encode behind a tested boundary, version field — everything downstream depends on this (the Python decoder in 4.1 is its other half)
- **3.3** — Addressing: `SYS` (network) + `SRC` (source) tags
- **3.4** — `SEQ` counter + `St` flight-state code replacing the emoji
- **3.5** — Extract launch detection as a host-tested pure unit
- **3.6** — Extract apogee detection as a host-tested pure unit
- **3.7** — Extract unit conversions (raw → g, Pa → altitude) as host-tested units

## Epic 4 — Ground service: logging + dashboard + web + OLED

*Goal: the Pi decodes the native RX stream, logs every flight, shows it live at the pad (dashboard + panel OLED), and publishes it to the web.*

- **4.1** — Python decoder implementing the v1 contract (green the failing test already written; add unknown-tag tolerance + malformed-packet handling)
- **4.2** — Ingest service: read the native radio stream → decoded packets
- **4.3** — Flight logging: per-flight CSV/JSON to disk, with `SRC` + `SEQ` packet-loss / link-quality stats
- **4.4** — Live local dashboard: gauges + altitude trace served on the Pi, viewable from your phone over the hotspot
- **4.5** — Web publish: push flight logs to the repo → render on velezf.github.io (Quarto/JS), one permalink per flight
- **4.6** — Status OLED (Adafruit 938, I²C): shares the I²C bus with the PiSugar at a different address; radio is on SPI. Driven **from a view-model snapshot on its own thread** (amended 2026-07-31 — the original "straight off each decoded packet" is the specification of a defect: it puts rendering on the RX thread, where a display fault can stall capture, and yields no idle page on a quiet pad) — altitude, peak, RSSI/link quality, `SEQ` loss, flight state, and both `SRC:1` + `SRC:2`. Reuses the handheld's OLED rendering; cut a window in the front panel
- **4.7** *(optional)* — Live-to-web during flight via MQTT-over-cell — gated on launch-site coverage

## Epic 5 — 9-DoF integration (LSM6DSOX + LIS3MDL)

*Goal: roll rate and orientation in the rocket's flight record, end to end.*

- **5.1** — Hardware: chain the 9-DoF onto the sled's STEMMA QT I²C bus; confirm reads
- **5.2** — Firmware: gyro/mag sampling + fusion (Madgwick/Mahony); derive roll rate and angle-off-vertical (ADXL375 stays the high-G / launch-detect channel)
- **5.3** — Extend v1 with additive tags (e.g. `Roll`, `Spin`)
- **5.4** — Decoder + dashboard + OLED updates to surface the new fields

## Epic 6 — Relay deployment  *(safety-critical)*

*Goal: the rocket deploys its own ejection charges via onboard relays — armed by a physical pad pin, fired autonomously, engineered to fail safe and ground-tested to your range's bar.*

- **6.1** — Pyro hardware: fire path through the relay's **normally-open** contact (de-energized = no fire, so reset / power loss fails open); charges on a **separate battery rail** broken by a **physical pad-safety pin**; an **e-match continuity** sense line. Confirm the relay's contact rating comfortably exceeds the e-match's all-fire current
- **6.2** — Deploy logic (firmware): fires autonomously on the rocket's own apogee detection; the **physical arm pin gates** the fire logic (disarmed → armed → apogee → fire), host-tested as a pure state machine (TDD); fail-open on reset / power loss
- **6.3** — Ground testing: bench-fire the relays into a test load (no live charge); ground ejection test to size charges + confirm reliable fire; verify nothing fires unarmed and that reset / power-cut fails safe

*(Open call — the last one left: one deployment event vs. apogee + main, decided at build time. The second commits your second relay to a main charge.)*

## Epic 7 — Deployable lander payload  *(`SRC:2`)*

*Goal: a deployable science payload — a second addressed node — that separates at main, descends on a streamer, and radios its own atmosphere + light data home. Realizes the multi-node addressing as the actual mission.*

- **7.1** — Lander brain: KB2040 + the second RFM96W breakout (both on hand); CircuitPython, so the lander firmware is Python; instant-on, no SD card
- **7.2** — Sensors: BME680 (temp / humidity / pressure / VOC) + APDS9960 (light / color) on STEMMA QT I²C; confirm reads
- **7.3** — Lander packet: its own sensor fields on the shared v1 grammar, tagged `SRC:2`; stagger its 1 Hz transmit so it doesn't collide with the rocket's
- **7.4** — Mechanical / boost survival: potted and hard-mounted, secured battery, no breadboard — it rides the same boost-g as the sled
- **7.5** — Separation + recovery: stow in the nosecone and eject forward at main, clear of the main's lines; streamer descent (fast and hard — must survive impact); self-beacon its position (RSSI now, GPS later)
- **7.6** — Ground integration: the ground service logs `SRC:2` as a separate flight record; decoder + dashboard + OLED surface the lander's atmosphere fields

## Epic 8 — Kids' mission-control handheld

*Goal: a rugged hold-in-your-hand display that listens to the broadcast and gets kids leaning in.*

- **8.1** — Hardware: Pi Zero 2 W (with headers, on hand) + the bonnet, secured with M2.5 standoffs; microSD (Pi OS Lite) + the PiSugar 3 for power
- **8.2** — Receiver firmware (Python / Blinka, on top of Adafruit's bonnet demo): listen to the v1 broadcast; OLED shows live altitude, "LIFTOFF!" on `St` → ascent, peak at apogee
- **8.3** — Multi-node display: track both `SRC:1` (rocket) and `SRC:2` (lander) on the one screen
- **8.4** — Guess-the-apogee game: each kid dials a guess with the buttons pre-launch, watches the climb live, and apogee reveals the actual max + who came closest
- **8.5** — Kid-involvement: messages and game logic are a few lines to tweak — let them change the text or the rules

---

## Parking lot (captured, out of core scope)

- **Recovery aids** — a buzzer / strobe finder for the last 50 m, complementing the planned LightAPRS GPS. If both relays go to deployment, a recovery buzzer needs its own switch (a third relay or a low-side MOSFET).
- **Additional TX nodes** — the lander (Epic 7) already exercises the `SYS` / `SRC` addressing; the freed ground-RX Feather M0 is now a candidate host for a third node or a backup RX.
- **Lander GPS** — a PA1010D STEMMA QT for real position instead of RSSI-only; deferred since LightAPRS covers the rocket's position.
