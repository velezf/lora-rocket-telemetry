# Epic 6 — Relay deployment: implementation plan

**Status: PROPOSAL. Nothing here is built. No code was written for this document.**

Epic 6 is the only safety-critical epic and the one that actually unblocks flying
([`PROJECT_PLAN.md`](PROJECT_PLAN.md) Epic 6; ordering rationale in
[`RESUME.md`](RESUME.md) "Epic order: 6 before 7"). This plan breaks it into
branch-sized units, specifies the arm-pin state machine, analyses fail-safe
behaviour against this project's existing fail-closed precedents, and makes the
one-event-vs-apogee-plus-main call.

---

## 0. Base commit and what it could not see

**BASE COMMIT: `44a0334`** — `merge: absent-is-not-zero — sled Max as peak source,
sentinel coalescing removed` (= `origin/main` and `main` at the time of writing).

Per the "Parallel agents — the canonical rules" rule 8, everything below is valid
**relative to that commit**. What it could not see:

| Blind spot | Consequence for this plan |
|---|---|
| **`CLAUDE.md` at `44a0334` has no "Parallel agents" section.** It exists only on branch `feat/oled-redesign` (`e4d1af0`). | Read from that ref explicitly; the rules were followed. Flagging it because a reader on `main` will not find the section this document cites. |
| **`B-decoupled` does not exist at `44a0334`.** `grep -rn "B-decoupled" docs firmware ground` returns nothing. Its nearest ancestor on `main` is **Epic 6 firmware rider #6** ("St-dependent TX rate") plus the "Launch detect samples at 1 Hz" gotcha, both in `RESUME.md`. | The item as briefed was read from `feat/oled-redesign` (`e4d1af0`) `docs/RESUME.md` §Backlog, items **A / B-decoupled / C / C2**. Every airtime and memory figure attributed below to "measured 2026-08-02" comes from that ref, **not** from anything I ran. |
| **The session's working branch (`feat/panel-leds`, `bd9ba31`, plus untracked `ground/panel/run_panel.py` and `apogee-panel.service`) is not in this worktree.** | Panel behaviour is cited from `RESUME.md` at base, which describes it as merged. If the panel's supervisor semantics changed on that branch, §3's precedent citations may be one revision stale. |
| **No hardware.** No Feather M0 on this machine, no Pi, no relays, no e-matches. | Nothing here was executed or measured. Every number I derived myself is labelled **computed**, not measured. |

---

## 1. The three findings that shape everything else

Before the task breakdown, three things found in the code that change what Epic 6
has to be.

### 1.1 The existing apogee detector is not deployment-grade, and it has a latent bug

`firmware/lib/apogee/apogee.h` declares apogee on **the first sample that is not
strictly greater than the running max**, and latches `descending_` permanently.
That is correct-as-specified — it is a faithful port of the V1 behaviour and its
tests (`firmware/test/test_apogee/test_apogee.cpp`) pin exactly that — and it is
fine for a *telemetry* signal, where a wrong `St:2` costs a wrong badge.

As a **fire trigger** it is disqualifying: one noisy barometric sample during
boost latches apogee for the rest of the flight, and would command a charge at
max-Q. The latch also means the wrong answer is unrecoverable — there is no path
back to ascent.

**Epic 6 must not reuse this unit as-is for the fire decision.** See 6.0c.

### 1.2 The deploy tick would sit behind an early `return`

`firmware/src/main.cpp` `loop()` opens with:

```
if (!bmp.performReading()) { Serial.println("BMP read failed"); return; }
```

A single failed barometer read skips the **entire** rest of the loop. If the
deploy tick is added anywhere below that line, one failed I²C transaction skips
the tick that would **de-energize a relay at the end of its fire pulse**. A
wedged I²C bus skips it forever.

This is structurally the same defect the ground station already fixed — the OLED
rendering synchronously inside the RX loop, where "a ~$10 display fault can stop
the box's only job" (`RESUME.md` §Backlog, `feat/oled-heartbeat`, severity HIGH).
**A peripheral fault must never be able to stall the safety path.** The deploy
tick runs first, unconditionally, from a monotonic clock — never behind a sensor.

### 1.3 Sampling is coupled to transmission, so the detectors see 1 Hz

`loop()` reads BMP + ADXL, updates the detectors, transmits, then `delay(1000)`.
One loop = one sample = one packet. This is already documented at base as a
gotcha ("Launch detect samples at 1 Hz", `RESUME.md` §Notes) and as Epic 6 rider
#6, and it is why the 2026-07-08 shake test's 2.2 g hand-jerk fell between
samples. §4 assesses what it means for a **deployment** decision. Short version:
it is a prerequisite, not an optimisation.

---

## 2. Task breakdown

One branch per unit, dependency-ordered. **P** = pure host-testable logic,
buildable now with no hardware. **H** = hardware-gated. **D** = document only.

### Phase 0 — prerequisites (all buildable now)

| # | Branch | Kind | What | Depends on |
|---|---|---|---|---|
| **6.0a** | `feat/sled-sample-decouple` | P (code) / H (verify) | Separate sample cadence from TX cadence in `loop()`: sample at ~20 Hz, transmit every Nth sample. No wire change, no airtime change. This is the backlog's **B-decoupled**, **promoted to an Epic 6.2 prerequisite** — see §4. | — |
| **6.0b** | `feat/flight-profile-fixture` | P | A pure synthetic flight-profile generator in `lib/` (altitude + accel vs. time for a nominal L1 flight, parameterised: apogee, burn time, noise amplitude, sample rate) plus a harness that drives any detector at a configurable rate and **reports the sample index at which it fired**. This is the measuring instrument for every latency and false-positive claim in 6.2. Without it, the invariants are opinions. | — |
| **6.0c** | `feat/apogee-confirm` | P | A new pure `ApogeeConfirm` unit: apogee is confirmed only when altitude has been **≥ H feet below the running peak for ≥ N consecutive samples**. Replaces the single-dip criterion of §1.1 **for the fire path**; see §8 Q10 for whether telemetry `St` should also adopt it. | 6.0b |

### 6.1 — Pyro hardware

**6.1 is blocked on procurement.** `PROJECT_PLAN.md` §Hardware roster lists the
2× STEMMA relays as *[have]*, and its shopping list says the deployment
hardware — "e-matches, pyro battery, arm switch" — is a later-epic purchase not
yet made. **No 6.1 unit except 6.1a can close today.**

| # | Branch | Kind | What | Depends on |
|---|---|---|---|---|
| **6.1a** | `docs/pyro-parameters` | D | The pyro parameter table: chosen e-match (resistance, **no-fire** current, **all-fire** current, recommended fire duration), pyro battery chemistry/capacity/internal resistance, arm switch and pad-safety-pin part numbers, relay contact and **coil** ratings — each with its datasheet citation. Every number in 6.1b–6.1d and 6.2 is read from this table. **Startable now** (as a table of blanks with the citations to be filled); closeable only after procurement. | — |
| **6.1b** | `feat/relay-bench-characterisation` | H | Bench-verify the relay against 6.1a: contact rating vs. all-fire current with margin; **and coil pull-in at flight voltage** — see §8 Q2, this is the one I expect to bite. Measure the 3.3 V rail during actuation into a representative load. | 6.1a |
| **6.1c** | `feat/pyro-rail` | H | Build the fire path: **NO contact only**; pyro charges on a separate battery rail broken by the physical pad-safety pin; **external pull-down on every relay control line** (see §3 — reset safety cannot be a firmware property). | 6.1a, 6.1b |
| **6.1d** | `feat/continuity-sense` | H | Continuity sense line + the written proof that its test current is far below the e-match no-fire current. See §8 Q1; topology recommendation below. | 6.1a, 6.1c |
| **6.1e** | `docs/adr-0004-deploy-safety` | D | **ADR 0004 — deployment safety architecture.** The project's pattern is an ADR per locked, cross-cutting decision (0001 wire contract, 0002 RX driver, 0003 clock gate). The pyro topology, the arm semantics, the invariant list, and the never-uplink rule are all exactly that shape. Draft with 6.2a; ratify when 6.1b–d have evidence. | 6.1b–d, 6.2b |

**Continuity topology — a genuine fork, with a recommendation.** With the relay's
NO contact open, a sense loop that runs *through* the fire path is broken, so
continuity cannot be read in the safe state — i.e. exactly when you want to read
it. **Recommend: bridge the relay contact with a high-value resistor and sense
the resulting divider from the LOGIC rail**, so continuity is measurable with the
pyro rail safed (pin still in). Sense current is then bounded by the logic rail
and the bridge resistor, and 6.1d's job is to show that bound is orders of
magnitude below the e-match no-fire current. The same node doubles as a
**fire-side-hot detector** — which §3 needs for the welded-contact case.

### 6.2 — Deploy logic (firmware)

| # | Branch | Kind | What | Depends on |
|---|---|---|---|---|
| **6.2a** | `feat/deploy-state-machine` | P | `lib/deploy/` — the pure state machine of §2 below. States, transitions, per-channel one-shot latch, bounded fire pulse. `lib/` purity rules apply (`firmware/lib/README`): no `<Arduino.h>`, no RadioHead, `native` stays dependency-free. Time is **injected** as a monotonic millisecond argument, never read from a clock — the same discipline as the ground service's `Observation(received_at, …)`. | 6.0c |
| **6.2b** | `feat/deploy-invariants` | P | The lockouts (min-MET, min-AGL, boost inhibit) **and** the invariant suite of §2.3, driven through 6.0b's profile harness including adversarial profiles (boost-phase noise spike, sensor dropout at apogee, altitude step, arm-line glitch). | 6.2a, 6.0b |
| **6.2c** | `feat/deploy-firmware-glue` | P (code) / H (verify) | `src/` glue: arm-pin and continuity reads, relay GPIO drive, and the **tick placement fix** of §1.2 (deploy tick first and unconditional, above any sensor early-return). `setup()` drives relay pins to the de-energized state before anything else. Enable the SAMD21 watchdog (§3) and confirm BOD (§8 Q4). | 6.2a, 6.2b, 6.1c |
| **6.2d** | `feat/deploy-telemetry` | P + ground | ADR 0001 **additive** tags for deployment state, the C encoder change, the Python decoder, and the dashboard/OLED surface. Touches the keystone contract → own branch, own review, **re-runs the e2e gate** (`RESUME.md` §Notes, standing merge gate). Design in §5. | 6.2a |

### 6.3 — Ground testing

All hardware-gated. Detailed protocol and evidence standard in §6.

| # | Branch / artifact | Kind | What | Depends on |
|---|---|---|---|---|
| **6.3a** | bench-fire into a test load | H | Relay switches a resistive/lamp load standing in for the e-match; measure actual pulse width against the commanded one, and the MCU rail during actuation. | 6.1c, 6.2c |
| **6.3b** | negative-test matrix | H | Every row of §3's table exercised on the real board: unarmed-never-fires, reset while armed, reset **mid-pulse**, power-cut mid-pulse, brownout, disarm mid-flight, I²C bus pulled. | 6.3a |
| **6.3c** | closed-loop profile test | H | The real firmware, real relays, **test load in place of the e-match**, driven by a real pressure profile (chamber, elevator, or a drive up a hill) — not synthetic data. Proves the shipped binary fires when and only when it should. | 6.3a, 6.3b |
| **6.3d** | **dry flight** | H | **Fly the deployment system as a passive passenger**: logic armed, relays wired to the continuity/indicator load, **no charge fitted**, on an otherwise motor-eject flight. Compare the commanded fire MET (from the 6.2d tags) against the apogee the telemetry independently shows. **This is the only evidence that describes the real thing**; see §6. | 6.3c, 6.2d |
| **6.3e** | ground ejection test | H | Live charge, in the actual airframe, on the ground, to size the charge and confirm separation. | 6.3d |
| **6.3f** | flight-readiness checklist | D | The written pad procedure, with the pad-safety-pin rule of §3 as its headline. | 6.3e |

**Ordering note.** 6.3d (dry flight) is placed *before* 6.3e (live charge)
deliberately. It is the cheapest way to test the apogee criterion against a real
trajectory, which is the one thing no bench test can substitute for (§3, detector
false negative). Every existing "flight" in this project is a hand swing
(`RESUME.md` §First flight — "a swing, not a climb").

---

## 3. The arm-pin state machine (the core of 6.2)

### 3.1 Inputs and outputs

Pure, tick-driven. `update()` takes: `now_ms` (injected monotonic), `armed`
(debounced arm-pin level), `in_flight` (from `LaunchDetector`), `apogee_confirmed`
(from 6.0c), `agl_ft`, `met_ms`. It returns, for each channel, a single boolean:
**energize / do not energize**. Nothing else. The machine never touches a pin,
never reads a clock, never allocates.

### 3.2 States and transitions

Two-channel by construction (see §5); channel 2 is compiled out under the
one-event configuration but its logic and tests exist from day one.

```
                  ┌──────────────────────────── armed==false at ANY tick ──────────┐
                  │                                                                │
                  ▼                                                                │
             ┌─────────┐   armed                ┌─────────┐  in_flight        ┌────┴─────┐
  reset ───▶ │  SAFE   │ ─────────────────────▶ │  ARMED  │ ────────────────▶ │  FLIGHT  │
             └─────────┘                        └─────────┘                   └────┬─────┘
              outputs 0                          outputs 0                     outputs 0
                                                                                   │
                                          apogee_confirmed && met_ms>=MIN_MET_MS   │
                                          && agl_ft>=MIN_AGL_FT && !ch1.spent      │
                                                                                   ▼
             ┌──────────┐  now-t0 >= PULSE_MS   ┌───────────┐                 ┌──────────┐
             │  DESCENT │ ◀──────────────────── │ FIRING_1  │ ◀───────────────┘
             └────┬─────┘   ch1.spent = true    └───────────┘
              outputs 0                          ch1 output 1
                  │
                  │  (2-event build only) agl_ft <= MAIN_AGL_FT && ch1.spent && !ch2.spent
                  ▼
             ┌───────────┐  now-t0 >= PULSE_MS   ┌──────────┐
             │ FIRING_2  │ ─────────────────────▶│  SPENT   │
             └───────────┘   ch2.spent = true    └──────────┘
              ch2 output 1                        outputs 0, terminal
```

**Arm is a continuous enable, not a key that was turned once.** Every energize
output is `AND`ed with `armed` at **every tick**. `armed==false` immediately
forces both outputs low and the state to `SAFE`, from anywhere, including
mid-pulse.

**Flight phase survives a disarm blip; spent latches survive everything.** A
transient loss of the arm signal must not permanently disable deployment (a
one-sample glitch would otherwise cost the recovery), so `in_flight`,
`apogee_confirmed` and both `spent` flags are held across a `SAFE` excursion and
re-arming resumes at the correct phase. A `spent` channel is never un-spent short
of a reset.

**Debounce belongs in the glue, not the machine.** `armed` arrives already
debounced; the machine's contract is that it is a clean level. Testing debounce
is a separate, also-pure unit.

### 3.3 What must be IMPOSSIBLE (the invariant suite — 6.2b)

Each row is a test. They are stated as *impossibilities*, not as behaviours,
because that is what a safety argument needs.

| # | Invariant | How it is tested |
|---|---|---|
| I1 | **No channel energizes while `armed==false`** — at any tick, in any state, including mid-pulse and after apogee. | Property test: drive every reachable state, force `armed=false`, assert both outputs low on the same tick. |
| I2 | **No channel energizes before `in_flight`.** | Full 6.0b pad profile with barometric noise for 10 minutes armed on the pad: outputs never assert. |
| I3 | **No channel energizes before `apogee_confirmed`.** | Boost + coast profiles, including one with a deliberate noise spike that would trip §1.1's detector. |
| I4 | **No channel energizes before `MIN_MET_MS`** (motor-burn lockout). | Profile with a spurious early apogee at T+1 s. |
| I5 | **No channel energizes below `MIN_AGL_FT`.** | Low-altitude profile that never clears the floor. |
| I6 | **A spent channel never re-energizes.** | Post-fire profile with repeated apogee-confirm signals, arm cycling, altitude oscillation. |
| I7 | **A pulse never exceeds `PULSE_MS`** — total energized time per channel is bounded. | Tick through the pulse; assert the de-energizing tick; assert cumulative energized ticks. |
| I8 | **Channel 2 never energizes before channel 1 is spent.** | Two-event build: descent profile with `ch1.spent=false`. |
| I9 | **Channel 2 never energizes above `MAIN_AGL_FT`.** | Descent profile, assert the crossing tick. |
| I10 | **After construction (= after reset) both channels are unspent and de-energized, and the state is `SAFE`** regardless of any input on the first tick. | Construct, feed a "descending at altitude, armed" tick; assert no output. |
| I11 | **Two channels never energize on the same tick.** | Adversarial: force both conditions true. Bounds the peak coil current the rail must survive. |
| I12 | **The machine is deterministic and time-monotonic** — the same tick sequence yields the same outputs; a non-increasing `now_ms` never advances a pulse deadline. | Replay + a `millis()`-rollover profile (`unsigned long` wraps at ~49.7 days; the flight is minutes, but the *test* is free). |

### 3.4 Constants, and where they come from

`PULSE_MS`, `MIN_MET_MS`, `MIN_AGL_FT`, `MAIN_AGL_FT`, `H` (hysteresis feet),
`N` (dwell samples). **None of these can be chosen today** — see §8 Q1, Q5, Q6.
They are compile-time constants in `lib/deploy/`, cited by the tests, never
duplicated into `src/`.

---

## 4. The sampling-rate interaction — is `B-decoupled` a prerequisite?

**Yes. It should be a prerequisite of 6.2, not an optimisation.** The reasoning:

### 4.1 The physics sets a floor that sampling cannot beat

Near apogee the trajectory is parabolic and vertical velocity passes through
zero, so altitude is *flat* — which is exactly why a criterion must use a
hysteresis in feet, not a single dip. **Computed** (free fall, ignoring drag,
32.2 ft/s²): falling **5 ft** below peak takes **0.56 s**; falling **20 ft**
takes **1.11 s**. That cost is paid regardless of sample rate.

### 4.2 At 1 Hz, both branches of the fork are unacceptable

- **Keep a robust criterion** (say H = 20 ft, N = 3 consecutive samples):
  ~1.1 s physics + up to 1.0 s quantisation + 2.0 s dwell ≈ **up to ~4 s**
  post-apogee. **Computed** free-fall at t = 4 s: ~**257 ft** fallen, ~**129 ft/s**
  (~88 mph). Deploying at 129 ft/s on an L1 airframe is a real zipper/shock-load
  risk, and the airframe is by then well off vertical.
- **Weaken the criterion to survive 1 Hz** (single sample below peak — i.e. what
  `apogee.h` does today): trades lateness for false positives, and a false
  positive during boost fires at max-Q. §1.1.

There is no third branch. A 1 Hz deployment decision is either late enough to
damage the airframe or twitchy enough to destroy it.

### 4.3 At 20 Hz the same criterion costs ~1.3 s

~1.1 s physics + 0.05 s quantisation + 0.15 s dwell ≈ **1.3 s** → **computed**
~27 ft fallen, ~42 ft/s. Same robustness, a third of the delay, a fifth of the
velocity at deployment. That is a categorical difference, not a tuning gain.

### 4.4 The cost is close to zero, which settles it

Per the backlog item (read from `feat/oled-redesign` `e4d1af0`, **outside my base
commit**): sample at ~20 Hz, transmit every 20th iteration — **~15 lines, no
hardware, no wire-format change, airtime unchanged.** Measured airtime facts from
the same source (SF7/BW125/CR4-5, ~92 B → ToA 159 ms, ~6.3 packets/s ceiling,
15.9 % duty at 1 Hz) confirm the transmit side is untouched because the transmit
*rate* is untouched.

The same item records the chicken-and-egg that kills the cheaper-looking
alternative: a `St`-dependent TX rate (Epic 6 rider #6) **cannot** improve launch
or apogee detection, because you must detect the event to switch rates and
detection runs at the slow rate.

**A prerequisite costing ~15 lines, no airtime and no contract change, standing
between the current state and a safe deployment decision, is a prerequisite.**

### 4.5 What 6.0a must additionally prove (honest caveats)

Two things are asserted by "20 Hz" that nobody has measured:

1. **Can the BMP390 actually deliver ~20 Hz** at the configured oversampling
   (`BMP3_OVERSAMPLING_8X` temp / `4X` pressure in `src/main.cpp`)? If not, either
   the OSR comes down (noisier samples) or the rate does. **Measure on the board;
   do not assume.**
2. **What is the IIR filter's phase lag at 20 Hz?** `BMP3_IIR_FILTER_COEFF_3` was
   chosen against a 1 Hz sample stream. The same coefficient at 20 Hz is a
   *different filter* in the time domain, and a lagging filter directly adds to
   deployment latency — silently. 6.0a is not done until the effective lag is
   measured and folded into the §4.3 budget.

Both are hardware-gated, so **6.0a splits**: the loop restructure and the
detector-at-20 Hz tests are pure and can land now; the rate and lag measurements
gate the *constants* in 6.2b, not the branch.

---

## 5. One deployment event vs. apogee + main — the call

### The trade-off

| | One event (apogee only) | Two events (drogue at apogee + main at altitude) |
|---|---|---|
| Fire decisions | 1 | 2 |
| Second decision's input | — | **absolute AGL** — the number this system has never validated against a real trajectory |
| Drift | Full chute from apogee. **Computed** example: 1500 ft at ~15 ft/s = ~100 s aloft; a 10 mph wind carries ~1,500 ft downrange | Small drogue then main low → far less drift |
| Airframe | Single deployment | Needs a dual-deploy-capable bay/av-bay with two charge wells — **not in the hardware roster** |
| Relay 2 | **Free** — the plan's parking lot already wants it for a recovery buzzer/strobe | Committed to the main charge; parking lot notes a buzzer would then need a third switch or a MOSFET |
| Failure modes to ground-test | 1 fire path | 2, plus the interaction (main-before-drogue, main-at-apogee) |
| Worst case | No fire → ballistic | No main → drogue-only landing (survivable, hard); early main → drift anyway |

### Recommendation: **ONE event now, on a two-channel machine, with the second event a build-time flag**

Reasons, in order of weight:

1. **Epic 6 exists to unblock flying** (`RESUME.md` §NEXT). The shortest safe path
   to a first deployment flight is one charge, one decision, one failure mode.
2. **The second event's input is unvalidated.** The main charge fires on absolute
   AGL, which depends on the pad baseline, which this project has *never* exercised
   against a real climb — F1 is a hand swing whose "10 ft peak" is sensor noise
   (`RESUME.md` §First flight). Committing a pyro to a number with no flight
   evidence is precisely the pattern this project keeps removing.
3. **The airframe prerequisite is not in hand.** Dual-deploy needs hardware that
   the roster does not list; deciding "two events" today decides it on paper only.
4. **Relay 2 has a better-evidenced use.** On an L1 field a recovery aid you will
   actually use beats a drift optimisation you can manage by waiting for lower wind
   — and drift is manageable at L1 altitudes, whereas a lost rocket is not.
5. **The cost of deferring is designed to be near zero.** Build the state machine
   **two-channel from day one** (channel array, per-channel spent latch, channel 2
   gated on channel 1 spent — invariants I8/I9/I11), with `kNumEvents` a build-time
   constant. This honours the plan's own "decided at build time" language
   *literally*: adding the main becomes a `-D` flag plus 6.3e/6.3d re-runs, not a
   redesign, and the two-channel invariants get written now while the logic is
   fresh rather than bolted on later under schedule pressure.

**Revive trigger for the second event:** the first flight targeting above
~2,500 ft AGL, **or** a measured drift under full chute that exceeds the recovery
area — whichever comes first. Not "when it feels worth it".

---

## 6. Fail-safe analysis

### 6.1 The precedents this project already set

Epic 6 does not need a new safety philosophy; it needs the existing one applied to
hardware.

| Precedent | The rule it establishes | Epic 6 application |
|---|---|---|
| **The fail-closed clock gate** (ADR 0003; `year≥2024 AND (NTP OR RTC-restore marker)`) | **Absence of positive evidence = refuse.** A plausible-looking value is not evidence. | Fire requires **positive evidence of every precondition, re-evaluated at the current tick**. There is no "no reason not to fire". |
| **Panel RED, driven by a supervisor that is its own process** (`RESUME.md` §Backlog, `feat/panel-leds`) | **The reporter must survive the failure it reports.** No fresh state → drive the down pattern. | Safety must not depend on the MCU being alive: **external pull-downs** on the relay control lines and a **watchdog**. Both outlive the firmware. |
| **The heartbeat** (1 Hz timer independent of traffic; atomic temp+rename; parse-fail retains last-good and ages out) | **Liveness is a positive periodic assertion**, not the absence of errors. | The watchdog is the same shape: the deploy tick pets it; a hang stops the petting; the reset de-energizes. |
| **"Panel signals designed but INERT"** register (`RESUME.md`) | **A designed-but-inert safety signal is worse than an absent one** — the surface reads "fine" while the condition goes unshown. | Any deployment indicator (continuity, arm state, `Dep` tag) that is not wired end-to-end **goes on that register by name** before anyone treats it as a pad check. |
| **OLED render off the RX thread** (severity HIGH) | **A peripheral fault must never stall the primary job.** | §1.2 — the deploy tick runs first and unconditionally, never behind a sensor read. |
| **Evidence must describe the running artifact** (the `0xAE` reseat re-run, 2026-08-02) | Evidence collected against a *different* binary is not evidence. | §6.3 below. |

### 6.2 Failure-by-failure

| Failure | What happens | Fails safe? |
|---|---|---|
| **MCU reset** (any cause) | GPIOs go high-Z at reset. If the relay control line floats, the coil state is **indeterminate**. With an **external pull-down** on each control line, high-Z = de-energized = NO contact open = no fire. State machine restarts in `SAFE` with both channels unspent; `groundPressure` recalibrates to the *current* altitude, so `MIN_AGL_FT` is measured from the wrong zero and `LaunchDetector` needs a fresh >3 g event that will not occur under chute. | **Pyro: YES**, but **only because of the pull-down** — this is a hardware property, not a firmware one. **Recovery: NO** — a mid-flight reset means no deployment for that flight. This is the accepted trade the plan asks for ("fail-open on reset"), and it must be stated plainly rather than described as simply "safe". |
| **Brownout** | Worse than a clean reset: the MCU may execute undefined logic while the coil rail sags. Mitigation is the SAMD21 **BOD**, which must force a reset rather than allow degraded running — see §8 Q4, currently **unverified**. Self-inflicted case: **relay coil inrush on a shared rail can cause the brownout**, i.e. *the act of firing can cause the reset that prevents the second fire*. | **Only with BOD + pull-downs, both present and verified.** Today: **UNVERIFIED — treat as failing unsafe until 6.1b measures the rail during actuation and 6.2c confirms BOD.** |
| **Power loss** (battery disconnect / dead pack) | Coils de-energize, NO contacts open. The pyro rail is separate *and* broken by the pad-safety pin, so even a welded contact is inert with the pin in. | **YES**, unconditionally. This is the strongest link in the chain and it is entirely due to the NO-contact + separate-rail + physical-pin architecture. |
| **MCU hang** (infinite loop, wedged I²C) | Three `while(1)` traps already exist in `setup()` (LoRa/BMP/ADXL init failure) — harmless, since nothing is armed. **The dangerous case is a hang while a relay is energized**: the coil stays energized indefinitely, sinking current, with no path back to de-energize. Also §1.2: a failed `bmp.performReading()` skips the loop, which would skip the de-energize tick. | **NO, as currently structured.** Fixed by three things together: (1) **watchdog** with a period comfortably shorter than `PULSE_MS`, so a hang during a pulse resets → pull-downs → de-energize; (2) the §1.2 tick-placement fix; (3) `PULSE_MS` bounded in the machine (invariant I7) *and* the total energized time bounded by the watchdog independently. Software alone cannot close this. |
| **Stuck / welded relay contact** | Welded **after** firing: that channel's charge is already spent; no further consequence for that channel. Welded **before** firing (manufacturing or a previous over-current event): the charge fires **the instant the pad-safety pin is pulled** — on the pad, with people at the rocket. **This is the worst credible outcome in Epic 6.** | **NO by design; must be managed procedurally and by sensing.** Two mitigations: (a) the **fire-side-hot detector** (§2, the continuity divider read from the logic rail with the pin still in) shows a closed contact *before* anyone pulls the pin; (b) the procedural rule that headlines 6.3f: **the pad-safety pin is pulled LAST, by one person, with the pad clear, after `Dep` reads SAFE and no fire node reads hot.** |
| **Detector false positive** (apogee declared during boost) | Charge fires at max-Q → airframe destruction at altitude. | **Managed, layered, not eliminated:** launch-detect gate (I2) + `MIN_MET_MS` motor-burn lockout (I4) + `MIN_AGL_FT` floor (I5) + hysteresis-and-dwell confirmation (6.0c) — the last of which **requires 20 Hz to be both robust and timely** (§4). An accelerometer cross-check ("still boosting → inhibit") is a candidate fifth layer; see §8 Q11. |
| **Detector false negative** (apogee never confirmed) | No fire → ballistic descent → a hazard on the ground and a destroyed airframe. | **NO — this is the residual risk Epic 6 accepts.** Commercial altimeters carry a backup timer; §7 explains why one is *not* being added now, and 6.3d (the dry flight) is the mitigation: measure the criterion against a real trajectory with no charge fitted before any charge is fitted. |
| **Arm-line glitch mid-flight** | One noisy sample reads disarmed. Machine drops to `SAFE`, outputs low; flight phase and spent latches are retained; re-assert resumes at the correct phase (§3.2). | **YES** in the fire direction (a glitch can never *cause* a fire — I1), and **tolerable** in the recovery direction because phase is retained. Debounce in the glue reduces the exposure further. |
| **Continuity open at the pad** (dud e-match, broken lead) | Detected pre-flight by 6.1d, surfaced by the 6.2d tag → a **go/no-go**, not a flight failure. | **YES — provided the indicator is actually wired.** If it is not, it goes on the INERT register and **must not be called a pad check**. |

---

## 7. Ground-test protocol for 6.3, and what counts as proof

### 7.1 The evidence standard

This project's standard, stated at base in `RESUME.md` §"What the OLED fix
taught": **evidence must describe the RUNNING artifact.** The `0xAE` reseat test
was re-run because removing one byte made the deployed binary different, so the
earlier evidence no longer covered it. Frank caught that one.

Applied to Epic 6, this is not a nicety — it is the whole safety argument:

1. **Every bench result records the exact firmware it was produced by**: the git
   SHA, and the hash and size of the `.bin` from `pio run -e feather_m0_tx`.
2. **Any firmware change after a fire test invalidates that test.** Not "probably
   fine" — invalidates. A one-line change to `PULSE_MS` means 6.3a and 6.3b re-run.
3. **The binary that flies is the binary that was tested**, verified by hash, not
   by recollection of having rebuilt.
4. **A reasoned expectation is not proof.** "The pull-down means it cannot fire on
   reset" is a hypothesis; a scope trace of the control line through a reset, with
   the pyro rail simulated and a load attached, is proof.

### 7.2 What must be proven before a live charge is ever fitted

In order. Nothing below a failed row proceeds.

| Gate | Proven by | Not accepted as proof |
|---|---|---|
| **G1 — the relay can carry the fire current** | Measured contact rating vs. the 6.1a all-fire current, with margin, on the actual part | The datasheet alone, or a bench test at a different voltage |
| **G2 — the coil pulls in at flight voltage** | Actuation confirmed at the *lowest expected* flight-battery voltage, not at USB 5 V | A bench test on USB |
| **G3 — firing does not brown out the MCU** | Rail trace during actuation into a representative load | The absence of an observed reset in one trial |
| **G4 — high-Z is de-energized** | Control line + coil state observed through a real reset, brownout, and power cut, load attached | Reading the pull-down's value off the schematic |
| **G5 — unarmed never fires** | The full 6.3b matrix on the real board with a test load, including a *deliberately induced* apogee condition while disarmed | The host test suite (necessary, not sufficient — it tests `lib/`, not the wiring) |
| **G6 — reset mid-pulse fails safe** | Reset asserted *while a channel is energized*, de-energization observed | Reasoning from I7 |
| **G7 — the pulse is bounded in hardware too** | Watchdog demonstrated by hanging the firmware deliberately mid-pulse | Watchdog enabled in code |
| **G8 — the shipped logic fires when and only when it should, against a real pressure profile** | 6.3c, closed-loop, real barometer, test load | Synthetic profiles (they are 6.2b's job, and they are necessary, not sufficient) |
| **G9 — the apogee criterion is right on a real trajectory** | **6.3d, the dry flight**: commanded fire MET (from the `Dep`/`DepT` tags) vs. the apogee the telemetry independently shows | Any ground test whatsoever. There is no substitute. |
| **G10 — continuity sensing cannot fire the e-match** | Measured sense current vs. the 6.1a no-fire current, with the margin written down | The resistor value |

**Only after G1–G10 does 6.3e fit a live charge.**

### 7.3 Standing rules for the fire tests themselves

- **Test load, never a live e-match**, for every test up to and including 6.3d.
- **The pad-safety pin is the last thing removed and the first thing replaced**,
  by one person, pad clear. This rule is the headline of 6.3f.
- **Bench-fire sessions are registered** in `docs/bench-sessions.md`, the existing
  append-only provenance list, so a deployment bench session is never mistaken for
  flight telemetry.
- **The `Dep` tag must be live for 6.3c onward** — otherwise the test has no
  independent record of what the machine decided, only of what the relay did.

---

## 8. Additive telemetry — does deployment state reach the ground?

**Yes, and it is additive: no `V` bump.** ADR 0001 §Versioning is explicit —
"Additive tags are allowed WITHIN a version, without a bump"; decoders tolerate
unknown and absent tags; the version bumps only if an *existing* tag changes.
Adding deployment tags is the policy working as designed.

**Why it must reach the ground:**

- **Pad go/no-go.** Armed state and e-match continuity are pre-launch checks. The
  operator standing at the box needs them; the alternative is walking to the rocket.
- **Post-flight forensics.** "Did it command fire, and when" is the single most
  important question after a deployment flight, and it is the entire content of
  G9's proof.

**Design recommendation — latched and monotonic, not momentary:**

| Tag | Content |
|---|---|
| `Dep` | Deploy state code, **latched and monotonically non-decreasing** (safe → armed → flight → fired-1 → fired-2 → spent) |
| `DepT` | **MET in seconds at which the first fire was commanded**, latched; absent before |
| `Cont` | Continuity mask, one bit per channel |

The latched-monotonic property is the direct application of the lesson from the
merge this plan is based on (`44a0334`, "sled Max as peak source"): a running,
onboard-latched value transmitted in **every** packet needs only **one** received
packet to be correct, whereas a momentary state transmitted once is lost to a
single drop at the wrong instant. F1 lost 1 of 76 packets, and loss near apogee
is the likely case. **The fire event is the one telemetry moment where a single
lost packet is least acceptable, so it must not be a momentary signal.**

Two traps to carry over from that same merge:

- **Reserve the tag names in ADR 0001 Appendix A first.** The appendix exists
  precisely to prevent collisions, and `Dep`/`DepT`/`Cont` are multi-character per
  its naming rules. `D` and `C` are exactly the kind of single letter it warns off.
- **Do not use `0` as a sentinel.** `DepT:0` is a valid MET. Absence means "not
  fired", per the ADR's absent-tags-are-normal rule — the same `Max:0` trap the
  base commit fixed.

**LOCKED, permanently: the ground is never in the fire path.** No uplink, no
ground-commanded fire, no ground-supplied threshold. The flight computer's radio
is TX-only and stays that way; adding an RX path to the deploy logic would create
a fire path reachable by a stray or malicious packet. This belongs in ADR 0004 as
a rejected alternative with the reason attached, so it is not re-derived.

---

## 9. What is NOT in Epic 6

Each with the trigger that would revive it. (Per the parallel-agent rules, ideas
noticed during this work go here with a concrete trigger rather than being
explored inline.)

| Item | Why not now | Revive trigger |
|---|---|---|
| **Backup apogee timer** (fire at T+X if apogee never confirms) | It adds a fire path whose correctness depends on a number nobody has measured, and it *violates invariant I3* — so it cannot be bolted on without reopening the safety argument. Adding a second way to fire is the opposite of what a first deployment flight should carry. | The 6.3d dry flight showing the confirmed-apogee margin is thin, **or** a planned flight profile (high-drag, low apogee) where the criterion is predicted marginal. |
| **Second deployment event (main)** | §5. | A flight targeting above ~2,500 ft AGL, or measured drift exceeding the recovery area. |
| **Recovery buzzer / strobe on relay 2** | Already in `PROJECT_PLAN.md` §Parking lot. Named here because it **competes with the second deployment event for the same relay** — that competition is currently invisible in both documents. | The first flight recovered by search rather than by sight. |
| **Ground-commanded fire / any uplink** | §8. Not deferred — **rejected.** | None. Record it as rejected in ADR 0004. |
| **Redundant / second flight computer** | Doubles the hardware and the fire paths to defend a failure that has never occurred here. | A flight where the primary demonstrably failed to deploy. |
| **Accelerometer-based apogee cross-check** | A genuinely good fifth layer (§6.2, false positive) but it is a *new detector* with its own thresholds, and Epic 6 already has one unvalidated detector. | The barometric criterion proving marginal in 6.3d, or a false-positive-shaped anomaly in flight telemetry. |
| **Onboard high-rate logging (backlog C / C2)** | Epic 6 does not need it: the deploy decision is made onboard in real time, and `Dep`/`DepT` (§8) carry the fire event at full fidelity because they are latched. C2's own analysis (read at `e4d1af0`) already concludes it improves **zero** published numbers once B-decoupled lands. | Wanting the high-rate curve for its own sake. Not a deployment requirement. |
| **`St:3` = landed** (existing Epic 6 rider #1) | Not a deployment input. Stays a rider. | Unchanged from `RESUME.md`. |
| **Per-unit `-DSRC_ID`, ±10 % TX jitter** (riders #2, #3) | `RESUME.md` §Epic 7 closure bar already reassigns these to **Epic 7** — they stop being optional the moment a second transmitter exists. **Do not re-admit them into Epic 6.** | Unchanged. |
| **`BAT` go/no-go tag** (rider #5) | Epic 6 *raises* its value — a pyro battery is a new pad check — but it stays a rider, because the pyro battery is a separate rail and would want its own indicator anyway. | Procurement of the pyro battery (6.1a), at which point re-score it against the admission rule. |
| **Deployment on the lander** | Epic 7. | Epic 7. |
| **Fixing `apogee.h`'s single-dip latch for telemetry `St`** | It is a real defect (§1.1) but changing `St` semantics is a behaviour change to the wire-visible flight state, so it should not ride inside a safety branch. | §8 Q10 being decided. If "unify", it becomes part of 6.0c and re-runs the e2e gate. |
| **Power integrity for the flight computer** (bulk capacitance / separate MCU rail so a coil actuation cannot reset the MCU) | Might turn out to be *required* rather than optional — 6.1b's G3 measurement decides. Listed here so it is not mistaken for a hardening nicety. | G3 showing the rail sags near the BOD threshold during actuation. |

---

## 10. Open questions

Each with the decision it blocks. **Q1, Q2, Q4, Q5 and Q6 block work that is
otherwise ready to start.**

| # | Question | Blocks |
|---|---|---|
| **Q1** | **Which e-match?** Resistance, no-fire current, all-fire current, recommended fire duration. Not purchased (`PROJECT_PLAN.md` shopping list). | All of 6.1 except 6.1a's skeleton: the relay contact-rating check (G1), the continuity sense current (G10), and `PULSE_MS`. **6.1 cannot close without it.** |
| **Q2** | **Does the STEMMA relay coil pull in reliably at LiPo-sagged voltage (~3.4–3.7 V)?** The Feather M0 has no 5 V rail on battery. A relay that actuates at 5.0 V on the bench and not at 3.5 V in the air is a **silent no-fire** — the failure this project would most regret discovering in flight. | The coil-power design: direct drive vs. boost converter vs. a dedicated rail vs. replacing the relay with a low-side MOSFET. Blocks 6.1c. |
| **Q3** | **Is the airframe dual-deploy-capable** (separate drogue/main bays, two charge wells)? | Whether §5's recommendation can ever be revisited without a rebuild. Answer it now even though the recommendation is one event. |
| **Q4** | **Is SAMD21 BOD33 enabled by the Arduino SAMD core, and at what threshold?** | The brownout fail-safe claim (§6.2), which is currently **unverified**. Blocks 6.2c and G3. |
| **Q5** | **What sample rate does the BMP390 actually achieve at the configured OSR, and what is the IIR filter's phase lag at that rate?** | 6.0a's latency budget (§4.5) and therefore `H`, `N` and the whole §4.3 argument. |
| **Q6** | **What are `MIN_MET_MS` and `MIN_AGL_FT`?** They are functions of the motor's burn time and the field, neither of which is written down anywhere in the repo. | 6.2b's constants and the expected values in invariants I4/I5. |
| **Q7** | **Do the relay control lines need external pull-downs, or does the STEMMA board already provide one?** | The **entire reset fail-safe claim** (§6.2 row 1). If the answer is "the board already does", it still needs measuring, not assuming — G4. |
| **Q8** | **What does the range / club require?** `PROJECT_PLAN.md` 6.3 says "ground-tested to your range's bar", but that bar is not written down. Arming scheme, pad procedure, and whether a dry flight with relays is even permitted. | 6.1a's arm-switch choice, 6.3d's admissibility, and 6.3f. |
| **Q9** | **Where does the arm pin physically live, and is it reachable with the rocket on the rail?** | 6.1c. An arm switch that cannot be reached at the pad is not an arm switch. |
| **Q10** | **Should telemetry `St` adopt the confirmed-apogee criterion, or keep today's first-dip semantics?** Unifying gives one apogee answer per vehicle (and fixes §1.1's latch); keeping them separate means two answers on one airframe — the shape the base commit just removed from the *ground* side. My lean: **unify**, since the fire path needs extra lockouts anyway, so it is one primitive with two policies rather than two primitives. Cost: `St:2` arrives ~1–2 s later and the e2e gate re-runs. | 6.0c's scope, and whether 6.0c re-runs the e2e gate. |
| **Q11** | **Should an accelerometer "still boosting → inhibit" cross-check be a mandatory fifth layer**, or backlog (§9)? | 6.2b's layer count. Cheap to add now, expensive to add after the invariant suite is written. |

---

## 11. Summary of the recommendations

1. **`B-decoupled` is promoted from backlog optimisation to a 6.2 prerequisite**
   (6.0a). ~15 lines, no airtime cost, no contract change; without it a robust
   apogee criterion costs up to ~4 s and ~129 ft/s at deployment (computed).
2. **One deployment event now**, on a **two-channel state machine** with the
   second event a build-time flag, and an explicit revive trigger.
3. **A new pure `ApogeeConfirm`** for the fire path — the existing `apogee.h`
   single-dip criterion must never be a fire trigger.
4. **The deploy tick runs first and unconditionally**, above any sensor
   early-return — the same lesson as OLED-off-the-RX-thread.
5. **Reset safety is hardware**: external pull-downs plus a watchdog. Firmware
   cannot make itself safe while it is not running.
6. **Latched, monotonic `Dep`/`DepT`/`Cont` tags** — additive per ADR 0001, no `V`
   bump, names reserved in Appendix A first, no `0` sentinels.
7. **The ground is never in the fire path.** Rejected, not deferred.
8. **6.3d, the dry flight, before any live charge.** It is the only evidence that
   describes the real thing.
9. **ADR 0004 — deployment safety architecture**, following 0001/0002/0003.
10. **6.1 is blocked on procurement.** Everything in Phase 0 and 6.2a/6.2b is
    pure and can start today.
