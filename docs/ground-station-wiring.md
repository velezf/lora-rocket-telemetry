# Ground Station Wiring — Apogee Zephyr (`apogee-gs`, Raspberry Pi 5)

Locked pin map for the Pi 5 ground station peripherals. Physical pin numbers refer to
the 40-pin header; BCM = Broadcom GPIO number. Bench-verified 2026-07-07 (radio RX
confirmed against the live V1 sled; OLED + PiSugar on I²C1).

> This is the authoritative wiring reference. The radio's `CS`/`RST` and the OLED's
> address are deliberately chosen to match the handheld bonnet convention so ground and
> handheld code stay in parity.

## RFM96W LoRa radio — SPI0

| Signal | Radio pin | Pi phys pin | BCM GPIO | Notes |
|--------|-----------|-------------|----------|-------|
| Power  | VIN       | **1**       | 3.3 V    | breakout has no regulator — 3.3 V only |
| Ground | GND       | **6**       | GND      | |
| Clock  | SCK       | **23**      | GPIO 11  | SPI0 SCLK |
| MISO   | MISO      | **21**      | GPIO 9   | SPI0 MISO |
| MOSI   | MOSI      | **19**      | GPIO 10  | SPI0 MOSI |
| Select | CS        | **26**      | GPIO 7 (**CE1**) | `/dev/spidev0.1` |
| Reset  | RST       | **22**      | GPIO 25  | active-low |

- **Unconnected:** `EN`, `G0` (DIO0), `G1`–`G5`. The driver **polls** `RegIrqFlags` — no DIO
  interrupt lines are wired. **`DIO0` is deliberately NOT wired** — in particular nothing is on
  **phys pin 15 / GPIO22** (don't confuse it with the wired `RST` on phys pin 22 / GPIO25). A
  rebuild or the Epic 8 handheld does **not** need a DIO0 wire; the polling driver never reads it.
- **SPI baudrate: 1 MHz** in code (breakout reliability).
- **CS/RST = CE1 / D25** to match the handheld bonnet convention for code parity.
- Verified: `RegVersion = 0x12` (SX1276); live RX from the V1 sled at 434.0 MHz,
  BW 125 kHz / SF7 / CR 4-5, PHY CRC on, RadioHead 4-byte header stripped.

## OLED — Adafruit 938 (STEMMA QT rev), I²C1

| Signal | OLED pin | Pi phys pin | BCM GPIO | Notes |
|--------|----------|-------------|----------|-------|
| Power  | VIN      | **17**      | 3.3 V    | |
| Ground | GND      | **9**       | GND      | |
| Data   | SDA      | **3**       | GPIO 2   | I²C1 SDA |
| Clock  | SCL      | **5**       | GPIO 3   | I²C1 SCL |

- **I²C address `0x3D`** (not `0x3C` — board silkscreen confirms).
- `Rst` / `CS` / `A0` / `DC` unwired; the board auto-resets on power-up.

## Front-panel LEDs — active-high

Wiring: `GPIO → series resistor → LED anode`, `LED cathode → GND`. Drive the GPIO **HIGH**
to light the LED.

A bring-up sweep (2026-07-07) mapped each GPIO to its **physical** panel position — the
physical order is **not** the GPIO numeric order (LED3–LED6 were cross-wired in the
harness). Corrected map, by physical position (LED1 = leftmost, LED6 = rightmost):

| LED (L→R) | Color | BCM GPIO |
|-----------|-------|----------|
| LED1 | green | GPIO 5   |
| LED2 | green | GPIO 6   |
| LED3 | green | GPIO 13  |
| LED4 | red   | GPIO 26  |
| LED5 | blue  | GPIO 12  |
| LED6 | blue  | GPIO 16  |

Physical layout, left→right: 🟢🟢🟢 🔴 🔵🔵. Firing sequence in physical order:
GPIO `5, 6, 13, 26, 12, 16`.

Bring-up / troubleshoot with [`ground/tools/led_check.py`](../ground/tools/led_check.py),
whose default pin list is in this physical order.

## Shared-bus notes

- **I²C1** also carries the **PiSugar 3 Plus** UPS: `0x57` (battery) + `0x68` (RTC). No
  address conflict with the OLED (`0x3D`).
- **SPI0** carries only the radio, on **CE1**. CE0 (`/dev/spidev0.0`) is free.

## Time / clock (field hardening)

There is no kernel RTC or `fake-hwclock` — the wall clock comes from NTP at home and
the **PiSugar 3 RTC** (`0x68`) in the field. One-time setup so a network-less boot has
the right date:

```sh
printf 'rtc_pi2rtc\n' | nc -q1 127.0.0.1 8423     # set the RTC from the (NTP-correct) clock
# then set "auto_rtc_sync": true in /etc/pisugar-server/config.json and restart pisugar-server
```

## Boot clock trust (RTC-boot-restore)

The Pi 5 `rtc0` has **no coin cell** (comes up 1970) and nothing read the PiSugar RTC
into the system clock, so `systemd-timesyncd` restored its *saved-clock floor* (= last
shutdown) and the old year-only gate opened a **mis-dated session** — corrected only by
NTP. Fixed by two pieces:

- **`apogee-rtc-restore.service`** (oneshot, `After=pisugar-server`, `Before=apogee-ingest`)
  reads the PiSugar RTC via the pisugar-server API and, only if the system clock is bogus
  or grossly behind the RTC, sets it and drops **`/run/apogee-rtc-restored`**. Never steps
  the clock backward; never writes the session/ops/index (audit → journald only).
- **`apogee-ingest` `ExecStartPre` = `ground.clock.gate`** — **fail-closed**: proceeds only
  if the clock is **NTP-synced OR RTC-restored (marker)**; a plausible-year floor alone no
  longer passes.

Inside the service, **silence/duration use `time.monotonic()` deltas** (immune to NTP/RTC
steps); the wall `received_at` is only what's recorded.

### Field escape hatch (dead RTC + no network)
If ingest won't start (gate fail-closed) at the range, set the clock by hand and attest it via
the `apogee-attest` oneshot. **The procedure is canonical in
[ADR 0003](adr/0003-rtc-boot-restore-clock-gate.md) ("Operator escape hatch")** — not restated
here so the two can't drift.

**Verify (closes the checklist item):** power off ≥30 min, boot with **Wi-Fi OFF** — `date`
should be correct and the new session correctly named, with **no NTP**.

The **Epic 8 handheld** (Pi Zero 2 W + PiSugar 3) has no `rtc0` either, so the software
RTC-boot-restore is the *only* path there — replicate this config.

## Power — auto-shutdown + wake-on-charge (PiSugar)

The PiSugar 3 governs power both ways, in `/etc/pisugar-server/config.json` (restart
`pisugar-server` after changes):

- **Low-battery auto-shutdown (Epic 2.6):** `auto_shutdown_level: 5`, `auto_shutdown_delay: 30`
  — graceful shutdown at 5 % after 30 s.
- **Wake-on-charge:** `auto_power_on: true` — the box auto-boots when power is **(re)connected**.

**Rising-edge semantics (the fact to remember in six months):** `auto_power_on` fires on the
**transition** of external power being connected, *not* on power merely being present. Therefore:

- `poweroff` with the charger **already plugged stays off** — no new connection edge. Verified
  2026-07-27: powered off charger-connected, stayed dark >100 s, no bounce. **`poweroff` means
  off**; there is no "boots in the bag" footgun unless the charger is unplugged/replugged.
- **Unplug→replug** (or connecting power to a dead pack) **boots it** — verified 2026-07-27 (woke
  on the replug rising edge). This is the field-recovery complement to auto-shutdown: a pack that
  shut down at 5 % comes back by reconnecting power, no button press.

If the box ever wakes unexpectedly, suspect a **power reconnect** (loose barrel jack, charger
re-seating), not a timer.

### Graceful shutdown — the button off-switch

Headless field off-switch so a shutdown closes the append-only session log cleanly (a raw power
cut can truncate the last JSONL line). Config in `/etc/pisugar-server/config.json`:

- `double_tap_enable: true`, `double_tap_shell: "/usr/bin/systemctl poweroff"` — a **double-tap**
  runs an orderly shutdown (ingest SIGTERM → writes `service_stop` + drains the queue → then
  `pisugar-poweroff` cuts the rails). Full path to `systemctl` (no PATH-dependence).
- `soft_poweroff: true`, `soft_poweroff_shell: "/usr/bin/systemctl poweroff"` — the same graceful
  command backs the **low-battery** path too (one definition of "graceful off", two triggers).
- `single_tap_enable: false`, `long_tap_enable: false` — only double-tap acts (anti-mistouch).
- `anti_mistouch: true` (runtime default) — guards against a stray single touch.

**The PiSugar 3 has two physical buttons:** the **tap-gesture button on the USB-C side** (the one
the `double_tap` config drives) and a **power button on the micro-USB side**. Use the USB-C-side
double-tap as the normal off-switch.

**Validated 2026-07-30 (both paths close the log cleanly):**
- **USB-C double-tap** → session `…266cc9` ended with a valid-JSON `service_stop` as its final
  record. No truncation. Confirms the SIGTERM drain completes before `pisugar-poweroff`'s 3 s
  countdown (services stop *before* `shutdown.target` pulls the rail-cut — no race).
- **micro-USB button, ~5 s hold** → session `…3915db` **also** closed cleanly (`service_stop`
  present). Surprising for a button described as "hard shutoff" — it behaves as an orderly
  power-key signal, **not** a raw truncating cut, at least at ~5 s. A genuine truncating cut would
  need a power pull / much longer hold — **not established, not chased** (the graceful path is
  proven, which is what matters). Do not assume this button truncates; the evidence says it didn't.

**Explicit for future readers:** at ~5 s the micro-USB button closed the log **cleanly**. We have
**NOT established that any hold length force-cuts / truncates** on either button. Do not assume a
destructive path exists and avoid a harmless action; if a true raw cut is ever needed, it is
unverified and would require a power pull.
