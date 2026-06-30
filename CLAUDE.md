# CLAUDE.md — working memory for this repo

RocketLoRaTelemetry V2: replatform the Apogee Zephyr telemetry system — Feather M0
sled TX firmware (PlatformIO), a Raspberry Pi 5 ground station with native LoRa RX,
the logging/dashboard/web pipeline, plus a deployable lander and a kids' handheld.

**To resume work, read [`docs/RESUME.md`](docs/RESUME.md) first** — it holds the
live status (current epic, open branches, next steps). Keep it current as work lands.

## Working agreement (most important)

- **Frank reviews and approves every commit and merge himself.** Default to working on
  a feature branch and **STOP before committing** unless told otherwise. **Never merge
  or push without explicit approval** — merging/pushing publishes to a public origin.
- **One branch per unit of work**, per-task commits (mirror the existing history).
- **TDD: red → green → refactor** for all logic. Write the failing test first.
- **Commit messages:** conventional prefixes (`feat`/`test`/`docs`/`chore`) with a
  scope, e.g. `feat(firmware): …`. End every commit with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **Git over SSH.** Origin: `git@github.com:velezf/lora-rocket-telemetry`.

## Repo layout

- `firmware/` — PlatformIO sled TX. **The only C++ in the project.**
- `handheld/` — Epic 8 Pi Zero 2 W handheld receiver (Python / uv / Blinka).
- `docs/` — `PROJECT_PLAN.md` (the roadmap), `adr/` (decision records), `RESUME.md` (status).
- `RocketLoRaTelemetry/` — **V1 reference firmware. READ-ONLY** — do not modify, move,
  or delete; it is ported into `firmware/` during Epic 3.
- `GroundStation/` — V1 LePotato / Node-RED ground station (legacy reference).

## The keystone contract

The v1 packet format — [`docs/adr/0001-packet-format-v1.md`](docs/adr/0001-packet-format-v1.md)
— is the **single source of truth** for the wire interface between the sled TX and every
receiver. Space-delimited keyed `KEY:VALUE` ASCII, leading `V:1`. The C encoder (Epic 3.2)
and the Python decoder (Epic 4.1) both assert against its golden vector. Any change goes
through the ADR + its versioning policy (reject unknown versions; additive tags within a
version; only breaking changes to existing tags bump `V`).

## Firmware (PlatformIO)

- **`pio` binary:** `~/.platformio/penv/bin/pio`. Interactive zsh has it on `PATH`;
  non-login shells (tool calls) need the full path.
- **Compile (no board needed):** `pio run -e feather_m0_tx`
- **Host logic tests:** `pio test -e native`. A bare `pio test` is a no-op by design
  (`test_ignore = *` on the board env keeps host tests off the embedded target).
- **`lib/` purity rule:** pure, portable C++ — **no `<Arduino.h>`, no RadioHead** — so it
  runs in the `native` env. Hardware glue lives in `src/`. The `native` env stays
  dependency-free.
- **No Feather M0 on hand:** flash/upload/parity steps are hardware-gated and deferred
  (Epic 1.4 upload smoke, 3.1b flash+parity). All Epic 3 *logic* is native/host-testable now.

## Multi-machine

Work happens on **the Mac** (firmware, heavy lifting) and **the Pi 5 ground station**
(on-box tinkering via Claude Code). Both sync through `origin/main` — **pull before
starting** so parallel sessions don't diverge.
