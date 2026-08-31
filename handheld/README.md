# Kids' mission-control handheld 🎮📡

**Epic 8.** A rugged, hold-in-your-hand display that listens to the 434 MHz LoRa
broadcast and gets kids leaning in — live altitude, a big **"LIFTOFF!"** on ascent,
the apogee reveal, and a guess-the-apogee game.

It's a **receive-only** node on the project's shared
[v1 packet contract](../README.md) — one more listener alongside the Pi 5 ground
station, with no RX firmware (native `adafruit_rfm9x`, the Epic 2.5 pattern).

> **Status (2026-08-31): 8.2 BUILT and BENCH-VERIFIED ON AIR.** The receiver
> (`app/`) ran against the live sled on the bench — 56 frames accepted, zero
> decode/render/RX errors — and runs as `apogee-handheld.service`, enabled for
> boot: every power-on brings up the OLED idle page unaided. Architecture:
> [ADR 0002](docs/adr/0002-receiver-reuses-ground-modules.md) — the app reuses
> the ground decoder, `LoRaConfig`, and `pad_baseline` from the repo checkout;
> no handheld copies. **Parked:** the PiSugar's I²C is dead (powers the board,
> `0x57`/`0x68` absent; `pisugar-server` answers "I2C not connected") — pogo-pin
> contact needs solder work, so battery %, RTC, and button events wait on that.
> 8.3 (multi-node) waits on the Epic 7 lander; 8.4–8.5 (game) not started.

## Hardware (Epic 8.1)

| Part | Role | Notes |
|------|------|-------|
| Pi Zero 2 W (headers) | compute | 512 MB RAM |
| Adafruit LoRa Radio Bonnet **RFM96W** | 434 MHz LoRa RX (SPI) | onboard SSD1306 128×32 OLED @ I²C `0x3C` + 3 buttons (D5/D6/D12) |
| PiSugar 3 | battery UPS + safe shutdown | *ordered* |
| BaoFeng SRH805S antenna | antenna | *ordered* — SMA-**female**, so the bonnet pigtail must present SMA-**male** |
| microSD + Pi OS Lite 64-bit, M2.5 standoffs | OS / mechanical | |

## Provisioning runbook

Verified on this Pi 2026-06-29 (Pi OS Lite 64-bit, Debian 13 Trixie, kernel 6.18).
Reproducible from a fresh card.

**0. Image the card** with Raspberry Pi Imager → Pi OS Lite (64-bit). In the gear
settings: set hostname, enable **SSH (public-key only)**, your Wi-Fi, locale. First
boot comes up headless on Wi-Fi.

**1. Update the OS**
```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade
```

**2. Enable the buses** the bonnet needs (radio on SPI, OLED on I²C):
```bash
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo apt-get install -y i2c-tools          # for i2cdetect
```

**3. PiSugar Power Manager** (battery %, RTC, safe shutdown; web UI on :8421):
```bash
curl https://cdn.pisugar.com/release/pisugar-power-manager.sh | sudo bash
```
Set a web-UI login in `/etc/pisugar-server/config.json` (`auth_user` / `auth_password`)
and `sudo systemctl restart pisugar-server` — it's open on the LAN otherwise.

**4. Python env with [uv](https://docs.astral.sh/uv/)** (the project's Python tool):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh        # installs uv to ~/.local/bin
cd ~/radio && uv sync                                   # this folder's pyproject/uv.lock
```
The env is Blinka + `rfm9x` + `ssd1306` + `pillow`, plus **`rpi-lgpio`** (the GPIO
shim Blinka needs on kernel 6.x — the stock `RPi.GPIO` is broken on the new pinctrl).
Building `lgpio` from source needs `sudo apt-get install -y swig gcc python3-dev liblgpio-dev`.

**5. Verify** once the bonnet + antenna are attached (HAT seated, then reboot):
```bash
i2cdetect -y 1            # expect 0x3C (OLED) and, with PiSugar, 0x57
ls /dev/spidev0.*         # radio bus present
```

### Gotcha: don't add `zram-tools`

Pi OS Trixie already provides zram swap via `systemd-zram-generator`
(full-RAM zstd + writeback). Installing `zram-tools` creates a **second** manager that
fights it over `/dev/zram0` and leaves a failed unit. The built-in is already optimal —
leave it alone. (Trixie also dropped `dphys-swapfile`.)

## Access & operations (recorded 2026-08-31 — facts live HERE, cite elsewhere)

- **Hostname `apogee-handheld`** (mDNS `apogee-handheld.local`), user
  **`rocketman`**, key-only SSH. On the home **WideRoad** Wi-Fi (its 2.4 GHz
  side — the Zero's radio proved it exists by scanning it), NM profile
  `WideRoad` at autoconnect-priority 100; the original `WideRoadGuest`
  netplan profile remains as fallback. **Do not develop against the guest
  network**: its client isolation intermittently blocks ICMP, mDNS, *and*
  TCP between clients (an afternoon was spent learning this).
- **Service:** `apogee-handheld.service` (systemd, enabled) runs
  `~/radio/.venv/bin/python -m handheld.app.main` from the repo checkout at
  `~/lora-rocket-telemetry` (deploys are `git pull`, per ADR 0002). Stop
  prints a counters line (`accepted/decode_errors/foreign_sys/rx_errors/`
  `render_errors`) — restart it to sample counters.
- **PiSugar: WORKING since Frank's second solder pass, 2026-08-31** —
  `0x57`/`0x68` on the bus, battery gauge live, RTC on wall time, and it
  powers the stack alone (verified with a clean unattended boot that picked
  up the sled). Full stack installed (`pisugar-server` + `pisugar-poweroff`
  + `pisugar-programmer`, 2.3.2-1 — matches the Pi 5) with the Pi 5's
  operational config ported and now LIVE: wake-on-charge, RTC sync,
  anti-mistouch, 5 %/30 s auto-shutdown, **double-tap → clean poweroff**,
  soft_poweroff (backup `config.json.bak-20260831`). Web UI
  `http://apogee-handheld.local:8421`, user `admin`; password is Frank's
  standard PiSugar one (secrets never in this repo — same rule as the
  hotspot secret). The receiver polls `get battery` on TCP :8423 every ~30 s
  for the idle-page gauge. History of the pogo-pin failure: RESUME's
  2026-08-31 handoff.
- **USB-ethernet gadget VERIFIED 2026-08-31:** one data micro-USB cable from
  the middle port ("USB", beside mini-HDMI) to the Mac supplies power AND a
  link-local network — the Mac gets an interface at the pinned MAC and
  `ssh apogee-handheld.local` works over the cable, router-free. PWR IN has
  no data lines, ever. Diagnostic freebie: a Zero enumerating on the Mac as
  `BCM2710 Boot` is powered fine but cannot find a bootable SD card.

## This folder

| Path | What |
|------|------|
| `app/` | the 8.2 receiver: `viewmodel`/`render`/`rx`/`oled`/`loop` (pure, host-tested) + `main.py` (thin Blinka glue) |
| `tests/` | host tests — run `.venv-test/bin/pytest handheld/tests/` from the repo root (Mac) |
| [`docs/adr/0001-handheld-receiver-platform.md`](docs/adr/0001-handheld-receiver-platform.md) | why Pi Zero 2 W + bonnet + PiSugar |
| [`docs/adr/0002-receiver-reuses-ground-modules.md`](docs/adr/0002-receiver-reuses-ground-modules.md) | why the app imports ground modules from the checkout (no copies, no packaging) |
| `pyproject.toml`, `uv.lock`, `.python-version` | the verified, reproducible bonnet env (mirrors `~/radio` on the device) |

## Roadmap (Epic 8)

- **8.2** ✅ Receiver firmware — BUILT + on-air bench 2026-08-31 (see Status). Boot test WITNESSED same day: unattended power-on → idle page, service active at 0 min. AGL fix verified on the running bonnet (`-85ft` → `0ft`). Slice 6: battery % on the idle page (pisugar-server gauge).
- **8.3** Multi-node — track `SRC:1` (rocket) + `SRC:2` (lander) on one screen *(waits on the Epic 7 lander)*
- **8.4** ✅ Guess-the-apogee — BUILT 2026-08-31, button flow bench-tested by Frank same day (`app/game.py`): the screen prompts each kid **by name** (`Bacon? 350ft`), #5 up / #6 down, and **#12 twice** — first shows `Bacon 350 OK?`, second banks it and seats the next kid (dialing during the OK? cancels; field feedback: one-press lock was guaranteed kid-fumble). Liftoff closes betting (an unlocked dial still banks), the apogee screen names the winner (ties → earlier in the roster), a sled power-cycle auto-resets the round. RSSI sits top-right on the live page so the dial owns the bottom row.
- **8.5** Kid-tweakable messages + rules — the knobs (`PLAYERS`, `RULE`, `STEP_FT`, `START_FT`) sit at the top of `app/game.py` with instructions; edit + service restart. `RULE`: `"closest"` (absolute distance, default) or `"no-over"` (Price-Is-Right — busting loses; everyone busts, the rocket wins)
