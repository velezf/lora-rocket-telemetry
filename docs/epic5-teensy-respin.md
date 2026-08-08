# Epic 5 — Teensy 4.1 sled respin: onboard fusion + SD flight recorder

**Status:** PLANNED 2026-08-08 (direction decision by Frank). No code until after F2 —
see Sequencing, which is firm.

## Direction and rationale

Epic 5 becomes a **sled respin onto a Teensy 4.1** (on hand; second RFM9x breakout on
order), carrying onboard attitude fusion and an SD flight recorder.

- **The M7 + FPU makes 5.c's measurement gate moot.** The SAMD21 soft-float question
  ("does Mahony fit at ≥100 Hz?") was the fork that could have forced fixed-point or a
  respin; the respin is now the decision, and Mahony runs at any rate we want. A sanity
  timing at bring-up is free and worth one line of evidence, but nothing gates on it.
- **The built-in microSD slot IS the onboard flight recorder.** Spin spectra — closed as
  impossible live at any encoding (RESUME, "EPIC 5 RE-SCOPED 2026-08-08": the
  integrator-integrity leg) — become a **logged post-recovery product at full sample
  rate**, while live attitude streams at 10 Hz.
- **C2's dump-over-radio design dissolves into "log to SD, pull the card."** C2's
  join/provenance analysis (RESUME, backlog entry "C2 — RADIO DUMP of the in-RAM
  high-rate buffer") **carries over VERBATIM as the SD integration design** — vehicle
  record vs ground record, SEQ as join key, one authoritative source per field,
  byte-identical rebuild with an optional derivation input. Cite it; do not re-derive
  it. `docs/epic6-plan.md:626` already concluded C2 improves zero published numbers —
  consistent with it dissolving into a logging path rather than a radio path.

## Sequencing — FIRM

**The 10 Hz rewrite finishes and FLIES on the Feather first (F2). Teensy work begins
after F2.** No MCU respin stacks onto an unflown RF rewrite: two revolutions with no
flight between them means failures that cannot be attributed to either.

## 1. Port-cost audit (measured 2026-08-08, base `0ca46dc`)

- **`firmware/lib/` is PURE — zero board includes across all five units** (`apogee`,
  `launch`, `packet`, `convert`, `profile`). Verified by grepping for real `#include`
  lines, not keywords: the keyword grep first returned every header, because the purity
  comments ("no `<Arduino.h>`, no RadioHead") match their own prohibition — the pgrep
  self-match class, in grep form. The include-anchored grep returns nothing.
- **The entire port surface is `firmware/src/main.cpp`** — 203 lines, 32 of them
  touching board APIs (pins, `Wire`, `Serial`, `rf95`, `millis`, `analogRead`) — plus a
  new `platformio.ini` env. The detectors, encoder, conversions and the profile harness
  move without edits; so do their 45 native tests.
- **New env:** `[env:teensy41_tx]` — `platform = teensy`, `board = teensy41`,
  `framework = arduino`. Pin/SPI-CS assignments for the external RFM9x replace the
  Feather's hardwired 8/3/4.
- **RadioHead on Teensy 4.1: INFERRED, verify by resolution at env creation.** The
  pinned 1.120.0 supports Teensy via `RH_PLATFORM_ARDUINO`/`TEENSYDUINO`, and Teensyduino
  ships its own tested RadioHead port — but the installed copy's grep showed only a
  Teensy 3.x macro, so this is not yet evidence for the 4.1. The verification is the
  same as Epic 5.1's integrity rule: add the env, build from scratch, show the
  dependency graph — not eyeballs on a header.
- **Sensor libraries** (Adafruit BMP3XX / ADXL375 / LSM6DS / LIS3MDL) are
  Arduino-portable: INFERRED fine on Teensy, same resolution-verification applies.
- **`analogRead(A7)` battery sense does not port** — the Feather's 2:1 divider is board
  wiring. The Teensy build needs its own divider on a chosen pin; note it or `Batt` goes
  silently wrong (sentinel-vs-legal-value: a wrong divider still returns plausible
  volts).

## 2. Hardware list

| item | status | note |
|---|---|---|
| Teensy 4.1 | **on hand** | 600 MHz M7, FPU, microSD slot |
| RFM9x breakout #2 | **on order** | sled keeps its own radio; the Feather stays intact as the flown reference article |
| Antenna | carries over | same 434 MHz quarter-wave, same connector chain |
| LiPo charging | **none built in — needs a board.** Cheapest sane option: Adafruit Micro-Lipo charger (~$7) charging the pack out-of-circuit or via a JST splice; LiPo feeds **VIN (3.6–5.5 V)** directly. **Trade, stated:** direct-VIN loses the pack tail below 3.6 V (~15 % of capacity). A 5 V boost (PowerBoost-class, ~$15) recovers it at the cost of a board and its quiescent draw. Decide at build with the measured flight-power number. | ESTIMATE — prices/current from memory, confirm at order time |
| Physical fit | **must be checked, not assumed** | Teensy 4.1 is ~61×18 mm vs the Feather's ~51×23 — narrower but longer, **plus a separate radio breakout where the Feather integrated it: two boards in the mini-Piercer bay, not one.** Measure the bay. |

**Clock-down plan:** run at **150 MHz** (`F_CPU` menu option) — Mahony at any plausible
rate is trivial there and it roughly quarters MCU draw. Draw ESTIMATES to be replaced by
measurement at bring-up: ~100 mA @600 MHz, ~40–45 mA @150 MHz (PJRC-derived figures).
**In flight the radio dominates regardless:** 17 dBm TX at 58.9 % duty ≈ +55–60 mA
average — the MCU clock choice is a pad-endurance knob, not a flight one.

## 3. SD flight recorder — design sketch

**What gets logged, at what rate:**

| stream | rate | content |
|---|---|---|
| IMU (LSM6DSOX FIFO) | **833 Hz ODR** (nearest standard step to 1 kHz on the ODR ladder; 1666 Hz available if spectra want it) | raw 6-axis, FIFO-drained in-loop |
| Baro | delivered rate (~25–50 Hz on its own conversion timing) | pressure, derived alt |
| Events | on occurrence | state transitions, launch/apogee instants, ms timestamps |
| TX mirror | per transmission | **every frame as transmitted, with its SEQ — the join key** |

**File format on the card:** one file per boot session, named by a persisted boot
counter (**the vehicle has no RTC** — vehicle time is `millis()`; wall-time attachment
happens at join time via the ground record, per C2). Append-only, length-prefixed binary
records with a one-byte type tag; periodic `sync()` every ~250 ms so a power cut costs
at most that window. Throughput is trivial (833 Hz × ~20 B ≈ 17 kB/s); the real risk is
**SD write-latency stalls**, mitigated by pre-allocation and a RAM ring buffer sized to
the worst observed stall — measure the stall distribution at bring-up before sizing.
CSV rejected for the IMU stream on volume, kept as an option for the event stream where
greppability pays.

**Join and provenance — C2's rules, carried verbatim (cite, don't re-derive):**
- **SD log = the VEHICLE's record. Session JSONL = the GROUND's record. Neither ever
  absorbs the other** — the one-writer discipline extended to the vehicle.
- Join key: (SYS, SRC, SEQ) via the TX-mirror stream against the ground session log.
- One authoritative source per field; published outputs rebuild byte-identically with
  the SD record as an **optional derivation input** — its absence never changes what the
  ground record alone would publish (a lost card costs enrichment, never the record).

## 4. Fusion tier

- **Mahony, gyro+accel only, onboard.** Mag EXCLUDED in flight (5.d stands — airframe
  mag environment); yaw drift accepted and **quantified from 5.a bias data**. Mag lives
  in pad frames.
- **Output: quaternion (Euler derived) at 10 Hz replacing `Wmx`** per 5.e — roll rate
  falls out of the solution, so `Wmx` is likely redundant; its retirement is decided at
  the 5.e wire design, not assumed here.
- **Calibration constants sourced from the E+F pad-frame pipeline — 5.a dependency
  unchanged** (ADR 0005 A1.3: the pad frame IS the calibration dataset).
- Any over-65 %-duty result at the 5.e wire step is **forcing function #4 for binary
  v2** and starts the binary epic per ADR 0005 A1.5 — not another ASCII compromise.

## Bring-up note — interleaved bench traffic is data, not noise

During Teensy bring-up the Feather sled will often be powered on the same bench, so ground
sessions will carry mixed-`SRC` packets. That is expected and USEFUL: the first Teensy
TX-smoke deliberately observes and records what the ground does with mixed traffic —
segmenter behaviour, panel, OLED source picker, session stats — and any bench session with
mixed traffic gets a bench-sessions register entry per the provenance rules. In the FIELD
the rule is one sled powered at a time (`docs/field-checklist.md`); sled-coexistence
collision design is explicitly rejected (see the corrected jitter-rider entry in
`docs/RESUME.md` — lander trigger, not sled trigger).

## 5. Explicitly NOT in Epic 5

- **Binary v2** — own trigger, own epic (ADR 0005 A1.5).
- **Any change to ADR-0001 framing.** Attitude tags arrive additively like every other
  tag.
- **Any ground service architecture change.** The ground station cannot tell a Teensy
  sled from a Feather sled except by what the frames carry — that is the contract
  working as designed.
