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

## Cite, don't restate (doc convention)

**Literal values get stated ONCE, at their authority, and are cited everywhere else** — paths,
GPIO pins, I²C addresses, ports, thresholds. Write `` the path is `STATE_PATH` in
`ground/panel/heartbeat.py` `` rather than pasting the path into prose. A fact stated once
cannot contradict itself; a fact stated four times drifts and is caught only by a human
happening to notice.

This is not theoretical: on 2026-07-31 three separate instances surfaced in one session — the
clock escape-hatch procedure across four locations, the panel LED L→R order contradicting
itself *within* `RESUME.md`, and the heartbeat state path wrong in two places while the
constant was right. Same discipline ADR 0003 already applies to the escape hatch.

For **prose procedures** (as opposed to literal values), the tool is the same convention, not a
test: one canonical copy, everything else links to it. No test can judge whether two prose
procedures mean the same thing.

## Parallel agents — the canonical rules (cite this, don't restate it)

Adopted 2026-08-02, first day of parallel work. **Agent prompts CITE this section by name;
they must not paraphrase it** — same discipline as ADR 0003 and the deploy path.

### Rules that constrain AGENTS

1. **The Pi is exclusive, by construction.** Only the main thread touches hardware. Agents get
   tasks that need none, so exclusivity never depends on an announce/release protocol holding
   under pressure. *(A probe stopping `apogee-ingest` is why this can't be implicit.)*
2. **Own branch/worktree; no two streams touch the same file.** Held on day one.
3. **Agents COMMIT to their own branch. They never merge, never push, never tag, never touch
   `main`.** The gate is MERGE AND PUSH, not commit — which fully preserves the intent ("no agent
   lands work on `main` without approval") while fixing four things the original wording broke:
   - **Uncommitted work cannot be reviewed with normal tools.** "Read the agent's diff" had no
     diff to read; `git merge` on a branch with zero commits is a silent no-op.
   - **It cannot be parked under rule 7** — a stream that ends the session uncommitted evaporates.
   - **It is destroyed by a stray checkout**, which nearly happened on 2026-08-02.
   - **A commit has a hash**, so claims about it can be verified — which is what this project's
     whole verification discipline turns on.
   **COROLLARY — merging an agent's branch ALWAYS requires a main-thread commit first.** The
   agent commits to its own branch; the main thread reviews that commit, then merges. There is no
   path where agent work reaches `main` without a human-gated merge, and no path where it reaches
   `main` uncommitted. *(Discovered the hard way: `git merge` on a zero-commit branch is a SILENT
   no-op — it reports success and changes nothing.)*
   *(Second rule to need correcting. The first was rule 10.)*
4. **No exploring new ideas inline.** Anything noticed goes to the stream's scratch file with the
   concrete trigger that would revive it.
5. **Each stream reports independently**, so reviews happen separately rather than as one blob.
6. **No agent writes `docs/RESUME.md`.** Per-stream scratch files, folded in serially by the main
   thread. *(RESUME is the most contended file in the repo; every stream wants to append backlog.)*
7. **A stream that doesn't reach a gate in-session is explicitly parked or closed**, named in
   RESUME with its state. *(Parallel branches are how 34 stale branches accumulated.)*
8. **An agent's report is only valid relative to its BASE COMMIT, and it must say so up front.**
   Agents branch from `main`, not the working branch, so anything committed only on a feature
   branch is invisible to them. *(An agent reported "X appears nowhere in RESUME" — true in its
   worktree, false in the repo. Scope must arrive attached to the claim.)*

### Rules that constrain the MAIN thread

9. **`.claude/worktrees/` is gitignored — scoped to `worktrees/` only**, never all of `.claude/`,
   which may later hold tracked agent definitions or settings.
10. **NEVER rely on inherited working directory. `cd` to the absolute repo root before any repo
    command.** The Bash tool persists cwd between calls, so a single earlier `cd` into a worktree
    silently relocates every subsequent "my repo" command — and **git will answer honestly about a
    tree you didn't mean to be in.** *(This produced six tool calls of wrong conclusions and an
    alarming, entirely false report of an agent isolation failure. Isolation had held.)*
    Convention first; a `PreToolUse` hook only **if it recurs** — a hook firing on every command
    has its own noise cost, and one occurrence isn't a pattern.
11. **Verify agent claims before relaying them.** Subagent reports are evidence, not findings.
    Three of today's were verified: two confirmed and materially corrected the main thread's
    picture; one was a base-commit artifact. Relaying unverified would have propagated all three.

12. **APPROVALS ARE AFFIRMATIVE AND EXPLICIT — and the default on ambiguity is STOP AND ASK.**
    A gate is cleared by "APPROVED: merge" / "APPROVED: push", never inferred from a phrase that
    *could* be read as clearance. **If an instruction has two readings and one of them authorises
    an irreversible action against a standing rule, that ambiguity is itself the signal to pause.**
    A push to a public remote is irreversible in practice.
    *(2026-08-02: "gate me on the merge, not the analysis" has two honest readings — "the merge is
    where you ask me" and "the merge is cleared". The convenient one was taken and `main` was
    merged and pushed without the approval the author intended to give. Same shape as rule 10:
    not carelessness, an unverified assumption that happened to be convenient. Both halves of that
    exchange matter — an ambiguous prompt and a self-serving reading — and neither is fixed by
    trying harder.)*

### FAILURE CLASS: a check that looked like it was checking

**Three instances in one day, all the same shape: a guard that reported success without
having verified anything.** Named as a class because it generalises to guards not yet
written — the question to ask of any check is not "did it pass?" but **"could this have
failed?"**

| Hollow form | Why it never fails | Reliable form |
|---|---|---|
| `pytest … \| tail -1 && git push` | the pipeline's exit status is `tail`'s, which is **always 0** — so "verified, then pushed" was not a gate at all | `pytest … \|\| exit 1` (or `set -o pipefail`) |
| `pgrep -f "some pattern"` | the checking command's own `bash -c` line **contains the pattern**, so it matches itself | `ps -eo args \| grep <pattern> \| grep -v grep` |
| a repo command relying on inherited `cwd` | the Bash tool persists cwd between calls; **git answers honestly about the wrong tree** | `cd <ABSOLUTE_REPO_ROOT> && …` (enforced by `.claude/hooks/verify-cwd.sh`) |

**Consequence that must stay visible:** an earlier "PROBE CONFIRMED RUNNING (pgrep-verified)"
may itself have been a self-match. **So the daylight glyph verification rests on a check that
may have been hollow** — which is a second, independent reason that item stays OPEN, on top of
the distances never being recorded. An open item should say WHY it is open.

**Instance 1 is rule 12 in mechanical form, and the shell-level reading misses the point.**
"Don't chain a verification into a push" is easy to obey while still missing why:
**the gate was never "tests passed" — it is "a human read the result and said the word."**
`|| exit 1` would have made the check honest while still removing the human from the loop.
A push conditioned on an exit code is a push nobody read.

**DESIGN CONSTRAINT ON HOOKS: scope narrowly enough that it survives.** Blocking every
`pytest … |` would fire on nearly every run, and a guard that gets turned off protects
nothing. The cwd hook is deliberately limited to commands that touch repo state for the same
reason. Breadth that guarantees the guard is disabled is worse than a narrower guard that
stays on.

**STATUS: the hook is COMMITTED BUT NOT WIRED.** `.claude/hooks/verify-cwd.sh` is inert until
registered as a `PreToolUse` hook in settings. Recorded here rather than left implicit,
because a guard that exists but does not run is exactly the designed-but-inert hazard this
project already tracks for panel signals.

**Relationship to the other recorded patterns.** *Self-correction has its own failure mode*
says looking harder carries its own bias. *A defect that does not reproduce casually* says
NOT finding something is weak evidence. This one says **finding something is weak evidence
too, if the instrument cannot fail.** All three are about the trustworthiness of evidence
rather than the correctness of code.

### Related rules that already existed and still apply

- **Admission rule** — admit only if it (a) prevents lost flight data, a corrupted record, or an
  ambiguous go/no-go at the pad, AND (b) has concrete evidence the failure is real.
- **Budget rule** — at most one correctness and one hardening branch **awaiting a gate** at a time.
  Slots are measured at the REVIEW QUEUE, not the worktree; parallelism does not add reviewer
  attention. Investigation streams that produce proposals rather than diffs don't consume a slot.
- **Gates** — Frank approves every commit, merge and push. Parallelism does not change this.

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
