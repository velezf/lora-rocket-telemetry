# CLAUDE.md — working memory for this repo

RocketLoRaTelemetry V2: replatform the Apogee Zephyr telemetry system — Feather M0
sled TX firmware (PlatformIO), a Raspberry Pi 5 ground station with native LoRa RX,
the logging/dashboard/web pipeline, plus a deployable lander and a kids' handheld.

**To resume work, read [`docs/RESUME.md`](docs/RESUME.md) first** — it holds the
live status (current epic, open branches, next steps). Keep it current as work lands.

## Working agreement (most important)

Approval gates, TDD, commit format and the parallel-agent protocol are global:
`~/.claude/CLAUDE.md`. Cross-project conventions (cite-don't-restate, the hollow-check
failure class, shared Pi hardware, repo hygiene) are in `~/code/CLAUDE.md`. Cite those by
section name; do not restate them. Repo-specific:

- **One branch per unit of work**, per-task commits (mirror the existing history).
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

## Cite, don't restate (doc convention)

The convention is `~/code/CLAUDE.md` "Cite, don't restate"; the 2026-07-31 incident that
motivated it happened in this repo. Authorities for literal values here: the packet format is
ADR 0001; the clock escape hatch is ADR 0003; heartbeat state path is `STATE_PATH` in
`ground/panel/heartbeat.py`; deploy and service paths are the `systemd/` unit files.

## Parallel agents — repo-specific rules

The protocol is the `parallel-agents` skill plus `~/.claude/CLAUDE.md` "Parallel agents";
the hollow-check failure class and Pi exclusivity are in `~/code/CLAUDE.md`. Adopted here
2026-08-02, first day of parallel work. **Agent prompts CITE those by name; they must not
paraphrase them.** What is specific to this repo:

- **Admission rule**: admit only if it (a) prevents lost flight data, a corrupted record, or an
  ambiguous go/no-go at the pad, AND (b) has concrete evidence the failure is real.
- **Budget rule**: at most one correctness and one hardening branch **awaiting a gate** at a
  time. Slots are measured at the REVIEW QUEUE, not the worktree; parallelism does not add
  reviewer attention. Investigation streams that produce proposals rather than diffs don't
  consume a slot.
- **No exploring new ideas inline.** Anything noticed goes to the stream's scratch file with
  the concrete trigger that would revive it.
- **Park or close every stream by name in `docs/RESUME.md`.** The global lifecycle rule applies;
  the reason it is load-bearing here: *parallel branches are how 34 stale branches accumulated.*
- **Hook status: `.claude/hooks/verify-cwd.sh` is COMMITTED BUT NOT WIRED.** It is inert until
  registered as a `PreToolUse` hook in settings. Recorded here rather than left implicit,
  because a guard that exists but does not run is exactly the designed-but-inert hazard this
  project already tracks for panel signals. Convention first; wire the hook **if it recurs**.
- **Consequence that must stay visible:** an earlier "PROBE CONFIRMED RUNNING (pgrep-verified)"
  may itself have been a self-match. **So the daylight glyph verification rests on a check that
  may have been hollow**, which is a second, independent reason that item stays OPEN, on top of
  the distances never being recorded. An open item should say WHY it is open.
- **Relationship to the other recorded patterns.** *Self-correction has its own failure mode*
  says looking harder carries its own bias. *A defect that does not reproduce casually* says
  NOT finding something is weak evidence. The hollow-check class says **finding something is
  weak evidence too, if the instrument cannot fail.** All three are about the trustworthiness
  of evidence rather than the correctness of code.

## Two surfaces, not peers: LEDs vs OLED

**The LED panel answers "IS THE SYSTEM WORKING". The OLED answers "WHAT IS THE FLIGHT DOING".**

The distinction is structural, not stylistic. The panel supervisor (`apogee-panel`) is its own
process and **survives the failures it reports** — when ingest dies, the supervisor sees a stale
heartbeat and drives RED fail-closed. The OLED's render thread lives **inside** `apogee-ingest`,
so when that process dies the display **freezes showing plausible content and cannot report its
own death**.

Consequences that follow, and should decide the next such question without re-deriving it:
- **The OLED must never be the authoritative reporter of a system-health fact.** Clock provenance
  appears on the IDLE page (a pre-launch check, made standing at the box where `B_CLOCK` can be
  cross-checked) and is **absent from LIVE and SUMMARY**, where a frozen `CLK rtc` would be a
  trust claim from the least trustworthy channel.
- **Deliberate redundancy is fine when the LED corrects the OLED.** Flight state lives on both at
  different ranges; on an ingest death the supervisor clears `G_FLIGHT` while the OLED still shows
  `ASCENT`. That is not tolerated duplication — it is the safety property.
- **The liveness glyph stays on the OLED**, because it reports the RENDER THREAD's aliveness — a
  different failure domain from `G_ALIVE` (the RX loop). No LED can report it.

### OPERATOR PROCEDURE — when the two surfaces disagree, believe the LEDs

**Dark `G_RX` with a plausible-looking hero on the OLED means ingest is dead and the display is
showing you the past.** The panel is fail-closed and outlives the process it reports on; the
display does not. Any disagreement resolves in the LEDs' favour, every time.

## Published output resolves from the record, never from the environment

**Anything that appears in published output — a page, an export, a permalink, a rendered
figure — resolves from the RECORD, never from the config or environment of the machine doing
the publishing.** Republishing the same record from another machine must produce byte-identical
output; if a value can differ because of *where* you ran the publisher, it is not publishable
input.

This is the same principle as the ops journal: annotations are data, not the state of somebody's
laptop. Concretely — the operator callsign on the flights page comes from `CALL` captured in the
session log, **not** from `callsign_binding` in `~/.config/apogee/ingest.json`, which is per-box
field config and uncommitted by design.

It is also why the 2026-08-01 provenance gap mattered: the published `flights.json` carried
annotations that no journal could reproduce, so the artifact could not be re-derived. Live config
is a subtler version of the same failure — it reproduces fine on *your* machine and nowhere else.

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
