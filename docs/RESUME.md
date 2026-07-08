# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: 2026-07-08 (Claude, on Mac + Pi 5 over SSH)._

## Where we are

**Epics 1–3 complete; Epic 4 (ground service) substantially built and merged.** Epic 1
(Mac PlatformIO) done, 1.4 upload proven on the Feather M0. The v1 packet contract is
locked as ADR 0001. Epic 2 ground station (`apogee-gs`) up: peripherals wired, native LoRa
RX driver (`ground/rx/`, raw spidev+lgpio; ADR 0002), PiSugar shutdown. Epic 3: the sled TX
emits ADR v1, e2e-verified against the ground driver + decoder.

**Epic 4 — 4.1 decoder, 4.2 ingest service, and 4.3 flight logging are all merged.** A single
radio-owning `apogee-ingest` **systemd service** (enabled, reboot-surviving): SX127x driver →
decoder → append-only JSONL session log + per-`(SYS,SRC)` link stats + foreign-traffic &
Part-97 callsign policy + **live flight detection** (advisory `flight_open`/`flight_close`
events). Plus an offline **flights CLI** (`rebuild`/`list`/`annotate`/`close`/`open`/`export`)
over a three-files/one-writer model (session ← service, ops journal ← CLI, index ← derivation).
**Next: 4.4 dashboard (Flask + Chart.js) + 4.6 status OLED**, both consuming 4.2. Epic 8
groundwork merged.

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
| 4 — Ground service (decode/log/dash/web/OLED) | 🟢 **4.1–4.3 done & merged.** 4.1 decoder (`ground/decode/`, structured errors, additive-tag policy); 4.2 **ingest** (`ground/ingest/` + `apogee-ingest.service` — radio owner → JSONL log + `LinkStats` + foreign-SYS/unknown-SRC + Part-97 callsign audit; enabled, reboot-surviving); 4.3 **flight logging** (`ground/flights/` — journal-based segmentation, concurrent multi-bird flights, export, CLI; index = f(session, ops), manual ops beat silence). Full ground suite 91 tests. **Remaining: 4.4 dashboard, 4.6 OLED, 4.5 web publish.** |
| 5 — 9-DoF integration | 🟡 **5.1 hardware evidence done** (LSM6DSOX 0x6a + LIS3MDL 0x1c on the sled bus; WHO_AM_I 0x6C/0x3D; sane gyro/mag). 5.2–5.4 not started; `Roll`/`Spin` reserved (ADR 0001 App. A). |
| 6 — Relay deployment (safety-critical) | ⏳ Not started. |
| 7 — Lander payload (`SRC:2`) | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 8 — Kids' handheld | 🟡 **8.1 platform groundwork merged** (PR #1, `handheld/`). Bench bring-up pending PiSugar 3 + SRH805S antenna (both ordered). 8.2–8.5 not started. |

## Open branches (pending review/merge)

**None** — all Epic 1–4.3 work is merged and pushed to `origin/main`. Recent merged
branches: `feat/ground-decoder`, `feat/ingest-{linkstats,records,flights-model,service}`,
`feat/callsign-id`, `feat/flight-logging` (+ earlier Epic 1–3 branches).

## Locked decisions

- **Packet format v1** ([ADR 0001](adr/0001-packet-format-v1.md)): keyed `KEY:VALUE` ASCII,
  leading `V:1`; `MET` time token; **no app-layer checksum** (rely on LoRa PHY CRC); `SYS`
  default `7`; `SRC` `1=sled, 2=lander`; additive tags tolerated, unknown tags ignored.
  Human-readable index: [`docs/telemetry-dictionary.md`](telemetry-dictionary.md).
- **Ground RX = raw spidev + lgpio** ([ADR 0002](adr/0002-ground-rx-driver-spidev.md)),
  Blinka rejected on Pi 5.
- **Ground service (Epic 4):** one radio-owning process fans out
  `Observation(received_at, rssi, packet)` to consumers — **time is injected, no consumer
  reads a clock.** Three files, one writer each: session JSONL (service), ops journal (CLI),
  flights index (derivation); **index = pure f(session, ops)**; a **manual close/open beats
  the silence timeout.** Foreign-SYS / unknown-SRC counted + logged as advisory events,
  **never** into stats/flights (SYS allowlist + known-SRC are field config, not repo
  constants). Flight **close = 90 s silence or manual CLI** (auto-landed deferred — no St
  code). **Dashboard = Flask + Chart.js** (live); **4.5 flight pages = Quarto + pandas +
  Plotly → velezf.github.io** (one permalink per flight).
- **ADR numbering:** global `docs/adr/` and per-component logs both fine.

## Epic 6 firmware riders (deferred — additive; each re-runs the e2e gate)

1. **SRC per-unit build config** (`-DSRC_ID` per device env) — never a shared constant; two
   sleds from one repo must not both claim `SRC:1`.
2. **±10 % TX-interval jitter** — anti-lockstep for simultaneous birds.
3. **Part-97 station ID** — `CALL:<callsign>` at TX start / ≤9.5 min / graceful shutdown,
   per-unit `-DCALLSIGN`. Ground side (decoder fixture + ingest `id` audit + CALL↔SYS
   binding) already merged; the **lander (Epic 7) inherits the ID-timer obligation.**

## Immediate next steps

1. **4.4 dashboard** (Flask + Chart.js): live-state snapshot + recent-packet ring buffer,
   gauges + altitude trace, phone-viewable; bench-test over home Wi-Fi first.
2. **4.6 status OLED** (`luma.oled` on I²C1 `0x3d`; verify vs PiSugar `0x57`): altitude /
   peak / RSSI / SEQ-loss / flight-state per SRC. Reuse the handheld rendering.
3. **4.5 web publish** (after the 4.3 export format settles): Quarto + pandas + Plotly
   per-flight pages → velezf.github.io.
4. **2.2 hotspot field test** + **assign the 6 panel-LED functions** (from decoded packets).
5. **Field/motion test:** shake the sled hard (g > 3 → St ascent) to watch a live
   `flight_open`→`flight_close` cycle end-to-end.

## Notes / gotchas

- **Standing merge gate:** the e2e check (sled TX → `ground/rx/` driver → payload matches
  the ADR fixtures) caught the newlib-nano float-printf bug that host tests could NOT —
  **keep the e2e check as a required gate for anything touching encode/decode.**
- **newlib-nano `%f`:** float printf is off by default → the feather env carries
  `-Wl,-u,_printf_float` (float tags encode empty on-target otherwise, though host tests pass).
- **Feather M0 re-flashing:** first upload of a session works; re-flashes reliably need a
  **manual double-tap to bootloader** (SAM-BA flake). See memory `feather-m0-flash-double-tap`.
- **Ground data on the Pi** (not in repo): session logs `~/apogee-data/session-*.jsonl`
  (service-written) + `flights-snapshot.json` (disposable derivation cache). The old
  `rx_test.py` / `rx_driver_check.py` scratch scripts were deleted in the 4.2 branch.
- **One radio owner:** `apogee-ingest.service` owns SPI continuously — stop it
  (`sudo systemctl stop apogee-ingest`) before any direct radio work; never a second owner.
