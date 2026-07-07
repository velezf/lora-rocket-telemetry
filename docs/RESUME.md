# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: 2026-07-07 (Claude, on Mac + Pi 5 over SSH)._

## Where we are

Foundations are down. Epic 1 (Mac PlatformIO toolchain) is built and merged; the v1
packet contract — the keystone everything downstream depends on — is **locked and
published** as ADR 0001. The Epic 2 ground station (`apogee-gs`) is software-complete
(2.1–2.4 + Pi Connect: on the network, remote-reachable, Claude Code authenticated,
repo cloned). The 2.5/2.6 **peripheral hardware is now wired and bench-verified**
(radio on SPI0 **CE1** → RegVersion `0x12`, OLED at I²C `0x3d`, PiSugar battery `0x57`
+ RTC `0x68`, plus six front-panel LEDs); **live RX from the V1 sled confirmed**. Only
the radio **RX software** env (2.5) remains. Next up is the Epic 3
firmware build (all host-testable; no board needed yet). Epic 8 has its platform
groundwork merged.

## Ground station (`apogee-gs`) — access

- **SSH:** `ssh rocketman@apogee-gs.local` (key auth, passwordless sudo).
- **Pi Connect:** signed in as device `apogee-gs` (`rpi-connect-lite`, remote shell;
  no screen sharing — headless). Reachable from anywhere, not just the local network.
- **Claude Code:** installed (`2.1.197`), on PATH (`~/.local/bin`), **authenticated** via
  `claude auth login` (claude.ai, Max). Headless `claude -p` works.
- **OS:** Raspberry Pi OS 64-bit, **Trixie / Debian 13** (not Bookworm). **Python 3.13.5**
  (`/usr/bin/python3`), `venv` works. No system `pip` (PEP 668 externally-managed — use
  venv/uv); **`uv` not yet installed** (wanted for the Epic 4 ground service).
- **Repo:** cloned at `~/lora-rocket-telemetry` via a **read-only deploy key**
  (`apogee-gs`); `git pull` works.
- **Wi-Fi:** home **WideRoad** (priority 0) first, **iPhone 17 hotspot** fallback
  (priority −10, infinite retry, persistent NM keyfile). Networking is netplan-rendered
  → NetworkManager. _(Hotspot secret lives only on the Pi, never in this repo.)_

## Wired peripherals (bench-verified 2026-07-07)

| Device | Bus | Address / CS | Notes |
|--------|-----|--------------|-------|
| RFM96 LoRa radio | SPI0 | **CE1** (`/dev/spidev0.1`, pin 26); RESET GPIO25 (pin 22) | `RegVersion 0x12`. Use `CS=board.CE1`, `RESET=board.D25`. **Not CE0** (originally doc'd as CE0; wire is on CE1). |
| OLED (Adafruit 938, SSD1306 128×64) | I²C-1 | `0x3d` | driven via `~/gs-venv` + **`luma.oled`** |
| PiSugar 3 Plus UPS | I²C-1 | `0x57` batt, `0x68` RTC | `pisugar-server`; `get battery` on TCP :8423 |
| Front-panel LEDs ×6 | GPIO | `5,6,13,26,12,16` (L→R: grn×3, red, blu×2) | active-high; bring-up via `ground/tools/led_check.py` |

OLED software lives in `~/gs-venv` (venv) using **`luma.oled`**. Adafruit **Blinka was skipped**:
its `RPi.GPIO`/`rpi_ws281x` wheels won't build on Pi 5 without `python3-dev`, and RPi.GPIO
doesn't run on BCM2712 anyway — revisit only if Epic 4.6 wants to reuse the handheld's
adafruit rendering. `rocketman` is in `spi`/`i2c`/`gpio` groups; `i2cdetect` is in `/usr/sbin`.

**Authoritative pin map:** [`docs/ground-station-wiring.md`](ground-station-wiring.md) — radio,
OLED, and the corrected front-panel LED harness map (the harness was cross-wired L3–L6).

## Epic status

| Epic | Status |
|------|--------|
| 1 — PlatformIO dev env (Mac) | ✅ **Done & published** (1.1–1.3). 1.4 upload smoke **deferred — hardware-gated** (no Feather M0). |
| 2 — Pi 5 ground-station bring-up | 🟢 **Software side done + peripheral HW wired & bench-verified.** 2.1–2.4 + Pi Connect (OS baseline, headless SSH, I²C+SPI, Python 3.13, Wi-Fi home→hotspot, Claude Code auth, deploy-key clone). **2.5/2.6 hardware verified 2026-07-07:** RFM96 on **SPI0 CE1** (RegVersion 0x12), OLED I²C **0x3d**, PiSugar battery **0x57** + RTC **0x68** (~84%); OLED text confirmed; **6 front-panel LEDs mapped & verified** (harness was cross-wired L3–L6 — corrected map in [`ground-station-wiring.md`](ground-station-wiring.md)); **live RX from the V1 sled confirmed**. LED *functions* not yet assigned (Epic 4). **Remaining: 2.5 radio-RX software; hotspot fallback field test.** |
| 3 — Sled TX firmware + contract | 🟡 **Contract locked & published (ADR 0001).** Firmware build not started. |
| 4 — Ground service (decode/log/dash/web/OLED) | ⏳ Not started. 4.1 decoder can begin against the published ADR. |
| 5 — 9-DoF integration | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 6 — Relay deployment (safety-critical) | ⏳ Not started. |
| 7 — Lander payload (`SRC:2`) | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 8 — Kids' handheld | 🟡 **8.1 platform groundwork merged** (PR #1, `handheld/`). Bench bring-up pending PiSugar 3 + SRH805S antenna (both ordered). 8.2–8.5 not started. |

## Open branches (pending review/merge)

**`feat/gs-bringup`** (Epic 2.5/2.6) — pushed to origin, **awaiting review/merge**. Commits:
`docs(ground-station): add wiring reference + LED bring-up tool` and
`docs(resume): Epic 2.5/2.6 hardware wired & bench-verified`. After it merges, the next
branch is `feat/sled-firmware-v1` (Epic 3).

## Locked decisions

- **Packet format v1** ([ADR 0001](adr/0001-packet-format-v1.md)): keyed `KEY:VALUE`
  ASCII, leading `V:1`; time token `MET:12`; **no app-layer checksum** (rely on LoRa PHY
  CRC); `SYS` default `7`; `SRC` registry `1=sled, 2=lander`. Battery *status* derived on
  the ground (payload carries raw `Batt:` volts only).
- **ADR numbering:** global `docs/adr/` **and** per-component logs (e.g.
  `handheld/docs/adr/`) are both fine.

## Immediate next steps

1. Build the **2.5 radio-RX software** in `~/gs-venv`: add `adafruit-circuitpython-rfm9x`
   (I²C OLED already works via `luma.oled`); wire a live RX read with `CS=CE1`, then decode
   against ADR 0001. (`uv`/Blinka optional; Blinka needs `python3-dev` + lgpio on Pi 5.)
2. Start **`feat/sled-firmware-v1`** for Epic 3, RED→GREEN per task, in dependency order:
   3.7 conversions → 3.5 launch → 3.6 apogee → 3.4 `St`+`SEQ` → 3.3 `SYS`/`SRC` →
   3.2 packet encoder (asserts ADR golden vector) → 3.1a port to `src/` (compile-only,
   `pio run -e feather_m0_tx`). Each pure unit obeys the `lib/` purity rule.
3. **Hardware day (batched, needs the Feather M0):** 1.4 upload smoke + 3.1b flash &
   parity diff vs. the V1 `.ino`.
4. **Field test (away from home Wi-Fi):** confirm `apogee-gs` falls back to the iPhone
   hotspot (`iwgetid -r` / `nmcli` should show the hotspot SSID).

## Hardware gating

No Feather M0 on hand. Everything in Epic 3 except 3.1b is native/host-testable on the
Mac or Pi. The first `pio run -e feather_m0_tx` (3.1a) also doubles as the first real
compile of Epic 1's pinned `lib_deps` against the SAMD target.
