# ADR 0001 — Handheld receiver platform: Raspberry Pi Zero 2 W

- **Status:** Accepted (platform groundwork)
- **Date:** 2026-06-29
- **Scope:** Epic 8 — Kids' mission-control handheld (8.1)
- **Project status when written:** Epic 1–2. Epic 8 is an optional node, not on the
  critical path to first flight. This ADR + runbook were captured opportunistically
  while the Pi Zero 2 W happened to be on the bench; they are **groundwork**, not
  active feature work.

## Context

Epic 8 wants a rugged, hold-in-your-hand display that listens to the live LoRa
broadcast and gets kids leaning in — altitude climbing in real time, a big
"LIFTOFF!", and the apogee reveal (8.2–8.4).

It is a **receiver only**, and just one more node on the project's shared grammar:

- The **v1 packet format** is the single contract for every node (locked in Epic 3.2):
  ```
  V:1 SYS:7 SRC:1 SEQ:42 ALT:1234ft Max:5678ft G:2.3 Pg:9.1 T:21.5C Batt:3.92V St:1 t+12s
  ```
  `V` version · `SYS` network · `SRC` source vehicle · `SEQ` counter · flight fields ·
  `St` state (0 pad / 1 ascent / 2 descent). New tags are additive. The handheld
  decodes this same string — it tracks `St` for LIFTOFF/apogee and `SRC` for the
  multi-node view (8.3). *(The current sled firmware still emits the legacy
  emoji-string telemetry; it migrates to v1 in Epic 3.1–3.4. The handheld targets v1.)*
- **Native-Pi RX** is already the project's RX pattern (Epic 2.5): `adafruit_rfm9x`
  at 434 MHz mirroring the sled's RadioHead modem config, SPI baud ~1 MHz, accept the
  `0xFF` broadcast address; the library strips the 4-byte RadioHead header and hands
  the payload to the decoder. The handheld **reuses this pattern** — there is no RX
  firmware anywhere in the project.

Constraints: battery powered and genuinely handheld; same 434.0 MHz signal; a small
display and a few buttons; and game logic/messages that are a few lines to tweak (8.5).

## Decision

Build the handheld on a **Raspberry Pi Zero 2 W** with:

| Part | Role | Status |
|------|------|--------|
| Pi Zero 2 W (with headers) | compute | have |
| Adafruit LoRa Radio Bonnet **RFM96W** + onboard SSD1306 128×32 OLED (I²C `0x3C`) + 3 buttons (D5/D6/D12) | 434 MHz receive (SPI) + display + game input | have |
| PiSugar 3 | LiPo UPS + battery gauge + clean shutdown | **ordered** |
| BaoFeng **SRH805S** antenna (SMA-female → bonnet pigtail must present SMA-male) | antenna | **ordered** |
| microSD + Raspberry Pi OS Lite 64-bit; M2.5 standoffs | OS / mechanical | have |

Software: **Python + Adafruit Blinka** on top of Adafruit's bonnet demo, using
`adafruit-circuitpython-rfm9x` (radio) and `adafruit-circuitpython-ssd1306` (OLED),
environment managed with **uv**. GPIO via the **`rpi-lgpio`** shim — the real
`RPi.GPIO` is broken on the kernel-6.x pinctrl, and `rpi-lgpio` is the drop-in
replacement Blinka's BCM283x backend imports as `RPi.GPIO`.

Radio at **434.0 MHz** to match the sled and ground station. The RFM96W is the
433 MHz-band variant and covers 434 fine.

## Consequences

- **Linux + Python** makes the kid-facing logic (8.5) trivial to edit in the field —
  no recompile/reflash like the Feather sled (the project's only C++).
- **512 MB RAM** is tight. Pi OS Trixie ships zram swap by default via
  `systemd-zram-generator`; we rely on that and **do not** add `zram-tools`
  (it fights the built-in over `/dev/zram0` — see runbook).
- **Headless**, provisioned over SSH (key-only) + Raspberry Pi Connect.
- **PiSugar 3** gives battery %, a soft power button, and safe shutdown — right for a
  device kids hold and switch off. (Software is installed now; the HAT itself is
  on order, so the I²C bus currently scans empty at `0x57`.)
- **Passive RX:** the handheld never transmits, so it cannot interfere with the
  telemetry link or the ground station's ACKs.

## Status / next steps (all later Epic 8 work)

- Hardware assembly is pending the **PiSugar 3 + SRH805S antenna** (both ordered).
- Bench bring-up (radio answers over SPI, OLED lights) is pending the antenna/HAT.
- Receiver firmware (8.2), multi-node display (8.3), apogee game (8.4), and the
  kid-tweakable message/rule layer (8.5) are all still to be built. Deliberately not
  started here — the receiver code will live alongside the ground-side v1 decoder
  patterns from Epic 4.

## Alternatives considered

- **Another Feather M0 + small display** — no Linux, so 8.5's "kids edit the rules in
  a few lines" becomes a reflash cycle; rejected.
- **LePotato / larger SBC** — not handheld; the Pi 5 is already the ground station.
- **ESP32 + LoRa** — capable, but a separate firmware port and loses the easy Python story.
