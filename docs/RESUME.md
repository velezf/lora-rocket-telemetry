# RESUME — project status & handoff

Living status doc. **Read this first to resume.** Update it whenever an epic/task or
branch state changes. (Conventions and how-to-build live in [`CLAUDE.md`](../CLAUDE.md).)

_Last updated: **2026-08-07** (Claude, on Mac + Pi 5). See HANDOFF below for the live state. Earlier context: **This session: `feat/panel-leds` MERGED and
pushed** — the six-LED supervisor is live and enabled for boot on `apogee-gs`. Also landed three
pieces of process that outlive the branch: the **sanctioned deploy path**, the canonical
**"designed but INERT"** register, and **"cite, don't restate"**. Repo-wide **branch cleanup**
done (34 stale branches removed; Mac/GitHub/Pi all on `main` only). **4.5 is UNGATED** — F1 bench
data is sufficient to publish; see Immediate next steps. Earlier: RTC-boot-restore
merged + pushed (ADR 0003); **wake-on-charge** (`auto_power_on`) enabled; **graceful button
off-switch** validated (USB-C double-tap → clean `service_stop`; both PiSugar buttons close the log
cleanly); **OLED rewire verified** (the "dark" was a no-idle-page firmware gap, not hardware).
**`feat/panel-leds` is now BUILT, not merely designed** (2026-07-31): pure LED policy + supervisor
logic + lamp-sweep plan, the ingest heartbeat publisher, and the Pi supervisor shell/unit — see
"Open branches". Still designed-not-built: `feat/oled-heartbeat` layout redesign — see Backlog. Still parked from 2026-07-08: the flights page mock on pages-repo branch
`feat/flights-section` awaiting Frank's review→merge→push, then Claude tags `v1.0-portfolio-genesis`._

## HANDOFF — 2026-08-25: BUILD ORDER COMPLETE, RED TEAM DONE — NEXT IS BENCH

**`feat/firmware-10hz` (local, never pushed) carries the whole ADR 0005 build order
(steps 2–7; step 1 was already on `main`) AND all nine red-team findings, fixed.**
88/88 native, 14/14 cross-end guard, 16/16 sx127x, target compiles. The red team ran
2026-08-24 (Fable 5 agent, briefed per the taxonomy section below — cited, not
restated); every finding was verified against the repo before relaying, then fixed,
one commit per finding cluster — **the per-finding detail lives in the commit
messages, cite them**: `310d9fe` (F6 stale-baro apogee feed), `e7ea59d` (F1+F8
mechanical register weld), `5ca4cf4` (F5 velocity noise test), `f80378b` (F7 stale
prose + F9 health consumer), `b4b0187` (F8 SX1276 errata regs), plus the CI workflow
and this docs commit.

### CUTOVER — the merge/deploy/flash ORDERING is the change (finding 2)

**`main` is cross-end inconsistent TODAY**: its ground default has been BW500 since
`d53b9a6` while its sled firmware is BW125 — the two ends of `main` cannot hear each
other. Consequences, so nobody burns hours on a "wedged radio" that is actually the
cutover: **a dark bench while the two boxes are on opposite sides of the cutover is
EXPECTED.** Before diagnosing any dark link, establish which side each box is on
(`git log` on the Pi; the sled is whatever was last flashed). Order after this branch
merges: flash the sled, redeploy/restart ingest on the Pi from the same `main`, run
the cross-end guard (`ground/rx/tests/test_rf_both_ends.py`) and confirm close-range
RSSI against the post-pigtail baseline (−40 ±1 dBm, §2 of ADR 0005).

### BENCH PROTOCOL — two additions that are now load-bearing (findings 3, 4)

1. **§8's RX-turn measurement does not cover this build** (1 Hz arrival, BW125, 109 B,
   pre-newtags decoder — the ADR status line now says so). The sustained-10 Hz bench
   with **FIFO-overwrite counts** (A1.6) is the evidence that replaces it, not a
   formality on top of it.
2. **Watch INTER-ARRIVAL TIMES on the ground, not loss alone.** TX SKIPs deliberately
   do not gap SEQ, so a repeatedly-wedging radio degrades 10 Hz → ~2 Hz while the loss
   statistic reads 0 %. The sled's serial RATE line carries `tx skips` / `tx forced` /
   `baro healthy` for the bench; the wire cannot carry them today (a counters tag is
   backlog, gated on the collision-proof process).

### FRANK-VERIFY BEFORE BENCH

- **SX1276 errata §2.1 register values** (`b4b0187`: 0x36=0x02, 0x3A=0x7F at 434 MHz
  BW500) were written from recollection, twice-agreed (agent + main thread) but from
  the SAME kind of source — check the published errata sheet; the close-range RSSI
  comparison corroborates.
- **`FAST_WINDOW_MS` = 300 s** (`lib/txsched/txsched.h`) is CHOSEN, NOT MEASURED —
  rationale beside the constant (~2× worst realistic flight; asymmetric risk).
- **CI** (`.github/workflows/checks.yml`) is UNVERIFIED until the first push runs it.
- **Rule 10 recurred three times in this session** (cwd drift between parallel tool
  calls, caught each time by a failed command rather than a wrong one). The
  committed-but-unwired `verify-cwd` hook now has its "if it recurs" evidence —
  wiring it is a settings change awaiting Frank's decision.

## HANDOFF — 2026-08-07, start of the 10 Hz build session

**NOTHING FLEW ON 2026-08-06.** The section below is titled "FLIGHT DAY" and describes a
bench-verified build; read it as *what was prepared*, not what was flown. The flight is
pigtail-gated (see DEFERRED).

**ON `main` NOW:** the launch **confirm-or-revert** gate (merged 2026-08-06) — altitude
confirms the launch, the accel gate only decides when to start watching, and both permanent
latches are closed (`max_provisional_ms` bounds PROVISIONAL from first entry). Flashed and
bench-clean: SEQ 112→157, 0 discontinuities, **RATE 17.00 Hz**, 0 baro failures, **0 launch
reverts**, `St:0` throughout. 45/45 native tests green.

**DECIDED, NOT BUILT:** [ADR 0005](adr/0005-telemetry-rate-and-rf-configuration.md) —
**10 Hz at SF7/BW500/17 dBm**, ACCEPTED, its §8 RX-turn gate measured and passed
(worst turn **25.65 ms** against a 100 ms budget, ~3.9x margin).

### BUILD ORDER — run in this sequence, each gated by Frank

1. **`ground/flights/baseline.py` `WINDOW=15` → time-based.** A *sample* count calibrated in *seconds*;
   at 10 Hz the AGL baseline silently locks on 1.5 s instead of 15 s. **Mandatory before any
   rate change.** Ground-side, host-testable, no hardware.
2. **`encode_packet` truncation LOUD + buffer 128 → 192.** Verified defect: on overflow it
   returns `out_len-1`, a valid-looking length, and the fragment is transmitted. A frame cut
   at 105 B decodes as a **valid packet with `MET:6` where the truth is 65535** — no counter
   moves. Record the range assumptions beside the number (§4 of the ADR).
3. **BMP390 temperature oversampling 8x → 1x** (NOT off — pressure compensation needs the
   term). **Measure the achieved rate; do not assume the gain.**
4. **Non-blocking TX.** Fire and poll; **`isSending()` does NOT exist on `RH_RF95`** — use
   `mode()`. On skip, **`seq` must NOT increment** or a sled scheduling decision publishes as
   RF loss. Guard the unbounded `waitPacketSent()` hang with a watchdog.
5. **`Vel` + G envelope (`Gmx`/`Gmn`).** Onboard dh/dt with light smoothing; envelope reset
   per TX window, tested. New worst case **139 B**.
6. **Both-ends BW500.** A **both-ends constant** whose failure mode is *silent total link
   loss*. One authority, cited — never copied.
7. **St-dependent 10 Hz** — 1 Hz on pad, 10 Hz in flight. **Bound it**: the flight states
   latch and there is no `St:3`, so "fast while `St != 0`" never turns off and would transmit
   until the battery died. MET-bounded window.

### RED TEAM BEFORE ANYTHING FLASHES

A Fable 5 agent reviews the **actual diff**, adversarially, and **reports without fixing**.
Brief it with this project's own failure taxonomy — every one of these shipped here:
hollow guards (a check that cannot fail, or that never ran); **a test derived from the same
assumption as the implementation**; **a test asserting a proxy for the property**; sentinel
colliding with a legal value; latches with no bounded exit; silent truncation or field loss;
restated facts that disagree with their source; evidence that does not describe the artifact
that will fly. Its specific hunting grounds here: the **both-ends BW constant**, the
**envelope reset logic**, and whether the **RX-turn measurement** actually covers 10 Hz.

### BENCH SCOPE — bench range only, and say so

The 10 Hz sustained bench runs **antenna-less at arm's length** (the link decodes fine there;
measured **−80/−81 dBm**). Report **loss** and **FIFO-overwrite** counts. This validates the
sled, the loop and the ground pipeline. **It does not validate the RF path.**

### DEFERRED — pigtail items CLEARED 2026-08-08; what remains is flight-gated

**The pigtail arrived, was wired to the project-box bulkhead antenna, and the repair was
CLEARED by Frank**: close range −40 ±1 dBm / zero loss / σ 0.38 (vs −80/−81 antenna-less;
gate −38..−14 — 2 dB shy of the weak edge, attributed to chain insertion loss). Wiggle
test and formal continuity check waived on judgement — named in ADR 0005 §2. **Still
open, now FLIGHT-gated, not pigtail-gated:** field-range margin, and the flight itself
(red team + bench first).

**WEDGED-RADIO HARDENING — admission-rule candidate with evidence (2026-08-08).** During
the antenna work the SX127x latched into a state that decoded NOTHING for 3.7 h while
ingest ran healthy — heartbeat green, loop turning, `G_RX` dark (the panel told the
truth; believe the LEDs). A polling driver cannot distinguish a wedged radio from a
silent sky: IRQ flags simply never set. Recovery was a service restart (full re-init).
Passes the admission rule: (a) at the field, wedging between pad power-cycle and launch
is a LOST FLIGHT; (b) tonight is the concrete evidence. Candidate fix: re-init the radio
after N minutes of RX silence — harmless when the sky is genuinely quiet. Also a
red-team hunting ground: the RX path has a latch with no bounded exit, the same class
just removed from the sled's detectors.

### Superseded 2026-08-08 (original pigtail-gated list)

- **Field-range link margin.** ADR 0005 §2's ~42 dB is a *design assumption*, unvalidated.
- **u.FL continuity check** — centre pin NOT shorted to shield, before the new pigtail is
  trusted. The connector was re-soldered 2026-08-06.
- **RSSI validation of the repair** — close range back in the **−38 to −14 dBm** band.
  Antenna-less "before" evidence: session `session-20260806T174610Z-4d657e`, 1,724 packets.
- **The flight itself.**

Until then: **any weak-RSSI symptom is the connector until proven otherwise.**

### RESOLVED 2026-08-07 — why Wi-Fi profiles appear to come and go

**Two profiles, two persistence mechanisms, and only one of them is durable in place.**

- `iphone17-hotspot` is a **native NetworkManager profile** in
  `/etc/NetworkManager/system-connections/`. It is edited in place and nothing regenerates it.
- `netplan-wlan0-WideRoad` is **netplan-rendered**: the truth lives in
  `/etc/netplan/90-NM-dd86560a-*.yaml` and is rebuilt into `/run/NetworkManager/system-connections/`
  **on every boot**. Anything in `/run` is disposable by design, so a netplan change rewrites
  that set wholesale.

That is the mechanism, and it is observed, not guessed. **Two honest limits on the claim:**
(a) the original "all profiles are gone" report was partly MY ERROR — the hotspot profile was
there the whole time and a broken grep (`wifi` against a field reading `802-11-wireless`)
could not see it; (b) whether a *home* profile ever existed before 2026-08-07 is unknown, so
netplan regeneration is a well-supported EXPLANATION for a disappearance, not an observed
cause of one. The durable practical consequence stands either way: **edits to a
netplan-rendered profile are not safe from netplan; edits to a native NM profile are.**

The actual cause of "no Wi-Fi" on 2026-08-06 was neither: `nmcli radio wifi` was **disabled**
(an NM-level switch independent of rfkill) *and* `rfkill` had `phy0` **soft-blocked**. Both
were invisible from the symptom, and both persist once set.

### FIELD FALLBACK — direction two confirmed, unattended

When the router came back up on 2026-08-07 the Pi moved **hotspot → WideRoad on priority with
no input at all**. That is the same autoconnect machinery that must pick the hotspot up at the
range, resolving the other way, and it ran unattended. Combined with the router-off validation
(ran on hotspot alone, dashboard served, sled RX lossless), both directions of the
priority scheme now have evidence behind them — home 100 wins at home, hotspot 50 with
infinite retry is the only candidate at the field.

### EPIC 5 RE-SCOPED 2026-08-08 — attitude is ONBOARD or it does not exist live

**CLOSED QUESTION at the head of the epic: live in-flight attitude can never come from
ground-side fusion.** The arithmetic, recorded with its load-bearing leg named:

Ground-side fusion needs raw gyro+accel at ≥ 50 Hz. At SF7/BW500 (all ToA incl. 4 B RH
header): ASCII raw frames at 50 Hz = **352 % duty** (impossible); minimal per-sample
binary (~20 B) = **77 %** (over the 65 % line); realistic per-sample binary (~34 B) =
**103 %** (over the RF ceiling itself). **Honesty note: duty alone does NOT close the
question** — batching 5 samples into a 10 Hz binary packet is ~65 B and **32 % duty**,
comfortably feasible. The question closes on three legs together:

1. **Duty** kills ASCII and per-sample binary outright (numbers above).
2. **Batching requires binary v2** — the largest contract change in the system, gated
   behind its own epic per ADR 0005 A1.5, not an incremental option.
3. **THE LOAD-BEARING LEG — integrator integrity, which holds at ANY encoding.** Attitude
   is an integration, and ground-side fusion integrates a lossy RF link: every tumble
   fade punches a hole in the input stream and the solution diverges at every gap, during
   exactly the dynamics it exists to capture. Onboard integration has a loss-free input
   by construction. No transport fixes this; it is structural.

**Therefore: attitude is computed ONBOARD and the solution is transmitted, or it doesn't
exist live.** Spin SPECTRA stay impossible live at any encoding — that path is onboard
log + post-flight dump (C2): noted, PARKED.

**DIRECTION DECISION, same day (supersedes 5.b/5.c of the morning's list): Epic 5 is the
TEENSY 4.1 SLED RESPIN — onboard fusion + SD flight recorder.** Full plan, port-cost
audit, hardware list, SD recorder sketch and not-in-scope list:
[`docs/epic5-teensy-respin.md`](epic5-teensy-respin.md) — cite it, don't restate it.
The morning's 5.c measurement gate (SAMD21 soft-float Mahony) is **MOOT** — the M7+FPU
is the decision. **5.a** (ground cal from E+F pad frames — the pad frame IS the
calibration dataset), **5.d** (mag excluded in flight, yaw drift quantified from 5.a)
and **5.e** (attitude replaces fields; over-65 % duty = forcing function #4 → binary
epic) **stand unchanged** and are restated normatively in the plan doc. C2's
join/provenance analysis carries over VERBATIM as the SD integration design (see plan
doc §3; C2 entry below stays the authority). Spin spectra: post-recovery product off
the card at full sample rate.

**SEQUENCING, FIRM: the 10 Hz rewrite finishes and FLIES on the Feather first (F2).
Teensy work begins after F2.** No MCU respin stacks onto an unflown RF rewrite — two
revolutions with no flight between them means unattributable failures.

No implementation now — recorded 2026-08-08.

### CORRECTION — the 59 ms/sample causal story below is WRONG

The section below attributes ~59 ms/sample to BMP390 conversion. The arithmetic is right and
**the causation is not**: `performReading()` does not wait for the conversion (no data-ready
poll), so 25 + 1.35 ≈ 26 ms, not 59. **The missing ~33 ms is `rf95.waitPacketSent()`
busy-waiting ~159 ms of air time once per second.** Two agents reached this independently.
Consequence: **the temperature-oversampling change is not a sample-rate fix** (and its saving
is 14.14 ms, not 16.3 — `temp_en` is set unconditionally); it is the *precondition* for any
tick below 25 ms. **Non-blocking TX is what actually raises the rate** — zero the TX block and
the loop returns ~20 Hz. Change the justification, or the next person measures no improvement
and thinks something broke.

## FLIGHT DAY 2026-08-06 — what was flown, and what is waiting

**FLYING: `03d70aa`** — 20 Hz-target sampling (17.00 Hz achieved), TX unchanged at 1 Hz,
confirmed apogee and confirmed launch. **Bench-verified clean against all seven abort checks**
before departure: `SEQ 193→307` with 0 discontinuities, 0.0% loss over 115 packets, session
opening, panel and OLED normal, baseline locked at −83 ft.

**MEASURED, NOT CLAIMED — the sample rate is 17.00 Hz, not 20.** Every doc that says 20 means
this number. Reason: BMP390 conversion is ~25 ms at the configured oversampling, of which
**16.3 ms is 8x TEMPERATURE oversampling that altitude does not use**, plus the ADXL I2C read
each tick ≈ 59 ms per sample. It is comfortably above the 8 Hz abort floor and past the 5 Hz
knee where the benefit flattens: the harness measures 20 Hz at 33.8 ft of apogee-detection loss
versus 10 Hz at 36.2 ft, so 17 Hz is indistinguishable from the target.

**EVIDENCE, not a note: the launch dwell held through a flash, a CPU reset and USB handling.**
`St` across the entire 115-packet bench run was `[0]` only. That is the first empirical proof
the dwell does what it was added for — and it happened by accident on the bench rather than by
design, which is the strongest kind. (Baseline locking at −83 ft against F1's −84 is a pleasant
barometer sanity signal; do not over-read it, pressure varies day to day.)

### Waiting for real flight data
- **The OLED trend strip becomes DECIDABLE.** Criterion already recorded: rising ramp through
  boost and coast, flatten at apogee, shallow steady decline under chute, autoscaled. A flat
  smear during descent means the autoscale is not earning its 10 px and the strip should be cut.
- **2.2 hotspot** — **most of it validated 2026-08-07** (router off, Ethernet down: Pi ran on
  hotspot alone, dashboard HTTP 200 by IP `172.20.10.2` and by `apogee-gs.local`, sled RX
  continued, 0 loss). **Its acceptance clause — cold-boot rejoin — is STILL OPEN**: the
  association was forced with `nmcli connection up`, so nothing proves unattended rejoin on
  boot. **CLOSED anyway 2026-08-07, on a risk argument rather than full coverage:** the
  hotspot is a CONVENIENCE path, not a DATA path — if it fails at the pad, capture, the panel
  LEDs and the OLED are all unaffected, so the untested edge cannot cost flight data. The
  first field cold boot is the rejoin observation; it is noted, not gated on.

### Increment 2 (`worktree-agent-a7e6e458b1b6637a5`, `9759989`) — NOT FLOWN, NOT COMPLETE
Per-axis accel as additive v1 tags `Ax`/`Ay`/`Az`. **DO NOT MERGE AS-IS — it has a DEFECT, not
a missing refinement:** with 1 Hz TX over 17 Hz sampling the transmitted axes are a random
1-in-17 snapshot, and a boost is 1-2 s. So the tags capture one or two arbitrary samples that
may be nowhere near peak — **close to worthless for the one number they exist to provide**, and
Epic 5's reference dataset is their whole justification. **The fix is PEAK-HOLD within the TX
window** (track max |a| across the window, transmit those axes, reset each TX), which turns a
snapshot into a measurement. ~30 min including the `main.cpp` conflict and a mandatory re-bench.
**Its `main.cpp` WILL conflict** — it branched from `ca99691`, before the sample/TX split; the
5-line re-apply is preserved below.

**What increment 2 already banked, and keeps regardless:**
- **A truncation defect caught BY MEASUREMENT BEFORE FLASHING, not after a flight.** With the
  new tags the worst case (ADXL375 clipping ±200 g on all three axes) is **143 bytes against a
  128-byte buffer** — bounded, never an overflow, but trailing tags **silently lost**, surfacing
  only on a hard lateral hit, i.e. exactly when the data matters most. `PACKET_BUF_LEN = 160`
  now lives once in `packet.h` with a regression test. *(The CURRENTLY FLASHED build is safe:
  measured worst case 107 bytes against 128.)*
- **The unknown-tag gate, verified through the real decode+ingest path** — additive tags move no
  `errors`, `anomalies` or `foreign` counter. Two of its tests are deliberately anti-hollow: one
  asserts the frame is still fully ACCEPTED (counters would also stay flat if it were dropped),
  and one proves the gate CAN fail by putting a foreign `SYS` on the same frame.

### ⚠ "UNKNOWN ⇒ INERT" IS NOT A GENERAL INVARIANT
**`CALL` is an unknown tag that ingest DOES read** — the Part-97 ID audit trail, and it can move
`id_mismatches`. So the gate above holds for `Ax`/`Ay`/`Az` but **one tag name is already
special-cased**. Anyone adding a tag needs to know this: it reads as a rule right up until it
bites.

### Backlog from today (not now)
- **Drop the BMP390 temperature oversampling from 8x.** It costs 16.3 ms of a ~25 ms conversion
  and **altitude does not use temperature at all** — it feeds only the `T:` telemetry tag. This
  buys back most of the sample-rate budget and is close to free.
- **Peak-hold for the accel axes** — see increment 2 above. Not a refinement; the defect.

## NEXT SESSION — start here: EPIC 6, PHASE 0

**Epic 4 CLOSED. The OLED redesign is MERGED. `main` is clean, three copies identical, single
branch, no worktrees. Nothing is in flight.** Epic 6 (relay deployment) is next and is the epic
that actually unblocks flying. **No Epic 6 code has been written.**

### THREE PREREQUISITES — none of them inside Epic 6, all before any relay work

1. **`firmware/lib/apogee/apogee.h` cannot be the fire trigger.** Fires on the first sample not
   strictly greater than the running max, latches permanently. One noisy boost sample commands a
   charge **at max-Q, irrecoverably**. Harmless today ONLY because nothing is wired to it.
2. **`firmware/src/main.cpp:89` returns from the WHOLE loop on a failed `bmp.performReading()`** —
   skipping any deploy tick below it, including the one that **de-energizes a relay**. A hot
   charge caused by a sensor glitch.
3. **`B-decoupled`** (sample 20 Hz, transmit 1 Hz). **There is no safe 1 Hz configuration.**

### PHASE 0 — its own branch, in THIS order (b -> c -> a, deliberately not a/b/c)

- **`6.0b` FIRST — synthetic flight-profile fixture + detector harness.** The measuring instrument
  for every latency claim in the epic. Nothing downstream can be validated without a profile to
  run it against.
- **`6.0c` — pure `ApogeeConfirm`** (hysteresis + dwell), validated against that profile. Its
  logic is rate-agnostic if dwell is parameterised, so it can be tested at both rates.
- **`6.0a` LAST — decouple sample rate from TX rate** in `loop()`. Only matters once there is a
  detector worth feeding at 20 Hz.

**Why this order is stronger than "build the fix first":** with the harness in place, `6.0b`+`6.0c`
can **PROVE the B-decoupled claim empirically** — run the same detector against the same profile
at 1 Hz and 20 Hz and MEASURE the deployment latency. Today that claim rests on free-fall
arithmetic (~257 ft at 128.8 ft/s vs ~27 ft at 41.9 ft/s). This turns it from computed into
measured, before any firmware is committed to it — which is this project's own evidence standard.

### EVIDENCE-TRUST PATTERN #4 (2026-08-06) — A TEST DERIVED FROM THE SAME ASSUMPTION AS THE IMPLEMENTATION IS NOT INDEPENDENT EVIDENCE

The sharpest one yet, and the strongest possible justification for having built `6.0b` FIRST.

While designing launch confirm-or-revert, "acceleration dropping back below threshold means the
transient is over, so revert" felt obviously right. It was written into `launch::Confirm`, and a
test — `test_accel_dropout_during_provisional_reverts_immediately` — was written asserting exactly
that. **The test passed. Both were wrong together.**

The profile harness caught it in one run: an **A8 NEVER CONFIRMED**. Its burn is 0.5 s but it does
not clear 50 ft until 0.557 s, so burnout arrives first and the launch was discarded at the instant
the rocket began coasting. **Every real launch drops below 3 g at burnout — that is what burnout
IS.** The rule was not merely imprecise; it was backwards for the general case.

**Why the test could not have caught it.** The test encoded the same belief the implementation
did, so it was a restatement, not a check. Green meant "the code does what I assumed", never "the
assumption is true". Only ANALYTIC GROUND TRUTH — a profile with a known apogee time and a known
altitude-versus-time curve, written before the detector — could separate the two.

**The rule:** a test written from the same mental model as the code under test measures
self-consistency, not correctness. Independent evidence has to come from outside that model:
ground truth, a physical measurement, or a second derivation. This is what `lib/profile` is FOR,
and it earned its place the first time it was pointed at something.

### EVIDENCE-TRUST PATTERN #5 (2026-08-06) — A TEST ASSERTING A PROXY FOR THE PROPERTY IS NOT A TEST OF THE PROPERTY

A DIFFERENT failure from #4, the same day, and worth keeping separate because the fix is different.

Having removed the accel-dropout revert, the confirm window became the ONLY revert path — so the
question was whether PROVISIONAL could be held open forever. The test drove 100 s of oscillating
acceleration and asserted `is_provisional() == false` at the end. It failed, and the failure was
the TEST's, not the code's: the detector legitimately re-enters PROVISIONAL immediately after
reverting, so the state at an arbitrary final instant measures **PHASE**, not boundedness.

**The property was "no continuous provisional run exceeds the ceiling". The assertion was "not
provisional right now".** Those are not the same claim, and the proxy is satisfiable by luck and
falsifiable by luck. Rewritten to track the longest CONTINUOUS provisional run and assert it stays
within `max_provisional_ms` + one sample period — which is the property, stated directly.

**The rule:** when a test fails, first ask whether the assertion is the property or a stand-in for
it. A proxy that is cheap to assert is usually cheap because it has thrown away the quantifier —
here, "for all runs, the run is bounded" collapsed into "at this instant, no run is open".

### RESTATED-FACT FAILURE #5 (2026-08-06) — CITE-DON'T-RESTATE APPLIES TO AGENT BRIEFS

`docs/RESUME.md:457` already recorded it: the sled 9-DoF is **LSM6DSOX at I²C 0x6a (WHO_AM_I
0x6C)** and **LIS3MDL at I²C 0x1c (WHO_AM_I 0x3D)**. The sensor-census agent brief restated this
from memory as "hardware at I²C addresses 0x6C and 0x3D" — **turning WHO_AM_I register VALUES into
bus ADDRESSES** — and sent the agent hunting a mystery that was already solved. It cost roughly
twenty minutes before the correction landed.

**The new surface:** cite-don't-restate has been applied to docs and to claims made to Frank. An
AGENT BRIEF is the same hazard with less feedback — the agent cannot tell that the premise is
wrong, has no independent access to the belief being restated, and will spend its whole budget
inside a false frame. A brief is a document that acts, so it inherits the rule.

**The fix:** briefs must POINT at the source (`docs/RESUME.md:457`) rather than paraphrase it, and
must tell the agent to read RESUME before concluding anything about integration state. Facts
carried in a brief should be quoted with their location or not carried at all.

**Two further defects fell out of the same session**, both found by measurement rather than
reasoning: (a) a stale PROVISIONAL kept its old anchor when a real launch began, backdating MET
**472 ms wrong**; and (b) once accel-dropout no longer reverted, the confirm window became the only
revert path — and re-anchoring restarted it, so oscillating acceleration could hold PROVISIONAL
**forever**. That is the removed latch reappearing in a new location. Fixed with an absolute
ceiling (`max_provisional_ms`, 5 s) measured from FIRST entry and never re-anchored. **Removing one
latch is not licence to leave a different one behind** — Frank asked the question that found it.

### MEASURED 2026-08-06 — the detectors, from the harness rather than the design intent

**`ApogeeConfirm(20 ft, 300 ms)` has a FIXED PRICE, not a proportional one.** At the measured
17 Hz, across a 30x range of apogee altitude (442 ft to 13,390 ft), latency is **1.47–1.52 s** and
altitude lost is **34.8–37.0 ft**. It is constant because the fall past apogee is free-fall: how
high you got has no bearing on how long it takes to drop 20 ft.

**The band costs 3.7x the dwell, which inverts the design assumption.** Falling 20 ft from rest is
1.115 s; the dwell is 0.300 s; one sample period is 0.059 s — total 1.474 s, matching the
measurement to 2%. **If apogee latency ever needs cutting, cut the BAND, not the dwell.**

**Depth alone never fires.** Single-sample spikes at 5, 15, 19.9, 20.1 and 50 ft below the running
max are ALL rejected — persistence is what fires, not depth. So at 17 Hz the band is not doing the
rejection work; **the band's actual job is stopping sensor noise from ratcheting the running max**,
which is a different and still-necessary job.

**Launch: 100 ms stays, and 300 ms was the wrong knob.** Measured at 59 ms/sample, a 100 ms dwell
LAUNCHES on a 3-sample (177 ms) knock; 300 ms needs 7 samples (413 ms). But altitude separates
handling from launch by **three orders of magnitude** (smallest motor: +40 ft at 0.5 s, +117 ft at
1.0 s; handling: 0 ft, always) where a dwell separates them by a **factor of two**. Tuning the
dwell was tuning the weaker discriminator. 300 ms would also have consumed **60% of an A8's burn**.
The dwell stays at 100 ms and altitude does the rejecting; 300 ms is reused for the accel-only
FALLBACK, where the better discriminator is gone and the weaker one should be tightened.

**Window sizing, from the slowest real case.** The A8 is the slowest motor to reach the 50 ft
confirm threshold: **0.557 s**. Worst MEASURED confirmation across all profiles was **944 ms** (the
gentle 4 g profile). `confirm_ms` is **2000 ms** — 3.6x the slowest-case climb and 2.1x the worst
measured confirmation. Generous on purpose: **the risk is asymmetric.** Too short discards a real
launch and the flight records St:0 throughout, which is unrecoverable; too long only leaves an
unpublished PROVISIONAL pending a little longer, which costs nothing observable.

**Cost of confirm-or-revert on the wire:** St:1 arrives **531–944 ms** late (A8 590, F15 531,
gentle 944, H 649) — under one extra St:0 packet at 1 Hz. **MET zero does not move**, because
`launch_ms()` is backdated to the accel gate. With a dead barometer the fallback confirms at
**354 ms** on every profile.

**The altitude confirm is a DELTA FROM t0, not AGL from the pad baseline** — so it inherits no
dependency on the baseline's settling window. Verified rather than assumed: a 63 hPa error in
`groundPressure` (1,795 ft of absolute offset) changes the measured 50 ft gain by **0.6 ft**. The
baseline term cancels, and it is locked in `setup()` before `loop()` ever runs.

### DECIDED 2026-08-03 — deployment events: ONE EVENT, on a TWO-CHANNEL machine

Apogee-only, which is also the standard L1/L2 configuration and what is actually being flown. The
second event is a **build-time flag**, not a second design: the state machine is two-channel from
day one (per-channel spent latch, ch2 gated on ch1 spent), so deferring costs nothing.

**Why not dual-deploy now:** a main charge fires on **absolute AGL**, and **the only AGL number
this system has ever produced is 10 ft from a hand swing.** Committing a pyro to a number never
validated against a real climb is the exact pattern this project keeps removing.

**RELAY 2 HAS A COMPETING USE — recorded so it is not foreclosed silently.** A recovery buzzer is
genuinely valuable for finding a rocket in tall grass. Committing relay 2 to a main charge
forecloses that, and an invisible decision of that kind is precisely what two days of work went
into eliminating. **Revive triggers for dual-deploy:** a flight above ~2,500 ft AGL, or measured
drift exceeding the recovery area.

### CHASE NOW — human and bench lead time, not code lead time

- **EXTERNAL DEPENDENCY ON FRANK (not a code task): the range's deployment-testing bar.** The plan
  says "tested to your range's bar" and **that bar is not a number anywhere.** Get the actual
  requirement from the club/RSO. **Blocks 6.1.** Nobody can write it down but Frank.
- **BENCH TODAY, before buying anything: does the relay coil pull in at LiPo-sagged 3.4-3.7 V?**
  The Feather has no 5 V rail on battery, and the failure mode is a **SILENT NO-FIRE**. Needs only
  a bench supply and a relay. **Cheapest of the four open questions and it gates the hardware
  list** — do it before e-matches or a pyro battery are ordered.
- **BENCH ALSO: the BMP390's real delivered rate at the configured oversampling**, plus the IIR
  `COEFF_3` phase lag at 20 Hz (the same coefficient is a different filter in time). These gate
  `6.0a`'s CONSTANTS, not the decision — and finding out after the restructure is the expensive
  order.

### Reading
`docs/epic6-plan.md` (14 units, fail-safe analysis, ground-test protocol, 11 open questions) and
`docs/adr/draft-0004-frame-type-classification.md` (six-site census; replacement, not addition).

## Previous session's handoff

**`feat/oled-heartbeat` — DONE and MERGED 2026-08-02** (`52e5fe0`). All three items **verified
LIVE on `apogee-gs`, not asserted**: the idle frame renders on a quiet pad with the liveness
glyph cycling and `CLK rtc`; a **STEMMA QT reseat recovered clean** with the render-error count
at **zero**; and the radio loop is provably unharmed (heartbeat still ticking ~1 Hz from inside
the RX loop, dashboard still 200). Kept below for the record:
1. **Periodic redraw** so the display doesn't go dark when the sled is quiet (the defect hit on
   the bench 2026-07-30 — `_oled_update` renders only on an observation callback, so a quiet pad
   sits at luma's cleared-black init state and looks dead).
2. **Idle/quiet page with real content** — ready, waiting for `SRC:1`, clock provenance,
   RSSI `--`, liveness indicator.
3. **Render OFF the RX thread** (severity HIGH) — today a wedged I²C bus blocks packet handling,
   so a *display* fault can stop *telemetry capture*. RX loop publishes a view-model snapshot;
   a render thread consumes it.

**TDD the pure part** (state → rendered content); keep timer + threading glue thin, like
`ground/panel/`. Plan first, then RED.

**EXPLICITLY DEFERRED — do NOT build** (this is the redesign, not the fix): 28 px hero digits,
hand-drawn digits, committed bitmap font, golden-image tests, the three-page system, page
transitions/persistence, RSSI sparkline, burn-in mitigation, stale-hero treatment.

### What the OLED fix taught (2026-08-02)

- **The re-init had to be UNCONDITIONAL because the fault is SILENT.** A power-cycled SSD1306
  comes back reset (charge pump off, display off) but **still ACKs**, so luma writes pixels into
  the dark and nothing raises. Proven: the reseat recovered with **0 render errors and no I2C
  error of any kind** — there was never anything for a triggered recovery to trigger on.
- **`0xAE` was flashing the panel once a second** and was removed. It is cold-start hygiene
  (blank an unconfigured panel while setting it up), **never part of recovery** — a reset display
  is already off. `0xAF` and the charge pump still ship unconditionally every frame, so the
  property survived the fix. Cadence stayed at 1 Hz: a slower tick reduces flash *frequency*
  without removing it, and a rare irregular flash is worse than a rhythmic one.
- **Evidence must describe the RUNNING artifact.** The first reseat passed against a sequence
  that still contained `0xAE`; once that byte was removed, the deployed binary was different and
  the old evidence no longer covered it, so the reseat was **re-run**. Same rule that caught
  preview-output-as-CI-evidence on 2026-08-01. Frank caught this one.
- **The two-layer split is falsifiable, not aspirational:** if the redesign forces a change to
  `spec.py`'s public surface, the seam was in the wrong place — surface that, don't work around it.

**NEXT: Epic 6 (relay deployment)** — safety-critical, gets the slot while attention is fresh.
Epic 6 **before** Epic 7 (separation at main requires deployment to work). Item 3 (the OLED
redesign) is a **consciously-spent exception** to the admission rule, bounded by its closure bar
(below); Epic 6 is what actually unblocks flying, so the redesign must not displace it.

### Hero glyphs — DAYLIGHT PASS, operator-approved (NOT measured)

**Approved 2026-08-02 at 4 px stroke; goldens unblocked.** Judged outdoors on the real panel via
the raw-bitmap probe. **Waved through on operator judgement rather than a measured distance** —
the numbers originally asked for (the distance at which `0689`'s counters stop being distinct,
and whether `10.2k`'s 4x5 px decimal survives at that distance in direct sun) were NOT recorded.
Logged that way deliberately rather than as a closed measurement.
**STILL OPEN, for TWO independent reasons** — (a) the distances asked for (where `0689`'s
counters stop being distinct; whether `10.2k`'s decimal survives at that distance in direct sun)
were never recorded, so this is an approval rather than a measurement; and (b) the probe was
confirmed running by `pgrep -f`, **which can match its own command line** — see the hollow-guard
failure class — so the verification itself may have been hollow. An open item should say WHY it
is open.
**Bounded, accepted risk:** if the counters turn out to fill outdoors later, the cost is redrawing
13 glyphs and regenerating goldens. Nothing structural depends on stroke weight — the layout
derives every horizontal position from `text_width()`/`advance()`, so only the glyphs and the
goldens would change.

### Superseded: the open-verification note that gated this

**Glyphs approved 2026-08-02 on the real panel** (rendered at true 28px via a raw-bitmap SSH
probe; `0689` counters, `10.2k` decimal, `k`, `-84`, `1834`). **But the closure bar says "at
arm's length IN DAYLIGHT", and the lighting of that judgement was not recorded — so the daylight
half is OPEN, not closed.** Same rule as evidence-must-describe-the-artifact: an indoor pass does
not license a daylight claim.
**Confirm outdoors BEFORE the redesign merges.** The specific risk is `0689`: 4 px strokes around
a 6 px counter. Sunlight lowers effective contrast, so counters that hold indoors can fill at
distance outdoors. If they do, **stroke drops to 3 px and all 13 glyphs are redrawn** — which
also invalidates every metric derived from them (`10.2k` = 70 px of 128, the hero band budget,
and any goldens generated in the meantime). **Do not generate goldens until daylight passes.**
Also unrecorded and worth capturing when confirmed: the distance at which `0689` counters stop
being distinct, and which frame is hardest at ten feet — that sets the real legibility floor.

### Item 3 closure bar (ACCEPTED 2026-08-02) — the redesign is DONE when...

At arm's length in daylight, the operator can answer **four questions** without touching the box:
1. **Is it capturing?** — state legible at a glance; idle vs live unambiguous.
2. **How high?** — hero readable from ~1 m, with **defined behaviour above 9,999 ft**.
3. **Is this number current?** — a frozen hero is visually distinct from a live one.
4. **Is the link healthy?** — RSSI and loss readable without decoding text.

Plus two build constraints: goldens are **deterministic across Mac and Pi** (hand-drawn digits +
committed TTF, no system font); and **the drawing-layer swap does not change `spec.py`'s public
surface** — a falsifiable test of whether the two-layer split actually worked.

**Anything not serving those four questions goes to backlog.** By that bar: burn-in mitigation is
IN (it protects question 2 over time), page transitions are OUT, and the trend strip is IN only
if it answers something the hero does not. **No fifth question** — "will the battery last" was
considered and rejected: RED fast-blink on the LED panel already answers it, and duplicating a
signal is not adding one. **Being able to drop things is the test of whether the bar is real.**

### Architecture question to ANSWER next session (not now): Quarto render source of truth

**The mental model was wrong, so rebuild from this.** Frank had been carrying: *the page is built
in the telemetry repo and copied to the site repo for CI to publish.* **What is actually built:**
`projects/lora-flights.qmd` lives in the **site repo** (`~/velezf.github.io`), and CI
**re-executes the Python on every push** (`freeze: false`) — with **unpinned**
`pandas numpy matplotlib seaborn` resolving *latest at run time* on **Ubuntu / Python 3.11**,
while Frank develops on **macOS / pandas 3.0.3**. The telemetry repo ships **DATA ONLY**
(`flights.json` + per-flight CSV) via Stage-1 `flights publish`; it never writes `.qmd`.

**The fork to decide:**
- **Keep `freeze: false`** — CI is the render source of truth and auto-rebuilds on every data
  push; but the render env drifts from Frank's (unpinned deps, different OS/Python), and
  `_freeze/` must stay gitignored (guard added 2026-08-01: `_freeze/projects/lora-flights/`).
- **Switch to `freeze: true` with committed `_freeze/`** — Frank renders locally with the real
  telemetry venv (one env, reproducible, matches what he tests against) and CI needs no Python,
  no kernel, no deps at all; but figures only update **when he remembers to re-render**, and
  **stale output becomes possible again** — the exact failure this session was designed to
  prevent.

**Scope of the decision — it governs ONLY the two matplotlib charts.** The OJS half (value boxes,
selector, summary line, the three Plot traces) reads `flights.json` and the CSV **client-side at
page load** and is **never frozen either way**. That asymmetry is also why a stale-figure failure
is invisible on the page: the OJS numbers stay correct while the Python figures go stale — which
is exactly how preview output got mistaken for CI evidence on 2026-08-01.

### Where the tag lives: `v1.0-portfolio-genesis` is on THIS repo, not the site repo

**`v1.0-portfolio-genesis` tags `lora-rocket-telemetry` at `42eacb5`.** It was briefly placed on
`velezf.github.io` on 2026-08-01 and **moved** (deleted local + remote, re-tagged here) the same
day. **The tag marks a state of the SYSTEM that produced the data** — firmware, packet contract,
RX driver, ground service, storage model, hardening, panel — **not a state of a website**. The
site repo is a *publishing surface*; it carries no tags. Do not re-tag it.

### Follow-up decided 2026-08-01: PIN the CI deps (not `freeze: true`)

**This — not the freeze fork — is the real answer to the blast-radius risk.** Verified facts:
`publish.yml` runs a **full-site `quarto render`** on a **daily cron (`0 6 * * *`)** as well as on
push; `_quarto.yml` sets no `error: true`, so **one page failing to execute aborts the whole
render** and the gh-pages deploy step is skipped — **no project deploys**. With
`pip install … pandas numpy matplotlib seaborn` **unpinned**, an upstream release can fail the
site on a day nobody touched anything.

**Proposed change** — pin that one line:
`pip install jupyter nbformat pandas==3.0.3 numpy==2.5.1 matplotlib==3.11.0 seaborn==0.13.2 requests`

**⚠ SHARED-FILE CAVEAT — the reason this needs its own review.** `publish.yml` is shared:
`el-nino-watch-2026` **also** runs `freeze: false` with its own kernel and **has been rendering
against `latest` for months**. Pinning to Frank's local macOS versions silently changes what THAT
page renders against. **Do not fix one exposure by breaking someone else's working page.** The
proposal must state how we'd know el-nino still renders clean — render it locally against the
pinned set first, or pin and then watch the next 06:00 UTC cron before trusting it. Evidence
baseline: **30/30 recent runs succeeded**, and on the very run that published the flight archive
(`30714197232`, 2026-08-01) **`el-nino-watch-2026` rendered CLEAN — `Cell 1/8`..`8/8`** against
current `latest`. That is the pre-pin baseline: if el-nino breaks after pinning, the pin caused it.

**Why NOT `freeze: true` for `lora-flights`** (settled 2026-08-01): the two matplotlib charts are
the *cross-flight* ones whose whole job is to gain a point when a flight is published. Frozen,
they update only when someone remembers to re-render locally — and since the OJS half reads
`flights.json` **client-side and is never frozen**, forgetting once yields a page **internally
inconsistent with itself** (selector and value boxes show the new flight; the charts silently omit
it). That is worse than either stale-everything or fresh-everything, and far harder to notice.
Also relevant: the coupling is **pre-existing** (el-nino already carries it) and a failed render
does **not** take the live site down — gh-pages keeps serving the last good deploy.

### Error pattern worth keeping: SELF-CORRECTION HAS ITS OWN FAILURE MODE

Three diagnostic-vs-signal failures on 2026-08-02, and **the third ran BACKWARDS**. The first two
were treating a real signal as noise, which teaches you to look harder. The third was the
opposite: pyright diagnostics were attributed **correctly** the first time, then "corrected" into
being wrong, and an alarming — entirely false — report of an agent isolation failure was built on
top of that correction.

**The mechanism: primed to find contamination, contamination was found in evidence that did not
support it.** Looking harder has its own bias. A correction is a claim like any other and needs
the same verification as the thing it corrects — running it, not reasoning about it. This one was
caught only by checking `pwd` from an absolute path, which is also why rule 10 is mechanical
rather than a reminder.

**Rules that must survive the context break** — full text under "Working rules":
- **Admission rule:** admit only if it **(a)** prevents lost flight data, a corrupted record, or
  an ambiguous go/no-go at the pad, **AND (b)** has concrete evidence the failure is real.
- **Budget rule:** at most **one correctness branch + one hardening branch** open at a time.
- New ideas go to Backlog, not explored inline.

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
**Field-time hardening** landed too: PiSugar RTC initialized + `auto_rtc_sync`, systemd clock
gate, and monotonic silence/duration deltas (immune to wall-clock steps); session filenames
are collision-proof. **4.4 dashboard + 4.6 status OLED are merged and deployed** (4.6 for `SRC:1` on the bench —
three plan clauses deferred, see Epic status)
— live Flask/Chart.js dashboard (density pass: header callsign, per-SRC flight badge + live
age, T+, RSSI sparkline, events feed, health line) + SSD1306 status OLED on `0x3d`, both on a
per-SRC **AGL pad baseline** (ALT−baseline while `St:0`; raw ALT untouched in records; resets
on `flight_close`). Bench-verified on `apogee-gs` against live sled telemetry. **EPIC 4 IS CLOSED (2026-08-01)** — 4.5 published the flight archive on F1
alone and it is verified live.
Epic 8 groundwork merged. **`feat/panel-leds` merged 2026-07-31** — six-LED supervisor live and
enabled for boot.

## Ground station (`apogee-gs`) — access

- **SSH:** `ssh rocketman@apogee-gs.local` (key auth, passwordless sudo).
- **Pi Connect:** signed in as device `apogee-gs` (`rpi-connect-lite`, remote shell;
  no screen sharing — headless). Reachable from anywhere, not just the local network.
- **Claude Code:** installed (`2.1.197`), on PATH (`~/.local/bin`), **authenticated** via
  `claude auth login` (claude.ai, Max). Headless `claude -p` works.
- **OS:** Raspberry Pi OS 64-bit, **Trixie / Debian 13** (not Bookworm). **Python 3.13.5**
  (`/usr/bin/python3`), `venv` works. No system `pip` (PEP 668 — use venv). **The
  `apogee-ingest` service runs from `~/gs-venv`** (`ExecStart`), the one env with all ground
  deps: `luma.oled`+`pillow` (pip) and `flask`/`spidev`/`lgpio` (via `--system-site-packages`).
  **System `python3` is no longer sufficient** — an SD-card rebuild must recreate `~/gs-venv`
  (`--system-site-packages`) with `luma.oled`. **`uv` not yet installed**.
- **Repo:** cloned at `~/lora-rocket-telemetry` via a **read-only deploy key** (`apogee-gs`);
  `git pull` works. **The deploy key is read-only and the Pi tracks `origin`, so an unpushed
  branch cannot reach the box by `git pull`** — that is exactly how the 2026-07-31 hand-copy
  drift happened. Deploy unpushed work over SSH from the Mac, never by copying files.
- **Wi-Fi:** home **WideRoad** (priority 0) first, **iPhone 17 hotspot** fallback
  (priority −10, infinite retry, persistent NM keyfile). Networking is netplan-rendered
  → NetworkManager. _(Hotspot secret lives only on the Pi, never in this repo.)_

## Deploying to `apogee-gs` — the sanctioned path

**Code reaches the Pi through git, never by copying files.** The absence of a written path is
what produced the 2026-07-31 hand-copy drift (a stale checkout running hand-placed files, whose
provenance had to be reconstructed afterwards by hashing). **Epic 8's handheld inherits this
procedure** — keep it in one place.

1. **Commit** on the feature branch (Mac). Frank's gate.
2. **Push the branch** to `origin` (Frank's gate — a *branch* push is separate from a `main`
   push). A WIP branch on the public repo is normal, disappears at merge, and gives durable
   off-laptop backup — the other lesson that keeps recurring.
3. **Pi pulls** with its existing read-only deploy key:
   `git fetch origin && git checkout <branch> && git pull --ff-only`.
   **`git status --porcelain` must be empty first** — a dirty tree means undeployed state that
   nobody can reproduce; inspect and discard it before checking out (`git diff` it first: on
   2026-07-31 the local edits turned out to be strictly *older* than the committed versions).
4. **Install units** from the repo — they execute from `/etc/systemd/system/`, not the checkout:
   `sudo install -m 644 ground/<area>/<unit>.service /etc/systemd/system/ && sudo systemctl daemon-reload`
5. **Restart** the affected services (`sudo systemctl restart apogee-ingest`;
   `sudo systemctl enable --now apogee-panel`).
6. **Verify — against the committed artifact, not by eye.** Confirm the installed unit matches
   the repo (`sha256sum` both), the service is `active`, and the *observable output* is correct
   (e.g. the heartbeat file's `ts` advancing ~1 Hz). Only then is a result attributable.

**Rejected alternative — the Pi as a git remote** (`git push apogee-gs <branch>` with
`receive.denyCurrentBranch=updateInstead` on the Pi). Rejected because it needs new machinery,
mutates the Pi's git config, and duplicates a read-only deploy key that already works — while
push-to-origin also buys off-laptop backup. **What we gave up is genuinely attractive, though:
`updateInstead` refuses to update a repo whose working tree is dirty**, which would have
*mechanically blocked* the exact drift we hit rather than merely documenting against it.
Revisit if pushing WIP branches to a public origin ever becomes undesirable.

## Host tests (the Mac) — `.venv-test`

Host tests run under **`.venv-test`** (gitignored): `.venv-test/bin/python -m pytest ground/ -q`.

**One venv, one purpose** — `.venv` is the Quarto/Stage-1 *render* env (its `pyproject.toml`
says so) and deliberately does **not** carry `pytest`; mixing them would repeat the
one-writer-per-file mistake in another form. Recreate with:

```
python3 -m venv .venv-test && .venv-test/bin/python -m pip install pytest pillow
```

**`pillow` added 2026-08-02** for the OLED drawing layer (`ground/oled/draw.py` renders a
128x64 1-bit image). Pinned to nothing, but the host and the Pi's `gs-venv` both currently carry
**12.3.0** — worth keeping aligned, since the redesign's golden-image tests will compare pixels
across the two machines.

**Rebuild implication:** a fresh Mac (or a wiped repo) has **no** pytest anywhere until this is
recreated — on 2026-07-31 pytest was absent from `.venv`, system `python3`, Homebrew, pyenv,
*and* the Pi's `~/gs-venv`, which blocked TDD outright until it was rebuilt. The ground suite is
pure/host-only, so it does **not** need the Pi. Current: **221 tests green**.

## Wired peripherals (bench-verified 2026-07-07)

| Device | Bus | Address / CS | Notes |
|--------|-----|--------------|-------|
| RFM96 LoRa radio | SPI0 | **CE1** (`/dev/spidev0.1`, pin 26); RESET GPIO25 (pin 22) | `RegVersion 0x12`. **Not CE0.** |
| OLED (Adafruit 938, SSD1306 128×64) | I²C-1 | `0x3d` | driven via `~/gs-venv` + **`luma.oled`** |
| PiSugar 3 Plus UPS | I²C-1 | `0x57` batt, `0x68` RTC | `pisugar-server`; auto-shutdown at 5% / 30 s |
| Front-panel LEDs ×6 | GPIO | physical **L→R: `16,12,26,13,6,5`** = 🔵🔵🔴🟢🟢🟢 (per-position, single-LED probed 2026-07-31) | active-high; bring-up via `ground/tools/led_check.py`. Canonical map: `ground/panel/leds.py` (host-tested) |
| Sled 9-DoF (bench, Epic 5.1) | I²C | LSM6DSOX `0x6a`, LIS3MDL `0x1c` | on the sled's STEMMA QT bus alongside BMP390 `0x77` / ADXL375 `0x53` |

**Native LoRa RX** = the repo's `ground/rx/` **SX127x driver** (raw `spidev`+`lgpio`,
host-tested against a fake SPI, CRC-enforcing, RadioHead-header aware). **Blinka rejected —
[ADR 0002](adr/0002-ground-rx-driver-spidev.md)** (RPi.GPIO won't run on BCM2712). OLED uses
`luma.oled`; the panel LEDs use **raw `lgpio`** (same single GPIO story as the RX transport —
no second GPIO abstraction on the box, which the Epic 8 handheld inherits) — the whole ground
stack is Blinka-free. `rocketman`
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
| 2 — Pi 5 ground-station bring-up | ✅ **CLOSED 2026-08-07, 2.2 included.** (2.2 validated router-off/Ethernet-down on hotspot alone — dashboard HTTP 200 by IP and by mDNS name, sled RX lossless throughout. Its "cold-boot rejoin" clause was NOT observed — association was forced — and is closed on the risk argument that the hotspot is a convenience path, not a data path: its failure costs no flight data. Named, not hidden.) (2.2's own acceptance clause is "verify cold-boot rejoin" and the hotspot field test is still open — calling the epic closed while its acceptance clause is unverified is the same claiming-coverage-we-lack pattern removed from the panel docs 2026-07-31.) **2.5 deviates from the plan BY DESIGN** — raw `spidev`+`lgpio`, not Blinka/`adafruit_rfm9x` (ADR 0002); plan text reconciled 2026-07-31. OS/SSH/Wi-Fi/Claude Code/deploy-key clone; radio SPI0/CE1, OLED 0x3d, PiSugar batt+RTC, **6 panel LEDs (per-position map probed 2026-07-31)**; **2.5 RX driver** (`ground/rx/`); **2.6 low-battery auto-shutdown** (+ wake-on-charge complement). **2.2 hotspot fallback field test** carried as the single open **physical validation** (deferred, not blocking — same pattern as the overnight cold-boot item; run post-merge, doubling as the marker-vs-NTP clock check); panel-LED *functions* → Epic 4. |
| 3 — Sled TX firmware + contract | ✅ **Complete.** ADR 0001 locked; encoder/launch/apogee/conversions as host-tested `lib/` units; `src/main.cpp` emits **ADR v1** (`V:1 SYS:7 SRC:1 …`) with live SYS/SRC/SEQ/St/MET (**B4/B5 folded into the integration commit**); **e2e verified** — sled→Pi driver, **22/22 ADR-OK**, 0 CRC errors. |
| 4 — Ground service (decode/log/dash/web/OLED) | ✅ **CLOSED 2026-08-01.** 4.1–4.5 done; 4.6 functionally done for `SRC:1` on the bench (three clauses deferred, below); 4.7 optional, not started. 4.1 decoder (`ground/decode/`); 4.2 **ingest** (`ground/ingest/` + `apogee-ingest.service` — radio owner → JSONL log + `LinkStats` + foreign-SYS/unknown-SRC + Part-97 callsign audit); 4.3 **flight logging** (`ground/flights/` — journal segmentation, multi-bird, export, CLI; index = f(session, ops)); **4.4 dashboard** (Flask + Chart.js, immutable snapshots, density pass) + **4.6 OLED** (`luma.oled` `0x3d`) on a per-SRC **AGL pad baseline**, both bench-verified live and **flown once** (`2026-07-08-F1`, real-RF golden fixture). **AGL baseline v2** merged: pure `pad_baseline()` (stability-gated trailing window) shared by live + derive — the zero **locks at flight_open**, unlocks at close, and `baseline_ft`+`baseline_n` are stored per flight in the index (auditable, reproduces on rebuild). Full ground suite **221 tests** (incl. `feat/rtc-boot-restore` + `feat/panel-leds`). **4.6 is NOT done as specified** (re-marked 2026-07-31): three plan clauses are deferred — **multi-node `SRC:2` display → Epic 7** (no lander exists), **"reuses the handheld's OLED rendering" → Epic 8** (no shared module exists), **"cut a window in the front panel" → enclosure** (still benchtop, not boxed). The clause that IS implemented — "driven straight off each decoded packet" — specifies the defect (render on the RX thread, no idle page) and was amended in the plan. **4.5 DONE 2026-08-01** — the archive is live at
`velezf.github.io/projects/lora-flights.html`, published on F1 alone and tagged
**`v1.0-portfolio-genesis` in THIS repo at `42eacb5`** (moved off the site repo 2026-08-01 —
see "Where the tag lives"). **Verified end to end, not merely built** — see the two-proof
method below. |
| 5 — TEENSY 4.1 SLED RESPIN (onboard fusion + SD recorder) | 🟡 **PLANNED — [`docs/epic5-teensy-respin.md`](epic5-teensy-respin.md)**; closed question (attitude is onboard or not live) + arithmetic in "EPIC 5 RE-SCOPED" above. Gated on F2 flying first. 5.1 hardware evidence done (LSM6DSOX 0x6a + LIS3MDL 0x1c; WHO_AM_I 0x6C/0x3D); raw channels reach the wire via the E+F pad frame (ADR 0005 A1.3). `Roll`/`Spin` stay reserved (ADR 0001 App. A). |
| 6 — Relay deployment (safety-critical) | ⏳ Not started. |
| 7 — Lander payload (`SRC:2`) | ⏳ Not started. Tag names reserved (ADR 0001 Appendix A). |
| 8 — Kids' handheld | 🟡 **8.1 platform groundwork merged** (PR #1, `handheld/`). Bench bring-up pending PiSugar 3 + SRH805S antenna (both ordered). 8.2–8.5 not started. |

## Open branches (pending review/merge)

**NONE OPEN.** `feat/panel-leds` **merged** (`--no-ff`, `6338aa9`) and pushed 2026-07-31 —
12 commits. **Branch cleanup done the same day: 34 stale branches deleted**, each verified an
ancestor of `origin/main` first; Mac, GitHub and Pi now carry **`main` only**. (Deleted tips
remain in the Mac reflog ~90 days, and every commit is in `main`'s history regardless.)

**Heartbeat verification — what was actually proven** (corrected 2026-07-31): the 1 Hz
loop-driven heartbeat was confirmed live on `apogee-gs`, and the running `service.py`,
`heartbeat.py` and the *installed* `apogee-ingest.service` were later verified **byte-identical
(sha256) to the committed versions** — so the result is sound and attributable. What was NOT
sound was reproducibility: the Pi's checkout was on `main`, 19 commits behind, with hand-copied
files and two superseded `ground/clock/` modules. Provenance verified after the fact by hashing,
not by the deploy path — which is why the **sanctioned deploy path** now exists. Re-verified
after the fact from a clean checkout: heartbeat ticking 1 Hz from committed code, all four units
hash-matching the repo, `apogee-panel` `active`/`enabled`, steady state confirmed on the physical
panel (`B_CLOCK` solid pos 2, `G_ALIVE` pulsing pos 6).

`feat/rtc-boot-restore` merged into `main` via `--no-ff` (RTC-boot-restore +
fail-closed clock gate + apogee-attest escape hatch; ADR 0003; verified on a Wi-Fi-OFF cold
boot) — **merged AND pushed** (`origin/main` carries it; the earlier "not yet pushed" note was
stale, corrected 2026-07-31 at the panel-LEDs merge).
Recent merged branches: `feat/status-oled` (4.4 dashboard density + 4.6 OLED + AGL baseline),
`feat/ground-decoder`, `feat/ingest-{linkstats,records,flights-model,service}`,
`feat/callsign-id`, `feat/flight-logging` (+ earlier Epic 1–3 branches).

## Locked decisions

- **NON-TELEMETRY FRAMES DO NOT PARTICIPATE IN FLIGHT ACCOUNTING (decided 2026-08-02).**
  A `CALL` beacon is the station identifying itself under Part 97 — **evidence the radio is
  alive, not evidence about the flight.** This is the **foreign-traffic rule applied to a second
  class of non-telemetry frame**: counted and segregated, never merged. Canonical statement of
  that precedent is `ground/ingest/core.py:12` — do not restate it here.
  1. **`packets_rx` EXCLUDES beacons; count them separately as `beacons_rx`.** They carry no
     `SEQ`, so they cannot participate in loss accounting — putting them in the denominator while
     they are absent from the sequence space would make the published loss percentage read
     artificially **LOW**. Visible, not discarded.
  2. **Beacons DO NOT reset the silence timeout and DO NOT extend `t_end`.** The 90 s rule detects
     "the vehicle stopped sending telemetry". If beacons held a flight open, a landed rocket
     beaconing every 60 s would **never close** — it would run until the battery died, and
     `duration_s` would become the interval between ID transmissions rather than the flight.
     **The flight must not be defined by its callsign.**
  **GENERALISES INTO `draft-0004`:** the principle underneath both halves is *"frames that are not
  telemetry do not participate in flight accounting"*. Stated that way it also covers **dump
  frames** if C2 is ever built, and it means the THIRD class resolves itself without a new
  decision. Flagged for the draft; naming the principle is the point.

- **Packet format v1** ([ADR 0001](adr/0001-packet-format-v1.md)): keyed `KEY:VALUE` ASCII,
  leading `V:1`; `MET` time token; **no app-layer checksum** (rely on LoRa PHY CRC); `SYS`
  default `7`; `SRC` `1=sled, 2=lander`; additive tags tolerated, unknown tags ignored.
  Human-readable index: [`docs/telemetry-dictionary.md`](telemetry-dictionary.md).
- **Ground RX = raw spidev + lgpio** ([ADR 0002](adr/0002-ground-rx-driver-spidev.md)),
  Blinka rejected on Pi 5.
- **Field-time integrity** ([ADR 0003](adr/0003-rtc-boot-restore-clock-gate.md)):
  `apogee-rtc-restore` oneshot reads the PiSugar RTC into the system clock at boot
  (`Before=apogee-ingest`); ingest's clock gate is **fail-closed** — `year≥2024 AND (NTP OR
  RTC-restore marker)`, so a plausible-year timesyncd floor alone no longer passes. Operator
  escape hatch = `attest_clock`. Verified on a Wi-Fi-OFF cold boot (2026-07-27).
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

1. **`St:3` = landed** — a landed flight-state code so the ground can auto-close a flight on
   landed (today it's 90 s silence + manual only — there is no landed signal).
2. **SRC per-unit build config** (`-DSRC_ID` per device env) — never a shared constant; two
   sleds from one repo must not both claim `SRC:1`.
3. **±10 % TX-interval jitter** — anti-lockstep for simultaneous birds. **TRIGGER CORRECTED
   2026-08-08 (Frank): revives when the LANDER (`SRC:2`) becomes real** — the node designed to
   transmit concurrently with a sled. It does NOT revive for the Teensy respin: the two SLEDS
   never transmit simultaneously in the field (one rocket flies at a time, the other sled is
   powered off; the handheld is RX-only), so sled-coexistence collision design was
   over-engineering for a scenario that can't occur. The field rule that replaces it lives in
   `docs/field-checklist.md` ("one sled powered at a time"). Interleaved traffic on the BENCH
   (Feather + Teensy powered together during bring-up) is expected, fine, and deliberately
   observed — see `docs/epic5-teensy-respin.md` bring-up note. Multi-node ground findings
   (per-SRC segmenter state, both-sources-`St:1`) file under **Epic 7 groundwork**, lander
   trigger — not as a second-sled blocker.
4. **Part-97 station ID** — `CALL:<callsign>` at TX start / ≤9.5 min / graceful shutdown,
   per-unit `-DCALLSIGN`. Ground side (decoder fixture + ingest `id` audit + CALL↔SYS
   binding) already merged; the **lander (Epic 7) inherits the ID-timer obligation.**
5. **`BAT` battery go/no-go tag** — a derived pad-check go/no-go indicator to surface on the
   dashboard/OLED (raw volts already ride `Batt:`; this is the launch-readiness signal).
6. **St-dependent TX rate** — fast in boost/descent, slow on pad/landed, for flight-record
   resolution. **Coupled to detection:** today the ADXL is read *once per TX loop* (`delay(1000)`
   in `firmware/src/main.cpp` — **launch detect samples at the 1 Hz TX cadence, no FIFO/ISR**),
   so a faster boost-phase TX rate *also* sharpens launch/apogee detection and MET granularity.
   **Do the duty-cycle / airtime math first** (ISM-band airtime budget + LoRa ToA at the chosen
   SF/BW) before picking rates; a cleaner design may decouple detection sampling (fast, FIFO/ISR)
   from TX cadence (airtime-limited). Re-runs the e2e gate.

## Physical tasks (Frank — not CC)

- [x] **Overnight/no-network cold boot — CLOSED 2026-07-27** (`feat/rtc-boot-restore`, Option B).
      _Diagnosis (2026-07-13 boot, WITH Wi-Fi):_ at boot the kernel set the clock from the Pi 5's
      `rtc0` → **1970** (no/dead coin cell), then `systemd-timesyncd` restored its **saved-clock
      floor = last shutdown (Jul 08 21:51)**, and **nothing read the PiSugar RTC into the system
      clock.** apogee-ingest's `year ≥ 2024` gate passed on that stale floor and opened a
      **mis-dated session** (`session-20260709T015114Z`, really Jul 13); only **NTP** (15:40:10)
      corrected it — offline it would have been silently wrong.
      _Verification (2026-07-27, true Wi-Fi-OFF cold boot, **no network at boot** — Ethernet
      physically unplugged until +15 min so no NTP could sneak in):_ **PASS.** The floor bug
      reproduced exactly — the system came up at the timesyncd floor (`sys_before` = `14:53:50Z`,
      ~62 min stale); `apogee-rtc-restore` read the PiSugar RTC (`11:56:09-04:00`) and `decide()`
      returned **`action=set / reason=sys-behind-rtc`** (Δ ≈ 3739 s ≫ 120 s `_FORWARD_THRESHOLD_S`),
      stepped the clock, and dropped `/run/apogee-rtc-restored` — **before** `apogee-ingest` started
      (`11:56:09` vs `11:56:16`). Ingest's fail-closed gate then passed **on the marker, not NTP**
      (first NTP sync was `12:11:13`, ~15 min later when the cable went in — it postdates both the
      clock-set and the session-open, proving the link was dead at boot) and opened a
      **correctly-named session** `session-20260727T155616Z-8059ca.jsonl`.
      _Criterion (1) — PiSugar RTC hold — satisfied free by the hiatus:_ the RTC kept correct
      wall-clock across a **~13-day fully-powered-off** span at 69 % with no drain (read back
      `2026-07-27T10:45:47-04:00` on power-up); the 30-min hold test need not be re-run.
- [x] **2.2 hotspot field test — CLOSED 2026-08-07** (validated at home with the router OFF,
      which removed the need for the field trip: no home infrastructure was in play). Away from
      home Wi-Fi, confirm fallback to the iPhone hotspot. **The last item of ORIGINAL Epic 1-4
      scope still open.** Not blocked on any code and not blocking anything — it needs physical
      absence from the home network, so it cannot be closed at the bench by any amount of work.
      **Un-park trigger:** the first trip away from home Wi-Fi with the box, which the first
      launch satisfies by construction. Doubles as the marker-vs-NTP clock check (the clock gate
      must pass on the RTC marker, not on NTP that only arrives later).
- [x] **Live shake test — done 2026-07-08** (see first flight below); hand-*jerk* peaked 2.2 g
      (missed the 1 Hz sample), a sustained **circular swing** hit 6.4 g and tripped it.

## First flight — `2026-07-08-F1` (shake test, bench)

The full live cycle is proven end-to-end on real RF: **pad→ascent→descent→close**, dashboard
badge/T+/AGL, OLED ascent page, and the AGL **baseline reset on `flight_close`** all fired.
Index entry: **dur 87.6 s, 75 rx, 1 lost** (one real SEQ gap mid-swing), peak −74 ft raw,
**AGL baseline −84 ft (n 15)** → peak **10 ft AGL**, RSSI −38..−14. **Derivation round-trip
byte-identical** (rebuilt twice → same index; the annotation survives). Captured as a
**version-controlled golden fixture** — `ground/flights/tests/fixtures/f1_{session,ops}.jsonl`
(widened to include the 19 quiet pre-boost pad packets so the baseline recomputes) +
`test_f1_golden.py` asserts decode→segment→derive reproduces F1 exactly (incl. baseline), so
real over-the-air bytes now guard every future contract change. (Profile is bench noise — a
swing, not a climb; the 10 ft "peak" is sensor noise. A real *trajectory* awaits an actual flight.)

## Immediate next steps

1. ~~**4.5 web publish**~~ — **DONE 2026-08-01. EPIC 4 CLOSED.** Live at
   `velezf.github.io/projects/lora-flights.html`; tagged **`v1.0-portfolio-genesis`** in **THIS repo** at `42eacb5`. F1 annotated from the ops journal (`flights annotate` → `rebuild`, byte-identical).

   **THE TWO-PROOF PUBLISH METHOD — reuse this, don't re-derive it.** Two risks, orthogonal, each
   invisible to the other's test; neither substitutes for the other:
   - **Stale figures (`freeze`)** — invisible on the page, provable ONLY in the **Actions run log**:
     `Executing 'lora-flights.quarto_ipynb'` + `Cell N/M` under the *Render Quarto site* step.
     **LOCATION-PINNED:** `quarto preview` prints *character-identical* strings, so terminal output
     is NOT evidence — the log must come from a real run at
     `github.com/velezf/velezf.github.io/actions` triggered by a push to `main`. This exact
     confusion happened on 2026-08-01 and nearly shipped an unverified tag.
   - **Missing data files (`resources:`)** — invisible in the log, provable ONLY by `curl -sI`
     against the **`https://velezf.github.io/...`** URLs (not `localhost`). **Capture the 404
     baseline BEFORE deploying** so the 404→200 transition is itself proof.
   - **Then verify CONTENT, not just status:** a `200` proves a file exists, not that it is the
     right file. Fetch the served `flights.json` and confirm the annotation.
   - Why neither alone suffices: the **OJS half reads `flights.json` client-side and is never
     frozen**, so page numbers stay correct while Python figures go stale; and a CSV-only 404
     leaves value boxes populated over three empty charts.
2. **4.5 (historical detail — data-driven model).** `flights
   publish` ships **DATA ONLY** into the portfolio site (a `flights.json` summary + per-flight
   CSVs under `projects/lora-flights/`) — never a `.qmd`. Stage-1 generator done in
   `ground/publish/` (pure, 8 tests): `flights_summary`, `permalink`
   (`…/projects/lora-flights.html?flight=<id>`), `write_flight_data`. The archive page is a
   hand-polished **Stage-2** artifact authored once in the site repo: `projects/lora-flights.qmd`
   — matplotlib/seaborn hero charts (`jupyter: lora-rocket-telemetry`, **`freeze:false`** so CI
   re-executes on data pushes) + **OJS** value boxes / selector / `?flight=` deep links. **Site
   env:** a uv `.venv` + registered `lora-rocket-telemetry` kernel in *this* repo (per the
   Portfolio Workflow doc); the site's action gets **one authorized line** registering that
   kernel in CI (no dep additions — CI already has pandas/numpy/matplotlib/seaborn). Mock built
   with F1's real data on pages-repo branch `feat/flights-section` (committed, **not merged** —
   Frank reviews + merges + pushes; then **Stage-3 tag** `v1.0-portfolio-genesis`). **Local preview — run from the SITE repo** (`~/velezf.github.io`, where the `.qmd`
   lives), with an absolute path to *this* repo's render venv (verified 2026-08-01; the earlier
   `$(pwd)/.venv` form was wrong — it silently assumed both repos were one directory, and the site
   repo has no `.venv` at all):
   `QUARTO_PYTHON=~/code/lora-rocket-telemetry/.venv/bin/python3 quarto preview projects/lora-flights.qmd`
   **`QUARTO_PYTHON` is DISCOVERY-ONLY, not execution.** The page declares
   `jupyter: lora-rocket-telemetry`, so Quarto resolves a *kernelspec by name* and
   `~/Library/Jupyter/kernels/lora-rocket-telemetry/kernel.json` pins the interpreter as an
   **absolute path** into this repo's `.venv` — independent of cwd and of `QUARTO_PYTHON`. The env
   var only gives Quarto a Python that *has* `jupyter` so it can enumerate kernelspecs at all
   (the system Pythons are bare — the same gap that had no `pytest`).
   **A clean preview does NOT predict a clean Action run.** It shares kernel-resolution-by-name,
   cell execution, `freeze:false`, and n=1 chart survival — but it CANNOT test the CI
   `ipykernel install` step (locally the kernelspec already exists) or the gh-pages deploy.
   Necessary, not sufficient.
   **4.5 IS UNGATED (2026-07-31).** The old "gated on the first real flight" was never tested —
   the Stage-1 pipeline was run against F1 and emits a **complete, well-formed payload**:
   `peak_agl_ft 10`, `baseline_ft −84`/`baseline_n 15`, `duration_s 87.556`, `packets_rx 75`,
   `packets_lost 1`, `loss_pct 1.32`, `rssi −38…−14`, plus a 75-row CSV and a resolving
   `?flight=2026-07-08-F1` permalink. **Nothing breaks at n=1.** Two things are *thin* (the
   selector has one option; the AGL profile is a 10 ft blip then ~80 s flat at 1 ft) and one is
   **unverified** — the Stage-2 page lives in the *site* repo, so any cross-flight element
   (peak-over-time, flight count, personal best) needs an n=1 fallback or hiding until n≥2.
   Check that at review time; it is the only thing that could look *broken* rather than thin.
   **Two conditions:** (a) `flights annotate 2026-07-08-F1` first — `motor`/`field` are empty
   strings and would render blank; set them (`motor: none`, `field: bench`) so the honest
   labelling rides in the data, not in prose; (b) **do not dress up the 10 ft** — it is hand-swing
   sensor noise, not a climb. Presenting it as an achievement would be the
   claiming-coverage-we-lack pattern, in public.

   **Execution order:** annotate F1 → Stage-1 `flights publish` → Frank reviews/merges/pushes
   pages-repo `feat/flights-section` → add the one authorized kernel line to the site Action →
   verify CI re-executes (`freeze:false`) and the permalink resolves → local preview gate →
   tag `v1.0-portfolio-genesis`. **This closes Epic 4.**
2. **OLED branch — ONE branch, not three** (`feat/oled-heartbeat`): idle page + **render off the
   RX thread** + reinit recovery. Frank's stated next start after 4.5. See Backlog for detail.
3. **Panel LEDs — DONE and merged** 2026-07-31.

## Working rules (adopted 2026-07-31)

**Admission rule.** Admit work into the current scope only if it **(a)** prevents a failure that
loses flight data, corrupts the record, or misleads the operator at the pad, **AND (b)** has
concrete evidence the failure is real — an incident, a probe, or a signal that actively lies.
Clause (b) is what makes it a rule and not a mood: `feat/drift-guards` failed on (b) (three
historical incidents, two of which its mechanism could not catch) and was deferred; the LED map
passed on both and was built.

**Currently ADMITTED** (all small; the three OLED items collapse into one branch):
`write_ok` wiring (RED's disk-full leg is on the INERT register — it claims coverage it lacks) ·
OLED render off the RX thread (a display fault can stall capture) · OLED idle page (observed
2026-07-30) · battery-discharge logging (15% is unmeasured; if the pack is the non-Plus it is
~5 min of warning, not ~20).

**Budget rule.** **Two slots, evidence-gated** — at most one *correctness* branch and one
*hardening* branch open at a time. Anything admitted must name the failure it prevents and the
evidence for it. The backlog never enters the critical path on its own momentum; it waits for a
flight to produce evidence.

**Epic order: 6 before 7.** Epic 7's closure bar requires separation *at main*, which requires
deployment to work — building the lander first yields a payload with nothing to eject it. Epic 6
is also the only safety-critical epic and deserves the slot while attention is fresh; its 6.2
arm-pin state machine is pure host-tested logic, which this project does well.

**Epic 7 closure bar.** Done when, **in one real flight**: a `SRC:2` node transmits valid v1
packets that the ground service logs as a **separate flight record**; its transmissions **do not
collide** with `SRC:1` (measured, not assumed); it **survives boost-g** and impact; it
**separates at main and is recovered**; and its atmosphere fields appear on dashboard + OLED.
*Sequencing:* 7.3 forces the two deferred **Epic 6 firmware riders** (per-unit `-DSRC_ID`, ±10%
TX jitter) — they stop being optional the moment a second transmitter exists, so **admit them
into Epic 7, not Epic 6**. 7.6 also unblocks 4.6's deferred `SRC:2` clause. Cheapest first slice:
**7.1 + 7.2 + 7.3**, pure bench work on hardware already in hand, retiring multi-node risk before
any mechanical commitment.

## Backlog (not now)

- **`feat/oled-heartbeat`** — the OLED goes silently blank in two distinct ways, both fixed by
  **one periodic render loop** (redraw every 1–2 s instead of the current render-on-packet-only):
  1. **No idle page** — `_oled_update` (service.py) renders *only* on an observation callback, so
     with no sled transmitting the panel sits at luma's cleared-black init state = looks dead
     (found 2026-07-30: OLED "dark" was really *no content* on a quiet pad; raw white-fill + a
     luma text frame proved the whole HW/luma path good — genuine SSD1306, charge-pump lit it).
     Fix: a startup + periodic **idle/pad frame** ("apogee-gs ready / waiting SRC:1 / RSSI --").
  2. **Silent reset-blank** — luma sends the init sequence only at startup; a power-cycled OLED
     (connector reseats in transit) resets to display-OFF but **still ACKs**, so luma writes
     pixels to a dark panel, no error anywhere. Fix: the same loop **re-sends the init** each
     redraw (unconditional periodic re-init — covers the case an on-I²C-error check can't see,
     since a reset SSD1306 throws nothing).
  A periodic redraw-with-reinit is the single smallest change covering both. **Same bug class for
  the Epic 8 handheld OLED** — replicate there. (Merges the earlier `oled-reinit-recovery` +
  `oled-idle-page` notes — they converge on one heartbeat loop.)
  **Layout redesign is DESIGNED** (2026-07-30, design-only): number-dominant live page — 28px
  hero altitude AGL, inverted state band + ▲/▼ glyph, RSSI icon+dBm, thin full-width trend strip
  (combine, number wins on cramping); three pages (idle/live/summary) sharing a common header;
  pad-only diagnostics (baseline) live on the idle page only. **Fonts:** no TTF on the Pi and a
  system font breaks golden-image tests (host vs Pi diverge), so **hand-draw the hero digits**
  (~12 glyphs, bold, pure) + **commit one bold pixel TTF** to `ground/oled/fonts/` for small text.
  Render = pure `render(snapshot)->PIL.Image`, golden-image tested. Burn-in: **1 px frame-shift
  every ~30–60 s + dimmed idle contrast** (never blank — blank re-creates "dark looks broken").
  **Stale hero (lying-display — same class as the flight LED):** if packets stop mid-flight the
  altitude number **freezes and is visually identical to a live reading**. Needs a freshness
  treatment on the hero — invert/blink it and/or show a data-age ("2.4s") — gated by a
  **state-dependent** threshold: silence on the **PAD is normal** (no alarm), silence during
  **ASCENT/DESCENT is not** (alarm fast). Drive it off `last_rx_ts` age (same field the RX LED
  uses), threshold = f(flight state). Untreated, a frozen hero is the OLED twin of a lit
  flight-LED after an ingest crash.
  **Page selection & persistence:** page is chosen by **flight state, not a timer** — IDLE (no
  flight open), LIVE (a flight open, any SRC), SUMMARY (after `flight_close`). **SUMMARY holds
  until the next flight opens — NOT a timeout**: it is what the operator reads walking downrange
  with the box in hand; a timeout would blank the one number they went to fetch. Multi-SRC: LIVE
  shows the active SRC (or cycles). **If ingest restarts mid-flight:** derive the current page
  from the session/flight state at startup (recoverable), **not** in-memory-only flags — a restart
  must return to LIVE if a flight is still open, not drop the operator back to IDLE.
  **REQUIREMENT — render OFF the RX thread (severity: HIGH).** Today `_oled_update` renders
  *synchronously inside the RX loop*, so a wedged I²C bus (luma write hangs) **halts packet
  handling** — a ~$10 display fault can stop the box's only job, telemetry capture, and stall
  the heartbeat into RED. `feat/oled-heartbeat` MUST move rendering to its own thread (RX loop
  publishes a view-model snapshot; the render thread consumes it), so no display fault can ever
  block capture. This is a correctness requirement of the epic, not a nicety.
- **`feat/panel-leds`** — six front-panel LEDs (GPIO 5/6/13 green, 26 red, 12/16 blue) as an
  operator-glance surface. **Architecture LOCKED** (2026-07-30): a **supervisor** (`apogee-panel`
  systemd unit, independent of ingest) **owns all six GPIO lines**; ingest is only a *state
  source* — it publishes the heartbeat state file (**one writer**; the path is `STATE_PATH` in
  `ground/panel/heartbeat.py` — canonical there, deliberately not restated here). Fail-closed by default:
  no fresh ingest state → supervisor drives the "down" pattern. This is the fix for the
  lying-panel problem — an ingest crash mid-flight must not leave the flight LED lit; the
  supervisor (not ingest) owns it and clears it on stale heartbeat. **State file:** heartbeat
  `ts` written on a **1 Hz timer independent of traffic** (NOT event-driven — the exact
  `_oled_update` bug), with `last_rx_ts` a **separate** field; **stale threshold 3 s** (tolerate
  2 missed ticks, avoid flap); **atomic temp+rename**; parse-fail = retain last-good ts (age out,
  don't flip). **Assignment:** RED (supervisor) = NOT RECORDING (ingest down / gate refused /
  **write-failing — NOT YET WIRED**, see below), slow-pulse=shutdown, fast=low-batt.
  **Logical names bind to a physical POSITION** (left→right, 1–6) — never to a GPIO number and
  never to an ordinal like "the first blue", which is unresolvable standing at a real panel and
  is exactly what turned this into a bench question. Confirmed layout 🔵🔵🔴🟢🟢🟢:
  **pos 1** `B_RF` RF trouble (foreign=slow, CRC-climbing=fast) · **pos 2** `B_CLOCK` clock
  provenance (solid=RTC, blink=attested, off=unknown) · **pos 3** `RED` NOT RECORDING ·
  **pos 4** `G_FLIGHT` flight open (solid) · **pos 5** `G_RX` RX activity · **pos 6** `G_ALIVE`
  alive-heartbeat. RED and `B_CLOCK` are adjacent on purpose — both answer "is my data good?",
  so trust reads in one glance; `G_FLIGHT` sits on RED's other side as the recording-status
  pair. **Canonical map:** `LED_GPIO`/`COLOR`/`lamp_test_order()` in `ground/panel/leds.py`,
  host-tested for mutual agreement.
  **Blink vocab** off/slow/fast/solid + heartbeat; **power-on lamp test** sweeps all six (dead-LED
  detection + resolves the physical L→R order). **Pure `led_states(state)->{led:BlinkState}` core,
  host-tested** like the clock work; thin Pi-only GPIO shell. **Doc bug — FIXED 2026-07-31:** the
  wiring doc's LED order was reversed in *every row*; each line was lit individually on the
  bench and its position counted. Lesson recorded there: single-LED probing is the only reliable
  method — a running sweep is too fast to call, and a whole-panel glance invites the left/right
  slip that produced the original wrong map.

### Panel signals designed but INERT

**Canonical list — the ONE place that says which panel signals are wired end-to-end and which
are not.** Code cites this heading by name (`ground/panel/{leds,run_panel}.py`); anywhere else
that describes panel behaviour must link here rather than restate it. The hazard being managed:
a designed-but-inert safety signal is *worse than an absent one*, because the panel reads
"fine" while the condition it was meant to catch goes unshown. **Nothing may be described as
panel-covered until it comes off this list.**

| Signal | Designed behaviour | Why it is INERT today | To activate |
|---|---|---|---|
| **RED — write-failing leg** | RED SOLID when the session log stops persisting (disk-full, failed append) | The pure core honours `write_ok=False` (tested), but the ingest publisher **hardcodes `write_ok=True`** — the leg is unreachable end-to-end | Queue-backed writer exposes a health flag → `state_snapshot(write_ok=...)` |
| **`B_RF` (panel position 1) — ENTIRELY** | RF trouble: foreign traffic (slow) / CRC climbing (fast) | **The signal can never fire.** `state_snapshot()` in `ground/ingest/service.py` publishes only `ts`, `last_rx_ts`, `flight_open` — `crc_climbing` and `rf_foreign` are read by the supervisor but **nothing ever sets them**. Position 1 is permanently dark. Found 2026-08-06 while writing the field checklist; the register had a gap | Publish RF counters in the heartbeat snapshot |
| **B_CLOCK — attested case** | SLOW blink = operator-attested clock, distinct from SOLID = RTC-restored | The `/run` marker is an **empty touch file**, so the supervisor cannot tell restore from attest; `read_provenance()` can only return `rtc`/`unknown` and attested reads as RTC | `restore_clock`/`attest_clock` write the *reason* into the marker; supervisor reads it |

**Consequences to state plainly:** RED does **not** cover disk-full, and B_CLOCK does **not**
distinguish an attested clock from an RTC-restored one. Wire both before the panel is trusted
for go/no-go. Fuller rationale for each in the backlog entries below.

- **Writer health → `write_ok` (RED's write-failing leg is INERT — see the table above).** The pure
  LED core lights RED SOLID on `write_ok=False` (tested), but the ingest heartbeat publisher
  **hardcodes `write_ok=True`**. Fix: have the queue-backed writer expose a health flag (last
  append failed / queue overflowing) and feed it into `state_snapshot(write_ok=...)`. Wire this
  before relying on the panel for go/no-go.
- **Battery-low threshold — turn 15% into a MEASURED minutes-of-warning.** `LOW_BATT_PCT=15`
  is derived from an *assumed* ~5 W draw; the real draw (Pi 5 + radio + OLED + six LEDs) is not
  that number. The supervisor already polls `battery_pct` at ~1 Hz (once per `TICKS_PER_SEC`
  ticks, not every tick) — **log it over time to get the actual discharge curve for free**, then
  reset `LOW_BATT_PCT` from real minutes-to-5%.
  **Where it belongs:** the supervisor (`apogee-panel`) is its OWN process, so it may write its
  own output — but **NOT** a second writer to any of the three data files (session JSONL / ops
  journal / flights index; one-writer-each is locked). Log to **journald** (rate-limited — on a
  ≥1% change or ~1/min, never 8 Hz), the established audit channel (like the clock events): no new
  file, rotates, no SD wear, `journalctl -u apogee-panel` gives the curve. Also feeds a future
  **runway estimate** (“~18 min left”) on the OLED summary page. (Confirm the Plus 5000 mAh pack
  by eye first — see the `LOW_BATT_PCT` comment; 15% only holds for the Plus.)
- **Clock-provenance in the /run marker (B_CLOCK attested case — INERT, see the table above).**
  The supervisor can only tell clock-trusted (marker present) from unknown (absent); it can't
  distinguish RTC-restore from a manual attest, so B_CLOCK shows solid=RTC even when attested.
  Fix: have `restore_clock`/
  `attest_clock` write the reason INTO the marker (they touch it empty today) so `B_CLOCK` (pos 2) can blink
  on attest. Small follow-up to the clock module.
- **`feat/drift-guards` — EVIDENCE UPDATE 2026-08-02: a drift-shaped failure fired, but NOT the
  predicted one.** Within an hour of starting parallel agents something drift-shaped did occur —
  and it was **NOT agent contamination**. An earlier claim in this session that it was is wrong,
  and was amplified before being checked. **Actual mechanism: an unverified assumption about the
  assistant's OWN working state.** The Bash tool persists working directory between calls; one
  earlier `cd` into an agent worktree silently relocated six subsequent "my repo" commands. `git`
  answered honestly — about a tree nobody meant to be in — producing an alarming and entirely
  false report of an isolation failure. **Worktree isolation held; rule 2 was never violated.**
  **What this is evidence FOR:** mechanical verification of assumed state, not a doc-drift
  detector. The cheap fix is rule 10 in `CLAUDE.md` (absolute-path discipline); try that before
  building any guard.
- **`feat/drift-guards` — NOT NOW, deliberately deferred (2026-07-31).** Would pair a
  non-duplication test with the unit-install guard below. **Deferred because the sanctioned
  deploy path removes most of the mechanism it would detect:** hand-copying happened because
  there was no sanctioned route to the Pi; once deploys go through `git pull`, the Pi cannot
  silently diverge. Building a detector for a failure mode we just designed out is backwards.
  **Re-evaluate after the deploy path has been used a few times** — if drift appears *despite*
  it, build then, against real evidence rather than three historical incidents.

  **Design, if it is ever built — INVERT the obvious approach.** The instinct is "assert docs
  agree with the authoritative constant". Better: **assert docs don't restate it at all.** You
  cannot detect a *wrong* path by searching for the *right* one — you'd have to shape-match
  (`/run/apogee[-/][\w-]*\.json`) and compare every hit, which brings regex maintenance and
  false positives on historical notes. Enforcing *non-duplication* needs no registry of expected
  values, has almost no false-positive surface, and is ~30 lines. Scope to **literal values
  only**; see the "cite, don't restate" convention in `CLAUDE.md` (adopted 2026-07-31, free).

  **Why the obvious version was worth less than it looked** — of the three incidents that
  motivated it, a path-drift test would have caught **one**:

  | Incident | Caught by a path-drift test? |
  |---|---|
  | Escape hatch restated across four locations | **No** — prose procedure, no literal to compare |
  | LED L→R order, `RESUME:63` vs `:270` | **No** — prose/emoji ordering, not a path |
  | State path wrong in `RESUME:257` + `heartbeat.py:3` | **Yes** |

  Two of three were prose, where the convention is the only workable tool. Recorded so this
  isn't re-derived.
- **The ops journal is the ONLY irreplaceable artifact in the system — it has no backup.**
  Everything else regenerates: sessions are raw capture, flights are derived, and the index
  rebuilds byte-identically from `derive(session, ops)`. **Annotations are human input and live in
  exactly one place — `~/apogee-data/ops-journal.jsonl` on an SD card.** Losing that card re-opens
  the very un-re-derivability gap closed on 2026-08-01 (the published `flights.json` carried
  annotations that no journal could reproduce). Distinct from the data-hop item below: that one is
  about workflow convenience, this one is about permanent loss of the only non-reproducible data
  in the project. Decide a backup/commit strategy.
- **Publish data hop — decide a home for the workflow.** The ops journal and sessions live on the
  Pi; the site repo lives on the Mac (`~/velezf.github.io`), so every `flights publish` needs a
  data transfer. Worked fine as a one-off on 2026-08-01, but decide where this workflow lives
  before the ad-hoc `scp` becomes habit.
- **CI kernel assertion (`jupyter kernelspec list | grep -q lora-rocket-telemetry`) — NOT NOW.**
  A missing kernel surfaces as a confusing *render* failure, not at the registration step that
  caused it; the one-line grep is an **assertion** (fails at the right place) rather than a
  **diagnostic** (dumps output nobody reads — and unread output stops being read even when it
  matters). Deliberately deferred: by the admission rule it fails clause (a) — it prevents a
  confusing debug session, not lost flight data. **Trigger to build it: the kernel step proving
  flaky across runs.** Recorded so the probe-vs-assertion reasoning isn't re-derived.
- **OLED redesign — three design gaps to close BEFORE building (raised 2026-08-02).** None are
  in the fix branch; all three are item-3 design decisions.
  1. **Digit overflow on the hero.** A 28 px hero fits ~4 digits. An L1 flight above **9,999 ft
     has no defined behaviour** — shrink the font, switch to `10.2k`, or clip? That is precisely
     the flight where the display most needs to work. Note the overflow policy belongs in the
     PURE layer (`_hero()` in `ground/oled/spec.py`), where it is testable; the drawing layer
     only picks a font size.
  2. **Trend-strip window — sample-based or time-based?** At 1 Hz, ~60 samples is the last
     minute: fine up to apogee, but **flat for the whole descent under chute**, when the strip
     would show nothing useful for minutes.
  3. **Hero freshness (the highest-consequence remaining lie).** If packets stop mid-flight the
     hero **freezes and is visually identical to a live reading** — the same lying-display class
     removed from the LEDs (a lit flight LED after an ingest crash). Needs a freshness treatment
     driven off `last_rx_ts` age with a **state-dependent** threshold: silence on the PAD is
     normal, silence during ASCENT/DESCENT is not.
- **SRC alias — display SRC numbers as callsign-style names (FLAVOR today; decided 2026-08-02,
  not built).** Show `KC3ZTQ-1` rather than `SRC:1 KC3ZTQ` — shorter, and real ham notation
  instead of decoration. Optionally pair with tactical names (`SLED`, `LANDER`) for
  glance-reading, SSID where identity matters (logs, the published page).

  **HARD CONSTRAINT — presentation only.** The wire format stays `SRC:1`: ADR 0001 v1 is locked,
  the e2e fixture gate protects it, and spending airtime on a name the ground station already
  knows is backwards. **Stored records keep raw `SRC`**, the same discipline as raw `ALT` never
  being transformed. The alias resolves at DISPLAY time.

  **Where the map lives — two halves, different owners; conflating them is the trap.** The ROLE
  (`1=sled, 2=lander, 9=handheld`) is **contract** and already lives in ADR 0001 Appendix A. The
  CALLSIGN is **operator config** (`callsign_binding`, uncommitted by design). So: one pure
  `node_name(src, callsign=None, style="ssid")` in a single module citing the ADR, with the
  callsign **passed in** by the caller — one implementation, three consumers (`frame_spec`, the
  dashboard, flights publish), no second config reader.

  **For the PUBLISHED page the callsign comes from the RECORD** (`CALL` in the session log,
  already carried in `flights.json`), never from live config — see **"Published output resolves
  from the record, never from the environment"** in `CLAUDE.md`. Do not restate that rule here.

  **Unknown SRC renders as the RAW NUMBER** (`SRC:7`), never a plausible name. This is not
  cosmetic: an unknown SRC is a *tracked anomaly* (`known_src`, the anomaly counter, the
  foreign-traffic/Part-97 policy all exist to surface nodes that should not be there). Dressing
  one as a name would **suppress a safety signal the system deliberately raises**. Unmapped must
  look unmapped.

  **SSID style: SRC-matching symmetry — `1→-1, 2→-2, 9→-9`. NOT the idiomatic `-11`.**
  Recorded so a future ham does not "fix" it: APRS convention does assign **-11 to
  balloons/aircraft/spacecraft**, so a rocket would idiomatically be `KC3ZTQ-11`. But we are
  **not transmitting APRS** — the callsign is Part-97 station ID and this is borrowed notation
  for readability only. Nobody decodes it as APRS, so being **self-documenting against the wire
  format** (the SSID digit *is* the `SRC` digit) is worth more than an idiom no one will check.

  **Scheduling: build in item 3 (the redesign) ONLY if it costs nothing to carry, and DROP it the
  moment it competes with the closure bar's four questions.** It does not serve any of them —
  identity is not *capturing / how high / is this current / link healthy* — so it rides as a
  second consciously-spent exception inside an epic that is already one. **Being able to drop it
  is the test of whether the bar is real.**

  **Admission scoring: fails clause (b), not clause (a).** At a multi-node launch, telling sled
  from lander at a glance IS operational — `SRC:1` vs `SRC:2` is a decoding step under time
  pressure. It fails today only because **there is no second node yet**, so there is no evidence.
  It becomes genuinely admissible when **Epic 7** makes one exist. Cost if built: ~30 lines pure
  + 5-6 tests + three one-line call sites.
- **OLED multi-SRC page cycling.** The LIVE page currently shows ONE panel, chosen by a rule
  that is **forced, not chosen**: with rendering moved off the RX thread there is no observed
  packet whose SRC keys the display, so `_pick()` prefers a panel with `flight_open`, else the
  lowest SRC. Cycling between multiple SRCs (rocket + lander) is a redesign idea and waits for
  Epic 7 to make a second node exist.
- **Consolidate the `/run/apogee-rtc-restored` marker path — FOUR restatements, own review.**
  The clock-trust marker is written out as a literal in `ground/panel/run_panel.py`,
  `ground/clock/gate.py`, `ground/clock/restore_clock.py` and `ground/clock/attest_clock.py` — a
  live **cite-don't-restate** violation of exactly the kind the convention was adopted for
  (2026-08-01). `ground/ingest/service.py` deliberately did NOT add a fifth: it imports
  `MARKER` from `ground.clock.gate` (2026-08-02). **Consolidating the other four touches the
  FAIL-CLOSED CLOCK GATE, so it gets its own branch and its own review — do not fold it into an
  unrelated branch.** Pick one owner (`gate.py` reads it, `restore_clock`/`attest_clock` write
  it) and import everywhere else.
- **Two pre-existing pyright errors (introduced with `feat/panel-leds`, unnoticed).**
  `ground/panel/tests/test_heartbeat.py:11` — `pytest` unresolved, because pyright runs against
  an interpreter without it (`.venv-test` isn't in `pyrightconfig.json`); and
  `ground/panel/tests/test_supervisor.py:94` — `None` passed to a `float` parameter. Verified
  present on clean `main`. The repo used to report **pyright 0**, so this is drift: pyright is
  not part of any gate, and nothing ran it on that branch. Fix both, and consider adding
  `venvPath`/`venv` to `pyrightconfig.json` so the pytest import resolves.
- **A — GROUND MUST USE THE SLED'S `Max`, NOT `max(received ALT)` (ADMISSIBLE; queue after the
  OLED redesign, AHEAD of pin-the-deps).** `ground/flights/segmenter.py:78` computes
  `fl["peak_alt"] = max(fl["peak_alt"], alt)` from RECEIVED packets, while the dashboard/OLED use
  the sled's onboard `Max` (`ground/dashboard/model.py:79`). **Two peaks, two answers.** The sled
  already computes a running max at its sampling rate and transmits it in EVERY packet, so the
  ground needs any ONE post-apogee packet to be correct — whereas `max(received ALT)` loses the
  peak to a single drop at the wrong instant, silently, on the headline number of a public page.
  **Admission: passes (a)** — a corrupted published record. **Passes (b)** — not an observed wrong
  number (F1 agrees at -74 by luck) but a demonstrably present mechanism: F1 lost 1 of 76 packets
  (1.32%) and loss near apogee is the likely case. A signal that actively lies; the lie has not
  been called yet.
  **TRAP — `Max:0` is not a sentinel.** The firmware sends `Max:0` before launch and **0 is a
  valid altitude**. Naively maxing `Max` over F1 yields `0`, which against baseline -84 would
  publish **+84 ft AGL** for a flight that reached 10. Any switch MUST ignore `Max` while `St==0`.
  Cost: ~10 lines + tests, no firmware, no airtime, no ADR change.
- **B-decoupled — SEPARATE THE SAMPLE RATE FROM THE TX RATE IN `loop()`.** Today they are the
  same thing: `firmware/src/main.cpp` `loop()` reads BMP+ADXL, updates the detectors, transmits,
  then `delay(1000)`. One loop = one sample = one packet, so the detectors see **1 sample/second**
  — which is why the 2026-07-08 shake test's 2.2 g hand-jerk was missed between samples. Sample
  at ~20 Hz and transmit every 20th iteration: detectors and onboard `Max` run at 20 Hz, airtime
  is unchanged, no hardware, no wire-format change. ~15 lines.
  **Note the chicken-and-egg that kills the simpler idea:** a `St`-dependent TX rate (the Epic 6
  rider) canNOT improve launch detection, because you must DETECT launch to switch rates and
  detection runs at the slow rate. It improves boost/coast profile fidelity only.
  **AIRTIME FACTS (measured 2026-08-02, not estimated).** SF7 / BW125 / CR4/5, real payload
  82-88 B (+4 RadioHead) ~= 92 B -> **ToA 159 ms**, **max ~6.3 packets/s**, **duty at 1 Hz =
  15.9%**. So **10 Hz is NOT achievable at this config** — 5 Hz (79% duty) is the ceiling; 10 Hz
  would need BW250 (-3 dB) or a shorter boost-mode payload (-> ADR bump). SF trade, ~2x airtime
  per step for ~+2.5 dB: SF8 287 ms / 3.5 per s · SF9 513 ms / 2.0 · SF10 944 ms / 1.06.
  **Part 97 under KC3ZTQ: NO duty-cycle regulation applies** (that is an EU 868 ISM rule). The
  only limits are airtime, link budget, and the 10-minute station ID already handled.
- **C — onboard high-rate logging (NICE-TO-HAVE, NOT on the honesty path).** **A + B-decoupled
  already make the published peak accurate to 20 Hz sampling and effectively loss-proof** (it
  needs one post-apogee packet). Peak is the only published figure at risk — duration is
  timestamp-derived, loss% is SEQ-derived, RSSI is link-side. **So logging buys the high-rate
  CURVE, not honest NUMBERS.**
  **Memory, measured from the build (`pio run -e feather_m0_tx`), not the datasheet:** SAMD21G18A,
  32,768 B SRAM / 262,144 B flash, no SD, no SPI flash. Static use **5,736 B (17.5%)**, flash
  55,868 B (21.3%) — so ~27 KB nominally free, but the Arduino SAMD linker reserves **8 KB of
  stack**, leaving **~18.8 KB safely usable**. ~206 KB of flash is unused.
  **Record budget for a ~120 s L1 flight:** at a FIXED rate, time is implicit in the index (saves
  4 B/sample). 2,400 samples @ 4 B (`alt`,`g`) = 9,600 B (fits); @ 6 B (+`pg`) = 14,400 B (tight);
  @ 8 B = 19,200 B (over). **MIXED RATE WINS BY 3-6x:** 20 Hz through boost+coast (15 s = 300) +
  1 Hz under chute (85 s = 85) = **385 samples; at 8 B with an explicit timestamp = 3,080 B**,
  leaving ~15.7 KB margin.
  **Two catches.** (1) **SRAM is volatile and the loss window IS the danger moment** — a brownout
  or reset on LANDING SHOCK destroys the record, which is disqualifying for "the record" and fine
  for "a chart". Mitigation: dump to flash **at apogee**, not at landing — the vehicle is quietest
  and boost+coast is already complete. (2) **USB download after every flight** is friction and a
  manual step that will eventually be forgotten (same reliability shape as remembering to
  re-render `_freeze`), plus a firmware command handler and a ground-side import path.
  **Storage model if ever built:** NOT a fourth writer — a new **immutable derivation input**
  (`index = f(session, ops, recovered?)`), so one-writer-per-file survives and byte-identical
  rebuild survives provided the recovered file is immutable and versioned. **Never merge it into
  the session log**, which must keep meaning "what the ground heard" or the link record is
  destroyed. **`SEQ` is the join key** (the onboard clock is `millis()`, the ground's is wall
  time). **Provenance is mandatory** — each value must record air-vs-card, or a recovered peak is
  indistinguishable from a received one.
- **C2 — RADIO DUMP of the in-RAM high-rate buffer (refinement of C; still NOT on the honesty
  path).** Buffer 20 Hz in RAM, replay it over the radio DURING DESCENT, no flash and no USB step.
  Strictly better than C: it removes the manual download and the landing-shock bet. **But with
  B-decoupled, onboard `Max` is already 20 Hz-accurate and transmitted every packet, so the dump
  improves ZERO published numbers.** It buys the CURVE between samples. Work estimate: **5-10x A**
  (firmware ring buffer + chunked dump protocol + ADR amendment + decoder frame-type classifier +
  ground collector + join/validate + coverage-aware derivation + hash provenance) for no accuracy
  gain. Build only if the high-rate curve is wanted for its own sake.
  **DUMP DURING DESCENT, not after landing.** Landing is the worst moment — vehicle horizontal,
  antenna in grass, max downrange, possibly behind terrain — and landing shock is the event most
  likely to brown out the MCU, so post-landing dumping bets the record on surviving the riskiest
  event first. Under chute: ~85 s, high, line-of-sight, slow and roughly upright (better antenna
  orientation than tumbling coast), with boost+coast already complete in the buffer. Residual
  volatility risk shrinks from "landing shock" (likely) to "brownout during boost" (much less so).
  **Limits:** a 500 ft flight gives a ~28 s descent = one pass only; **a chute failure gives ~10 s
  ballistic and essentially no dump** — precisely the flight you would most want it from.
  **AIRTIME (measured 2026-08-02).** 3,080 B binary -> 4,108 chars base64 (+33%). RadioHead allows
  **251 B frames** vs the 92 B used today, which more than compensates: **21 packets, ToA 394 ms,
  8.3 s total**. Descent budget: 1x = 9.7% duty, **3x = 29.2% (+15.9% live = 45.1%)**. Three
  redundant passes fit comfortably.
  **It is a JOIN, not a merge — one authoritative source per field.** LINK fields (RSSI, loss,
  timing) come from the session ONLY and always: the vehicle cannot know its own RSSI. VEHICLE
  fields (alt, g, pg) come from the dump where covered AND validated, else the session. The
  session log must keep meaning "what the ground heard" or the link record is destroyed.
  **SEQ join:** do NOT infer anchors — the firmware knows `(buffer_index, SEQ)` at TX time and
  must record them explicitly; inference breaks on any skipped or delayed TX. SEQ wrap is a
  non-issue within a flight (65535 at 1 Hz = 18.2 h); guard with a monotonicity check, and a
  decreasing SEQ invalidates the join. **Start buffering AT LAUNCH DETECT** so the buffer can
  never start mid-flight, plus a ~2 s / 40-sample / 320 B pre-launch ring to capture the launch
  transient that 1 Hz detection misses entirely.
  **OVERLAP IS A FREE INTEGRITY CHECK — and must FAIL CLOSED.** Transmitted samples appear in both
  records and must agree exactly. On any mismatch, invalidate the JOIN (not just the sample), fall
  back to session-only derivation, and record the mismatch count in the index. A partially-trusted
  dump is the worst option: you cannot tell which half lied.
  **PARTIAL DUMPS:** per-time-range authority, and **which chunks arrived must be recorded in the
  dump artifact itself**, not reconstructed at rebuild time — otherwise "which source won where"
  depends on when you rebuilt and determinism is gone.
  **BYTE-IDENTICAL REBUILD SURVIVES — but only with a HASH.** The index must record the dump's
  content hash AND coverage, not merely that one was used. Without it, a session-only rebuild and
  a with-dump rebuild both claim to be *the* rebuild of that flight and nothing distinguishes
  them. `index = f(session, ops, dump?)` is a function only if `dump?` is identified.
  **PROTOCOL — the real trap, and it is worse than an ADR question.** ADR-0001's "unknown tags
  ignored" clause is exactly what makes this unsafe: a dump frame with no `ALT`/`St` does not look
  like a new frame type to the current decoder, it looks like a MALFORMED TELEMETRY PACKET.
  **And if dump frames carry `SEQ` they inject into the sequence space and manufacture fake gaps
  in `LinkStats`, corrupting the published loss percentage on every dump.** So: syntactically
  additive, semantically a NEW FRAME TYPE. Needs an **ADR amendment** defining frame-type
  classification BEFORE field interpretation, and dump frames must carry their own counter, never
  `SEQ`. Likely not a `V` bump (no existing tag changes meaning) but definitely an ADR + decoder
  change.
  **LOSS FORK — looping (a) wins decisively.** 3x redundancy costs 45% duty, which is affordable,
  while a reverse link (b) costs: a TX path on the Pi (the driver is RX-only today), a Part 97 ID
  obligation once the ground station transmits, a half-duplex conflict during the most valuable
  telemetry window, a sled RX window competing with sampling, and it forfeits the quietly valuable
  property that the ground station currently CANNOT transmit. Improve (a) by interleaving chunks
  with live telemetry and rotating chunk order between passes, so the three passes fail
  independently against fading instead of all missing the same fade.
- **BLOCKER ON EPIC 6 (`CALL` beaconing) AND LIKELY EPIC 7 (lander) — a frame missing `SEQ`
  or `ALT` corrupts published numbers catastrophically. MEASURED 2026-08-02 through the REAL
  consumer path.**
  **CORRECTION to an earlier entry in this file:** the defect is NOT partial mutation in
  `FlightSegmenter.observe()`. That path is UNREACHABLE from the live flow, because
  `ground/flights/live.py:38-39` already coalesces. The first demonstration called `observe()`
  directly and bypassed the very guard that exists — a badly constructed test, corrected here.
  **The real defect is SENTINEL COALESCING — `None -> 0`, where `0` is a VALID value for both
  fields.** `on_observation` does `f.get("ALT") if ... else 0` and `f.get("SEQ") if ... else 0`.
  Consequences, measured on identical received frames with one beacon substituted mid-flight:
  | field | telemetry | CALL beacon |
  |---|---|---|
  | `packets_lost` | 0 | **65,536** (`gaps += (0 - last_seq - 1) % 65536` wraps) |
  | `peak_alt_ft` (F1-shaped, negative raw) | -74 | **0** |
  | published peak AGL | 10 ft | **84 ft** |
  `loss_pct` would read ~100%. The `+84` is the SAME shape as the `Max:0` trap in the `Max`
  item — different code path, identical cause: a sentinel that collides with a legal value.
  **NOT LIVE TODAY.** Three gates prevent it: `firmware/lib/packet/packet.cpp` emits `SEQ` and
  `ALT` unconditionally; the RX driver is CRC-enforcing so truncated frames never decode; and
  foreign-SYS / unknown-SRC are filtered upstream. It arrives with **beaconing (Epic 6)** and
  plausibly the **lander (Epic 7)**, whose packet carries BME/APDS fields and may omit `ALT`.
  **Fix:** stop coalescing. `observe()` should take optional values and SKIP the fields it cannot
  compute, while advancing `last_seq` only when a real `SEQ` is present. Bundle with the `Max`
  item — same trap, same module, one review. **Defence in depth, separately worth doing:** make
  `observe()` atomic (compute, then commit) so no future raise can leave half-mutated state.
- **`ObserverRegistry.dispatch` swallows consumer failures with NO counter and NO log.** The
  isolation is correct and deliberate (D4: one bad consumer must never take down the radio loop),
  but `except Exception: pass` means a consumer can fail on EVERY packet and nothing anywhere
  says so. It hides failures in every consumer — OLED, dashboard, LiveFlights.
  **Wiring assessment — do NOT route this to RED.** RED means exactly one thing: NOT RECORDING.
  A consumer failure does not stop recording: the session log is written by `sink` inside
  `core.handle`, **not** through the registry, so raw packets still land durably and an offline
  `rebuild` still yields a correct index. Firing RED on a consumer error would make it lie while
  recording is fine. It also must NOT be used to "activate" RED's INERT write-failure leg — that
  leg needs the queue-backed WRITER's health flag, the actual not-recording condition; substituting
  a different signal would make RED mean two things and neither precisely, on the highest-stakes
  indicator on the panel.
  **Correct home:** a `consumer_errors` counter (per-observer) in the ingest heartbeat state file
  as DATA, plus the dashboard health dict alongside `decode_errors`, plus journald. Counted and
  visible, not an LED. Makes a whole class of future consumer bugs self-reporting.
- **FRAME CLASSIFICATION IS ALREADY HAPPENING, SIX TIMES, UNOWNED (census 2026-08-02).** REPLACES
  the earlier three-site framing. Every site independently re-guesses "is this frame telemetry?"
  from whichever field it happens to need:
  | # | Site | Predicate | Silently does to a failing frame |
  |---|---|---|---|
  | A | `flights/live.py:32-39` | **none** | everything reaches the segmenter; `ALT`/`SEQ` coerced to 0 |
  | B | `flights/derive.py:45` | `St is not None` | **dropped — no counter, no event, no log** |
  | C | `ingest/core.py:78` | `"SEQ" in f` | skipped for loss accounting (right outcome, unnamed) |
  | D | `ingest/core.py:61,83` | `unknown.get("CALL")` | inverse classifier; also fires on telemetry frames |
  | E | `dashboard/model.py:57-59` | `SRC is None -> return` | a beacon HAS `SRC`, so it passes and clobbers the panel |
  | F | `flights/export.py:20` | `type=="packet"` + src match | **emits an all-null row into the PUBLISHED per-flight CSV** |
  **Row F is the strongest beaconing evidence we have** — VERIFIED by running it: a beacon inside a
  flight's window becomes a CSV row with all eleven telemetry columns null, in the file the public
  flights page plots. Only census row reaching a public artifact.
  **Rows A and B are the same decision made twice, and they DISAGREE** on identical input —
  undetected for the whole of Epic 4. So `draft-0004` is **replacement, not addition**.
  **Instructive contrast:** `core.py:63,70` gate on SYS/SRC policy and get it RIGHT — a failing
  frame is counted (`foreign`, `anomalies`) AND written as an advisory event. Network-policy
  failures are surfaced; frame-shape failures are not. Hence: **a frame that fails classification
  must be counted and surfaced, never silently dropped**, or the amendment relocates row B's silence.
  **Forward mis-fire:** an Epic 7 lander frame (`SRC:2`, no `St`) is silently dropped from flight
  derivation — no anomaly, no event, no error. Same class as `ObserverRegistry.dispatch`'s bare
  `except Exception: pass`: correct-in-intent isolation that discards the evidence it fired.
- **ARCHITECTURE CLASS — "sentinel colliding with a legal value". The v1 wire format has no way
  to express ABSENT distinctly from ZERO, and every ground consumer that coalesces `None -> 0`
  inherits it.** Three instances found so far are one defect shape, not three bugs: `Max:0` sent
  pre-launch (0 is a valid altitude), `SEQ -> 0` on an absent tag (0 is a valid sequence number),
  `ALT -> 0` on an absent tag (0 is a valid altitude).
  **TARGETED SWEEP of `ground/` (2026-08-02) — the blast radius is SMALL and bounded:**
  | site | path | coalesces | verdict |
  |---|---|---|---|
  | `flights/live.py:38-39` | live | `ALT->0`, `SEQ->0` | **LOAD-BEARING** |
  | `flights/derive.py:62-63` | **offline rebuild** | `ALT->0`, `SEQ->0` | **LOAD-BEARING** |
  | `oled/render.py:19` | display | `seq_loss_pct->0` | cosmetic (uses `--` for RSSI but `0` for loss) |
  | `oled/spec.py:132` | sort key | `src->0` | safe — panels always carry `src` |
  | `dashboard/model.py:118-119`, `publish/data.py:29`, `linkstats.py:39-44` | counters | `->0` | safe — counters legitimately start at 0 |
  No `or 0` anywhere. **The DECODER is clean**: absent tags never enter `fields`, so
  `fields.get("ALT")` correctly returns `None`. Every instance is DOWNSTREAM coalescing.
  **CORRECTION (2026-08-02, after `fcdc86a` claimed otherwise): the offline REBUILD was NEVER
  exposed to a bare beacon.** `derive.py:45` admits only records where `fields.get("St") is not
  None`, and a bare `CALL` beacon carries no `St`, so it is dropped before segmentation. The
  corruption is **LIVE-PATH ONLY**. `fcdc86a` asserted a second broken site *without running it* —
  the same failure as the earlier `observe()`-direct demonstration, one level up. **An agent
  checking the claim caught it**, and it would otherwise have been carried forward as fact.
  The honest framing is sharper than the wrong one: the LIVE record contradicts what a REBUILD
  produces from the same session, so `flight_close` and `flights-snapshot.json` disagree with the
  canonical index. Both coalescing sites are still worth fixing — a genuine telemetry frame that
  carries `St` but omits `ALT` is legal under ADR 0001 and hits `derive.py:62-63` for real.
  ~~The offline REBUILD has the same defect as the live path~~ — so a session log containing one
  beacon reproduces `packets_lost = 65,536` on every `flights rebuild`, **byte-identically**.
  Determinism does not protect against a wrong sentinel; it reproduces the wrong number
  faithfully, and rebuild is what regenerates the PUBLISHED index. Any fix must land in BOTH
  sites or live and rebuild will silently disagree.
  **OPEN QUESTION FOR ADR-0001 — state it, decide it deliberately, do NOT answer it in passing.**
  Should the wire format gain an explicit ABSENT representation, or is "the ground never
  coalesces" a sufficient rule? Arguments both ways: a wire-level absent marker costs airtime on
  every packet and touches the locked v1 contract (the e2e fixture gate protects it); a
  ground-side rule costs nothing but must be re-enforced at every new consumer forever, and has
  already been violated twice in two modules. **This arrives again with Epic 7**: the lander
  carries BME/APDS fields and may legitimately omit `ALT`, so a node whose packets have no
  altitude is a REAL case, not a hypothetical. Decide before Epic 7 wiring, not during.
- **ADR amendment: classify FRAME TYPE before interpreting fields (arrives WITHOUT C2).** The
  frame-type problem is on a path we are actually taking, not a hypothetical one: `CALL`
  beaconing is an Epic 6 rider and produces exactly the no-`ALT`/no-`St` shape analysed under C2.
  ADR-0001 v1's "unknown tags ignored / missing tags valid" clauses mean such frames are
  *syntactically valid telemetry* to every consumer, which is how the loss-inflation bug above
  arises. Amendment should define a frame-type tag and require classification BEFORE field
  interpretation. Likely **not** a `V` bump (no existing tag changes meaning). Reasoning and the
  dump-frame variant are in the C2 entry — cite, do not restate.
- **`ObserverRegistry.dispatch` swallows consumer failures with NO counter and NO log.** The
  isolation is correct and deliberate (D4: a consumer must never break the radio loop), but
  `except Exception: pass` means a consumer can fail on **every packet** and nothing anywhere
  says so — which is precisely how the beacon bug above stays invisible. Add an observer-error
  counter (per-observer) surfaced in the health dict alongside `decode_errors`, so isolation
  degrades loudly instead of silently. Small, and it makes a whole class of future consumer bugs
  self-reporting.
- **`ground/flights/cli.py:53` prints `peak=Noneft` for a manually-opened flight.** Visible tail
  of the `force_open` seed change in `004744f` — seeding `peak=None` instead of a phantom `0` is
  correct (same sentinel-vs-legal-value bug in a third place, and endorsed), but the listing now
  renders a string that reads like a crash. Small and user-facing. **Fix in whichever stream
  touches `cli.py` next**; do not leave it. Trigger: any `ground/flights/` work, or the first
  person confused by the output.
- **EPIC 6 PREREQUISITES — two latent DEPLOYMENT hazards, both verified by reading the code.
  Neither is an Epic 6 line item; both must land BEFORE any relay work starts.**
  1. **`firmware/lib/apogee/apogee.h` is disqualified as a fire trigger.** It declares apogee
     on the FIRST sample not strictly greater than the running max, and `descending_` latches
     permanently. No hysteresis, no dwell, no confirmation. One noisy boost sample — turbulence,
     transonic, a pressure spike — commands a charge **at max-Q, irrecoverably**. Harmless today
     ONLY because nothing is wired to it; that is what LATENT means. Needs hysteresis + dwell +
     confirmation as a stated prerequisite of 6.2.
  2. **`firmware/src/main.cpp:89` returns from the WHOLE loop on a failed `bmp.performReading()`.**
     A deploy tick below it — including **the tick that de-energizes a relay at the end of its
     firing pulse** — would be skipped by one failed I2C read. A charge stays hot, triggered by
     exactly the condition where the safe state matters most. **Third instance of "one failure
     path takes out an unrelated responsibility"** (after OLED-on-the-RX-thread and
     `ObserverRegistry`'s silent swallow). Extra edge found on inspection: the `return` is BEFORE
     `delay(1000)`, so persistent barometer failure busy-loops at full speed — minor today,
     but combined with relay control it is a fast-spinning loop holding a hot charge.
  **`B-decoupled` is the third prerequisite** (sample at 20 Hz, transmit at 1 Hz). Re-derived
  independently: 1.11 s of physics to detect a 20 ft drop, paid at any rate; at 1 Hz a robust
  criterion costs ~4 s -> **257.6 ft fallen at 128.8 ft/s**, at 20 Hz ~1.3 s -> **27.2 ft at
  41.9 ft/s**. **THERE IS NO SAFE 1 Hz CONFIGURATION** — robust enough not to false-fire deploys
  off-vertical at speed, weak enough to fit 1 Hz IS the single-dip detector that fires at max-Q.
  That reclassifies the 1 Hz choice **from a resolution limit to a safety constraint**. The two
  caveats (BMP390's real delivered rate at the configured OSR; `COEFF_3` being a different filter
  in time at 20 Hz) gate the CONSTANTS, not the decision.
- **The baseline-unlock defect DOES NOT REPRODUCE CASUALLY — pair this with the self-correction
  entry.** The first repro attempt FAILED: with a beacon immediately after the boost frame, the
  re-lock coincidentally recomputed the same `-84` because pre-boost samples still filled the
  window after `EXCLUDE_TAIL`. It only bites once ~2+ flight altitudes are in the window. **Anyone
  checking by hand would conclude it is absent.** Yesterday's entry says *looking harder has its
  own bias*; this one says **NOT finding something is weak evidence when the bug is
  timing-sensitive**; the hollow-guard class says *finding* something is weak evidence too if the
  instrument cannot fail. Three sides of the same question: how far to trust evidence.
- **`alt=None` enters `alt_hist` in `dashboard/model.py` while `FlightSegmenter._push_alt` takes
  the OPPOSITE line — the FOURTH instance of absent-vs-zero.** A beacon pushes a `None` into the
  baseline history; `pad_baseline` skips it *inside* the window, but the `samples[:-EXCLUDE_TAIL]`
  slice happens first, so the `None` consumes a slot. Two paths disagree about whether ABSENT is a
  VALUE, in the file family just fixed. Files under the absent-vs-zero architecture class, not as
  a dashboard nicety. Trigger: the absent-vs-zero ADR decision, or any `model.py` baseline work.
- **TRAP, verbatim, for whoever reaches for the obvious fix:** a beacon blanks the dashboard peak
  tile for one frame (pre-existing, not introduced). Making `peak` **sticky** is the obvious fix
  and is a trap — **`reset_baseline` does not clear `peak`, so a sticky peak would carry one
  flight's number onto the NEXT flight's pad.** If peak is made sticky, the clear must be fixed
  in the same change.
- **A silent AGL corruption whose only tell is a blanked small field — LYING-DISPLAY class.** When
  the baseline is lost the dashboard falls back to raw ALT with only a dash in `baseline_ft` as
  the signal. Belongs on the OLED/LED surface backlog: a "RAW — no baseline" badge on the altitude
  tile, or the OLED state band. Same class as a lit flight LED after an ingest crash.
- **`beacons_rx` NOT added to the published `flights.json` schema — deferred, trigger "beaconing
  lands".** The migration-cost argument for adding it now does not hold: `write_flight_data`
  REGENERATES `flights.json` wholesale from the derived index on every publish, so there is no
  migration and no heterogeneous-record risk — adding it later costs exactly the same. Until
  beaconing exists it would read `0` for every flight and the Quarto page does not consume it.
  *(Recorded honestly: the premise was asserted without reading the file — the same failure being
  flagged elsewhere in this document all session.)*
- **OLED trend strip — DECIDABLE AFTER A FLIGHT, not open-forever.** It cannot be judged from a
  static pad state. Criterion to judge it against: with real motion it should show a **rising ramp
  through boost and coast, flatten at apogee, then a shallow steady decline under chute**,
  autoscaled to the window's own min/max so a slow descent still shows slope. **If it reads as a
  flat smear during descent the autoscale is not earning the 10 px and the strip should be CUT** —
  it is the sacrificial element. Do not cut it on silence; decide after the first real flight.
- **Unit-install drift guard** (before Epic 8 replicates this config) — three systemd units
  (`apogee-ingest`, `apogee-rtc-restore`, `apogee-attest`) are **versioned in `ground/ingest/`
  but execute from `/etc/systemd/system/`**, with a hand-recreate step on SD rebuild. Same
  "right in the docs, wrong on the machine, found under stress" failure class the escape-hatch
  cwd bug was. Cheap fix: either a **verify-installed-units-match-repo check** (diff installed
  `apogee-*.service` against the repo copies; run at deploy/boot or as a test) **or** a single
  sanctioned `install-units.sh` (copy + `daemon-reload`). Not implemented — pick one when Epic 8
  needs it.
- ~~**Stale-branch cleanup pass**~~ — **DONE 2026-07-31.** 34 branches deleted (26 `feat/*`+`docs/*`,
  7 `worktree-agent-*`, plus `origin/feat/gs-bringup` and the Pi's local `feat/panel-leds`). Each
  was verified an ancestor of `origin/main` *before* deletion, then deleted with `git branch -d`
  (the safe form) — two independent checks; 0 skipped, 0 refused. Worktree registry pruned first,
  since a branch checked out in a stale worktree cannot be deleted. Mac, GitHub and Pi now carry
  **`main` only**.
- **Pi 5 RTC coin cell (Option A)** — connect a battery to the Pi 5 RTC header (J5) so `rtc0`
  keeps time and the kernel sets a correct clock at boot with no PiSugar/NTP. Cleanest, most
  robust fallback; complements (doesn't replace) the `feat/rtc-boot-restore` software path. Frank
  to order the cell. **Epic 8 rider:** the handheld (Pi Zero 2 W) has **no `rtc0` at all**, so the
  software RTC-boot-restore (Option B) is the *only* option there — replicate it to the handheld.
- **Manual flight-open/close from the live dashboard (a "log" button)** — mark flight boundaries
  at the range when the 1 Hz launch detect misses. **Not a quick add** — the dashboard is a
  read-only consumer and the ops journal is one-writer (CLI). Invariant-respecting design: a POST
  endpoint on the ingest service force-opens/closes in the **live segmenter** and writes the
  advisory to the **session log** (service-owned → one-writer preserved), thread-safe so it never
  blocks RX. Live dashboard only (the public archive is static). Its own branch/epic.
- **"KC3ZTQ RadioRocket V2" portfolio writeup** — full Stage-2 page in the site repo when the
  project wraps (or at first real flight). Raw material already in-repo: [ADR 0001](adr/0001-packet-format-v1.md)/
  [0002](adr/0002-ground-rx-driver-spidev.md), [agl-baseline-v2-audit](agl-baseline-v2-audit.md),
  [telemetry-dictionary](telemetry-dictionary.md), the Portfolio Workflow doc, this RESUME history,
  and the genesis-flight story. Links the flight-archive page as the live exhibit. **Start
  `references.bib` accumulating now** (per the workflow doc): N3VEM RadioRocket attribution,
  LoRa / Part-97 sources, BMP390 / ADXL375 / 9-DoF datasheets as consulted.

## Notes / gotchas

- **The data store on `apogee-gs` (`~/apogee-data/`) — four files, four owners.** `session-*.jsonl`
  ← the ingest service (raw capture). **`ops-journal.jsonl` ← the flights CLI** (human annotations;
  created 2026-08-01). `flights.json` ← **derivation only** — it is `rebuild` = `derive(session, ops)`
  and is rewritten wholesale, never edited (verified byte-identical across repeated rebuilds).
  **`flights-snapshot.json` ← the INGEST SERVICE** (`LiveFlights`), an advisory live snapshot —
  **do NOT hand-edit it and do not mistake it for the index**: as of 2026-08-01 it is stale
  (`duration_s 88.283`, no baseline fields — it predates AGL baseline v2), so publishing from it
  would ship wrong numbers.
- **Bench-artifact sessions:** session logs produced by bench tests (not flights) are registered
  in [`docs/bench-sessions.md`](bench-sessions.md) — the canonical, append-only provenance list so
  they aren't mistaken for real telemetry. Add a row per bench session; don't restate elsewhere.
- **Wake-on-charge = rising-edge, not presence:** `auto_power_on: true` (PiSugar, Epic 2.6's
  complement) boots the box when power is **(re)connected**, not when power is merely present —
  so `poweroff` with the charger plugged **stays off**, and **unplug→replug wakes it** (both
  verified 2026-07-27). If it wakes unexpectedly, suspect a power reconnect, not a timer. Setup +
  semantics: [`ground-station-wiring.md`](ground-station-wiring.md).
- **Real-RF golden fixture:** `ground/flights/tests/fixtures/f1_*.jsonl` is the F1 shake-test
  slice; `test_f1_golden.py` guards decode→segment→derive against real bytes. **Treat it like the
  ADR golden vector** — a change that alters F1's decoded fields or index entry is a contract break.
- **Launch detect samples at 1 Hz** (TX-coupled; `firmware/src/main.cpp` reads the ADXL once per
  `delay(1000)` loop, no FIFO/ISR). Bench hand-*jerks* fall between samples — use a **sustained
  circular swing** (>3 g held across a sample) to trip launch on the bench. See Epic 6 rider #6.
- **Standing merge gate:** the e2e check (sled TX → `ground/rx/` driver → payload matches
  the ADR fixtures) caught the newlib-nano float-printf bug that host tests could NOT —
  **keep the e2e check as a required gate for anything touching encode/decode.**
- **Session-file retention** is unbounded today (one JSONL per service start in
  `~/apogee-data/`; names are collision-proof). Fine for now — revisit rotation/pruning
  only if the ground station ever runs unattended for weeks.
- **Diagnostics:** repo carries a `pyrightconfig.json` so `ground.*` imports resolve;
  `pyright ground/` is clean (Pi-only libs + test union-access are suppressed with reasons).
- **newlib-nano `%f`:** float printf is off by default → the feather env carries
  `-Wl,-u,_printf_float` (float tags encode empty on-target otherwise, though host tests pass).
- **Feather M0 re-flashing:** first upload of a session works; re-flashes reliably need a
  **manual double-tap to bootloader** (SAM-BA flake). See memory `feather-m0-flash-double-tap`.
- **Ground data on the Pi** (not in repo): session logs `~/apogee-data/session-*.jsonl`
  (service-written) + `flights-snapshot.json` (disposable derivation cache). The old
  `rx_test.py` / `rx_driver_check.py` scratch scripts were deleted in the 4.2 branch.
- **One radio owner:** `apogee-ingest.service` owns SPI continuously — stop it
  (`sudo systemctl stop apogee-ingest`) before any direct radio work; never a second owner.
- **Service runs from `~/gs-venv`:** `ExecStart` points at `~/gs-venv/bin/python` (the OLED
  needs `luma.oled`, which system `python3` lacks). An **SD-card rebuild must recreate
  `~/gs-venv` with `--system-site-packages`** and pip-install `luma.oled` (`flask`/`spidev`/
  `lgpio` come through system-site). If the venv is missing the unit fails to start —
  system `python3` is no longer a drop-in substitute.
