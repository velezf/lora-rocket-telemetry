# Kids' mission-control handheld 🎮📡

**Epic 8.** A rugged, hold-in-your-hand display that listens to the 434 MHz LoRa
broadcast and gets kids leaning in — live altitude, a big **"LIFTOFF!"** on ascent,
the apogee reveal, and a guess-the-apogee game.

It's a **receive-only** node on the project's shared
[v1 packet contract](../README.md) — one more listener alongside the Pi 5 ground
station, with no RX firmware (native `adafruit_rfm9x`, the Epic 2.5 pattern).

> **Status: platform groundwork only.** The project is at Epic 1–2; Epic 8 is an
> optional node. This folder currently holds the **provisioning runbook**, the
> [platform ADR](docs/adr/0001-handheld-receiver-platform.md), and the reproducible
> Python env. The PiSugar 3 and SRH805S antenna are still on order, so the radio/OLED
> haven't been bench-brought-up yet, and the receiver firmware (8.2–8.5) isn't written.

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

## This folder

| Path | What |
|------|------|
| [`docs/adr/0001-handheld-receiver-platform.md`](docs/adr/0001-handheld-receiver-platform.md) | why Pi Zero 2 W + bonnet + PiSugar |
| `pyproject.toml`, `uv.lock`, `.python-version` | the verified, reproducible bonnet env (mirrors `~/radio` on the device) |

## Roadmap (Epic 8)

- **8.2** Receiver firmware — listen to v1, OLED shows altitude / LIFTOFF / apogee
- **8.3** Multi-node — track `SRC:1` (rocket) + `SRC:2` (lander) on one screen
- **8.4** Guess-the-apogee game — kids dial a guess on the buttons; apogee reveals the winner
- **8.5** Kid-tweakable messages + rules
